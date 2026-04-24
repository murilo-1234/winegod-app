"""Exporter Tier2 global (semanal, Playwright+IA, pais != br).

Le `vinhos_{pais}_fontes` filtrando lojas cujo
`lojas_scraping.metodo_recomendado='playwright_ia'` (Tier2 real).

Colapsa os 5 chats historicos (chat1..5) em artefato unico. Exclui `br`
(tratado em `tier2_br.py`). `pipeline_family=tier2`. Saida em
`reports/data_ops_artifacts/tier2_global/`.

Se nao houver loja Tier2 cadastrada (fora BR), termina com
`reason=no_producer_tier2_global` honesto.
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


PIPELINE_FAMILY = "tier2"
SOURCE_LABEL = "tier2_global_artifact"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "data_ops_artifacts" / "tier2_global"
TIER2_METHODS = ["playwright_ia"]
EXCLUDED_COUNTRIES = {"br"}


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
class Tier2GlobalConfig:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    max_items: int | None = None
    country_filter: list[str] | None = None
    methods: list[str] = field(default_factory=lambda: list(TIER2_METHODS))
    batch_size: int = BATCH_SIZE
    dsn: str | None = None
    excluded_countries: set[str] = field(default_factory=lambda: set(EXCLUDED_COUNTRIES))


def _iter_rows(conn, cfg: Tier2GlobalConfig) -> Iterator[ExportRow]:
    tables = list_country_tables(conn)
    with conn.cursor() as cur:
        for base in tables:
            cc = base.split("_", 1)[1]
            if cc in cfg.excluded_countries:
                continue
            if cfg.country_filter and cc.upper() not in [c.upper() for c in cfg.country_filter]:
                continue
            host_to_loja = list_lojas_by_method(
                conn, methods=cfg.methods, pais_codigo=cc.upper()
            )
            if not host_to_loja:
                continue
            loja_hosts = set(host_to_loja.keys())
            source_table = f"{base}_fontes"
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
                WHERE f.url_original IS NOT NULL
                ORDER BY f.id DESC
            """
            offset = 0
            while True:
                cur.execute(sql + " LIMIT %s OFFSET %s", [cfg.batch_size, offset])
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


def run_export(cfg: Tier2GlobalConfig | None = None) -> ExporterResult:
    cfg = cfg or Tier2GlobalConfig()
    started_at = datetime.now(timezone.utc)
    run_id = f"{SOURCE_LABEL}_{started_at.strftime('%Y%m%d_%H%M%S')}"
    try:
        with connect_readonly(cfg.dsn) as conn:
            total_lojas = len(list_lojas_by_method(conn, methods=cfg.methods))
            if total_lojas == 0:
                return ExporterResult(
                    ok=False,
                    reason="no_producer_tier2_global",
                    notes=[
                        "nenhuma_loja_em_lojas_scraping_com_metodo_playwright_ia",
                        "scraper_codex_tier2_pausado_ou_nao_inicializado",
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
                input_scope=",".join(cfg.country_filter) if cfg.country_filter else "global_non_br",
                max_items=cfg.max_items,
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
