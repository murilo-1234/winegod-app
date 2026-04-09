import time
from flask import Blueprint, jsonify
from config import Config

health_bp = Blueprint('health', __name__)


@health_bp.route('/healthz', methods=['GET'])
def healthz():
    """GET /healthz — Liveness probe. Sem DB, sem dependencias externas."""
    return jsonify({"status": "ok"}), 200


@health_bp.route('/ready', methods=['GET'])
def ready():
    """GET /ready — Readiness probe. Verifica conexao com DB via SELECT 1."""
    try:
        from db.connection import get_connection, release_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            db_ok = True
        finally:
            release_connection(conn)
    except Exception:
        db_ok = False

    if db_ok:
        return jsonify({"status": "ready", "database": "connected"}), 200
    else:
        return jsonify({"status": "not_ready", "database": "error"}), 503


@health_bp.route('/health', methods=['GET'])
def health():
    """GET /health — Status do sistema. Compatibilidade mantida, sem COUNT(*)."""
    db_status = "disconnected"
    wines_estimate = 0

    try:
        from db.connection import get_connection, release_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # Estimativa barata via pg_class (sem seq scan)
                cur.execute(
                    "SELECT reltuples::bigint FROM pg_class WHERE relname = 'wines'"
                )
                row = cur.fetchone()
                wines_estimate = row[0] if row and row[0] > 0 else 0
            db_status = "connected"
        finally:
            release_connection(conn)
    except Exception:
        db_status = "error"

    claude_status = "configured" if Config.ANTHROPIC_API_KEY else "missing"

    return jsonify({
        "status": "ok",
        "database": db_status,
        "claude_api": claude_status,
        "wines_count_estimate": wines_estimate,
        "version": "0.2.0",
    })
