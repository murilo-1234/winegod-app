from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable

import psycopg2

from sdk.plugs.common import load_repo_envs, sha256_text
from .schemas import ExportBundle


REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_ROOT = REPO_ROOT / "reports"
ENRICHED_ROOT = REPORTS_ROOT / "ingest_pipeline_enriched"
STATE_PATH = REPORTS_ROOT / "gemini_batch_state.json"
INPUT_PATH = REPORTS_ROOT / "gemini_batch_input.jsonl"
OUTPUT_PATH = REPORTS_ROOT / "gemini_batch_output.jsonl"


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def _latest_files(pattern: str) -> list[Path]:
    return sorted(ENRICHED_ROOT.rglob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _iter_csv(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield row


def _ready_record(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "gemini_batch_reports",
        "route": row.get("_post_enrich_status") or "ready",
        "wine_identity": {
            "nome": row.get("nome"),
            "produtor": row.get("produtor"),
            "safra": row.get("safra"),
            "pais": row.get("pais"),
            "regiao": row.get("regiao"),
            "tipo": row.get("tipo"),
        },
        "enrichment": {
            "status": row.get("_post_enrich_status") or "ready",
            "confidence": row.get("_enriched_confidence"),
            "model": row.get("_enriched_source_model"),
            "escalated": row.get("_enriched_escalated"),
            "reasons": row.get("_enriched_reasons") or row.get("_post_enrich_reasons") or [],
            "router_status": row.get("_router_status"),
        },
        "source_lineage": {
            "source_system": "gemini_batch_reports",
            "source_kind": "file",
            "source_pointer": str(path),
            "source_record_count": 1,
            "notes": f"route={row.get('_post_enrich_status') or 'ready'}"[:256],
        },
    }


def _uncertain_record(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    raw_json = row.get("raw_json") or ""
    parsed = {}
    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except Exception:
            parsed = {}
    confidence_raw = row.get("confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw not in (None, "") else None
    except ValueError:
        confidence = None

    return {
        "source": "gemini_batch_reports",
        "route": "uncertain",
        "wine_identity": {
            "nome": row.get("nome_enriquecido") or row.get("nome_original") or parsed.get("nome"),
            "produtor": row.get("produtor_enriquecido") or row.get("produtor_original") or parsed.get("produtor"),
            "pais": row.get("pais_enriquecido") or parsed.get("pais"),
            "regiao": parsed.get("regiao"),
            "safra": parsed.get("safra"),
        },
        "enrichment": {
            "status": "uncertain",
            "confidence": confidence,
            "kind": row.get("kind"),
            "reasons": row.get("reasons"),
            "raw_json_hash": sha256_text(raw_json) if raw_json else None,
        },
        "source_lineage": {
            "source_system": "gemini_batch_reports",
            "source_kind": "file",
            "source_pointer": str(path),
            "source_record_count": 1,
            "notes": f"router_index={row.get('router_index')}; source={row.get('source')}"[:256],
        },
    }


def _not_wine_record(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "gemini_batch_reports",
        "route": "not_wine",
        "wine_identity": {
            "nome": row.get("nome"),
            "produtor": row.get("produtor"),
            "pais": row.get("pais"),
        },
        "enrichment": {
            "status": "not_wine",
            "confidence": row.get("_enriched_confidence"),
            "model": row.get("_enriched_source_model"),
            "reasons": row.get("_enriched_reasons") or row.get("_post_enrich_reasons") or [],
        },
        "source_lineage": {
            "source_system": "gemini_batch_reports",
            "source_kind": "file",
            "source_pointer": str(path),
            "source_record_count": 1,
            "notes": "route=not_wine",
        },
    }


def _flash_notes() -> list[str]:
    dsn = os.environ.get("WINEGOD_DATABASE_URL")
    if not dsn:
        return []

    conn = psycopg2.connect(dsn, connect_timeout=10)
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout TO 15000")
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('flash_vinhos', 'flash_queries')
                ORDER BY table_name
                """
            )
            tables = {row[0] for row in cur.fetchall()}
            notes: list[str] = []
            if "flash_vinhos" in tables:
                cur.execute("SELECT count(*) FROM public.flash_vinhos")
                notes.append(f"flash_vinhos_count={int(cur.fetchone()[0] or 0)}")
            if "flash_queries" in tables:
                cur.execute("SELECT count(*) FROM public.flash_queries")
                notes.append(f"flash_queries_count={int(cur.fetchone()[0] or 0)}")
            return notes
    finally:
        conn.close()


def export_gemini_batch_reports(limit: int) -> ExportBundle:
    ready_files = _latest_files("enriched_ready.jsonl")
    uncertain_files = _latest_files("enriched_uncertain_review.csv")
    not_wine_files = _latest_files("enriched_not_wine.jsonl")

    if not any([STATE_PATH.exists(), INPUT_PATH.exists(), OUTPUT_PATH.exists(), ready_files, uncertain_files, not_wine_files]):
        return ExportBundle(
            source="gemini_batch_reports",
            state="blocked_missing_source",
            notes=["nenhum artifact local de gemini/enrichment encontrado"],
        )

    state = _load_json(STATE_PATH) if STATE_PATH.exists() else {}
    items: list[dict[str, Any]] = []

    for path in ready_files:
        for row in _iter_jsonl(path):
            items.append(_ready_record(path, row))
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break

    if len(items) < limit:
        for path in uncertain_files:
            for row in _iter_csv(path):
                items.append(_uncertain_record(path, row))
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break

    if len(items) < limit:
        for path in not_wine_files:
            for row in _iter_jsonl(path):
                items.append(_not_wine_record(path, row))
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break

    notes = [
        f"items_exported={len(items)}",
        f"gemini_total_requests={int(state.get('total_requests') or 0)}",
        f"gemini_total_wines={int(state.get('total_wines') or 0)}",
        f"gemini_output_lines={_line_count(OUTPUT_PATH)}",
        f"ready_files={len(ready_files)}",
        f"uncertain_files={len(uncertain_files)}",
        f"not_wine_files={len(not_wine_files)}",
    ]
    notes.extend(_flash_notes())

    return ExportBundle(
        source="gemini_batch_reports",
        state="observed" if items else "blocked_missing_source",
        items=items,
        notes=notes,
    )


EXPORTERS = {
    "gemini_batch_reports": export_gemini_batch_reports,
}


load_repo_envs()
