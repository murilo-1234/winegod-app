"""CLI Tier2 BR (semanal, Playwright+IA, pais=br).

Gera JSONL + summary em `reports/data_ops_artifacts/tier2/br/`.
Read-only. Nao aplica. Retorna exit=2 com `no_producer_tier2_br` se o
`lojas_scraping` nao tiver lojas BR Tier2 cadastradas.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.plugs.commerce_dq_v3.artifact_exporters.tier2_br import (
    DEFAULT_OUTPUT_DIR,
    TIER2_METHODS,
    Tier2BrConfig,
    run_export,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporter Tier2 Brasil (Playwright+IA).")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), type=Path)
    parser.add_argument("--max-items", type=int, default=10000)
    parser.add_argument(
        "--methods",
        default=None,
        help=f"CSV metodos (default: {','.join(TIER2_METHODS)})",
    )
    parser.add_argument("--batch-size", type=int, default=10000)
    args = parser.parse_args()

    methods = (
        [m.strip() for m in args.methods.split(",") if m.strip()]
        if args.methods
        else list(TIER2_METHODS)
    )
    cfg = Tier2BrConfig(
        output_dir=args.output_dir,
        max_items=args.max_items,
        methods=methods,
        batch_size=args.batch_size,
    )
    result = run_export(cfg)
    if result.ok:
        sha_short = (result.artifact_sha256 or "")[:12]
        print(
            f"OK items_emitted={result.items_emitted} rows_read={result.rows_read} "
            f"duplicates_skipped={result.duplicates_skipped} sha256={sha_short} "
            f"artifact={result.jsonl_path.name if result.jsonl_path else '?'}"
        )
        return 0
    print(f"FAIL reason={result.reason or 'erro_desconhecido'}")
    if result.notes:
        print("notes:", "; ".join(result.notes[:20]))
    return 2 if (result.reason or "").startswith("no_producer") else 1


if __name__ == "__main__":
    raise SystemExit(main())
