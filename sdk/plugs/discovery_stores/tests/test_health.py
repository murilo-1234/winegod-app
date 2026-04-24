from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sdk.plugs.discovery_stores import health as h


def _setup(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    staging = tmp_path / "staging"
    sched = tmp_path / "sched"
    natura = tmp_path / "natura"
    (natura / "agent_discovery").mkdir(parents=True, exist_ok=True)
    staging.mkdir(parents=True, exist_ok=True)
    sched.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(h, "STAGING_DIR", staging)
    monkeypatch.setattr(h, "SCHED_DIR", sched)
    monkeypatch.setattr(h, "NATURA_ROOT", natura)
    monkeypatch.setattr(h, "DISCOVERY_PHASES", natura / "agent_discovery" / "discovery_phases.json")
    return {"staging": staging, "sched": sched, "natura": natura}


def _write_summary(staging: Path, *, items: int, state: str, known: int) -> Path:
    text = (
        "# Discovery Stores Plug\n\n"
        f"- source: `agent_discovery`\n"
        f"- state: `{state}`\n"
        "- delivery_mode: `dry_run`\n"
        f"- items: `{items}`\n"
        f"- known_store_hits: `{known}`\n"
    )
    path = staging / f"20260424_060000_agent_discovery_discovery_stores_summary.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_discovery_health_failed_when_no_source_files(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    report = h.assess_health()
    assert report["status"] == "failed"
    assert "no_source_files_found" in report["reasons"]


def test_discovery_health_ok_when_everything_ready(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    (dirs["natura"] / "ecommerces_vinhos_br_v2.json").write_text("{}", encoding="utf-8")
    (dirs["natura"] / "agent_discovery" / "discovery_phases.json").write_text("{}", encoding="utf-8")
    _write_summary(dirs["staging"], items=100, state="observed", known=40)
    now = datetime.now(timezone.utc)
    report = h.assess_health(now=now, stale_hours=168.0)
    assert report["status"] == "ok"
    assert report["latest_summary"]["items"] == 100
    assert report["latest_summary"]["known_store_hits"] == 40


def test_discovery_health_warning_when_summary_stale(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    (dirs["natura"] / "ecommerces_vinhos_br_v2.json").write_text("{}", encoding="utf-8")
    (dirs["natura"] / "agent_discovery" / "discovery_phases.json").write_text("{}", encoding="utf-8")
    summary = _write_summary(dirs["staging"], items=50, state="observed", known=10)
    # Marca o summary como ANTIGO.
    old_time = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
    import os
    os.utime(summary, (old_time, old_time))
    report = h.assess_health(stale_hours=24.0)
    assert report["status"] == "warning"
    assert any("summary_stale" in w for w in report["warnings"])


def test_discovery_health_warning_when_state_not_observed(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    (dirs["natura"] / "ecommerces_vinhos_br_v2.json").write_text("{}", encoding="utf-8")
    (dirs["natura"] / "agent_discovery" / "discovery_phases.json").write_text("{}", encoding="utf-8")
    _write_summary(dirs["staging"], items=0, state="blocked_missing_source", known=0)
    report = h.assess_health(stale_hours=168.0)
    assert report["status"] == "warning"
    assert any("summary_state_blocked_missing_source" == w for w in report["warnings"])


def test_status_to_exit_code_maps_correctly():
    assert h.status_to_exit_code("ok") == 0
    assert h.status_to_exit_code("warning") == 2
    assert h.status_to_exit_code("failed") == 3
    assert h.status_to_exit_code("unexpected") == 3


def test_render_md_includes_status_and_contract(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    (dirs["natura"] / "ecommerces_vinhos_br_v2.json").write_text("{}", encoding="utf-8")
    _write_summary(dirs["staging"], items=1, state="observed", known=0)
    report = h.assess_health()
    md = h._render_md(report)
    assert "Discovery Dominio Health Check" in md
    assert "files_count: `1`" in md
