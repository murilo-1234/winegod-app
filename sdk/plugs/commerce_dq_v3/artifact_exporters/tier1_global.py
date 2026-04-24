"""Exporter Tier1 global (semanal, APIs/sitemap deterministico).

Le `vinhos_{pais}_fontes` filtrando pelas lojas cujo
`lojas_scraping.metodo_recomendado` seja um metodo Tier1:

- api_shopify, api_woocommerce, api_vtex
- sitemap_html, sitemap_jsonld, sitemap_woocommerce, sitemap_vtex,
  sitemap_nuvemshop, sitemap_prestashop, sitemap_parse

Matching host com boundary real (ver `build_commerce_artifact.py`).
`pipeline_family=tier1`. Saida em `reports/data_ops_artifacts/tier1/`.

Se nao houver lojas Tier1 cadastradas, termina com `reason=no_producer_tier1_global`
(stub honesto - o scraper Codex pode nao ter sido setado ainda).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .base import (
    REPO_ROOT,
    BATCH_SIZE,
    ExportRow,
    ExporterResult,
    build_item,
    write_artifact,
    _normalize_host,
)
from ._db import connect_readonly, list_country_tables, list_lojas_by_method


PIPELINE_FAMILY = "tier1"
SOURCE_LABEL = "tier1_global"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "data_ops_artifacts" / "tier1"
TIER1_METHODS = [
    "api_shopify",
    "api_woocommerce",
    "api_vtex",
    "sitemap_html",
    "sitemap_jsonld",
    "sitemap_woocommerce",
    "sitemap_vtex",
    "sitemap_nuvemshop",
    "sitemap_prestashop",
    "sitemap_parse",
]


def _host_eligible(fonte_host: str | None, loja_hosts: set[str]) -> bool:
    if not fonte_host:
        return False
    if fonte_host in loja_hosts:
        return True
    for h in loja_hosts:
        if fonte_host.endswith("." + h):
            return True
    return False


@dataclass
class Tier1GlobalConfig:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    max_items: int | None = None
    country_filter: list[str] | None = None
    methods: list[str] = field(default_factory=lambda: list(TIER1_METHODS))
    batch_size: int = BATCH_SIZE
    dsn: str | None = None
    country_code_filter: str | None = None  # alias de country_filter[0] se 1 pais
    # Sharding (plano 3 fases): permite limitar a 1 tabela-pais e faixa fonte_id.
    source_table_filter: str | None = None  # ex: "vinhos_us_fontes"
    min_fonte_id: int | None = None
    max_fonte_id: int | None = None
    shard_id: str | None = None  # label pro manifest


def _iter_rows(
    conn,
    cfg: Tier1GlobalConfig,
    pais_codigo: str | None = None,
) -> Iterator[ExportRow]:
    """Itera rows de todos os paises (ou so pais_codigo) que cruzam Tier1."""

    tables = list_country_tables(conn)
    with conn.cursor() as cur:
        for base in tables:
            cc = base.split("_", 1)[1]
            if cfg.country_filter and cc.upper() not in [c.upper() for c in cfg.country_filter]:
                continue
            if pais_codigo and cc.upper() != pais_codigo.upper():
                continue
            source_table = f"{base}_fontes"
            if cfg.source_table_filter and source_table != cfg.source_table_filter:
                continue
            host_to_loja = list_lojas_by_method(
                conn, methods=cfg.methods, pais_codigo=cc.upper()
            )
            if not host_to_loja:
                continue
            loja_hosts = set(host_to_loja.keys())
            range_clause = ""
            range_params: list = []
            if cfg.min_fonte_id is not None:
                range_clause += " AND f.id >= %s"
                range_params.append(cfg.min_fonte_id)
            if cfg.max_fonte_id is not None:
                range_clause += " AND f.id <= %s"
                range_params.append(cfg.max_fonte_id)
            sql = f"""
                SELECT
                  v.id,
                  v.nome,
                  COALESCE(v.vinicola_nome, v.produtor_normalizado),
                  v.safra,
                  f.preco,
                  f.moeda,
                  f.url_original,
                  f.fonte,
                  v.pais_codigo,
                  COALESCE(f.atualizado_em, f.descoberto_em, v.atualizado_em, v.descoberto_em) AS captured_at,
                  f.id
                FROM public.{source_table} f
                JOIN public.{base} v ON v.id = f.vinho_id
                WHERE f.url_original IS NOT NULL{range_clause}
                ORDER BY f.id DESC
            """
            offset = 0
            while True:
                cur.execute(sql + " LIMIT %s OFFSET %s", range_params + [cfg.batch_size, offset])
                rows = cur.fetchall()
                if not rows:
                    break
                for r in rows:
                    url = r[6]
                    host = _normalize_host(url)
                    if not _host_eligible(host, loja_hosts):
                        continue
                    loja = host_to_loja.get(host)
                    if loja is None:
                        for loja_host, loja_info in host_to_loja.items():
                            if host and host.endswith("." + loja_host):
                                loja = loja_info
                                break
                    yield ExportRow(
                        vinho_id=r[0],
                        nome=r[1],
                        produtor=r[2],
                        safra=r[3],
                        preco=r[4],
                        moeda=r[5],
                        url_original=url,
                        fonte=r[7],
                        pais_codigo=r[8],
                        store_name=(loja or {}).get("nome"),
                        store_domain=host,
                        captured_at=r[9],
                        source_table=source_table,
                        fonte_id=r[10],
                    )
                if len(rows) < cfg.batch_size:
                    break
                offset += cfg.batch_size


def run_export(cfg: Tier1GlobalConfig | None = None) -> ExporterResult:
    cfg = cfg or Tier1GlobalConfig()
    if cfg.min_fonte_id is not None and cfg.max_fonte_id is not None:
        if cfg.min_fonte_id > cfg.max_fonte_id:
            return ExporterResult(
                ok=False,
                reason="shard_range_invalid",
                notes=[f"min_fonte_id={cfg.min_fonte_id} > max_fonte_id={cfg.max_fonte_id}"],
            )
    started_at = datetime.now(timezone.utc)
    run_id = f"{SOURCE_LABEL}_{started_at.strftime('%Y%m%d_%H%M%S')}"
    shard_spec = {
        "shard_id": cfg.shard_id,
        "source_table": cfg.source_table_filter,
        "min_fonte_id": cfg.min_fonte_id,
        "max_fonte_id": cfg.max_fonte_id,
    } if (cfg.shard_id or cfg.source_table_filter or cfg.min_fonte_id is not None or cfg.max_fonte_id is not None) else None
    try:
        with connect_readonly(cfg.dsn) as conn:
            # Precheck rapido: existe loja Tier1?
            total_lojas = len(list_lojas_by_method(conn, methods=cfg.methods))
            if total_lojas == 0:
                return ExporterResult(
                    ok=False,
                    reason="no_producer_tier1_global",
                    notes=[
                        "nenhuma_loja_em_lojas_scraping_com_metodo_tier1",
                        f"metodos_checados={cfg.methods}",
                    ],
                )

            def items_gen():
                for row in _iter_rows(conn, cfg):
                    yield build_item(
                        row,
                        pipeline_family=PIPELINE_FAMILY,
                        run_id=run_id,
                    )
            result = write_artifact(
                items=items_gen(),
                output_dir=cfg.output_dir,
                source_label=SOURCE_LABEL,
                pipeline_family=PIPELINE_FAMILY,
                run_id=run_id,
                started_at=started_at,
                input_scope=",".join(cfg.country_filter) if cfg.country_filter else "global",
                max_items=cfg.max_items,
                shard_spec=shard_spec,
            )
    except RuntimeError as exc:
        return ExporterResult(ok=False, reason=f"dsn_missing:{exc}")
    return result


def run_export_from_rows(
    rows: list[ExportRow],
    *,
    output_dir: Path,
    max_items: int | None = None,
    started_at: datetime | None = None,
) -> ExporterResult:
    started_at = started_at or datetime.now(timezone.utc)
    run_id = f"{SOURCE_LABEL}_{started_at.strftime('%Y%m%d_%H%M%S')}"
    items = (build_item(row, pipeline_family=PIPELINE_FAMILY, run_id=run_id) for row in rows)
    return write_artifact(
        items=items,
        output_dir=output_dir,
        source_label=SOURCE_LABEL,
        pipeline_family=PIPELINE_FAMILY,
        run_id=run_id,
        started_at=started_at,
        input_scope="fixture",
        max_items=max_items,
    )
