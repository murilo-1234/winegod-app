import os
import requests
from flask import Blueprint, request, jsonify, redirect
from db.models_auth import upsert_user
from routes.auth import _create_jwt, _get_redirect_uri

auth_facebook_bp = Blueprint('auth_facebook', __name__)

FACEBOOK_APP_ID = os.getenv("FACEBOOK_APP_ID", "")
FACEBOOK_APP_SECRET = os.getenv("FACEBOOK_APP_SECRET", "")

FB_AUTH_URL = "https://www.facebook.com/v19.0/dialog/oauth"
FB_TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"
FB_USERINFO_URL = "https://graph.facebook.com/v19.0/me"


@auth_facebook_bp.route('/auth/facebook', methods=['GET'])
def facebook_login():
    """Redireciona para Facebook OAuth consent screen."""
    redirect_uri = _get_redirect_uri()
    params = {
        "client_id": FACEBOOK_APP_ID,
        "redirect_uri": redirect_uri,
        "scope": "email,public_profile",
        "response_type": "code",
        "state": "facebook",
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    return redirect(f"{FB_AUTH_URL}?{query}")


@auth_facebook_bp.route('/auth/facebook/callback', methods=['POST'])
def facebook_callback():
    """Recebe o code do Facebook, troca por token, cria/atualiza usuario."""
    data = request.get_json()
    code = data.get("code") if data else None
    if not code:
        return jsonify({"error": "Campo 'code' e obrigatorio"}), 400

    redirect_uri = _get_redirect_uri()

    # Trocar code por access token
    token_resp = requests.get(FB_TOKEN_URL, params={
        "client_id": FACEBOOK_APP_ID,
        "client_secret": FACEBOOK_APP_SECRET,
        "redirect_uri": redirect_uri,
        "code": code,
    })

    if token_resp.status_code != 200:
        return jsonify({"error": "Falha ao trocar code por token"}), 400

    access_token = token_resp.json().get("access_token")

    # Buscar dados do usuario no Facebook
    userinfo_resp = requests.get(FB_USERINFO_URL, params={
        "fields": "id,name,email,picture.type(large)",
        "access_token": access_token,
    })

    if userinfo_resp.status_code != 200:
        return jsonify({"error": "Falha ao obter dados do Facebook"}), 400

    userinfo = userinfo_resp.json()
    facebook_id = userinfo["id"]
    email = userinfo.get("email", "")
    name = userinfo.get("name", "")
    picture = ""
    if userinfo.get("picture", {}).get("data", {}).get("url"):
        picture = userinfo["picture"]["data"]["url"]

    if not email:
        return jsonify({"error": "Email nao disponivel na conta Facebook"}), 400

    # Criar ou atualizar usuario no banco
    user = upsert_user("facebook", facebook_id, email, name, picture)

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
