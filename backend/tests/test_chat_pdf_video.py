"""Test chat.py PDF/video integration with resolver pre-resolve.

Runs offline (no DB, no Gemini, no Qwen): python -m tests.test_chat_pdf_video
All external calls are mocked.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routes.chat as chat_mod
from services.tracing import RequestTrace


# --- Mock helpers ---

def _mock_process_pdf(result):
    """Replace process_pdf with a function that returns a fixed result."""
    def fake_process_pdf(base64_pdf):
        return result
    return fake_process_pdf


def _mock_process_video(result):
    """Replace process_video with a function that returns a fixed result."""
    def fake_process_video(base64_video):
        return result
    return fake_process_video


def _mock_resolve_wines_from_ocr(resolved_items=None, unresolved_items=None):
    """Replace resolve_wines_from_ocr with a function that returns fixed items."""
    resolved_items = resolved_items or []
    unresolved_items = unresolved_items or []
    def fake_resolve(ocr_result):
        return {
            "resolved_wines": [it["wine"] for it in resolved_items],
            "unresolved": [it["ocr"].get("name", "?") for it in unresolved_items],
            "resolved_items": resolved_items,
            "unresolved_items": unresolved_items,
            "timing_ms": 10,
        }
    return fake_resolve


def _mock_format_resolved_context(return_text="[MOCKED CONTEXT]"):
    """Replace format_resolved_context with a function that captures args."""
    calls = []
    def fake_format(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return return_text
    return fake_format, calls


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


class _FakeTrace:
    """Minimal trace mock that supports context manager."""
    def step(self, name):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _noop_discover(unresolved_items, trace=None, initial_seen_ids=None):
    """No-op discovery mock: returns all items as still_unresolved."""
    return {
        "newly_resolved": [],
        "still_unresolved": list(unresolved_items) if unresolved_items else [],
        "stats": {},
    }


def _noop_auto_create(unresolved_items, source_channel="chat", session_id=None, initial_seen_ids=None):
    """No-op auto-create mock: returns all items as still_unresolved."""
    return {
        "newly_resolved": [],
        "still_unresolved": list(unresolved_items) if unresolved_items else [],
        "stats": {},
    }


def _run_process_media(data, message="test", mocks=None):
    """Run _process_media with mocks applied, restore after.

    Always mocks discover_unknowns to avoid DB hits, unless caller provides explicit mock.
    """
    mocks = mocks or {}
    originals = {}

    # Defaults: no-op discovery and logging to avoid DB calls
    if "discover_unknowns" not in mocks:
        mocks["discover_unknowns"] = _noop_discover
    if "auto_create_unknowns" not in mocks:
        mocks["auto_create_unknowns"] = _noop_auto_create
    if "log_discovery" not in mocks:
        mocks["log_discovery"] = lambda *a, **kw: None

    # Apply mocks
    import tools.media as media_mod
    import tools.resolver as resolver_mod
    mock_map = {
        "process_pdf": (media_mod, "process_pdf"),
        "process_video": (media_mod, "process_video"),
        "resolve_wines_from_ocr": (resolver_mod, "resolve_wines_from_ocr"),
        "format_resolved_context": (resolver_mod, "format_resolved_context"),
    }

    # Also mock the imports in chat module
    chat_mock_map = {
        "process_pdf": (chat_mod, "process_pdf"),
        "process_video": (chat_mod, "process_video"),
        "resolve_wines_from_ocr": (chat_mod, "resolve_wines_from_ocr"),
        "format_resolved_context": (chat_mod, "format_resolved_context"),
        "discover_unknowns": (chat_mod, "discover_unknowns"),
        "auto_create_unknowns": (chat_mod, "auto_create_unknowns"),
        "log_discovery": (chat_mod, "log_discovery"),
    }

    for key, fn in mocks.items():
        if key in mock_map:
            mod, attr = mock_map[key]
            originals[(mod, attr)] = getattr(mod, attr)
            setattr(mod, attr, fn)
        if key in chat_mock_map:
            mod, attr = chat_mock_map[key]
            originals[(mod, attr)] = getattr(mod, attr)
            setattr(mod, attr, fn)

    try:
        trace = _FakeTrace()
        return chat_mod._process_media(data, message, trace)
    finally:
        for (mod, attr), orig in originals.items():
            setattr(mod, attr, orig)


# ============================================================
# PDF tests
# ============================================================

def test_pdf_with_wines_calls_pre_resolve():
    """PDF with wines should call resolve_wines_from_ocr and format_resolved_context."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Alamos Malbec", "price": "R$ 89"}, "wine": wine, "status": "confirmed_with_note"}]

    fake_format, format_calls = _mock_format_resolved_context("[RICH CONTEXT]")

    msg, photo_mode = _run_process_media(
        {"pdf": "base64data"},
        message="analise esta carta",
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success",
                "description": "3 wines found",
                "extraction_method": "native_text",
                "was_truncated": False,
                "pages_processed": 2,
                "wines": [{"name": "Alamos Malbec", "price": "R$ 89"}],
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(
                resolved_items=resolved_items,
            ),
            "format_resolved_context": fake_format,
        },
    )

    # format_resolved_context was called
    assert len(format_calls) == 1, f"Expected 1 format call, got {len(format_calls)}"

    # Verify args
    call = format_calls[0]
    assert call["kwargs"].get("header_override") is not None
    assert "native_text" in call["kwargs"]["header_override"] or "paginas" in call["kwargs"]["header_override"]
    assert call["kwargs"].get("ocr_label") == "no PDF"
    assert call["args"][2] == "pdf"  # image_type

    # photo_mode is False for PDF
    assert photo_mode is False

    # Context includes rich context + pdf rules
    assert "[RICH CONTEXT]" in msg
    assert "REGRAS CRITICAS DESTE PDF" in msg
    assert "FONTE UNICA DA CARTA" in msg


