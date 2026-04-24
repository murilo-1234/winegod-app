from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sdk.plugs.commerce_dq_v3.artifact_contract import (
    ITEM_REQUIRED_FIELDS,
    SUMMARY_REQUIRED_FIELDS,
    validate_artifact_dir,
)


def _item(**overrides) -> dict:
    base = {
        "pipeline_family": "amazon_mirror_primary",
        "run_id": "run-001",
        "country": "us",
        "store_name": "Amazon US",
        "store_domain": "amazon.com",
        "url_original": "https://amazon.com/dp/B0EXAMPLE",
        "nome": "Vinho Teste",
        "produtor": "Produtor Teste",
        "safra": 2022,
        "preco": 49.99,
        "moeda": "USD",
        "captured_at": "2026-04-23T19:30:00Z",
        "source_pointer": "amazon_mirror/run-001",
    }
    base.update(overrides)
    return base


def _summary(**overrides) -> dict:
    base = {
        "run_id": "run-001",
        "pipeline_family": "amazon_mirror_primary",
        "started_at": "2026-04-23T19:00:00Z",
        "finished_at": "2026-04-23T19:30:00Z",
        "host": "pc_espelho",
        "input_scope": "US,BR",
        "items_emitted": 1,
    }
    base.update(overrides)
    return base


def _write_artifact(dirpath: Path, items: list[dict], summary: dict | None, *, name: str = "20260423_193000_run-001") -> Path:
    jsonl = dirpath / f"{name}.jsonl"
    jsonl.write_text("\n".join(json.dumps(it) for it in items), encoding="utf-8")
    if summary is not None:
        summary = dict(summary)
        summary["artifact_sha256"] = hashlib.sha256(jsonl.read_bytes()).hexdigest()
        (dirpath / f"{name}_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return jsonl


def test_required_fields_enumeration():
    assert "pipeline_family" in ITEM_REQUIRED_FIELDS
    assert "artifact_sha256" in SUMMARY_REQUIRED_FIELDS
    assert len(ITEM_REQUIRED_FIELDS) == 13
    assert len(SUMMARY_REQUIRED_FIELDS) == 8


def test_valid_artifact_passes(tmp_path: Path):
    jsonl = _write_artifact(tmp_path, [_item()], _summary())
    result = validate_artifact_dir(
        artifact_dir=tmp_path,
        expected_family="amazon_mirror_primary",
        item_limit=10,
    )
    assert result.ok is True
    assert result.artifact_path == jsonl
    assert result.items and result.items[0]["run_id"] == "run-001"


def test_missing_item_field_fails(tmp_path: Path):
    bad = _item()
    del bad["captured_at"]
    _write_artifact(tmp_path, [bad], _summary())
    result = validate_artifact_dir(
        artifact_dir=tmp_path,
        expected_family="amazon_mirror_primary",
        item_limit=10,
    )
    assert result.ok is False
    assert any("captured_at" in n for n in result.notes)


def test_missing_summary_fails(tmp_path: Path):
    _write_artifact(tmp_path, [_item()], summary=None)
    result = validate_artifact_dir(
        artifact_dir=tmp_path,
        expected_family="amazon_mirror_primary",
        item_limit=10,
    )
    assert result.ok is False
    assert any("summary_ausente" in n for n in result.notes)


def test_sha_mismatch_fails(tmp_path: Path):
    jsonl = _write_artifact(tmp_path, [_item()], _summary())
    # sobrescrever summary com hash intencional errado
    summary_path = jsonl.with_name(jsonl.stem + "_summary.json")
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    data["artifact_sha256"] = "deadbeef" * 8
    summary_path.write_text(json.dumps(data), encoding="utf-8")
    result = validate_artifact_dir(
        artifact_dir=tmp_path,
        expected_family="amazon_mirror_primary",
        item_limit=10,
    )
    assert result.ok is False
    assert any("sha256_nao_confere" in n for n in result.notes)


def test_wrong_pipeline_family_fails(tmp_path: Path):
    _write_artifact(tmp_path, [_item(pipeline_family="tier1")], _summary())
    result = validate_artifact_dir(
        artifact_dir=tmp_path,
        expected_family="amazon_mirror_primary",
        item_limit=10,
    )
    assert result.ok is False
    assert any("pipeline_family" in n for n in result.notes)


def test_no_jsonl_returns_blocked(tmp_path: Path):
    result = validate_artifact_dir(
        artifact_dir=tmp_path,
        expected_family="tier1",
        item_limit=10,
    )
    assert result.ok is False
    assert result.artifact_path is None
    assert "nenhum_artefato_jsonl_em" in (result.reason or "")


def test_summary_wrong_family_fails(tmp_path: Path):
    _write_artifact(tmp_path, [_item()], _summary(pipeline_family="tier1"))
    result = validate_artifact_dir(
        artifact_dir=tmp_path,
        expected_family="amazon_mirror_primary",
        item_limit=10,
    )
    assert result.ok is False
    assert any("summary_pipeline_family" in n for n in result.notes)
