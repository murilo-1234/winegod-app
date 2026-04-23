from __future__ import annotations

from pathlib import Path

from sdk.plugs.enrichment.exporters import _ready_record, _uncertain_record


def test_ready_record_keeps_route_and_model(tmp_path: Path):
    path = tmp_path / "enriched_ready.jsonl"
    row = {
        "nome": "Wine",
        "produtor": "Producer",
        "_post_enrich_status": "ready",
        "_enriched_source_model": "gemini-2.5-flash-lite",
        "_enriched_confidence": 0.9,
    }
    record = _ready_record(path, row)
    assert record["route"] == "ready"
    assert record["enrichment"]["model"] == "gemini-2.5-flash-lite"


def test_uncertain_record_hashes_raw_payload(tmp_path: Path):
    path = tmp_path / "enriched_uncertain_review.csv"
    row = {
        "nome_original": "Wine",
        "produtor_original": "Producer",
        "confidence": "0.7",
        "raw_json": '{"nome":"Wine"}',
    }
    record = _uncertain_record(path, row)
    assert record["route"] == "uncertain"
    assert record["enrichment"]["raw_json_hash"]
