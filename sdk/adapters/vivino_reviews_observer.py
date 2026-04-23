"""Observer read-only: Vivino Reviews Global.

PII: proibido enviar reviewer_name/avatar/text/email/profile_url para ops.*.
Apenas contagens agregadas.
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


MANIFEST_PATH = HERE / "manifests" / "reviews_vivino_global.yaml"

# Lista dura de campos PROIBIDOS em qualquer payload ops.* produzido por este adapter.
PII_FORBIDDEN_KEYS = (
    "reviewer_name", "reviewer_avatar_url", "review_text_full",
    "email", "profile_url",
)


def _assert_no_pii(payload: dict) -> None:
    for k in PII_FORBIDDEN_KEYS:
        if k in payload:
            raise RuntimeError(f"PII key '{k}' found in payload — blocked by adapter")


def run(dry_run: bool = True, limit: int = 0) -> int:
    load_envs_from_repo()
    manifest = load_manifest(MANIFEST_PATH)
    print(f"[{manifest.scraper_id}] manifest loaded, dry_run={dry_run}")

    dsn = os.environ.get("DATABASE_URL_LOCAL_VIVINO") or os.environ.get("VIVINO_DB_URL")

    if dry_run:
        from winegod_scraper_sdk.schemas import BatchEventPayload
        from winegod_scraper_sdk.idempotency import new_uuid
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        rid = new_uuid(); bid = new_uuid()
        payload = {
            "batch_id": str(bid), "run_id": str(rid), "scraper_id": manifest.scraper_id,
            "seq": 0, "ts": ts,
            "items_extracted": 0, "items_valid_local": 0, "items_sent": 0,
            "items_final_inserted": 0,
            "source_lineage": {
                "source_system": "vivino_db", "source_kind": "table",
                "source_pointer": "vivino_reviews", "source_record_count": 0,
            },
            "idempotency_key": str(bid),
        }
        _assert_no_pii(payload)
        BatchEventPayload.model_validate(payload)
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
            message="DATABASE_URL_LOCAL_VIVINO / VIVINO_DB_URL nao configurado",
            level="warn",
        )
        reporter.fail(
            error_summary="source_unavailable: DATABASE_URL_LOCAL_VIVINO not set",
            status="failed",
        )
        print(f"[{manifest.scraper_id}] source unavailable -> run=failed")
        return 3

    try:
        with SafeReadOnlyClient(dsn) as client:
            total_reviews = 0
            total_wines = 0
            try:
                row = client.fetchone("SELECT count(*) FROM vivino_reviews")
                total_reviews = int(row[0] or 0) if row else 0
            except Exception:
                pass
            try:
                row = client.fetchone("SELECT count(*) FROM vivino_vinhos")
                total_wines = int(row[0] or 0) if row else 0
            except Exception:
                pass

        # NUNCA enviar reviewer_name/avatar/text — só contagens
        reporter.heartbeat(items_collected_so_far=total_reviews)
        reporter.batch_metrics(
            seq=0,
            items_extracted=total_reviews,
            items_valid_local=total_reviews,
            items_sent=total_reviews,
            items_final_inserted=0,
            source_lineage={
                "source_system": "vivino_db",
                "source_kind": "table",
                "source_pointer": f"vivino_reviews+vivino_vinhos (wines={total_wines})",
                "source_record_count": total_reviews,
            },
        )
        reporter.end(
            status="success",
            items_extracted=total_reviews,
            items_valid_local=total_reviews,
            items_sent=total_reviews,
            items_final_inserted=0,
            batches_total=1,
        )
        print(f"[{manifest.scraper_id}] run OK reviews={total_reviews} wines={total_wines}")
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
