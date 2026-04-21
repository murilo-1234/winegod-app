"""Testes do classificador deterministico de prontidao para ingestao.

Fase 1 do `WINEGOD_PRE_INGEST_ROUTER`. Puro — sem banco, sem HTTP,
sem Gemini.

Roda com qualquer um destes:
    cd backend && python -m tests.test_ingest_classifier
    python -m pytest backend/tests/test_ingest_classifier.py -v
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))  # backend/
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "..", "scripts"))

from _ingest_classifier import classify  # noqa: E402


# ============ READY ============

def test_ready_vinho_completo_com_pais():
    s, r = classify({
        "nome": "Catena Alta Malbec",
        "produtor": "Catena Zapata",
        "safra": "2020",
        "pais": "ar",
    })
    assert s == "ready", f"{s} {r}"
    assert "ready_all_conditions_met" in r


def test_ready_vinho_completo_com_regiao():
    s, r = classify({
        "nome": "Premier Grand Cru Chateau",
        "produtor": "Chateau Exemplo",
        "regiao": "Bordeaux",
    })
    assert s == "ready", f"{s} {r}"


def test_ready_vinho_com_ean_mesmo_sem_pais():
    s, r = classify({
        "nome": "Gran Reserva Privada",
        "produtor": "Vinicola Importante",
        "ean_gtin": "7891234567890",
    })
    assert s == "ready", f"{s} {r}"


def test_ready_com_subregiao_apenas():
    s, r = classify({
        "nome": "Cuvee Especial Gran Reserva",
        "produtor": "Vinicola Alfa",
        "sub_regiao": "Medoc",
    })
    assert s == "ready", f"{s} {r}"


def test_ready_nome_longo_produtor_forte_pais_iso():
    s, r = classify({
        "nome": "Chateau Margaux Premier Grand Cru Classe",
        "produtor": "Chateau Margaux",
        "safra": "2015",
        "pais": "FR",
        "tipo": "tinto",
    })
    assert s == "ready", f"{s} {r}"


# ============ NEEDS_ENRICHMENT ============

def test_needs_enrichment_nome_forte_sem_produtor():
    s, r = classify({
        "nome": "Chateau Margaux Premier Grand Cru Classe",
    })
    assert s == "needs_enrichment", f"{s} {r}"
    assert any("nome_forte_sem_produtor" in x for x in r)


def test_needs_enrichment_produtor_sem_pais_regiao_ean():
    s, r = classify({
        "nome": "Grande Reserva Tinto Especial",
        "produtor": "Vinicola Exemplo Forte",
        "safra": "2020",
    })
    assert s == "needs_enrichment", f"{s} {r}"
    assert any("produtor_sem_pais_regiao_ean" in x for x in r)


def test_needs_enrichment_nome_com_regiao_sem_produtor():
    s, r = classify({
        "nome": "Chateauneuf du Pape Rhone Valley Reserve",
        "regiao": "Rhone Valley",
    })
    assert s == "needs_enrichment", f"{s} {r}"


def test_needs_enrichment_ean_com_nome_fraco():
    s, r = classify({
        "nome": "Red",
        "ean_gtin": "7891234567890",
    })
    assert s == "needs_enrichment", f"{s} {r}"
    assert any("ean_com_nome_fraco" in x for x in r)


def test_needs_enrichment_descricao_longa():
    desc = (
        "Vinho elaborado em regiao tradicional, com uvas colhidas manualmente "
        "e estagio de 18 meses em barricas de carvalho frances. Notas de frutas "
        "vermelhas, especiarias e taninos macios."
    )
    s, r = classify({
        "nome": "Cuvee Prestige",
        "produtor": "Vinicola Do Vale",
        "descricao": desc,
    })
    # Tem produtor mas nao tem geo -> needs_enrichment via produtor
    # e tambem tem descricao longa como ancora adicional
    assert s == "needs_enrichment", f"{s} {r}"


def test_needs_enrichment_nome_generico_mas_produtor_forte():
    s, r = classify({
        "nome": "Red",
        "produtor": "Vinicola Catena Zapata",
    })
    assert s == "needs_enrichment", f"{s} {r}"


def test_needs_enrichment_uva_hint_no_nome():
    s, r = classify({
        "nome": "Malbec Reserva Premium Argentino",
        "produtor": "Vinicola do Vale",
    })
    # Tem produtor + uva hint, faltando geo -> needs_enrichment
    assert s == "needs_enrichment", f"{s} {r}"


# ============ NOT_WINE (primeiro filtro deterministico) ============

def test_not_wine_whisky():
    s, r = classify({"nome": "Johnnie Walker Black Label Whisky 750ml"})
    assert s == "not_wine", f"{s} {r}"
    assert any("whisky" in x.lower() for x in r)


def test_not_wine_vodka():
    s, r = classify({"nome": "Absolut Vodka Citron 700ml"})
    assert s == "not_wine", f"{s} {r}"


def test_not_wine_cerveja():
    s, r = classify({"nome": "Heineken Beer 355ml Pack of 6"})
    assert s == "not_wine", f"{s} {r}"


def test_not_wine_kit_case():
    s, r = classify({"nome": "Caja de Vinos Navidenas 12 unidades"})
    assert s == "not_wine", f"{s} {r}"


def test_not_wine_gramatura():
    s, r = classify({"nome": "Cheese Platter 450g Gift"})
    assert s == "not_wine", f"{s} {r}"


def test_not_wine_volume_nao_padrao():
    s, r = classify({"nome": "Rose Water Fee Brothers 4oz"})
    assert s == "not_wine", f"{s} {r}"


def test_not_wine_abv_fora():
    # ABV > 15% tipico de fortificado legitimo... mas se vier 40% e claro spirit
    s, r = classify({"nome": "Grappa Premium 40% ABV"})
    assert s == "not_wine", f"{s} {r}"


def test_not_wine_cachaca():
    s, r = classify({"nome": "Cachaca Ypioca 51 Gold"})
    assert s == "not_wine", f"{s} {r}"


# ============ UNCERTAIN ============

def test_uncertain_nome_e_produtor_vazios():
    s, r = classify({})
    assert s == "uncertain", f"{s} {r}"
    assert any("nome_e_produtor_vazios" in x for x in r)


def test_uncertain_nome_curto_sem_ean():
    s, r = classify({"nome": "Ab"})
    assert s == "uncertain", f"{s} {r}"


def test_uncertain_nome_generico_sem_produtor_sem_ean():
    s, r = classify({"nome": "Red Wine"})
    assert s == "uncertain", f"{s} {r}"
    assert any("nome_generico" in x for x in r)


def test_uncertain_nome_e_produtor_ambos_vazios_explicito():
    s, r = classify({"nome": "", "produtor": ""})
    assert s == "uncertain", f"{s} {r}"


def test_uncertain_house_white_sem_ancora():
    s, r = classify({"nome": "House White"})
    assert s == "uncertain", f"{s} {r}"


def test_uncertain_cuvee_reserva_solo():
    # Nome composto so de termos genericos, sem produtor/ean/geo
    s, r = classify({"nome": "Cuvee Reserva Brut"})
    assert s == "uncertain", f"{s} {r}"
    assert any("nome_generico" in x for x in r)


# ============ Edges ============

def test_not_a_dict_returns_uncertain():
    s, r = classify(None)  # type: ignore[arg-type]
    assert s == "uncertain"
    assert "item_nao_e_dict" in r


def test_nome_com_safra_em_latim_nao_trava_ready():
    # "MMXI" sozinho seria ambiguo, mas com produtor + pais passa
    s, r = classify({
        "nome": "MMXI Special Edition Blend",
        "produtor": "Chateau Exemplo",
        "pais": "fr",
    })
    assert s == "ready", f"{s} {r}"


def test_ean_sem_nome_sem_produtor_vai_pra_enrichment():
    s, r = classify({"ean_gtin": "7891234567890"})
    assert s == "needs_enrichment", f"{s} {r}"


def test_ready_com_acentos_no_nome():
    s, r = classify({
        "nome": "Côtes du Rhône Réserve Spéciale",
        "produtor": "Domaine Exemplé",
        "pais": "fr",
    })
    assert s == "ready", f"{s} {r}"


if __name__ == "__main__":
    tests = sorted(name for name in globals() if name.startswith("test_"))
    passed = failed = 0
    for name in tests:
        try:
            globals()[name]()
            print(f"  PASS {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
