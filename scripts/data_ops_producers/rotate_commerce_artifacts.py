"""CLI de rotacao/retencao dos artefatos commerce.

Default: `--plan-only` (nao apaga nada; imprime plano).

`--apply` exige env `COMMERCE_ROTATION_AUTHORIZED=1` para mexer em disco.

Exemplos:

    python scripts/data_ops_producers/rotate_commerce_artifacts.py --plan-only
    $env:COMMERCE_ROTATION_AUTHORIZED="1"
    python scripts/data_ops_producers/rotate_commerce_artifacts.py --apply

Ver `sdk/plugs/commerce_dq_v3/retention.py` para regras detalhadas.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.plugs.commerce_dq_v3 import disk_monitor
from sdk.plugs.commerce_dq_v3.retention import apply_plan, build_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotacao + retencao artefatos commerce.")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "data_ops_artifacts",
    )
    parser.add_argument("--max-age-days", type=int, default=30)
    parser.add_argument("--max-files", type=int, default=10)
    parser.add_argument("--compress-after-days", type=int, default=7)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--plan-only", action="store_true", default=True)
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    plan = build_plan(
        base_dir=args.base_dir,
        max_age_days=args.max_age_days,
        max_files=args.max_files,
        compress_after_days=args.compress_after_days,
    )
    disk = disk_monitor.summary(args.base_dir)

    print(f"disk_status={disk['status']} bytes={disk['bytes']:,} mb={disk['mb']}")
    print(f"plan actions total={len(plan.actions)}")
    by_kind: dict[str, int] = {}
    for action in plan.actions:
        by_kind[action.kind] = by_kind.get(action.kind, 0) + 1
        print(f"  [{action.kind}] {action.family}/{action.artifact.name} ({action.reason})")
    print("summary:", json.dumps(by_kind))

    if args.apply:
        if os.environ.get("COMMERCE_ROTATION_AUTHORIZED") != "1":
            print(
                "ABORT: --apply exige env COMMERCE_ROTATION_AUTHORIZED=1.",
                file=sys.stderr,
            )
            return 2
        counts = apply_plan(plan)
        print(f"applied={counts}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
