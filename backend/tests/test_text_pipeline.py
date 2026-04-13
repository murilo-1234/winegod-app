"""Test Fase 1: text wine extraction pipeline.

Runs offline (no DB, no Gemini, no Qwen): python -m tests.test_text_pipeline
Tests extract_wines_from_text, _try_text_wine_extraction, and integration.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.media as media_mod
import routes.chat as chat_mod
from tools.media import extract_wines_from_text, _text_looks_wine_related


# --- Mock helpers ---

class _FakeTrace:
    def step(self, name):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


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


# ============================================================
# 1. extract_wines_from_text unit tests
# ============================================================

def test_extract_too_short():
    """Text shorter than 20 chars should return too_short."""
    assert extract_wines_from_text("")["status"] == "too_short"
    assert extract_wines_from_text(None)["status"] == "too_short"
    assert extract_wines_from_text("short")["status"] == "too_short"
    assert extract_wines_from_text("a" * 19)["status"] == "too_short"


def test_extract_monolithic_path():
    """Medium wine-related text should use monolithic Qwen/Gemini path and deduplicate."""
    orig_qwen = media_mod._qwen_text_generate
    orig_gemini = media_mod._gemini_generate

    def mock_qwen(prompt):
        return '{"wines": [{"name": "Alamos Malbec", "price": "R$ 89"}, {"name": "alamos malbec", "price": null}]}'

    media_mod._qwen_text_generate = mock_qwen
    try:
        result = extract_wines_from_text(
            "Carta de Vinhos\nTintos\nAlamos Malbec 2020 R$ 89\nAlamos Malbec reserva"
        )
        assert result["status"] == "success"
        assert result["wine_count"] == 1, f"Expected 1 after dedup, got {result['wine_count']}"
        assert result["wines"][0]["name"] == "Alamos Malbec"
    finally:
        media_mod._qwen_text_generate = orig_qwen
        media_mod._gemini_generate = orig_gemini


def test_extract_gemini_fallback():
    """When Qwen returns None, should fallback to Gemini."""
    orig_qwen = media_mod._qwen_text_generate
    orig_gemini = media_mod._gemini_generate

    def mock_qwen(prompt):
        return None  # Qwen unavailable

    def mock_gemini(contents, **kwargs):
        return '{"wines": [{"name": "Casillero Cabernet"}]}'

    media_mod._qwen_text_generate = mock_qwen
    media_mod._gemini_generate = mock_gemini
    try:
        result = extract_wines_from_text(
            "Carta de vinhos do restaurante reserva malbec cabernet tinto"
        )
        assert result["status"] == "success"
        assert result["wines"][0]["name"] == "Casillero Cabernet"
    finally:
        media_mod._qwen_text_generate = orig_qwen
        media_mod._gemini_generate = orig_gemini


def test_extract_no_wines():
    """Text that parses but has no wines should return no_wines."""
    orig_qwen = media_mod._qwen_text_generate

    def mock_qwen(prompt):
        return '{"wines": []}'

    media_mod._qwen_text_generate = mock_qwen
    try:
        result = extract_wines_from_text(
            "Carta de vinhos do restaurante com reserva malbec cabernet description"
        )
        assert result["status"] == "no_wines"
        assert result["wines"] == []
    finally:
        media_mod._qwen_text_generate = orig_qwen


def test_extract_long_text_uses_chunked():
    """Text longer than _LONG_TEXT_THRESHOLD and wine-related should use chunked path."""
    orig_chunked = media_mod._extract_wines_native_chunked
    chunked_called = [False]

    def mock_chunked(text, **kwargs):
        chunked_called[0] = True
        return [{"name": "Wine A"}, {"name": "Wine B"}]

    media_mod._extract_wines_native_chunked = mock_chunked
    try:
        # Build long wine-related text
        wine_para = "Vinho tinto Alamos Malbec 2020 Cabernet Sauvignon Argentina R$ 89,00"
        long_text = "\n\n".join([wine_para] * 250)
        assert len(long_text) > media_mod._LONG_TEXT_THRESHOLD

        result = extract_wines_from_text(long_text)
        assert chunked_called[0], "Should use chunked path for long text"
        assert result["status"] == "success"
        assert result["wine_count"] == 2
    finally:
        media_mod._extract_wines_native_chunked = orig_chunked


def test_extract_error_handling():
    """Exceptions should be caught and return error status."""
    orig_qwen = media_mod._qwen_text_generate

    def mock_qwen(prompt):
        raise RuntimeError("API down")

    media_mod._qwen_text_generate = mock_qwen
    try:
        result = extract_wines_from_text(
            "Carta de vinhos com reserva malbec cabernet tinto branco espumante"
        )
        assert result["status"] == "error"
        assert result["wines"] == []
    finally:
        media_mod._qwen_text_generate = orig_qwen


# ============================================================
# 2. qwen_text_generate wrapper
# ============================================================

def test_qwen_text_generate_wrapper():
    """Public wrapper should call the private function."""
    from tools.media import qwen_text_generate
    orig = media_mod._qwen_text_generate
    called = [False]

    def mock(prompt):
        called[0] = True
        return "result"

    media_mod._qwen_text_generate = mock
    try:
        result = qwen_text_generate("test prompt")
        assert called[0]
        assert result == "result"
    finally:
        media_mod._qwen_text_generate = orig


# ============================================================
# 3. _try_text_wine_extraction helper
# ============================================================

def _mock_extract_wines(wines):
    def fake(text):
        if wines:
            return {"wines": wines, "wine_count": len(wines), "status": "success"}
        return {"wines": [], "wine_count": 0, "status": "no_wines"}
    return fake


def _mock_resolve(resolved_items=None, unresolved_items=None):
    resolved_items = resolved_items or []
    unresolved_items = unresolved_items or []
    def fake(ocr_result):
        return {
            "resolved_wines": [it["wine"] for it in resolved_items],
            "unresolved": [it["ocr"].get("name", "?") for it in unresolved_items],
            "resolved_items": resolved_items,
            "unresolved_items": unresolved_items,
            "timing_ms": 10,
        }
    return fake


def _noop_discover(unresolved_items, trace=None, initial_seen_ids=None):
    """No-op discovery mock: returns all items as still_unresolved."""
    return {
        "newly_resolved": [],
        "still_unresolved": list(unresolved_items) if unresolved_items else [],
        "stats": {},
    }


def _noop_auto_create(unresolved_items, source_channel="chat", session_id=None, initial_seen_ids=None):
    return {
        "newly_resolved": [],
        "still_unresolved": list(unresolved_items) if unresolved_items else [],
        "stats": {},
    }


def _run_try_text(message, extract_mock=None, resolve_mock=None, discover_mock=None):
    """Run _try_text_wine_extraction with mocks."""
    originals = {}

    if extract_mock:
        originals["extract"] = (chat_mod, "extract_wines_from_text", getattr(chat_mod, "extract_wines_from_text"))
        chat_mod.extract_wines_from_text = extract_mock
    if resolve_mock:
        originals["resolve"] = (chat_mod, "resolve_wines_from_ocr", getattr(chat_mod, "resolve_wines_from_ocr"))
        chat_mod.resolve_wines_from_ocr = resolve_mock
    # Always mock discovery and logging to avoid DB hits
    dm = discover_mock or _noop_discover
    originals["discover"] = (chat_mod, "discover_unknowns", getattr(chat_mod, "discover_unknowns"))
    chat_mod.discover_unknowns = dm
    originals["auto"] = (chat_mod, "auto_create_unknowns", getattr(chat_mod, "auto_create_unknowns"))
    chat_mod.auto_create_unknowns = _noop_auto_create
    originals["log"] = (chat_mod, "log_discovery", getattr(chat_mod, "log_discovery"))
    chat_mod.log_discovery = lambda *a, **kw: None

    try:
        return chat_mod._try_text_wine_extraction(message, _FakeTrace())
    finally:
        for key, (mod, attr, orig) in originals.items():
            setattr(mod, attr, orig)


def test_try_text_short_message_skips():
    """Messages <= 150 chars should return None (skip)."""
    result = _run_try_text("qual o melhor malbec?")
    assert result is None


def test_try_text_non_wine_skips():
    """Non-wine text should return None (skip)."""
    long_non_wine = "O " * 100 + "restaurante tem boa comida e ambiente agradavel " * 3
    assert len(long_non_wine) > 150
    result = _run_try_text(long_non_wine)
    assert result is None


def test_try_text_wine_list_resolves():
    """Wine list text should extract, resolve, and return rich context."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Alamos Malbec"}, "wine": wine, "status": "confirmed_with_note"}]

    wines = [{"name": "Alamos Malbec", "price": "R$ 89"}]
    # Text must be >150 chars and wine-related (3+ keywords)
    wine_text = (
        "Carta de Vinhos do Restaurante\nTintos\n"
        "Alamos Malbec 2020 Mendoza Argentina R$ 89,00\n"
        "Casillero del Diablo Cabernet Sauvignon Reserva 2019 Chile R$ 65,00\n"
        "Marques de Casa Concha Merlot 2018 Valle del Maipo R$ 120,00\n"
    )
    assert len(wine_text) > 150, f"Test text must be >150 chars, got {len(wine_text)}"
    result = _run_try_text(
        wine_text,
        extract_mock=_mock_extract_wines(wines),
        resolve_mock=_mock_resolve(resolved_items=resolved_items),
    )

    assert result is not None
    msg, photo_mode = result
    assert photo_mode is False
    assert "vinhos extraidos" in msg


