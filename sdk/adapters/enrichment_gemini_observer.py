"""Observer read-only: enrichment Gemini/Flash persistido."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SDK_ROOT = HERE.parent
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from winegod_scraper_sdk import Reporter, load_manifest  # noqa: E402
from winegod_scraper_sdk.connectors import TelemetryDelivery  # noqa: E402
from .common import (  # noqa: E402
    SafeReadOnlyClient,
    count_rows,
    load_envs_from_repo,
    max_column_by_candidates,
    sum_column,
    table_exists,
)


MANIFEST_PATH = HERE / "manifests" / "enrichment_gemini_flash.yaml"
REPORTS_ROOT = Path("C:/winegod-app/reports")
STATE_PATH = REPORTS_ROOT / "gemini_batch_state.json"
INPUT_JSONL_PATH = REPORTS_ROOT / "gemini_batch_input.jsonl"
OUTPUT_JSONL_PATH = REPORTS_ROOT / "gemini_batch_output.jsonl"
ENRICHED_DIR = REPORTS_ROOT / "ingest_pipeline_enriched"


def _get_source_dsn() -> str | None:
    return (
        os.environ.get("WINEGOD_DATABASE_URL")
        or os.environ.get("DATABASE_URL_LOCAL_WINEGOD")
        or os.environ.get("WINEGOD_DB_URL")
    )


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def _count_ready_outputs(base: Path) -> tuple[int, int, int]:
    ready_total = 0
    uncertain_total = 0
    not_wine_total = 0
    if not base.exists():
        return (0, 0, 0)

    for path in base.rglob("enriched_ready.jsonl"):
        ready_total += _count_lines(path)
    for path in base.rglob("enriched_not_wine.jsonl"):
        not_wine_total += _count_lines(path)
    for path in base.rglob("enriched_uncertain_review.csv"):
        rows = _count_lines(path)
        uncertain_total += max(rows - 1, 0)
    return (ready_total, uncertain_total, not_wine_total)


def run(dry_run: bool = True, limit: int = 0) -> int:
    load_envs_from_repo()
    manifest = load_manifest(MANIFEST_PATH)
    print(f"[{manifest.scraper_id}] manifest loaded, dry_run={dry_run}")

    dsn = _get_source_dsn()

    if dry_run:
        from datetime import datetime, timezone
        from winegod_scraper_sdk.idempotency import new_uuid
        from winegod_scraper_sdk.schemas import BatchEventPayload

        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        rid = new_uuid()
        bid = new_uuid()
        BatchEventPayload.model_validate(
            {
                "batch_id": str(bid),
                "run_id": str(rid),
                "scraper_id": manifest.scraper_id,
                "seq": 0,
                "ts": ts,
                "items_extracted": 0,
                "items_valid_local": 0,
                "items_sent": 0,
                "items_rejected_notwine": 0,
                "items_uncertain": 0,
                "items_final_inserted": 0,
                "source_lineage": {
                    "source_system": "gemini_flash",
                    "source_kind": "file",
                    "source_pointer": str(STATE_PATH),
                    "source_record_count": 0,
                },
                "idempotency_key": str(bid),
            }
        )
        print(f"[{manifest.scraper_id}] dry-run OK")
        return 0

    base_url = os.environ.get("OPS_BASE_URL")
    token = os.environ.get("OPS_TOKEN")
    if not base_url or not token:
        print(f"[{manifest.scraper_id}] ERROR: OPS_BASE_URL/OPS_TOKEN missing", file=sys.stderr)
        return 2

    delivery = TelemetryDelivery.from_env(default_url=base_url)
    reporter = Reporter(manifest=manifest, delivery=delivery)
    reporter.register()
    reporter.start_run()

    try:
        state = {}
        if STATE_PATH.exists():
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

        input_lines = _count_lines(INPUT_JSONL_PATH)
        output_lines = _count_lines(OUTPUT_JSONL_PATH)
        ready_total, uncertain_total, not_wine_total = _count_ready_outputs(ENRICHED_DIR)

        flash_total = 0
        query_total = 0
        cost_total_usd = 0.0
        latest_exec = None
        if dsn:
            with SafeReadOnlyClient(dsn) as client:
                if table_exists(client, "flash_vinhos"):
                    flash_total = count_rows(client, "flash_vinhos")
                if table_exists(client, "flash_queries"):
                    query_total = count_rows(client, "flash_queries")
                    cost_total_usd = sum_column(client, "flash_queries", "custo_estimado_usd")
                    latest_exec = max_column_by_candidates(
                        client,
                        "flash_queries",
                        ["executada_em", "criada_em"],
                    )

        total_requests = int(state.get("total_requests") or input_lines or 0)
        total_wines = int(state.get("total_wines") or flash_total or 0)
        latest_seen = latest_exec or state.get("created_at") or "unknown"

        if not any(
            [
                STATE_PATH.exists(),
                INPUT_JSONL_PATH.exists(),
                OUTPUT_JSONL_PATH.exists(),
                ENRICHED_DIR.exists(),
                flash_total,
                query_total,
            ]
        ):
            reporter.event(
                code="source.unavailable",
                message="fontes locais de Gemini/Flash nao encontradas",
                level="warn",
            )
            reporter.fail(
                error_summary="source_unavailable: gemini flash artifacts missing",
                status="failed",
            )
            return 3

        source_records = flash_total or total_wines or total_requests
        reporter.heartbeat(items_collected_so_far=source_records)
        reporter.batch_metrics(
            seq=0,
            items_extracted=total_wines,
            items_valid_local=ready_total,
            items_sent=ready_total,
            items_rejected_notwine=not_wine_total,
            items_uncertain=uncertain_total,
            items_final_inserted=0,
            source_lineage={
                "source_system": "gemini_flash",
                "source_kind": "file" if not flash_total else "table",
                "source_pointer": "flash_vinhos+flash_queries+reports/gemini_batch_state.json",
                "source_record_count": source_records,
                "notes": (
                    f"requests={total_requests}; output_lines={output_lines}; "
                    f"query_total={query_total}; cost_usd={cost_total_usd:.4f}; latest_seen={latest_seen}"
                )[:256],
            },
        )
        reporter.event(
            code="gemini_flash.snapshot",
            message=(
                f"total_wines={total_wines} requests={total_requests} ready={ready_total} "
                f"uncertain={uncertain_total} not_wine={not_wine_total} output_lines={output_lines} "
                f"flash_total={flash_total} query_total={query_total} cost_usd={cost_total_usd:.4f} "
                f"latest_seen={latest_seen}"
            )[:1024],
            level="audit",
        )
        reporter.end(
            status="success",
            items_extracted=total_wines,
            items_valid_local=ready_total,
            items_sent=ready_total,
            items_final_inserted=0,
            batches_total=1,
        )
        print(
            f"[{manifest.scraper_id}] run OK total_wines={total_wines} ready={ready_total} "
            f"uncertain={uncertain_total}"
        )
        return 0
    except Exception as exc:
        try:
            reporter.event(code="observer.error", message=str(exc)[:500], level="error")
            reporter.fail(error_summary=str(exc)[:1000], status="failed")
        except Exception:
            pass
        print(
            f"[{manifest.scraper_id}] run failed: {type(exc).__name__}: {str(exc)[:200]}",
            file=sys.stderr,
        )
        return 5


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.apply and args.dry_run:
        print("--apply and --dry-run are mutually exclusive", file=sys.stderr)
        return 1
    return run(dry_run=not args.apply, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
