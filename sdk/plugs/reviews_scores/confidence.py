"""Wrapper do helper canonico de confianca WCF.

A formula unica esta em `scripts/wcf_confidence.py`. Este modulo so injeta
`scripts/` no sys.path e re-exporta `confianca` como `confidence`. Nao ha
fallback: se o import falhar, a chamada falha explicitamente - evitando
divergencia silenciosa de formula.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_scripts_on_path() -> None:
    scripts_root = Path(__file__).resolve().parents[3] / "scripts"
    entry = str(scripts_root)
    if entry not in sys.path:
        sys.path.insert(0, entry)


_ensure_scripts_on_path()
from wcf_confidence import confianca as _canonical_confianca  # noqa: E402


def confidence(sample_size: int | None) -> float:
    return _canonical_confianca(sample_size)


__all__ = ["confidence"]