def test_try_text_photo_mode_false():
    """Text extraction should always return photo_mode=False."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Test"}, "wine": wine, "status": "confirmed_with_note"}]
    wines = [{"name": "Test"}]

    result = _run_try_text(
        "Carta de Vinhos tinto branco reserva malbec cabernet " * 5,
        extract_mock=_mock_extract_wines(wines),
        resolve_mock=_mock_resolve(resolved_items=resolved_items),
    )

    assert result is not None
    _, photo_mode = result
    assert photo_mode is False


# ============================================================
# 4. Text wording: no "documento", no "na imagem"
# ============================================================

def test_text_rich_path_no_documento():
    """Text rich path must NOT contain 'documento'."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Unknown", "producer": "Prod", "price": "R$ 50"}, "status": "visual_only"}]

    wines = [{"name": "Known"}, {"name": "Unknown", "producer": "Prod", "price": "R$ 50"}]

    result = _run_try_text(
        "Carta de Vinhos tinto branco reserva malbec cabernet " * 5,
        extract_mock=_mock_extract_wines(wines),
        resolve_mock=_mock_resolve(resolved_items=resolved_items, unresolved_items=unresolved_items),
    )

    assert result is not None
    msg, _ = result
    assert "documento" not in msg, f"Text context must not say 'documento'. Got:\n{msg}"


