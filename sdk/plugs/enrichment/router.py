"""Deterministic router do loop de qualidade.

Recebe um item ja processado pelo sistema v3 (parsed + confidence) e
decide: ready / uncertain / not_wine. Zero rede. Zero Gemini.

O threshold padrao e 0.8 e pode ser sobrescrito via env
`ENRICHMENT_CONFIDENCE_THRESHOLD`.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


REPO_ROOT = Path(__file__).resolve().parents[3]

# Acesso read-only ao wine_filter.should_skip_wine (fonte unica NOT_WINE).
_SCRIPTS = REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

try:
    from pre_ingest_filter import should_skip_wine as _pre_ingest_should_skip_wine  # type: ignore
except Exception:  # pragma: no cover - fallback mais fraco
    _pre_ingest_should_skip_wine = None  # type: ignore

try:
    from wine_filter import is_not_wine as _fallback_is_not_wine  # type: ignore
except Exception:  # pragma: no cover
    _fallback_is_not_wine = None  # type: ignore


def _should_skip_wine(nome: str) -> tuple[bool, str | None]:
    if _pre_ingest_should_skip_wine is not None:
        skip, reason = _pre_ingest_should_skip_wine(nome)
        return skip, reason
    if _fallback_is_not_wine is not None:
        skip, reason = _fallback_is_not_wine(nome)
        return skip, reason
    return False, None


Route = Literal["ready", "uncertain", "not_wine"]


_CORE_FIELDS = ("producer", "wine_name", "country_code")


def _default_threshold() -> float:
    raw = os.environ.get("ENRICHMENT_CONFIDENCE_THRESHOLD")
    if raw is None:
        return 0.8
    try:
        value = float(raw)
    except ValueError:
        return 0.8
    return max(0.0, min(value, 1.0))


def _current_year() -> int:
    return datetime.now(timezone.utc).year


def _has_core_fields(parsed: dict[str, Any]) -> bool:
    return all(parsed.get(field) for field in _CORE_FIELDS)


def _vintage_conflict(parsed: dict[str, Any]) -> bool:
    vintage = parsed.get("vintage")
    if not vintage:
        return False
    try:
        year = int(vintage)
    except (TypeError, ValueError):
        return True
    return year > _current_year() or year < 1800


def route_item(parsed: dict[str, Any], *, threshold: float | None = None) -> Route:
    """Classifica um item ja processado pelo v3.

    parsed = elemento de `result["items"]` retornado por `enrich_items_v3`.
    confidence esperado em `parsed["confidence"]`; se ausente, usa a funcao
    derivada do propio enrichment_v3.
    """
    kind = (parsed.get("kind") or "unknown").lower()
    if kind in {"not_wine", "spirit"}:
        return "not_wine"

    # Cross-check com wine_filter local (source of truth).
    candidate_name = (
        parsed.get("full_name")
        or parsed.get("wine_name")
        or ""
    )
    if candidate_name:
        skip, _ = _should_skip_wine(candidate_name)
        if skip:
            return "not_wine"

    if kind != "wine":
        return "uncertain"

    if not _has_core_fields(parsed):
        return "uncertain"

    if _vintage_conflict(parsed):
        return "uncertain"

    confidence = parsed.get("confidence")
    if confidence is None:
        # Sem confidence explicito o item nao pode ser promovido a ready.
        return "uncertain"
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        return "uncertain"
    if confidence < (threshold if threshold is not None else _default_threshold()):
        return "uncertain"

    return "ready"


def classify_batch(items: list[dict[str, Any]], *, threshold: float | None = None) -> dict[str, list[dict[str, Any]]]:
    """Roteia uma lista, retornando buckets por rota."""
    buckets: dict[str, list[dict[str, Any]]] = {"ready": [], "uncertain": [], "not_wine": []}
    for item in items:
        route = route_item(item, threshold=threshold)
        buckets[route].append({**item, "route": route})
    return buckets


__all__ = ["route_item", "classify_batch", "Route"]
