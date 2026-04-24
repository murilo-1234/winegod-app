from __future__ import annotations

import os
from typing import Any

import pytest

from sdk.plugs.discovery_stores import promotion as prom
from sdk.plugs.discovery_stores.promotion import StorePromoter


def _valid_candidate(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "normalized_domain": "example-store.com.br",
        "store_name": "Example Store",
        "country": "br",
        "url": "https://www.example-store.com.br",
        "platform": "shopify",
        "validation_status": "verified",
        "tier_hint": "tier1_template",
        "recipe_candidate": {"plataforma": "shopify", "metodo_listagem": "api"},
        "sample_scrape": {
            "products_extractable": 15,
            "selectors_declared": 10,
            "selectors_matched": 9,
            "catalog_patterns": [
                "https://www.example-store.com.br/c/wine/a",
                "https://www.example-store.com.br/c/wine/b",
                "https://www.example-store.com.br/c/wine/c",
            ],
        },
        "source_lineage": {"source_system": "agent_discovery"},
    }
    base.update(overrides)
    return base


def test_candidate_below_min_products_is_skipped():
    c = _valid_candidate(sample_scrape={**_valid_candidate()["sample_scrape"],
                                        "products_extractable": 3})
    plan = StorePromoter().plan([c])
    assert plan.approved_stores == 0
    assert plan.skipped[0]["reason_code"] == prom.REASON_CODES["G1"]


def test_duplicate_domain_is_skipped():
    c = _valid_candidate()
    promoter = StorePromoter(existing_store_domains={"example-store.com.br"})
    plan = promoter.plan([c])
    assert plan.approved_stores == 0
    assert plan.skipped[0]["reason_code"] == prom.REASON_CODES["G4"]


def test_invalid_country_is_skipped():
    c = _valid_candidate(country="brasil")
    plan = StorePromoter().plan([c])
    assert plan.approved_stores == 0
    assert plan.skipped[0]["reason_code"] == prom.REASON_CODES["G5"]


def test_low_selector_hit_rate_is_skipped():
    c = _valid_candidate(sample_scrape={**_valid_candidate()["sample_scrape"],
                                        "selectors_matched": 3})
    plan = StorePromoter().plan([c])
    assert plan.approved_stores == 0
    assert plan.skipped[0]["reason_code"] == prom.REASON_CODES["G2"]


def test_apply_without_authorized_raises(tmp_path, monkeypatch):
    promoter = StorePromoter()
    plan = promoter.plan([_valid_candidate()])
    with pytest.raises(PermissionError, match="authorized=True"):
        promoter.apply(plan, authorized=False)


def test_apply_without_env_raises(monkeypatch):
    monkeypatch.delenv(prom.AUTH_ENV, raising=False)
    promoter = StorePromoter()
    plan = promoter.plan([_valid_candidate()])
    with pytest.raises(PermissionError, match=prom.AUTH_ENV):
        promoter.apply(plan, authorized=True)


def test_apply_with_mock_conn_writes_and_commits(monkeypatch):
    monkeypatch.setenv(prom.AUTH_ENV, "1")
    promoter = StorePromoter()
    plan = promoter.plan([_valid_candidate(), _valid_candidate(
        normalized_domain="other-store.com.br",
        url="https://other-store.com.br",
        store_name="Other Store",
    )])
    assert plan.approved_stores == 2

    calls: list[tuple] = []

    class _FakeCur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params):
            calls.append(("execute", sql.strip().split()[0], params[0]))
        def fetchone(self):
            return (42,)

    class _FakeConn:
        def __init__(self):
            self.committed = 0
            self.closed = False
        def cursor(self): return _FakeCur()
        def commit(self): self.committed += 1
        def close(self): self.closed = True

    conn_instance = _FakeConn()
    result = promoter.apply(
        plan,
        authorized=True,
        batch_size=100,
        conn_factory=lambda: conn_instance,
    )
    assert result.stores_inserted == 2
    assert result.batches_committed == 1
    assert conn_instance.closed is True


def test_plan_hash_is_idempotent():
    candidates = [_valid_candidate(), _valid_candidate(
        normalized_domain="other.com.br",
        url="https://other.com.br",
        store_name="Other",
    )]
    plan_a = StorePromoter().plan(candidates)
    plan_b = StorePromoter().plan(candidates)
    assert plan_a.plan_hash == plan_b.plan_hash
    assert plan_a.total_candidates == 2


def test_missing_source_lineage_is_skipped():
    c = _valid_candidate()
    c.pop("source_lineage")
    plan = StorePromoter().plan([c])
    assert plan.approved_stores == 0
    assert plan.skipped[0]["reason_code"] == prom.REASON_CODES["MISSING_LINEAGE"]


def test_persist_plan_writes_json(tmp_path, monkeypatch):
    monkeypatch.setattr(prom, "PLANS_DIR", tmp_path)
    promoter = StorePromoter()
    plan = promoter.plan([_valid_candidate()])
    path = promoter.persist_plan(plan, timestamp="20260424_120000")
    assert path.exists()
    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["plan_hash"] == plan.plan_hash


def test_summary_markdown_contains_plan_hash():
    plan = StorePromoter().plan([_valid_candidate()])
    md = prom.summary_markdown(plan)
    assert plan.plan_hash in md
    assert "Discovery Stores Promotion Plan" in md


def test_legacy_recipe_conflict_flag():
    promoter = StorePromoter(
        existing_store_domains=set(),
        existing_store_id_by_domain={"example-store.com.br": 999},
        legacy_recipes_by_store_id={999},
    )
    # candidate's domain not in existing_store_domains (fresh) but store_id has legacy recipe
    # To exercise: add it to existing domains too so we can see flag independently — but that
    # would fail G4. Instead, approve it and then emulate the legacy flag path.
    c = _valid_candidate(normalized_domain="example-store.com.br")
    # Force into approved list by making the normalized domain not in existing_store_domains
    promoter._existing_domains = set()
    plan = promoter.plan([c])
    approved = [x for x in plan.candidates if x.approved]
    assert approved
    # With mapping pointing to 999, and 999 in legacy set, flag should flip
    # Since plan logic only flags legacy_conflict (not skip), recipes_count should drop
    assert approved[0].legacy_conflict is True
    assert plan.approved_recipes == 0
