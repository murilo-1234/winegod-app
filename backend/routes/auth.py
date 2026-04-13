import os
import jwt
import requests
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, redirect
from db.models_auth import upsert_user, get_user_by_id
from config import Config

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
        "access_type": "offline",
        "prompt": "consent",
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
        "credits": {
            "used": used,
            "remaining": remaining,
            "limit": limit,
        }
    })


@auth_bp.route('/auth/logout', methods=['POST'])
def logout():
    """Logout — no server-side, JWT e stateless. Frontend remove o token."""
    return jsonify({"message": "Logout realizado com sucesso"})
