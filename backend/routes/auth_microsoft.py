import os
import requests
from flask import Blueprint, request, jsonify, redirect
from db.models_auth import upsert_user
from routes.auth import _create_jwt, _get_redirect_uri

auth_microsoft_bp = Blueprint('auth_microsoft', __name__)

MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")

# /consumers/ aceita contas pessoais (Hotmail, Outlook)
MS_AUTH_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
MS_USERINFO_URL = "https://graph.microsoft.com/v1.0/me"


@auth_microsoft_bp.route('/auth/microsoft', methods=['GET'])
def microsoft_login():
    """Redireciona para Microsoft OAuth consent screen."""
    redirect_uri = _get_redirect_uri()
    params = {
        "client_id": MICROSOFT_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile User.Read",
        "state": "microsoft",
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    return redirect(f"{MS_AUTH_URL}?{query}")


@auth_microsoft_bp.route('/auth/microsoft/callback', methods=['POST'])
def microsoft_callback():
    """Recebe o code da Microsoft, troca por token, cria/atualiza usuario."""
    data = request.get_json()
    code = data.get("code") if data else None
    if not code:
        return jsonify({"error": "Campo 'code' e obrigatorio"}), 400

    redirect_uri = _get_redirect_uri()

    # Trocar code por access token
    token_resp = requests.post(MS_TOKEN_URL, data={
        "client_id": MICROSOFT_CLIENT_ID,
        "client_secret": MICROSOFT_CLIENT_SECRET,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "scope": "openid email profile User.Read",
    })

    if token_resp.status_code != 200:
        return jsonify({"error": "Falha ao trocar code por token"}), 400

    access_token = token_resp.json().get("access_token")

    # Buscar dados do usuario no Microsoft Graph
    userinfo_resp = requests.get(MS_USERINFO_URL, headers={
        "Authorization": f"Bearer {access_token}",
    })

    if userinfo_resp.status_code != 200:
        return jsonify({"error": "Falha ao obter dados da Microsoft"}), 400

    userinfo = userinfo_resp.json()
    microsoft_id = userinfo["id"]
    name = userinfo.get("displayName", "")
    email = userinfo.get("mail") or userinfo.get("userPrincipalName", "")

    if not email:
        return jsonify({"error": "Email nao disponivel na conta Microsoft"}), 400

    # Criar ou atualizar usuario (Microsoft Graph tem foto mas e complexo — passar vazio)
    user = upsert_user("microsoft", microsoft_id, email, name, "")

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
