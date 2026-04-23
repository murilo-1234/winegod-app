"""Observer read-only: Vivino reviewers global.

PII: nunca envia nome, foto, bio, redes sociais, email ou telefone para ops.*.
Somente contagens agregadas e marcadores de cobertura.
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
from winegod_scraper_sdk.connectors import TelemetryDelivery  # noqa: E402
from .common import (  # noqa: E402
    SafeReadOnlyClient,
    count_distinct,
    count_recent_rows_by_candidates,
    count_rows,
    load_envs_from_repo,
    sum_column,
    table_exists,
)


MANIFEST_PATH = HERE / "manifests" / "reviewers_vivino_global.yaml"
PII_FORBIDDEN_KEYS = (
    "nome",
    "foto_url",
    "bio",
    "email_encontrado",
    "website",
    "instagram",
    "twitter",
    "telefone",
    "empresa",
    "background_image",
)


def _assert_no_pii(payload: dict) -> None:
    for key in PII_FORBIDDEN_KEYS:
        if key in payload:
            raise RuntimeError(f"PII key '{key}' found in payload")


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
        payload = {
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
                "source_pointer": "vivino_reviewers",
                "source_record_count": 0,
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
            if not table_exists(client, "vivino_reviewers"):
                reporter.event(
                    code="source.schema_missing",
                    message="vivino_reviewers ausente",
                    level="error",
                )
                reporter.fail(
                    error_summary="source_schema_missing: vivino_reviewers",
                    status="failed",
                )
                return 4

            total_reviewers = count_rows(client, "vivino_reviewers")
            recent_reviewers_7d = count_recent_rows_by_candidates(
                client,
                "vivino_reviewers",
                ["atualizado_em", "coletado_em", "criado_em"],
                hours=24 * 7,
            )
            countries_total = count_distinct(client, "vivino_reviewers", "localizacao_pais_codigo")
            ratings_sum_total = int(sum_column(client, "vivino_reviewers", "ratings_sum"))
            premium_row = client.fetchone(
                "SELECT count(*) FROM public.vivino_reviewers WHERE is_premium IS TRUE"
            )
            premium_total = int(premium_row[0] or 0) if premium_row else 0

        reporter.heartbeat(items_collected_so_far=total_reviewers)
        reporter.batch_metrics(
            seq=0,
            items_extracted=total_reviewers,
            items_valid_local=total_reviewers,
            items_sent=total_reviewers,
            items_final_inserted=0,
            source_lineage={
                "source_system": "vivino_db",
                "source_kind": "table",
                "source_pointer": "vivino_reviewers",
                "source_record_count": total_reviewers,
                "notes": (
                    f"recent_reviewers_7d={recent_reviewers_7d}; countries={countries_total}; "
                    f"ratings_sum_total={ratings_sum_total}; premium_total={premium_total}"
                )[:256],
            },
        )
        reporter.event(
            code="reviewers.snapshot",
            message=(
                f"reviewers={total_reviewers} recent_reviewers_7d={recent_reviewers_7d} "
                f"countries={countries_total} ratings_sum_total={ratings_sum_total} "
                f"premium_total={premium_total}"
            )[:1024],
            level="audit",
        )
        reporter.end(
            status="success",
            items_extracted=total_reviewers,
            items_valid_local=total_reviewers,
            items_sent=total_reviewers,
            items_final_inserted=0,
            batches_total=1,
        )
        print(f"[{manifest.scraper_id}] run OK reviewers={total_reviewers}")
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
