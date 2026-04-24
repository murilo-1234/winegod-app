"""Testes exporter amazon_mirror (via fixtures, sem DB)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sdk.plugs.commerce_dq_v3.artifact_contract import validate_artifact_dir_full
from sdk.plugs.commerce_dq_v3.artifact_exporters.amazon_mirror import (
    PIPELINE_FAMILY,
    run_export_from_rows,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters.base import load_state
from sdk.plugs.commerce_dq_v3.tests.fixtures.commerce_rows import (
    amazon_mirror_rows,
    duplicate_url_rows,
    row_with_missing_fields,
)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_gera_jsonl_valido(tmp_path: Path) -> None:
    rows = amazon_mirror_rows(5)
    result = run_export_from_rows(rows, output_dir=tmp_path, update_state=False)
    assert result.ok, f"esperado OK, veio: {result.reason} notes={result.notes}"
    assert result.items_emitted == 5
    items = _read_jsonl(result.jsonl_path)
    assert len(items) == 5
    # 13 campos obrigatorios presentes em todos
    for it in items:
        for k in (
            "pipeline_family", "run_id", "country", "store_name", "store_domain",
            "url_original", "nome", "produtor", "safra", "preco", "moeda",
            "captured_at", "source_pointer",
        ):
            assert k in it, f"falta {k}"
        assert it["pipeline_family"] == PIPELINE_FAMILY


def test_pipeline_family_correto(tmp_path: Path) -> None:
    rows = amazon_mirror_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path, update_state=False)
    items = _read_jsonl(result.jsonl_path)
    assert all(it["pipeline_family"] == "amazon_mirror_primary" for it in items)


def test_captured_at_formato_iso(tmp_path: Path) -> None:
    rows = amazon_mirror_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path, update_state=False)
    items = _read_jsonl(result.jsonl_path)
    for it in items:
        dt = datetime.fromisoformat(it["captured_at"].replace("Z", "+00:00"))
        assert dt.tzinfo is not None


def test_dedup_por_url(tmp_path: Path) -> None:
    rows = duplicate_url_rows()
    result = run_export_from_rows(rows, output_dir=tmp_path, update_state=False)
    assert result.ok
    assert result.items_emitted == 1
    assert result.duplicates_skipped == 1


def test_filtra_items_incompletos(tmp_path: Path) -> None:
    rows = amazon_mirror_rows(2) + [row_with_missing_fields()]
    result = run_export_from_rows(rows, output_dir=tmp_path, update_state=False)
    assert result.ok
    assert result.items_emitted == 2  # row_with_missing_fields rejeitada


def test_summary_com_8_campos(tmp_path: Path) -> None:
    rows = amazon_mirror_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path, update_state=False)
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    for k in (
        "run_id", "pipeline_family", "started_at", "finished_at",
        "host", "input_scope", "items_emitted", "artifact_sha256",
    ):
        assert k in summary, f"summary sem {k}"
    assert summary["pipeline_family"] == PIPELINE_FAMILY
    assert summary["items_emitted"] == 3


def test_artifact_sha_bate(tmp_path: Path) -> None:
    rows = amazon_mirror_rows(3)
    result = run_export_from_rows(rows, output_dir=tmp_path, update_state=False)
    validation = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="amazon_mirror_primary"
    )
    assert validation.ok, validation.notes


def test_state_incremental_atualizado(tmp_path: Path) -> None:
    """Rodar com `update_state=True` atualiza state key customizado."""

    rows = amazon_mirror_rows(4)
    key = "amazon_mirror_test_" + datetime.now(timezone.utc).strftime("%H%M%S%f")
    result = run_export_from_rows(
        rows,
        output_dir=tmp_path,
        update_state=True,
        state_source_key=key,
    )
    assert result.ok
    state = load_state(key)
    assert state.get("last_artifact_sha256") == result.artifact_sha256
    assert state.get("last_items_emitted") == result.items_emitted
    assert "last_captured_at" in state


def test_validator_full_ok(tmp_path: Path) -> None:
    rows = amazon_mirror_rows(4)
    result = run_export_from_rows(rows, output_dir=tmp_path, update_state=False)
    assert result.ok
    validation = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="amazon_mirror_primary"
    )
    assert validation.ok, validation.notes
    assert len(validation.items) == 4


def test_batch_10k_respeita_contract(tmp_path: Path) -> None:
    """Escreve 100 items e confere que sao todos validos e emittidos."""

    rows = amazon_mirror_rows(100)
    result = run_export_from_rows(rows, output_dir=tmp_path, update_state=False)
    assert result.ok
    assert result.items_emitted == 100
