"""Safety net de manifests do dominio discovery.

Trava drift silencioso:
  - plug_discovery_stores existe e declara outputs=[ops] (sem tabelas finais);
  - discovery_agent_global manifest linka via tag `plug:discovery_stores`;
  - can_create_wine_sources=False em ambos;
  - nenhum manifest do dominio declara public.wines/wine_sources/stores/store_recipes em outputs.
"""
from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFESTS_DIR = REPO_ROOT / "sdk" / "adapters" / "manifests"
PLUG_MANIFEST = REPO_ROOT / "sdk" / "plugs" / "discovery_stores" / "manifest.yaml"

DOMAIN_MANIFESTS = [
    "discovery_agent_global.yaml",
]

FINAL_TABLES = {"public.wines", "public.wine_sources", "public.stores", "public.store_recipes"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_plug_manifest_is_discovery_stores_owner():
    data = _load(PLUG_MANIFEST)
    assert data["scraper_id"] == "plug_discovery_stores"
    assert data["family"] == "discovery"
    assert data["outputs"] == ["ops"], data["outputs"]
    assert data["can_create_wine_sources"] is False


def test_domain_manifests_reference_plug_tag():
    missing: list[str] = []
    for name in DOMAIN_MANIFESTS:
        path = MANIFESTS_DIR / name
        data = _load(path)
        tags = data.get("tags") or []
        if "plug:discovery_stores" not in tags:
            missing.append(name)
    assert not missing, f"manifests sem tag plug:discovery_stores: {missing}"


def test_discovery_never_declares_final_outputs():
    violations: list[str] = []
    paths = [PLUG_MANIFEST] + [MANIFESTS_DIR / n for n in DOMAIN_MANIFESTS]
    for path in paths:
        data = _load(path)
        for out in data.get("outputs") or []:
            if out in FINAL_TABLES:
                violations.append(f"{path.name}:{out}")
    assert not violations, f"discovery declarou outputs finais: {violations}"


def test_discovery_manifests_lock_flags():
    paths = [PLUG_MANIFEST] + [MANIFESTS_DIR / n for n in DOMAIN_MANIFESTS]
    for path in paths:
        data = _load(path)
        assert data.get("can_create_wine_sources") is False, path.name
        assert data.get("requires_dq_v3") is False, path.name
        assert data.get("requires_matching") is False, path.name
