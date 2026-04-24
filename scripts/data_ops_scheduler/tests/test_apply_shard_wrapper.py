"""Testes do wrapper run_commerce_apply_shard.ps1 (plano 3 fases).

Testa via leitura textual — nao executa PowerShell. Cobre:
- gate de limite MAX_SHARD_ITEMS=50000;
- gate de env var de autorizacao (so apply, nao dry-run);
- validator FULL antes de runner;
- anti-reprocessamento via artifact_sha256 + run_manifest.jsonl;
- append no manifest ao fim;
- extracao de apply_run_id do summary markdown.
"""

from __future__ import annotations

from pathlib import Path

WRAPPER = Path(__file__).resolve().parents[1] / "run_commerce_apply_shard.ps1"


def _read():
    assert WRAPPER.exists(), f"wrapper nao existe: {WRAPPER}"
    return WRAPPER.read_text(encoding="utf-8")


def test_wrapper_has_limit_gate():
    text = _read()
    assert "if ($Limit -gt 50000)" in text
    assert "MAX_SHARD_ITEMS=50000" in text


def test_wrapper_has_env_gate_only_for_apply():
    text = _read()
    assert "if (-not $DryRun)" in text
    assert "COMMERCE_APPLY_AUTHORIZED_" in text


def test_wrapper_calls_validator_before_runner():
    text = _read()
    validator_idx = text.find("validate_commerce_artifact.py")
    runner_idx = text.find("sdk.plugs.commerce_dq_v3.runner")
    assert validator_idx > 0
    assert runner_idx > 0
    assert validator_idx < runner_idx, "validator deve rodar antes do runner"


def test_wrapper_computes_artifact_sha256():
    text = _read()
    assert "hash_artifact.py" in text
    assert "$artifactSha" in text


def test_wrapper_checks_manifest_for_reprocess():
    text = _read()
    assert "run_manifest.jsonl" in text
    assert "ja foi aplicado com PASS" in text
    assert 'exit 5' in text  # codigo de erro anti-reprocessamento


def test_wrapper_appends_to_manifest():
    text = _read()
    assert "append_run_manifest.py" in text
    assert "--artifact-sha256" in text
    assert "--apply-run-id" in text
    assert "--status" in text


def test_wrapper_extracts_run_id_from_summary():
    text = _read()
    assert "_commerce_" in text
    assert "_summary.md" in text
    assert "run_id:" in text  # regex pra extrair do markdown


def test_wrapper_has_bloked_queue_explosion_check():
    text = _read()
    assert "BLOCKED_QUEUE_EXPLOSION" in text


def test_wrapper_sets_artifact_dir_env_for_tier():
    text = _read()
    assert "TIER1_ARTIFACT_DIR" in text
    assert "TIER2_ARTIFACT_DIR" in text
    assert "AMAZON_MIRROR_ARTIFACT_DIR" in text
