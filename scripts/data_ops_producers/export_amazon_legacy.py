"""CLI Amazon legacy backfill (one-time).

Gera JSONL + summary em `reports/data_ops_artifacts/amazon_local_legacy_backfill/`
para os dados historicos do scraper Amazon desativado. Read-only no
`winegod_db`. Nao aplica.

Ver `sdk/plugs/commerce_dq_v3/artifact_exporters/amazon_legacy.py`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.plugs.commerce_dq_v3.artifact_exporters.amazon_legacy import (
    AmazonLegacyConfig,
    DEFAULT_OUTPUT_DIR,
    run_export,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporter Amazon legacy (one-time backfill).")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), type=Path)
    parser.add_argument("--max-items", type=int, default=50000, help="Piloto default 50k")
    parser.add_argument(
        "--country-filter",
        default=None,
        help="CSV de ISO-2 (ex: us,br,fr). Omitir = todos os paises.",
    )
    parser.add_argument("--batch-size", type=int, default=10000)
    args = parser.parse_args()

    country_filter = None
    if args.country_filter:
        country_filter = [c.strip().lower() for c in args.country_filter.split(",") if c.strip()]

    cfg = AmazonLegacyConfig(
        output_dir=args.output_dir,
        max_items=args.max_items,
        country_filter=country_filter,
        batch_size=args.batch_size,
    )
    result = run_export(cfg)
    if result.ok:
        sha_short = (result.artifact_sha256 or "")[:12]
        print(
            f"OK items_emitted={result.items_emitted} "
            f"rows_read={result.rows_read} duplicates_skipped={result.duplicates_skipped} "
            f"sha256={sha_short} artifact={result.jsonl_path.name if result.jsonl_path else '?'}"
        )
        return 0
    print(f"FAIL reason={result.reason or 'erro_desconhecido'}")
    if result.notes:
        print("notes:", "; ".join(result.notes[:20]))
    return 2 if (result.reason or "").startswith("no_producer") else 1


if __name__ == "__main__":
    raise SystemExit(main())
