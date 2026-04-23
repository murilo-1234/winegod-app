"""Observer read-only: CellarTracker persistido em winegod_db."""
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
    first_existing_column,
    list_tables,
    load_envs_from_repo,
    max_column_by_candidates,
    table_exists,
)


MANIFEST_PATH = HERE / "manifests" / "scores_cellartracker.yaml"


def _get_source_dsn() -> str | None:
    return (
        os.environ.get("WINEGOD_DATABASE_URL")
        or os.environ.get("DATABASE_URL_LOCAL_WINEGOD")
        or os.environ.get("WINEGOD_DB_URL")
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
                    "source_system": "cellartracker",
                    "source_kind": "table",
                    "source_pointer": "ct_vinhos+ct_queries+ct_exec_*",
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
            message="WINEGOD_DATABASE_URL nao configurado para CellarTracker",
            level="warn",
        )
        reporter.fail(
            error_summary="source_unavailable: WINEGOD_DATABASE_URL not set",
            status="failed",
        )
        return 3

    try:
        with SafeReadOnlyClient(dsn) as client:
            if not table_exists(client, "ct_vinhos"):
                reporter.event(
                    code="source.schema_missing",
                    message="ct_vinhos ausente",
                    level="error",
                )
                reporter.fail(error_summary="source_schema_missing: ct_vinhos", status="failed")
                return 4

            total_wines = count_rows(client, "ct_vinhos")
            queries_total = count_rows(client, "ct_queries") if table_exists(client, "ct_queries") else 0
            score_rows = client.fetchone(
                "SELECT count(*) FROM public.ct_vinhos WHERE ct_score IS NOT NULL"
            )
            wines_with_score = int(score_rows[0] or 0) if score_rows else 0
            drink_rows = client.fetchone(
                """
                SELECT count(*)
                FROM public.ct_vinhos
                WHERE ct_drink_window IS NOT NULL AND trim(ct_drink_window) <> ''
                """
            )
            wines_with_drink_window = int(drink_rows[0] or 0) if drink_rows else 0
            latest_seen = max_column_by_candidates(
                client,
                "ct_vinhos",
                ["atualizado_em", "descoberto_em"],
            )

            exec_tables = list_tables(client, "ct_exec_%")
            progress_tables = list_tables(client, "ct%progress")
            exec_total = 0
            recent_execs_7d = 0
            latest_exec = None
            for table_name in exec_tables:
                exec_total += count_rows(client, table_name)
                recent_execs_7d += count_recent_rows_by_candidates(
                    client,
                    table_name,
                    ["executada_em", "criada_em", "atualizado_em"],
                    hours=24 * 7,
                )
                table_latest = max_column_by_candidates(
                    client,
                    table_name,
                    ["executada_em", "criada_em", "atualizado_em"],
                )
                if table_latest and (latest_exec is None or table_latest > latest_exec):
                    latest_exec = table_latest

            progress_rows = 0
            for table_name in progress_tables:
                progress_rows += count_rows(client, table_name)

        observed_total = total_wines + queries_total + exec_total + progress_rows
        reporter.heartbeat(items_collected_so_far=observed_total)
        reporter.batch_metrics(
            seq=0,
            items_extracted=total_wines,
            items_valid_local=wines_with_score,
            items_sent=wines_with_score,
            items_final_inserted=0,
            source_lineage={
                "source_system": "cellartracker",
                "source_kind": "table",
                "source_pointer": "ct_vinhos+ct_queries+ct_exec_*",
                "source_record_count": observed_total,
                "notes": (
                    f"queries_total={queries_total}; exec_total={exec_total}; "
                    f"recent_execs_7d={recent_execs_7d}; progress_rows={progress_rows}; "
                    f"latest_seen={latest_seen or latest_exec or 'unknown'}"
                )[:256],
            },
        )
        reporter.event(
            code="cellartracker.snapshot",
            message=(
                f"wines={total_wines} with_score={wines_with_score} "
                f"with_drink_window={wines_with_drink_window} queries={queries_total} "
                f"exec_total={exec_total} recent_execs_7d={recent_execs_7d} "
                f"progress_rows={progress_rows} latest_seen={latest_seen or latest_exec or 'unknown'}"
            )[:1024],
            level="audit",
        )
        reporter.end(
            status="success",
            items_extracted=total_wines,
            items_valid_local=wines_with_score,
            items_sent=wines_with_score,
            items_final_inserted=0,
            batches_total=1,
        )
        print(
            f"[{manifest.scraper_id}] run OK wines={total_wines} scored={wines_with_score} "
            f"exec_tables={len(exec_tables)}"
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
