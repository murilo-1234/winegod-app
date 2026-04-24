"""Testes exporter tier1_global (via fixtures, sem DB)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdk.plugs.commerce_dq_v3.artifact_contract import validate_artifact_dir_full
from sdk.plugs.commerce_dq_v3.artifact_exporters.tier1_global import (
    PIPELINE_FAMILY,
    run_export_from_rows,
)
from sdk.plugs.commerce_dq_v3.tests.fixtures.commerce_rows import (
    amazon_mirror_rows,
    duplicate_url_rows,
    row_with_missing_fields,
    tier1_rows,
)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_gera_jsonl_tier1(tmp_path: Path) -> None:
    rows = tier1_rows(5)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    assert result.ok
    items = _read_jsonl(result.jsonl_path)
    assert len(items) == 5
    assert all(it["pipeline_family"] == "tier1" for it in items)


def test_store_domain_diferente_por_row(tmp_path: Path) -> None:
    rows = tier1_rows(5)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    items = _read_jsonl(result.jsonl_path)
    domains = {it["store_domain"] for it in items}
    assert len(domains) == 5  # cada fixture tier1 tem dominio unico


def test_dedup_url(tmp_path: Path) -> None:
    result = run_export_from_rows(duplicate_url_rows(), output_dir=tmp_path)
    # duplicate_url_rows gera mirror rows; o exporter tier1 escreve com
    # PIPELINE_FAMILY=tier1 mesmo; dedup por URL se aplica igual
    assert result.items_emitted == 1


def test_filtra_incompletos(tmp_path: Path) -> None:
    rows = tier1_rows(2) + [row_with_missing_fields()]
    result = run_export_from_rows(rows, output_dir=tmp_path)
    assert result.items_emitted == 2


def test_moeda_variavel(tmp_path: Path) -> None:
    rows = tier1_rows(5)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    items = _read_jsonl(result.jsonl_path)
    for it in items:
        assert it["moeda"]


def test_summary_pipeline_family_tier1(tmp_path: Path) -> None:
    rows = tier1_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["pipeline_family"] == "tier1"


def test_validator_full_passa(tmp_path: Path) -> None:
    rows = tier1_rows(4)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    validation = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="tier1"
    )
    assert validation.ok, validation.notes


def test_mistura_com_mirror_nao_vira_tier1(tmp_path: Path) -> None:
    """Se chamamos run_export_from_rows com rows heterogeneos, todos entram
    como tier1 (porque o exporter for qual eles sao atribuidos). Validar
    que PIPELINE_FAMILY do export batem com modulo, nao com fonte original.
    """

    rows = tier1_rows(2) + amazon_mirror_rows(2)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    items = _read_jsonl(result.jsonl_path)
    for it in items:
        assert it["pipeline_family"] == PIPELINE_FAMILY  # tier1


def test_max_items(tmp_path: Path) -> None:
    rows = tier1_rows(10)
    result = run_export_from_rows(rows, output_dir=tmp_path, max_items=2)
    assert result.items_emitted == 2
