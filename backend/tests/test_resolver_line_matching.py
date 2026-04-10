"""Regression test: line/family + variety/style matching in resolver.

Testa que _score_match rejeita candidatos de linha/familia errada,
variedade/estilo incompativel, e aceita candidatos corretos.

Roda offline (sem banco): python -m tests.test_resolver_line_matching
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.resolver import (
    _score_match,
    _extract_line_tokens,
    _extract_canonical_varieties,
    _collapse_initials,
    _build_scoring_name,
    _MIN_MATCH_SCORE,
)
from tools.normalize import normalizar


# --- Helpers ---

def _make_candidate(nome, produtor):
    return {"nome": nome, "produtor": produtor, "id": hash(nome)}


def assert_rejects(ocr_name, nome, produtor, reason=""):
    """Score must be 0 (rejected by gate)."""
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


# =============================================
# UNIT TESTS
# =============================================

def test_line_token_extraction():
    """Verifica que _extract_line_tokens extrai tokens corretos."""
    section("UNIT: _extract_line_tokens")
    results = []

    cases = [
        ("MontGras Aura Reserva Carmenere", "MontGras", ["aura"]),
        ("Casa Silva Family Wines Cabernet Sauvignon", "Casa Silva", ["family", "wines"]),
        ("MontGras Day One Carmenere", "MontGras", ["day", "one"]),
        ("Casillero del Diablo Carmenere", "Concha y Toro", ["casillero", "diablo"]),
        ("Amaral Red Blend Colchagua Costa", "Amaral", ["colchagua", "costa"]),
        ("D. Eugenio Reserva Malbec", "D. Eugenio", []),
        ("Terrazas Reserva Malbec", "Terrazas de los Andes", []),
        ("Toro Centenario Chardonnay", "Toro Centenario", []),
        ("Krug Grande Cuvee", "Krug", []),  # 'grande'=classification, 'cuvee'=generic
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


def test_canonical_variety_extraction():
    """Verifica que _extract_canonical_varieties extrai frases corretas."""
    section("UNIT: _extract_canonical_varieties")
    results = []

    cases = [
        # (name_norm, expected_canonicals)
        ("montgras aura reserva carmenere", ["carmenere"]),
        ("toro centenario chardonnay", ["chardonnay"]),
        ("toro centenario rose", ["rose"]),
        ("alamos cabernet sauvignon reserva", ["cabernet sauvignon"]),
        ("emiliana sauvignon blanc", ["sauvignon blanc"]),
        ("krug grande cuvee", []),
        ("freixenet cava brut", ["brut"]),
        ("pinot noir reserva", ["pinot noir"]),
        ("ruinart blanc de blancs brut", ["blanc de blancs", "brut"]),
        ("champagne extra brut", ["extra brut"]),
    ]

    for name_norm, expected in cases:
        actual = _extract_canonical_varieties(name_norm)
        ok = actual == expected
        status = "PASS" if ok else "FAIL"
        print(f"  {status}: {name_norm!r}")
        if not ok:
            print(f"         expected={expected}, got={actual}")
        results.append(ok)

    return results


# =============================================
# LINE/FAMILY GATE TESTS (Gate 0)
# =============================================

def test_montGras_aura():
    """MontGras Aura: 'Aura' obrigatoria."""
    section("LINE: MontGras Aura (shelf)")
    results = []

    results.append(assert_rejects(
        "MontGras Aura Reserva Carmenere",
        "MontGras De.Vine Reserva Carmenere", "MontGras",
        "wrong line: De.Vine"
    ))
    results.append(assert_rejects(
        "MontGras Aura Carmenere",
        "MontGras Day One Carmenere", "MontGras",
        "wrong line: Day One"
    ))
    results.append(assert_rejects(
        "MontGras Aura Reserva Merlot",
        "MontGras Quatro Reserva Merlot", "MontGras",
        "wrong line: Quatro"
    ))
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
    """Casa Silva Family Wines: 'Family Wines' obrigatoria."""
    section("LINE: Casa Silva Family Wines (shelf)")
    results = []

    results.append(assert_rejects(
        "Casa Silva Family Wines Cabernet Sauvignon",
        "Casa Silva Los Lingues Single Block S38 Cabernet Sauvignon", "Casa Silva",
        "wrong line: Los Lingues"
    ))
    results.append(assert_rejects(
        "Casa Silva Family Wines Carmenere",
        "Casa Silva Reserva Carmenere", "Casa Silva",
        "wrong line: no line vs Family Wines"
    ))
    results.append(assert_accepts(
        "Casa Silva Family Wines Cabernet Sauvignon",
        "Casa Silva Family Wines Cabernet Sauvignon", "Casa Silva",
        "exact match"
    ))

    return results


def test_amaral():
    """Amaral: region tokens as line identifiers."""
    section("LINE: Amaral (shelf)")
    results = []

    results.append(assert_rejects(
        "Amaral Red Blend Colchagua Costa",
        "Amaral Syrah Valle de Leyda", "Amaral",
        "different wine/region tokens"
    ))
    results.append(assert_accepts(
        "Amaral Red Blend Colchagua Costa",
        "Amaral Red Blend Colchagua Costa", "Amaral",
        "exact match"
    ))

    return results


def test_d_eugenio():
    """D. Eugenio: producer = line, no line tokens."""
    section("LINE: D. Eugenio (label)")
    results = []

    results.append(assert_accepts(
        "D. Eugenio Reserva Malbec",
        "D. Eugenio Reserva Malbec 2020", "D. Eugenio",
        "producer match, no line conflict"
    ))
    results.append(assert_rejects(
        "D. Eugenio Reserva Malbec",
        "Catena Zapata Malbec Reserva", "Catena Zapata",
        "completely different wine"
    ))

    return results


def test_cuatro_vientos():
    """Cuatro Vientos: line or producer depending on context."""
    section("LINE: Cuatro Vientos")
    results = []

    results.append(assert_accepts(
        "Cuatro Vientos Cabernet Sauvignon",
        "Cuatro Vientos Cabernet Sauvignon Reserva", "Cuatro Vientos",
        "producer match, no line tokens"
    ))
    results.append(assert_rejects(
        "Cuatro Vientos Cabernet Sauvignon",
        "Sol de Chile Cabernet Sauvignon", "Sol de Chile",
        "wrong producer and wine"
    ))

    return results


def test_casillero():
    """Casillero del Diablo: line within Concha y Toro."""
    section("LINE: Casillero del Diablo (screenshot)")
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


def test_alamos():
    """Alamos: line within Catena."""
    section("LINE: Alamos Malbec (screenshot)")
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


def test_trivento():
    """Trivento: reserve is classification, not line."""
    section("LINE: Trivento Reserve Malbec (label)")
    results = []

    results.append(assert_accepts(
        "Trivento Reserve Malbec",
        "Trivento Reserve Malbec 2021", "Trivento",
        "correct match"
    ))
    results.append(assert_accepts(
        "Trivento Reserve Malbec",
        "Trivento Golden Reserve Malbec", "Trivento",
        "no line tokens in OCR — reserve is classification"
    ))

    return results


def test_terrazas():
    """Terrazas: producer variant."""
    section("LINE: Terrazas Reserva Malbec (label)")
    results = []

    results.append(assert_accepts(
        "Terrazas Reserva Malbec",
        "Terrazas de los Andes Reserva Malbec", "Terrazas de los Andes",
        "producer variant, same wine"
    ))

    return results


# =============================================
# VARIETY/STYLE GATE TESTS (Gate V)
# =============================================

def test_variety_toro_centenario():
    """Bug confirmado: Toro Centenario Chardonnay -> Rose."""
    section("VARIETY: Toro Centenario (cross-grape)")
    results = []

    results.append(assert_rejects(
        "Toro Centenario Chardonnay",
        "Toro Centenario Rose", "Toro Centenario",
        "chardonnay != rose"
    ))
    results.append(assert_accepts(
        "Toro Centenario Chardonnay",
        "Toro Centenario Chardonnay 2023", "Toro Centenario",
        "same grape"
    ))

    return results


def test_variety_cross_grape():
    """Variedades incompativeis devem rejeitar."""
    section("VARIETY: Cross-grape rejections")
    results = []

    results.append(assert_rejects(
        "Alamos Cabernet Sauvignon",
        "Alamos Merlot", "Catena",
        "cabernet sauvignon != merlot"
    ))
    results.append(assert_rejects(
        "Trivento Carmenere",
        "Trivento Malbec", "Trivento",
        "carmenere != malbec"
    ))
    results.append(assert_rejects(
        "MontGras Aura Pinot Noir",
        "MontGras Aura Syrah", "MontGras",
        "pinot noir != syrah"
    ))
    results.append(assert_rejects(
        "Emiliana Sauvignon Blanc",
        "Emiliana Chardonnay", "Emiliana",
        "sauvignon blanc != chardonnay"
    ))

    return results


def test_variety_compound_conflicts():
    """Compostos que compartilham token mas sao variedades diferentes."""
    section("VARIETY: Compound conflicts (token parcial)")
    results = []

    # Pedidos pelo usuario — casos criticos
    results.append(assert_rejects(
        "Emiliana Sauvignon Blanc",
        "Emiliana Cabernet Sauvignon", "Emiliana",
        "sauvignon blanc != cabernet sauvignon"
    ))
    results.append(assert_rejects(
        "Trivento Cabernet Franc",
        "Trivento Cabernet Sauvignon", "Trivento",
        "cabernet franc != cabernet sauvignon"
    ))
    results.append(assert_rejects(
        "MontGras Pinot Grigio",
        "MontGras Pinot Noir", "MontGras",
        "pinot grigio != pinot noir"
    ))
    results.append(assert_rejects(
        "Ruinart Blanc de Blancs",
        "Champagne Extra Brut", "Ruinart",
        "blanc de blancs != extra brut"
    ))

    return results


def test_variety_same_grape():
    """Mesma variedade deve aceitar."""
    section("VARIETY: Same grape accepts")
    results = []

    results.append(assert_accepts(
        "MontGras Aura Carmenere",
        "MontGras Aura Carmenere Reserva", "MontGras",
        "same grape + line"
    ))
    results.append(assert_accepts(
        "Alamos Malbec",
        "Alamos Malbec 2022", "Catena",
        "same grape, vintage diff"
    ))

    return results


def test_variety_no_grape_in_ocr():
    """OCR sem variedade: nao deve restringir."""
    section("VARIETY: No grape in OCR")
    results = []

    results.append(assert_accepts(
        "Krug Grande Cuvee",
        "Krug Grande Cuvee Brut", "Krug",
        "no grape in OCR — accept any"
    ))

    return results


def test_variety_style_conflict():
    """Conflito de estilo (brut vs seco, etc)."""
    section("VARIETY: Style conflicts")
    results = []

    results.append(assert_rejects(
        "Freixenet Cava Brut",
        "Freixenet Cava Seco", "Freixenet",
        "brut != seco"
    ))
    results.append(assert_accepts(
        "Freixenet Cava Brut",
        "Freixenet Cava Brut Nature", "Freixenet",
        "brut matches — nature is extra"
    ))

    return results


# =============================================
# COMBINED GATE TESTS (Line + Variety)
# =============================================

def test_combined_krug_ruinart():
    """Krug / Ruinart: champagne shelf from real test."""
    section("COMBINED: Krug / Ruinart (shelf)")
    results = []

    results.append(assert_accepts(
        "Krug Grande Cuvee",
        "Krug Grande Cuvee Brut", "Krug",
        "correct match"
    ))
    results.append(assert_rejects(
        "Ruinart Blanc de Blancs Brut",
        "Ruinart Rose", "Ruinart",
        "wrong style: blanc de blancs vs rose"
    ))

    return results


def test_combined_contada_1926():
    """Contada 1926: line tokens + variety."""
    section("COMBINED: Contada 1926 (shelf)")
    results = []

    # 'contada' and '1926' are line tokens (1926 has 4 digits but is not a vintage year...
    # actually it IS 4 digits so it gets filtered. Only 'contada' remains.)
    results.append(assert_accepts(
        "Contada 1926 Chianti",
        "Contada 1926 Chianti Classico", "Contada",
        "same line, chianti matches"
    ))
    results.append(assert_rejects(
        "Contada 1926 Chianti",
        "Contada 1926 Montepulciano", "Contada",
        "same line but different grape"
    ))

    return results


def test_combined_montGras_aura_cross_grape():
    """MontGras Aura: right line but wrong grape."""
    section("COMBINED: MontGras Aura cross-grape")
    results = []

    results.append(assert_rejects(
        "MontGras Aura Carmenere",
        "MontGras Aura Merlot", "MontGras",
        "right line, wrong grape"
    ))
    results.append(assert_rejects(
        "MontGras Aura Reserva Carmenere",
        "MontGras Aura Reserva Merlot", "MontGras",
        "right line + classification, wrong grape"
    ))
    results.append(assert_accepts(
        "MontGras Aura Reserva Carmenere",
        "MontGras Aura Reserva Carmenere 2021", "MontGras",
        "right line + grape + classification"
    ))

    return results


# =============================================
# RECALL HELPERS TESTS
# =============================================

def test_collapse_initials():
    """_collapse_initials: single-letter words collapse."""
    section("UNIT: _collapse_initials")
    results = []

    cases = [
        ("d eugenio crianza", "deugenio crianza"),
        ("j p chenet", "jp chenet"),
        ("montgras aura", "montgras aura"),  # no single-letter words
        ("d o mancha", "do mancha"),
        ("alamos malbec", "alamos malbec"),
    ]

    for input_val, expected in cases:
        actual = _collapse_initials(input_val)
        ok = actual == expected
        status = "PASS" if ok else "FAIL"
        print(f"  {status}: {input_val!r} -> {actual!r}")
        if not ok:
            print(f"         expected={expected!r}")
        results.append(ok)

    return results


def test_build_scoring_name():
    """_build_scoring_name: structured fields -> clean name."""
    section("UNIT: _build_scoring_name")
    results = []

    cases = [
        # (ocr_dict, expected_scoring_name)
        ({"name": "D. Eugenio Crianza 2018 La Mancha", "producer": "D. Eugenio",
          "line": "Crianza", "classification": "Crianza"},
         "D. Eugenio Crianza"),  # removes "La Mancha", dedup classification
        ({"name": "Freixenet ICE Cuvée Especial", "producer": "Freixenet",
          "line": "ICE", "classification": "Cuvée Especial"},
         "Freixenet ICE Cuvée Especial"),
        ({"name": "Cuatro Vientos Tinto"},  # no structured fields
         "Cuatro Vientos Tinto"),
        ({"name": "MontGras Aura Reserva Carmenere", "producer": "MontGras",
          "line": "Aura", "variety": "Carmenere", "classification": "Reserva"},
         "MontGras Aura Reserva Carmenere"),
    ]

    for w, expected in cases:
        actual = _build_scoring_name(w)
        ok = actual == expected
        status = "PASS" if ok else "FAIL"
        print(f"  {status}: {w.get('name')!r} -> {actual!r}")
        if not ok:
            print(f"         expected={expected!r}")
        results.append(ok)

    return results


# =============================================
# RECALL: SCORING WITH CLEAN NAME (positive)
# =============================================

def test_recall_d_eugenio():
    """D. Eugenio: scoring_name removes 'La Mancha' region."""
    section("RECALL: D. Eugenio (scoring_name)")
    results = []

    # With raw name, "mancha" would be a false line token -> reject
    # With scoring_name "D. Eugenio Crianza", no false line tokens
    results.append(assert_accepts(
        "D. Eugenio Crianza",  # scoring_name (clean)
        "D.Eugenio Vino de Crianza", "D. Eugenio",
        "scoring_name removes region, crianza matches"
    ))

    # Safety: still rejects wrong wine
    results.append(assert_rejects(
        "D. Eugenio Crianza",
        "Marques de Riscal Crianza", "Marques de Riscal",
        "different producer"
    ))

    return results


def test_recall_cuatro_vientos():
    """Cuatro Vientos: producer=Aromo, but 'Cuatro Vientos' in wine name."""
    section("RECALL: Cuatro Vientos")
    results = []

    # DB producer is "Aromo" but wine name contains "Cuatro Vientos"
    results.append(assert_accepts(
        "Cuatro Vientos Tinto",
        "Cuatro Vientos Tinto", "Aromo",
        "line tokens match even with different producer"
    ))

    return results


def test_recall_freixenet_ice():
    """Freixenet ICE: line 'ICE' in scoring."""
    section("RECALL: Freixenet ICE")
    results = []

    results.append(assert_accepts(
        "Freixenet ICE Cuvée Especial",
        "Freixenet Ice Cuvee Especial", "Freixenet",
        "exact wine match"
    ))

    # Safety: ICE != Cordon Negro
    results.append(assert_rejects(
        "Freixenet ICE Cuvée Especial",
        "Freixenet Cordon Negro Brut", "Freixenet",
        "wrong line: ICE vs Cordon Negro"
    ))

    return results


# --- Main ---

def main():
    print("REGRESSION TEST — Line/Family + Variety/Style Matching")
    print("=" * 60)

    all_results = []

    # Unit tests
    all_results.extend(test_line_token_extraction())
    all_results.extend(test_canonical_variety_extraction())

    # Line gate tests
    all_results.extend(test_montGras_aura())
    all_results.extend(test_casa_silva_family_wines())
    all_results.extend(test_amaral())
    all_results.extend(test_d_eugenio())
    all_results.extend(test_cuatro_vientos())
    all_results.extend(test_casillero())
    all_results.extend(test_alamos())
    all_results.extend(test_trivento())
    all_results.extend(test_terrazas())

    # Variety gate tests
    all_results.extend(test_variety_toro_centenario())
    all_results.extend(test_variety_cross_grape())
    all_results.extend(test_variety_compound_conflicts())
    all_results.extend(test_variety_same_grape())
    all_results.extend(test_variety_no_grape_in_ocr())
    all_results.extend(test_variety_style_conflict())

    # Combined gate tests
    all_results.extend(test_combined_krug_ruinart())
    all_results.extend(test_combined_contada_1926())
    all_results.extend(test_combined_montGras_aura_cross_grape())

    # Recall helper tests
    all_results.extend(test_collapse_initials())
    all_results.extend(test_build_scoring_name())

    # Recall positive tests (scoring with clean name)
    all_results.extend(test_recall_d_eugenio())
    all_results.extend(test_recall_cuatro_vientos())
    all_results.extend(test_recall_freixenet_ice())

    passed = sum(all_results)
    total = len(all_results)

    print(f"\n{'='*60}")
    print(f"RESULTADO: {passed}/{total} casos passaram")
    print(f"{'='*60}")

    return 0 if all(all_results) else 1


if __name__ == "__main__":
    sys.exit(main())
