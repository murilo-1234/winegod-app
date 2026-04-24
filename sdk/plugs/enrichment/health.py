"""Health check observacional do dominio enrichment.

READ-ONLY. Nao chama Gemini, nao chama banco em modo de escrita, nao
modifica state/staging.

Observa:
  - artefatos locais (`reports/gemini_batch_state.json`,
    `reports/gemini_batch_input.jsonl`, `reports/gemini_batch_output.jsonl`,
    `reports/ingest_pipeline_enriched/**`);
  - ultimo summary markdown em `reports/data_ops_plugs_staging/`;
  - ultimos logs do scheduler em `reports/data_ops_scheduler/`;
  - state do bundle (`observed` vs `blocked_missing_source`).

Classifica em `ok` / `warning` / `failed` e expoe a foto como JSON/MD.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_ROOT = REPO_ROOT / "reports"
STAGING_DIR = REPORTS_ROOT / "data_ops_plugs_staging"
SCHED_DIR = REPORTS_ROOT / "data_ops_scheduler"
STATE_PATH = REPORTS_ROOT / "gemini_batch_state.json"
INPUT_PATH = REPORTS_ROOT / "gemini_batch_input.jsonl"
OUTPUT_PATH = REPORTS_ROOT / "gemini_batch_output.jsonl"
ENRICHED_ROOT = REPORTS_ROOT / "ingest_pipeline_enriched"
CANONICAL_SOURCE = "gemini_batch_reports"


def _latest(path: Path, pattern: str) -> Path | None:
    if not path.exists():
        return None
    items = sorted(
        (p for p in path.glob(pattern) if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return items[0] if items else None


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _collect_artifacts() -> dict[str, Any]:
    def _info(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"present": False, "path": str(path)}
        stat = path.stat()
        return {
            "present": True,
            "path": str(path),
            "mtime_utc": _iso(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)),
            "size_bytes": stat.st_size,
        }

    enriched_count = 0
    if ENRICHED_ROOT.exists():
        enriched_count = sum(1 for _ in ENRICHED_ROOT.rglob("*.jsonl")) + sum(
            1 for _ in ENRICHED_ROOT.rglob("*.csv")
        )
    return {
        "state": _info(STATE_PATH),
        "input": _info(INPUT_PATH),
        "output": _info(OUTPUT_PATH),
        "enriched_root_exists": ENRICHED_ROOT.exists(),
        "enriched_artifact_count": enriched_count,
    }


_STATE_RE = re.compile(r"- state: `([a-z_]+)`")
_ITEMS_RE = re.compile(r"- items: `(\d+)`")
_READY_RE = re.compile(r"- ready: `(\d+)`")
_UNCERTAIN_RE = re.compile(r"- uncertain: `(\d+)`")
_NOT_WINE_RE = re.compile(r"- not_wine: `(\d+)`")


def _collect_latest_summary() -> dict[str, Any]:
    summary = _latest(STAGING_DIR, f"*_{CANONICAL_SOURCE}_enrichment_summary.md")
    if not summary:
        return {"present": False}
    text = summary.read_text(encoding="utf-8", errors="replace")
    stat = summary.stat()

    def _int(regex: re.Pattern[str]) -> int | None:
        m = regex.search(text)
        return int(m.group(1)) if m else None

    state_m = _STATE_RE.search(text)
    return {
        "present": True,
        "path": str(summary),
        "mtime_utc": _iso(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)),
        "state": state_m.group(1) if state_m else None,
        "items": _int(_ITEMS_RE),
        "ready": _int(_READY_RE),
        "uncertain": _int(_UNCERTAIN_RE),
        "not_wine": _int(_NOT_WINE_RE),
    }


def _collect_latest_log() -> dict[str, Any]:
    log = _latest(SCHED_DIR, f"*_enrichment_dryrun_{CANONICAL_SOURCE}.log")
    if not log:
        return {"present": False, "dir": str(SCHED_DIR)}
    stat = log.stat()
    return {
        "present": True,
        "path": str(log),
        "mtime_utc": _iso(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)),
    }


def assess_health(*, stale_hours: float = 168.0, now: datetime | None = None) -> dict[str, Any]:
    """Snapshot read-only do dominio enrichment.

    stale_hours: janela para considerar o ultimo summary velho (default 7 dias).
    Enrichment e cadencia semanal/diaria, nao sub-horaria.
    """
    now = now or datetime.now(timezone.utc)
    artifacts = _collect_artifacts()
    summary = _collect_latest_summary()
    log = _collect_latest_log()

    reasons: list[str] = []
    warnings: list[str] = []

    any_artifact = any(
        artifacts[key].get("present")
        for key in ("state", "input", "output")
    ) or artifacts["enriched_artifact_count"] > 0
    if not any_artifact:
        reasons.append("no_enrichment_artifacts_found")

    if summary.get("present"):
        mtime = summary.get("mtime_utc")
        if mtime:
            dt = datetime.fromisoformat(mtime.replace("Z", "+00:00"))
            if now - dt > timedelta(hours=stale_hours):
                warnings.append(
                    f"summary_stale_last_run_{int((now - dt).total_seconds() // 3600)}h_ago"
                )
        if summary.get("state") and summary.get("state") != "observed":
            warnings.append(f"summary_state_{summary.get('state')}")
    else:
        warnings.append("no_summary_yet")

    status = "failed" if reasons else ("warning" if warnings else "ok")

    return {
        "source": CANONICAL_SOURCE,
        "generated_at_utc": _iso(now),
        "status": status,
        "reasons": reasons,
        "warnings": warnings,
        "artifacts": artifacts,
        "latest_summary": summary,
        "latest_log": log,
        "contract": {
            "canonical_source": CANONICAL_SOURCE,
            "writes_to_final_tables": False,
            "allowed_outputs": ["ops"],
            "non_goals": [
                "public.wines",
                "public.wine_sources",
                "gemini_live_call",
                "flash_live_call",
            ],
        },
    }


def status_to_exit_code(status: str) -> int:
    return {"ok": 0, "warning": 2, "failed": 3}.get(status, 3)


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Enrichment Dominio Health Check",
        "",
        f"- source: `{report['source']}`",
        f"- status: `{report['status']}`",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
    ]
    if report["reasons"]:
        lines.append(f"- reasons: `{', '.join(report['reasons'])}`")
    if report["warnings"]:
        lines.append(f"- warnings: `{', '.join(report['warnings'])}`")
    arts = report["artifacts"]
    lines.append("")
    lines.append("## Artefatos locais")
    for key in ("state", "input", "output"):
        info = arts[key]
        lines.append(f"- {key}.present: `{info.get('present')}`")
        if info.get("present"):
            lines.append(f"  - path: `{info.get('path')}`")
            lines.append(f"  - mtime_utc: `{info.get('mtime_utc')}`")
    lines.append(f"- enriched_root_exists: `{arts['enriched_root_exists']}`")
    lines.append(f"- enriched_artifact_count: `{arts['enriched_artifact_count']}`")
    summary = report["latest_summary"]
    if summary.get("present"):
        lines.extend(
            [
                "",
                "## Ultimo summary",
                f"- path: `{summary.get('path')}`",
                f"- mtime_utc: `{summary.get('mtime_utc')}`",
                f"- state: `{summary.get('state')}`",
                f"- items: `{summary.get('items')}`",
                f"- ready: `{summary.get('ready')}`",
                f"- uncertain: `{summary.get('uncertain')}`",
                f"- not_wine: `{summary.get('not_wine')}`",
            ]
        )
    log = report["latest_log"]
    if log.get("present"):
        lines.extend(
            [
                "",
                "## Ultimo log do scheduler",
                f"- path: `{log.get('path')}`",
                f"- mtime_utc: `{log.get('mtime_utc')}`",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Health check do dominio enrichment")
    parser.add_argument("--stale-hours", type=float, default=168.0)
    parser.add_argument("--stdout", choices=("json", "md"), default="json")
    parser.add_argument("--write-md", type=str, default=None)
    args = parser.parse_args()
    report = assess_health(stale_hours=args.stale_hours)
    if args.stdout == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_md(report))
    if args.write_md:
        Path(args.write_md).write_text(_render_md(report), encoding="utf-8")
    return status_to_exit_code(report["status"])


if __name__ == "__main__":
    raise SystemExit(main())
