from __future__ import annotations

import json
from pathlib import Path

from sdk.plugs.discovery_stores import recipe_generator as rg


_JSONLD_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "Product",
  "name": "Chateau X 2018",
  "brand": "Chateau X"
}
</script>
</head><body>R$ 189,90</body></html>
"""

_OG_HTML = """
<html><head>
<meta property="og:type" content="product" />
<meta property="og:brand" content="Producer Y" />
</head><body>$19.99</body></html>
"""

_EMPTY_HTML = "<html><body>Sem estrutura</body></html>"


def test_jsonld_product_gives_high_confidence():
    cand = rg.generate_recipe(
        domain="chateau-x.com.br",
        platform="vtex",
        sample_html=_JSONLD_HTML,
        sample_url="https://chateau-x.com.br/vinho/chateau-x",
        sample_product_name="Chateau X 2018",
    )
    assert cand.confidence >= 0.5
    assert cand.signals["jsonld_product"] is True
    assert cand.proposed_recipe["metodo_listagem"] == "jsonld"
    assert cand.needs_manual_review is False


def test_opengraph_product_medium_confidence():
    cand = rg.generate_recipe(
        domain="producer-y.com",
        platform="shopify",
        sample_html=_OG_HTML,
        sample_url=None,
        sample_product_name=None,
    )
    assert 0.15 <= cand.confidence < 0.6
    assert cand.signals["og_product"] is True


def test_empty_html_flags_manual_review():
    cand = rg.generate_recipe(
        domain="empty.com.br",
        platform=None,
        sample_html=_EMPTY_HTML,
        sample_url=None,
    )
    assert cand.confidence < 0.4
    assert cand.needs_manual_review is True


def test_pagination_detected_by_page_param():
    assert rg.detect_pagination("https://x.com/shop?page=2") == r"[?&]page=\d+"
    assert rg.detect_pagination("https://x.com/shop/page/3") == r"/page/\d+"
    assert rg.detect_pagination("https://x.com/shop") is None


def test_price_extracted_from_multiple_formats():
    assert rg.extract_price_signal("R$ 1.234,56", "x.com.br")["currency"] == "BRL"
    assert rg.extract_price_signal("$99.99", "x.com")["currency"] == "USD"
    assert rg.extract_price_signal("150.00 EUR", "x.com")["currency"] == "EUR"


def test_currency_inferred_from_tld_when_no_symbol():
    signal = rg.extract_price_signal("Preco indisponivel", "x.com.br")
    assert signal["currency"] == "BRL"
    assert signal["pattern"] == "tld_fallback"


def test_vintage_extracted_from_product_name():
    assert rg.extract_vintage_from_name("Chateau X 2018") == 2018
    assert rg.extract_vintage_from_name("No vintage") is None
    assert rg.extract_vintage_from_name("1849 is too old") is None


def test_producer_extracted_from_og_brand():
    assert rg.extract_producer_from_html(_OG_HTML) == "Producer Y"
    assert rg.extract_producer_from_html("<html></html>") is None


def test_persist_candidate_writes_json(tmp_path, monkeypatch):
    monkeypatch.setattr(rg, "CANDIDATES_DIR", tmp_path)
    cand = rg.generate_recipe(
        domain="x.com.br",
        platform="vtex",
        sample_html=_JSONLD_HTML,
        sample_url=None,
    )
    path = rg.persist_candidate(cand, timestamp="20260424_120000")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["domain"] == "x.com.br"
    assert "proposed_recipe" in data
