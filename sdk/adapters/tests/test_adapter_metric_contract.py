"""§4B.10 item 2 — contratos Pydantic dos 4 adapters e item 4 — manifestos."""
from __future__ import annotations

from pathlib import Path

import pytest

from winegod_scraper_sdk.manifest import load_manifest


ADAPTERS_DIR = Path(__file__).resolve().parents[1]
MANIFESTS = [
    "commerce_world_winegod_admin.yaml",
    "reviews_vivino_global.yaml",
    "critics_decanter_persisted.yaml",
    "commerce_dq_v3_observer.yaml",
]


@pytest.mark.parametrize("name", MANIFESTS)
def test_manifest_loads(name):
    m = load_manifest(ADAPTERS_DIR / "manifests" / name)
    assert m.outputs == ["ops"]
    assert m.can_create_wine_sources is False
    assert m.requires_dq_v3 is False
    assert m.requires_matching is False
    assert m.connector_type == "TelemetryDelivery"
    assert m.pii_policy == "strict"
    assert m.source_hash is not None


def test_scraper_ids_correct():
    got = {load_manifest(ADAPTERS_DIR / "manifests" / n).scraper_id for n in MANIFESTS}
    assert got == {
        "commerce_world_winegod_admin",
        "reviews_vivino_global",
        "critics_decanter_persisted",
        "commerce_dq_v3_observer",
    }


def test_families_correct():
    fams = {load_manifest(ADAPTERS_DIR / "manifests" / n).family for n in MANIFESTS}
    assert fams == {"commerce", "review", "critic"}


def test_dry_run_contracts_pass():
    """Cada adapter em --dry-run constrói payloads válidos (Pydantic aceita)."""
    import importlib
    for mod_name in (
        "adapters.winegod_admin_commerce_observer",
        "adapters.vivino_reviews_observer",
        "adapters.decanter_persisted_observer",
        "adapters.dq_v3_observer",
    ):
        m = importlib.import_module(mod_name)
        rc = m.run(dry_run=True, limit=0)
        assert rc == 0, f"{mod_name} dry-run falhou rc={rc}"
