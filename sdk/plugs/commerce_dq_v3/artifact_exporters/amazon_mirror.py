"""Exporter Amazon mirror primary (recorrente).

Le `vinhos_{pais}_fontes` com `fonte='amazon_playwright'` (feed ativo do
PC espelho). `pipeline_family=amazon_mirror_primary`. Saida em
`reports/data_ops_artifacts/amazon_mirror/`.

Modos:
- `full`: le tudo (primeiro run).
- `incremental`: le so com `captured_at > state.last_captured_at`
  (estado em `reports/data_ops_export_state/amazon_mirror.json`).

State journal (Fase 1, plano subida-3fases-20260424):
- `run_export` NAO escreve direto em `amazon_mirror.json`;
- escreve em `amazon_mirror.pending.json`;
- `commit_pending_state()` promove pending -> oficial apos apply PASS;
- `abort_pending_state()` move pending -> aborted/<ts>.json em falha;
- se ja existir pending orfao no inicio de um run novo, aborta com
  `blocked_state_pending_orfao`.

Respeita REGRA 5 (batches 10k). Read-only no `winegod_db`. Nao aplica.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .base import (
    REPO_ROOT,
    STATE_DIR,
    BATCH_SIZE,
    ExportRow,
    ExporterResult,
    build_item,
    load_state,
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
    # Sharding (plano 3 fases).
    source_table_filter: str | None = None
    min_fonte_id: int | None = None
    max_fonte_id: int | None = None
    shard_id: str | None = None


def _pending_path(state_source_key: str) -> Path:
    return STATE_DIR / f"{state_source_key}.pending.json"


def _official_path(state_source_key: str) -> Path:
    return STATE_DIR / f"{state_source_key}.json"


def _write_pending_state(state_source_key: str, data: dict) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _pending_path(state_source_key)
    payload = dict(data)
    payload.setdefault("pending_since", datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def has_pending_state(state_source_key: str = STATE_KEY) -> bool:
    """Retorna True se existe pending state (journal nao-commitado/nao-abortado)."""

    return _pending_path(state_source_key).exists()


def commit_pending_state(state_source_key: str = STATE_KEY) -> dict:
    """Promove pending -> state oficial apos apply PASS."""

    pending_path = _pending_path(state_source_key)
    official_path = _official_path(state_source_key)
    if not pending_path.exists():
        raise FileNotFoundError(f"pending nao existe: {pending_path}")
    data = json.loads(pending_path.read_text(encoding="utf-8"))
    data["committed_at"] = datetime.now(timezone.utc).isoformat()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    official_path.write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8"
    )
    pending_path.unlink()
    return data


def abort_pending_state(
    state_source_key: str = STATE_KEY, reason: str = "unknown"
) -> Path:
    """Move pending -> aborted/<state_source_key>.aborted_<ts>.json apos apply FAIL."""

    pending_path = _pending_path(state_source_key)
    if not pending_path.exists():
        raise FileNotFoundError(f"pending nao existe: {pending_path}")
    aborted_dir = STATE_DIR / "aborted"
    aborted_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    aborted_path = aborted_dir / f"{state_source_key}.aborted_{ts}.json"
    data = json.loads(pending_path.read_text(encoding="utf-8"))
    data["aborted_at"] = datetime.now(timezone.utc).isoformat()
    data["abort_reason"] = reason
    aborted_path.write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8"
    )
    pending_path.unlink()
    return aborted_path


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
            if cfg.source_table_filter and source_table != cfg.source_table_filter:
                continue
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
            if cfg.min_fonte_id is not None:
                sql += " AND f.id >= %s"
                params.append(cfg.min_fonte_id)
            if cfg.max_fonte_id is not None:
                sql += " AND f.id <= %s"
                params.append(cfg.max_fonte_id)
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
    if cfg.min_fonte_id is not None and cfg.max_fonte_id is not None:
        if cfg.min_fonte_id > cfg.max_fonte_id:
            return ExporterResult(
                ok=False,
                reason="shard_range_invalid",
                notes=[f"min_fonte_id={cfg.min_fonte_id} > max_fonte_id={cfg.max_fonte_id}"],
            )
    # Guard: pending orfao bloqueia um novo run para nao perder historia.
    if has_pending_state(cfg.state_source_key):
        pending = _pending_path(cfg.state_source_key)
        return ExporterResult(
            ok=False,
            reason="blocked_state_pending_orfao",
            notes=[
                f"pending_path={pending}",
                "resolver via scripts/data_ops_producers/amazon_mirror_state.py "
                "{commit|abort --reason TEXT} antes de rodar novo export",
            ],
        )
    since = _resolve_since(cfg)
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
                shard_spec=shard_spec,
            )
            if result.ok and captured_seen:
                latest = max(captured_seen)
                _write_pending_state(
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
    """Entrada alternativa para testes com fixtures (sem DB).

    Quando `update_state=True`, grava em `<state_source_key>.pending.json`
    (mesmo padrao de `run_export`). O chamador e responsavel por commitar
    ou abortar via `commit_pending_state` / `abort_pending_state`.
    """

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
        _write_pending_state(
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
