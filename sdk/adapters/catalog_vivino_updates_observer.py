"""Observer read-only: Vivino catalog updates persistidos."""
from __future__ import annotations

import argparse
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
    count_recent_rows_by_candidates,
    count_rows,
    load_envs_from_repo,
    max_column_by_candidates,
    table_exists,
)


MANIFEST_PATH = HERE / "manifests" / "catalog_vivino_updates.yaml"


def _get_source_dsn() -> str | None:
    return (
        os.environ.get("VIVINO_DATABASE_URL")
        or os.environ.get("DATABASE_URL_LOCAL_VIVINO")
        or os.environ.get("VIVINO_DB_URL")
    )


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
                "items_final_inserted": 0,
                "source_lineage": {
                    "source_system": "vivino_db",
                    "source_kind": "table",
                    "source_pointer": "vivino_vinhos+vivino_execucoes",
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

    if not dsn:
        reporter.event(
            code="source.unavailable",
            message="VIVINO_DATABASE_URL nao configurado",
            level="warn",
        )
        reporter.fail(
            error_summary="source_unavailable: VIVINO_DATABASE_URL not set",
            status="failed",
        )
        return 3

    try:
        with SafeReadOnlyClient(dsn) as client:
            if not table_exists(client, "vivino_vinhos"):
                reporter.event(
                    code="source.schema_missing",
                    message="vivino_vinhos ausente",
                    level="error",
                )
                reporter.fail(
                    error_summary="source_schema_missing: vivino_vinhos",
                    status="failed",
                )
                return 4

            total_wines = count_rows(client, "vivino_vinhos")
            recent_updates_7d = count_recent_rows_by_candidates(
                client,
                "vivino_vinhos",
                ["atualizado_em", "reviews_atualizado_em", "sabor_atualizado_em"],
                hours=24 * 7,
            )
            executions_total = count_rows(client, "vivino_execucoes") if table_exists(client, "vivino_execucoes") else 0
            latest_exec = (
                max_column_by_candidates(
                    client,
                    "vivino_execucoes",
                    ["concluido_em", "iniciado_em"],
                )
                if executions_total
                else None
            )

        reporter.heartbeat(items_collected_so_far=total_wines)
        reporter.batch_metrics(
            seq=0,
            items_extracted=total_wines,
            items_valid_local=total_wines,
            items_sent=total_wines,
            items_final_inserted=0,
            source_lineage={
                "source_system": "vivino_db",
                "source_kind": "table",
                "source_pointer": "vivino_vinhos+vivino_execucoes",
                "source_record_count": total_wines,
                "notes": (
                    f"recent_updates_7d={recent_updates_7d}; executions_total={executions_total}; "
                    f"latest_exec={latest_exec or 'unknown'}"
                )[:256],
            },
        )
        reporter.event(
            code="catalog.snapshot",
            message=(
                f"wines={total_wines} recent_updates_7d={recent_updates_7d} "
                f"executions_total={executions_total} latest_exec={latest_exec or 'unknown'}"
            )[:1024],
            level="audit",
        )
        reporter.end(
            status="success",
            items_extracted=total_wines,
            items_valid_local=total_wines,
            items_sent=total_wines,
            items_final_inserted=0,
            batches_total=1,
        )
        print(f"[{manifest.scraper_id}] run OK wines={total_wines}")
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
