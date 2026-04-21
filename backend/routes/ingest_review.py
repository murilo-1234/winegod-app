"""Endpoint de aprovacao manual da review queue (DQ V3 Escopo 4).

POST /api/ingest/review/<queue_id>

Headers:
    X-Ingest-Token: <Config.BULK_INGEST_TOKEN>   (mesmo token do /ingest/bulk)

Body JSON:
    {
        "action": "approve_merge" | "approve_new" | "reject",
        "canonical_wine_id": 12345,   # obrigatorio em approve_merge;
                                       # deve estar em candidate_wine_ids da queue
        "reviewed_by": "murilo",       # opcional, <= 128 chars
        "dry_run": true | false        # default false
    }

Comportamento:
    approve_merge: UPDATE em `wines.id = canonical_wine_id` com COALESCE
        conservador + UPSERT em `wine_sources`. Queue status -> "merged".
    approve_new:   INSERT novo wine + UPSERT sources. Queue status -> "created_new".
    reject:        Queue status -> "rejected". Nenhuma mutacao em wines/wine_sources.

Rastreabilidade: `ingestion_run_id` gravado em `wines`/`wine_sources` usa o
`run_id` ORIGINAL da queue row (upload original), NAO um novo run da aprovacao.
Isso mantem rollback granular por run coerente com o Escopo 1+2.

Dry-run: simula a decisao e retorna `would_*`. Zero writes em wines,
wine_sources ou ingestion_review_queue.
"""

from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, jsonify, request

try:
    from config import Config
except ImportError:  # pragma: no cover
    from backend.config import Config  # type: ignore

from db.connection import get_connection, release_connection
from services.bulk_ingest import (
    _to_bool,
    _validate,
    _apply_batch,
    _apply_sources_batch,
    _prevalidate_store_ids,
    _has_run_log_v3_columns,
)


ingest_review_bp = Blueprint("ingest_review", __name__)


_VALID_ACTIONS = {"approve_merge", "approve_new", "reject"}
_V3_COUNTER_COLS = {
    "approve_merge": "approved_merge",
    "approve_new": "approved_new",
    "reject": "rejected_review",
}


def _check_token() -> bool:
    expected = (Config.BULK_INGEST_TOKEN or "").strip()
    if not expected:
        return False
    received = (request.headers.get("X-Ingest-Token") or "").strip()
    return received == expected


