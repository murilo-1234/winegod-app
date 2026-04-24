"""Safety net de manifests do dominio reviews.

Garante que:
  - o manifest do plug oficial existe e tem o contrato esperado;
  - todos os manifests observadores do dominio reviews referenciam o plug
    oficial via tag `plug:reviews_scores`;
  - as 4 fontes pausadas (CT / Decanter / WE / WS) continuam
    `registry_status: observed`, sem sobrescrita acidental para `apply`.

Esta suite nao importa nada do plug; so le YAML.
"""
from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFESTS_DIR = REPO_ROOT / "sdk" / "adapters" / "manifests"
PLUG_MANIFEST = REPO_ROOT / "sdk" / "plugs" / "reviews_scores" / "manifest.yaml"

REVIEW_MANIFEST_NAMES = [
    # canal Vivino (entrada canonica do dominio)
    "catalog_vivino_updates.yaml",
    "reviewers_vivino_global.yaml",
    "reviews_vivino_global.yaml",
    "reviews_vivino_partition_a.yaml",
    "reviews_vivino_partition_b.yaml",
    "reviews_vivino_partition_c.yaml",
    # fontes externas pausadas nesta fase
    "scores_cellartracker.yaml",
    "critics_decanter_persisted.yaml",
    "critics_wine_enthusiast.yaml",
    "market_winesearcher.yaml",
]

PAUSED_SOURCES = {
    "scores_cellartracker.yaml",
    "critics_decanter_persisted.yaml",
    "critics_wine_enthusiast.yaml",
    "market_winesearcher.yaml",
}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_plug_manifest_is_reviews_scores_owner():
    data = _load(PLUG_MANIFEST)
    assert data["scraper_id"] == "plug_reviews_scores"
    assert data["family"] == "review"
    # O plug aplica em wine_scores + wines. Se isso mudar, o contrato mudou.
    assert "public.wine_scores" in data["outputs"]
    assert "public.wines" in data["outputs"]


def test_all_review_manifests_reference_plug_tag():
    missing: list[str] = []
    for name in REVIEW_MANIFEST_NAMES:
        path = MANIFESTS_DIR / name
        data = _load(path)
        tags = data.get("tags") or []
        if "plug:reviews_scores" not in tags:
            missing.append(name)
    assert not missing, f"manifests sem tag plug:reviews_scores: {missing}"


def test_paused_sources_stay_observed_not_applied():
    """Fase atual: CT / Decanter / WE / WS em pausa controlada.

    Mudar `registry_status` para algo diferente de `observed` exige contrato
    e reabertura explicita; este teste trava o drift silencioso.
    """
    drift: list[str] = []
    for name in PAUSED_SOURCES:
        path = MANIFESTS_DIR / name
        data = _load(path)
        status = data.get("registry_status")
        if status != "observed":
            drift.append(f"{name}:{status}")
        # Nao podem virar fonte de wine_sources por erro.
        assert data.get("can_create_wine_sources") is False
        # Nao podem declarar requires_matching true sem matching implementado.
        assert data.get("requires_matching") is False
    assert not drift, f"fontes pausadas mudaram de status: {drift}"


def test_review_manifests_never_declare_commerce_outputs():
    """Dominio reviews nao pode escrever em wine_sources nesta fase."""
    violations: list[str] = []
    for name in REVIEW_MANIFEST_NAMES:
        path = MANIFESTS_DIR / name
        data = _load(path)
        outputs = data.get("outputs") or []
        if "public.wine_sources" in outputs:
            violations.append(name)
    assert not violations, f"manifests declararam wine_sources: {violations}"
