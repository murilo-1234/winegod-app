"""Observer read-only: Decanter persistido.

Lê:
- Arquivo local decanter_collector_status.json.
- Não chama Decanter API. Não usa token externo.
- Opcionalmente, se DATABASE_URL_LOCAL_DECANTER estiver setada, lê count de decanter_vinhos.
"""
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
from winegod_scraper_sdk.connectors import ConnectorError, TelemetryDelivery  # noqa: E402
from .common import SafeReadOnlyClient, load_envs_from_repo  # noqa: E402


MANIFEST_PATH = HERE / "manifests" / "critics_decanter_persisted.yaml"
DEFAULT_STATUS_JSON = Path("C:/natura-automation/winegod_v2/decanter_collector_status.json")


def _safe_read_status(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run(dry_run: bool = True, limit: int = 0) -> int:
    load_envs_from_repo()
    manifest = load_manifest(MANIFEST_PATH)
    print(f"[{manifest.scraper_id}] manifest loaded, dry_run={dry_run}")

    status_path = DEFAULT_STATUS_JSON
    dsn_opt = os.environ.get("DATABASE_URL_LOCAL_DECANTER") or os.environ.get("DECANTER_DB_URL")

    if dry_run:
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
                "source_system": "decanter_persisted", "source_kind": "file",
                "source_pointer": str(status_path), "source_record_count": 0,
            },
            "idempotency_key": str(bid),
        })
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

    # Lê JSON status
    status = _safe_read_status(status_path)
    status_records = 0
    source_pointer = str(status_path)

    if status:
        # Tenta inferir contagem do JSON (chaves variam conforme projeto)
        for k in ("total_vinhos", "total_scraped", "total", "count"):
            if k in status and isinstance(status[k], (int, float)):
                status_records = int(status[k])
                break

    # Se houver DSN opcional, lê count de decanter_vinhos
    db_records = 0
    db_ok = False
    if dsn_opt:
        try:
            with SafeReadOnlyClient(dsn_opt) as client:
                row = client.fetchone("SELECT count(*) FROM decanter_vinhos")
                if row:
                    db_records = int(row[0] or 0)
                    db_ok = True
                    source_pointer = f"decanter_vinhos+{status_path.name}"
        except Exception as e:
            reporter.event(code="source.db_error", message=str(e)[:500], level="warn")

    total = max(status_records, db_records)

    try:
        reporter.heartbeat(items_collected_so_far=total)
        reporter.batch_metrics(
            seq=0,
            items_extracted=total,
            items_valid_local=total,
            items_sent=total,
            items_final_inserted=0,
            source_lineage={
                "source_system": "decanter_persisted",
                "source_kind": "table" if db_ok else "file",
                "source_pointer": source_pointer,
                "source_record_count": total,
            },
        )
        reporter.end(
            status="success",
            items_extracted=total,
            items_valid_local=total,
            items_sent=total,
            items_final_inserted=0,
            batches_total=1,
        )
        print(f"[{manifest.scraper_id}] run OK total={total} status_json={status_records} db={db_records}")
        return 0
    except Exception as e:
        try:
            reporter.event(code="observer.error", message=str(e)[:500], level="error")
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
