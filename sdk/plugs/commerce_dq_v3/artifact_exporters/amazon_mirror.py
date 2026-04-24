"""Exporter Amazon mirror primary (recorrente).

Le `vinhos_{pais}_fontes` com `fonte='amazon_playwright'` (feed ativo do
PC espelho). `pipeline_family=amazon_mirror_primary`. Saida em
`reports/data_ops_artifacts/amazon_mirror/`.

Modos:
- `full`: le tudo (primeiro run).
- `incremental`: le so com `captured_at > state.last_captured_at`
  (estado em `reports/data_ops_export_state/amazon_mirror.json`).

Respeita REGRA 5 (batches 10k). Read-only no `winegod_db`. Nao aplica.
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
    load_state,
    save_state,
    write_artifact,
)
from ._db import FONTES_BY_FAMILY, connect_readonly, list_country_tables


PIPELINE_FAMILY = "amazon_mirror_primary"
SOURCE_LABEL = "amazon_mirror_primary"
STATE_KEY = "amazon_mirror"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "data_ops_artifacts" / "amazon_mirror"


@dataclass
class AmazonMirrorConfig:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    max_items: int | None = None
    mode: str = "incremental"  # "incremental" | "full"
    since: datetime | None = None  # override explicito
    country_filter: list[str] | None = None
    batch_size: int = BATCH_SIZE
    dsn: str | None = None
    state_source_key: str = STATE_KEY  # customizavel para testes


def _iter_rows(conn, cfg: AmazonMirrorConfig, since: datetime | None) -> Iterator[ExportRow]:
    fontes = FONTES_BY_FAMILY["amazon_mirror"]
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
            """
            params: list = list(fontes)
            if since is not None:
                sql += " AND COALESCE(f.atualizado_em, f.descoberto_em) > %s"
                params.append(since)
            sql += " ORDER BY f.id DESC"
            offset = 0
            while True:
                cur.execute(sql + " LIMIT %s OFFSET %s", params + [cfg.batch_size, offset])
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


def _resolve_since(cfg: AmazonMirrorConfig) -> datetime | None:
    if cfg.mode == "full":
        return None
    if cfg.since is not None:
        return cfg.since
    state = load_state(cfg.state_source_key)
    raw = state.get("last_captured_at") if state else None
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def run_export(cfg: AmazonMirrorConfig | None = None) -> ExporterResult:
    cfg = cfg or AmazonMirrorConfig()
    since = _resolve_since(cfg)
    started_at = datetime.now(timezone.utc)
    run_id = f"{SOURCE_LABEL}_{started_at.strftime('%Y%m%d_%H%M%S')}"
    try:
        with connect_readonly(cfg.dsn) as conn:
            captured_seen: list[datetime] = []

            def items_gen():
                for row in _iter_rows(conn, cfg, since):
                    if isinstance(row.captured_at, datetime):
                        captured_seen.append(row.captured_at)
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
            if result.ok and captured_seen:
                latest = max(captured_seen)
                save_state(
                    cfg.state_source_key,
                    {
                        "last_captured_at": latest.astimezone(timezone.utc).isoformat(),
                        "last_run_id": run_id,
                        "last_items_emitted": result.items_emitted,
                        "last_artifact_sha256": result.artifact_sha256,
                        "mode": cfg.mode,
                    },
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
    state_source_key: str = STATE_KEY,
    update_state: bool = True,
) -> ExporterResult:
    """Entrada alternativa para testes com fixtures (sem DB)."""

    started_at = started_at or datetime.now(timezone.utc)
    run_id = f"{SOURCE_LABEL}_{started_at.strftime('%Y%m%d_%H%M%S')}"
    captured_seen: list[datetime] = []
    items_built = []
    for row in rows:
        if isinstance(row.captured_at, datetime):
            captured_seen.append(row.captured_at)
        items_built.append(build_item(row, pipeline_family=PIPELINE_FAMILY, run_id=run_id))
    result = write_artifact(
        items=iter(items_built),
        output_dir=output_dir,
        source_label=SOURCE_LABEL,
        pipeline_family=PIPELINE_FAMILY,
        run_id=run_id,
        started_at=started_at,
        input_scope="fixture",
        max_items=max_items,
    )
    if result.ok and update_state and captured_seen:
        latest = max(captured_seen)
        save_state(
            state_source_key,
            {
                "last_captured_at": latest.astimezone(timezone.utc).isoformat(),
                "last_run_id": run_id,
                "last_items_emitted": result.items_emitted,
                "last_artifact_sha256": result.artifact_sha256,
                "mode": "fixture",
            },
        )
    return result
