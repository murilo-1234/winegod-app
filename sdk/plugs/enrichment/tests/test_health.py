from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sdk.plugs.enrichment import health as h


def _setup(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    reports = tmp_path / "reports"
    staging = reports / "data_ops_plugs_staging"
    sched = reports / "data_ops_scheduler"
    enriched = reports / "ingest_pipeline_enriched"
    for d in (staging, sched, enriched):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(h, "REPORTS_ROOT", reports)
    monkeypatch.setattr(h, "STAGING_DIR", staging)
    monkeypatch.setattr(h, "SCHED_DIR", sched)
    monkeypatch.setattr(h, "STATE_PATH", reports / "gemini_batch_state.json")
    monkeypatch.setattr(h, "INPUT_PATH", reports / "gemini_batch_input.jsonl")
    monkeypatch.setattr(h, "OUTPUT_PATH", reports / "gemini_batch_output.jsonl")
    monkeypatch.setattr(h, "ENRICHED_ROOT", enriched)
    return {"reports": reports, "staging": staging, "sched": sched, "enriched": enriched}


def _write_summary(staging: Path, *, items: int, state: str, ready: int, uncertain: int, not_wine: int) -> Path:
    text = (
        "# Enrichment Plug\n\n"
        f"- source: `gemini_batch_reports`\n"
        f"- state: `{state}`\n"
        "- delivery_mode: `dry_run`\n"
        f"- items: `{items}`\n"
        f"- ready: `{ready}`\n"
        f"- uncertain: `{uncertain}`\n"
        f"- not_wine: `{not_wine}`\n"
    )
    path = staging / "20260424_060000_gemini_batch_reports_enrichment_summary.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_failed_when_no_artifacts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    report = h.assess_health()
    assert report["status"] == "failed"
    assert "no_enrichment_artifacts_found" in report["reasons"]


def test_ok_when_artifacts_and_fresh_summary(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    (dirs["reports"] / "gemini_batch_state.json").write_text('{}', encoding="utf-8")
    (dirs["reports"] / "gemini_batch_input.jsonl").write_text("", encoding="utf-8")
    _write_summary(dirs["staging"], items=10, state="observed", ready=7, uncertain=2, not_wine=1)
    report = h.assess_health(stale_hours=168.0)
    assert report["status"] == "ok"
    assert report["latest_summary"]["items"] == 10
    assert report["latest_summary"]["ready"] == 7


def test_warning_when_summary_state_blocked(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    (dirs["reports"] / "gemini_batch_state.json").write_text('{}', encoding="utf-8")
    _write_summary(dirs["staging"], items=0, state="blocked_missing_source", ready=0, uncertain=0, not_wine=0)
    report = h.assess_health(stale_hours=168.0)
    assert report["status"] == "warning"
    assert any("summary_state_blocked_missing_source" == w for w in report["warnings"])


def test_warning_when_summary_stale(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    (dirs["reports"] / "gemini_batch_state.json").write_text('{}', encoding="utf-8")
    summary = _write_summary(dirs["staging"], items=5, state="observed", ready=5, uncertain=0, not_wine=0)
    old = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
    os.utime(summary, (old, old))
    report = h.assess_health(stale_hours=24.0)
    assert report["status"] == "warning"
    assert any("summary_stale" in w for w in report["warnings"])


def test_enriched_root_counted_as_artifact(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    (dirs["enriched"] / "enriched_ready.jsonl").write_text("", encoding="utf-8")
    report = h.assess_health()
    # Tem artifact, mas nao tem summary ainda.
    assert report["status"] == "warning"
    assert report["artifacts"]["enriched_artifact_count"] == 1


def test_render_md_covers_artifacts(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    (dirs["reports"] / "gemini_batch_state.json").write_text('{}', encoding="utf-8")
    _write_summary(dirs["staging"], items=3, state="observed", ready=3, uncertain=0, not_wine=0)
    report = h.assess_health()
    md = h._render_md(report)
    assert "Enrichment Dominio Health Check" in md
    assert "state.present: `True`" in md
