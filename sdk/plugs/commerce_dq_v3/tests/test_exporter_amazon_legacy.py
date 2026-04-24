"""Testes exporter amazon_legacy (via fixtures, sem DB)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdk.plugs.commerce_dq_v3.artifact_contract import validate_artifact_dir_full
from sdk.plugs.commerce_dq_v3.artifact_exporters.amazon_legacy import (
    PIPELINE_FAMILY,
    run_export_from_rows,
)
from sdk.plugs.commerce_dq_v3.tests.fixtures.commerce_rows import (
    amazon_legacy_rows,
    duplicate_url_rows,
    row_with_missing_fields,
)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_gera_jsonl_valido(tmp_path: Path) -> None:
    rows = amazon_legacy_rows(5)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    assert result.ok
    items = _read_jsonl(result.jsonl_path)
    assert len(items) == 5
    assert all(it["pipeline_family"] == "amazon_local_legacy_backfill" for it in items)


def test_pipeline_family_legacy(tmp_path: Path) -> None:
    rows = amazon_legacy_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    items = _read_jsonl(result.jsonl_path)
    assert all(it["pipeline_family"] == PIPELINE_FAMILY for it in items)


def test_fontes_cobrem_amazon_antigo(tmp_path: Path) -> None:
    """Todas as 3 fontes do legacy (amazon, amazon_scraper, amazon_scrapingdog)."""

    rows = amazon_legacy_rows(9)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    items = _read_jsonl(result.jsonl_path)
    fontes = {it.get("_source_fonte") for it in items}
    assert {"amazon", "amazon_scraper", "amazon_scrapingdog"}.issubset(fontes)


def test_dedup_url(tmp_path: Path) -> None:
    result = run_export_from_rows(duplicate_url_rows(), output_dir=tmp_path)
    assert result.ok
    assert result.items_emitted == 1
    assert result.duplicates_skipped == 1


def test_filtra_incompletos(tmp_path: Path) -> None:
    rows = amazon_legacy_rows(2) + [row_with_missing_fields()]
    result = run_export_from_rows(rows, output_dir=tmp_path)
    assert result.items_emitted == 2


def test_summary_artifact_sha256_bate(tmp_path: Path) -> None:
    rows = amazon_legacy_rows(4)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["artifact_sha256"] == result.artifact_sha256


def test_max_items_respeitado(tmp_path: Path) -> None:
    rows = amazon_legacy_rows(10)
    result = run_export_from_rows(rows, output_dir=tmp_path, max_items=3)
    assert result.items_emitted == 3


def test_validator_full_passa(tmp_path: Path) -> None:
    rows = amazon_legacy_rows(5)
    result = run_export_from_rows(rows, output_dir=tmp_path)
    assert result.ok
    validation = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="amazon_local_legacy_backfill"
    )
    assert validation.ok, validation.notes


def test_zero_items_elegiveis(tmp_path: Path) -> None:
    """So item incompleto = zero_items_elegiveis."""

    result = run_export_from_rows([row_with_missing_fields()], output_dir=tmp_path)
    assert not result.ok
    assert result.reason == "zero_items_elegiveis"
