"""Testes do loader de manifesto."""
from __future__ import annotations

from pathlib import Path

import pytest

from winegod_scraper_sdk.manifest import load_manifest


CANARY_PATH = Path(__file__).resolve().parent.parent / "examples" / "canary_manifest.yaml"


def test_canary_manifest_loads():
    m = load_manifest(CANARY_PATH)
    assert m.scraper_id == "canary_synthetic"
    assert m.family == "canary"
    assert m.outputs == ["ops"]
    assert m.can_create_wine_sources is False
    assert m.requires_dq_v3 is False
    assert m.requires_matching is False
    assert m.source_hash is not None
    assert len(m.source_hash) == 64  # sha256 hex


def test_canary_manifest_to_register_payload():
    m = load_manifest(CANARY_PATH)
    p = m.to_register_payload()
    assert p["scraper_id"] == "canary_synthetic"
    assert p["family"] == "canary"
    assert p["contract_name"] == "canary_event.v1"
    assert p["contract_version"] == "v1"
    assert p["can_create_wine_sources"] is False
    assert p["requires_dq_v3"] is False
    assert p["requires_matching"] is False
    assert p["manifest_hash"] == m.source_hash


def test_manifest_rejects_can_create_wine_sources_true(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
scraper_id: x
display_name: x
family: commerce
source: s
host: este_pc
contracts:
  - { name: c, version: v1 }
outputs: [ops]
can_create_wine_sources: true
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        load_manifest(bad)


def test_manifest_rejects_outputs_without_ops(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
scraper_id: x
display_name: x
family: canary
source: synthetic
host: este_pc
contracts:
  - { name: c, version: v1 }
outputs: [final_stub]
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        load_manifest(bad)


def test_manifest_rejects_extra_field(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
scraper_id: x
display_name: x
family: canary
source: synthetic
host: este_pc
contracts:
  - { name: c, version: v1 }
outputs: [ops]
unknown_field: whatever
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        load_manifest(bad)
