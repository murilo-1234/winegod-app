"""Exporter Tier2 BR (semanal, Playwright+IA, pais=br).

Le `vinhos_br_fontes` (ou `vinhos_{pais}` genericamente pais=br) + lojas
com `metodo_recomendado='playwright_ia'` em `lojas_scraping` filtrado
por `pais_codigo='BR'`.

`pipeline_family=tier2`. Saida em `reports/data_ops_artifacts/tier2/br/`.

Se nao houver loja Tier2 BR cadastrada, termina com `reason=no_producer_tier2_br`.
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
from ._db import connect_readonly, list_lojas_by_method


PIPELINE_FAMILY = "tier2"
SOURCE_LABEL = "tier2_br"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "data_ops_artifacts" / "tier2" / "br"
TIER2_METHODS = ["playwright_ia"]
COUNTRY = "br"


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
class Tier2BrConfig:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    max_items: int | None = None
    methods: list[str] = field(default_factory=lambda: list(TIER2_METHODS))
    batch_size: int = BATCH_SIZE
    dsn: str | None = None
    # Sharding (plano 3 fases). source_table_filter default = vinhos_br_fontes.
    source_table_filter: str | None = None
    min_fonte_id: int | None = None
    max_fonte_id: int | None = None
    shard_id: str | None = None


def _iter_rows(conn, cfg: Tier2BrConfig) -> Iterator[ExportRow]:
    host_to_loja = list_lojas_by_method(conn, methods=cfg.methods, pais_codigo=COUNTRY.upper())
    if not host_to_loja:
        return
    loja_hosts = set(host_to_loja.keys())
    source_table = f"vinhos_{COUNTRY}_fontes"
    if cfg.source_table_filter and cfg.source_table_filter != source_table:
        # Tier2 BR so opera sobre vinhos_br_fontes; shard filter diferente = zero.
        return
    base = f"vinhos_{COUNTRY}"
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
    with conn.cursor() as cur:
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


def run_export(cfg: Tier2BrConfig | None = None) -> ExporterResult:
    cfg = cfg or Tier2BrConfig()
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
        "source_table": cfg.source_table_filter or f"vinhos_{COUNTRY}_fontes",
        "min_fonte_id": cfg.min_fonte_id,
        "max_fonte_id": cfg.max_fonte_id,
    } if (cfg.shard_id or cfg.source_table_filter or cfg.min_fonte_id is not None or cfg.max_fonte_id is not None) else None
    try:
        with connect_readonly(cfg.dsn) as conn:
            host_to_loja = list_lojas_by_method(
                conn, methods=cfg.methods, pais_codigo=COUNTRY.upper()
            )
            if not host_to_loja:
                return ExporterResult(
                    ok=False,
                    reason="no_producer_tier2_br",
                    notes=[
                        "nenhuma_loja_BR_em_lojas_scraping_com_metodo_playwright_ia",
                    ],
                )

            def items_gen():
                for row in _iter_rows(conn, cfg):
                    yield build_item(row, pipeline_family=PIPELINE_FAMILY, run_id=run_id)

            result = write_artifact(
                items=items_gen(),
                output_dir=cfg.output_dir,
                source_label=SOURCE_LABEL,
                pipeline_family=PIPELINE_FAMILY,
                run_id=run_id,
                started_at=started_at,
                input_scope="br",
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
        input_scope="br",
        max_items=max_items,
    )
