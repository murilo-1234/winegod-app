from flask import Blueprint, request, jsonify
from routes.auth import get_current_user
from db.models_conversations import (
    create_conversation,
    get_conversation,
    list_conversations,
    update_conversation,
    delete_conversation,
    set_saved,
    DuplicateConversationError,
)

conversations_bp = Blueprint('conversations', __name__)


def _require_user():
    """Retorna user dict ou None."""
    user = get_current_user(request)
    if not user:
        return None
    return user


@conversations_bp.route('/conversations', methods=['GET'])
def list_convs():
    """GET /api/conversations — lista conversas do usuario autenticado.
    Query params opcionais: q (busca em title), limit, offset."""
    user = _require_user()
    if not user:
        return jsonify({"error": "Autenticacao necessaria"}), 401

    query = request.args.get("q", "").strip() or None

    try:
        limit = int(request.args.get("limit", 50))
    except (ValueError, TypeError):
        return jsonify({"error": "Parametro 'limit' invalido"}), 400

    try:
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Parametro 'offset' invalido"}), 400

    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)

    saved_param = request.args.get("saved")
    saved = None
    if saved_param is not None:
        saved = saved_param.lower() == "true"

    convs = list_conversations(user["id"], query=query, saved=saved, limit=limit, offset=offset)
    return jsonify(convs)


@conversations_bp.route('/conversations/<conv_id>', methods=['GET'])
def get_conv(conv_id):
    """GET /api/conversations/<id> — retorna uma conversa com mensagens."""
    user = _require_user()
    if not user:
        return jsonify({"error": "Autenticacao necessaria"}), 401

    conv = get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversa nao encontrada"}), 404
    if conv["user_id"] != user["id"]:
        return jsonify({"error": "Acesso negado"}), 403

    return jsonify(conv)


@conversations_bp.route('/conversations', methods=['POST'])
def create_conv():
    """POST /api/conversations — cria conversa nova."""
    user = _require_user()
    if not user:
        return jsonify({"error": "Autenticacao necessaria"}), 401

    data = request.get_json(silent=True) or {}
    conv_id = data.get("id")
    if not conv_id:
        return jsonify({"error": "Campo 'id' e obrigatorio"}), 400

    title = data.get("title")
    messages = data.get("messages", [])

    if not isinstance(messages, list):
        return jsonify({"error": "Campo 'messages' deve ser um array"}), 400

    try:
        conv = create_conversation(conv_id, user["id"], title=title, messages=messages)
    except DuplicateConversationError:
        existing = get_conversation(conv_id)
        if existing and existing["user_id"] != user["id"]:
            return jsonify({"error": "Acesso negado"}), 403
        return jsonify({"error": "Conversa com este id ja existe"}), 409

    return jsonify(conv), 201


@conversations_bp.route('/conversations/<conv_id>', methods=['PUT'])
def update_conv(conv_id):
    """PUT /api/conversations/<id> — atualiza title e/ou messages."""
    user = _require_user()
    if not user:
        return jsonify({"error": "Autenticacao necessaria"}), 401

    conv = get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversa nao encontrada"}), 404
    if conv["user_id"] != user["id"]:
        return jsonify({"error": "Acesso negado"}), 403

    data = request.get_json(silent=True) or {}
    title = data.get("title")
    messages = data.get("messages")

    if messages is not None and not isinstance(messages, list):
        return jsonify({"error": "Campo 'messages' deve ser um array"}), 400

    updated = update_conversation(conv_id, title=title, messages=messages)
    return jsonify(updated)


@conversations_bp.route('/conversations/<conv_id>/saved', methods=['PUT'])
def set_conv_saved(conv_id):
    """PUT /api/conversations/<id>/saved — marca ou desmarca conversa salva."""
    user = _require_user()
    if not user:
        return jsonify({"error": "Autenticacao necessaria"}), 401

    conv = get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversa nao encontrada"}), 404
    if conv["user_id"] != user["id"]:
        return jsonify({"error": "Acesso negado"}), 403

    data = request.get_json(silent=True) or {}
    saved = data.get("saved")
    if not isinstance(saved, bool):
        return jsonify({"error": "Campo 'saved' (boolean) e obrigatorio"}), 400

    updated = set_saved(conv_id, saved)
    return jsonify(updated)


@conversations_bp.route('/conversations/<conv_id>', methods=['DELETE'])
def delete_conv(conv_id):
    """DELETE /api/conversations/<id> — deleta conversa."""
    user = _require_user()
    if not user:
        return jsonify({"error": "Autenticacao necessaria"}), 401

    conv = get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversa nao encontrada"}), 404
    if conv["user_id"] != user["id"]:
        return jsonify({"error": "Acesso negado"}), 403

    delete_conversation(conv_id)
    return jsonify({"message": "Conversa excluida"}), 200
