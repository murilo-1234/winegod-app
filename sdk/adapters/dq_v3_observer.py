"""Observer READ-ONLY do DQ V3 já validado (bridge oficial).

Lê via SELECT:
- ingestion_run_log
- wines.ingestion_run_id
- wine_sources.ingestion_run_id
- not_wine_rejections
- ingestion_review_queue

NÃO escreve em nenhuma tabela DQ V3. NÃO faz apply. NÃO chama Gemini.
NÃO altera wines/wine_sources. NÃO recria DQ V3.
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


MANIFEST_PATH = HERE / "manifests" / "commerce_dq_v3_observer.yaml"


def run(dry_run: bool = True, limit: int = 0) -> int:
    load_envs_from_repo()
    manifest = load_manifest(MANIFEST_PATH)
    print(f"[{manifest.scraper_id}] manifest loaded, dry_run={dry_run}")

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print(f"[{manifest.scraper_id}] ERROR: DATABASE_URL missing", file=sys.stderr)
        return 2

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
                "source_system": "dq_v3", "source_kind": "table",
                "source_pointer": "ingestion_run_log", "source_record_count": 0,
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

    try:
        with SafeReadOnlyClient(dsn) as client:
            # total runs DQ V3
            runs_total = 0
            try:
                r = client.fetchone("SELECT count(*) FROM ingestion_run_log")
                runs_total = int(r[0] or 0) if r else 0
            except Exception:
                pass

            # wines com ingestion_run_id
            wines_with_run = 0
            try:
                r = client.fetchone(
                    "SELECT count(*) FROM public.wines WHERE ingestion_run_id IS NOT NULL"
                )
                wines_with_run = int(r[0] or 0) if r else 0
            except Exception:
                pass

            # wine_sources com ingestion_run_id
            sources_with_run = 0
            try:
                r = client.fetchone(
                    "SELECT count(*) FROM public.wine_sources WHERE ingestion_run_id IS NOT NULL"
                )
                sources_with_run = int(r[0] or 0) if r else 0
            except Exception:
                pass

            # not_wine_rejections total
            not_wine_total = 0
            try:
                r = client.fetchone("SELECT count(*) FROM not_wine_rejections")
                not_wine_total = int(r[0] or 0) if r else 0
            except Exception:
                pass

            # review queue pendente
            review_queue_total = 0
            try:
                r = client.fetchone("SELECT count(*) FROM ingestion_review_queue")
                review_queue_total = int(r[0] or 0) if r else 0
            except Exception:
                pass

            # último run_id
            last_run_id = None
            try:
                r = client.fetchone(
                    "SELECT run_id FROM ingestion_run_log ORDER BY iniciado_em DESC LIMIT 1"
                )
                if r and r[0]:
                    last_run_id = str(r[0])[:64]
            except Exception:
                try:
                    r = client.fetchone(
                        "SELECT id FROM ingestion_run_log ORDER BY id DESC LIMIT 1"
                    )
                    if r and r[0]:
                        last_run_id = str(r[0])
                except Exception:
                    pass

        observed_total = runs_total + wines_with_run + sources_with_run + not_wine_total + review_queue_total

        reporter.heartbeat(items_collected_so_far=observed_total)
        reporter.batch_metrics(
            seq=0,
            items_extracted=observed_total,
            items_valid_local=observed_total,
            items_sent=observed_total,
            items_final_inserted=0,  # DQ V3 insere em wines/wine_sources, mas observer NÃO
            items_accepted_ready=runs_total,
            items_rejected_notwine=not_wine_total,
            items_uncertain=review_queue_total,
            source_lineage={
                "source_system": "dq_v3",
                "source_kind": "table",
                "source_pointer": f"ingestion_run_log:{last_run_id or 'unknown'}",
                "source_record_count": observed_total,
            },
            field_coverage={
                "runs_total": 1.0 if runs_total > 0 else 0.0,
                "wines_with_run": 1.0 if wines_with_run > 0 else 0.0,
                "wine_sources_with_run": 1.0 if sources_with_run > 0 else 0.0,
                "not_wine_rejections": 1.0 if not_wine_total > 0 else 0.0,
            },
        )
        reporter.event(
            code="dq_v3.snapshot",
            message=(
                f"runs={runs_total} wines_with_run={wines_with_run} "
                f"sources_with_run={sources_with_run} not_wine={not_wine_total} "
                f"review_queue={review_queue_total}"
            ),
            level="audit",
        )
        reporter.end(
            status="success",
            items_extracted=observed_total,
            items_sent=observed_total,
            items_final_inserted=0,
            batches_total=1,
        )
        print(f"[{manifest.scraper_id}] DQ V3 observed: runs={runs_total} wines={wines_with_run} "
              f"sources={sources_with_run} not_wine={not_wine_total} queue={review_queue_total}")
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
