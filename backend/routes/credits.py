from functools import wraps
from flask import Blueprint, request, jsonify
from routes.auth import decode_jwt
from db.models_auth import (
    count_messages_today,
    count_messages_session,
    log_message,
)

credits_bp = Blueprint('credits', __name__)

GUEST_LIMIT = 5
USER_LIMIT = 15


def check_credits(req):
    """
    Verifica se o usuario/guest tem creditos disponíveis.
    Retorna (allowed, remaining, reason, user_id).
    """
    auth_header = req.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        payload = decode_jwt(auth_header[7:])
        if payload:
            user_id = payload["user_id"]
            used = count_messages_today(user_id)
            remaining = max(0, USER_LIMIT - used)
            if used >= USER_LIMIT:
                return False, 0, "daily_limit", user_id
            return True, remaining, None, user_id

    # Guest — usar session_id
    data = req.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    if not session_id:
        session_id = req.args.get("session_id", "")

    used = count_messages_session(session_id) if session_id else 0
    remaining = max(0, GUEST_LIMIT - used)
    if session_id and used >= GUEST_LIMIT:
        return False, 0, "guest_limit", None

    return True, remaining, None, None


def require_credits(f):
    """
    Decorator para endpoints de chat.
    Checa creditos antes de processar e registra uso apos.

    Uso em chat.py:
        from routes.credits import require_credits

        @chat_bp.route('/chat', methods=['POST'])
        @require_credits
        def chat():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        allowed, remaining, reason, user_id = check_credits(request)

        if not allowed:
            status = "guest_limit" if reason == "guest_limit" else "daily_limit"
            return jsonify({
                "error": "credits_exhausted",
                "reason": status,
                "remaining": 0,
                "message": "Creditos esgotados" if status == "daily_limit"
                    else "Mensagens gratuitas esgotadas. Entre com Google para mais 15 mensagens.",
            }), 429

        # Executar endpoint
        response = f(*args, **kwargs)

        # Registrar uso apos sucesso (status < 400)
        if hasattr(response, 'status_code'):
            status_code = response.status_code
        elif isinstance(response, tuple):
            status_code = response[1] if len(response) > 1 else 200
        else:
            status_code = 200

        if status_code < 400:
            data = request.get_json(silent=True) or {}
            session_id = data.get("session_id", "")
            ip = request.remote_addr or ""
            log_message(user_id, session_id, ip)

        return response

    return decorated


@credits_bp.route('/credits', methods=['GET'])
def get_credits():
    """GET /api/credits — Retorna creditos restantes."""
    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        payload = decode_jwt(auth_header[7:])
        if payload:
            used = count_messages_today(payload["user_id"])
            remaining = max(0, USER_LIMIT - used)
            return jsonify({
                "used": used,
                "remaining": remaining,
                "limit": USER_LIMIT,
                "type": "user",
            })

    session_id = request.args.get("session_id", "")
    used = count_messages_session(session_id) if session_id else 0
    remaining = max(0, GUEST_LIMIT - used)

    return jsonify({
        "used": used,
        "remaining": remaining,
        "limit": GUEST_LIMIT,
        "type": "guest",
    })
