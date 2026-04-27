"""Testes da funcao normalize_wine_type do plug commerce_dq_v3."""

from sdk.plugs.commerce_dq_v3.normalizers import normalize_wine_type


def test_lowercase_canonico_passa_intocado():
    for tipo in ("tinto", "branco", "rose", "espumante", "fortificado", "sobremesa"):
        assert normalize_wine_type(tipo) == tipo


def test_capitalizado_normaliza_para_lowercase():
    assert normalize_wine_type("Tinto") == "tinto"
    assert normalize_wine_type("Branco") == "branco"
    assert normalize_wine_type("Espumante") == "espumante"
    assert normalize_wine_type("Sobremesa") == "sobremesa"
    assert normalize_wine_type("Fortificado") == "fortificado"


def test_caps_full_uppercase():
    assert normalize_wine_type("TINTO") == "tinto"
    assert normalize_wine_type("BRANCO") == "branco"
    assert normalize_wine_type("ROSE") == "rose"


def test_acento_e_removido():
    assert normalize_wine_type("Rose") == "rose"
    assert normalize_wine_type("rose") == "rose"
    assert normalize_wine_type("ROSE") == "rose"


def test_aliases_multilingua():
    assert normalize_wine_type("Red") == "tinto"
    assert normalize_wine_type("white") == "branco"
    assert normalize_wine_type("Rosado") == "rose"
    assert normalize_wine_type("Rosato") == "rose"
    assert normalize_wine_type("sparkling") == "espumante"
    assert normalize_wine_type("Fortified") == "fortificado"
    assert normalize_wine_type("dessert") == "sobremesa"


def test_desconhecido_passa():
    assert normalize_wine_type("desconhecido") == "desconhecido"
    assert normalize_wine_type("Desconhecido") == "desconhecido"


def test_strip_espacos():
    assert normalize_wine_type("  tinto  ") == "tinto"
    assert normalize_wine_type("\tRose\n") == "rose"


def test_invalido_retorna_none():
    assert normalize_wine_type("vinho fortificado natural") is None
    assert normalize_wine_type("xyz") is None
    assert normalize_wine_type("123") is None


def test_vazio_ou_none_retorna_none():
    assert normalize_wine_type(None) is None
    assert normalize_wine_type("") is None
    assert normalize_wine_type("   ") is None


def test_aceita_int_e_float_via_str():
    # robustez contra entrada inesperada
    assert normalize_wine_type(123) is None
