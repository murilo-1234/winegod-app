from __future__ import annotations

import json
from pathlib import Path

from sdk.plugs.enrichment import uncertain_queue as uq
from sdk.plugs.enrichment import human_queue as hq


def test_uncertain_queue_builds_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(uq, "QUEUE_DIR", tmp_path)
    items = [
        {
            "full_name": "Wine A",
            "producer": "Prod A",
            "confidence": 0.6,
            "kind": "unknown",
        },
        {
            "wine_name": "Wine B",
            "confidence": None,
            "kind": "unknown",
        },
    ]
    path = uq.persist_queue(items, timestamp="20260424_120000")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["ocr"]["name"] == "Wine A"
    assert first["retry_round"] == 2
    assert first["hints"]["previous_confidence"] == 0.6


def test_human_queue_markdown_has_rows_and_headers(tmp_path, monkeypatch):
    monkeypatch.setattr(hq, "HUMAN_DIR", tmp_path)
    items = [
        {
            "full_name": "Wine X",
            "producer": None,
            "wine_name": "Wine X",
            "country_code": None,
            "confidence": 0.4,
            "vintage": 2050,
            "kind": "wine",
            "wine_identity": {"vivino_id": 123},
        },
    ]
    path = hq.persist_queue(items, timestamp="20260424_120000")
    text = path.read_text(encoding="utf-8")
    assert "Enrichment Human Queue" in text
    assert "producer_missing" in text
    assert "country_missing" in text
    assert "vivino://123" in text
    assert "vintage_out_of_range=2050" in text


def test_human_queue_handles_unnamed_items(tmp_path, monkeypatch):
    monkeypatch.setattr(hq, "HUMAN_DIR", tmp_path)
    path = hq.persist_queue([{"kind": "unknown"}], timestamp="20260424_120000")
    text = path.read_text(encoding="utf-8")
    assert "(sem nome)" in text
