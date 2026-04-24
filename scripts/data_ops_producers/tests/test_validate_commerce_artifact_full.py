"""Testes do validator CLI em modo FULL.

Garante que:
1. linhas invalidas depois da janela antiga (item_limit=200) sao detectadas
   em modo full e reprovam o contrato;
2. mismatch de `summary.items_emitted` vs linhas reais reprova o contrato;
3. artefato 100% valido passa sem falsos positivos.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_UNSET = object()

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sdk.plugs.commerce_dq_v3.artifact_contract import (  # noqa: E402
    validate_artifact_dir,
    validate_artifact_dir_full,
)


def _item(i: int, family: str = "tier1") -> dict:
    return {
        "pipeline_family": family,
        "run_id": "run-test",
        "country": "us",
        "store_name": "Test Store",
        "store_domain": "teststore.com",
        "url_original": f"https://teststore.com/p/{i}",
        "nome": f"Wine {i}",
        "produtor": "Test Producer",
        "safra": 2020,
        "preco": 10.5,
        "moeda": "USD",
        "captured_at": "2026-04-24T12:00:00Z",
        "source_pointer": f"table#id_{i}",
    }


def _write_artifact(
    tmp_path: Path,
    *,
    items: list[dict],
    extra_lines: list[str] | None = None,
    family: str = "tier1",
    declared_items_emitted: Any = _UNSET,
    break_sha: bool = False,
) -> Path:
    """Escreve JSONL + summary no tmp_path. Retorna o diretorio.

    `declared_items_emitted` aceita qualquer valor JSON-serializavel para
    testar contrato (int correto, int mentiroso, string, float, bool). Se
    omitido (`_UNSET`), usa o total real de linhas validas.
    """

    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    jsonl_path = artifact_dir / "20260424_120000_test.jsonl"
    body_lines = [json.dumps(it) for it in items]
    if extra_lines:
        body_lines.extend(extra_lines)
    jsonl_path.write_text("\n".join(body_lines), encoding="utf-8")
    real_sha = hashlib.sha256(jsonl_path.read_bytes()).hexdigest()
    declared_sha = "0" * 64 if break_sha else real_sha
    total_non_empty = sum(1 for line in body_lines if line.strip())
    summary = {
        "run_id": "run-test",
        "pipeline_family": family,
        "started_at": "2026-04-24T12:00:00Z",
        "finished_at": "2026-04-24T12:05:00Z",
        "host": "este_pc",
        "input_scope": "test",
        "items_emitted": (
            total_non_empty
            if declared_items_emitted is _UNSET
            else declared_items_emitted
        ),
        "artifact_sha256": declared_sha,
    }
    (artifact_dir / "20260424_120000_test_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    return artifact_dir


def test_full_valido_passa(tmp_path: Path) -> None:
    artifact_dir = _write_artifact(tmp_path, items=[_item(i) for i in range(5)])
    result = validate_artifact_dir_full(
        artifact_dir=artifact_dir, expected_family="tier1"
    )
    assert result.ok, f"esperado OK, veio: {result.reason} notes={result.notes}"
    assert len(result.items) == 5
    assert any(n.startswith("lines_validated=5") for n in result.notes)


def test_full_detecta_linha_invalida_pos_janela(tmp_path: Path) -> None:
    """Cria 210 itens validos + 1 linha invalida na posicao 211.

    A janela antiga de 200 nao ve a linha 211. O modo full deve ver.
    """

    items = [_item(i) for i in range(210)]
    extra_garbage = ["{ this is not valid json }"]
    artifact_dir = _write_artifact(tmp_path, items=items, extra_lines=extra_garbage)

    # Modo janela (simula comportamento antigo do CLI com --item-limit 200)
    window_result = validate_artifact_dir(
        artifact_dir=artifact_dir, expected_family="tier1", item_limit=200
    )
    assert window_result.ok, (
        "janela de 200 nao deveria ver linha invalida na 211; se mudar, "
        "adaptar este teste"
    )

    # Modo FULL: precisa reprovar
    full_result = validate_artifact_dir_full(
        artifact_dir=artifact_dir, expected_family="tier1"
    )
    assert not full_result.ok, "modo full deveria reprovar linha invalida pos-janela"
    assert any("_invalida=" in n for n in full_result.notes), full_result.notes


def test_full_detecta_items_emitted_mismatch(tmp_path: Path) -> None:
    items = [_item(i) for i in range(10)]
    artifact_dir = _write_artifact(
        tmp_path,
        items=items,
        declared_items_emitted=999,  # mente sobre itens
    )
    result = validate_artifact_dir_full(
        artifact_dir=artifact_dir, expected_family="tier1"
    )
    assert not result.ok
    assert any("summary_items_emitted_mismatch" in n for n in result.notes), result.notes


def test_full_detecta_sha_mismatch(tmp_path: Path) -> None:
    items = [_item(i) for i in range(5)]
    artifact_dir = _write_artifact(tmp_path, items=items, break_sha=True)
    result = validate_artifact_dir_full(
        artifact_dir=artifact_dir, expected_family="tier1"
    )
    assert not result.ok
    assert any("summary_sha256_nao_confere" in n for n in result.notes), result.notes


def test_full_expected_family_mismatch(tmp_path: Path) -> None:
    items = [_item(i, family="tier2") for i in range(3)]
    artifact_dir = _write_artifact(tmp_path, items=items, family="tier2")
    result = validate_artifact_dir_full(
        artifact_dir=artifact_dir, expected_family="tier1"
    )
    assert not result.ok
    assert any("pipeline_family" in n for n in result.notes), result.notes


def test_full_artefato_ausente(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = validate_artifact_dir_full(
        artifact_dir=empty_dir, expected_family="tier1"
    )
    assert not result.ok
    assert result.artifact_path is None
    assert (result.reason or "").startswith("nenhum_artefato_jsonl_em=")


# --- Fix 2: summary.items_emitted tem de ser int (contador numerico). --- #


def test_full_rejeita_items_emitted_string(tmp_path: Path) -> None:
    """items_emitted como string ("10") deve reprovar com nota explicita.

    Motivacao: o contrato operacional espera contador numerico; string
    passaria pela checagem `isinstance(x, int)` antiga so porque nao era
    `None`, ignorando o mismatch real.
    """

    items = [_item(i) for i in range(10)]
    artifact_dir = _write_artifact(
        tmp_path,
        items=items,
        declared_items_emitted="10",  # tipo errado
    )
    result = validate_artifact_dir_full(
        artifact_dir=artifact_dir, expected_family="tier1"
    )
    assert not result.ok
    assert any("summary_items_emitted_not_int" in n for n in result.notes), result.notes


def test_full_rejeita_items_emitted_float(tmp_path: Path) -> None:
    items = [_item(i) for i in range(5)]
    artifact_dir = _write_artifact(
        tmp_path,
        items=items,
        declared_items_emitted=5.0,
    )
    result = validate_artifact_dir_full(
        artifact_dir=artifact_dir, expected_family="tier1"
    )
    assert not result.ok
    assert any("summary_items_emitted_not_int" in n for n in result.notes), result.notes


def test_full_rejeita_items_emitted_bool(tmp_path: Path) -> None:
    items = [_item(i) for i in range(1)]
    artifact_dir = _write_artifact(
        tmp_path,
        items=items,
        declared_items_emitted=True,  # bool e subclasse de int; nao vale como contador
    )
    result = validate_artifact_dir_full(
        artifact_dir=artifact_dir, expected_family="tier1"
    )
    assert not result.ok
    assert any("summary_items_emitted_not_int" in n for n in result.notes), result.notes


def test_window_ignora_type_check_de_items_emitted(tmp_path: Path) -> None:
    """Modo janela nao faz a checagem de items_emitted (so modo full faz).

    Garantia de nao-regressao: runner em dry-run continua usando janela
    curta e nao deve quebrar por causa do fix 2.
    """

    items = [_item(i) for i in range(3)]
    artifact_dir = _write_artifact(
        tmp_path,
        items=items,
        declared_items_emitted="3",  # string; modo janela nao se importa com isso
    )
    result = validate_artifact_dir(
        artifact_dir=artifact_dir, expected_family="tier1", item_limit=50
    )
    # items_emitted nao vazio como string passa em validate_summary, e o
    # modo janela nao faz checagem de tipo. Resultado esperado: contrato OK.
    assert result.ok, f"esperado OK no modo janela, veio: {result.reason} notes={result.notes}"
