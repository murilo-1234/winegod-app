"""Regression test: line/family matching in resolver.

Testa que _score_match rejeita candidatos de linha/familia errada
e aceita candidatos da linha correta.

Roda offline (sem banco): python -m tests.test_resolver_line_matching
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.resolver import (
    _score_match,
    _extract_line_tokens,
    _MIN_MATCH_SCORE,
)
from tools.normalize import normalizar


# --- Helpers ---

def _make_candidate(nome, produtor):
    return {"nome": nome, "produtor": produtor, "id": hash(nome)}


def assert_rejects(ocr_name, nome, produtor, reason=""):
    """Score must be 0 (rejected by line gate)."""
    cand = _make_candidate(nome, produtor)
    score = _score_match(ocr_name, cand)
    status = "PASS" if score == 0.0 else f"FAIL (score={score:.3f})"
    label = f"  REJECT {ocr_name!r} vs {nome!r}"
    if reason:
        label += f"  [{reason}]"
    print(f"  {status}: {label}")
    return score == 0.0


def assert_accepts(ocr_name, nome, produtor, reason=""):
    """Score must be above MIN_MATCH_SCORE."""
    cand = _make_candidate(nome, produtor)
    score = _score_match(ocr_name, cand)
    status = "PASS" if score > _MIN_MATCH_SCORE else f"FAIL (score={score:.3f})"
    label = f"  ACCEPT {ocr_name!r} vs {nome!r}"
    if reason:
        label += f"  [{reason}]"
    print(f"  {status}: {label}")
    return score > _MIN_MATCH_SCORE


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# --- Test Cases ---

def test_montGras_aura():
    """Caso 1-2: MontGras Aura (shelf photo)
    OCR le: MontGras Aura Reserva Carmenere / MontGras Aura Carmenere
    Linha 'Aura' deve ser obrigatoria no match.
    """
    section("CASO 1-2: MontGras Aura (shelf)")
    results = []

    # MUST reject: same producer, wrong line
    results.append(assert_rejects(
        "MontGras Aura Reserva Carmenere",
        "MontGras De.Vine Reserva Carmenere", "MontGras",
        "wrong line: De.Vine instead of Aura"
    ))
    results.append(assert_rejects(
        "MontGras Aura Carmenere",
        "MontGras Day One Carmenere", "MontGras",
        "wrong line: Day One instead of Aura"
    ))
    results.append(assert_rejects(
        "MontGras Aura Reserva Merlot",
        "MontGras Quatro Reserva Merlot", "MontGras",
        "wrong line: Quatro instead of Aura"
    ))

    # MUST accept: correct line
    results.append(assert_accepts(
        "MontGras Aura Reserva Carmenere",
        "MontGras Aura Reserva Carmenere", "MontGras",
        "exact match"
    ))
    results.append(assert_accepts(
        "MontGras Aura Carmenere",
        "MontGras Aura Carmenere 2022", "MontGras",
        "correct line, vintage suffix"
    ))

    return results


def test_casa_silva_family_wines():
    """Caso 3-4: Casa Silva Family Wines (shelf photo)
    OCR le: Casa Silva Family Wines Cabernet Sauvignon
    Linha 'Family Wines' deve ser obrigatoria.
    """
    section("CASO 3-4: Casa Silva Family Wines (shelf)")
    results = []

    # MUST reject: same producer, wrong line
    results.append(assert_rejects(
        "Casa Silva Family Wines Cabernet Sauvignon",
        "Casa Silva Los Lingues Single Block S38 Cabernet Sauvignon", "Casa Silva",
        "wrong line: Los Lingues instead of Family Wines"
    ))
    results.append(assert_rejects(
        "Casa Silva Family Wines Carmenere",
        "Casa Silva Reserva Carmenere", "Casa Silva",
        "wrong line: no line vs Family Wines"
    ))

    # MUST accept: correct line
    results.append(assert_accepts(
        "Casa Silva Family Wines Cabernet Sauvignon",
        "Casa Silva Family Wines Cabernet Sauvignon", "Casa Silva",
        "exact match"
    ))

    return results


def test_amaral():
    """Caso 5-6: Amaral (shelf photo)
    OCR le: Amaral Red Blend Colchagua Costa / Amaral Syrah Valle de Leyda
    Amaral is producer. If DB has no match, should be unresolved.
    Line tokens: 'colchagua', 'costa' / 'valle', 'leyda'
    """
    section("CASO 5-6: Amaral (shelf)")
    results = []

    # Line tokens include region words — reject if candidate has different region
    results.append(assert_rejects(
        "Amaral Red Blend Colchagua Costa",
        "Amaral Syrah Valle de Leyda", "Amaral",
        "different wine/region tokens"
    ))

    # Accept exact match
    results.append(assert_accepts(
        "Amaral Red Blend Colchagua Costa",
        "Amaral Red Blend Colchagua Costa", "Amaral",
        "exact match"
    ))

    return results


def test_d_eugenio():
    """Caso 7: D. Eugenio (label photo)
    OCR le: D. Eugenio Reserva Malbec
    If producer is 'D. Eugenio', no line tokens remain — normal scoring.
    """
    section("CASO 7: D. Eugenio (label)")
    results = []

    # Producer matches — 'eugenio' is producer, not line
    results.append(assert_accepts(
        "D. Eugenio Reserva Malbec",
        "D. Eugenio Reserva Malbec 2020", "D. Eugenio",
        "producer match, no line conflict"
    ))

    # Wrong producer
    results.append(assert_rejects(
        "D. Eugenio Reserva Malbec",
        "Catena Zapata Malbec Reserva", "Catena Zapata",
        "completely different wine"
    ))

    return results


def test_cuatro_vientos():
    """Caso 8: Cuatro Vientos (shelf or label)
    OCR le: Cuatro Vientos Cabernet Sauvignon
    'Cuatro Vientos' can be line or producer.
    """
    section("CASO 8: Cuatro Vientos")
    results = []

    # If producer is 'Cuatro Vientos', line tokens empty — accept
    results.append(assert_accepts(
        "Cuatro Vientos Cabernet Sauvignon",
        "Cuatro Vientos Cabernet Sauvignon Reserva", "Cuatro Vientos",
        "producer match, no line tokens"
    ))

    # If producer is something else, 'cuatro' + 'vientos' are line tokens
    results.append(assert_rejects(
        "Cuatro Vientos Cabernet Sauvignon",
        "Sol de Chile Cabernet Sauvignon", "Sol de Chile",
        "wrong producer and wine"
    ))

    return results


def test_screenshot_case_1():
    """Caso 9: Screenshot com vinho Vivino
    OCR le: Casillero del Diablo Carmenere
    """
    section("CASO 9: Screenshot — Casillero del Diablo")
    results = []

    results.append(assert_accepts(
        "Casillero del Diablo Carmenere",
        "Casillero del Diablo Carmenere Reserva", "Concha y Toro",
        "correct wine line"
    ))
    results.append(assert_rejects(
        "Casillero del Diablo Carmenere",
        "Marques de Casa Concha Carmenere", "Concha y Toro",
        "same producer, wrong line"
    ))

    return results


def test_screenshot_case_2():
    """Caso 10: Screenshot com vinho generico
    OCR le: Alamos Malbec
    """
    section("CASO 10: Screenshot — Alamos Malbec")
    results = []

    results.append(assert_accepts(
        "Alamos Malbec",
        "Alamos Malbec 2022", "Catena",
        "correct line"
    ))
    results.append(assert_rejects(
        "Alamos Malbec",
        "Catena Alta Malbec", "Catena",
        "same producer, wrong line"
    ))

    return results


def test_label_case_1():
    """Caso 11: Label — Trivento Reserve Malbec"""
    section("CASO 11: Label — Trivento Reserve Malbec")
    results = []

    results.append(assert_accepts(
        "Trivento Reserve Malbec",
        "Trivento Reserve Malbec 2021", "Trivento",
        "correct match"
    ))
    # 'reserve' is classification, not line — 'Golden' is the line token
    # OCR has no line tokens (reserve=classification, malbec=grape) → accepts
    results.append(assert_accepts(
        "Trivento Reserve Malbec",
        "Trivento Golden Reserve Malbec", "Trivento",
        "no line tokens in OCR — reserve is classification"
    ))

    return results


def test_label_case_2():
    """Caso 12: Label — Terrazas Reserva Malbec"""
    section("CASO 12: Label — Terrazas Reserva Malbec")
    results = []

    # 'terrazas' is producer token, 'reserva' is classification — no line tokens
    results.append(assert_accepts(
        "Terrazas Reserva Malbec",
        "Terrazas de los Andes Reserva Malbec", "Terrazas de los Andes",
        "producer variant, same wine"
    ))

    return results


def test_line_token_extraction():
    """Verifica que _extract_line_tokens extrai tokens corretos."""
    section("UNIT: _extract_line_tokens")
    results = []

    cases = [
        # (ocr_name, producer, expected_tokens)
        ("MontGras Aura Reserva Carmenere", "MontGras", ["aura"]),
        ("Casa Silva Family Wines Cabernet Sauvignon", "Casa Silva", ["family", "wines"]),
        ("MontGras Day One Carmenere", "MontGras", ["day", "one"]),
        ("Casillero del Diablo Carmenere", "Concha y Toro", ["casillero", "diablo"]),
        ("Amaral Red Blend Colchagua Costa", "Amaral", ["colchagua", "costa"]),
        ("D. Eugenio Reserva Malbec", "D. Eugenio", []),
        ("Terrazas Reserva Malbec", "Terrazas de los Andes", []),
    ]

    for ocr_name, producer, expected in cases:
        ocr_norm = normalizar(ocr_name)
        prod_norm = normalizar(producer)
        actual = _extract_line_tokens(ocr_norm, prod_norm)
        ok = actual == expected
        status = "PASS" if ok else "FAIL"
        print(f"  {status}: {ocr_name!r} (prod={producer!r})")
        if not ok:
            print(f"         expected={expected}, got={actual}")
        results.append(ok)

    return results


# --- Main ---

def main():
    print("REGRESSION TEST — Line/Family Matching in Resolver")
    print("=" * 60)

    all_results = []
    all_results.extend(test_line_token_extraction())
    all_results.extend(test_montGras_aura())
    all_results.extend(test_casa_silva_family_wines())
    all_results.extend(test_amaral())
    all_results.extend(test_d_eugenio())
    all_results.extend(test_cuatro_vientos())
    all_results.extend(test_screenshot_case_1())
    all_results.extend(test_screenshot_case_2())
    all_results.extend(test_label_case_1())
    all_results.extend(test_label_case_2())

    passed = sum(all_results)
    total = len(all_results)

    print(f"\n{'='*60}")
    print(f"RESULTADO: {passed}/{total} casos passaram")
    print(f"{'='*60}")

    return 0 if all(all_results) else 1


if __name__ == "__main__":
    sys.exit(main())