def test_pdf_preserves_source_note():
    """PDF pre-resolve should include source_note in header_override."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Test"}, "wine": wine, "status": "confirmed_with_note"}]
    fake_format, format_calls = _mock_format_resolved_context()

    _run_process_media(
        {"pdf": "base64data"},
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success",
                "description": "test",
                "extraction_method": "visual_fallback",
                "was_truncated": False,
                "pages_processed": 3,
                "wines": [{"name": "Test"}],
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(resolved_items=resolved_items),
            "format_resolved_context": fake_format,
        },
    )

    header = format_calls[0]["kwargs"]["header_override"]
    assert "leitura visual por OCR" in header
    assert "3 paginas" in header


def test_pdf_preserves_truncation_note():
    """PDF pre-resolve should include truncation warning in header_override."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Test"}, "wine": wine, "status": "confirmed_with_note"}]
    fake_format, format_calls = _mock_format_resolved_context()

    _run_process_media(
        {"pdf": "base64data"},
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success",
                "description": "test",
                "extraction_method": "native_text",
                "was_truncated": True,
                "pages_processed": 5,
                "wines": [{"name": "Test"}],
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(resolved_items=resolved_items),
            "format_resolved_context": fake_format,
        },
    )

    header = format_calls[0]["kwargs"]["header_override"]
    assert "truncado" in header


def test_pdf_fallback_preserves_original_rules():
    """PDF with 0 wines from resolver should use original 5-rule fallback."""
    msg, photo_mode = _run_process_media(
        {"pdf": "base64data"},
        message="analise",
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success",
                "description": "Wine list content here",
                "extraction_method": "native_text",
                "was_truncated": False,
                "pages_processed": 2,
                "wines": [],  # no wines extracted
            }),
        },
    )

    assert photo_mode is False
    # All 5 original rules present
    assert "FONTE UNICA DA CARTA" in msg
    assert "USO CORRETO DO search_wine" in msg
    assert "IDENTIDADE DO ITEM" in msg
    assert "RANKING DA CARTA" in msg
    assert "HONESTIDADE" in msg
    assert "Wine list content here" in msg


