"""Testa o gating do done marker em run_commerce_apply_amazon_legacy.ps1.

Regras do plano V2 Codex (secao 6.1 item 4): done marker so pode ser criado
quando COMMERCE_AMAZON_LEGACY_MARK_DONE=1 E auditoria confirma todos shards
Amazon legacy PASS no manifest.

Este teste nao executa PowerShell; apenas le o arquivo do wrapper e valida
padroes via regex.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WRAPPER = REPO_ROOT / "scripts" / "data_ops_scheduler" / "run_commerce_apply_amazon_legacy.ps1"


def _read_wrapper() -> str:
    assert WRAPPER.exists(), f"wrapper nao encontrado: {WRAPPER}"
    return WRAPPER.read_text(encoding="utf-8")


def test_wrapper_has_env_gate() -> None:
    """Wrapper deve conter o gate COMMERCE_AMAZON_LEGACY_MARK_DONE=1."""
    content = _read_wrapper()
    pattern = r'\$env:COMMERCE_AMAZON_LEGACY_MARK_DONE\s+-eq\s+"1"'
    assert re.search(pattern, content), (
        "wrapper nao contem o gate "
        '`if ($env:COMMERCE_AMAZON_LEGACY_MARK_DONE -eq "1")`'
    )


def test_wrapper_references_manifest() -> None:
    """Wrapper deve ler run_manifest.jsonl para validar shards PASS."""
    content = _read_wrapper()
    assert "run_manifest.jsonl" in content, (
        "wrapper nao referencia run_manifest.jsonl"
    )
    assert "allPass" in content, "wrapper nao contem a variavel allPass"


def test_wrapper_does_not_unconditionally_write_marker() -> None:
    """`$doneMarker = @{` nao pode aparecer fora do bloco gated por env.

    Heuristica: localizamos o unico match de `$doneMarker = @{` e conferimos
    que antes dele existe a linha do gate COMMERCE_AMAZON_LEGACY_MARK_DONE.
    """
    content = _read_wrapper()
    matches = [m.start() for m in re.finditer(r"\$doneMarker\s*=\s*@\{", content)]
    assert len(matches) == 1, (
        f"esperado 1 ocorrencia de `$doneMarker = @{{`, achei {len(matches)}"
    )
    marker_pos = matches[0]
    gate_match = re.search(
        r'\$env:COMMERCE_AMAZON_LEGACY_MARK_DONE\s+-eq\s+"1"', content
    )
    assert gate_match is not None, "gate nao encontrado"
    assert gate_match.start() < marker_pos, (
        "gate COMMERCE_AMAZON_LEGACY_MARK_DONE deve vir ANTES da escrita do marker"
    )


def test_wrapper_keeps_initial_done_flag_check() -> None:
    """Check inicial que bloqueia re-run quando marker existe deve continuar."""
    content = _read_wrapper()
    assert "amazon_legacy_backfill_done.json ja existe" in content, (
        "check inicial de re-run bloqueado foi removido por engano"
    )
