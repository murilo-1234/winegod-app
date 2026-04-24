"""CLI Amazon mirror primary (recorrente).

Gera JSONL + summary em `reports/data_ops_artifacts/amazon_mirror/` lendo
`winegod_db.vinhos_*_fontes` com `fonte='amazon_playwright'`. Modo
incremental via state em `reports/data_ops_export_state/amazon_mirror.json`.

Read-only. Nao aplica.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.plugs.commerce_dq_v3.artifact_exporters.amazon_mirror import (
    AmazonMirrorConfig,
    DEFAULT_OUTPUT_DIR,
    run_export,
)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporter Amazon mirror primary.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), type=Path)
    parser.add_argument("--max-items", type=int, default=50000)
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="incremental usa state file; full le tudo",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Override ISO-8601 UTC (ex: 2026-04-01T00:00:00Z). Ignora state.",
    )
    parser.add_argument("--country-filter", default=None)
    parser.add_argument("--batch-size", type=int, default=10000)
    # Sharding (plano 3 fases):
    parser.add_argument("--source-table", default=None)
    parser.add_argument("--min-fonte-id", type=int, default=None)
    parser.add_argument("--max-fonte-id", type=int, default=None)
    parser.add_argument("--shard-id", default=None)
    args = parser.parse_args()

    country_filter = None
    if args.country_filter:
        country_filter = [c.strip().lower() for c in args.country_filter.split(",") if c.strip()]
    since = _parse_iso(args.since) if args.since else None

    cfg = AmazonMirrorConfig(
        output_dir=args.output_dir,
        max_items=args.max_items,
        mode=args.mode,
        since=since,
        country_filter=country_filter,
        batch_size=args.batch_size,
        source_table_filter=args.source_table,
        min_fonte_id=args.min_fonte_id,
        max_fonte_id=args.max_fonte_id,
        shard_id=args.shard_id,
    )
    result = run_export(cfg)
    if result.ok:
        sha_short = (result.artifact_sha256 or "")[:12]
        print(
            f"OK mode={args.mode} items_emitted={result.items_emitted} "
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