def test_pdf_photo_mode_always_false():
    """PDF should always return photo_mode=False, even with resolved items."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Test"}, "wine": wine, "status": "confirmed_with_note"}]

    _, photo_mode = _run_process_media(
        {"pdf": "base64data"},
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success",
                "description": "test",
                "extraction_method": "native_text",
                "was_truncated": False,
                "pages_processed": 1,
                "wines": [{"name": "Test"}],
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(resolved_items=resolved_items),
            "format_resolved_context": _mock_format_resolved_context()[0],
        },
    )

    assert photo_mode is False


def test_pdf_error_preserves_error_message():
    """PDF processing error should preserve error message."""
    msg, photo_mode = _run_process_media(
        {"pdf": "base64data"},
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "error",
                "message": "PDF muito grande",
            }),
        },
    )

    assert photo_mode is False
    assert "PDF muito grande" in msg


# ============================================================
# Video tests
# ============================================================

def test_video_with_wines_calls_pre_resolve():
    """Video with wines should call resolve and format_resolved_context."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Malbec"}, "wine": wine, "status": "confirmed_with_note"}]
    fake_format, format_calls = _mock_format_resolved_context("[VIDEO CONTEXT]")

    msg, photo_mode = _run_process_media(
        {"video": "base64data"},
        message="o que tem nesse video",
        mocks={
            "process_video": _mock_process_video({
                "status": "success",
                "wines": [{"name": "Malbec"}],
                "wine_count": 1,
                "frames_analyzed": 5,
                "description": "Bottle of Malbec on table",
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(resolved_items=resolved_items),
            "format_resolved_context": fake_format,
        },
    )

    assert len(format_calls) == 1
    call = format_calls[0]
    assert call["kwargs"].get("ocr_label") == "no video"
    assert "frames" in call["kwargs"]["header_override"]
    assert call["args"][2] == "video"  # image_type

    assert photo_mode is False
    assert "[VIDEO CONTEXT]" in msg
    assert "search_wine UMA VEZ" in msg


def test_video_photo_mode_always_false():
    """Video should always return photo_mode=False."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Test"}, "wine": wine, "status": "confirmed_with_note"}]

    _, photo_mode = _run_process_media(
        {"video": "base64data"},
        mocks={
            "process_video": _mock_process_video({
                "status": "success",
                "wines": [{"name": "Test"}],
                "wine_count": 1,
                "frames_analyzed": 3,
                "description": "Wine",
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(resolved_items=resolved_items),
            "format_resolved_context": _mock_format_resolved_context()[0],
        },
    )

    assert photo_mode is False


def test_video_fallback_when_no_wines():
    """Video with no wines from resolver should use original fallback."""
    msg, photo_mode = _run_process_media(
        {"video": "base64data"},
        mocks={
            "process_video": _mock_process_video({
                "status": "success",
                "wines": [],
                "wine_count": 0,
                "frames_analyzed": 3,
                "description": "Some bottles visible",
            }),
        },
    )

    assert photo_mode is False
    assert "Some bottles visible" in msg
    assert "Use search_wine" in msg


def test_video_error_preserves_error_message():
    """Video processing error should preserve error message."""
    msg, photo_mode = _run_process_media(
        {"video": "base64data"},
        mocks={
            "process_video": _mock_process_video({
                "status": "error",
                "message": "Video muito longo",
            }),
        },
    )

    assert photo_mode is False
    assert "Video muito longo" in msg


# ============================================================
# Video wording: no "documento" anywhere
# ============================================================

def test_video_rich_path_no_documento():
    """Video rich path must NOT contain the word 'documento' anywhere."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Unknown", "producer": "Prod", "price": "R$ 50"}, "status": "visual_only"}]

    # Use REAL format_resolved_context (not mock) to verify actual wording
    msg, photo_mode = _run_process_media(
        {"video": "base64data"},
        message="analise",
        mocks={
            "process_video": _mock_process_video({
                "status": "success",
                "wines": [{"name": "Known"}, {"name": "Unknown", "producer": "Prod", "price": "R$ 50"}],
                "wine_count": 2,
                "frames_analyzed": 5,
                "description": "Wine bottles",
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(
                resolved_items=resolved_items,
                unresolved_items=unresolved_items,
            ),
            # NOT mocking format_resolved_context — use real one
        },
    )

    assert photo_mode is False
    assert "documento" not in msg, f"Video context must not say 'documento'. Got:\n{msg}"


def test_video_rich_path_has_video_wording():
    """Video rich path should have consistent video wording throughout."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Unknown", "price": "R$ 50"}, "status": "visual_only"}]

    msg, _ = _run_process_media(
        {"video": "base64data"},
        message="analise",
        mocks={
            "process_video": _mock_process_video({
                "status": "success",
                "wines": [{"name": "Known"}, {"name": "Unknown"}],
                "wine_count": 2,
                "frames_analyzed": 5,
                "description": "Wine bottles",
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(
                resolved_items=resolved_items,
                unresolved_items=unresolved_items,
            ),
        },
    )

    # Summary line
    assert "no video" in msg
    # Unresolved section
    assert "identificados no video" in msg
    # Rule
    assert "preco do video" in msg


def test_pdf_rich_path_still_has_documento():
    """PDF rich path should still use 'documento' wording (not broken by video fix)."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Unknown", "price": "R$ 50"}, "status": "visual_only"}]

    msg, _ = _run_process_media(
        {"pdf": "base64data"},
        message="analise",
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success",
                "description": "test",
                "extraction_method": "native_text",
                "was_truncated": False,
                "pages_processed": 1,
                "wines": [{"name": "Known"}, {"name": "Unknown"}],
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(
                resolved_items=resolved_items,
                unresolved_items=unresolved_items,
            ),
        },
    )

    assert "no documento" in msg
    assert "identificados no documento" in msg


