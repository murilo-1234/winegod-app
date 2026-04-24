from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from sdk.plugs.enrichment import gemini_dispatcher as gd


def _setup(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    batches = tmp_path / "batches"
    pilot = tmp_path / "pilot"
    budget = tmp_path / "budget"
    for d in (batches, pilot, budget):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(gd, "BATCHES_DIR", batches)
    monkeypatch.setattr(gd, "PILOT_DIR", pilot)
    monkeypatch.setattr(gd, "BUDGET_DIR", budget)
    return {"batches": batches, "pilot": pilot, "budget": budget}


def _write_budget(dirs: dict[str, Path], *, total_cost: str) -> Path:
    path = dirs["budget"] / "20260424_120000_budget.json"
    payload = {
        "generated_at_utc": "2026-04-24T12:00:00Z",
        "estimate": {"total_cost_usd": total_cost},
        "items_within_cap": 1000,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_prepare_writes_input_file_without_calling_adapter(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    items = [{"ocr": {"name": f"Wine {i}"}} for i in range(5)]
    result = gd.prepare(items, timestamp="20260424_120000")
    assert result.mode == "prepare"
    assert result.items == 5
    assert result.path.exists()
    # metadata file tambem
    assert (dirs["batches"] / "20260424_120000_metadata.json").exists()


def test_dispatch_without_env_raises(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.delenv(gd.AUTH_ENV, raising=False)
    with pytest.raises(PermissionError, match=gd.AUTH_ENV):
        gd.dispatch([{"ocr": {"name": "Wine"}}])


def test_dispatch_without_pilot_max_items_raises(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv(gd.AUTH_ENV, "1")
    monkeypatch.delenv(gd.PILOT_MAX_ITEMS_ENV, raising=False)
    with pytest.raises(PermissionError, match=gd.PILOT_MAX_ITEMS_ENV):
        gd.dispatch([{"ocr": {"name": "Wine"}}])


def test_dispatch_without_budget_raises(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv(gd.AUTH_ENV, "1")
    monkeypatch.setenv(gd.PILOT_MAX_ITEMS_ENV, "1000")
    with pytest.raises(RuntimeError, match="recent budget"):
        gd.dispatch([{"ocr": {"name": "Wine"}}])


def test_dispatch_rejects_cost_over_cap(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv(gd.AUTH_ENV, "1")
    monkeypatch.setenv(gd.PILOT_MAX_ITEMS_ENV, "1000")
    _write_budget(dirs, total_cost="99.99")
    with pytest.raises(RuntimeError, match="exceeds cap"):
        gd.dispatch([{"ocr": {"name": "Wine"}}], cap_usd=Decimal("50"))


def test_dispatch_rejects_batch_over_pilot_cap(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv(gd.AUTH_ENV, "1")
    monkeypatch.setenv(gd.PILOT_MAX_ITEMS_ENV, "2")
    _write_budget(dirs, total_cost="0.01")
    with pytest.raises(ValueError, match="pilot cap"):
        gd.dispatch([{"ocr": {}}] * 3)


def test_pilot_cap_over_hard_cap_is_rejected(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv(gd.AUTH_ENV, "1")
    monkeypatch.setenv(gd.PILOT_MAX_ITEMS_ENV, "20001")
    with pytest.raises(ValueError, match="must be in"):
        gd.dispatch([{"ocr": {}}])


def test_dispatch_calls_mock_adapter_and_persists(tmp_path, monkeypatch):
    dirs = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv(gd.AUTH_ENV, "1")
    monkeypatch.setenv(gd.PILOT_MAX_ITEMS_ENV, "5")
    _write_budget(dirs, total_cost="0.01")

    captured: dict = {}

    def fake_enrich(items, channel):
        captured["items"] = list(items)
        captured["channel"] = channel
        return [{"index": 1, "kind": "wine"} for _ in items]

    result = gd.dispatch(
        [{"ocr": {"name": "X"}}],
        enrich_fn=fake_enrich,
        timestamp="20260424_121000",
    )
    assert result.mode == "dispatch"
    assert result.path.exists()
    assert captured["channel"] == "enrichment_pilot"
    # result file contem 1 linha
    lines = result.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["kind"] == "wine"
