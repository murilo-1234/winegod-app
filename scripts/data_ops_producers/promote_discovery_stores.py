"""CLI para promover candidatos discovery -> public.stores + store_recipes.

DRY-RUN-ONLY por default. `--apply` exige env DISCOVERY_PROMOTION_AUTHORIZED=1.

Gera PromotionPlan em reports/data_ops_promotion_plans/ mesmo em dry-run
(e default desta rodada).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sdk.plugs.common import load_repo_envs  # noqa: E402
from sdk.plugs.discovery_stores.exporters import export_agent_discovery  # noqa: E402
from sdk.plugs.discovery_stores.promotion import (  # noqa: E402
    StorePromoter,
    PLANS_DIR,
    AUTH_ENV,
    summary_markdown,
)


def _build_store_lookup() -> dict[str, int]:
    from sdk.plugs.common import build_store_lookup

    try:
        return build_store_lookup()
    except Exception as exc:  # pragma: no cover - DB absent in this session
        print(f"[warn] build_store_lookup failed ({exc}); treating as empty",
              flush=True)
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote discovery candidates to stores (dry-run default)")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--plan-only", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    load_repo_envs()

    lookup = _build_store_lookup()
    bundle = export_agent_discovery(limit=args.limit, lookup=lookup)
    candidates = bundle.items

    # For sample-scrape fields required by gates, merge any synthetic defaults
    # from the candidate. The producer sees only staged candidates; gate checks
    # will fail honestly if sample data is missing.
    existing_domains = set(lookup)
    promoter = StorePromoter(existing_store_domains=existing_domains)

    plan = promoter.plan(candidates)
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    plan_path = promoter.persist_plan(plan, timestamp=ts)
    summary_path = PLANS_DIR / f"{ts}_plan_summary.md"
    summary_path.write_text(summary_markdown(plan), encoding="utf-8")

    print(
        f"[promote_discovery_stores] plan={plan_path}\n"
        f"[promote_discovery_stores] summary={summary_path}\n"
        f"[promote_discovery_stores] total_candidates={plan.total_candidates} "
        f"approved_stores={plan.approved_stores} approved_recipes={plan.approved_recipes} "
        f"skipped={len(plan.skipped)} plan_hash={plan.plan_hash}",
        flush=True,
    )

    if args.apply:
        import os

        if os.environ.get(AUTH_ENV) != "1":
            parser.error(
                f"--apply requires env {AUTH_ENV}=1 (dry-run by default)"
            )
        parser.error(
            "[promote_discovery_stores] --apply disabled in this session "
            "(REGRA 1 + contract gate). Use the dry-run plan to review."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