# ============================================================
# OCR supplement for unresolved items
# ============================================================

def test_pdf_unresolved_preserves_producer():
    """PDF rich path with unresolved item containing producer should include it."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known Wine"}, "wine": wine, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Reserva Especial", "producer": "Frescobaldi", "price": "R$ 100"}, "status": "visual_only"}]

    msg, photo_mode = _run_process_media(
        {"pdf": "base64data"},
        message="analise",
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success",
                "description": "test",
                "extraction_method": "native_text",
                "was_truncated": False,
                "pages_processed": 1,
                "wines": [{"name": "Known Wine"}, {"name": "Reserva Especial", "producer": "Frescobaldi", "price": "R$ 100"}],
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(
                resolved_items=resolved_items,
                unresolved_items=unresolved_items,
            ),
            "format_resolved_context": _mock_format_resolved_context("[RICH]")[0],
        },
    )

    assert photo_mode is False
    assert "Frescobaldi" in msg
    assert "Reserva Especial" in msg
    assert "Produtor: Frescobaldi" in msg


def test_pdf_unresolved_preserves_all_fields():
    """PDF rich path should preserve vintage, region, grape, price for unresolved."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]
    unresolved_items = [{
        "ocr": {
            "name": "Brunello di Montalcino",
            "producer": "Frescobaldi",
            "vintage": "2018",
            "region": "Toscana",
            "grape": "Sangiovese",
            "price": "R$ 450",
        },
        "status": "visual_only",
    }]

    msg, _ = _run_process_media(
        {"pdf": "base64data"},
        message="analise",
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success",
                "description": "test",
                "extraction_method": "native_text",
                "was_truncated": False,
                "pages_processed": 1,
                "wines": [{"name": "Known"}, {"name": "Brunello di Montalcino"}],
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(
                resolved_items=resolved_items,
                unresolved_items=unresolved_items,
            ),
            "format_resolved_context": _mock_format_resolved_context("[RICH]")[0],
        },
    )

    assert "Produtor: Frescobaldi" in msg
    assert "Safra: 2018" in msg
    assert "Regiao: Toscana" in msg
    assert "Uva: Sangiovese" in msg
    assert "Preco: R$ 450" in msg


