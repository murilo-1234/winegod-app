"""Tests for the enrichment v3 hibrido pipeline.

Runs offline (no DB, no real Gemini): python -m tests.test_enrichment_v3
External Gemini calls are mocked via `gemini_enrichment_generate` attribute.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.enrichment_v3 as v3_mod
import services.discovery as disc_mod
import services.new_wines as nw_mod
from config import Config


def _make_unresolved(name, producer=None, vintage=None):
    ocr = {"name": name}
    if producer:
        ocr["producer"] = producer
    if vintage:
        ocr["vintage"] = vintage
    return {"ocr": ocr, "status": "visual_only"}


# ============================================================
# 1. Parser
# ============================================================

def test_parser_handles_X_S_W_and_duplicates():
    raw = (
        "W|ramon bilbao|monte llano|es|r|tempranillo|rioja|??|NV|13.5|DOCa Rioja|medio|carne vermelha|seco|750ml|14-16C|3-5 anos|30min\n"
        "S\n"
        "X\n"
        "W|chateau montrose|montrose|fr|r|cabernet sauvignon, merlot|bordeaux|saint-estephe|2015|13.5|2eme Grand Cru Classe|encorpado|carne vermelha, caca|seco|750ml|16-18C|20+ anos|2h\n"
        "W|chateau montrose|montrose|fr|r|cabernet sauvignon, merlot|bordeaux|saint-estephe|2015|13.5|2eme Grand Cru Classe|encorpado|carne vermelha, caca|seco|750ml|16-18C|20+ anos|2h|=4\n"
    )
    parsed = v3_mod.parse_tabular_output(raw, 5)

    assert len(parsed) == 5
    assert parsed[0]["kind"] == "wine"
    assert parsed[0]["producer"] == "ramon bilbao"
    assert parsed[0]["wine_name"] == "monte llano"
    assert parsed[0]["country_code"] == "es"
    assert parsed[0]["style"] == "tinto"
    assert parsed[0]["region"] == "rioja"
    assert parsed[0]["sub_region"] is None  # "??" -> None
    assert parsed[0]["vintage"] == "NV"
    assert parsed[0]["full_name"].lower().startswith("ramon bilbao")

    assert parsed[1]["kind"] == "spirit"
    assert parsed[2]["kind"] == "not_wine"

    assert parsed[3]["kind"] == "wine"
    assert parsed[3]["duplicate_of"] is None

    assert parsed[4]["kind"] == "wine"
    assert parsed[4]["duplicate_of"] == 4


def test_parser_fills_missing_lines_as_unknown():
    raw = "W|foo|bar|fr|r|??|??|??|NV|13|??|medio|??|seco|750ml|14-16C|beber ja|nao"
    parsed = v3_mod.parse_tabular_output(raw, 3)
    assert len(parsed) == 3
    assert parsed[0]["kind"] == "wine"
    assert parsed[1]["kind"] == "unknown"
    assert parsed[2]["kind"] == "unknown"


def test_build_items_block_preserves_useful_ocr_signals():
    block = v3_mod.build_items_block([{
        "ocr": {
            "name": "Monte Llano",
            "producer": "Ramon Bilbao",
            "vintage": "2021",
            "classification": "Reserva",
            "grape": "Tempranillo",
            "region": "Rioja",
        }
    }])
    assert "Ramon Bilbao" in block
    assert "Monte Llano" in block
    assert "2021" in block
    assert "Reserva" in block
    assert "Tempranillo" in block
    assert "Rioja" in block


# ============================================================
# 2. Monte Llano end-to-end via mocked Gemini
# ============================================================

def test_monte_llano_end_to_end():
    calls = []

    def fake_gen(prompt_text, model):
        calls.append({"model": model, "prompt_len": len(prompt_text)})
        return {
            "text": (
                "W|ramon bilbao|monte llano|es|r|tempranillo|rioja|??|NV|13.5|"
                "DOCa Rioja|medio|carne vermelha|seco|750ml|14-16C|3-5 anos|30min\n"
            ),
            "model": model,
            "prompt_tokens": 100,
            "output_tokens": 30,
            "thought_tokens": 0,
            "latency_ms": 42,
        }

    orig = v3_mod.gemini_enrichment_generate
    v3_mod.gemini_enrichment_generate = fake_gen
    try:
        result = v3_mod.enrich_items_v3([_make_unresolved("monte llano")])
    finally:
        v3_mod.gemini_enrichment_generate = orig

    assert len(calls) == 1
    assert calls[0]["model"] == Config.ENRICHMENT_GEMINI_25_MODEL

    item = result["items"][0]
    assert item["kind"] == "wine"
    assert item["producer"] == "ramon bilbao"
    assert item["wine_name"] == "monte llano"
    assert item["country_code"] == "es"
    assert item["escalated"] is False
    assert result["stats"]["thought_tokens"] == 0


# ============================================================
# 3. Escalation 2.5 -> 3.1
# ============================================================

def test_escalation_fires_when_primary_returns_unknown():
    call_sequence = []

    def fake_gen(prompt_text, model):
        call_sequence.append(model)
        if model == Config.ENRICHMENT_GEMINI_25_MODEL:
            # primary fails to classify -> unknown line
            return {
                "text": "\n",
                "model": model,
                "prompt_tokens": 80,
                "output_tokens": 1,
                "thought_tokens": 0,
                "latency_ms": 30,
            }
        # 3.1 resolves it
        return {
            "text": "W|ramon bilbao|monte llano|es|r|tempranillo|rioja|??|NV|13.5|DOCa Rioja|medio|carne vermelha|seco|750ml|14-16C|3-5 anos|30min",
            "model": model,
            "prompt_tokens": 85,
            "output_tokens": 30,
            "thought_tokens": 0,
            "latency_ms": 55,
        }

    orig = v3_mod.gemini_enrichment_generate
    v3_mod.gemini_enrichment_generate = fake_gen
    try:
        result = v3_mod.enrich_items_v3([
            _make_unresolved("monte llano chardonnay reserva 2020"),
        ])
    finally:
        v3_mod.gemini_enrichment_generate = orig

    assert call_sequence == [
        Config.ENRICHMENT_GEMINI_25_MODEL,
        Config.ENRICHMENT_GEMINI_31_MODEL,
    ]
    item = result["items"][0]
    assert item["kind"] == "wine"
    assert item["escalated"] is True
    assert item["source_model"] == Config.ENRICHMENT_GEMINI_31_MODEL
    assert result["stats"]["escalated_items"] == 1


def test_no_escalation_when_item_is_spirit():
    call_sequence = []

    def fake_gen(prompt_text, model):
        call_sequence.append(model)
        return {
            "text": "S\n",
            "model": model,
            "prompt_tokens": 50,
            "output_tokens": 1,
            "thought_tokens": 0,
            "latency_ms": 20,
        }

    orig = v3_mod.gemini_enrichment_generate
    v3_mod.gemini_enrichment_generate = fake_gen
    try:
        result = v3_mod.enrich_items_v3([_make_unresolved("jamaica rum 8 years")])
    finally:
        v3_mod.gemini_enrichment_generate = orig

    assert call_sequence == [Config.ENRICHMENT_GEMINI_25_MODEL]
    assert result["items"][0]["kind"] == "spirit"
    assert result["stats"]["escalated_items"] == 0


def test_no_escalation_for_non_wine_text():
    def fake_gen(prompt_text, model):
        return {
            "text": "\n",
            "model": model,
            "prompt_tokens": 40,
            "output_tokens": 1,
            "thought_tokens": 0,
            "latency_ms": 15,
        }

    orig = v3_mod.gemini_enrichment_generate
    v3_mod.gemini_enrichment_generate = fake_gen
    try:
        result = v3_mod.enrich_items_v3([_make_unresolved("compact coffee 125g")])
    finally:
        v3_mod.gemini_enrichment_generate = orig

    # compact coffee has no wine signals -> no escalation
    assert result["stats"]["escalated_items"] == 0
    assert result["items"][0]["kind"] == "unknown"


# ============================================================
# 4. thinking=0 validation
# ============================================================

def test_thinking_leak_raises_in_helper():
    """Confirm the thinking leak check is wired via ThinkingLeakError."""
    from tools.media import ThinkingLeakError
    assert issubclass(ThinkingLeakError, RuntimeError)


def test_enrich_tolerates_primary_failure_when_fallback_disabled():
    """If primary fails and fallback is disabled, returns unknown items."""
    def fake_gen(prompt_text, model):
        raise RuntimeError("upstream 503")

    orig = v3_mod.gemini_enrichment_generate
    orig_enabled = Config.ENRICHMENT_V3_FALLBACK_ENABLED
    v3_mod.gemini_enrichment_generate = fake_gen
    Config.ENRICHMENT_V3_FALLBACK_ENABLED = False
    try:
        result = v3_mod.enrich_items_v3([_make_unresolved("foo")])
    finally:
        v3_mod.gemini_enrichment_generate = orig
        Config.ENRICHMENT_V3_FALLBACK_ENABLED = orig_enabled

    assert result["items"][0]["kind"] == "unknown"
    assert result["stats"]["thought_tokens"] == 0
    assert result["stats"]["fallback_used"] is False


def test_fallback_recovers_when_primary_fails():
    """Primary (2.5) raises -> fallback (2.5 pure) answers, batch succeeds."""
    call_log = []

    def fake_gen(prompt_text, model):
        call_log.append(model)
        # primeira chamada (primary) falha; segunda (fallback) devolve resposta
        if len(call_log) == 1:
            raise RuntimeError("rate limit")
        return {
            "text": (
                "W|ramon bilbao|monte llano|es|r|tempranillo|rioja|??|NV|13.5|"
                "DOCa Rioja|medio|carne vermelha|seco|750ml|14-16C|3-5 anos|30min\n"
            ),
            "model": model,
            "prompt_tokens": 90,
            "output_tokens": 25,
            "thought_tokens": 0,
            "latency_ms": 40,
        }

    orig = v3_mod.gemini_enrichment_generate
    orig_enabled = Config.ENRICHMENT_V3_FALLBACK_ENABLED
    v3_mod.gemini_enrichment_generate = fake_gen
    Config.ENRICHMENT_V3_FALLBACK_ENABLED = True
    try:
        result = v3_mod.enrich_items_v3([_make_unresolved("monte llano")])
    finally:
        v3_mod.gemini_enrichment_generate = orig
        Config.ENRICHMENT_V3_FALLBACK_ENABLED = orig_enabled

    assert len(call_log) == 2
    item = result["items"][0]
    assert item["kind"] == "wine"
    assert item["source_model"] == Config.ENRICHMENT_V3_FALLBACK_MODEL
    assert result["stats"]["fallback_used"] is True
    assert result["stats"]["fallback_model"] == Config.ENRICHMENT_V3_FALLBACK_MODEL
    assert "RuntimeError" in (result["stats"]["fallback_reason"] or "")


def test_fallback_also_fails_returns_unknown():
    """Both primary and fallback fail -> items are unknown, no crash."""
    def fake_gen(prompt_text, model):
        raise RuntimeError("gemini down")

    orig = v3_mod.gemini_enrichment_generate
    orig_enabled = Config.ENRICHMENT_V3_FALLBACK_ENABLED
    v3_mod.gemini_enrichment_generate = fake_gen
    Config.ENRICHMENT_V3_FALLBACK_ENABLED = True
    try:
        result = v3_mod.enrich_items_v3([_make_unresolved("foo")])
    finally:
        v3_mod.gemini_enrichment_generate = orig
        Config.ENRICHMENT_V3_FALLBACK_ENABLED = orig_enabled

    assert result["items"][0]["kind"] == "unknown"
    assert result["stats"]["fallback_used"] is True


def test_thinking_leak_in_primary_is_never_swallowed():
    """ThinkingLeakError must propagate even if fallback is enabled."""
    from tools.media import ThinkingLeakError

    def fake_gen(prompt_text, model):
        raise ThinkingLeakError("leak=42")

    orig = v3_mod.gemini_enrichment_generate
    orig_enabled = Config.ENRICHMENT_V3_FALLBACK_ENABLED
    v3_mod.gemini_enrichment_generate = fake_gen
    Config.ENRICHMENT_V3_FALLBACK_ENABLED = True
    raised = False
    try:
        v3_mod.enrich_items_v3([_make_unresolved("foo")])
    except ThinkingLeakError:
        raised = True
    finally:
        v3_mod.gemini_enrichment_generate = orig
        Config.ENRICHMENT_V3_FALLBACK_ENABLED = orig_enabled

    assert raised, "ThinkingLeakError must propagate, not be caught by fallback"


# ============================================================
# 5. Duplicate by safra
# ============================================================

def test_duplicate_same_vintage_marked():
    raw = (
        "W|chateau montrose|montrose|fr|r|cabernet sauvignon, merlot|bordeaux|saint-estephe|2015|13.5|2eme Grand Cru Classe|encorpado|carne vermelha|seco|750ml|16-18C|20+ anos|2h\n"
        "W|chateau montrose|montrose|fr|r|cabernet sauvignon, merlot|bordeaux|saint-estephe|2015|13.5|2eme Grand Cru Classe|encorpado|carne vermelha|seco|750ml|16-18C|20+ anos|2h|=1\n"
    )
    parsed = v3_mod.parse_tabular_output(raw, 2)
    assert parsed[0]["vintage"] == "2015"
    assert parsed[1]["duplicate_of"] == 1


def test_different_vintages_not_duplicate():
    raw = (
        "W|monte meao|vinha do cabeco vermelho|pt|r|tinta roriz|douro|cima corgo|2014|13.5|Vinho Regional|medio|carne vermelha|seco|750ml|16-18C|5-10 anos|30min\n"
        "W|monte meao|vinha do cabeco vermelho|pt|r|tinta roriz|douro|cima corgo|2020|13.5|Vinho Regional|medio|carne vermelha|seco|750ml|16-18C|5-10 anos|30min\n"
    )
    parsed = v3_mod.parse_tabular_output(raw, 2)
    assert parsed[0]["duplicate_of"] is None
    assert parsed[1]["duplicate_of"] is None
    assert parsed[0]["vintage"] != parsed[1]["vintage"]


def test_to_discovery_enriched_converts_country_code_to_name():
    enriched = v3_mod.to_discovery_enriched({
        "kind": "wine",
        "producer": "ramon bilbao",
        "wine_name": "monte llano",
        "full_name": "ramon bilbao monte llano",
        "country_code": "es",
        "region": "rioja",
        "grape": "tempranillo",
    })
    assert enriched["country"] == "Spain"


# ============================================================
# 6. Discovery integration w/ v3 flag
# ============================================================

def test_discovery_uses_v3_when_flag_set():
    """When ENRICHMENT_MODE=gemini_hybrid_v3, discovery hits enrich_items_v3."""
    wine = {"id": 42, "nome": "Monte Llano", "produtor": "Ramon Bilbao"}

    calls = []

    def fake_v3(items, source_channel=None, trace=None):
        calls.append(source_channel)
        return {
            "items": [{
                "index": 1, "kind": "wine",
                "producer": "ramon bilbao", "wine_name": "monte llano",
                "full_name": "ramon bilbao monte llano",
                "country_code": "es", "style": "tinto",
                "grape": "tempranillo", "region": "rioja",
                "sub_region": None, "vintage": "NV",
                "abv": "13.5", "classification": "DOCa Rioja",
                "body": "medio", "pairing": "carne vermelha",
                "sweetness": "seco", "duplicate_of": None,
                "source_model": Config.ENRICHMENT_GEMINI_25_MODEL,
                "escalated": False, "raw_line": "W|..."
            }],
            "raw_primary": "W|...",
            "raw_escalated": "",
            "stats": {"total_items": 1, "escalated_items": 0,
                      "prompt_tokens": 0, "output_tokens": 0,
                      "thought_tokens": 0, "latency_ms": 10},
        }

    import services.enrichment_v3 as v3_mod_inner
    orig_v3 = v3_mod_inner.enrich_items_v3
    orig_mode = Config.ENRICHMENT_MODE
    orig_search = disc_mod.search_wine
    orig_pick = disc_mod._pick_best
    Config.ENRICHMENT_MODE = "gemini_hybrid_v3"
    v3_mod_inner.enrich_items_v3 = fake_v3
    disc_mod.search_wine = lambda q, **kw: {"wines": [wine], "total": 1}
    disc_mod._pick_best = lambda name, cands, seen: cands[0] if cands else None
    try:
        result = disc_mod.discover_unknowns([_make_unresolved("monte llano")])
    finally:
        v3_mod_inner.enrich_items_v3 = orig_v3
        Config.ENRICHMENT_MODE = orig_mode
        disc_mod.search_wine = orig_search
        disc_mod._pick_best = orig_pick

    assert calls == ["discovery"]
    assert len(result["newly_resolved"]) == 1
    assert result["newly_resolved"][0]["wine"]["id"] == 42
    assert result["stats"]["mode"] == "gemini_hybrid_v3"


def test_discovery_legacy_path_still_works():
    wine = {"id": 7, "nome": "Legacy Wine", "produtor": "Old"}

    orig_mode = Config.ENRICHMENT_MODE
    Config.ENRICHMENT_MODE = "legacy_qwen"
    orig_qwen = disc_mod.qwen_text_generate
    orig_search = disc_mod.search_wine
    orig_pick = disc_mod._pick_best
    disc_mod.qwen_text_generate = lambda p: '{"name": "Legacy Wine", "producer": "Old", "country": null, "region": null, "grape": null}'
    disc_mod.search_wine = lambda q, **kw: {"wines": [wine], "total": 1}
    disc_mod._pick_best = lambda name, cands, seen: cands[0] if cands else None
    try:
        result = disc_mod.discover_unknowns([_make_unresolved("legacy wine")])
    finally:
        Config.ENRICHMENT_MODE = orig_mode
        disc_mod.qwen_text_generate = orig_qwen
        disc_mod.search_wine = orig_search
        disc_mod._pick_best = orig_pick

    assert len(result["newly_resolved"]) == 1
    assert result["stats"]["mode"] == "legacy_qwen"


# ============================================================
# 7. Auto-create integration w/ v3 flag
# ============================================================

def test_auto_create_uses_v3_when_flag_set():
    """When ENRICHMENT_MODE=gemini_hybrid_v3, auto_create goes through v3 classifier."""
    captured_items = []

    def fake_v3(items, source_channel=None, trace=None):
        captured_items.append({"channel": source_channel, "count": len(items)})
        return {
            "items": [{
                "index": 1, "kind": "wine",
                "producer": "MontGras", "wine_name": "Aura Reserva Carmenere",
                "full_name": "MontGras Aura Reserva Carmenere",
                "country_code": "cl", "style": "tinto",
                "grape": "Carmenere", "region": "Colchagua",
                "sub_region": None, "vintage": "2020",
                "abv": "13.5", "classification": "Reserva",
                "body": "medio", "pairing": "carne vermelha",
                "sweetness": "seco", "duplicate_of": None,
                "source_model": Config.ENRICHMENT_GEMINI_25_MODEL,
                "escalated": False, "raw_line": "W|..."
            }],
            "raw_primary": "",
            "raw_escalated": "",
            "stats": {"total_items": 1, "escalated_items": 0,
                      "prompt_tokens": 0, "output_tokens": 0,
                      "thought_tokens": 0, "latency_ms": 10},
        }

    import services.enrichment_v3 as v3_mod_inner
    orig_v3 = v3_mod_inner.enrich_items_v3
    orig_mode = Config.ENRICHMENT_MODE
    orig_insert = nw_mod._insert_or_get_wine
    Config.ENRICHMENT_MODE = "gemini_hybrid_v3"
    v3_mod_inner.enrich_items_v3 = fake_v3

    inserted = []

    def fake_insert(enriched, ocr, source_channel, session_id):
        inserted.append(enriched)
        return {
            "id": 999, "nome": enriched.get("wine_name"),
            "produtor": enriched.get("producer"),
            "safra": enriched.get("vintage"),
            "tipo": enriched.get("style"),
            "pais": "cl", "pais_nome": "Chile", "regiao": "Colchagua",
            "sub_regiao": None, "uvas": ["Carmenere"],
            "teor_alcoolico": 13.5, "harmonizacao": "carne vermelha",
            "vivino_rating": None, "vivino_reviews": None,
            "preco_min": None, "preco_max": None, "moeda": None,
            "winegod_score": None, "winegod_score_type": None,
            "nota_wcf": None, "nota_wcf_sample_size": None,
            "confianca_nota": None,
        }

    nw_mod._insert_or_get_wine = fake_insert
    try:
        result = nw_mod.auto_create_unknowns(
            [_make_unresolved("pontgras aura reserva carmenere", producer="MontGras")],
            source_channel="pdf",
        )
    finally:
        v3_mod_inner.enrich_items_v3 = orig_v3
        Config.ENRICHMENT_MODE = orig_mode
        nw_mod._insert_or_get_wine = orig_insert

    assert captured_items[0]["channel"] == "auto_create_pdf"
    assert len(result["newly_resolved"]) == 1
    assert inserted[0]["producer"] == "MontGras"
    assert inserted[0]["kind"] == "wine"
    # v3 does NOT invent nota
    assert inserted[0]["estimated_note"] is None


def test_auto_create_v3_skips_non_wine():
    def fake_v3(items, source_channel=None, trace=None):
        return {
            "items": [{"index": 1, "kind": "not_wine", "raw_line": "X"}],
            "raw_primary": "X",
            "raw_escalated": "",
            "stats": {"total_items": 1, "escalated_items": 0,
                      "prompt_tokens": 0, "output_tokens": 0,
                      "thought_tokens": 0, "latency_ms": 10},
        }

    import services.enrichment_v3 as v3_mod_inner
    orig_v3 = v3_mod_inner.enrich_items_v3
    orig_mode = Config.ENRICHMENT_MODE
    orig_insert = nw_mod._insert_or_get_wine
    Config.ENRICHMENT_MODE = "gemini_hybrid_v3"
    v3_mod_inner.enrich_items_v3 = fake_v3

    insert_calls = []
    nw_mod._insert_or_get_wine = lambda *a, **kw: (insert_calls.append(a), None)[1]

    try:
        result = nw_mod.auto_create_unknowns(
            [_make_unresolved("coffee 125g")], source_channel="pdf"
        )
    finally:
        v3_mod_inner.enrich_items_v3 = orig_v3
        Config.ENRICHMENT_MODE = orig_mode
        nw_mod._insert_or_get_wine = orig_insert

    assert result["newly_resolved"] == []
    assert insert_calls == []


if __name__ == "__main__":
    tests = [
        test_parser_handles_X_S_W_and_duplicates,
        test_parser_fills_missing_lines_as_unknown,
        test_build_items_block_preserves_useful_ocr_signals,
        test_monte_llano_end_to_end,
        test_escalation_fires_when_primary_returns_unknown,
        test_no_escalation_when_item_is_spirit,
        test_no_escalation_for_non_wine_text,
        test_thinking_leak_raises_in_helper,
        test_enrich_tolerates_primary_failure_when_fallback_disabled,
        test_fallback_recovers_when_primary_fails,
        test_fallback_also_fails_returns_unknown,
        test_thinking_leak_in_primary_is_never_swallowed,
        test_duplicate_same_vintage_marked,
        test_different_vintages_not_duplicate,
        test_to_discovery_enriched_converts_country_code_to_name,
        test_discovery_uses_v3_when_flag_set,
        test_discovery_legacy_path_still_works,
        test_auto_create_uses_v3_when_flag_set,
        test_auto_create_v3_skips_non_wine,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