def _increment_run_log(conn, run_id: str | None, action: str) -> None:
    """Incrementa o contador correspondente em ingestion_run_log.

    No-op se migration 019 nao aplicada, se run_id ausente, ou se a linha do
    run nao existir no log. Nunca quebra o fluxo principal.
    """
    if not run_id:
        return
    col = _V3_COUNTER_COLS.get(action)
    if not col:
        return
    try:
        if not _has_run_log_v3_columns(conn):
            return
        with conn.cursor() as cur:
            # `col` eh whitelisted acima. Seguranca OK.
            cur.execute(
                f"UPDATE ingestion_run_log SET {col} = COALESCE({col}, 0) + 1 "
                f"WHERE run_id = %s",
                (run_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()


def _load_queue_row(conn, queue_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, run_id, source, source_payload, match_tier,
                   candidate_wine_ids, status
            FROM ingestion_review_queue
            WHERE id = %s
            """,
            (queue_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    (qid, run_id, source, source_payload, match_tier, candidate_wine_ids,
     status) = row
    return {
        "id": qid,
        "run_id": run_id,
        "source": source,
        "source_payload": source_payload,
        "match_tier": match_tier,
        "candidate_wine_ids": list(candidate_wine_ids or []),
        "status": status,
    }


def _set_queue_status(conn, queue_id: int, status: str, reviewed_by: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ingestion_review_queue
            SET status = %s,
                reviewed_by = %s,
                reviewed_at = NOW()
            WHERE id = %s
            """,
            (status, reviewed_by, queue_id),
        )
    conn.commit()


def _apply_review_decision(queue_id: int, action: str,
                           canonical_wine_id: int | None,
                           reviewed_by: str | None,
                           dry_run: bool) -> tuple[dict, int]:
    """Aplica a decisao de review. Retorna (response_dict, http_status)."""
    conn = get_connection()
    try:
        row = _load_queue_row(conn, queue_id)
        if row is None:
            return {"error": "queue_id_not_found"}, 404
        if row["status"] != "pending":
            return {
                "error": "already_reviewed",
                "status": row["status"],
            }, 409

        if action == "approve_merge":
            if canonical_wine_id is None:
                return {"error": "canonical_wine_id_required"}, 400
            if canonical_wine_id not in row["candidate_wine_ids"]:
                return {
                    "error": "canonical_wine_id_not_in_candidates",
                    "candidates": row["candidate_wine_ids"],
                }, 400

        payload = dict(row["source_payload"] or {})

        # Dry-run: simula sem escrever NADA.
        if dry_run:
            sim: dict[str, Any] = {
                "queue_id": queue_id,
                "action": action,
                "dry_run": True,
                "status": row["status"],  # permanece pending
                "run_id": row["run_id"],
            }
            if action == "reject":
                sim["would_update_status"] = "rejected"
                return sim, 200
            sources = payload.get("sources") or []
            if action == "approve_merge":
                sim["would_update_wine_id"] = canonical_wine_id
                sim["would_upsert_sources"] = len(sources) if isinstance(sources, list) else 0
                sim["would_next_status"] = "merged"
            else:  # approve_new
                sim["would_insert_wine"] = True
                sim["would_upsert_sources"] = len(sources) if isinstance(sources, list) else 0
                sim["would_next_status"] = "created_new"
            return sim, 200

        # Apply real -----------------------------------------------------
        if action == "reject":
            _set_queue_status(conn, queue_id, "rejected", reviewed_by)
            _increment_run_log(conn, row["run_id"], action)
            return {
                "queue_id": queue_id,
                "action": action,
                "dry_run": False,
                "status": "rejected",
                "run_id": row["run_id"],
            }, 200

        # approve_merge / approve_new: re-valida o payload e aplica.
        validated, reason = _validate(payload)
        if validated is None:
            return {
                "error": "payload_revalidation_failed",
                "reason": reason,
            }, 500

        validated["_payload_index"] = 0
        schema_cache: dict[str, bool] = {}
        source = row["source"] or (
            "review_merge" if action == "approve_merge" else "review_new"
        )

        if action == "approve_merge":
            hash_to_id = {validated["hash_dedup"]: canonical_wine_id}
            inserted, updated, _id_cache = _apply_batch(
                conn, [validated], source, hash_to_id, row["run_id"], schema_cache
            )
            wine_id = canonical_wine_id
            next_status = "merged"
            wine_inserted = False
            wine_updated = updated > 0
        else:  # approve_new
            hash_to_id = {}
            inserted, updated, id_cache = _apply_batch(
                conn, [validated], source, hash_to_id, row["run_id"], schema_cache
            )
            wine_id = id_cache.get(validated["hash_dedup"])
            next_status = "created_new"
            wine_inserted = inserted > 0
            wine_updated = updated > 0

        # Sources (se houver)
        sources_inserted = 0
        sources_updated = 0
        if validated.get("_sources") and wine_id is not None:
            store_ids = {s["store_id"] for s in validated["_sources"]}
            valid_store_ids = _prevalidate_store_ids(conn, store_ids)
            validated["_sources"] = [
                s for s in validated["_sources"] if s["store_id"] in valid_store_ids
            ]
            validated["_wine_id"] = wine_id
            if validated["_sources"]:
                try:
                    sources_inserted, sources_updated = _apply_sources_batch(
                        conn, [validated], row["run_id"], schema_cache
                    )
                except Exception as e:
                    conn.rollback()
                    return {
                        "error": f"sources_apply_failed: {type(e).__name__}: {e}",
                    }, 500

        # Queue status + contador
        _set_queue_status(conn, queue_id, next_status, reviewed_by)
        _increment_run_log(conn, row["run_id"], action)

        return {
            "queue_id": queue_id,
            "action": action,
            "dry_run": False,
            "status": next_status,
            "run_id": row["run_id"],
            "wine_id": wine_id,
            "wine_inserted": wine_inserted,
            "wine_updated": wine_updated,
            "sources_inserted": sources_inserted,
            "sources_updated": sources_updated,
        }, 200
    finally:
        release_connection(conn)


@ingest_review_bp.route("/ingest/review/<int:queue_id>", methods=["POST"])
def review_queue_item(queue_id: int):
    if not _check_token():
        return jsonify({"error": "unauthorized"}), 401

    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    action_raw = body.get("action")
    action = str(action_raw or "").strip().lower()
    if action not in _VALID_ACTIONS:
        return jsonify({"error": "invalid_action", "valid": sorted(_VALID_ACTIONS)}), 400

    canonical_raw = body.get("canonical_wine_id")
    canonical_wine_id: int | None = None
    if canonical_raw is not None and canonical_raw != "":
        try:
            canonical_wine_id = int(canonical_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "canonical_wine_id_not_int"}), 400

    reviewed_by_raw = body.get("reviewed_by")
    reviewed_by = str(reviewed_by_raw).strip()[:128] if reviewed_by_raw else None
    if reviewed_by == "":
        reviewed_by = None

    dry_run = _to_bool(body.get("dry_run"), default=False)

    response, status_code = _apply_review_decision(
        queue_id=queue_id,
        action=action,
        canonical_wine_id=canonical_wine_id,
        reviewed_by=reviewed_by,
        dry_run=bool(dry_run),
    )
    return jsonify(response), status_code
