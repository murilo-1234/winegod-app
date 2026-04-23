from __future__ import annotations

from sdk.plugs.discovery_stores.exporters import infer_recipe_candidate, infer_validation_status


def test_infer_recipe_candidate_vtex_prefers_api():
    recipe = infer_recipe_candidate("vtex", "https://www.worldwine.com.br")
    assert recipe is not None
    assert recipe["metodo_listagem"] == "api"
    assert recipe["plataforma"] == "vtex"


def test_infer_validation_status_no_ecommerce_wins():
    status = infer_validation_status(
        {
            "url": "https://example.com",
            "tem_ecommerce": False,
            "verificado": True,
            "plataforma": "shopify",
        }
    )
    assert status == "no_ecommerce"
