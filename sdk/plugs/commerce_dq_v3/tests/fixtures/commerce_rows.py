"""Fixtures sinteticas de rows commerce para testar exporters sem DB.

Cada helper retorna uma lista de `ExportRow` simulando saida do join
`vinhos_<pais>_fontes + vinhos_<pais> [+ lojas_scraping]` que o exporter
consumiria do `winegod_db`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sdk.plugs.commerce_dq_v3.artifact_exporters.base import ExportRow


def _dt(year: int, month: int = 4, day: int = 1, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)


def amazon_mirror_rows(n: int = 5) -> list[ExportRow]:
    out: list[ExportRow] = []
    for i in range(n):
        out.append(
            ExportRow(
                vinho_id=100 + i,
                nome=f"Mirror Wine {i}",
                produtor=f"Mirror Producer {i % 3}",
                safra=2020 + (i % 4),
                preco=15.90 + i,
                moeda="USD" if i % 2 == 0 else "BRL",
                url_original=f"https://www.amazon.com/dp/ASIN{i:04d}",
                fonte="amazon_playwright",
                pais_codigo="US" if i % 2 == 0 else "BR",
                store_name="Amazon US" if i % 2 == 0 else "Amazon BR",
                store_domain="amazon.com" if i % 2 == 0 else "amazon.com.br",
                captured_at=_dt(2026, 4, 1 + (i % 10)),
                source_table="vinhos_us_fontes" if i % 2 == 0 else "vinhos_br_fontes",
                fonte_id=9000 + i,
            )
        )
    return out


def amazon_legacy_rows(n: int = 5) -> list[ExportRow]:
    fontes = ["amazon", "amazon_scraper", "amazon_scrapingdog"]
    out: list[ExportRow] = []
    for i in range(n):
        out.append(
            ExportRow(
                vinho_id=200 + i,
                nome=f"Legacy Wine {i}",
                produtor=f"Legacy Producer {i % 3}",
                safra=2015 + (i % 5),
                preco=19.90 + i,
                moeda="USD",
                url_original=f"https://www.amazon.com/legacy/ASIN{i:04d}",
                fonte=fontes[i % len(fontes)],
                pais_codigo="US",
                store_name="Amazon US",
                store_domain="amazon.com",
                captured_at=_dt(2025, 10, 1 + (i % 10)),
                source_table="vinhos_us_fontes",
                fonte_id=7000 + i,
            )
        )
    return out


def tier1_rows(n: int = 5) -> list[ExportRow]:
    out: list[ExportRow] = []
    fontes = ["shopify", "woocommerce", "vtex"]
    for i in range(n):
        out.append(
            ExportRow(
                vinho_id=300 + i,
                nome=f"Tier1 Wine {i}",
                produtor=f"Tier1 Producer {i % 3}",
                safra=2019 + (i % 5),
                preco=25.00 + i,
                moeda="USD",
                url_original=f"https://shop-{i}.example.com/wine/{i}",
                fonte=fontes[i % len(fontes)],
                pais_codigo="US",
                store_name=f"Shop {i}",
                store_domain=f"shop-{i}.example.com",
                captured_at=_dt(2026, 4, 15),
                source_table="vinhos_us_fontes",
                fonte_id=4000 + i,
            )
        )
    return out


def tier2_global_rows(n: int = 5) -> list[ExportRow]:
    out: list[ExportRow] = []
    for i in range(n):
        out.append(
            ExportRow(
                vinho_id=400 + i,
                nome=f"Tier2 Global Wine {i}",
                produtor=f"Tier2 Producer {i % 3}",
                safra=2018 + (i % 6),
                preco=32.50 + i,
                moeda="EUR",
                url_original=f"https://store-t2-{i}.eu/wine/{i}",
                fonte="opus" if i % 2 == 0 else "grok",
                pais_codigo="FR",
                store_name=f"Tier2 Store {i}",
                store_domain=f"store-t2-{i}.eu",
                captured_at=_dt(2026, 4, 10),
                source_table="vinhos_fr_fontes",
                fonte_id=5000 + i,
            )
        )
    return out


def tier2_br_rows(n: int = 5) -> list[ExportRow]:
    out: list[ExportRow] = []
    for i in range(n):
        out.append(
            ExportRow(
                vinho_id=500 + i,
                nome=f"Tier2 BR Wine {i}",
                produtor=f"Produtor BR {i % 3}",
                safra=2020 + (i % 4),
                preco=89.90 + i,
                moeda="BRL",
                url_original=f"https://loja-br-{i}.com.br/vinho/{i}",
                fonte="opus",
                pais_codigo="BR",
                store_name=f"Loja BR {i}",
                store_domain=f"loja-br-{i}.com.br",
                captured_at=_dt(2026, 4, 12),
                source_table="vinhos_br_fontes",
                fonte_id=6000 + i,
            )
        )
    return out


def row_with_missing_fields() -> ExportRow:
    """Row sem `nome`/`produtor` (deve ser filtrada pelo write_artifact)."""

    return ExportRow(
        vinho_id=999,
        nome="",
        produtor="",
        safra=None,
        preco=None,
        moeda=None,
        url_original="https://example.com/x",
        fonte="amazon_playwright",
        pais_codigo="US",
        store_name=None,
        store_domain=None,
        captured_at=_dt(2026, 4, 1),
        source_table="vinhos_us_fontes",
        fonte_id=1,
    )


def duplicate_url_rows() -> list[ExportRow]:
    """2 rows com mesma URL - dedup deve pegar."""

    base = amazon_mirror_rows(1)[0]
    dup = ExportRow(
        vinho_id=base.vinho_id + 1,
        nome=base.nome + " V2",
        produtor=base.produtor,
        safra=base.safra,
        preco=base.preco + 1.0,
        moeda=base.moeda,
        url_original=base.url_original,
        fonte=base.fonte,
        pais_codigo=base.pais_codigo,
        store_name=base.store_name,
        store_domain=base.store_domain,
        captured_at=base.captured_at,
        source_table=base.source_table,
        fonte_id=(base.fonte_id or 0) + 1,
    )
    return [base, dup]
