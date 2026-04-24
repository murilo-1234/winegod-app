"""Testes exporter tier2_br (via fixtures, sem DB)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdk.plugs.commerce_dq_v3.artifact_contract import validate_artifact_dir_full
from sdk.plugs.commerce_dq_v3.artifact_exporters.tier2_br import (
    PIPELINE_FAMILY,
    run_export_from_rows,
)
from sdk.plugs.commerce_dq_v3.tests.fixtures.commerce_rows import (
    duplicate_url_rows,
    row_with_missing_fields,
    tier2_br_rows,
)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_gera_jsonl_br(tmp_path: Path) -> None:
    rows = tier2_br_rows(5)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    assert result.ok
    items = _read_jsonl(result.jsonl_path)
    assert all(it["country"] == "br" for it in items)
    assert all(it["pipeline_family"] == "tier2" for it in items)


def test_moeda_brl(tmp_path: Path) -> None:
    rows = tier2_br_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    items = _read_jsonl(result.jsonl_path)
    assert all(it["moeda"] == "BRL" for it in items)


def test_dedup_url(tmp_path: Path) -> None:
    result = run_export_from_rows(duplicate_url_rows(), output_dir=tmp_path)
    assert result.items_emitted == 1


def test_filtra_incompletos(tmp_path: Path) -> None:
    rows = tier2_br_rows(2) + [row_with_missing_fields()]
    result = run_export_from_rows(rows, output_dir=tmp_path)
    assert result.items_emitted == 2


def test_summary_br_input_scope(tmp_path: Path) -> None:
    rows = tier2_br_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["input_scope"] == "br"


def test_validator_full_passa(tmp_path: Path) -> None:
    rows = tier2_br_rows(5)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    validation = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="tier2"
    )
    assert validation.ok, validation.notes


def test_dominio_brasil(tmp_path: Path) -> None:
    rows = tier2_br_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    items = _read_jsonl(result.jsonl_path)
    for it in items:
        assert it["store_domain"].endswith(".com.br")


def test_max_items(tmp_path: Path) -> None:
    rows = tier2_br_rows(10)
    result = run_export_from_rows(rows, output_dir=tmp_path, max_items=3)
    assert result.items_emitted == 3


def test_source_pointer_nao_vazio(tmp_path: Path) -> None:
    rows = tier2_br_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    items = _read_jsonl(result.jsonl_path)
    for it in items:
        assert it["source_pointer"]
        assert "#" in it["source_pointer"]
