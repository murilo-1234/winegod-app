"""Gera budget forecast para o loop de enrichment.

Le a fila atual (staging mais recente de `gemini_batch_reports`) e
escreve um relatorio em `reports/data_ops_enrichment_budget/`.

ZERO chamada ao Gemini. ZERO tocar no sistema v3.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sdk.plugs.common import load_repo_envs  # noqa: E402
from sdk.plugs.enrichment.budget import (  # noqa: E402
    estimate_cost,
    recommended_batch_cap,
    report_md,
)

BUDGET_DIR = REPO_ROOT / "reports" / "data_ops_enrichment_budget"
STAGING_DIR = REPO_ROOT / "reports" / "data_ops_plugs_staging"


def _latest_enrichment_jsonl() -> Path | None:
    if not STAGING_DIR.exists():
        return None
    files = sorted(
        STAGING_DIR.glob("*_gemini_batch_reports_enrichment.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def _count_by_route(path: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    if not path.exists():
        return dict(counts)
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            route = row.get("route") or "unknown"
            counts[route] += 1
    return dict(counts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Budget forecast do enrichment loop")
    parser.add_argument("--items", type=int, default=None,
                        help="override manual do total de items (pula leitura do staging)")
    parser.add_argument("--cap-usd", type=str, default="50",
                        help="cap USD para recomendar batch size (default 50)")
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="override do diretorio de saida (default reports/data_ops_enrichment_budget/)",
    )
    args = parser.parse_args()

    load_repo_envs()
    out_dir = Path(args.out_dir) if args.out_dir else BUDGET_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.items is not None:
        total = args.items
        by_route = {"override": total}
    else:
        latest = _latest_enrichment_jsonl()
        if not latest:
            by_route = {}
            total = 0
        else:
            by_route = _count_by_route(latest)
            total = sum(by_route.values())

    estimate = estimate_cost(total)
    cap_usd = Decimal(args.cap_usd)
    cap_items = recommended_batch_cap(cap_usd)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    md_path = out_dir / f"{ts}_budget.md"
    json_path = out_dir / f"{ts}_budget.json"

    md = report_md(estimate, by_route=by_route)
    md += (
        f"\n## Recomendacao de batch cap\n\n"
        f"- cap_usd: `{cap_usd}`\n"
        f"- items_within_cap: `{cap_items}`\n"
    )
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "by_route": by_route,
                "estimate": estimate.to_dict(),
                "cap_usd": str(cap_usd),
                "items_within_cap": cap_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"[enrichment_budget_forecast] md={md_path}\n"
        f"[enrichment_budget_forecast] json={json_path}\n"
        f"[enrichment_budget_forecast] items={total} total_cost_usd={estimate.total_cost_usd}"
        f" cap_usd={cap_usd} items_within_cap={cap_items}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
