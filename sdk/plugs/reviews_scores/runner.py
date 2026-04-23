from __future__ import annotations

import argparse
import json
from pathlib import Path

from sdk.plugs.common import load_repo_envs, make_reporter, report_path, utc_compact, write_jsonl
from .checkpoint import load_state, save_state
from .exporters import EXPORTERS, export_vivino_wines_to_ratings
from .schemas import PER_REVIEW_SOURCES
from .writer import apply_bundle


MANIFEST_PATH = Path(__file__).resolve().with_name("manifest.yaml")
MODES = ("incremental_recent", "backfill_windowed")
BACKFILL_SUPPORTED_SOURCES = {"vivino_wines_to_ratings"}


def _summary_md(
    source: str,
    mode: str,
    dry_run: bool,
    items_count: int,
    staging_path: Path,
    apply_payload: dict | None,
    notes: list[str],
    checkpoint_before: dict | None,
    checkpoint_after: dict | None,
) -> str:
    lines = [
        "# Reviews Scores Plug",
        "",
        f"- source: `{source}`",
        f"- mode: `{mode}`",
        f"- delivery_mode: `{'dry_run' if dry_run else 'apply'}`",
        f"- items: `{items_count}`",
    ]
    for note in notes:
        lines.append(f"- note: `{note}`")
    lines.append(f"- staging: `{staging_path}`")
    if checkpoint_before is not None:
        lines.append(f"- checkpoint_before: `{json.dumps(checkpoint_before, ensure_ascii=False)}`")
    if checkpoint_after is not None:
        lines.append(f"- checkpoint_after: `{json.dumps(checkpoint_after, ensure_ascii=False)}`")
    if apply_payload is not None:
        lines.extend(
            [
                "",
                "## Apply result",
                "",
                "```json",
                json.dumps(apply_payload, indent=2, ensure_ascii=False),
                "```",
            ]
        )
    return "\n".join(lines) + "\n"


def _build_bundle(source: str, *, limit: int, mode: str, after_id: int):
    if source == "vivino_wines_to_ratings":
        return export_vivino_wines_to_ratings(limit, mode=mode, after_id=after_id)
    if mode == "backfill_windowed" and source not in BACKFILL_SUPPORTED_SOURCES:
        raise ValueError(
            f"source `{source}` nao suporta backfill_windowed (use incremental_recent)"
        )
    return EXPORTERS[source](limit)


def _extract_max_id(bundle_notes: list[str]) -> int | None:
    for note in bundle_notes:
        if note.startswith("max_id="):
            try:
                return int(note.split("=", 1)[1])
            except ValueError:
                return None
    return None


def run(source: str, *, limit: int, dry_run: bool, mode: str) -> int:
    load_repo_envs()
    checkpoint_before = load_state(source) if mode == "backfill_windowed" else None
    after_id = int((checkpoint_before or {}).get("last_id", 0))
    bundle = _build_bundle(source, limit=limit, mode=mode, after_id=after_id)
    timestamp = utc_compact()
    out_path = report_path(f"{timestamp}_{source}.jsonl")
    write_jsonl(out_path, bundle.items)

    apply_payload: dict | None = None
    apply_status = "success"
    if not dry_run:
        try:
            writer_result = apply_bundle(bundle.items, source=source)
            apply_payload = writer_result.to_payload()
            if writer_result.errors:
                apply_status = "partial"
        except Exception as exc:
            apply_payload = {
                "source": source,
                "processed": len(bundle.items),
                "errors": [f"{type(exc).__name__}: {str(exc)[:300]}"],
            }
            apply_status = "failed"

    checkpoint_after: dict | None = None
    if mode == "backfill_windowed" and not dry_run and apply_status != "failed":
        max_id = _extract_max_id(bundle.notes)
        if max_id is not None and max_id > after_id:
            state_path = save_state(source, last_id=max_id, mode=mode)
            checkpoint_after = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            # Sem novos items: mantem o checkpoint, mas ainda grava um touch
            # para visualizar "fim da base" (bundle.items == 0).
            if len(bundle.items) == 0 and checkpoint_before is not None:
                checkpoint_after = {**checkpoint_before, "note": "reached_end_or_no_progress"}

    summary_path = report_path(f"{timestamp}_{source}_summary.md")
    summary_path.write_text(
        _summary_md(
            source,
            mode,
            dry_run,
            len(bundle.items),
            out_path,
            apply_payload,
            bundle.notes,
            checkpoint_before,
            checkpoint_after,
        ),
        encoding="utf-8",
    )

    reporter = make_reporter(MANIFEST_PATH)
    if reporter:
        reporter.register()
        reporter.start_run(
            run_params={
                "source": source,
                "limit": limit,
                "dry_run": dry_run,
                "mode": mode,
                "after_id": after_id,
            }
        )
        # Regra MVP: items_final_inserted=0 nos metricos de batch/run do SDK.
        # As contagens reais de apply ficam no event payload e no summary.
        reporter.batch_metrics(
            seq=0,
            items_extracted=len(bundle.items),
            items_valid_local=len(bundle.items),
            items_sent=len(bundle.items),
            items_final_inserted=0,
            source_lineage={
                "source_system": "reviews_scores_plug",
                "source_kind": "file",
                "source_pointer": str(out_path),
                "source_record_count": len(bundle.items),
                "notes": f"source={source}; dry_run={dry_run}; mode={mode}"[:256],
            },
        )
        audit_message_parts = [
            f"source={source} mode={mode} items={len(bundle.items)} dry_run={dry_run}"
        ]
        if apply_payload:
            audit_message_parts.append(
                " ".join(
                    f"{k}={apply_payload.get(k)}"
                    for k in (
                        "matched",
                        "unmatched",
                        "wine_scores_upserted",
                        "wine_scores_changed",
                        "wines_rating_updated",
                        "batches_committed",
                    )
                )
            )
        reporter.event(
            code="plug.reviews_scores.summary",
            message=" | ".join(audit_message_parts)[:1024],
            level="audit",
            payload_pointer=str(summary_path),
            payload_sample=json.dumps(bundle.items[:2], ensure_ascii=False)[:1024] if bundle.items else None,
        )
        end_status = "success" if apply_status in ("success", "partial") else "failed"
        reporter.end(
            status=end_status,
            items_extracted=len(bundle.items),
            items_valid_local=len(bundle.items),
            items_sent=len(bundle.items),
            items_final_inserted=0,
            batches_total=1,
        )
    return 0 if apply_status != "failed" else 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Plug de sinais derivados de reviews/scores")
    parser.add_argument("--source", required=True, choices=sorted(EXPORTERS))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--mode",
        choices=MODES,
        default="incremental_recent",
        help=(
            "incremental_recent = topo mais recente (default, nao progride). "
            "backfill_windowed = varre a base com checkpoint persistente."
        ),
    )
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error("--apply e --dry-run sao mutuamente exclusivos")
    if args.apply and args.source in PER_REVIEW_SOURCES:
        parser.error(
            f"source `{args.source}` e per-review e nao aplica em wine_scores. "
            "Use `vivino_wines_to_ratings` para apply de rating Vivino."
        )
    if args.mode == "backfill_windowed" and args.source not in BACKFILL_SUPPORTED_SOURCES:
        parser.error(
            f"source `{args.source}` nao suporta mode=backfill_windowed. "
            f"Suportadas: {sorted(BACKFILL_SUPPORTED_SOURCES)}"
        )
    dry_run = not args.apply
    return run(args.source, limit=args.limit, dry_run=dry_run, mode=args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
