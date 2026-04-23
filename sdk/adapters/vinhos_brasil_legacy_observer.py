"""Observer read-only: legado Vinhos Brasil."""
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


MANIFEST_PATH = HERE / "manifests" / "commerce_br_vinhos_brasil_legacy.yaml"


def _get_source_dsn() -> str | None:
    return os.environ.get("VINHOS_BRASIL_DATABASE_URL")


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
                    "source_system": "vinhos_brasil",
                    "source_kind": "table",
                    "source_pointer": (
                        "vinhos_brasil+vinhos_brasil_fontes+vinhos_brasil_execucoes"
                    ),
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
            message="VINHOS_BRASIL_DATABASE_URL nao configurado",
            level="warn",
        )
        reporter.fail(
            error_summary="source_unavailable: VINHOS_BRASIL_DATABASE_URL not set",
            status="failed",
        )
        return 3

    try:
        with SafeReadOnlyClient(dsn) as client:
            required_tables = [
                "vinhos_brasil",
                "vinhos_brasil_fontes",
                "vinhos_brasil_execucoes",
            ]
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
                return 4

            total_wines = count_rows(client, "vinhos_brasil")
            total_sources = count_rows(client, "vinhos_brasil_fontes")
            total_runs = count_rows(client, "vinhos_brasil_execucoes")
            runs_24h = count_recent_rows_by_candidates(
                client,
                "vinhos_brasil_execucoes",
                ["concluido_em", "iniciado_em"],
                hours=24,
            )
            latest_exec = max_column_by_candidates(
                client,
                "vinhos_brasil_execucoes",
                ["concluido_em", "iniciado_em"],
            )
            latest_source = max_column_by_candidates(
                client,
                "vinhos_brasil_fontes",
                ["atualizado_em", "descoberto_em"],
            )

            rows = client.fetchall(
                """
                SELECT coalesce(nullif(mercado, ''), nullif(fonte, ''), 'unknown') AS bucket,
                       count(*)
                FROM public.vinhos_brasil_fontes
                GROUP BY 1
                ORDER BY 2 DESC, 1
                LIMIT 5
                """
            )
            top_markets = ", ".join(f"{name}:{count}" for name, count in rows)

        observed_total = total_wines + total_sources + total_runs
        reporter.heartbeat(items_collected_so_far=observed_total)
        reporter.batch_metrics(
            seq=0,
            items_extracted=total_wines,
            items_valid_local=total_wines,
            items_sent=total_wines,
            items_final_inserted=0,
            source_lineage={
                "source_system": "vinhos_brasil",
                "source_kind": "table",
                "source_pointer": "vinhos_brasil+vinhos_brasil_fontes+vinhos_brasil_execucoes",
                "source_record_count": observed_total,
                "notes": (
                    f"runs_24h={runs_24h}; latest_exec={latest_exec or 'unknown'}; "
                    f"latest_source={latest_source or 'unknown'}; top_markets={top_markets or 'none'}"
                )[:256],
            },
        )
        reporter.event(
            code="vinhos_brasil.snapshot",
            message=(
                f"wines={total_wines} sources={total_sources} runs={total_runs} "
                f"runs_24h={runs_24h} latest_exec={latest_exec or 'unknown'} "
                f"latest_source={latest_source or 'unknown'} top_markets={top_markets or 'none'}"
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
        print(
            f"[{manifest.scraper_id}] run OK wines={total_wines} sources={total_sources} "
            f"runs={total_runs}"
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
