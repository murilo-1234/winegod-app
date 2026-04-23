from __future__ import annotations

import argparse
import json
from pathlib import Path

from sdk.plugs.common import build_store_lookup, load_repo_envs, make_reporter, report_path, utc_compact, write_jsonl
from .exporters import EXPORTERS


MANIFEST_PATH = Path(__file__).resolve().with_name("manifest.yaml")


def run(source: str, *, limit: int, dry_run: bool = True) -> int:
    load_repo_envs()
    lookup = build_store_lookup()
    bundle = EXPORTERS[source](limit=limit, lookup=lookup)
    timestamp = utc_compact()
    out_path = report_path(f"{timestamp}_{source}_discovery_stores.jsonl")
    write_jsonl(out_path, bundle.items)

    known_count = sum(1 for item in bundle.items if item.get("already_known_store"))
    summary_path = report_path(f"{timestamp}_{source}_discovery_stores_summary.md")
    summary_path.write_text(
        "\n".join(
            [
                "# Discovery Stores Plug",
                "",
                f"- source: `{source}`",
                f"- state: `{bundle.state}`",
                f"- delivery_mode: `{'dry_run' if dry_run else 'apply'}`",
                f"- items: `{len(bundle.items)}`",
                f"- known_store_hits: `{known_count}`",
                *[f"- note: `{note}`" for note in bundle.notes],
                f"- output: `{out_path}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    reporter = make_reporter(MANIFEST_PATH)
    if reporter:
        reporter.register()
        reporter.start_run(run_params={"source": source, "limit": limit, "dry_run": dry_run})
        reporter.batch_metrics(
            seq=0,
            items_extracted=len(bundle.items),
            items_valid_local=len(bundle.items),
            items_sent=len(bundle.items),
            items_final_inserted=0,
            source_lineage={
                "source_system": "discovery_stores_plug",
                "source_kind": "file",
                "source_pointer": str(out_path),
                "source_record_count": len(bundle.items),
                "notes": f"source={source}; state={bundle.state}; known_store_hits={known_count}"[:256],
            },
        )
        reporter.event(
            code="plug.discovery.summary",
            message=f"source={source} state={bundle.state} items={len(bundle.items)} known_store_hits={known_count}",
            level="audit",
            payload_pointer=str(summary_path),
            payload_sample=json.dumps(bundle.items[:2], ensure_ascii=False)[:1024] if bundle.items else None,
        )
        reporter.end(
            status="success",
            items_extracted=len(bundle.items),
            items_valid_local=len(bundle.items),
            items_sent=len(bundle.items),
            items_final_inserted=0,
            batches_total=1,
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Plug de staging para discovery e stores candidatas")
    parser.add_argument("--source", required=True, choices=sorted(EXPORTERS))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply:
        parser.error("discovery_stores e staging-only nesta sessao; use --dry-run ou o default")
    return run(args.source, limit=args.limit, dry_run=True)


if __name__ == "__main__":
    raise SystemExit(main())
