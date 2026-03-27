"""Rotas de compartilhamento: criar e recuperar shares."""

from flask import Blueprint, request, jsonify

from db.models_share import create_share, get_share, increment_views

sharing_bp = Blueprint('sharing', __name__)

SHARE_BASE_URL = "https://chat.winegod.ai/c"


@sharing_bp.route('/share', methods=['POST'])
def post_share():
    """POST /api/share — Cria compartilhamento."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Body JSON obrigatorio"}), 400

    wine_ids = data.get("wine_ids")
    if not wine_ids or not isinstance(wine_ids, list):
        return jsonify({"error": "wine_ids obrigatorio (lista de IDs)"}), 400

    title = data.get("title", "")
    context = data.get("context", "")

    try:
        share_id = create_share(title, context, wine_ids)
        return jsonify({
            "share_id": share_id,
            "url": f"{SHARE_BASE_URL}/{share_id}",
        }), 201
    except Exception as e:
        return jsonify({"error": f"Erro ao criar compartilhamento: {str(e)}"}), 500


@sharing_bp.route('/share/<share_id>', methods=['GET'])
def get_share_by_id(share_id):
    """GET /api/share/:id — Recupera compartilhamento + vinhos."""
    try:
        share = get_share(share_id)
        if not share:
            return jsonify({"error": "Compartilhamento nao encontrado"}), 404

        # Incrementa views em background (nao bloqueia resposta)
        try:
            increment_views(share_id)
        except Exception:
            pass  # view_count e best-effort

        return jsonify(share), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao buscar compartilhamento: {str(e)}"}), 500
