"""Canário sintético — Winegod Data Ops Fase 1.

Modos:
    --dry-run   : valida manifesto + payloads sem HTTP.
    --apply     : envia ao backend se OPS_BASE_URL + OPS_TOKEN presentes.
    --items N   : número de registros sintéticos (default 100).

NUNCA escreve em banco de negócio. Gera `synthetic_id`/`synthetic_value` puros.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


HERE = Path(__file__).resolve().parent
SDK_ROOT = HERE.parent
# Garante que sdk eh importavel quando rodado de qualquer cwd.
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from winegod_scraper_sdk import Reporter, load_manifest
from winegod_scraper_sdk.connectors import TelemetryDelivery
from winegod_scraper_sdk.schemas import BatchEventPayload, StartRunPayload


MANIFEST_PATH = HERE / "canary_manifest.yaml"


def _generate_items(n: int, seed: int = 42) -> List[Dict[str, Any]]:
    """Gera N itens sintéticos. SEM PII. SEM referência a dado de negócio."""
    rng = random.Random(seed)
    items: List[Dict[str, Any]] = []
    for i in range(n):
        items.append(
            {
                "synthetic_id": f"syn-{i:04d}",
                "synthetic_value": rng.random(),
            }
        )
    return items


def run(dry_run: bool = True, items_count: int = 100) -> int:
    manifest = load_manifest(MANIFEST_PATH)
    print(f"[canary] manifest loaded: {manifest.scraper_id}")
    print(f"[canary] manifest_hash: {manifest.source_hash}")

    items = _generate_items(items_count)
    print(f"[canary] generated {len(items)} synthetic items")

    if dry_run:
        print("[canary] dry-run: validating payloads without HTTP...")
        delivery = TelemetryDelivery(base_url="http://localhost:0", token="dry")
        rep = Reporter(manifest=manifest, delivery=delivery)
        # Valida manifesto → register_payload
        _ = manifest.to_register_payload()
        # Valida start/heartbeat/end localmente via Pydantic.
        from winegod_scraper_sdk.idempotency import new_uuid, idem_key_for_run

        rid = new_uuid()
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        StartRunPayload.model_validate(
            {
                "run_id": str(rid),
                "scraper_id": manifest.scraper_id,
                "host": manifest.host,
                "contract_name": manifest.contract_primary().name,
                "contract_version": manifest.contract_primary().version,
                "started_at": ts,
                "idempotency_key": idem_key_for_run(rid),
            }
        )
        # Batch fake
        bid = new_uuid()
        BatchEventPayload.model_validate(
            {
                "batch_id": str(bid),
                "run_id": str(rid),
                "scraper_id": manifest.scraper_id,
                "seq": 0,
                "ts": ts,
                "items_extracted": len(items),
                "items_valid_local": len(items),
                "items_sent": len(items),
                "items_final_inserted": 0,
                "field_coverage": {
                    "synthetic_id": 1.0,
                    "synthetic_value": 1.0,
                },
                "source_lineage": {
                    "source_system": "canary",
                    "source_kind": "synthetic",
                    "source_pointer": "synthetic",
                    "source_record_count": len(items),
                },
                "idempotency_key": str(bid),
            }
        )
        print("[canary] dry-run OK: all payloads valid.")
        return 0

    # Modo apply — exige OPS_BASE_URL e OPS_TOKEN.
    base_url = os.environ.get("OPS_BASE_URL", "http://localhost:5000")
    token = os.environ.get("OPS_TOKEN", "")
    if not token:
        print("[canary] ERROR: OPS_TOKEN not set. Use --dry-run or define env.", file=sys.stderr)
        return 2

    delivery = TelemetryDelivery.from_env(default_url=base_url)
    rep = Reporter(manifest=manifest, delivery=delivery)

    # 1. Health check
    try:
        hc = rep.delivery.health()
        print(f"[canary] /ops/health -> {hc.status_code} ok={hc.body.get('ok')}")
    except Exception as e:
        print(f"[canary] health failed: {e}", file=sys.stderr)
        return 3

    # 2. Register scraper
    reg = rep.register()
    print(f"[canary] register -> duplicated={reg.duplicated if reg else 'buffered'}")

    # 3. Start run
    run_id = rep.start_run()
    print(f"[canary] run_id={run_id}")

    # 4. Heartbeats + batches em 10 lotes
    batch_size = max(1, items_count // 10)
    for seq in range(10):
        chunk = items[seq * batch_size : (seq + 1) * batch_size]
        rep.heartbeat(items_collected_so_far=(seq + 1) * batch_size)
        rep.batch_metrics(
            seq=seq,
            items_extracted=len(chunk),
            items_valid_local=len(chunk),
            items_sent=len(chunk),
            items_accepted_ready=len(chunk),
            items_final_inserted=0,
            field_coverage={"synthetic_id": 1.0, "synthetic_value": 1.0},
            source_lineage={
                "source_system": "canary",
                "source_kind": "synthetic",
                "source_pointer": "synthetic",
                "source_record_count": len(chunk),
            },
        )

    # 5. Fim
    rep.end(
        status="success",
        items_extracted=items_count,
        items_valid_local=items_count,
        items_sent=items_count,
        items_rejected_schema=0,
        items_final_inserted=0,
        batches_total=10,
    )
    print("[canary] run completed OK.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Winegod canary synthetic")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--items", type=int, default=100)
    args = parser.parse_args()

    if args.apply and args.dry_run:
        print("--apply and --dry-run are mutually exclusive", file=sys.stderr)
        return 1
    # Default: dry-run
    dry = not args.apply
    return run(dry_run=dry, items_count=args.items)


if __name__ == "__main__":
    raise SystemExit(main())