def test_video_unresolved_preserves_producer():
    """Video rich path with unresolved item containing producer should include it."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Mystery Wine", "producer": "Bodega Catena"}, "status": "visual_only"}]

    msg, photo_mode = _run_process_media(
        {"video": "base64data"},
        message="analise",
        mocks={
            "process_video": _mock_process_video({
                "status": "success",
                "wines": [{"name": "Known"}, {"name": "Mystery Wine", "producer": "Bodega Catena"}],
                "wine_count": 2,
                "frames_analyzed": 3,
                "description": "Wine bottles",
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(
                resolved_items=resolved_items,
                unresolved_items=unresolved_items,
            ),
            "format_resolved_context": _mock_format_resolved_context("[VIDEO]")[0],
        },
    )

    assert photo_mode is False
    assert "Bodega Catena" in msg
    assert "Produtor: Bodega Catena" in msg


def test_pdf_no_unresolved_no_supplement():
    """PDF with all resolved should NOT add OCR supplement section."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known", "producer": "Test"}, "wine": wine, "status": "confirmed_with_note"}]

    msg, _ = _run_process_media(
        {"pdf": "base64data"},
        message="analise",
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success",
                "description": "test",
                "extraction_method": "native_text",
                "was_truncated": False,
                "pages_processed": 1,
                "wines": [{"name": "Known"}],
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(
                resolved_items=resolved_items,
                unresolved_items=[],
            ),
            "format_resolved_context": _mock_format_resolved_context("[RICH]")[0],
        },
    )

    assert "Detalhes extraidos dos nao encontrados" not in msg


