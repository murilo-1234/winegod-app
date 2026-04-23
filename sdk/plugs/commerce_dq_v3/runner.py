from __future__ import annotations

import argparse
import json
from pathlib import Path

from sdk.plugs.common import (
    build_store_lookup,
    load_repo_envs,
    make_reporter,
    process_bulk_http,
    process_bulk_local,
    report_path,
    utc_compact,
    write_jsonl,
)
from .exporters import EXPORTERS, export_tier2_to_dq_stub


MANIFEST_PATH = Path(__file__).resolve().with_name("manifest.yaml")
TIER2_SOURCES = {"tier2_chat1", "tier2_chat2", "tier2_chat3", "tier2_chat4", "tier2_chat5", "tier2_br"}


def _summary_md(
    source: str,
    run_id: str,
    bundle,
    result: dict | None,
    payload_path: Path,
    *,
    dry_run: bool,
    transport: str,
) -> str:
    lines = [
        "# Commerce DQ V3 Plug",
        "",
        f"- source: `{source}`",
        f"- state: `{bundle.state}`",
        f"- run_id: `{run_id}`",
        f"- delivery_mode: `{'dry_run' if dry_run else 'apply'}`",
        f"- transport: `{transport}`",
        f"- payload: `{payload_path}`",
    ]
    for note in bundle.notes:
        lines.append(f"- note: `{note}`")
    if bundle.command_hint:
        lines.append(f"- command_hint: `{bundle.command_hint}`")
    if bundle.unresolved_domains:
        lines.append(f"- unresolved_domains_sample: `{', '.join(bundle.unresolved_domains[:10])}`")
    if result:
        lines.extend(
            [
                "",
                "## DQ V3 result",
                "",
                "```json",
                json.dumps(result, indent=2, ensure_ascii=False),
                "```",
            ]
        )
    return "\n".join(lines) + "\n"


def run(source: str, *, limit: int, apply: bool, transport: str) -> int:
    load_repo_envs()
    lookup = build_store_lookup()
    exporter = EXPORTERS.get(source)
    if source in TIER2_SOURCES:
        bundle = export_tier2_to_dq_stub(source=source)
    elif exporter:
        bundle = exporter(limit=limit, lookup=lookup)
    else:
        raise ValueError(f"source desconhecida: {source}")

    timestamp = utc_compact()
    run_id = f"plug_commerce_dq_v3_{source}_{timestamp}"[:128]
    payload_path = report_path(f"{timestamp}_commerce_{source}_payload.jsonl")
    write_jsonl(payload_path, bundle.items)

    reporter = make_reporter(MANIFEST_PATH)
    if reporter:
        reporter.register()
        reporter.start_run(run_params={"source": source, "dry_run": not apply, "transport": transport, "limit": limit})

    result = None
    if bundle.state == "observed" and bundle.items:
        processor = process_bulk_local if transport == "local" else process_bulk_http
        result = processor(
            bundle.items,
            dry_run=not apply,
            source=source,
            run_id=run_id,
            create_sources=True,
        )

    summary_path = report_path(f"{timestamp}_commerce_{source}_summary.md")
    summary_path.write_text(
        _summary_md(
            source,
            run_id,
            bundle,
            result,
            payload_path,
            dry_run=not apply,
            transport=transport,
        ),
        encoding="utf-8",
    )

    if reporter:
        extracted = len(bundle.items)
        valid = int((result or {}).get("valid", extracted if bundle.state == "observed" else 0) or 0)
        duplicates = int((result or {}).get("duplicates_in_input", 0) or 0)
        notwine = len((result or {}).get("filtered_notwine", [])) if result else 0
        reporter.batch_metrics(
            seq=0,
            items_extracted=extracted,
            items_valid_local=valid,
            items_sent=valid,
            items_accepted_ready=valid,
            items_rejected_notwine=notwine,
            items_duplicate=duplicates,
            items_final_inserted=0,
            source_lineage={
                "source_system": "commerce_dq_v3_plug",
                "source_kind": "file",
                "source_pointer": str(payload_path),
                "source_record_count": extracted,
                "notes": f"source={source}; state={bundle.state}; transport={transport}"[:256],
            },
        )
        reporter.event(
            code="plug.commerce.summary",
            message=(
                f"source={source} state={bundle.state} extracted={extracted} valid={valid} "
                f"duplicates={duplicates} unresolved_domains={len(bundle.unresolved_domains)}"
            )[:1024],
            level="audit",
            payload_pointer=str(summary_path),
        )
        reporter.end(
            status="success",
            items_extracted=extracted,
            items_valid_local=valid,
            items_sent=valid,
            items_final_inserted=0,
            batches_total=1,
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Plug commerce -> DQ V3")
    parser.add_argument("--source", required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--transport", choices=["local", "http"], default="local")
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")
    return run(args.source, limit=args.limit, apply=args.apply, transport=args.transport)


if __name__ == "__main__":
    raise SystemExit(main())
