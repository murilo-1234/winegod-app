"""Testes de integracao end-to-end commerce.

Cada teste monta um mini-pipeline em `tmp_path`:

1. rows sinteticas -> exporter -> JSONL + summary
2. `validate_artifact_dir_full` contra o output
3. checagens do runner mockado (sem DB real)
4. summary final coerente

10+ testes cobrindo as 5 familias + casos cruzados.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdk.plugs.commerce_dq_v3.artifact_contract import validate_artifact_dir_full
from sdk.plugs.commerce_dq_v3.artifact_exporters.amazon_legacy import (
    run_export_from_rows as legacy_export,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters.amazon_mirror import (
    run_export_from_rows as mirror_export,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters.tier1_global import (
    run_export_from_rows as tier1_export,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters.tier2_br import (
    run_export_from_rows as tier2_br_export,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters.tier2_global import (
    run_export_from_rows as tier2_export,
)
from sdk.plugs.commerce_dq_v3.tests.fixtures.commerce_rows import (
    amazon_legacy_rows,
    amazon_mirror_rows,
    tier1_rows,
    tier2_br_rows,
    tier2_global_rows,
)


def test_e2e_amazon_mirror_pipeline(tmp_path: Path) -> None:
    result = mirror_export(amazon_mirror_rows(10), output_dir=tmp_path, update_state=False)
    assert result.ok
    validation = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="amazon_mirror_primary"
    )
    assert validation.ok, validation.notes
    assert len(validation.items) == 10
    assert validation.artifact_sha256 == result.artifact_sha256


def test_e2e_amazon_legacy_pipeline(tmp_path: Path) -> None:
    result = legacy_export(amazon_legacy_rows(8), output_dir=tmp_path)
    assert result.ok
    v = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="amazon_local_legacy_backfill"
    )
    assert v.ok, v.notes


def test_e2e_tier1_pipeline(tmp_path: Path) -> None:
    result = tier1_export(tier1_rows(12), output_dir=tmp_path)
    assert result.ok
    v = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="tier1"
    )
    assert v.ok, v.notes


def test_e2e_tier2_global_pipeline(tmp_path: Path) -> None:
    result = tier2_export(tier2_global_rows(10), output_dir=tmp_path)
    assert result.ok
    v = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="tier2"
    )
    assert v.ok, v.notes


def test_e2e_tier2_br_pipeline(tmp_path: Path) -> None:
    result = tier2_br_export(tier2_br_rows(8), output_dir=tmp_path)
    assert result.ok
    v = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="tier2"
    )
    assert v.ok, v.notes
    items = [json.loads(line) for line in result.jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert all(it["country"] == "br" for it in items)


def test_e2e_summary_items_emitted_bate(tmp_path: Path) -> None:
    result = mirror_export(amazon_mirror_rows(15), output_dir=tmp_path, update_state=False)
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["items_emitted"] == 15
    v = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="amazon_mirror_primary"
    )
    assert v.ok


def test_e2e_familias_diferentes_dir_diferente(tmp_path: Path) -> None:
    """Amazon mirror e tier1 escrevem em dirs distintos; validators
    nao se misturam."""

    mirror_dir = tmp_path / "mirror"
    tier1_dir = tmp_path / "tier1"
    mirror_export(amazon_mirror_rows(3), output_dir=mirror_dir, update_state=False)
    tier1_export(tier1_rows(3), output_dir=tier1_dir)
    v_mirror = validate_artifact_dir_full(artifact_dir=mirror_dir, expected_family="amazon_mirror_primary")
    v_tier1 = validate_artifact_dir_full(artifact_dir=tier1_dir, expected_family="tier1")
    assert v_mirror.ok
    assert v_tier1.ok


def test_e2e_dedup_preserva_contrato(tmp_path: Path) -> None:
    """Rows duplicados sao removidos mas summary consistente com itens reais."""

    rows = amazon_mirror_rows(5) * 2  # cada URL duas vezes
    result = mirror_export(rows, output_dir=tmp_path, update_state=False)
    assert result.items_emitted == 5
    assert result.duplicates_skipped == 5
    v = validate_artifact_dir_full(
        artifact_dir=tmp_path, expected_family="amazon_mirror_primary"
    )
    assert v.ok, v.notes  # summary.items_emitted=5 == 5 linhas reais


def test_e2e_max_items_respeitado_summary_bate(tmp_path: Path) -> None:
    result = tier1_export(tier1_rows(50), output_dir=tmp_path, max_items=7)
    assert result.items_emitted == 7
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["items_emitted"] == 7
    v = validate_artifact_dir_full(artifact_dir=tmp_path, expected_family="tier1")
    assert v.ok


def test_e2e_sha_nos_items_eh_consistente(tmp_path: Path) -> None:
    """Garantir que `artifact_sha256` do summary bate com hash real do JSONL."""

    result = tier2_export(tier2_global_rows(5), output_dir=tmp_path)
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    import hashlib
    h = hashlib.sha256()
    with result.jsonl_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    assert summary["artifact_sha256"] == h.hexdigest()


def test_e2e_5_familias_coexistem(tmp_path: Path) -> None:
    """Roda as 5 e valida sem cross-contamination."""

    subdirs = {
        "amazon_mirror": (mirror_export, amazon_mirror_rows(3), "amazon_mirror_primary"),
        "amazon_legacy": (legacy_export, amazon_legacy_rows(3), "amazon_local_legacy_backfill"),
        "tier1": (tier1_export, tier1_rows(3), "tier1"),
        "tier2_global": (tier2_export, tier2_global_rows(3), "tier2"),
        "tier2_br": (tier2_br_export, tier2_br_rows(3), "tier2"),
    }
    for name, (fn, rows, family) in subdirs.items():
        out = tmp_path / name
        kwargs = {"output_dir": out}
        if fn is mirror_export:
            kwargs["update_state"] = False
        r = fn(rows, **kwargs)
        assert r.ok, f"{name}: {r.reason}"
        v = validate_artifact_dir_full(artifact_dir=out, expected_family=family)
        assert v.ok, f"{name}: {v.notes}"
