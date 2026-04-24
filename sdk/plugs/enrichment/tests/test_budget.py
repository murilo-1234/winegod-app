from __future__ import annotations

from decimal import Decimal

from sdk.plugs.enrichment import budget as b


def test_estimate_cost_zero_items():
    est = b.estimate_cost(0)
    assert est.items == 0
    assert est.total_cost_usd == Decimal("0.0000")


def test_estimate_cost_sample_numbers():
    est = b.estimate_cost(1000,
                          input_tokens_per_item=200,
                          output_tokens_per_item=100,
                          input_rate_usd_per_1m=Decimal("0.1"),
                          output_rate_usd_per_1m=Decimal("0.4"))
    # input = 1000 * 200 = 200000 tokens = 0.02 USD
    # output = 1000 * 100 = 100000 tokens = 0.04 USD
    assert est.input_cost_usd == Decimal("0.0200")
    assert est.output_cost_usd == Decimal("0.0400")
    assert est.total_cost_usd == Decimal("0.0600")


def test_env_overrides_are_respected(monkeypatch):
    monkeypatch.setenv("ENRICHMENT_INPUT_RATE_USD_PER_1M", "1.0")
    monkeypatch.setenv("ENRICHMENT_OUTPUT_RATE_USD_PER_1M", "2.0")
    monkeypatch.setenv("ENRICHMENT_INPUT_TOKENS_PER_ITEM", "100")
    monkeypatch.setenv("ENRICHMENT_OUTPUT_TOKENS_PER_ITEM", "50")
    est = b.estimate_cost(1_000_000)
    # in = 1M*100 tokens = 100M -> 100M/1M*1 = 100 USD
    # out = 1M*50 tokens = 50M -> 50M/1M*2 = 100 USD
    assert est.total_cost_usd == Decimal("200.0000")


def test_recommended_batch_cap_under_50_usd():
    cap = b.recommended_batch_cap(
        Decimal("50"),
        input_tokens_per_item=200,
        output_tokens_per_item=100,
        input_rate_usd_per_1m=Decimal("0.1"),
        output_rate_usd_per_1m=Decimal("0.4"),
    )
    # per item = 0.02/1000 + 0.04/1000 = 0.00006 USD
    # 50 / 0.00006 ~ 833333
    assert cap >= 800_000


def test_items_negative_raises():
    import pytest

    with pytest.raises(ValueError):
        b.estimate_cost(-1)


def test_report_md_contains_key_lines():
    est = b.estimate_cost(100)
    md = b.report_md(est, by_route={"ready": 50, "uncertain": 30, "not_wine": 20})
    assert "Enrichment Budget Forecast" in md
    assert "items: `100`" in md
    assert "ready" in md
    assert "uncertain" in md
