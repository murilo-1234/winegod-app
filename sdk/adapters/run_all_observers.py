"""Runner unificado dos observers read-only.

Roda todos os adapters em ordem. Se um falhar, segue com os demais e
registra falhas. Exit code != 0 se qualquer --apply falhar.

Uso:
    python sdk/adapters/run_all_observers.py --dry-run
    python sdk/adapters/run_all_observers.py --apply
    python sdk/adapters/run_all_observers.py --adapter dq_v3_observer --apply
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SDK_ROOT = HERE.parent
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))


ADAPTERS = [
    ("winegod_admin_commerce_observer", "adapters.winegod_admin_commerce_observer"),
    ("vivino_reviews_observer", "adapters.vivino_reviews_observer"),
    ("reviewers_vivino_observer", "adapters.reviewers_vivino_observer"),
    ("catalog_vivino_updates_observer", "adapters.catalog_vivino_updates_observer"),
    ("decanter_persisted_observer", "adapters.decanter_persisted_observer"),
    ("dq_v3_observer", "adapters.dq_v3_observer"),
    ("vinhos_brasil_legacy_observer", "adapters.vinhos_brasil_legacy_observer"),
    ("cellartracker_observer", "adapters.cellartracker_observer"),
    ("winesearcher_observer", "adapters.winesearcher_observer"),
    ("wine_enthusiast_observer", "adapters.wine_enthusiast_observer"),
    ("discovery_agent_observer", "adapters.discovery_agent_observer"),
    ("enrichment_gemini_observer", "adapters.enrichment_gemini_observer"),
    ("amazon_local_observer", "adapters.amazon_local_observer"),
]


def run_one(module_name: str, dry_run: bool, limit: int) -> tuple[str, int]:
    try:
        mod = importlib.import_module(module_name)
    except Exception as e:
        return (module_name, -1)
    try:
        rc = mod.run(dry_run=dry_run, limit=limit)
        return (module_name, int(rc))
    except Exception as e:
        print(f"[{module_name}] EXCEPTION: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        return (module_name, 99)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--adapter", default=None, help="nome curto ex: dq_v3_observer")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.apply and args.dry_run:
        print("--apply and --dry-run are mutually exclusive", file=sys.stderr)
        return 1
    dry = not args.apply

    targets = ADAPTERS
    if args.adapter:
        targets = [a for a in ADAPTERS if a[0] == args.adapter]
        if not targets:
            print(f"adapter '{args.adapter}' nao encontrado", file=sys.stderr)
            return 1

    results = []
    for short, mod in targets:
        print(f"=== running {short} (dry_run={dry}) ===")
        results.append(run_one(mod, dry_run=dry, limit=args.limit))

    print("=" * 60)
    print("RESUMO:")
    has_fail = False
    for short, rc in results:
        status = "OK" if rc == 0 else f"FAIL(rc={rc})"
        print(f"  {short}: {status}")
        if rc != 0:
            has_fail = True

    if dry:
        # dry-run não derruba pipeline se um adapter estiver bloqueado
        return 0 if all(rc == 0 for _, rc in results) else 2
    return 0 if not has_fail else 2


if __name__ == "__main__":
    raise SystemExit(main())