def test_text_rich_path_no_na_imagem():
    """Text rich path must NOT contain 'na imagem'."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known", "price": "R$ 80"}, "wine": wine, "status": "confirmed_with_note"}]

    wines = [{"name": "Known", "price": "R$ 80"}]

    result = _run_try_text(
        "Carta de Vinhos tinto branco reserva malbec cabernet " * 5,
        extract_mock=_mock_extract_wines(wines),
        resolve_mock=_mock_resolve(resolved_items=resolved_items),
    )

    assert result is not None
    msg, _ = result
    assert "na imagem" not in msg, f"Text context must not say 'na imagem'. Got:\n{msg}"


def test_text_rich_path_has_text_wording():
    """Text rich path should have consistent text wording."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Unknown", "price": "R$ 50"}, "status": "visual_only"}]

    wines = [{"name": "Known"}, {"name": "Unknown"}]

    result = _run_try_text(
        "Carta de Vinhos tinto branco reserva malbec cabernet " * 5,
        extract_mock=_mock_extract_wines(wines),
        resolve_mock=_mock_resolve(resolved_items=resolved_items, unresolved_items=unresolved_items),
    )

    msg, _ = result
    # Summary
    assert "no texto" in msg
    # Unresolved section
    assert "identificados no texto" in msg
    # Rule
    assert "preco do texto" in msg
    # Item labels
    assert "Lido no texto:" in msg


# ============================================================
# 5. Unresolved supplement preserves fields
# ============================================================

def test_text_unresolved_preserves_producer():
    """Text rich path should preserve producer in unresolved supplement."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Reserva Especial", "producer": "Frescobaldi", "price": "R$ 100"}, "status": "visual_only"}]

    wines = [{"name": "Known"}, {"name": "Reserva Especial", "producer": "Frescobaldi", "price": "R$ 100"}]

    result = _run_try_text(
        "Carta de Vinhos tinto branco reserva malbec cabernet " * 5,
        extract_mock=_mock_extract_wines(wines),
        resolve_mock=_mock_resolve(resolved_items=resolved_items, unresolved_items=unresolved_items),
    )

    msg, _ = result
    assert "Produtor: Frescobaldi" in msg


# ============================================================
# 6. Integration in chat() and chat_stream()
# ============================================================

def test_chat_calls_text_extraction():
    """chat() should call _try_text_wine_extraction when has_media=False."""
    called = [False]
    orig = chat_mod._try_text_wine_extraction

    def spy(message, trace):
        called[0] = True
        return None  # Don't change flow, just verify it's called

    chat_mod._try_text_wine_extraction = spy
    try:
        # We can't easily call chat() without Flask context,
        # so we verify the function exists and is callable from the module
        assert hasattr(chat_mod, '_try_text_wine_extraction')
        assert callable(chat_mod._try_text_wine_extraction)
        # Verify it's wired in the source code
        import inspect
        source = inspect.getsource(chat_mod.chat)
        assert "_try_text_wine_extraction" in source, "chat() should call _try_text_wine_extraction"
    finally:
        chat_mod._try_text_wine_extraction = orig


def test_chat_stream_calls_text_extraction():
    """chat_stream() should call _try_text_wine_extraction when has_media=False."""
    import inspect
    source = inspect.getsource(chat_mod.chat_stream)
    assert "_try_text_wine_extraction" in source, "chat_stream() should call _try_text_wine_extraction"


# --- Runner ---

if __name__ == "__main__":
    tests = [
        # extract_wines_from_text
        test_extract_too_short,
        test_extract_monolithic_path,
        test_extract_gemini_fallback,
        test_extract_no_wines,
        test_extract_long_text_uses_chunked,
        test_extract_error_handling,
        # wrapper
        test_qwen_text_generate_wrapper,
        # _try_text_wine_extraction
        test_try_text_short_message_skips,
        test_try_text_non_wine_skips,
        test_try_text_wine_list_resolves,
        test_try_text_photo_mode_false,
        # wording
        test_text_rich_path_no_documento,
        test_text_rich_path_no_na_imagem,
        test_text_rich_path_has_text_wording,
        # unresolved supplement
        test_text_unresolved_preserves_producer,
        # integration
        test_chat_calls_text_extraction,
        test_chat_stream_calls_text_extraction,
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
