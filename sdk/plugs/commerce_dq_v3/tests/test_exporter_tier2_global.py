"""Testes exporter tier2_global (via fixtures, sem DB)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdk.plugs.commerce_dq_v3.artifact_contract import validate_artifact_dir_full
from sdk.plugs.commerce_dq_v3.artifact_exporters.tier2_global import (
    PIPELINE_FAMILY,
    run_export_from_rows,
)
from sdk.plugs.commerce_dq_v3.tests.fixtures.commerce_rows import (
    duplicate_url_rows,
    row_with_missing_fields,
    tier2_global_rows,
)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_gera_jsonl_tier2_global(tmp_path: Path) -> None:
    rows = tier2_global_rows(5)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    assert result.ok
    items = _read_jsonl(result.jsonl_path)
    assert all(it["pipeline_family"] == "tier2" for it in items)


def test_pais_nao_br(tmp_path: Path) -> None:
    """Fixtures Tier2 global usam FR - confirmar que country preserva."""

    rows = tier2_global_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    items = _read_jsonl(result.jsonl_path)
    for it in items:
        assert it["country"] == "fr"
        assert it["country"] != "br"


def test_dedup_url(tmp_path: Path) -> None:
    result = run_export_from_rows(duplicate_url_rows(), output_dir=tmp_path)
    assert result.items_emitted == 1


def test_filtra_incompletos(tmp_path: Path) -> None:
    rows = tier2_global_rows(2) + [row_with_missing_fields()]
    result = run_export_from_rows(rows, output_dir=tmp_path)
    assert result.items_emitted == 2


def test_summary_pipeline_family(tmp_path: Path) -> None:
    rows = tier2_global_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["pipeline_family"] == "tier2"


def test_validator_full_passa(tmp_path: Path) -> None:
    rows = tier2_global_rows(5)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    validation = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="tier2"
    )
    assert validation.ok, validation.notes


def test_produtor_e_nome_nao_vazios(tmp_path: Path) -> None:
    rows = tier2_global_rows(5)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    items = _read_jsonl(result.jsonl_path)
    for it in items:
        assert it["nome"]
        assert it["produtor"]


def test_max_items(tmp_path: Path) -> None:
    rows = tier2_global_rows(10)
    result = run_export_from_rows(rows, output_dir=tmp_path, max_items=4)
    assert result.items_emitted == 4


def test_moeda_eur_em_fixture(tmp_path: Path) -> None:
    rows = tier2_global_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    items = _read_jsonl(result.jsonl_path)
    assert all(it["moeda"] == "EUR" for it in items)
