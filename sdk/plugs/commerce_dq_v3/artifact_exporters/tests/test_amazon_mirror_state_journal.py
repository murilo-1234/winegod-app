"""Testes do journal pending/commit/abort do exporter amazon_mirror.

Garantem que `last_captured_at` NAO avanca antes de um commit explicito
(apply PASS). Parte da Fase 1 do plano subida-3fases-20260424.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sdk.plugs.commerce_dq_v3.artifact_exporters import amazon_mirror as mod
from sdk.plugs.commerce_dq_v3.artifact_exporters.amazon_mirror import (
    AmazonMirrorConfig,
    abort_pending_state,
    commit_pending_state,
    has_pending_state,
    run_export,
    run_export_from_rows,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters import base as base_mod
from sdk.plugs.commerce_dq_v3.tests.fixtures.commerce_rows import amazon_mirror_rows


@pytest.fixture
def isolated_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redireciona STATE_DIR para tmp_path e garante isolamento por teste."""

    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(base_mod, "STATE_DIR", state_dir)
    monkeypatch.setattr(mod, "STATE_DIR", state_dir)
    return state_dir


def _unique_key() -> str:
    return "amazon_mirror_journal_" + datetime.now(timezone.utc).strftime("%H%M%S%f")


def test_export_escreve_pending_nao_oficial(
    tmp_path: Path, isolated_state_dir: Path
) -> None:
    key = _unique_key()
    rows = amazon_mirror_rows(4)
    result = run_export_from_rows(
        rows,
        output_dir=tmp_path,
        update_state=True,
        state_source_key=key,
    )
    assert result.ok, f"esperado OK: {result.reason} {result.notes}"
    pending_path = isolated_state_dir / f"{key}.pending.json"
    official_path = isolated_state_dir / f"{key}.json"
    assert pending_path.exists(), "pending nao foi escrito"
    assert not official_path.exists(), "oficial nao pode existir antes do commit"
    assert has_pending_state(key)
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    for k in (
        "last_captured_at",
        "last_run_id",
        "last_items_emitted",
        "last_artifact_sha256",
        "mode",
        "pending_since",
    ):
        assert k in pending, f"pending sem {k}"
    assert pending["last_artifact_sha256"] == result.artifact_sha256
    assert pending["last_items_emitted"] == result.items_emitted


def test_commit_pending_state_promove_pra_oficial(
    tmp_path: Path, isolated_state_dir: Path
) -> None:
    key = _unique_key()
    rows = amazon_mirror_rows(3)
    result = run_export_from_rows(
        rows,
        output_dir=tmp_path,
        update_state=True,
        state_source_key=key,
    )
    assert result.ok
    pending_path = isolated_state_dir / f"{key}.pending.json"
    official_path = isolated_state_dir / f"{key}.json"
    assert pending_path.exists()

    data = commit_pending_state(key)
    assert not pending_path.exists(), "pending deveria ter sido removido"
    assert official_path.exists(), "oficial deveria existir apos commit"
    assert "committed_at" in data
    official = json.loads(official_path.read_text(encoding="utf-8"))
    assert official.get("last_artifact_sha256") == result.artifact_sha256
    assert "committed_at" in official
    assert not has_pending_state(key)


def test_abort_pending_state_move_pra_aborted(
    tmp_path: Path, isolated_state_dir: Path
) -> None:
    key = _unique_key()
    rows = amazon_mirror_rows(3)
    result = run_export_from_rows(
        rows,
        output_dir=tmp_path,
        update_state=True,
        state_source_key=key,
    )
    assert result.ok
    pending_path = isolated_state_dir / f"{key}.pending.json"
    official_path = isolated_state_dir / f"{key}.json"
    assert pending_path.exists()

    aborted_path = abort_pending_state(key, reason="apply_fail_fixture")
    assert aborted_path.exists()
    assert aborted_path.parent.name == "aborted"
    assert aborted_path.name.startswith(f"{key}.aborted_")
    assert not pending_path.exists(), "pending deveria ter sido removido"
    assert not official_path.exists(), "oficial NAO pode existir em abort"

    aborted = json.loads(aborted_path.read_text(encoding="utf-8"))
    assert aborted.get("abort_reason") == "apply_fail_fixture"
    assert "aborted_at" in aborted
    assert aborted.get("last_artifact_sha256") == result.artifact_sha256


def test_run_export_bloqueia_se_pending_orfao(
    tmp_path: Path, isolated_state_dir: Path
) -> None:
    key = _unique_key()
    # Simula pending orfao deixado por um run anterior que quebrou.
    pending_path = isolated_state_dir / f"{key}.pending.json"
    pending_path.write_text(
        json.dumps(
            {
                "last_captured_at": "2026-04-20T00:00:00+00:00",
                "last_run_id": "orfao_xpto",
                "last_items_emitted": 1,
                "last_artifact_sha256": "deadbeef",
                "mode": "incremental",
                "pending_since": "2026-04-20T00:00:00+00:00",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    cfg = AmazonMirrorConfig(
        output_dir=tmp_path,
        mode="full",
        state_source_key=key,
        dsn="postgresql://forcar-nao-conectar/invalid",
    )
    result = run_export(cfg)
    assert result.ok is False
    assert result.reason == "blocked_state_pending_orfao"
    # Pending intacto: guard nao toca no arquivo existente.
    assert pending_path.exists()
