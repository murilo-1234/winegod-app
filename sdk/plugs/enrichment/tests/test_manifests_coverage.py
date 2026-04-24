"""Safety net de manifests do dominio enrichment."""
from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFESTS_DIR = REPO_ROOT / "sdk" / "adapters" / "manifests"
PLUG_MANIFEST = REPO_ROOT / "sdk" / "plugs" / "enrichment" / "manifest.yaml"

DOMAIN_MANIFESTS = [
    "enrichment_gemini_flash.yaml",
]

FINAL_TABLES = {"public.wines", "public.wine_sources", "public.stores", "public.store_recipes"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_plug_manifest_is_enrichment_owner():
    data = _load(PLUG_MANIFEST)
    assert data["scraper_id"] == "plug_enrichment"
    assert data["family"] == "enrichment"
    assert data["outputs"] == ["ops"], data["outputs"]
    assert data["can_create_wine_sources"] is False


def test_domain_manifests_reference_plug_tag():
    missing: list[str] = []
    for name in DOMAIN_MANIFESTS:
        path = MANIFESTS_DIR / name
        data = _load(path)
        tags = data.get("tags") or []
        if "plug:enrichment" not in tags:
            missing.append(name)
    assert not missing, f"manifests sem tag plug:enrichment: {missing}"


def test_enrichment_never_declares_final_outputs():
    violations: list[str] = []
    paths = [PLUG_MANIFEST] + [MANIFESTS_DIR / n for n in DOMAIN_MANIFESTS]
    for path in paths:
        data = _load(path)
        for out in data.get("outputs") or []:
            if out in FINAL_TABLES:
                violations.append(f"{path.name}:{out}")
    assert not violations, f"enrichment declarou outputs finais: {violations}"


def test_enrichment_flags_are_locked():
    paths = [PLUG_MANIFEST] + [MANIFESTS_DIR / n for n in DOMAIN_MANIFESTS]
    for path in paths:
        data = _load(path)
        assert data.get("can_create_wine_sources") is False, path.name
        assert data.get("requires_dq_v3") is False, path.name
        assert data.get("requires_matching") is False, path.name
