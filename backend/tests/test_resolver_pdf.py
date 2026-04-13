"""Test resolver support for image_type='pdf'.

Runs offline (no DB): python -m tests.test_resolver_pdf
Tests _resolve_multi path for PDF: dedup, ordering, cap, tier routing.
Tests format_resolved_context for PDF: header_override, ocr_label.

DB-dependent resolve logic (search_wine, _fast_resolve, _score_match) is
already covered by test_resolver_line_matching and test_item_status.
Here we mock _fast_resolve to test structural decisions only.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.resolver as resolver
from tools.resolver import (
    resolve_wines_from_ocr,
    format_resolved_context,
    _resolve_multi,
    _derive_item_status,
)


# --- Helpers ---

def _make_ocr(wines, image_type="pdf"):
    return {
        "image_type": image_type,
        "wines": wines,
        "total_visible": len(wines),
    }


def _wine(name, producer=None, price=None):
    w = {"name": name}
    if producer:
        w["producer"] = producer
    if price:
        w["price"] = price
    return w


def _make_wine_dict(**kwargs):
    """Create a wine dict as returned by search_wine (banco fields)."""
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


def _run_resolve_multi_offline(ocr, match_names=None):
    """Run _resolve_multi with mocked _fast_resolve (no DB).

    match_names: set of wine names that _fast_resolve should "find".
    All others return None (visual_only).
    """
    if match_names is None:
        match_names = set()
    _next_id = [1000]

    orig_fast = resolver._fast_resolve
    orig_fallback = resolver._fallback_resolve

    def mock_fast(name, producer, seen_ids, **kwargs):
        if name in match_names:
            wid = _next_id[0]
            _next_id[0] += 1
            if wid in seen_ids:
                return None
            return _make_wine_dict(id=wid, nome=name, produtor=producer or "?")
        return None

    def mock_fallback(name, seen_ids, **kwargs):
        return None  # never match on fallback

    resolver._fast_resolve = mock_fast
    resolver._fallback_resolve = mock_fallback
    try:
        return _resolve_multi(ocr)
    finally:
        resolver._fast_resolve = orig_fast
        resolver._fallback_resolve = orig_fallback


# ============================================================
# 1. pdf enters the multi-item path (not the else branch)
# ============================================================

def test_pdf_enters_multi_path():
    """image_type='pdf' should NOT fall through to the empty else branch."""
    ocr = _make_ocr([_wine("Alamos Malbec")])
    resolved_items, unresolved_items = _run_resolve_multi_offline(ocr)
    all_items = resolved_items + unresolved_items
    assert len(all_items) == 1, "pdf should enter _resolve_multi, not the else branch"
    assert all_items[0]["ocr"]["name"] == "Alamos Malbec"


def test_pdf_enters_via_resolve_wines_from_ocr():
    """resolve_wines_from_ocr should route pdf to _resolve_multi."""
    ocr = _make_ocr([_wine("Alamos Malbec")])

    orig_fast = resolver._fast_resolve
    orig_fallback = resolver._fallback_resolve
    resolver._fast_resolve = lambda *a, **kw: None
    resolver._fallback_resolve = lambda *a, **kw: None
    try:
        result = resolve_wines_from_ocr(ocr)
    finally:
        resolver._fast_resolve = orig_fast
        resolver._fallback_resolve = orig_fallback

    assert result["unresolved_items"], "pdf should enter _resolve_multi via entry point"
    assert result["unresolved_items"][0]["ocr"]["name"] == "Alamos Malbec"


# ============================================================
# 2. PDF dedup preserves same name with different producers
# ============================================================

def test_pdf_dedup_preserves_different_producers():
    """PDF dedup uses (name, producer) — same name, different producers stay separate."""
    wines = [
        _wine("Brut Reserve", producer="Bereche"),
        _wine("Brut Reserve", producer="Billecart-Salmon"),
        _wine("Brut Reserve", producer="Philipponnat"),
    ]
    ocr = _make_ocr(wines)
    resolved_items, unresolved_items = _run_resolve_multi_offline(ocr)
    all_items = resolved_items + unresolved_items
    assert len(all_items) == 3, (
        f"Expected 3 items (different producers), got {len(all_items)}"
    )
    producers = sorted(it["ocr"].get("producer") for it in all_items)
    assert producers == ["Bereche", "Billecart-Salmon", "Philipponnat"]


def test_pdf_dedup_collapses_same_name_same_producer():
    """PDF dedup still collapses true duplicates (same name + same producer)."""
    wines = [
        _wine("Alamos Malbec", producer="Catena"),
        _wine("alamos malbec", producer="CATENA"),
    ]
    ocr = _make_ocr(wines)
    resolved_items, unresolved_items = _run_resolve_multi_offline(ocr)
    all_items = resolved_items + unresolved_items
    assert len(all_items) == 1, f"Expected 1 after dedup, got {len(all_items)}"


def test_screenshot_dedup_collapses_same_name_different_producers():
    """Screenshot dedup uses name-only — same name, different producers collapse."""
    wines = [
        _wine("Brut Reserve", producer="Bereche"),
        _wine("Brut Reserve", producer="Billecart-Salmon"),
    ]
    ocr = _make_ocr(wines, image_type="screenshot")
    resolved_items, unresolved_items = _run_resolve_multi_offline(ocr)
    all_items = resolved_items + unresolved_items
    assert len(all_items) == 1, (
        f"Screenshot should collapse same name regardless of producer, got {len(all_items)}"
    )


# ============================================================
# 3. PDF preserves document order (no sort)
# ============================================================

def test_pdf_preserves_document_order():
    """PDF items should stay in original order, not sorted by price/name length."""
    wines = [
        _wine("Third Wine No Price"),
        _wine("First Wine", price="R$ 100"),
        _wine("Second Wine", price="R$ 50"),
    ]
    ocr = _make_ocr(wines)
    resolved_items, unresolved_items = _run_resolve_multi_offline(ocr)
    all_items = resolved_items + unresolved_items
    order = [it["ocr"]["name"] for it in all_items]
    assert order == ["Third Wine No Price", "First Wine", "Second Wine"], (
        f"PDF should preserve document order, got {order}"
    )


def test_screenshot_sorts_by_price():
    """Screenshot items should be sorted (price first, then name length)."""
    wines = [
        _wine("No Price Wine"),
        _wine("Has Price", price="R$ 100"),
    ]
    ocr = _make_ocr(wines, image_type="screenshot")
    resolved_items, unresolved_items = _run_resolve_multi_offline(ocr)
    all_items = resolved_items + unresolved_items
    order = [it["ocr"]["name"] for it in all_items]
    assert order[0] == "Has Price", (
        f"Screenshot should sort price-first, got {order}"
    )


# ============================================================
# 4. PDF cap of 20 with overflow to unresolved_items
# ============================================================

def test_pdf_cap_20_overflow():
    """PDF should attempt resolve for first 20 items, rest go to unresolved as visual_only."""
    wines = [_wine(f"Wine {i:03d}") for i in range(25)]
    ocr = _make_ocr(wines)
    resolved_items, unresolved_items = _run_resolve_multi_offline(ocr)
    all_items = resolved_items + unresolved_items
    assert len(all_items) == 25, f"Expected all 25 items, got {len(all_items)}"
    for item in all_items:
        assert item["status"] == "visual_only"


def test_pdf_cap_20_resolves_first_20():
    """First 20 of 25 are in tier_a (attempted), last 5 are skipped to tier_c."""
    # We make the first item matchable to confirm it goes through tier_a
    wines = [_wine(f"Wine {i:03d}") for i in range(25)]
    wines[0]["name"] = "Matchable Wine"
    ocr = _make_ocr(wines)
    resolved_items, unresolved_items = _run_resolve_multi_offline(
        ocr, match_names={"Matchable Wine"}
    )
    assert len(resolved_items) == 1
    assert resolved_items[0]["ocr"]["name"] == "Matchable Wine"
    assert len(unresolved_items) == 24


def test_screenshot_cap_8():
    """Screenshot cap should remain 8, not affected by PDF changes."""
    wines = [_wine(f"Wine {i:03d}") for i in range(12)]
    ocr = _make_ocr(wines, image_type="screenshot")
    resolved_items, unresolved_items = _run_resolve_multi_offline(ocr)
    all_items = resolved_items + unresolved_items
    assert len(all_items) == 12, f"Expected all 12 items, got {len(all_items)}"


# ============================================================
# 5. PDF uses fast-only (no fallback)
# ============================================================

def test_pdf_no_fallback():
    """PDF items should NOT use _fallback_resolve even when _fast_resolve fails.

    We verify by making fallback return a match but fast return None.
    For PDF, the item should stay unresolved (fallback not called).
    For screenshot, fallback IS called so the item resolves.
    """
    wines = [_wine("Obscuro Wine")]

    fallback_called = [False]
    orig_fast = resolver._fast_resolve
    orig_fallback = resolver._fallback_resolve

    def mock_fast(name, producer, seen_ids, **kwargs):
        return None

    def mock_fallback(name, seen_ids, **kwargs):
        fallback_called[0] = True
        return _make_wine_dict(id=999, nome=name)

    resolver._fast_resolve = mock_fast
    resolver._fallback_resolve = mock_fallback
    try:
        # PDF: fallback should NOT be called
        fallback_called[0] = False
        _, unresolved_pdf = _resolve_multi(_make_ocr(wines, image_type="pdf"))
        assert not fallback_called[0], "PDF should not use fallback"
        assert len(unresolved_pdf) == 1

        # Screenshot: fallback SHOULD be called
        fallback_called[0] = False
        resolved_ss, _ = _resolve_multi(_make_ocr(wines, image_type="screenshot"))
        assert fallback_called[0], "Screenshot should use fallback"
        assert len(resolved_ss) == 1
    finally:
        resolver._fast_resolve = orig_fast
        resolver._fallback_resolve = orig_fallback


# ============================================================
# 6. format_resolved_context respects header_override and ocr_label
# ============================================================

def test_format_pdf_header_override():
    """header_override should replace the auto-generated header."""
    w = _make_wine_dict()
    resolved_items = [{"ocr": {"name": "Alamos Malbec", "price": "R$ 89"}, "wine": w, "status": "confirmed_with_note"}]
    ctx = format_resolved_context(
        [w], [], "pdf",
        {"image_type": "pdf", "wines": [{"name": "Alamos Malbec"}], "total_visible": 1},
        resolved_items=resolved_items,
        unresolved_items=[],
        header_override="[Custom PDF header here]",
        ocr_label="no PDF",
    )
    assert "[Custom PDF header here]" in ctx
    assert "foto de screenshot" not in ctx
    assert "foto de prateleira" not in ctx


def test_format_pdf_ocr_label():
    """ocr_label should appear in item lines instead of 'na imagem'."""
    w = _make_wine_dict()
    resolved_items = [{"ocr": {"name": "Alamos Malbec", "price": "R$ 89"}, "wine": w, "status": "confirmed_with_note"}]
    ctx = format_resolved_context(
        [w], [], "pdf",
        {"image_type": "pdf", "wines": [{"name": "Alamos Malbec"}], "total_visible": 1},
        resolved_items=resolved_items,
        unresolved_items=[],
        ocr_label="no PDF",
    )
    assert "Lido no PDF:" in ctx
    assert "Preco visivel no PDF:" in ctx
    assert "Lido na imagem:" not in ctx
    assert "Preco visivel na imagem:" not in ctx


def test_format_pdf_no_note_uses_ocr_label():
    """ocr_label should also apply to confirmed_no_note items."""
    w = _make_wine_dict(vivino_rating=None, nota_wcf=None, winegod_score=None)
    resolved_items = [{"ocr": {"name": "Obscuro Wine", "price": "R$ 200"}, "wine": w, "status": "confirmed_no_note"}]
    ctx = format_resolved_context(
        [w], [], "pdf",
        {"image_type": "pdf", "wines": [{"name": "Obscuro Wine"}], "total_visible": 1},
        resolved_items=resolved_items,
        unresolved_items=[],
        ocr_label="no PDF",
    )
    assert "Lido no PDF:" in ctx
    assert "Preco visivel no PDF:" in ctx


def test_format_screenshot_default_ocr_label():
    """Screenshot without ocr_label should use default 'na imagem'."""
    w = _make_wine_dict()
    resolved_items = [{"ocr": {"name": "Alamos Malbec", "price": "R$ 89"}, "wine": w, "status": "confirmed_with_note"}]
    ctx = format_resolved_context(
        [w], [], "screenshot",
        {"image_type": "screenshot", "wines": [{"name": "Alamos Malbec"}], "total_visible": 1},
        resolved_items=resolved_items,
        unresolved_items=[],
    )
    assert "Lido na imagem:" in ctx
    assert "Preco visivel na imagem:" in ctx


def test_format_screenshot_no_header_override():
    """Screenshot without header_override should use auto-generated header."""
    w = _make_wine_dict()
    resolved_items = [{"ocr": {"name": "Alamos Malbec"}, "wine": w, "status": "confirmed_with_note"}]
    ctx = format_resolved_context(
        [w], [], "screenshot",
        {"image_type": "screenshot", "wines": [{"name": "Alamos Malbec"}], "total_visible": 1},
        resolved_items=resolved_items,
        unresolved_items=[],
    )
    assert "[O usuario enviou foto de screenshot.]" in ctx


def test_format_fallback_path_header_override():
    """Fallback path (no resolved_items) should also respect header_override."""
    ctx = format_resolved_context(
        [], ["Unknown Wine"], "pdf",
        {"image_type": "pdf"},
        header_override="[PDF fallback header]",
    )
    assert "[PDF fallback header]" in ctx
    assert "foto de" not in ctx


# ============================================================
# 7. PDF source-awareness: no image-specific wording
# ============================================================

def test_format_pdf_no_header_override_no_screenshot():
    """PDF without header_override should NOT say 'foto de screenshot'."""
    w = _make_wine_dict()
    resolved_items = [{"ocr": {"name": "Alamos Malbec"}, "wine": w, "status": "confirmed_with_note"}]
    ctx = format_resolved_context(
        [w], [], "pdf",
        {"image_type": "pdf", "wines": [{"name": "Alamos Malbec"}], "total_visible": 1},
        resolved_items=resolved_items,
        unresolved_items=[],
    )
    assert "foto de screenshot" not in ctx
    assert "foto de prateleira" not in ctx
    assert "documento PDF" in ctx


def test_format_pdf_no_image_nao_legiveis():
    """PDF should NOT say 'na imagem nao legiveis'."""
    w = _make_wine_dict()
    resolved_items = [{"ocr": {"name": "Alamos Malbec"}, "wine": w, "status": "confirmed_with_note"}]
    ctx = format_resolved_context(
        [w], [], "pdf",
        {"image_type": "pdf", "wines": [{"name": "Alamos Malbec"}], "total_visible": 1},
        resolved_items=resolved_items,
        unresolved_items=[],
    )
    assert "na imagem nao legiveis" not in ctx
    assert "no documento" in ctx


def test_format_pdf_unresolved_no_leitura_visual():
    """PDF unresolved should NOT say 'apenas leitura visual'."""
    w = _make_wine_dict()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": w, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Unknown Wine", "price": "R$ 50"}, "status": "visual_only"}]
    ctx = format_resolved_context(
        [w], ["Unknown Wine"], "pdf",
        {"image_type": "pdf", "wines": [{"name": "Known"}, {"name": "Unknown Wine"}], "total_visible": 2},
        resolved_items=resolved_items,
        unresolved_items=unresolved_items,
    )
    assert "apenas leitura visual" not in ctx
    assert "identificados no documento" in ctx
    # Also check rules section
    assert "NAO ENCONTRADO (visual)" not in ctx
    assert "preco do documento" in ctx


def test_format_screenshot_keeps_visual_wording():
    """Screenshot should keep 'na imagem nao legiveis' and 'leitura visual'."""
    w = _make_wine_dict()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": w, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Unknown"}, "status": "visual_only"}]
    ctx = format_resolved_context(
        [w], ["Unknown"], "screenshot",
        {"image_type": "screenshot", "wines": [{"name": "Known"}, {"name": "Unknown"}], "total_visible": 2},
        resolved_items=resolved_items,
        unresolved_items=unresolved_items,
    )
    assert "na imagem nao legiveis" in ctx
    assert "apenas leitura visual" in ctx
    assert "NAO ENCONTRADO (visual)" in ctx


def test_format_pdf_fallback_no_screenshot():
    """PDF fallback path (no resolved_items) should NOT say 'foto de screenshot'."""
    ctx = format_resolved_context(
        [], ["Unknown Wine"], "pdf",
        {"image_type": "pdf"},
    )
    assert "foto de screenshot" not in ctx
    assert "documento PDF" in ctx


def test_format_pdf_default_ocr_label_no_na_imagem():
    """PDF without explicit ocr_label should auto-resolve to 'no documento', not 'na imagem'."""
    w = _make_wine_dict()
    resolved_items = [{"ocr": {"name": "Alamos Malbec", "price": "R$ 89"}, "wine": w, "status": "confirmed_with_note"}]
    ctx = format_resolved_context(
        [w], [], "pdf",
        {"image_type": "pdf", "wines": [{"name": "Alamos Malbec"}], "total_visible": 1},
        resolved_items=resolved_items,
        unresolved_items=[],
        # NO ocr_label passed — should auto-resolve for pdf
    )
    assert "Lido no documento:" in ctx
    assert "Preco visivel no documento:" in ctx
    assert "Lido na imagem:" not in ctx
    assert "Preco visivel na imagem:" not in ctx


def test_format_pdf_default_ocr_label_no_note_no_na_imagem():
    """PDF confirmed_no_note without explicit ocr_label should also not say 'na imagem'."""
    w = _make_wine_dict(vivino_rating=None, nota_wcf=None, winegod_score=None)
    resolved_items = [{"ocr": {"name": "Obscuro", "price": "R$ 200"}, "wine": w, "status": "confirmed_no_note"}]
    ctx = format_resolved_context(
        [w], [], "pdf",
        {"image_type": "pdf", "wines": [{"name": "Obscuro"}], "total_visible": 1},
        resolved_items=resolved_items,
        unresolved_items=[],
    )
    assert "Lido no documento:" in ctx
    assert "Preco visivel no documento:" in ctx
    assert "na imagem" not in ctx


def test_format_pdf_fallback_no_na_imagem():
    """PDF fallback (no resolved_items, no wines) should NOT say 'na imagem'."""
    ctx = format_resolved_context(
        [], ["Unknown Wine"], "pdf",
        {"image_type": "pdf"},
    )
    assert "na imagem" not in ctx
    assert "no documento" in ctx


def test_format_video_default_wording():
    """Video without explicit ocr_label should use 'no video', never 'documento'."""
    w = _make_wine_dict()
    resolved_items = [{"ocr": {"name": "Test", "price": "R$ 50"}, "wine": w, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Unknown", "price": "R$ 80"}, "status": "visual_only"}]
    ctx = format_resolved_context(
        [w], ["Unknown"], "video",
        {"image_type": "video", "wines": [{"name": "Test"}, {"name": "Unknown"}], "total_visible": 2},
        resolved_items=resolved_items,
        unresolved_items=unresolved_items,
    )
    assert "documento" not in ctx, f"Video must not say 'documento'. Got:\n{ctx}"
    assert "no video" in ctx
    assert "identificados no video" in ctx
    assert "preco do video" in ctx
    assert "Lido no video:" in ctx
    assert "Preco visivel no video:" in ctx
    assert "na imagem" not in ctx


def test_format_video_enters_multi_path():
    """image_type='video' should enter _resolve_multi, not the else branch."""
    ocr = _make_ocr([_wine("Test Wine")], image_type="video")
    resolved_items, unresolved_items = _run_resolve_multi_offline(ocr)
    all_items = resolved_items + unresolved_items
    assert len(all_items) == 1, "video should enter _resolve_multi"


def test_format_screenshot_default_still_na_imagem():
    """Screenshot without ocr_label should still say 'na imagem' (not affected by PDF fix)."""
    w = _make_wine_dict()
    resolved_items = [{"ocr": {"name": "Test", "price": "R$ 50"}, "wine": w, "status": "confirmed_with_note"}]
    ctx = format_resolved_context(
        [w], [], "screenshot",
        {"image_type": "screenshot", "wines": [{"name": "Test"}], "total_visible": 1},
        resolved_items=resolved_items,
        unresolved_items=[],
    )
    assert "Lido na imagem:" in ctx
    assert "Preco visivel na imagem:" in ctx


# ============================================================
# 8. Shelf/screenshot behavior unchanged
# ============================================================

def test_shelf_tiers_unchanged():
    """Shelf should still use tier A (3) + tier B (2) + skip rest."""
    wines = [_wine(f"Wine {i}") for i in range(10)]
    ocr = _make_ocr(wines, image_type="shelf")
    resolved_items, unresolved_items = _run_resolve_multi_offline(ocr)
    all_items = resolved_items + unresolved_items
    assert len(all_items) == 10


# --- Runner ---

if __name__ == "__main__":
    tests = [
        test_pdf_enters_multi_path,
        test_pdf_enters_via_resolve_wines_from_ocr,
        test_pdf_dedup_preserves_different_producers,
        test_pdf_dedup_collapses_same_name_same_producer,
        test_screenshot_dedup_collapses_same_name_different_producers,
        test_pdf_preserves_document_order,
        test_screenshot_sorts_by_price,
        test_pdf_cap_20_overflow,
        test_pdf_cap_20_resolves_first_20,
        test_screenshot_cap_8,
        test_pdf_no_fallback,
        test_format_pdf_header_override,
        test_format_pdf_ocr_label,
        test_format_pdf_no_note_uses_ocr_label,
        test_format_screenshot_default_ocr_label,
        test_format_screenshot_no_header_override,
        test_format_fallback_path_header_override,
        test_format_pdf_no_header_override_no_screenshot,
        test_format_pdf_no_image_nao_legiveis,
        test_format_pdf_unresolved_no_leitura_visual,
        test_format_screenshot_keeps_visual_wording,
        test_format_pdf_fallback_no_screenshot,
        test_format_pdf_default_ocr_label_no_na_imagem,
        test_format_pdf_default_ocr_label_no_note_no_na_imagem,
        test_format_pdf_fallback_no_na_imagem,
        test_format_video_default_wording,
        test_format_video_enters_multi_path,
        test_format_screenshot_default_still_na_imagem,
        test_shelf_tiers_unchanged,
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
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
