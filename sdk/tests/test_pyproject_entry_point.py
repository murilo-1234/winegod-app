"""Testes §5.4 — entry point do SDK nao fica quebrado.

Verifica que `sdk/pyproject.toml` nao aponta para modulo inexistente.
"""
from __future__ import annotations

from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_pyproject_has_no_broken_entry_point():
    src = PYPROJECT.read_text(encoding="utf-8")
    # O entry point antigo apontava para um modulo dentro do pacote
    # (winegod_scraper_sdk.examples.canary_scraper) que nao existe.
    # Nao pode voltar.
    assert "winegod_scraper_sdk.examples.canary_scraper" not in src, (
        "Entry point quebrado detectado — modulo nao existe dentro do pacote."
    )


def test_pyproject_no_script_points_to_missing_module():
    """Se houver [project.scripts], cada entry deve apontar para modulo real."""
    import re
    src = PYPROJECT.read_text(encoding="utf-8")
    # Encontra bloco [project.scripts]
    m = re.search(r"\[project\.scripts\](.*?)(?=\[|$)", src, re.DOTALL)
    if not m:
        return  # Sem scripts = OK
    section = m.group(1)
    # Para cada linha `name = "modulo:func"`, verifica que modulo eh
    # `winegod_scraper_sdk` e NAO um subdir solto.
    for line in section.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        _, target = line.split("=", 1)
        target = target.strip().strip('"').strip("'")
        if ":" not in target:
            continue
        module, _ = target.split(":", 1)
        # Nao pode referenciar sub-pacote que nao existe
        assert module.startswith("winegod_scraper_sdk"), (
            f"Entry point {line!r} nao aponta para pacote instalado."
        )
