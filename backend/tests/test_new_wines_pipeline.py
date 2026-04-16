"""Test auto-cadastro online de vinhos novos.

Runs offline (no DB, no Qwen, no Gemini): python -m tests.test_new_wines_pipeline
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.new_wines as nw_mod
import routes.chat as chat_mod
from services.display import resolve_display


def _make_wine(**kwargs):
    defaults = {
        "id": 999,
        "nome": "MontGras Aura Reserva Carmenere",
        "produtor": "MontGras",
        "safra": "2020",
        "tipo": "tinto",
        "pais": "cl",
        "pais_nome": "Chile",
        "regiao": "Colchagua Valley",
        "sub_regiao": None,
        "uvas": ["Carmenere"],
        "teor_alcoolico": 13.5,
        "harmonizacao": "carne vermelha",
        "vivino_rating": None,
        "vivino_reviews": None,
        "preco_min": None,
        "preco_max": None,
        "moeda": None,
        "winegod_score": None,
        "winegod_score_type": None,
        "nota_wcf": None,
        "nota_wcf_sample_size": None,
        "confianca_nota": None,
    }
    defaults.update(kwargs)
    return defaults


def _make_unresolved(name, producer=None, price=None):
    ocr = {"name": name}
    if producer:
        ocr["producer"] = producer
    if price:
        ocr["price"] = price
    return {"ocr": ocr, "status": "visual_only"}


class _FakeTrace:
    def step(self, name):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class _FakeCursor:
    def __init__(self, row):
        self.row = row
        self.executed = []
        self.description = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        self.executed.append({"query": query, "params": params})
        if query.strip().startswith("SELECT id, nome"):
            self.description = [(k,) for k in self.row.keys()]

    def fetchone(self):
        return tuple(self.row[k] for k in self.row.keys())


class _FakeConn:
    def __init__(self, row):
        self.cursor_obj = _FakeCursor(row)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_classify_candidates_uses_qwen():
    orig_qwen = nw_mod.qwen_text_generate
    orig_gemini = nw_mod.gemini_text_generate

    nw_mod.qwen_text_generate = lambda prompt: '{"items": [{"index": 1, "kind": "wine", "full_name": "Wine A", "producer": "Prod A", "wine_name": "Wine A", "country_code": "AR", "style": "tinto", "confidence": 0.9}]}'
    nw_mod.gemini_text_generate = lambda prompt, thinking=False: None
    try:
        result = nw_mod._classify_candidates([_make_unresolved("Wine A")])
    finally:
        nw_mod.qwen_text_generate = orig_qwen
        nw_mod.gemini_text_generate = orig_gemini

    assert result["items"][0]["kind"] == "wine"
    assert result["items"][0]["producer"] == "Prod A"


def test_classify_candidates_falls_back_to_gemini():
    orig_qwen = nw_mod.qwen_text_generate
    orig_gemini = nw_mod.gemini_text_generate

    nw_mod.qwen_text_generate = lambda prompt: None
    nw_mod.gemini_text_generate = lambda prompt, thinking=False: '{"items": [{"index": 1, "kind": "wine", "full_name": "Wine B", "producer": "Prod B", "wine_name": "Wine B", "country_code": "CL", "style": "tinto", "confidence": 0.92}]}'
    try:
        result = nw_mod._classify_candidates([_make_unresolved("Wine B")])
    finally:
        nw_mod.qwen_text_generate = orig_qwen
        nw_mod.gemini_text_generate = orig_gemini

    assert result["items"][0]["producer"] == "Prod B"


def test_auto_create_skips_not_wine():
    orig_classify = nw_mod._classify_candidates
    orig_insert = nw_mod._insert_or_get_wine
    orig_mode = nw_mod.Config.ENRICHMENT_MODE
    orig_enable = nw_mod.Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE
    insert_called = [False]

    nw_mod.Config.ENRICHMENT_MODE = "legacy"
    nw_mod.Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE = False
    nw_mod._classify_candidates = lambda items: {
        "items": [{"index": 1, "kind": "not_wine", "full_name": None, "producer": None, "confidence": 0.99}]
    }

    def spy_insert(*a, **kw):
        insert_called[0] = True
        return None

    nw_mod._insert_or_get_wine = spy_insert
    try:
        result = nw_mod.auto_create_unknowns([_make_unresolved("Gift Basket")], source_channel="pdf")
    finally:
        nw_mod._classify_candidates = orig_classify
        nw_mod._insert_or_get_wine = orig_insert
        nw_mod.Config.ENRICHMENT_MODE = orig_mode
        nw_mod.Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE = orig_enable

    assert len(result["newly_resolved"]) == 0
    assert len(result["still_unresolved"]) == 1
    assert result["blocked_items"] == []
    assert insert_called[0] is False


def test_auto_create_blocks_catalog_not_wine_before_insert():
    orig_classify = nw_mod._classify_candidates
    orig_insert = nw_mod._insert_or_get_wine
    orig_mode = nw_mod.Config.ENRICHMENT_MODE
    orig_enable = nw_mod.Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE
    insert_called = [False]

    nw_mod.Config.ENRICHMENT_MODE = "legacy"
    nw_mod.Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE = False
    nw_mod._classify_candidates = lambda items: {
        "items": [{
            "index": 1,
            "kind": "wine",
            "full_name": "Giffard Liqueur Gift Pack",
            "producer": "Giffard",
            "wine_name": "Liqueur Gift Pack",
            "country_code": "FR",
            "style": "tinto",
            "confidence": 0.99,
        }]
    }

    def spy_insert(*a, **kw):
        insert_called[0] = True
        return None

    nw_mod._insert_or_get_wine = spy_insert
    try:
        result = nw_mod.auto_create_unknowns([_make_unresolved("Giffard Liqueur Gift Pack", producer="Giffard")])
    finally:
        nw_mod._classify_candidates = orig_classify
        nw_mod._insert_or_get_wine = orig_insert
        nw_mod.Config.ENRICHMENT_MODE = orig_mode
        nw_mod.Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE = orig_enable

    assert result["stats"]["blocked_not_wine"] == 1
    assert result["newly_resolved"] == []
    assert result["still_unresolved"] == []
    assert len(result["blocked_items"]) == 1
    assert result["blocked_items"][0]["reason"] == "wine_filter=giffard"
    assert insert_called[0] is False


def test_auto_create_caps_at_two():
    orig_classify = nw_mod._classify_candidates
    orig_insert = nw_mod._insert_or_get_wine
    orig_mode = nw_mod.Config.ENRICHMENT_MODE
    orig_enable = nw_mod.Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE

    nw_mod.Config.ENRICHMENT_MODE = "legacy"
    nw_mod.Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE = False
    nw_mod._classify_candidates = lambda items: {
        "items": [
            {"index": 1, "kind": "wine", "full_name": "Wine Alpha", "producer": "Prod A", "wine_name": "Alpha", "country_code": "AR", "style": "tinto", "confidence": 0.9},
            {"index": 2, "kind": "wine", "full_name": "Wine Beta", "producer": "Prod B", "wine_name": "Beta", "country_code": "CL", "style": "tinto", "confidence": 0.9},
        ]
    }
    nw_mod._insert_or_get_wine = lambda enriched, ocr, source_channel, session_id: _make_wine(
        id=100 + enriched["index"], nome=enriched["full_name"], produtor=enriched["producer"]
    )
    try:
        result = nw_mod.auto_create_unknowns(
            [_make_unresolved("Alpha"), _make_unresolved("Beta"), _make_unresolved("Gamma")],
            source_channel="text",
        )
    finally:
        nw_mod._classify_candidates = orig_classify
        nw_mod._insert_or_get_wine = orig_insert
        nw_mod.Config.ENRICHMENT_MODE = orig_mode
        nw_mod.Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE = orig_enable

    assert len(result["newly_resolved"]) == 2
    assert len(result["still_unresolved"]) == 1
    assert result["still_unresolved"][0]["ocr"]["name"] == "Gamma"


def test_insert_or_get_wine_blocks_catalog_not_wine_without_db_connection():
    orig_get = nw_mod.get_connection
    orig_release = nw_mod.release_connection
    conn_called = [False]
    release_called = [False]

    nw_mod.get_connection = lambda: conn_called.__setitem__(0, True)
    nw_mod.release_connection = lambda c: release_called.__setitem__(0, True)
    try:
        wine = nw_mod._insert_or_get_wine(
            {
                "kind": "wine",
                "full_name": "Original 10 Year Old",
                "producer": "Glenmorangie",
                "wine_name": "Original 10 Year Old",
                "country_code": "GB",
                "style": "tinto",
                "confidence": 0.99,
            },
            {"name": "Original 10 Year Old", "producer": "Glenmorangie"},
            "pdf",
            "sid-2",
        )
    finally:
        nw_mod.get_connection = orig_get
        nw_mod.release_connection = orig_release

    assert wine is None
    assert conn_called[0] is False
    assert release_called[0] is False


def test_insert_or_get_wine_persists_expected_fields():
    row = _make_wine(
        nome="Aura Reserva Carmenere",
        nota_wcf=4.05,
        confianca_nota=0.88,
    )
    conn = _FakeConn(row)
    released = [False]

    orig_get = nw_mod.get_connection
    orig_release = nw_mod.release_connection

    nw_mod.get_connection = lambda: conn
    nw_mod.release_connection = lambda c: released.__setitem__(0, True)
    try:
        wine = nw_mod._insert_or_get_wine(
            {
                "kind": "wine",
                "full_name": "MontGras Aura Reserva Carmenere",
                "producer": "MontGras",
                "wine_name": "Aura Reserva Carmenere",
                "country_code": "CL",
                "style": "tinto",
                "grape": "Carmenere",
                "region": "Colchagua Valley",
                "sub_region": None,
                "vintage": "2020",
                "abv": "13.5",
                "classification": "Reserva",
                "body": "medio",
                "pairing": "carne vermelha",
                "sweetness": "seco",
                "estimated_note": 4.05,
                "confidence": 0.88,
            },
            {"name": "Pontgras Aura Reserva Carmenere"},
            "pdf",
            "sid-1",
        )
    finally:
        nw_mod.get_connection = orig_get
        nw_mod.release_connection = orig_release

    assert conn.committed
    assert released[0] is True
    assert wine["nome"] == "Aura Reserva Carmenere"
    insert_params = conn.cursor_obj.executed[0]["params"]
    assert insert_params[0] == nw_mod._generate_hash_dedup("aura reserva carmenere", "montgras", "2020")
    assert insert_params[1] == "Aura Reserva Carmenere"
    assert insert_params[7] == "cl"
    assert insert_params[8] == "Chile"
    assert insert_params[17] == 4.05
    assert insert_params[18] == 0.88


def test_resolve_display_supports_ai_estimated_note():
    display = resolve_display(
        _make_wine(
            nota_wcf=3.92,
            nota_wcf_sample_size=None,
            vivino_rating=None,
            confianca_nota=0.84,
        )
    )
    assert display["display_note"] == 3.92
    assert display["display_note_type"] == "estimated"
    assert display["display_note_source"] == "ai"


def test_pdf_auto_create_moves_item_to_resolved():
    wine = _make_wine(
        id=555,
        nome="Aura Reserva Carmenere",
        produtor="MontGras",
        nota_wcf=4.05,
        confianca_nota=0.88,
    )

    resolved_items = []
    unresolved_items = [_make_unresolved("Pontgras Aura Reserva Carmenere", producer="MontGras", price="R$ 89")]

    import tools.media as media_mod
    import tools.resolver as resolver_mod

    orig_process_pdf = media_mod.process_pdf
    orig_chat_process_pdf = chat_mod.process_pdf
    orig_resolve = chat_mod.resolve_wines_from_ocr
    orig_resolver_resolve = resolver_mod.resolve_wines_from_ocr
    orig_discover = chat_mod.discover_unknowns
    orig_auto = chat_mod.auto_create_unknowns
    orig_log = chat_mod.log_discovery

    media_mod.process_pdf = lambda b: {
        "status": "success",
        "description": "test",
        "extraction_method": "native_text",
        "was_truncated": False,
        "pages_processed": 1,
        "wines": [{"name": "Pontgras Aura Reserva Carmenere", "producer": "MontGras", "price": "R$ 89"}],
    }
    chat_mod.process_pdf = media_mod.process_pdf

    def fake_resolve(ocr_result):
        return {
            "resolved_wines": [],
            "unresolved": [it["ocr"]["name"] for it in unresolved_items],
            "resolved_items": list(resolved_items),
            "unresolved_items": list(unresolved_items),
            "timing_ms": 10,
        }

    resolver_mod.resolve_wines_from_ocr = fake_resolve
    chat_mod.resolve_wines_from_ocr = fake_resolve
    chat_mod.discover_unknowns = lambda unresolved_items, trace=None, initial_seen_ids=None: {
        "newly_resolved": [],
        "still_unresolved": list(unresolved_items),
        "stats": {},
    }
    chat_mod.auto_create_unknowns = lambda unresolved_items, source_channel="chat", session_id=None, initial_seen_ids=None: {
        "newly_resolved": [{
            "ocr": unresolved_items[0]["ocr"],
            "wine": wine,
            "status": "confirmed_with_note",
            "auto_created": True,
            "enriched_data": {"full_name": "MontGras Aura Reserva Carmenere", "wine_name": wine["nome"]},
        }],
        "still_unresolved": [],
        "stats": {"created": 1},
    }
    chat_mod.log_discovery = lambda *a, **kw: None

    try:
        msg, photo_mode = chat_mod._process_media({"pdf": "base64data"}, "test", _FakeTrace(), session_id="sid")
    finally:
        media_mod.process_pdf = orig_process_pdf
        chat_mod.process_pdf = orig_chat_process_pdf
        resolver_mod.resolve_wines_from_ocr = orig_resolver_resolve
        chat_mod.resolve_wines_from_ocr = orig_resolve
        chat_mod.discover_unknowns = orig_discover
        chat_mod.auto_create_unknowns = orig_auto
        chat_mod.log_discovery = orig_log

    assert photo_mode is False
    assert "Aura Reserva Carmenere" in msg
    assert "MontGras" in msg
    assert "(estimated)" in msg
    assert "[NAO ENCONTRADO(S) no banco" not in msg


def test_auto_create_respects_initial_seen_ids():
    orig_classify = nw_mod._classify_candidates
    orig_insert = nw_mod._insert_or_get_wine
    orig_mode = nw_mod.Config.ENRICHMENT_MODE
    orig_enable = nw_mod.Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE

    nw_mod.Config.ENRICHMENT_MODE = "legacy"
    nw_mod.Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE = False
    nw_mod._classify_candidates = lambda items: {
        "items": [{"index": 1, "kind": "wine", "full_name": "MontGras Aura Reserva Carmenere", "producer": "MontGras", "wine_name": "Aura Reserva Carmenere", "country_code": "CL", "style": "tinto", "confidence": 0.9}]
    }
    nw_mod._insert_or_get_wine = lambda enriched, ocr, source_channel, session_id: _make_wine(
        id=555,
        nome="Aura Reserva Carmenere",
        produtor="MontGras",
        nota_wcf=4.05,
        confianca_nota=0.88,
    )
    try:
        result = nw_mod.auto_create_unknowns(
            [_make_unresolved("Pontgras Aura Reserva Carmenere", producer="MontGras")],
            source_channel="pdf",
            initial_seen_ids={555},
        )
    finally:
        nw_mod._classify_candidates = orig_classify
        nw_mod._insert_or_get_wine = orig_insert
        nw_mod.Config.ENRICHMENT_MODE = orig_mode
        nw_mod.Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE = orig_enable

    assert result["newly_resolved"] == []
    assert len(result["still_unresolved"]) == 1


def test_apply_auto_create_removes_blocked_not_wine_without_new_resolution():
    orig_auto = chat_mod.auto_create_unknowns
    unresolved = _make_unresolved("Giffard Liqueur Gift Pack", producer="Giffard")
    resolved = {
        "resolved_wines": [],
        "unresolved": [unresolved["ocr"]["name"]],
        "resolved_items": [],
        "unresolved_items": [unresolved],
    }

    chat_mod.auto_create_unknowns = lambda unresolved_items, source_channel="chat", session_id=None, initial_seen_ids=None: {
        "newly_resolved": [],
        "still_unresolved": [],
        "blocked_items": [{"ocr": unresolved["ocr"], "reason": "wine_filter=giffard"}],
        "stats": {"blocked_not_wine": 1},
    }
    try:
        chat_mod._apply_auto_create(resolved, _FakeTrace())
    finally:
        chat_mod.auto_create_unknowns = orig_auto

    assert resolved["resolved_items"] == []
    assert resolved["resolved_wines"] == []
    assert resolved["unresolved_items"] == []
    assert resolved["unresolved"] == []


def test_single_image_calls_discovery_before_auto_create():
    """Proves single image path goes: pre_resolve -> discovery -> auto_create."""
    import tools.media as media_mod
    import tools.resolver as resolver_mod

    discovery_called = [False]
    auto_create_called = [False]
    call_order = []

    wine = _make_wine(id=700, nome="Test Wine", produtor="Test Producer")
    unresolved = [_make_unresolved("Unknown Wine")]

    orig_process_image = media_mod.process_image
    orig_chat_process_image = chat_mod.process_image
    orig_resolve = chat_mod.resolve_wines_from_ocr
    orig_resolver_resolve = resolver_mod.resolve_wines_from_ocr
    orig_discover = chat_mod.discover_unknowns
    orig_auto = chat_mod.auto_create_unknowns
    orig_log = chat_mod.log_discovery

    media_mod.process_image = lambda b: {
        "image_type": "shelf",
        "wines": [{"name": "Unknown Wine"}],
        "total_visible": 1,
    }
    chat_mod.process_image = media_mod.process_image

    def fake_resolve(ocr_result):
        return {
            "resolved_wines": [],
            "unresolved": ["Unknown Wine"],
            "resolved_items": [],
            "unresolved_items": list(unresolved),
            "timing_ms": 10,
        }

    resolver_mod.resolve_wines_from_ocr = fake_resolve
    chat_mod.resolve_wines_from_ocr = fake_resolve

    def fake_discover(unresolved_items, trace=None, initial_seen_ids=None):
        discovery_called[0] = True
        call_order.append("discovery")
        return {"newly_resolved": [], "still_unresolved": list(unresolved_items), "stats": {}}

    def fake_auto_create(unresolved_items, source_channel="chat", session_id=None, initial_seen_ids=None):
        auto_create_called[0] = True
        call_order.append("auto_create")
        return {
            "newly_resolved": [{"ocr": unresolved_items[0]["ocr"], "wine": wine, "status": "confirmed_no_note", "auto_created": True, "enriched_data": {}}],
            "still_unresolved": [],
            "stats": {"created": 1},
        }

    chat_mod.discover_unknowns = fake_discover
    chat_mod.auto_create_unknowns = fake_auto_create
    chat_mod.log_discovery = lambda *a, **kw: None

    try:
        msg, photo_mode = chat_mod._process_single_image("base64data", "test", _FakeTrace())
    finally:
        media_mod.process_image = orig_process_image
        chat_mod.process_image = orig_chat_process_image
        resolver_mod.resolve_wines_from_ocr = orig_resolver_resolve
        chat_mod.resolve_wines_from_ocr = orig_resolve
        chat_mod.discover_unknowns = orig_discover
        chat_mod.auto_create_unknowns = orig_auto
        chat_mod.log_discovery = orig_log

    assert discovery_called[0], "discovery was not called in single image path"
    assert auto_create_called[0], "auto_create was not called in single image path"
    assert call_order == ["discovery", "auto_create"], f"wrong order: {call_order}"


def test_batch_image_calls_discovery_before_auto_create():
    """Proves batch image path goes: pre_resolve -> discovery -> auto_create."""
    import tools.media as media_mod
    import tools.resolver as resolver_mod

    discovery_called = [False]
    auto_create_called = [False]
    call_order = []

    wine = _make_wine(id=701, nome="Test Wine B", produtor="Test Producer B")
    unresolved = [_make_unresolved("Unknown Wine B")]

    orig_batch = media_mod.process_images_batch
    orig_chat_batch = chat_mod.process_images_batch
    orig_resolve = chat_mod.resolve_wines_from_ocr
    orig_resolver_resolve = resolver_mod.resolve_wines_from_ocr
    orig_discover = chat_mod.discover_unknowns
    orig_auto = chat_mod.auto_create_unknowns
    orig_log = chat_mod.log_discovery

    media_mod.process_images_batch = lambda imgs: {
        "image_count": 1,
        "labels": [],
        "screenshots": [],
        "shelves": [{"wines": [{"name": "Unknown Wine B"}], "total_visible": 1}],
        "errors": [],
    }
    chat_mod.process_images_batch = media_mod.process_images_batch

    def fake_resolve(ocr_result):
        return {
            "resolved_wines": [],
            "unresolved": ["Unknown Wine B"],
            "resolved_items": [],
            "unresolved_items": list(unresolved),
            "timing_ms": 10,
        }

    resolver_mod.resolve_wines_from_ocr = fake_resolve
    chat_mod.resolve_wines_from_ocr = fake_resolve

    def fake_discover(unresolved_items, trace=None, initial_seen_ids=None):
        discovery_called[0] = True
        call_order.append("discovery")
        return {"newly_resolved": [], "still_unresolved": list(unresolved_items), "stats": {}}

    def fake_auto_create(unresolved_items, source_channel="chat", session_id=None, initial_seen_ids=None):
        auto_create_called[0] = True
        call_order.append("auto_create")
        return {
            "newly_resolved": [{"ocr": unresolved_items[0]["ocr"], "wine": wine, "status": "confirmed_no_note", "auto_created": True, "enriched_data": {}}],
            "still_unresolved": [],
            "stats": {"created": 1},
        }

    chat_mod.discover_unknowns = fake_discover
    chat_mod.auto_create_unknowns = fake_auto_create
    chat_mod.log_discovery = lambda *a, **kw: None

    try:
        msg, photo_mode = chat_mod._process_batch_images(["base64a", "base64b"], "test", _FakeTrace())
    finally:
        media_mod.process_images_batch = orig_batch
        chat_mod.process_images_batch = orig_chat_batch
        resolver_mod.resolve_wines_from_ocr = orig_resolver_resolve
        chat_mod.resolve_wines_from_ocr = orig_resolve
        chat_mod.discover_unknowns = orig_discover
        chat_mod.auto_create_unknowns = orig_auto
        chat_mod.log_discovery = orig_log

    assert discovery_called[0], "discovery was not called in batch image path"
    assert auto_create_called[0], "auto_create was not called in batch image path"
    assert call_order == ["discovery", "auto_create"], f"wrong order: {call_order}"


def test_classify_falls_back_to_gemini_on_empty_qwen():
    """Proves Gemini is tried when Qwen returns empty string."""
    orig_qwen = nw_mod.qwen_text_generate
    orig_gemini = nw_mod.gemini_text_generate

    gemini_called = [False]

    def fake_gemini(prompt, thinking=False):
        gemini_called[0] = True
        return '{"items": [{"index": 1, "kind": "wine", "full_name": "Wine C", "producer": "Prod C", "wine_name": "Wine C", "country_code": "FR", "style": "tinto", "confidence": 0.85}]}'

    nw_mod.qwen_text_generate = lambda prompt: ""
    nw_mod.gemini_text_generate = fake_gemini
    try:
        result = nw_mod._classify_candidates([_make_unresolved("Wine C")])
    finally:
        nw_mod.qwen_text_generate = orig_qwen
        nw_mod.gemini_text_generate = orig_gemini

    assert gemini_called[0], "Gemini was not called when Qwen returned empty string"
    assert result["items"][0]["kind"] == "wine"


def test_classify_falls_back_to_gemini_on_invalid_json():
    """Proves Gemini is tried when Qwen returns invalid JSON."""
    orig_qwen = nw_mod.qwen_text_generate
    orig_gemini = nw_mod.gemini_text_generate

    gemini_called = [False]

    def fake_gemini(prompt, thinking=False):
        gemini_called[0] = True
        return '{"items": [{"index": 1, "kind": "wine", "full_name": "Wine D", "producer": "Prod D", "wine_name": "Wine D", "country_code": "IT", "style": "branco", "confidence": 0.88}]}'

    nw_mod.qwen_text_generate = lambda prompt: "this is not valid json at all"
    nw_mod.gemini_text_generate = fake_gemini
    try:
        result = nw_mod._classify_candidates([_make_unresolved("Wine D")])
    finally:
        nw_mod.qwen_text_generate = orig_qwen
        nw_mod.gemini_text_generate = orig_gemini

    assert gemini_called[0], "Gemini was not called when Qwen returned invalid JSON"
    assert result["items"][0]["producer"] == "Prod D"


if __name__ == "__main__":
    tests = [
        test_classify_candidates_uses_qwen,
        test_classify_candidates_falls_back_to_gemini,
        test_auto_create_skips_not_wine,
        test_auto_create_blocks_catalog_not_wine_before_insert,
        test_auto_create_caps_at_two,
        test_insert_or_get_wine_blocks_catalog_not_wine_without_db_connection,
        test_insert_or_get_wine_persists_expected_fields,
        test_resolve_display_supports_ai_estimated_note,
        test_pdf_auto_create_moves_item_to_resolved,
        test_auto_create_respects_initial_seen_ids,
        test_apply_auto_create_removes_blocked_not_wine_without_new_resolution,
        test_single_image_calls_discovery_before_auto_create,
        test_batch_image_calls_discovery_before_auto_create,
        test_classify_falls_back_to_gemini_on_empty_qwen,
        test_classify_falls_back_to_gemini_on_invalid_json,
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
