"""Observer read-only: WineGod Admin Commerce Mundial.

Lê fonte local do Winegod Admin (WINEGOD_DATABASE_URL ou equivalente).
Se fonte indisponível, registra evento e fecha run com status blocked/failed.
"""
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
from winegod_scraper_sdk.connectors import ConnectorError, TelemetryDelivery  # noqa: E402
from .common import SafeReadOnlyClient, load_envs_from_repo  # noqa: E402


MANIFEST_PATH = HERE / "manifests" / "commerce_world_winegod_admin.yaml"


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
        # Valida pipeline de payload sem HTTP
        from winegod_scraper_sdk.schemas import BatchEventPayload
        from winegod_scraper_sdk.idempotency import new_uuid
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        rid = new_uuid(); bid = new_uuid()
        BatchEventPayload.model_validate({
            "batch_id": str(bid), "run_id": str(rid), "scraper_id": manifest.scraper_id,
            "seq": 0, "ts": ts,
            "items_extracted": 0, "items_valid_local": 0, "items_sent": 0,
            "items_final_inserted": 0,
            "source_lineage": {
                "source_system": "winegod_admin", "source_kind": "table",
                "source_pointer": "winegod_db.vinhos_*", "source_record_count": 0,
            },
            "idempotency_key": str(bid),
        })
        print(f"[{manifest.scraper_id}] dry-run OK")
        return 0

    # Modo apply — precisa de OPS_BASE_URL + OPS_TOKEN
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
        # Fonte indisponível — reporta blocked
        reporter.event(
            code="source.unavailable",
            message=(
                "WINEGOD_DATABASE_URL / DATABASE_URL_LOCAL_WINEGOD / "
                "WINEGOD_DB_URL nao configurado"
            ),
            level="warn",
        )
        reporter.fail(
            error_summary="source_unavailable: WINEGOD_DATABASE_URL not set",
            status="failed",
        )
        print(f"[{manifest.scraper_id}] source unavailable -> run=failed")
        return 3

    # Coleta read-only
    try:
        with SafeReadOnlyClient(dsn) as client:
            # Lista tabelas vinhos_*
            rows = client.fetchall("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_name LIKE 'vinhos_%'
                ORDER BY table_name
            """)
            tables = [r[0] for r in rows]
            total_records = 0
            for t in tables[:50]:
                try:
                    cnt = client.fetchone(f"SELECT count(*) FROM public.{t}")
                    if cnt:
                        total_records += int(cnt[0] or 0)
                except Exception:
                    continue

        reporter.heartbeat(items_collected_so_far=total_records, items_per_minute=None)
        reporter.batch_metrics(
            seq=0,
            items_extracted=total_records,
            items_valid_local=total_records,
            items_sent=total_records,
            items_final_inserted=0,
            source_lineage={
                "source_system": "winegod_admin",
                "source_kind": "table",
                "source_pointer": f"public.vinhos_* ({len(tables)} tables)",
                "source_record_count": total_records,
            },
        )
        reporter.end(
            status="success",
            items_extracted=total_records,
            items_valid_local=total_records,
            items_sent=total_records,
            items_final_inserted=0,
            batches_total=1,
        )
        print(f"[{manifest.scraper_id}] run OK records={total_records} tables={len(tables)}")
        return 0
    except Exception as e:
        try:
            reporter.event(code="source.error", message=str(e)[:500], level="error")
            reporter.fail(error_summary=str(e)[:1000], status="failed")
        except Exception:
            pass
        print(f"[{manifest.scraper_id}] run failed: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        return 4


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
