"""Validador do contrato de artefato commerce (docs/TIER_COMMERCE_CONTRACT.md).

Escopo: `amazon_mirror_primary`, `tier1_global`, `tier2_*`.

Regras aplicadas:

- JSONL mais recente do diretorio deve existir;
- cada item deve carregar os 13 campos minimos;
- deve existir `<prefix>_summary.json` correspondente (mesmo prefix do JSONL);
- summary deve carregar 8 campos minimos;
- summary.artifact_sha256 deve bater com o SHA do JSONL real;
- se o item traz `pipeline_family`, precisa bater com o esperado da fonte.

Ao achar qualquer falha, devolve `ContractValidation(ok=False, reason=..., ...)`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ITEM_REQUIRED_FIELDS: tuple[str, ...] = (
    "pipeline_family",
    "run_id",
    "country",
    "store_name",
    "store_domain",
    "url_original",
    "nome",
    "produtor",
    "safra",
    "preco",
    "moeda",
    "captured_at",
    "source_pointer",
)

# Campos que precisam estar presentes mas PODEM ter valor null
# (docs/TIER_COMMERCE_CONTRACT.md: "safra (pode ser null)",
#  "preco (pode ser null)").
ITEM_NULLABLE_FIELDS: frozenset[str] = frozenset({"safra", "preco"})

SUMMARY_REQUIRED_FIELDS: tuple[str, ...] = (
    "run_id",
    "pipeline_family",
    "started_at",
    "finished_at",
    "host",
    "input_scope",
    "items_emitted",
    "artifact_sha256",
)


@dataclass
class ContractValidation:
    ok: bool
    reason: str | None = None
    items: list[dict] = field(default_factory=list)
    artifact_path: Path | None = None
    summary_path: Path | None = None
    artifact_sha256: str | None = None
    notes: list[str] = field(default_factory=list)


def pick_latest_jsonl(base: Path) -> Path | None:
    if not base.exists():
        return None
    candidates = sorted(
        (p for p in base.iterdir() if p.is_file() and p.suffix == ".jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _summary_path_for(jsonl_path: Path) -> Path:
    # Prefix match: `<prefix>.jsonl` -> `<prefix>_summary.json`
    return jsonl_path.with_name(jsonl_path.stem + "_summary.json")


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_jsonl(path: Path, limit: int) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    notes: list[str] = []
    with path.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                notes.append(f"linha_{i}_invalida={type(exc).__name__}")
            if len(items) >= limit:
                break
    return items, notes


def validate_items(items: Iterable[dict], *, expected_family: str | None) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for idx, item in enumerate(items):
        missing: list[str] = []
        for field_name in ITEM_REQUIRED_FIELDS:
            # Todos os campos devem ESTAR PRESENTES (chave existir).
            if field_name not in item:
                missing.append(field_name)
                continue
            value = item[field_name]
            # Campos nullable podem ter valor None/null.
            if field_name in ITEM_NULLABLE_FIELDS:
                continue
            # Campos nao-nullable nao podem ser None nem string vazia.
            if value is None or value == "":
                missing.append(field_name)
        if missing:
            errors.append(f"item_{idx}_faltando={','.join(missing)}")
            continue
        if expected_family and item.get("pipeline_family") != expected_family:
            errors.append(
                f"item_{idx}_pipeline_family={item.get('pipeline_family')}_esperado={expected_family}"
            )
    return (not errors), errors[:20]


def validate_summary(summary_path: Path, *, expected_family: str | None, jsonl_path: Path) -> tuple[bool, list[str], dict]:
    if not summary_path.exists():
        return False, [f"summary_ausente={summary_path.name}"], {}
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, [f"summary_invalido={type(exc).__name__}"], {}
    errors: list[str] = []
    missing = [f for f in SUMMARY_REQUIRED_FIELDS if data.get(f) in (None, "")]
    if missing:
        errors.append(f"summary_faltando={','.join(missing)}")
    if expected_family and data.get("pipeline_family") != expected_family:
        errors.append(f"summary_pipeline_family={data.get('pipeline_family')}_esperado={expected_family}")
    declared_sha = data.get("artifact_sha256")
    real_sha = _hash_file(jsonl_path)
    if declared_sha and declared_sha != real_sha:
        errors.append("summary_sha256_nao_confere")
    return (not errors), errors, data


def validate_artifact_dir(
    *,
    artifact_dir: Path,
    expected_family: str | None,
    item_limit: int,
) -> ContractValidation:
    latest = pick_latest_jsonl(artifact_dir)
    if latest is None:
        return ContractValidation(
            ok=False,
            reason=f"nenhum_artefato_jsonl_em={artifact_dir}",
        )
    real_sha = _hash_file(latest)
    items, jsonl_notes = _load_jsonl(latest, item_limit)
    if not items:
        return ContractValidation(
            ok=False,
            reason="jsonl_sem_itens_validos",
            artifact_path=latest,
            artifact_sha256=real_sha,
            notes=jsonl_notes,
        )
    items_ok, items_errors = validate_items(items, expected_family=expected_family)
    summary_path = _summary_path_for(latest)
    summary_ok, summary_errors, _summary = validate_summary(
        summary_path, expected_family=expected_family, jsonl_path=latest
    )
    if items_ok and summary_ok:
        return ContractValidation(
            ok=True,
            items=items,
            artifact_path=latest,
            summary_path=summary_path,
            artifact_sha256=real_sha,
            notes=jsonl_notes,
        )
    notes = jsonl_notes + items_errors + summary_errors
    return ContractValidation(
        ok=False,
        reason="contrato_invalido",
        items=items,
        artifact_path=latest,
        summary_path=summary_path if summary_path.exists() else None,
        artifact_sha256=real_sha,
        notes=notes,
    )
