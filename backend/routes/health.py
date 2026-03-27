from flask import Blueprint, jsonify
from config import Config

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health():
    """GET /health — Status do sistema."""
    db_status = "disconnected"
    wines_count = 0

    try:
        from db.queries import get_wines_count
        wines_count = get_wines_count()
        db_status = "connected"
    except Exception:
        db_status = "error"

    claude_status = "configured" if Config.ANTHROPIC_API_KEY else "missing"

    return jsonify({
        "status": "ok",
        "database": db_status,
        "claude_api": claude_status,
        "wines_count": wines_count,
        "version": "0.1.0",
    })
