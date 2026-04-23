from __future__ import annotations

from sdk.plugs.reviews_scores.exporters import EXPORTERS


def test_reviews_exporters_catalog():
    assert "vivino_reviews_to_scores_reviews" in EXPORTERS
    assert "winesearcher_to_market_signals" in EXPORTERS
