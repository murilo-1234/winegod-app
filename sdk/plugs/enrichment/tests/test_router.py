from __future__ import annotations

from datetime import datetime, timezone

from sdk.plugs.enrichment import router as r


def _base_wine(**overrides):
    item = {
        "kind": "wine",
        "producer": "Producer",
        "wine_name": "Wine X",
        "full_name": "Producer Wine X",
        "country_code": "BR",
        "confidence": 0.9,
        "vintage": 2018,
    }
    item.update(overrides)
    return item


def test_ready_when_full_and_high_confidence():
    assert r.route_item(_base_wine()) == "ready"


def test_uncertain_when_confidence_below_threshold():
    assert r.route_item(_base_wine(confidence=0.7)) == "uncertain"


def test_uncertain_when_missing_core_field():
    assert r.route_item(_base_wine(country_code=None)) == "uncertain"


def test_uncertain_when_vintage_in_future():
    future = datetime.now(timezone.utc).year + 5
    assert r.route_item(_base_wine(vintage=future)) == "uncertain"


def test_not_wine_when_kind_declared():
    assert r.route_item(_base_wine(kind="not_wine")) == "not_wine"
    assert r.route_item(_base_wine(kind="spirit")) == "not_wine"


def test_not_wine_via_wine_filter_match():
    # "whisky" deve bater no wine_filter.
    it = _base_wine(wine_name="Jack Daniels Whiskey", full_name="Jack Daniels Whiskey")
    assert r.route_item(it) == "not_wine"


def test_threshold_override_via_env(monkeypatch):
    monkeypatch.setenv("ENRICHMENT_CONFIDENCE_THRESHOLD", "0.95")
    assert r.route_item(_base_wine(confidence=0.9)) == "uncertain"
    monkeypatch.setenv("ENRICHMENT_CONFIDENCE_THRESHOLD", "0.5")
    assert r.route_item(_base_wine(confidence=0.6)) == "ready"


def test_threshold_invalid_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("ENRICHMENT_CONFIDENCE_THRESHOLD", "abc")
    # default 0.8, 0.7 should be uncertain
    assert r.route_item(_base_wine(confidence=0.7)) == "uncertain"


def test_classify_batch_buckets_routes():
    items = [
        _base_wine(),  # ready
        _base_wine(confidence=0.5),  # uncertain
        _base_wine(kind="not_wine"),
    ]
    buckets = r.classify_batch(items)
    assert len(buckets["ready"]) == 1
    assert len(buckets["uncertain"]) == 1
    assert len(buckets["not_wine"]) == 1
    assert buckets["ready"][0]["route"] == "ready"


def test_confidence_non_numeric_is_uncertain():
    assert r.route_item(_base_wine(confidence="baixo")) == "uncertain"


def test_uncertain_when_confidence_missing():
    item = _base_wine()
    item.pop("confidence")
    assert r.route_item(item) == "uncertain"
