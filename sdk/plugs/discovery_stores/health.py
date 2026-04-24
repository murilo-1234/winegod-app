"""Health check observacional do dominio discovery.

READ-ONLY. Nao chama banco, nao chama APIs externas, nao modifica state.

Observa:
  - existencia dos artifacts de origem em ``C:\\natura-automation\\``;
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
STAGING_DIR = REPO_ROOT / "reports" / "data_ops_plugs_staging"
SCHED_DIR = REPO_ROOT / "reports" / "data_ops_scheduler"
NATURA_ROOT = Path("C:/natura-automation")
DISCOVERY_PHASES = NATURA_ROOT / "agent_discovery" / "discovery_phases.json"
DISCOVERY_GLOB = "ecommerces_vinhos_*_v2.json"
CANONICAL_SOURCE = "agent_discovery"


def _latest(path: Path, pattern: str) -> Path | None:
    if not path.exists():
        return None
    items = sorted(
        (p for p in path.glob(pattern) if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return items[0] if items else None


def _collect_source_artifacts() -> dict[str, Any]:
    phases_exists = DISCOVERY_PHASES.exists()
    files = sorted(
        NATURA_ROOT.glob(DISCOVERY_GLOB),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    latest: dict[str, Any] = {}
    if files:
        stat = files[0].stat()
        latest = {
            "path": str(files[0]),
            "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "size_bytes": stat.st_size,
        }
    return {
        "root_exists": NATURA_ROOT.exists(),
        "phases_exists": phases_exists,
        "files_count": len(files),
        "latest_file": latest,
    }


_ITEMS_RE = re.compile(r"- items: `(\d+)`")
_STATE_RE = re.compile(r"- state: `([a-z_]+)`")
_KNOWN_RE = re.compile(r"- known_store_hits: `(\d+)`")


def _collect_latest_summary() -> dict[str, Any]:
    summary = _latest(STAGING_DIR, f"*_{CANONICAL_SOURCE}_discovery_stores_summary.md")
    if not summary:
        return {"present": False}
    text = summary.read_text(encoding="utf-8", errors="replace")
    stat = summary.stat()
    items_m = _ITEMS_RE.search(text)
    state_m = _STATE_RE.search(text)
    known_m = _KNOWN_RE.search(text)
    return {
        "present": True,
        "path": str(summary),
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "items": int(items_m.group(1)) if items_m else None,
        "state": state_m.group(1) if state_m else None,
        "known_store_hits": int(known_m.group(1)) if known_m else None,
    }


def _collect_latest_log() -> dict[str, Any]:
    log = _latest(SCHED_DIR, f"*_discovery_dryrun_{CANONICAL_SOURCE}.log")
    if not log:
        return {"present": False, "dir": str(SCHED_DIR)}
    stat = log.stat()
    return {
        "present": True,
        "path": str(log),
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def assess_health(*, stale_hours: float = 168.0, now: datetime | None = None) -> dict[str, Any]:
    """Snapshot read-only do dominio discovery.

    stale_hours: janela para considerar o ultimo summary velho. Default 168h
    (7 dias) porque discovery e daily/weekly, nao sub-horario.
    """
    now = now or datetime.now(timezone.utc)
    artifacts = _collect_source_artifacts()
    summary = _collect_latest_summary()
    log = _collect_latest_log()

    reasons: list[str] = []
    warnings: list[str] = []

    if not artifacts["root_exists"]:
        reasons.append("natura_root_missing")
    elif artifacts["files_count"] == 0:
        reasons.append("no_source_files_found")
    if not artifacts["phases_exists"]:
        warnings.append("discovery_phases_json_missing")

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
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "status": status,
        "reasons": reasons,
        "warnings": warnings,
        "source_artifacts": artifacts,
        "latest_summary": summary,
        "latest_log": log,
        "contract": {
            "canonical_source": CANONICAL_SOURCE,
            "writes_to_final_tables": False,
            "allowed_outputs": ["ops"],
            "non_goals": [
                "public.wines",
                "public.wine_sources",
                "public.stores",
                "public.store_recipes",
            ],
        },
    }


def status_to_exit_code(status: str) -> int:
    return {"ok": 0, "warning": 2, "failed": 3}.get(status, 3)


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Discovery Dominio Health Check",
        "",
        f"- source: `{report['source']}`",
        f"- status: `{report['status']}`",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
    ]
    if report["reasons"]:
        lines.append(f"- reasons: `{', '.join(report['reasons'])}`")
    if report["warnings"]:
        lines.append(f"- warnings: `{', '.join(report['warnings'])}`")
    arts = report["source_artifacts"]
    lines.extend(
        [
            "",
            "## Artefatos de origem",
            f"- root_exists: `{arts['root_exists']}`",
            f"- phases_exists: `{arts['phases_exists']}`",
            f"- files_count: `{arts['files_count']}`",
        ]
    )
    if arts.get("latest_file"):
        latest = arts["latest_file"]
        lines.append(f"- latest_file: `{latest.get('path')}`")
        lines.append(f"- latest_file_mtime_utc: `{latest.get('mtime_utc')}`")
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
                f"- known_store_hits: `{summary.get('known_store_hits')}`",
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
    parser = argparse.ArgumentParser(description="Health check do dominio discovery")
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