def test_unresolved_without_extra_fields_no_supplement():
    """Unresolved items with only name (no producer/vintage/etc) should not add supplement."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Unknown Wine"}, "status": "visual_only"}]

    msg, _ = _run_process_media(
        {"pdf": "base64data"},
        message="analise",
        mocks={
            "process_pdf": _mock_process_pdf({
                "status": "success",
                "description": "test",
                "extraction_method": "native_text",
                "was_truncated": False,
                "pages_processed": 1,
                "wines": [{"name": "Known"}, {"name": "Unknown Wine"}],
            }),
            "resolve_wines_from_ocr": _mock_resolve_wines_from_ocr(
                resolved_items=resolved_items,
                unresolved_items=unresolved_items,
            ),
            "format_resolved_context": _mock_format_resolved_context("[RICH]")[0],
        },
    )

    # No extra fields → no supplement
    assert "Detalhes extraidos dos nao encontrados" not in msg


# ============================================================
# _format_unresolved_ocr_details unit tests
# ============================================================

def test_format_unresolved_ocr_details_basic():
    """Helper should format producer/vintage/region/grape/price."""
    items = [{"ocr": {"name": "Wine A", "producer": "Prod A", "vintage": "2020", "price": "R$ 50"}, "status": "visual_only"}]
    result = chat_mod._format_unresolved_ocr_details(items)
    assert result is not None
    assert "Wine A" in result
    assert "Produtor: Prod A" in result
    assert "Safra: 2020" in result
    assert "Preco: R$ 50" in result


def test_format_unresolved_ocr_details_empty():
    """Helper should return None for empty list."""
    assert chat_mod._format_unresolved_ocr_details([]) is None
    assert chat_mod._format_unresolved_ocr_details(None) is None


def test_format_unresolved_ocr_details_no_extras():
    """Helper should return None when items have no extra fields."""
    items = [{"ocr": {"name": "Wine A"}, "status": "visual_only"}]
    assert chat_mod._format_unresolved_ocr_details(items) is None


# ============================================================
# Image flow unchanged
# ============================================================

def test_image_flow_unchanged():
    """Single image should still go through _process_single_image, not PDF path."""
    # We verify by checking that process_pdf is NOT called
    pdf_called = [False]

    def spy_process_pdf(base64_pdf):
        pdf_called[0] = True
        return {"status": "error"}

    # _process_single_image calls process_image which needs mocking
    import tools.media as media_mod
    orig_process_image = media_mod.process_image
    orig_resolve = chat_mod.resolve_wines_from_ocr

    def mock_process_image(base64_image):
        return {"image_type": "not_wine", "message": "Not a wine photo"}

    media_mod.process_image = mock_process_image
    chat_mod.process_image = mock_process_image
    chat_mod.process_pdf = spy_process_pdf
    try:
        trace = _FakeTrace()
        msg, photo_mode = chat_mod._process_media({"image": "base64img"}, "test", trace)
        assert not pdf_called[0], "process_pdf should NOT be called for images"
        assert photo_mode is False  # not_wine returns False
    finally:
        media_mod.process_image = orig_process_image
        chat_mod.process_image = orig_process_image
        chat_mod.process_pdf = chat_mod.__spec__ and None  # will be restored below
        # Restore by re-importing
        from tools.media import process_pdf as orig_pdf
        chat_mod.process_pdf = orig_pdf


# ============================================================
# _resolve_wine_list unit test
# ============================================================

def test_resolve_wine_list_uses_pdf_type():
    """_resolve_wine_list should pass image_type='pdf' to resolver."""
    import tools.resolver as resolver_mod
    orig = resolver_mod.resolve_wines_from_ocr
    captured = []

    def spy_resolve(ocr_result):
        captured.append(ocr_result)
        return {"resolved_wines": [], "unresolved": [], "resolved_items": [], "unresolved_items": [], "timing_ms": 0}

    resolver_mod.resolve_wines_from_ocr = spy_resolve
    # Also patch the import in chat_mod
    chat_orig = chat_mod.resolve_wines_from_ocr
    chat_mod.resolve_wines_from_ocr = spy_resolve
    try:
        chat_mod._resolve_wine_list([{"name": "Test Wine"}])
        assert len(captured) == 1
        assert captured[0]["image_type"] == "pdf"
        assert len(captured[0]["wines"]) == 1
    finally:
        resolver_mod.resolve_wines_from_ocr = orig
        chat_mod.resolve_wines_from_ocr = chat_orig


def test_resolve_wine_list_empty():
    """_resolve_wine_list with empty list should return None."""
    result = chat_mod._resolve_wine_list([])
    assert result is None

    result = chat_mod._resolve_wine_list(None)
    assert result is None


# --- Runner ---

if __name__ == "__main__":
    tests = [
        test_pdf_with_wines_calls_pre_resolve,
        test_pdf_preserves_source_note,
        test_pdf_preserves_truncation_note,
        test_pdf_fallback_preserves_original_rules,
        test_pdf_photo_mode_always_false,
        test_pdf_error_preserves_error_message,
        test_video_with_wines_calls_pre_resolve,
        test_video_photo_mode_always_false,
        test_video_fallback_when_no_wines,
        test_video_error_preserves_error_message,
        test_video_rich_path_no_documento,
        test_video_rich_path_has_video_wording,
        test_pdf_rich_path_still_has_documento,
        test_pdf_unresolved_preserves_producer,
        test_pdf_unresolved_preserves_all_fields,
        test_video_unresolved_preserves_producer,
        test_pdf_no_unresolved_no_supplement,
        test_unresolved_without_extra_fields_no_supplement,
        test_format_unresolved_ocr_details_basic,
        test_format_unresolved_ocr_details_empty,
        test_format_unresolved_ocr_details_no_extras,
        test_image_flow_unchanged,
        test_resolve_wine_list_uses_pdf_type,
        test_resolve_wine_list_empty,
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
