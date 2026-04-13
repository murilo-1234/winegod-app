import os
import json
import time
import jwt
import requests
from flask import Blueprint, request, redirect, jsonify
from db.models_auth import upsert_user
from routes.auth import _create_jwt

auth_apple_bp = Blueprint('auth_apple', __name__)

APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "")
APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID", "")
APPLE_KEY_ID = os.getenv("APPLE_KEY_ID", "")
APPLE_PRIVATE_KEY = os.getenv("APPLE_PRIVATE_KEY", "").replace("\\n", "\n")

APPLE_AUTH_URL = "https://appleid.apple.com/auth/authorize"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"


def _get_apple_redirect_uri():
    """Redirect URI para Apple aponta pro BACKEND (form_post)."""
    backend_url = os.getenv("BACKEND_URL", "http://localhost:5000")
    return f"{backend_url}/api/auth/apple/web-callback"


def _generate_apple_client_secret():
    """Gera o client_secret como JWT assinado com a private key (ES256)."""
    now = int(time.time())
    payload = {
        "iss": APPLE_TEAM_ID,
        "iat": now,
        "exp": now + 86400 * 180,
        "aud": "https://appleid.apple.com",
        "sub": APPLE_CLIENT_ID,
    }
    return jwt.encode(payload, APPLE_PRIVATE_KEY, algorithm="ES256",
                      headers={"kid": APPLE_KEY_ID})


@auth_apple_bp.route('/auth/apple', methods=['GET'])
def apple_login():
    """Redireciona para Apple Sign-In consent screen."""
    redirect_uri = _get_apple_redirect_uri()
    params = {
        "client_id": APPLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "response_mode": "form_post",
        "scope": "name email",
        "state": "apple",
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    return redirect(f"{APPLE_AUTH_URL}?{query}")


@auth_apple_bp.route('/auth/apple/web-callback', methods=['POST'])
def apple_web_callback():
    """Apple faz POST aqui com form data. Troca code, gera JWT, redireciona pro frontend."""
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    code = request.form.get("code")

    if not code:
        return redirect(f"{frontend_url}/auth/callback?error=apple_no_code")

    # Extrair nome (so vem na primeira autorizacao)
    name = ""
    user_data = request.form.get("user", "")
    if user_data:
        try:
            user_json = json.loads(user_data)
            first = user_json.get("name", {}).get("firstName", "")
            last = user_json.get("name", {}).get("lastName", "")
            name = f"{first} {last}".strip()
        except (json.JSONDecodeError, AttributeError):
            pass

    # Trocar code por id_token
    client_secret = _generate_apple_client_secret()
    token_resp = requests.post(APPLE_TOKEN_URL, data={
        "client_id": APPLE_CLIENT_ID,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": _get_apple_redirect_uri(),
    })

    if token_resp.status_code != 200:
        return redirect(f"{frontend_url}/auth/callback?error=apple_token_fail")

    id_token = token_resp.json().get("id_token")
    if not id_token:
        return redirect(f"{frontend_url}/auth/callback?error=apple_no_id_token")

    # Decodificar id_token (confiavel — recebido direto da Apple via HTTPS)
    claims = jwt.decode(id_token, options={"verify_signature": False})
    apple_id = claims["sub"]
    email = claims.get("email", "")

    if not email:
        return redirect(f"{frontend_url}/auth/callback?error=apple_no_email")

    # Usar email como fallback para nome
    if not name:
        name = email.split("@")[0]

    # Criar ou atualizar usuario (Apple nao fornece foto)
    user = upsert_user("apple", apple_id, email, name, "")

    # Gerar JWT interno e redirecionar pro frontend com token na URL
    token = _create_jwt(user["id"], user["email"])
    return redirect(f"{frontend_url}/auth/callback?token={token}&provider=apple")
