"""Endpoint unico de ingestao em bulk.

POST /api/ingest/bulk

Headers:
    X-Ingest-Token: <Config.BULK_INGEST_TOKEN>

Body JSON:
    {
        "items": [{"nome": "...", "produtor": "...", ...}, ...],
        "dry_run": true|false,
        "source": "wcf" | "scraping_x" | "chat_auto" | "..."
    }

Resposta:
    {
        "dry_run": bool,
        "source": str,
        "received": int,
        "valid": int,
        "duplicates_in_input": int,
        "would_insert": int,
        "would_update": int,
        "inserted": int,
        "updated": int,
        "filtered_notwine": [{index, reason}, ...],
        "rejected": [{index, reason}, ...],
        "errors": [str, ...],
        "batches": int
    }
"""

from flask import Blueprint, jsonify, request

try:
    from config import Config
except ImportError:  # pragma: no cover
    from backend.config import Config  # type: ignore

from services.bulk_ingest import process_bulk


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

    dry_run = bool(body.get("dry_run", True))
    source = str(body.get("source") or "unknown")[:64]

    result = process_bulk(items, dry_run=dry_run, source=source)
    return jsonify(result), 200
