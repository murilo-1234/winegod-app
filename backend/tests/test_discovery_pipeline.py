"""Test Fase 2: discovery pipeline (enrichment + second resolve).

Runs offline (no DB, no Qwen, no Gemini): python -m tests.test_discovery_pipeline
All external calls are mocked.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.discovery as disc_mod
from services.discovery import discover_unknowns, _enrich_wine, _second_resolve
import routes.chat as chat_mod


# --- Mock helpers ---

def _make_wine(**kwargs):
    defaults = {
        "id": 1, "nome": "Test Wine", "produtor": "Test Producer",
        "safra": "2020", "tipo": "tinto", "pais_nome": "Argentina",
        "regiao": "Mendoza", "vivino_rating": 4.2, "preco_min": 50,
        "preco_max": 80, "moeda": "BRL", "winegod_score": 3.8,
        "winegod_score_type": "verified", "nota_wcf": 4.1,
        "nota_wcf_sample_size": 150,
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


def _with_mocks(mocks):
    """Context manager that patches disc_mod attributes and restores after."""
    class _Ctx:
        def __init__(self):
            self._originals = {}
        def __enter__(self):
            for attr, fn in mocks.items():
                self._originals[attr] = getattr(disc_mod, attr)
                setattr(disc_mod, attr, fn)
            return self
        def __exit__(self, *a):
            for attr, orig in self._originals.items():
                setattr(disc_mod, attr, orig)
    return _Ctx()


# ============================================================
# 1. discover_unknowns core
# ============================================================

def test_enrichment_corrects_ocr_and_resolves():
    """OCR error -> enrichment corrects -> second resolve finds match."""
    wine = _make_wine(id=42, nome="MontGras Aura Reserva Carmenere")

    def mock_qwen(prompt):
        return '{"name": "MontGras Aura Reserva Carmenere", "producer": "MontGras", "country": "Chile", "region": null, "grape": "Carmenere"}'

    def mock_search(query, **kwargs):
        return {"wines": [wine], "total": 1}

    def mock_pick_best(ocr_name, candidates, seen_ids):
        if candidates and candidates[0]["id"] not in seen_ids:
            return candidates[0]
        return None

    with _with_mocks({"qwen_text_generate": mock_qwen, "search_wine": mock_search, "_pick_best": mock_pick_best}):
        items = [_make_unresolved("Pontgras Aura Reserva Carmenere")]
        result = discover_unknowns(items)

    assert len(result["newly_resolved"]) == 1
    assert result["newly_resolved"][0]["wine"]["id"] == 42
    assert result["newly_resolved"][0]["enriched"] is True
    assert result["newly_resolved"][0]["enriched_data"]["name"] == "MontGras Aura Reserva Carmenere"
    assert result["newly_resolved"][0]["status"] in ("confirmed_with_note", "confirmed_no_note")
    assert len(result["still_unresolved"]) == 0


def test_enrichment_infers_producer():
    """Missing producer -> enrichment infers -> second resolve finds match."""
    wine = _make_wine(id=99, nome="Alamos Malbec", produtor="Catena")

    def mock_qwen(prompt):
        return '{"name": "Alamos Malbec", "producer": "Catena", "country": "Argentina", "region": "Mendoza", "grape": "Malbec"}'

    def mock_search(query, **kwargs):
        if kwargs.get("produtor") == "Catena":
            return {"wines": [wine], "total": 1}
        return {"wines": [], "total": 0}

    def mock_pick_best(ocr_name, candidates, seen_ids):
        if candidates:
            return candidates[0]
        return None

    with _with_mocks({"qwen_text_generate": mock_qwen, "search_wine": mock_search, "_pick_best": mock_pick_best}):
        items = [_make_unresolved("Alamos Malbec")]  # no producer in OCR
        result = discover_unknowns(items)

    assert len(result["newly_resolved"]) == 1
    assert result["newly_resolved"][0]["enriched_data"]["producer"] == "Catena"


def test_nonexistent_wine_stays_unresolved():
    """Wine not in DB -> quality gate rejects -> stays unresolved."""
    def mock_qwen(prompt):
        return '{"name": "Chateau Inexistente 2019", "producer": "Inexistente", "country": null, "region": null, "grape": null}'

    def mock_search(query, **kwargs):
        return {"wines": [], "total": 0}

    with _with_mocks({"qwen_text_generate": mock_qwen, "search_wine": mock_search}):
        items = [_make_unresolved("Chateau Inexistente 2019")]
        result = discover_unknowns(items)

    assert len(result["newly_resolved"]) == 0
    assert len(result["still_unresolved"]) == 1


def test_enrichment_failure_keeps_unresolved():
    """Enrichment returns None -> item stays unresolved."""
    def mock_qwen(prompt):
        return None  # Qwen unavailable

    with _with_mocks({"qwen_text_generate": mock_qwen}):
        items = [_make_unresolved("Some Wine")]
        result = discover_unknowns(items)

    assert len(result["newly_resolved"]) == 0
    assert len(result["still_unresolved"]) == 1


def test_enrichment_invalid_json_keeps_unresolved():
    """Enrichment returns garbage -> item stays unresolved."""
    def mock_qwen(prompt):
        return "this is not json at all"

    with _with_mocks({"qwen_text_generate": mock_qwen}):
        items = [_make_unresolved("Some Wine")]
        result = discover_unknowns(items)

    assert len(result["newly_resolved"]) == 0
    assert len(result["still_unresolved"]) == 1


def test_quality_gate_rejects_bad_match():
    """Second resolve returns candidates but _pick_best rejects -> stays unresolved."""
    wine = _make_wine(id=50, nome="Completely Different Wine")

    def mock_qwen(prompt):
        return '{"name": "Reserva Especial", "producer": null, "country": null, "region": null, "grape": null}'

    def mock_search(query, **kwargs):
        return {"wines": [wine], "total": 1}

    def mock_pick_best(ocr_name, candidates, seen_ids):
        return None  # Quality gate rejects

    with _with_mocks({"qwen_text_generate": mock_qwen, "search_wine": mock_search, "_pick_best": mock_pick_best}):
        items = [_make_unresolved("Reserva Especial")]
        result = discover_unknowns(items)

    assert len(result["newly_resolved"]) == 0
    assert len(result["still_unresolved"]) == 1


def test_budget_exceeded_stops_gracefully():
    """Budget exceeded -> stops processing, remaining items go to unresolved."""
    call_count = [0]

    def mock_qwen_slow(prompt):
        call_count[0] += 1
        time.sleep(0.01)  # Tiny delay, we'll override budget
        return '{"name": "Wine", "producer": null, "country": null, "region": null, "grape": null}'

    def mock_search(query, **kwargs):
        return {"wines": [], "total": 0}

    # Override budget to something very small
    orig_budget = disc_mod.MAX_BUDGET_MS
    disc_mod.MAX_BUDGET_MS = 1  # 1ms — will exceed immediately after first item

    with _with_mocks({"qwen_text_generate": mock_qwen_slow, "search_wine": mock_search}):
        try:
            items = [_make_unresolved("Wine A"), _make_unresolved("Wine B")]
            result = discover_unknowns(items)
        finally:
            disc_mod.MAX_BUDGET_MS = orig_budget

    # First item was processed (enriched), second should be in still_unresolved
    total = len(result["newly_resolved"]) + len(result["still_unresolved"])
    assert total == 2
    assert result["stats"]["enriched"] >= 1


def test_cap_2_processes_first_2_only():
    """10 unknowns -> processes first 2, rest go to still_unresolved."""
    call_count = [0]

    def mock_qwen(prompt):
        call_count[0] += 1
        return '{"name": "Wine", "producer": null, "country": null, "region": null, "grape": null}'

    def mock_search(query, **kwargs):
        return {"wines": [], "total": 0}

    with _with_mocks({"qwen_text_generate": mock_qwen, "search_wine": mock_search}):
        items = [_make_unresolved(f"Wine {i}") for i in range(10)]
        result = discover_unknowns(items)

    assert call_count[0] == 2, f"Should enrich exactly 2, got {call_count[0]}"
    assert len(result["still_unresolved"]) == 10  # all unresolved (no DB match)
    assert result["stats"]["skipped"] == 8
    assert result["stats"]["enriched"] == 2


def test_seen_ids_prevents_duplicates():
    """seen_ids should prevent the same wine being resolved twice."""
    wine = _make_wine(id=42, nome="MontGras")

    call_count = [0]

    def mock_qwen(prompt):
        return '{"name": "MontGras", "producer": "MontGras", "country": null, "region": null, "grape": null}'

    def mock_search(query, **kwargs):
        return {"wines": [wine], "total": 1}

    # First call returns the wine, second call returns None (seen_ids blocks)
    def mock_pick_best(ocr_name, candidates, seen_ids):
        nonlocal call_count
        call_count[0] += 1
        for c in candidates:
            if c["id"] not in seen_ids:
                return c
        return None

    with _with_mocks({"qwen_text_generate": mock_qwen, "search_wine": mock_search, "_pick_best": mock_pick_best}):
        items = [_make_unresolved("MontGras A"), _make_unresolved("MontGras B")]
        result = discover_unknowns(items)

    # First item resolved, second blocked by seen_ids
    assert len(result["newly_resolved"]) == 1
    assert len(result["still_unresolved"]) == 1


def test_initial_seen_ids_prevents_pre_resolve_duplicates():
    """initial_seen_ids should block discovery from resolving to a wine already in pre-resolve."""
    wine = _make_wine(id=42, nome="MontGras")

    def mock_qwen(prompt):
        return '{"name": "MontGras", "producer": "MontGras", "country": null, "region": null, "grape": null}'

    def mock_search(query, **kwargs):
        return {"wines": [wine], "total": 1}

    def mock_pick_best(ocr_name, candidates, seen_ids):
        for c in candidates:
            if c["id"] not in seen_ids:
                return c
        return None

    with _with_mocks({"qwen_text_generate": mock_qwen, "search_wine": mock_search, "_pick_best": mock_pick_best}):
        items = [_make_unresolved("MontGras Aura")]
        # Pass wine id=42 as already resolved in pre-resolve
        result = discover_unknowns(items, initial_seen_ids={42})

    assert len(result["newly_resolved"]) == 0, "Should NOT resolve to a wine already in pre-resolve"
    assert len(result["still_unresolved"]) == 1


def test_initial_seen_ids_allows_different_wine():
    """initial_seen_ids should NOT block a different wine.id."""
    wine = _make_wine(id=99, nome="Alamos Malbec")

    def mock_qwen(prompt):
        return '{"name": "Alamos Malbec", "producer": "Catena", "country": null, "region": null, "grape": null}'

    def mock_search(query, **kwargs):
        return {"wines": [wine], "total": 1}

    def mock_pick_best(ocr_name, candidates, seen_ids):
        for c in candidates:
            if c["id"] not in seen_ids:
                return c
        return None

    with _with_mocks({"qwen_text_generate": mock_qwen, "search_wine": mock_search, "_pick_best": mock_pick_best}):
        items = [_make_unresolved("Alamos")]
        # id=42 in pre-resolve, but wine is id=99 — should pass
        result = discover_unknowns(items, initial_seen_ids={42})

    assert len(result["newly_resolved"]) == 1
    assert result["newly_resolved"][0]["wine"]["id"] == 99


def test_empty_input():
    """Empty input returns empty result."""
    result = discover_unknowns([])
    assert result["newly_resolved"] == []
    assert result["still_unresolved"] == []


def test_item_without_name_stays_unresolved():
    """Item with empty name should be skipped without enrichment."""
    call_count = [0]

    def mock_qwen(prompt):
        call_count[0] += 1
        return '{}'

    with _with_mocks({"qwen_text_generate": mock_qwen}):
        items = [{"ocr": {"name": ""}, "status": "visual_only"}]
        result = discover_unknowns(items)

    assert call_count[0] == 0, "Should not call enrichment for empty name"
    assert len(result["still_unresolved"]) == 1


# ============================================================
# 2. _enrich_wine unit tests
# ============================================================

def test_enrich_wine_strips_code_fences():
    """Enrichment should strip markdown code fences."""
    def mock_qwen(prompt):
        return '```json\n{"name": "Wine", "producer": "Prod", "country": null, "region": null, "grape": null}\n```'

    with _with_mocks({"qwen_text_generate": mock_qwen}):
        result = _enrich_wine("Wine", "Prod")

    assert result is not None
    assert result["name"] == "Wine"


def test_enrich_wine_returns_none_on_error():
    """Enrichment should return None on any error."""
    def mock_qwen(prompt):
        raise RuntimeError("API down")

    with _with_mocks({"qwen_text_generate": mock_qwen}):
        result = _enrich_wine("Wine", "Prod")

    assert result is None


# ============================================================
# 3. Integration: _apply_discovery in chat.py
# ============================================================

class _FakeTrace:
    def step(self, name):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _mock_process_pdf(result):
    def fake(base64_pdf):
        return result
    return fake


def _mock_process_video(result):
    def fake(base64_video):
        return result
    return fake


def _mock_resolve_returning(resolved_items, unresolved_items):
    def fake(ocr_result):
        return {
            "resolved_wines": [it["wine"] for it in resolved_items],
            "unresolved": [it["ocr"].get("name", "?") for it in unresolved_items],
            "resolved_items": list(resolved_items),
            "unresolved_items": list(unresolved_items),
            "timing_ms": 10,
        }
    return fake


def _mock_discover_that_resolves(wine):
    """Mock discover_unknowns that resolves the first unresolved item."""
    def fake(unresolved_items, trace=None, initial_seen_ids=None):
        if not unresolved_items:
            return {"newly_resolved": [], "still_unresolved": [], "stats": {}}
        first = unresolved_items[0]
        rest = unresolved_items[1:]
        return {
            "newly_resolved": [{
                "ocr": first["ocr"],
                "wine": wine,
                "status": "confirmed_with_note",
                "enriched": True,
                "enriched_data": {"name": wine["nome"]},
            }],
            "still_unresolved": rest,
            "stats": {"enriched": 1, "resolved_second": 1, "budget_used_ms": 500, "skipped": 0},
        }
    return fake


def _mock_discover_that_finds_nothing():
    """Mock discover_unknowns that resolves nothing."""
    def fake(unresolved_items, trace=None, initial_seen_ids=None):
        return {
            "newly_resolved": [],
            "still_unresolved": list(unresolved_items),
            "stats": {"enriched": 1, "resolved_second": 0, "budget_used_ms": 500, "skipped": 0},
        }
    return fake


def _noop_auto_create(unresolved_items, source_channel="chat", session_id=None, initial_seen_ids=None):
    return {
        "newly_resolved": [],
        "still_unresolved": list(unresolved_items or []),
        "stats": {},
    }


def _run_process_media(data, message="test", mocks=None):
    mocks = mocks or {}
    originals = {}

    # Default: no-op logging to avoid DB calls
    if "log_discovery" not in mocks:
        mocks["log_discovery"] = lambda *a, **kw: None
    if "auto_create_unknowns" not in mocks:
        mocks["auto_create_unknowns"] = _noop_auto_create

    import tools.media as media_mod
    mock_map = {
        "process_pdf": [(media_mod, "process_pdf"), (chat_mod, "process_pdf")],
        "process_video": [(media_mod, "process_video"), (chat_mod, "process_video")],
        "resolve_wines_from_ocr": [(chat_mod, "resolve_wines_from_ocr")],
        "discover_unknowns": [(chat_mod, "discover_unknowns")],
        "auto_create_unknowns": [(chat_mod, "auto_create_unknowns")],
        "log_discovery": [(chat_mod, "log_discovery")],
    }

    for key, fn in mocks.items():
        if key in mock_map:
            for mod, attr in mock_map[key]:
                originals[(mod, attr)] = getattr(mod, attr)
                setattr(mod, attr, fn)

    try:
        trace = _FakeTrace()
        return chat_mod._process_media(data, message, trace, session_id="test-sid")
    finally:
        for (mod, attr), orig in originals.items():
            setattr(mod, attr, orig)


def test_pdf_discovery_moves_item_to_resolved():
    """PDF: discovery resolves unresolved item -> item appears in confirmed context."""
    known_wine = _make_wine(id=1)
    discovery_wine = _make_wine(id=2, nome="Discovered Wine", produtor="Discovery Producer")

    resolved_items = [{"ocr": {"name": "Known"}, "wine": known_wine, "status": "confirmed_with_note"}]
    unresolved_items = [_make_unresolved("Unknown Wine", producer="Prod")]

    msg, photo_mode = _run_process_media(
        {"pdf": "base64data"},
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success", "description": "test",
                "extraction_method": "native_text", "was_truncated": False,
                "pages_processed": 1,
                "wines": [{"name": "Known"}, {"name": "Unknown Wine", "producer": "Prod"}],
            }),
            "resolve_wines_from_ocr": _mock_resolve_returning(resolved_items, unresolved_items),
            "discover_unknowns": _mock_discover_that_resolves(discovery_wine),
        },
    )

    assert photo_mode is False
    assert "Discovered Wine" in msg
    assert "Discovery Producer" in msg


def test_video_discovery_moves_item_to_resolved():
    """Video: discovery resolves unresolved item."""
    known_wine = _make_wine(id=1)
    discovery_wine = _make_wine(id=2, nome="Found Via Enrichment")

    resolved_items = [{"ocr": {"name": "Known"}, "wine": known_wine, "status": "confirmed_with_note"}]
    unresolved_items = [_make_unresolved("Mystery")]

    msg, photo_mode = _run_process_media(
        {"video": "base64data"},
        mocks={
            "process_video": _mock_process_video({
                "status": "success", "wines": [{"name": "Known"}, {"name": "Mystery"}],
                "wine_count": 2, "frames_analyzed": 3, "description": "Bottles",
            }),
            "resolve_wines_from_ocr": _mock_resolve_returning(resolved_items, unresolved_items),
            "discover_unknowns": _mock_discover_that_resolves(discovery_wine),
        },
    )

    assert photo_mode is False
    assert "Found Via Enrichment" in msg
    assert "documento" not in msg


def test_text_discovery_moves_item_to_resolved():
    """Text: discovery resolves unresolved item."""
    known_wine = _make_wine(id=1)
    discovery_wine = _make_wine(id=2, nome="Enriched Match")

    resolved_items = [{"ocr": {"name": "Known"}, "wine": known_wine, "status": "confirmed_with_note"}]
    unresolved_items = [_make_unresolved("Mystery")]

    # Mock extract_wines_from_text + resolve + discover + log
    orig_extract = chat_mod.extract_wines_from_text
    orig_resolve = chat_mod.resolve_wines_from_ocr
    orig_discover = chat_mod.discover_unknowns
    orig_auto = chat_mod.auto_create_unknowns
    orig_text_looks = chat_mod._text_looks_wine_related
    orig_log = chat_mod.log_discovery

    chat_mod.extract_wines_from_text = lambda text: {"wines": [{"name": "Known"}, {"name": "Mystery"}], "wine_count": 2, "status": "success"}
    chat_mod._text_looks_wine_related = lambda text, **kw: True
    chat_mod.resolve_wines_from_ocr = _mock_resolve_returning(resolved_items, unresolved_items)
    chat_mod.discover_unknowns = _mock_discover_that_resolves(discovery_wine)
    chat_mod.auto_create_unknowns = _noop_auto_create
    chat_mod.log_discovery = lambda *a, **kw: None

    try:
        trace = _FakeTrace()
        # Long wine-related text
        wine_text = "Carta de Vinhos tinto branco reserva malbec cabernet " * 5
        result = chat_mod._try_text_wine_extraction(wine_text, trace)
    finally:
        chat_mod.extract_wines_from_text = orig_extract
        chat_mod.resolve_wines_from_ocr = orig_resolve
        chat_mod.discover_unknowns = orig_discover
        chat_mod.auto_create_unknowns = orig_auto
        chat_mod._text_looks_wine_related = orig_text_looks
        chat_mod.log_discovery = orig_log

    assert result is not None
    msg, photo_mode = result
    assert photo_mode is False
    assert "Enriched Match" in msg
    assert "documento" not in msg
    assert "na imagem" not in msg


def test_discovery_finds_nothing_context_stays_honest():
    """When discovery finds nothing, context should still show unresolved items."""
    known_wine = _make_wine(id=1)
    resolved_items = [{"ocr": {"name": "Known"}, "wine": known_wine, "status": "confirmed_with_note"}]
    unresolved_items = [_make_unresolved("Still Unknown", producer="Prod")]

    msg, _ = _run_process_media(
        {"pdf": "base64data"},
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success", "description": "test",
                "extraction_method": "native_text", "was_truncated": False,
                "pages_processed": 1,
                "wines": [{"name": "Known"}, {"name": "Still Unknown", "producer": "Prod"}],
            }),
            "resolve_wines_from_ocr": _mock_resolve_returning(resolved_items, unresolved_items),
            "discover_unknowns": _mock_discover_that_finds_nothing(),
        },
    )

    assert "Still Unknown" in msg
    assert "Produtor: Prod" in msg  # OCR supplement preserved


def test_pdf_no_duplicate_when_discovery_resolves_same_wine():
    """PDF: if pre-resolve already has wine.id=42, discovery must NOT add it again."""
    wine_42 = _make_wine(id=42, nome="MontGras Aura Carmenere", produtor="MontGras")

    resolved_items = [{"ocr": {"name": "MontGras Aura"}, "wine": wine_42, "status": "confirmed_with_note"}]
    unresolved_items = [_make_unresolved("Pontgras Aura", producer="MontGras")]

    # Discovery mock that WOULD resolve to id=42 if not blocked
    def mock_discover_that_tries_same_id(unresolved_items, trace=None, initial_seen_ids=None):
        seen = set(initial_seen_ids) if initial_seen_ids else set()
        newly = []
        still = []
        for item in unresolved_items:
            if 42 not in seen:
                newly.append({
                    "ocr": item["ocr"], "wine": wine_42,
                    "status": "confirmed_with_note", "enriched": True,
                    "enriched_data": {"name": "MontGras Aura Carmenere"},
                })
                seen.add(42)
            else:
                still.append(item)
        return {"newly_resolved": newly, "still_unresolved": still, "stats": {}}

    msg, photo_mode = _run_process_media(
        {"pdf": "base64data"},
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success", "description": "test",
                "extraction_method": "native_text", "was_truncated": False,
                "pages_processed": 1,
                "wines": [{"name": "MontGras Aura"}, {"name": "Pontgras Aura", "producer": "MontGras"}],
            }),
            "resolve_wines_from_ocr": _mock_resolve_returning(resolved_items, unresolved_items),
            "discover_unknowns": mock_discover_that_tries_same_id,
        },
    )

    assert photo_mode is False
    # Count occurrences of the wine in the context
    count = msg.count("MontGras Aura Carmenere")
    assert count == 1, f"Wine should appear only once in context, found {count} times:\n{msg}"


# --- Runner ---

if __name__ == "__main__":
    tests = [
        # discover_unknowns core
        test_enrichment_corrects_ocr_and_resolves,
        test_enrichment_infers_producer,
        test_nonexistent_wine_stays_unresolved,
        test_enrichment_failure_keeps_unresolved,
        test_enrichment_invalid_json_keeps_unresolved,
        test_quality_gate_rejects_bad_match,
        test_budget_exceeded_stops_gracefully,
        test_cap_2_processes_first_2_only,
        test_seen_ids_prevents_duplicates,
        test_initial_seen_ids_prevents_pre_resolve_duplicates,
        test_initial_seen_ids_allows_different_wine,
        test_empty_input,
        test_item_without_name_stays_unresolved,
        # _enrich_wine
        test_enrich_wine_strips_code_fences,
        test_enrich_wine_returns_none_on_error,
        # integration
        test_pdf_discovery_moves_item_to_resolved,
        test_video_discovery_moves_item_to_resolved,
        test_text_discovery_moves_item_to_resolved,
        test_discovery_finds_nothing_context_stays_honest,
        test_pdf_no_duplicate_when_discovery_resolves_same_wine,
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
