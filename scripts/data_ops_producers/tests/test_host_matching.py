"""Testes do matching por host normalizado do producer commerce.

Cobertura-chave: falso positivo de substring (`mazon.com.br` vs `amazon.com.br`)
e aceitacao legitima de subdominio (`shop.amazon.com.br`).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = ROOT / "scripts" / "data_ops_producers"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from build_commerce_artifact import _host_eligible, normalize_host  # type: ignore


def test_normalize_host_com_protocolo():
    assert normalize_host("https://amazon.com.br/produto/xyz") == "amazon.com.br"


def test_normalize_host_sem_protocolo():
    assert normalize_host("amazon.com.br/x") == "amazon.com.br"


def test_normalize_host_com_www():
    assert normalize_host("https://www.amazon.com.br") == "amazon.com.br"


def test_normalize_host_vazio():
    assert normalize_host("") is None
    assert normalize_host(None) is None


def test_eligible_igualdade_exata():
    assert _host_eligible("amazon.com.br", {"amazon.com.br"}) is True


def test_eligible_subdominio_legitimo():
    assert _host_eligible("shop.amazon.com.br", {"amazon.com.br"}) is True


def test_rejeita_falso_positivo_substring_sem_boundary():
    # `mazon.com.br` NAO deve bater com `amazon.com.br`
    assert _host_eligible("mazon.com.br", {"amazon.com.br"}) is False


def test_rejeita_dominio_totalmente_diferente():
    assert _host_eligible("outroSite.com", {"amazon.com.br"}) is False


def test_rejeita_sufixo_coincidente_sem_boundary():
    # `malamazon.com.br` tambem NAO pode bater com `amazon.com.br`
    assert _host_eligible("malamazon.com.br", {"amazon.com.br"}) is False


def test_eligible_com_loja_sem_www_e_url_com_www():
    assert _host_eligible(normalize_host("https://www.winesite.com/xyz"), {"winesite.com"}) is True


def test_multiplas_lojas_na_allowlist():
    hosts = {"amazon.com.br", "mercadolivre.com.br"}
    assert _host_eligible("amazon.com.br", hosts) is True
    assert _host_eligible("mercadolivre.com.br", hosts) is True
    assert _host_eligible("amazonas.com.br", hosts) is False


def test_host_none_nao_eh_eligivel():
    assert _host_eligible(None, {"amazon.com.br"}) is False
    assert _host_eligible("", {"amazon.com.br"}) is False
