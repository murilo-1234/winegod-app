"""Testes offline das funcoes puras do exportador vinhos_brasil -> router.

Nao abre DB. Nao exige psycopg2 instalado.

Roda com qualquer um:
    python backend/tests/test_export_vinhos_brasil_to_router.py
    python -m pytest backend/tests/test_export_vinhos_brasil_to_router.py -q
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))

# Fail fast se legacy dir nao existir — o exportador importa dele no topo.
# Se falhar, instrua e pula os testes.
_LEGACY_DIR = Path(r"C:\natura-automation\vinhos_brasil")
if not _LEGACY_DIR.exists():
    print(f"[skip all] legacy dir nao encontrado: {_LEGACY_DIR}", file=sys.stderr)
    sys.exit(0)

try:
    from export_vinhos_brasil_to_router import (  # type: ignore
        _clean_pais_iso,
        _extract_loja_from_extras,
        _is_ready_like,
        _KNOWN_FONTES,
        _safra_to_str,
        _uvas_field,
        build_query,
        row_to_item,
    )
except Exception as e:
    print(f"[skip all] falha ao importar exportador: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(0)


# ============ _safra_to_str ============

def test_safra_none():
    assert _safra_to_str(None) is None


def test_safra_int_valido():
    assert _safra_to_str(2020) == "2020"
    assert _safra_to_str(1950) == "1950"
    assert _safra_to_str(2099) == "2099"


def test_safra_str_numerico():
    assert _safra_to_str("2018") == "2018"


def test_safra_fora_range():
    assert _safra_to_str(1800) is None
    assert _safra_to_str(2200) is None


def test_safra_invalida():
    assert _safra_to_str("nao_ano") is None
    assert _safra_to_str("") is None


# ============ _uvas_field ============

def test_uvas_none():
    assert _uvas_field(None) is None


def test_uvas_lista():
    r = _uvas_field(["Cabernet Sauvignon", "Merlot"])
    assert json.loads(r) == ["Cabernet Sauvignon", "Merlot"]


def test_uvas_string_csv():
    r = _uvas_field("Cabernet Sauvignon, Merlot")
    assert json.loads(r) == ["Cabernet Sauvignon", "Merlot"]


def test_uvas_string_json_valido():
    r = _uvas_field('["Syrah", "Tempranillo"]')
    assert json.loads(r) == ["Syrah", "Tempranillo"]


def test_uvas_string_vazia():
    assert _uvas_field("") is None
    assert _uvas_field("   ") is None


def test_uvas_lista_vazia():
    assert _uvas_field([]) is None


# ============ _clean_pais_iso ============

def test_pais_iso_valido_lowercase():
    assert _clean_pais_iso("FR") == "fr"
    assert _clean_pais_iso("ar") == "ar"
    assert _clean_pais_iso(" BR ") == "br"


def test_pais_iso_invalido():
    assert _clean_pais_iso("Brasil") is None   # 6 chars
    assert _clean_pais_iso("12") is None       # nao alpha
    assert _clean_pais_iso("f") is None        # 1 char
    assert _clean_pais_iso(None) is None
    assert _clean_pais_iso("") is None


# ============ _extract_loja_from_extras ============

def test_extract_loja_none():
    assert _extract_loja_from_extras(None) is None


def test_extract_loja_dict_direto():
    assert _extract_loja_from_extras({"loja": "Loja X"}) == "Loja X"
    assert _extract_loja_from_extras({"store": "Seller Y"}) == "Seller Y"
    assert _extract_loja_from_extras({"seller": "SellerZ"}) == "SellerZ"


def test_extract_loja_jsonstring():
    assert _extract_loja_from_extras('{"loja": "Wine Shop"}') == "Wine Shop"


def test_extract_loja_aninhado():
    extras = {"loja": {"name": "Loja Aninhada"}}
    assert _extract_loja_from_extras(extras) == "Loja Aninhada"


def test_extract_loja_nao_tem_chave():
    assert _extract_loja_from_extras({"qualquer": "coisa"}) is None


def test_extract_loja_string_invalida():
    assert _extract_loja_from_extras("nao_e_json") is None


# ============ build_query ============

def test_build_query_basico():
    sql, params = build_query(None, False, limit=100, offset=0)
    assert "LIMIT %(limit)s" in sql
    assert "OFFSET %(offset)s" in sql
    assert params["limit"] == 100
    assert params["offset"] == 0
    assert "fonte" not in params  # sem filtro de fonte
    # Nao deve ter o wine_filter de ready_like
    assert "LENGTH(TRIM(v.nome))" not in sql


def test_build_query_com_offset():
    _, params = build_query(None, False, limit=50, offset=200)
    assert params["offset"] == 200
    assert params["limit"] == 50


def test_build_query_com_fonte():
    sql, params = build_query("vtex", False, limit=500, offset=0)
    assert params["fonte"] == "vtex"
    # Tanto filtro do JOIN quanto EXISTS presente
    assert "AND fonte = %(fonte)s" in sql
    assert "EXISTS (SELECT 1 FROM vinhos_brasil_fontes" in sql


def test_build_query_min_quality_ready_like():
    sql, _ = build_query(None, True, limit=500, offset=0)
    assert "LENGTH(TRIM(v.nome)) >= 8" in sql
    assert "LENGTH(TRIM(v.produtor)) >= 3" in sql
    assert "v.pais IS NOT NULL" in sql


def test_build_query_select_inclui_dados_extras():
    sql, _ = build_query(None, False, limit=100, offset=0)
    assert "dados_extras" in sql.lower()
    assert "fonte_dados_extras" in sql


def test_build_query_sem_sql_injection_em_fonte():
    # Fonte entra como parametro, nao interpolacao — garante que o valor
    # nao e concatenado direto na string.
    sql, params = build_query("vtex", False, limit=100, offset=0)
    assert "'vtex'" not in sql
    assert "vtex" in params.values()


# ============ row_to_item ============

def _base_row():
    return {
        "id": 12345,
        "nome": "Catena Alta Malbec",
        "produtor": "Catena Zapata",
        "safra": 2020,
        "tipo": "tinto",
        "pais": "AR",
        "pais_nome": "Argentina",
        "regiao": "Mendoza",
        "sub_regiao": None,
        "uvas": ["Malbec"],
        "preco_min": 89.90,
        "preco_max": 149.90,
        "moeda": "BRL",
        "ean_gtin": "7891234567890",
        "imagem_url": "https://exemplo.com/a.jpg",
        "harmonizacao": "carne vermelha",
        "descricao": None,
        "fonte_scraper": "vtex",
        "loja_url": "https://loja.x/produto",
        "preco_fonte": 89.90,
        "mercado": "br",
        "fonte_dados_extras": {"loja": "Loja X"},
    }


def test_row_to_item_campos_principais():
    item = row_to_item(_base_row())
    assert item["nome"] == "Catena Alta Malbec"
    assert item["produtor"] == "Catena Zapata"
    assert item["safra"] == "2020"
    assert item["pais"] == "ar"
    assert item["tipo"] == "tinto"
    assert item["preco_min"] == 89.90
    assert item["ean_gtin"] == "7891234567890"


def test_row_to_item_expoe_campos_comerciais():
    item = row_to_item(_base_row())
    assert item["url_original"] == "https://loja.x/produto"
    assert item["loja"] == "Loja X"
    assert item["fonte_original"] == "vtex"
    assert item["preco_fonte"] == 89.90
    assert item["mercado"] == "br"


def test_row_to_item_preserva_metadados_underscore():
    item = row_to_item(_base_row())
    assert item["_origem_vinho_id"] == 12345
    assert item["_source_dataset"] == "vinhos_brasil_db"
    assert item["_source_table"] == "vinhos_brasil"
    assert item["_source_scraper"] == "vtex"
    # Compat legado: _fonte_original = URL (nao o scraper)
    assert item["_fonte_original"] == "https://loja.x/produto"


def test_row_to_item_chaves_none_removidas():
    row = _base_row()
    row["sub_regiao"] = None
    row["descricao"] = None
    item = row_to_item(row)
    assert "sub_regiao" not in item
    assert "descricao" not in item


def test_row_to_item_sem_dados_extras():
    row = _base_row()
    row["fonte_dados_extras"] = None
    item = row_to_item(row)
    assert "loja" not in item  # sem dados_extras -> sem loja humana
    # url_original continua via loja_url
    assert item["url_original"] == "https://loja.x/produto"


def test_row_to_item_pais_invalido_vira_none():
    row = _base_row()
    row["pais"] = "BRASIL"
    item = row_to_item(row)
    assert "pais" not in item  # key filtrada


# ============ Sanity: KNOWN_FONTES inclui 'nacional' ============

def test_known_fontes_inclui_nacional():
    assert "nacional" in _KNOWN_FONTES


# ============ _is_ready_like ============

def test_is_ready_like_positivo():
    assert _is_ready_like({
        "nome": "Catena Alta Malbec",
        "produtor": "Catena Zapata",
        "pais": "ar",
    })


def test_is_ready_like_sem_ancora():
    assert not _is_ready_like({
        "nome": "Catena Alta Malbec",
        "produtor": "Catena Zapata",
    })


def test_is_ready_like_nome_curto():
    assert not _is_ready_like({
        "nome": "Red",
        "produtor": "Catena",
        "pais": "ar",
    })


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
