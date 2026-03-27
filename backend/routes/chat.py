import json
import time
import uuid
from flask import Blueprint, request, jsonify, Response
from services.baco import get_baco_response, stream_baco_response, MODEL
from tools.media import process_image

chat_bp = Blueprint('chat', __name__)

# Sessoes em memoria: {session_id: {"messages": [...], "last_access": timestamp}}
sessions = {}

SESSION_EXPIRY = 3600  # 1 hora
MAX_HISTORY = 10


def _get_session(session_id):
    """Retorna ou cria sessao, removendo expiradas."""
    now = time.time()

    # Limpar sessoes expiradas
    expired = [sid for sid, s in sessions.items() if now - s["last_access"] > SESSION_EXPIRY]
    for sid in expired:
        del sessions[sid]

    if session_id not in sessions:
        sessions[session_id] = {"messages": [], "last_access": now}

    session = sessions[session_id]
    session["last_access"] = now
    return session


def _process_image_context(data, message):
    """Se houver campo image no request, roda OCR e prepend contexto ao message."""
    image_base64 = data.get("image")
    if not image_base64:
        return message

    ocr = process_image(image_base64)
    if ocr.get("status") == "success":
        return (
            f"[O usuario enviou foto de um rotulo. OCR identificou: {ocr['search_text']}. "
            f"Use search_wine para buscar este vinho e responda sobre ele.]\n\n{message}"
        )
    return (
        f"[O usuario tentou enviar uma foto mas nao foi possivel identificar o vinho.]\n\n{message}"
    )


@chat_bp.route('/chat', methods=['POST'])
def chat():
    """POST /api/chat — Envia mensagem e recebe resposta completa do Baco."""
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Campo 'message' e obrigatorio"}), 400

    message = data["message"]
    session_id = data.get("session_id", str(uuid.uuid4()))
    message = _process_image_context(data, message)

    session = _get_session(session_id)
    history = session["messages"][-MAX_HISTORY:]

    try:
        response_text, model = get_baco_response(message, session_id, history)
    except Exception as e:
        return jsonify({"error": f"Erro ao chamar Claude API: {str(e)}"}), 500

    # Salvar no historico
    session["messages"].append({"role": "user", "content": message})
    session["messages"].append({"role": "assistant", "content": response_text})

    return jsonify({
        "response": response_text,
        "session_id": session_id,
        "model": model,
    })


@chat_bp.route('/chat/stream', methods=['POST'])
def chat_stream():
    """POST /api/chat/stream — SSE streaming da resposta do Baco."""
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Campo 'message' e obrigatorio"}), 400

    message = data["message"]
    session_id = data.get("session_id", str(uuid.uuid4()))
    message = _process_image_context(data, message)

    session = _get_session(session_id)
    history = session["messages"][-MAX_HISTORY:]

    def generate():
        yield f"data: {json.dumps({'type': 'start'})}\n\n"

        full_response = []
        try:
            for chunk in stream_baco_response(message, session_id, history):
                full_response.append(chunk)
                yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'end', 'model': MODEL})}\n\n"

        # Salvar no historico apos streaming completo
        session["messages"].append({"role": "user", "content": message})
        session["messages"].append({"role": "assistant", "content": "".join(full_response)})

    return Response(generate(), mimetype='text/event-stream',
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
