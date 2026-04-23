"""Observer read-only: Amazon local persistido neste host."""
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
    count_distinct,
    count_recent_rows_by_candidates,
    count_rows,
    load_envs_from_repo,
    max_column_by_candidates,
    sum_column,
    table_exists,
)


MANIFEST_PATH = HERE / "manifests" / "commerce_amazon_local.yaml"
AMAZON_ROOT = Path("C:/natura-automation/amazon")


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
                    "source_system": "amazon_local",
                    "source_kind": "table",
                    "source_pointer": "amazon_queries+amazon_categorias+amazon_reviews",
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

    if not AMAZON_ROOT.exists():
        reporter.event(
            code="source.path_missing",
            message=f"{AMAZON_ROOT} ausente",
            level="warn",
        )
        reporter.fail(
            error_summary="source_unavailable: amazon local path missing",
            status="failed",
        )
        return 3

    if not dsn:
        reporter.event(
            code="source.unavailable",
            message="WINEGOD_DATABASE_URL nao configurado para Amazon local",
            level="warn",
        )
        reporter.fail(
            error_summary="source_unavailable: WINEGOD_DATABASE_URL not set",
            status="failed",
        )
        return 4

    try:
        with SafeReadOnlyClient(dsn) as client:
            required_tables = ["amazon_queries", "amazon_categorias", "amazon_reviews"]
            missing = [name for name in required_tables if not table_exists(client, name)]
            if missing:
                reporter.event(
                    code="source.schema_missing",
                    message=f"missing tables: {', '.join(missing)}",
                    level="error",
                )
                reporter.fail(
                    error_summary=f"source_schema_missing: {', '.join(missing)}",
                    status="failed",
                )
                return 5

            total_queries = count_rows(client, "amazon_queries")
            total_categories = count_rows(client, "amazon_categorias")
            total_reviews = count_rows(client, "amazon_reviews")
            recent_queries_24h = count_recent_rows_by_candidates(
                client,
                "amazon_queries",
                ["executado_em", "criado_em"],
                hours=24,
            )
            items_found_total = int(sum_column(client, "amazon_queries", "itens_encontrados"))
            wines_new_total = int(sum_column(client, "amazon_queries", "vinhos_novos"))
            credits_used_total = int(sum_column(client, "amazon_queries", "creditos_usados"))
            countries_total = count_distinct(client, "amazon_queries", "pais_codigo")
            latest_seen = max_column_by_candidates(
                client,
                "amazon_queries",
                ["executado_em", "criado_em"],
            ) or max_column_by_candidates(
                client,
                "amazon_categorias",
                ["ultimo_scraping"],
            ) or max_column_by_candidates(
                client,
                "amazon_reviews",
                ["coletado_em", "data_review"],
            )

        observed_total = total_queries + total_categories + total_reviews
        reporter.heartbeat(items_collected_so_far=observed_total)
        reporter.batch_metrics(
            seq=0,
            items_extracted=wines_new_total,
            items_valid_local=wines_new_total,
            items_sent=wines_new_total,
            items_final_inserted=0,
            source_lineage={
                "source_system": "amazon_local",
                "source_kind": "table",
                "source_pointer": "amazon_queries+amazon_categorias+amazon_reviews",
                "source_record_count": observed_total,
                "notes": (
                    f"items_found_total={items_found_total}; recent_queries_24h={recent_queries_24h}; "
                    f"credits_used_total={credits_used_total}; countries={countries_total}; "
                    f"latest_seen={latest_seen or 'unknown'}"
                )[:256],
            },
        )
        reporter.event(
            code="amazon_local.snapshot",
            message=(
                f"queries={total_queries} categories={total_categories} reviews={total_reviews} "
                f"items_found_total={items_found_total} wines_new_total={wines_new_total} "
                f"recent_queries_24h={recent_queries_24h} credits_used_total={credits_used_total} "
                f"countries={countries_total} latest_seen={latest_seen or 'unknown'}"
            )[:1024],
            level="audit",
        )
        reporter.end(
            status="success",
            items_extracted=wines_new_total,
            items_valid_local=wines_new_total,
            items_sent=wines_new_total,
            items_final_inserted=0,
            batches_total=1,
        )
        print(
            f"[{manifest.scraper_id}] run OK queries={total_queries} wines_new_total={wines_new_total} "
            f"reviews={total_reviews}"
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
        return 6


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
