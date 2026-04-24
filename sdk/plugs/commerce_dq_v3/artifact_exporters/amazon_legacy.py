"""Exporter Amazon legacy (one-time backfill).

Le `vinhos_{pais}_fontes` com `fonte IN ('amazon', 'amazon_scraper',
'amazon_scrapingdog')` - todos os historicos Amazon EXCETO o feed
`amazon_playwright` (mirror ativo; tratado em `amazon_mirror.py`).

`pipeline_family=amazon_local_legacy_backfill`, output em
`reports/data_ops_artifacts/amazon_local_legacy_backfill/`.

Deduplica por `url_original`. Respeita REGRA 5 (batch de 10.000 linhas).
NAO escreve em `winegod_db`. NAO aplica em Render.
"""

from __future__ import annotations

from dataclasses import dataclass
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
)
from ._db import FONTES_BY_FAMILY, connect_readonly, list_country_tables


PIPELINE_FAMILY = "amazon_local_legacy_backfill"
SOURCE_LABEL = "amazon_local_legacy_backfill"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "data_ops_artifacts" / "amazon_local_legacy_backfill"


@dataclass
class AmazonLegacyConfig:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    max_items: int | None = None
    country_filter: list[str] | None = None
    batch_size: int = BATCH_SIZE
    dsn: str | None = None


def _iter_rows(conn, cfg: AmazonLegacyConfig) -> Iterator[ExportRow]:
    fontes = FONTES_BY_FAMILY["amazon_legacy"]
    placeholders = ",".join(["%s"] * len(fontes))
    tables = list_country_tables(conn)
    with conn.cursor() as cur:
        for base in tables:
            cc = base.split("_", 1)[1]
            if cfg.country_filter and cc.upper() not in [c.upper() for c in cfg.country_filter]:
                continue
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
                  AND f.fonte IN ({placeholders})
                ORDER BY f.id DESC
            """
            offset = 0
            while True:
                cur.execute(sql + " LIMIT %s OFFSET %s", fontes + [cfg.batch_size, offset])
                rows = cur.fetchall()
                if not rows:
                    break
                for r in rows:
                    yield ExportRow(
                        vinho_id=r[0],
                        nome=r[1],
                        produtor=r[2],
                        safra=r[3],
                        preco=r[4],
                        moeda=r[5],
                        url_original=r[6],
                        fonte=r[7],
                        pais_codigo=r[8],
                        store_name=None,
                        store_domain=None,
                        captured_at=r[9],
                        source_table=source_table,
                        fonte_id=r[10],
                    )
                if len(rows) < cfg.batch_size:
                    break
                offset += cfg.batch_size


def run_export(cfg: AmazonLegacyConfig | None = None) -> ExporterResult:
    cfg = cfg or AmazonLegacyConfig()
    started_at = datetime.now(timezone.utc)
    run_id = f"{SOURCE_LABEL}_{started_at.strftime('%Y%m%d_%H%M%S')}"
    try:
        with connect_readonly(cfg.dsn) as conn:
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
    """Entrada alternativa para testes com fixtures (sem DB)."""

    started_at = started_at or datetime.now(timezone.utc)
    run_id = f"{SOURCE_LABEL}_{started_at.strftime('%Y%m%d_%H%M%S')}"
    items = (
        build_item(row, pipeline_family=PIPELINE_FAMILY, run_id=run_id) for row in rows
    )
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
