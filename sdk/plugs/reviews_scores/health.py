"""Health check observacional do canal canonico vivino_wines_to_ratings.

Este modulo NAO executa apply. Ele apenas observa o estado do dominio reviews
para dar uma foto rapida e auditavel ao operador/painel:

  - cursor persistente (`reports/data_ops_plugs_state/vivino_wines_to_ratings.json`);
  - sentinela de fim de backfill (`*.BACKFILL_DONE`);
  - ultimos N summaries do staging (`reports/data_ops_plugs_staging/`);
  - ultimos logs do scheduler (backfill/incremental em `reports/data_ops_scheduler/`);
  - heuristica de staleness do cursor e erros recentes.

Saida:
  - stdout: JSON compacto (consumivel pelo painel / control plane);
  - retorno main(): 0 (ok), 2 (warning), 3 (stalled/failed).

Regras:
  - READ-ONLY: nenhuma conexao a banco, nenhuma escrita alem do log opcional;
  - sem efeitos colaterais no plug oficial;
  - nao reimplementa apply nem backfill.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
STATE_DIR = REPO_ROOT / "reports" / "data_ops_plugs_state"
STAGING_DIR = REPO_ROOT / "reports" / "data_ops_plugs_staging"
SCHED_BACKFILL_DIR = REPO_ROOT / "reports" / "data_ops_scheduler" / "vivino_reviews_backfill"
SCHED_INCREMENTAL_DIR = REPO_ROOT / "reports" / "data_ops_scheduler" / "vivino_reviews_incremental"

CANONICAL_SOURCE = "vivino_wines_to_ratings"
STATE_FILE = STATE_DIR / f"{CANONICAL_SOURCE}.json"
SENTINEL_FILE = STATE_DIR / f"{CANONICAL_SOURCE}.BACKFILL_DONE"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _latest(path: Path, pattern: str = "*") -> Path | None:
    if not path.exists():
        return None
    items = sorted(
        (p for p in path.glob(pattern) if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return items[0] if items else None


_APPLY_JSON_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _apply_payload_from_summary(summary_path: Path) -> dict[str, Any] | None:
    try:
        text = summary_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _APPLY_JSON_RE.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _mode_from_summary(summary_path: Path) -> str | None:
    try:
        text = summary_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"- mode: `([^`]+)`", text)
    return m.group(1) if m else None


def _items_from_summary(summary_path: Path) -> int | None:
    try:
        text = summary_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"- items: `(\d+)`", text)
    return int(m.group(1)) if m else None


def _collect_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {
            "present": False,
            "last_id": None,
            "runs": 0,
            "updated_at": None,
            "mode": None,
        }
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"present": False, "malformed": True}
    return {
        "present": True,
        "last_id": int(data.get("last_id", 0)),
        "runs": int(data.get("runs", 0)),
        "updated_at": data.get("updated_at"),
        "mode": data.get("mode"),
    }


def _collect_sentinel() -> dict[str, Any]:
    if not SENTINEL_FILE.exists():
        return {"present": False}
    try:
        text = SENTINEL_FILE.read_text(encoding="utf-8")
    except OSError:
        return {"present": True, "unreadable": True}
    return {"present": True, "content": text.strip()[:1024]}


def _collect_latest_summary() -> dict[str, Any]:
    summary = _latest(STAGING_DIR, f"*{CANONICAL_SOURCE}_summary.md")
    if not summary:
        return {"present": False}
    stat = summary.stat()
    updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "present": True,
        "path": str(summary),
        "mtime_utc": updated_at,
        "mode": _mode_from_summary(summary),
        "items": _items_from_summary(summary),
        "apply_payload": _apply_payload_from_summary(summary),
    }


def _collect_latest_log(sched_dir: Path) -> dict[str, Any]:
    if not sched_dir.exists():
        return {"present": False, "dir": str(sched_dir)}
    log = _latest(sched_dir, "*.log")
    if not log:
        return {"present": False, "dir": str(sched_dir)}
    stat = log.stat()
    text = ""
    try:
        with open(log, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        pass
    exit_m = re.search(r"^exit=(-?\d+)", text, re.MULTILINE)
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "present": True,
        "path": str(log),
        "mtime_utc": mtime,
        "exit": int(exit_m.group(1)) if exit_m else None,
    }


def assess_health(*, stall_hours: float = 3.0, now: datetime | None = None) -> dict[str, Any]:
    """Coleta foto rapida do dominio reviews e classifica em ok/warning/failed.

    Args:
        stall_hours: janela em horas para considerar o cursor parado sem sentinela.
        now: injetado nos testes; default utc.
    """
    now = now or datetime.now(timezone.utc)
    state = _collect_state()
    sentinel = _collect_sentinel()
    summary = _collect_latest_summary()
    backfill_log = _collect_latest_log(SCHED_BACKFILL_DIR)
    incremental_log = _collect_latest_log(SCHED_INCREMENTAL_DIR)

    reasons: list[str] = []
    warnings: list[str] = []

    if not state.get("present"):
        reasons.append("checkpoint_state_missing")
    else:
        updated = _parse_iso(state.get("updated_at"))
        if updated is not None and not sentinel.get("present"):
            delta = now - updated
            if delta > timedelta(hours=stall_hours):
                warnings.append(
                    f"cursor_stale_last_updated_{int(delta.total_seconds() // 60)}_minutes_ago"
                )

    for name, log in (("backfill", backfill_log), ("incremental", incremental_log)):
        if log.get("present") and log.get("exit") not in (0, None):
            reasons.append(f"{name}_last_run_exit_{log.get('exit')}")

    apply_payload = summary.get("apply_payload") or {}
    if apply_payload.get("errors"):
        reasons.append("last_summary_has_errors")

    if sentinel.get("present"):
        status = "ok_backfill_done"
    elif reasons:
        status = "failed"
    elif warnings:
        status = "warning"
    else:
        status = "ok"

    return {
        "source": CANONICAL_SOURCE,
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "status": status,
        "reasons": reasons,
        "warnings": warnings,
        "state": state,
        "sentinel": sentinel,
        "latest_summary": summary,
        "backfill_log": backfill_log,
        "incremental_log": incremental_log,
        "contract": {
            "canonical_source": CANONICAL_SOURCE,
            "applies_to": ["public.wine_scores", "public.wines.vivino_rating", "public.wines.vivino_reviews"],
            "wcf_enqueue_trigger": "trg_score_recalc",
            "paused_sources": [
                "scores_cellartracker",
                "critics_decanter_persisted",
                "critics_wine_enthusiast",
                "market_winesearcher",
            ],
        },
    }


def status_to_exit_code(status: str) -> int:
    if status.startswith("ok"):
        return 0
    if status == "warning":
        return 2
    return 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Health check do dominio reviews (vivino)")
    parser.add_argument("--stall-hours", type=float, default=3.0)
    parser.add_argument(
        "--write-md",
        type=str,
        default=None,
        help="Opcional: caminho de saida para um snapshot markdown legivel.",
    )
    parser.add_argument(
        "--stdout",
        choices=("json", "md"),
        default="json",
        help="Formato de saida no stdout.",
    )
    args = parser.parse_args()
    report = assess_health(stall_hours=args.stall_hours)
    if args.stdout == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_md(report))
    if args.write_md:
        Path(args.write_md).write_text(_render_md(report), encoding="utf-8")
    return status_to_exit_code(report["status"])


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Reviews Dominio Health Check",
        "",
        f"- source: `{report['source']}`",
        f"- status: `{report['status']}`",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
    ]
    if report["reasons"]:
        lines.append(f"- reasons: `{', '.join(report['reasons'])}`")
    if report["warnings"]:
        lines.append(f"- warnings: `{', '.join(report['warnings'])}`")
    state = report["state"]
    lines.extend(
        [
            "",
            "## Checkpoint",
            f"- present: `{state.get('present')}`",
            f"- last_id: `{state.get('last_id')}`",
            f"- runs: `{state.get('runs')}`",
            f"- updated_at: `{state.get('updated_at')}`",
            f"- mode: `{state.get('mode')}`",
            "",
            "## Sentinela fim de backfill",
            f"- present: `{report['sentinel'].get('present')}`",
        ]
    )
    summary = report["latest_summary"]
    if summary.get("present"):
        lines.extend(
            [
                "",
                "## Ultimo summary",
                f"- path: `{summary.get('path')}`",
                f"- mtime_utc: `{summary.get('mtime_utc')}`",
                f"- mode: `{summary.get('mode')}`",
                f"- items: `{summary.get('items')}`",
            ]
        )
        apply_payload = summary.get("apply_payload")
        if apply_payload:
            lines.append("")
            lines.append("### Apply payload")
            lines.append("```json")
            lines.append(json.dumps(apply_payload, indent=2, ensure_ascii=False))
            lines.append("```")
    for label, key in (("Backfill", "backfill_log"), ("Incremental", "incremental_log")):
        log = report[key]
        if log.get("present"):
            lines.extend(
                [
                    "",
                    f"## {label} ultimo log",
                    f"- path: `{log.get('path')}`",
                    f"- mtime_utc: `{log.get('mtime_utc')}`",
                    f"- exit: `{log.get('exit')}`",
                ]
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
