import os
import re
import jwt
import requests
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, redirect
from db.models_auth import (
    upsert_user,
    get_user_by_id,
    delete_user,
    update_user_preferences,
)
from config import Config
from utils.i18n_locale import with_request_locale

ALLOWED_UI_LOCALES = ("pt-BR", "en-US", "es-419", "fr-FR")
ALLOWED_PREFERENCE_FIELDS = ("ui_locale", "market_country", "currency_override")
_COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")
_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")


def _validate_preferences(raw):
    """Valida o bloco `preferences` do body do PATCH. Retorna
    (preferences_limpo, erro_tuple). Em caso de erro, preferences_limpo e None
    e erro_tuple e (message_code, http_status)."""
    if not isinstance(raw, dict):
        return None, ("invalid_preferences", 400)

    unknown = [k for k in raw.keys() if k not in ALLOWED_PREFERENCE_FIELDS]
    if unknown:
        return None, ("unknown_preference_field", 400)

    if not any(k in raw for k in ALLOWED_PREFERENCE_FIELDS):
        return None, ("no_preferences_fields", 400)

    clean = {}

    if "ui_locale" in raw:
        value = raw["ui_locale"]
        if not isinstance(value, str) or value not in ALLOWED_UI_LOCALES:
            return None, ("invalid_ui_locale", 400)
        clean["ui_locale"] = value

    if "market_country" in raw:
        value = raw["market_country"]
        if not isinstance(value, str) or not _COUNTRY_RE.match(value):
            return None, ("invalid_market_country", 400)
        clean["market_country"] = value.upper()

    if "currency_override" in raw:
        value = raw["currency_override"]
        if value is None:
            clean["currency_override"] = None
        elif isinstance(value, str) and _CURRENCY_RE.match(value):
            clean["currency_override"] = value.upper()
        else:
            return None, ("invalid_currency_override", 400)

    return clean, None

auth_bp = Blueprint('auth', __name__)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
JWT_SECRET = os.getenv("JWT_SECRET", os.urandom(32).hex())
JWT_EXPIRY_DAYS = 7

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def _get_redirect_uri():
    """Monta o redirect URI baseado no ambiente."""
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return f"{frontend_url}/auth/callback"


