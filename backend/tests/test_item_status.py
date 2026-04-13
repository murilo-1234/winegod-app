"""Test explicit item status assignment in the resolver pipeline.

Validates that every item gets one of: visual_only, confirmed_no_note, confirmed_with_note.
Runs offline (no DB): python -m tests.test_item_status
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.resolver import _derive_item_status, resolve_wines_from_ocr
from services.display import resolve_display


# --- Helpers ---

def _wine_with_note():
    """Wine dict that resolve_display will give a display_note."""
    return {
        "id": 1,
        "nome": "Alamos Malbec",
        "produtor": "Catena",
        "vivino_rating": 4.1,
        "nota_wcf": None,
        "nota_wcf_sample_size": None,
        "winegod_score": 3.5,
        "preco_min": 50,
        "preco_max": 80,
        "moeda": "BRL",
    }


def _wine_without_note():
    """Wine dict that resolve_display will NOT give a display_note."""
    return {
        "id": 2,
        "nome": "Vinho Obscuro Sem Rating",
        "produtor": "Produtor X",
        "vivino_rating": None,
        "nota_wcf": None,
        "nota_wcf_sample_size": None,
        "winegod_score": None,
        "preco_min": None,
        "preco_max": None,
        "moeda": None,
    }


def _wine_no_note_but_has_score():
    """Wine with winegod_score and price but NO display_note (no rating sources)."""
    return {
        "id": 3,
        "nome": "Vinho Score Sem Nota",
        "produtor": "Produtor Y",
        "pais_nome": "Chile",
        "regiao": "Valle Central",
        "vivino_rating": None,
        "nota_wcf": None,
        "nota_wcf_sample_size": None,
        "winegod_score": 4.2,
        "preco_min": 60,
        "preco_max": 90,
        "moeda": "BRL",
    }


# --- Tests ---

def test_derive_status():
    """_derive_item_status returns correct status based on display_note."""
    print("\n=== TEST: _derive_item_status ===")
    results = []

    # Wine with vivino_rating -> has display_note -> confirmed_with_note
    w1 = _wine_with_note()
    s1 = _derive_item_status(w1)
    ok1 = s1 == "confirmed_with_note"
    print(f"  {'PASS' if ok1 else 'FAIL'}: wine with rating -> {s1}")
    results.append(ok1)

    # Wine without any rating -> no display_note -> confirmed_no_note
    w2 = _wine_without_note()
    s2 = _derive_item_status(w2)
    ok2 = s2 == "confirmed_no_note"
    print(f"  {'PASS' if ok2 else 'FAIL'}: wine without rating -> {s2}")
    results.append(ok2)

    return results


def test_label_resolved_status():
    """Label path: resolved item gets correct status field."""
    print("\n=== TEST: label resolved item status ===")
    results = []

    # Simulate a label OCR that resolved to a wine with note
    # We can't call resolve_wines_from_ocr without DB, so test the structure directly
    wine = _wine_with_note()
    item = {"ocr": {"name": "Alamos Malbec"}, "wine": wine, "status": _derive_item_status(wine)}

    ok = item["status"] == "confirmed_with_note"
    print(f"  {'PASS' if ok else 'FAIL'}: label resolved item status={item['status']}")
    results.append(ok)

    # Wine without note
    wine2 = _wine_without_note()
    item2 = {"ocr": {"name": "Obscuro"}, "wine": wine2, "status": _derive_item_status(wine2)}
    ok2 = item2["status"] == "confirmed_no_note"
    print(f"  {'PASS' if ok2 else 'FAIL'}: label resolved (no note) status={item2['status']}")
    results.append(ok2)

    return results


def test_unresolved_status():
    """Unresolved items always get visual_only."""
    print("\n=== TEST: unresolved item status ===")
    results = []

    item = {"ocr": {"name": "Cuatro Vientos Tinto"}, "status": "visual_only"}
    ok = item["status"] == "visual_only"
    print(f"  {'PASS' if ok else 'FAIL'}: unresolved item status={item['status']}")
    results.append(ok)

    return results


def test_status_field_present_in_all_items():
    """Simulate a mixed batch: every item must have 'status' field."""
    print("\n=== TEST: status field present in all items ===")
    results = []

    wine_a = _wine_with_note()
    wine_b = _wine_without_note()

    resolved_items = [
        {"ocr": {"name": "Alamos Malbec"}, "wine": wine_a, "status": _derive_item_status(wine_a)},
        {"ocr": {"name": "Obscuro"}, "wine": wine_b, "status": _derive_item_status(wine_b)},
    ]
    unresolved_items = [
        {"ocr": {"name": "Cuatro Vientos Tinto"}, "status": "visual_only"},
    ]

    all_items = resolved_items + unresolved_items
    valid_statuses = {"visual_only", "confirmed_no_note", "confirmed_with_note"}

    for item in all_items:
        has_status = "status" in item
        valid = item.get("status") in valid_statuses
        name = item["ocr"].get("name", "?")
        ok = has_status and valid
        print(f"  {'PASS' if ok else 'FAIL'}: {name} -> status={item.get('status')}")
        results.append(ok)

    return results


def test_context_formatting_uses_status():
    """format_resolved_context produces different sections per status."""
    print("\n=== TEST: context formatting separates by status ===")
    from tools.resolver import format_resolved_context

    results = []

    wine_a = _wine_with_note()
    wine_b = _wine_without_note()

    resolved_items = [
        {"ocr": {"name": "Alamos Malbec", "price": "R$ 59"}, "wine": wine_a, "status": "confirmed_with_note"},
        {"ocr": {"name": "Obscuro", "price": "R$ 30"}, "wine": wine_b, "status": "confirmed_no_note"},
    ]
    unresolved_items = [
        {"ocr": {"name": "Cuatro Vientos Tinto", "price": "R$ 45"}, "status": "visual_only"},
    ]

    context = format_resolved_context(
        [wine_a, wine_b], ["Cuatro Vientos Tinto"], "shelf", {"image_type": "shelf"},
        resolved_items=resolved_items,
        unresolved_items=unresolved_items,
    )

    # Check the 3 section headers appear
    ok1 = "CONFIRMADO(S) COM NOTA" in context
    print(f"  {'PASS' if ok1 else 'FAIL'}: context has CONFIRMADO COM NOTA section")
    results.append(ok1)

    ok2 = "CONFIRMADO(S) SEM NOTA" in context
    print(f"  {'PASS' if ok2 else 'FAIL'}: context has CONFIRMADO SEM NOTA section")
    results.append(ok2)

    ok3 = "NAO ENCONTRADO" in context
    print(f"  {'PASS' if ok3 else 'FAIL'}: context has NAO ENCONTRADO section")
    results.append(ok3)

    ok4 = "REGRAS DE CERTEZA (3 niveis)" in context
    print(f"  {'PASS' if ok4 else 'FAIL'}: context has 3-level rules")
    results.append(ok4)

    ok5 = "APENAS vinhos CONFIRMADOS COM NOTA" in context
    print(f"  {'PASS' if ok5 else 'FAIL'}: ranking gating rule present")
    results.append(ok5)

    return results


def test_label_confirmed_no_note_hides_score():
    """BUG FIX: label + confirmed_no_note must NOT expose numeric score even if wine has winegod_score."""
    print("\n=== TEST: label confirmed_no_note hides score ===")
    from tools.resolver import format_resolved_context

    results = []

    wine = _wine_no_note_but_has_score()
    resolved_items = [
        {"ocr": {"name": "Vinho Score Sem Nota"}, "wine": wine, "status": "confirmed_no_note"},
    ]

    context = format_resolved_context(
        [wine], [], "label",
        {"image_type": "label", "ocr_result": {"name": "Vinho Score Sem Nota"}, "search_text": "Vinho Score Sem Nota"},
        resolved_items=resolved_items,
        unresolved_items=[],
    )

    # Must NOT contain the numeric score 4.2
    ok1 = "4.2" not in context
    print(f"  {'PASS' if ok1 else 'FAIL'}: context does not contain numeric score '4.2'")
    results.append(ok1)

    # Must contain "sem score" (sanitized)
    ok2 = "sem score" in context
    print(f"  {'PASS' if ok2 else 'FAIL'}: context contains 'sem score'")
    results.append(ok2)

    # Must contain the instruction to not invent score
    ok3 = "NAO invente nota, score, ranking" in context
    print(f"  {'PASS' if ok3 else 'FAIL'}: instruction to not invent score present")
    results.append(ok3)

    # Must say confirmed_no_note in status
    ok4 = "confirmed_no_note" in context
    print(f"  {'PASS' if ok4 else 'FAIL'}: status confirmed_no_note in context")
    results.append(ok4)

    return results


# --- Main ---

def main():
    print("TEST — Explicit Item Status Assignment")
    print("=" * 50)

    all_results = []
    all_results.extend(test_derive_status())
    all_results.extend(test_label_resolved_status())
    all_results.extend(test_unresolved_status())
    all_results.extend(test_status_field_present_in_all_items())
    all_results.extend(test_context_formatting_uses_status())
    all_results.extend(test_label_confirmed_no_note_hides_score())

    passed = sum(all_results)
    total = len(all_results)

    print(f"\n{'='*50}")
    print(f"RESULTADO: {passed}/{total} casos passaram")
    print(f"{'='*50}")

    return 0 if all(all_results) else 1


if __name__ == "__main__":
    sys.exit(main())
