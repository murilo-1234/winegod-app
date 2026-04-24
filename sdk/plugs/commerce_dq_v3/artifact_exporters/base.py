"""Utilitarios compartilhados pelos exporters commerce.

- `ExportRow` / `ExporterResult`: tipos pequenos.
- `build_item`: normaliza row-do-join para o contrato
  `docs/TIER_COMMERCE_CONTRACT.md` (13 campos obrigatorios + opcionais).
- `write_artifact`: grava `<prefix>.jsonl` + `<prefix>_summary.json`,
  deduplica por `url_original`, respeita batch de 10k linhas.
- `load_state` / `save_state`: checkpoint por exporter em
  `reports/data_ops_export_state/<source>.json`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[4]
STATE_DIR = REPO_ROOT / "reports" / "data_ops_export_state"
BATCH_SIZE = 10_000
# Plano 3 fases (Codex, 2026-04-24): apply por shard capped em 50k itens
# (REGRA 5 + BULK_INGEST_MAX_ITEMS=50000 em backend/config.py:56).
MAX_SHARD_ITEMS = 50_000


@dataclass
class ExportRow:
    """Row generica lida do winegod_db (pos-join com lojas_scraping)."""

    vinho_id: int
    nome: str | None
    produtor: str | None
    safra: Any | None
    preco: Any | None
    moeda: str | None
    url_original: str | None
    fonte: str | None
    pais_codigo: str | None
    store_name: str | None
    store_domain: str | None
    captured_at: Any | None
    source_table: str
    fonte_id: int | None = None


@dataclass
class ExporterResult:
    ok: bool
    reason: str | None = None
    jsonl_path: Path | None = None
    summary_path: Path | None = None
    items_emitted: int = 0
    artifact_sha256: str | None = None
    duplicates_skipped: int = 0
    rows_read: int = 0
    notes: list[str] = field(default_factory=list)


def _normalize_host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
    except Exception:
        return None
    host = (parsed.hostname or "").lower().strip()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host


def _to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    return str(value)


def build_item(
    row: ExportRow,
    *,
    pipeline_family: str,
    run_id: str,
) -> dict:
    """Converte `ExportRow` para o contrato TIER_COMMERCE_CONTRACT."""

    store_domain = row.store_domain or _normalize_host(row.url_original) or "unknown.domain"
    country = (row.pais_codigo or "").lower() or "xx"
    preco_val: float | None
    try:
        preco_val = float(row.preco) if row.preco is not None else None
    except (TypeError, ValueError):
        preco_val = None
    safra_val: int | str | None
    if row.safra is None or row.safra == "":
        safra_val = None
    else:
        try:
            safra_val = int(row.safra)
        except (TypeError, ValueError):
            safra_val = str(row.safra)
    item = {
        "pipeline_family": pipeline_family,
        "run_id": run_id,
        "country": country,
        "store_name": row.store_name or "unknown_store",
        "store_domain": store_domain,
        "url_original": row.url_original or "",
        "nome": row.nome or "",
        "produtor": row.produtor or "",
        "safra": safra_val,
        "preco": preco_val,
        "moeda": row.moeda or "XXX",
        "captured_at": _to_iso(row.captured_at),
        "source_pointer": f"{row.source_table}#{row.fonte_id or row.vinho_id}",
    }
    if row.fonte:
        item["_source_fonte"] = row.fonte
    return item


def _is_item_complete(item: dict) -> bool:
    """Respeita o contrato: nome, produtor, url_original, store_domain nao-vazios."""

    return bool(
        item.get("nome")
        and item.get("produtor")
        and item.get("url_original")
        and item.get("store_domain")
        and item.get("store_domain") != "unknown.domain"
    )


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def write_artifact(
    *,
    items: Iterable[dict],
    output_dir: Path,
    source_label: str,
    pipeline_family: str,
    run_id: str,
    started_at: datetime,
    input_scope: str = "global",
    max_items: int | None = None,
    shard_spec: dict | None = None,
) -> ExporterResult:
    """Grava JSONL + summary. Dedup por `url_original`. Respeita contrato.

    `max_items` limita o numero total de items escritos (piloto / smoke).
    `shard_spec` e um dict opcional com `shard_id`, `source_table`,
    `min_fonte_id`, `max_fonte_id` para rastreio anti-reprocessamento.

    Raise ValueError se `max_items > MAX_SHARD_ITEMS` (hard cap do plano
    3 fases: apply por shard capped em 50000 itens).
    """

    if max_items is not None and max_items > MAX_SHARD_ITEMS:
        raise ValueError(
            f"max_items={max_items} excede MAX_SHARD_ITEMS={MAX_SHARD_ITEMS} "
            "(apply commerce capped em 50k itens por shard; REGRA 5 + "
            "BULK_INGEST_MAX_ITEMS=50000 em backend/config.py)."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    seen_urls: set[str] = set()
    duplicates = 0
    rows_read = 0
    emitted = 0
    prefix = started_at.strftime("%Y%m%d_%H%M%S") + "_" + source_label
    jsonl_path = output_dir / f"{prefix}.jsonl"
    summary_path = output_dir / f"{prefix}_summary.json"

    with jsonl_path.open("w", encoding="utf-8") as fh:
        for item in items:
            rows_read += 1
            if not _is_item_complete(item):
                continue
            url = item.get("url_original")
            if url in seen_urls:
                duplicates += 1
                continue
            seen_urls.add(url)
            fh.write(json.dumps(item, default=str, ensure_ascii=False) + "\n")
            emitted += 1
            if max_items is not None and emitted >= max_items:
                break

    if emitted == 0:
        # Apaga arquivos vazios para manter diretorio limpo.
        try:
            jsonl_path.unlink()
        except FileNotFoundError:
            pass
        return ExporterResult(
            ok=False,
            reason="zero_items_elegiveis",
            rows_read=rows_read,
            duplicates_skipped=duplicates,
            notes=[f"rows_read={rows_read}", f"duplicates_skipped={duplicates}"],
        )

    real_sha = _hash_file(jsonl_path)
    finished_at = datetime.now(timezone.utc)
    summary = {
        "run_id": run_id,
        "pipeline_family": pipeline_family,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "host": socket.gethostname() or "este_pc",
        "input_scope": input_scope,
        "items_emitted": emitted,
        "artifact_sha256": real_sha,
    }
    if shard_spec:
        summary["shard_spec"] = {
            "shard_id": shard_spec.get("shard_id"),
            "source_table": shard_spec.get("source_table"),
            "min_fonte_id": shard_spec.get("min_fonte_id"),
            "max_fonte_id": shard_spec.get("max_fonte_id"),
        }
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return ExporterResult(
        ok=True,
        jsonl_path=jsonl_path,
        summary_path=summary_path,
        items_emitted=emitted,
        artifact_sha256=real_sha,
        duplicates_skipped=duplicates,
        rows_read=rows_read,
        notes=[
            f"rows_read={rows_read}",
            f"duplicates_skipped={duplicates}",
            f"items_emitted={emitted}",
            f"artifact_sha256_prefix={real_sha[:12]}",
        ],
    )


def load_state(source: str) -> dict:
    path = STATE_DIR / f"{source}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(source: str, data: dict) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{source}.json"
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path
