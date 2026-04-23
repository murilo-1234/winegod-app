"""Observer read-only: discovery agent global."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SDK_ROOT = HERE.parent
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from winegod_scraper_sdk import Reporter, load_manifest  # noqa: E402
from winegod_scraper_sdk.connectors import TelemetryDelivery  # noqa: E402
from .common import load_envs_from_repo  # noqa: E402


MANIFEST_PATH = HERE / "manifests" / "discovery_agent_global.yaml"
DISCOVERY_ROOT = Path("C:/natura-automation")
DISCOVERY_PHASES_PATH = DISCOVERY_ROOT / "agent_discovery" / "discovery_phases.json"
DISCOVERY_JSON_GLOB = "ecommerces_vinhos_*_v2.json"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(dry_run: bool = True, limit: int = 0) -> int:
    load_envs_from_repo()
    manifest = load_manifest(MANIFEST_PATH)
    print(f"[{manifest.scraper_id}] manifest loaded, dry_run={dry_run}")

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
                    "source_system": "agent_discovery",
                    "source_kind": "file",
                    "source_pointer": str(DISCOVERY_PHASES_PATH),
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
        if not DISCOVERY_PHASES_PATH.exists():
            reporter.event(
                code="source.file_missing",
                message=f"{DISCOVERY_PHASES_PATH} ausente",
                level="warn",
            )
            reporter.fail(
                error_summary="source_unavailable: discovery_phases.json missing",
                status="failed",
            )
            return 3

        json_files = sorted(DISCOVERY_ROOT.glob(DISCOVERY_JSON_GLOB))
        if not json_files:
            reporter.event(
                code="source.file_missing",
                message=f"nenhum arquivo {DISCOVERY_JSON_GLOB} encontrado",
                level="warn",
            )
            reporter.fail(
                error_summary="source_unavailable: discovery json files missing",
                status="failed",
            )
            return 4

        phases = _load_json(DISCOVERY_PHASES_PATH)
        platforms = Counter()
        countries = Counter()
        verified_total = 0
        no_ecommerce_total = 0
        stores_total = 0
        latest_mtime = DISCOVERY_PHASES_PATH.stat().st_mtime

        for path in json_files:
            payload = _load_json(path)
            latest_mtime = max(latest_mtime, path.stat().st_mtime)
            country_code = str(payload.get("codigo") or payload.get("pais") or path.stem)
            stores = payload.get("lojas") or []
            countries[country_code] += len(stores)
            stores_total += len(stores)
            for store in stores:
                if not isinstance(store, dict):
                    continue
                platform = str(store.get("plataforma") or "unknown").strip() or "unknown"
                platforms[platform] += 1
                if bool(store.get("verificado")):
                    verified_total += 1
                if store.get("tem_ecommerce") is False:
                    no_ecommerce_total += 1

        latest_iso = phases.get("_updated") or int(latest_mtime)
        top_platforms = ", ".join(f"{name}:{count}" for name, count in platforms.most_common(5))
        top_countries = ", ".join(f"{name}:{count}" for name, count in countries.most_common(5))
        countries_total = len(phases.get("countries", {})) or len(countries)
        observed_total = stores_total + len(json_files) + countries_total

        reporter.heartbeat(items_collected_so_far=observed_total)
        reporter.batch_metrics(
            seq=0,
            items_extracted=stores_total,
            items_valid_local=verified_total,
            items_sent=verified_total,
            items_final_inserted=0,
            source_lineage={
                "source_system": "agent_discovery",
                "source_kind": "file",
                "source_pointer": (
                    f"{DISCOVERY_PHASES_PATH};files={len(json_files)}"
                ),
                "source_record_count": stores_total,
                "notes": (
                    f"countries={countries_total}; no_ecommerce={no_ecommerce_total}; "
                    f"latest={latest_iso}; top_platforms={top_platforms}"
                )[:256],
            },
        )
        reporter.event(
            code="discovery.snapshot",
            message=(
                f"stores={stores_total} verified={verified_total} no_ecommerce={no_ecommerce_total} "
                f"countries={countries_total} files={len(json_files)} latest={latest_iso} "
                f"top_platforms={top_platforms or 'none'} top_countries={top_countries or 'none'}"
            )[:1024],
            level="audit",
        )
        reporter.end(
            status="success",
            items_extracted=stores_total,
            items_valid_local=verified_total,
            items_sent=verified_total,
            items_final_inserted=0,
            batches_total=1,
        )
        print(
            f"[{manifest.scraper_id}] run OK stores={stores_total} "
            f"countries={countries_total} files={len(json_files)}"
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
