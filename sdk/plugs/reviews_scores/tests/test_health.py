from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sdk.plugs.reviews_scores import health as health_mod


def _setup_dirs(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    state_dir = tmp_path / "state"
    staging_dir = tmp_path / "staging"
    back_dir = tmp_path / "sched" / "vivino_reviews_backfill"
    inc_dir = tmp_path / "sched" / "vivino_reviews_incremental"
    for d in (state_dir, staging_dir, back_dir, inc_dir):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(health_mod, "STATE_DIR", state_dir)
    monkeypatch.setattr(health_mod, "STAGING_DIR", staging_dir)
    monkeypatch.setattr(health_mod, "SCHED_BACKFILL_DIR", back_dir)
    monkeypatch.setattr(health_mod, "SCHED_INCREMENTAL_DIR", inc_dir)
    monkeypatch.setattr(
        health_mod,
        "STATE_FILE",
        state_dir / f"{health_mod.CANONICAL_SOURCE}.json",
    )
    monkeypatch.setattr(
        health_mod,
        "SENTINEL_FILE",
        state_dir / f"{health_mod.CANONICAL_SOURCE}.BACKFILL_DONE",
    )
    return {
        "state_dir": state_dir,
        "staging_dir": staging_dir,
        "back_dir": back_dir,
        "inc_dir": inc_dir,
    }


def _write_state(dirs: dict[str, Path], *, last_id: int, runs: int, updated_at: str) -> Path:
    payload = {
        "source": health_mod.CANONICAL_SOURCE,
        "mode": "backfill_windowed",
        "last_id": last_id,
        "updated_at": updated_at,
        "runs": runs,
    }
    path = dirs["state_dir"] / f"{health_mod.CANONICAL_SOURCE}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_summary(dirs: dict[str, Path], *, items: int, mode: str, payload: dict) -> Path:
    text = (
        "# Reviews Scores Plug\n\n"
        f"- source: `{health_mod.CANONICAL_SOURCE}`\n"
        f"- mode: `{mode}`\n"
        "- delivery_mode: `apply`\n"
        f"- items: `{items}`\n\n"
        "## Apply result\n\n"
        "```json\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "```\n"
    )
    path = dirs["staging_dir"] / f"20260424_120000_{health_mod.CANONICAL_SOURCE}_summary.md"
    path.write_text(text, encoding="utf-8")
    return path


def _write_log(dir_path: Path, *, exit_code: int) -> Path:
    content = f"started_at=2026-04-24T10:00:00Z\nexit={exit_code}\n"
    path = dir_path / "20260424_100000_test.log"
    path.write_text(content, encoding="utf-8")
    return path


def test_health_ok_when_cursor_fresh_and_no_errors(tmp_path, monkeypatch):
    dirs = _setup_dirs(tmp_path, monkeypatch)
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    updated_at = (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    _write_state(dirs, last_id=1_500_000, runs=10, updated_at=updated_at)
    payload = {
        "source": health_mod.CANONICAL_SOURCE,
        "processed": 10000,
        "matched": 9950,
        "unmatched": 50,
        "wine_scores_upserted": 9950,
        "wine_scores_changed": 5,
        "wines_rating_updated": 0,
        "skipped_per_review": 0,
        "skipped_no_score": 0,
        "batches_committed": 1,
        "errors": [],
    }
    _write_summary(dirs, items=10000, mode="backfill_windowed", payload=payload)
    _write_log(dirs["back_dir"], exit_code=0)
    _write_log(dirs["inc_dir"], exit_code=0)

    report = health_mod.assess_health(now=now)
    assert report["status"] == "ok"
    assert report["reasons"] == []
    assert report["warnings"] == []
    assert report["state"]["last_id"] == 1_500_000
    assert report["latest_summary"]["items"] == 10000
    assert report["sentinel"]["present"] is False
    assert health_mod.status_to_exit_code(report["status"]) == 0


def test_health_warning_when_cursor_stale_without_sentinel(tmp_path, monkeypatch):
    dirs = _setup_dirs(tmp_path, monkeypatch)
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    updated_at = (now - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
    _write_state(dirs, last_id=1_500_000, runs=10, updated_at=updated_at)
    _write_log(dirs["back_dir"], exit_code=0)
    _write_log(dirs["inc_dir"], exit_code=0)

    report = health_mod.assess_health(now=now, stall_hours=3.0)
    assert report["status"] == "warning"
    assert any("cursor_stale" in w for w in report["warnings"])
    assert health_mod.status_to_exit_code(report["status"]) == 2


def test_health_failed_when_last_run_nonzero_exit(tmp_path, monkeypatch):
    dirs = _setup_dirs(tmp_path, monkeypatch)
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    updated_at = (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    _write_state(dirs, last_id=1_500_000, runs=10, updated_at=updated_at)
    _write_log(dirs["back_dir"], exit_code=3)

    report = health_mod.assess_health(now=now)
    assert report["status"] == "failed"
    assert any("backfill_last_run_exit_3" == r for r in report["reasons"])
    assert health_mod.status_to_exit_code(report["status"]) == 3


def test_health_ok_when_sentinel_present(tmp_path, monkeypatch):
    dirs = _setup_dirs(tmp_path, monkeypatch)
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    updated_at = (now - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    _write_state(dirs, last_id=2_000_000, runs=250, updated_at=updated_at)
    # Sentinela presente -> backfill concluido, cursor velho nao e problema.
    (dirs["state_dir"] / f"{health_mod.CANONICAL_SOURCE}.BACKFILL_DONE").write_text(
        "backfill_reached_end_at=2026-04-22T10:00:00Z\n",
        encoding="utf-8",
    )
    report = health_mod.assess_health(now=now, stall_hours=3.0)
    assert report["status"] == "ok_backfill_done"
    assert report["sentinel"]["present"] is True
    assert health_mod.status_to_exit_code(report["status"]) == 0


def test_health_markdown_render_contains_status_and_state(tmp_path, monkeypatch):
    dirs = _setup_dirs(tmp_path, monkeypatch)
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    updated_at = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    _write_state(dirs, last_id=42, runs=1, updated_at=updated_at)
    report = health_mod.assess_health(now=now)
    md = health_mod._render_md(report)
    assert "Reviews Dominio Health Check" in md
    assert "last_id: `42`" in md
    assert "status: `ok`" in md


def test_health_missing_state_is_failed(tmp_path, monkeypatch):
    _setup_dirs(tmp_path, monkeypatch)
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    report = health_mod.assess_health(now=now)
    assert "checkpoint_state_missing" in report["reasons"]
    assert report["status"] == "failed"
