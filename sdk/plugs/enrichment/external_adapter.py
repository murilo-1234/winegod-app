"""Adapter fino para o sistema de enriquecimento existente (v3).

READ-ONLY proxy do sistema em `backend/services/enrichment_v3.py`.
NAO altera NADA do sistema existente. Nao reenvolve o prompt. Nao muda
modelo. So chama a interface publica documentada:

  `enrich_items_v3(items, source_channel=None, trace=None) -> dict`

Uso:

    from sdk.plugs.enrichment.external_adapter import enrich_wine, enrich_batch

    result = enrich_wine({"ocr": {"name": "Wine X"}})
    results = enrich_batch([{"ocr": {"name": "Wine X"}}, ...])

Cap hard-coded: 20_000 items por chamada. Acima, raise.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"

MAX_BATCH = 20_000

_cached_enrich: Callable[..., Any] | None = None


def _ensure_backend_on_path() -> None:
    entry = str(BACKEND_ROOT)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def _load_existing_enrich() -> Callable[..., Any]:
    """Lazy import do sistema existente. Nao importa em module level porque
    o backend exige envs e depend extras que podem faltar em CI.
    """
    global _cached_enrich
    if _cached_enrich is not None:
        return _cached_enrich
    _ensure_backend_on_path()
    from services.enrichment_v3 import enrich_items_v3  # type: ignore

    _cached_enrich = enrich_items_v3
    return _cached_enrich


def enrich_wine(item: dict[str, Any], *, source_channel: str | None = "enrichment_loop") -> dict[str, Any]:
    """Proxy 1:1 do v3 para um unico item."""
    enrich_fn = _load_existing_enrich()
    result = enrich_fn([item], source_channel=source_channel)
    items = result.get("items") or []
    parsed = items[0] if items else {"kind": "unknown"}
    return {
        "parsed": parsed,
        "raw_primary": result.get("raw_primary", ""),
        "raw_escalated": result.get("raw_escalated", ""),
        "stats": result.get("stats", {}),
    }


def enrich_batch(items: list[dict[str, Any]], *, source_channel: str | None = "enrichment_loop") -> list[dict[str, Any]]:
    """Proxy do v3 para uma lista. Cap hard 20k items (REGRA do prompt)."""
    if len(items) > MAX_BATCH:
        raise ValueError(
            f"enrich_batch recusa lote com {len(items)} items (cap={MAX_BATCH})"
        )
    if not items:
        return []
    enrich_fn = _load_existing_enrich()
    result = enrich_fn(items, source_channel=source_channel)
    parsed_list = result.get("items") or []
    # garantia: um elemento por input (v3 ja devolve lista paralela)
    return list(parsed_list)


def describe_interface() -> dict[str, Any]:
    """Documenta a interface do sistema existente para uso em relatorios/docs."""
    return {
        "path": str(BACKEND_ROOT / "services" / "enrichment_v3.py"),
        "public_function": "enrich_items_v3",
        "signature": "enrich_items_v3(items, source_channel=None, trace=None) -> dict",
        "input_format": "items = [{'ocr': {...}}, ...]",
        "output_keys": ["items", "raw_primary", "raw_escalated", "stats"],
        "models": {
            "primary": "Config.ENRICHMENT_GEMINI_25_MODEL (gemini-2.5-flash-lite)",
            "escalated": "Config.ENRICHMENT_GEMINI_31_MODEL (gemini-3.1-flash-lite-preview)",
        },
        "cap_batch": MAX_BATCH,
        "read_only": True,
    }


__all__ = [
    "enrich_wine",
    "enrich_batch",
    "describe_interface",
    "MAX_BATCH",
]