def _create_jwt(user_id, email):
    """Cria um JWT com user_id e email."""
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_jwt(token):
    """Decodifica e valida um JWT. Retorna payload ou None."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def get_current_user(req):
    """Extrai e valida usuario do Bearer token. Retorna dict do user ou None."""
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    payload = decode_jwt(auth_header[7:])
    if not payload:
        return None
    return get_user_by_id(payload["user_id"])


@auth_bp.route('/auth/google', methods=['GET'])
def google_login():
    """Redireciona para Google OAuth consent screen."""
    redirect_uri = _get_redirect_uri()
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": "google",
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    return redirect(f"{GOOGLE_AUTH_URL}?{query}")


@auth_bp.route('/auth/google/callback', methods=['POST'])
def google_callback():
    """Recebe o code do Google (enviado pelo frontend), troca por token, cria/atualiza usuario."""
    data = request.get_json()
    code = data.get("code") if data else None
    if not code:
        return jsonify({"error": "Campo 'code' e obrigatorio"}), 400

    redirect_uri = _get_redirect_uri()

    # Trocar code por access token
    token_resp = requests.post(GOOGLE_TOKEN_URL, data={
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })

    if token_resp.status_code != 200:
        return jsonify({"error": "Falha ao trocar code por token"}), 400

    access_token = token_resp.json().get("access_token")

    # Buscar dados do usuario no Google
    userinfo_resp = requests.get(GOOGLE_USERINFO_URL, headers={
        "Authorization": f"Bearer {access_token}"
    })

    if userinfo_resp.status_code != 200:
        return jsonify({"error": "Falha ao obter dados do Google"}), 400

    userinfo = userinfo_resp.json()
    google_id = userinfo["id"]
    email = userinfo["email"]
    name = userinfo.get("name", "")
    picture = userinfo.get("picture", "")

    # Criar ou atualizar usuario no banco
    user = upsert_user("google", google_id, email, name, picture)

    # Gerar JWT
    token = _create_jwt(user["id"], user["email"])

    return jsonify({
        "token": token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "picture_url": user["picture_url"],
        }
    })


@auth_bp.route('/auth/me', methods=['GET'])
@with_request_locale
def get_me():
    """Retorna dados do usuario logado + creditos restantes."""
    user = get_current_user(request)
    if not user:
        return jsonify({"error": "Token invalido ou expirado"}), 401

    from db.models_auth import count_messages_today
    used = count_messages_today(user["id"])
    limit = Config.USER_CREDIT_LIMIT
    remaining = max(0, limit - used)

    return jsonify({
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "picture_url": user["picture_url"],
            "provider": user.get("provider", "google"),
            "last_login": user.get("last_login"),
        },
        "preferences": {
            "ui_locale": user.get("ui_locale") or "pt-BR",
            "market_country": user.get("market_country") or "BR",
            "currency_override": user.get("currency_override"),
        },
        "credits": {
            "used": used,
            "remaining": remaining,
            "limit": limit,
        }
    })


def _get_bearer_payload(req):
    """F1.7 - Retorna (payload, error_tuple).

    Distingue entre token ausente/invalido (401 unauthorized) e JWT valido
    cujo user_id nao existe mais no banco (404 user_not_found). Diferente de
    `get_current_user`, que colapsa os dois casos em None.

    Em sucesso: (payload_dict, None).
    Em 401: (None, ('unauthorized', 401)).
    """
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, ("unauthorized", 401)
    payload = decode_jwt(auth_header[7:])
    if not payload or "user_id" not in payload:
        return None, ("unauthorized", 401)
    return payload, None


@auth_bp.route('/auth/me/preferences', methods=['PATCH'])
@with_request_locale
def patch_preferences():
    """F1.7 - Atualiza preferencias i18n do usuario autenticado.

    Body esperado:
      { "preferences": { "ui_locale": "...", "market_country": "...",
                          "currency_override": "..." } }

    Pelo menos uma das 3 chaves deve estar presente. Valida whitelist de
    ui_locale, ISO alpha-2 de market_country, ISO 4217 de currency_override.
    Nao valida contra enabled_locales nem markets.json nesta fase.
    """
    payload, err = _get_bearer_payload(request)
    if err is not None:
        code, status = err
        return jsonify({
            "error": code,
            "message_code": f"errors.auth.{code}",
        }), status

    user = get_user_by_id(payload["user_id"])
    if not user:
        return jsonify({
            "error": "user_not_found",
            "message_code": "errors.auth.user_not_found",
        }), 404

    try:
        body = request.get_json(silent=False)
    except Exception:
        body = None

    if not isinstance(body, dict):
        return jsonify({
            "error": "invalid_json",
            "message_code": "errors.auth.invalid_json",
        }), 400

    if "preferences" not in body:
        return jsonify({
            "error": "missing_preferences",
            "message_code": "errors.auth.missing_preferences",
        }), 400

    clean, err = _validate_preferences(body.get("preferences"))
    if err is not None:
        code, status = err
        return jsonify({
            "error": code,
            "message_code": f"errors.auth.{code}",
        }), status

    updated = update_user_preferences(user["id"], clean)
    if updated is None:
        return jsonify({
            "error": "user_not_found",
            "message_code": "errors.auth.user_not_found",
        }), 404

    return jsonify({"preferences": updated})


@auth_bp.route('/auth/me', methods=['DELETE'])
@with_request_locale
def delete_me():
    """DELETE /api/auth/me — exclui a conta do usuario autenticado.
    Cascade: conversations deletadas, message_log.user_id set NULL."""
    user = get_current_user(request)
    if not user:
        return jsonify({"error": "Token invalido ou expirado"}), 401

    deleted = delete_user(user["id"])
    if not deleted:
        return jsonify({"error": "Usuario nao encontrado"}), 404

    return jsonify({"message": "Conta excluida com sucesso"})


@auth_bp.route('/auth/logout', methods=['POST'])
def logout():
    """Logout — no server-side, JWT e stateless. Frontend remove o token."""
    return jsonify({"message": "Logout realizado com sucesso"})
