"""Endpoint unico de ingestao em bulk.

POST /api/ingest/bulk

Headers:
    X-Ingest-Token: <Config.BULK_INGEST_TOKEN>

Body JSON:
    {
        "items": [{"nome": "...", "produtor": "...",
                   "sources": [{"store_id": 1, "url": "...", ...}], ...}, ...],
        "dry_run": true|false,
        "source": "wcf" | "scraping_x" | "chat_auto" | "amazon_br" | "...",
        "run_id": "amazon_20260421_01",
        "create_sources": true
    }

Resposta inclui contadores de wines e (DQ V3 Escopo 1+2) de wine_sources:
    {
        "dry_run": bool,
        "source": str,
        "run_id": str|null,
        "received": int,
        "valid": int,
        "duplicates_in_input": int,
        "would_insert": int, "would_update": int,
        "inserted": int, "updated": int,
        "sources_in_input": int,
        "sources_duplicates_in_input": int,
        "sources_rejected": [{item_index, source_index, reason}, ...],
        "would_insert_sources": int, "would_update_sources": int,
        "sources_inserted": int, "sources_updated": int,
        "create_sources": bool,
        "filtered_notwine": [...],
        "rejected": [...],
        "errors": [...],
        "batches": int
    }
"""

from flask import Blueprint, jsonify, request

try:
    from config import Config
except ImportError:  # pragma: no cover
    from backend.config import Config  # type: ignore

from services.bulk_ingest import process_bulk, _to_bool


ingest_bp = Blueprint("ingest", __name__)


def _check_token() -> bool:
    expected = (Config.BULK_INGEST_TOKEN or "").strip()
    if not expected:
        return False
    received = (request.headers.get("X-Ingest-Token") or "").strip()
    return received == expected


@ingest_bp.route("/ingest/bulk", methods=["POST"])
def bulk_ingest():
    if not _check_token():
        return jsonify({"error": "unauthorized"}), 401

    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    items = body.get("items")
    if not isinstance(items, list):
        return jsonify({"error": "items_must_be_list"}), 400

    # Bool parsing explicito (bug hardening): `bool("false") == True` em Python.
    # Usa _to_bool do service, que aceita "false"/"0"/"no"/"nao"/"não" como False.
    dry_run = _to_bool(body.get("dry_run"), default=True)
    source = str(body.get("source") or "unknown")[:64]
    run_id_raw = body.get("run_id")
    run_id = str(run_id_raw).strip()[:128] if run_id_raw is not None else None
    create_sources = _to_bool(body.get("create_sources"), default=True)

    result = process_bulk(
        items,
        dry_run=dry_run,
        source=source,
        run_id=run_id,
        create_sources=create_sources,
    )
    return jsonify(result), 200
