import json
import time
import uuid
from flask import Blueprint, request, jsonify, Response
from services.baco import get_baco_response, stream_baco_response, MODEL
from tools.media import process_image, process_images_batch, process_video, process_pdf
from routes.credits import require_credits

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


def _build_image_context(ocr_result):
    """Gera contexto textual para o Claude baseado no tipo de imagem detectado."""
    image_type = ocr_result.get("image_type", "")

    if image_type == "label":
        search_text = ocr_result.get("search_text", "")
        return (
            f"[O usuario enviou foto de um rotulo. OCR identificou: {search_text}. "
            f"Use search_wine para buscar este vinho e responda sobre ele.]"
        )
    elif image_type == "screenshot":
        wines = ocr_result.get("wines", [])
        if wines:
            names = [w.get("name", "?") for w in wines]
            return (
                f"[O usuario enviou screenshot com {len(wines)} vinho(s): {', '.join(names)}. "
                f"Use search_wine para buscar cada vinho e responda sobre eles.]"
            )
        return "[O usuario enviou screenshot mas nenhum vinho foi identificado.]"
    elif image_type == "shelf":
        wines = ocr_result.get("wines", [])
        total = ocr_result.get("total_visible", len(wines))
        if wines:
            names = [w.get("name", "?") for w in wines]
            return (
                f"[O usuario enviou foto de prateleira com ~{total} garrafas. "
                f"Consegui ler {len(wines)}: {', '.join(names)}. "
                f"Use search_wine para buscar os vinhos legiveis e responda sobre eles.]"
            )
        return f"[O usuario enviou foto de prateleira com ~{total} garrafas mas nenhum rotulo foi legivel.]"

    return "[O usuario tentou enviar uma foto mas nao foi possivel identificar o vinho.]"


def _build_batch_context(batch_result):
    """Gera contexto textual para batch de imagens."""
    parts = []

    for label in batch_result.get("labels", []):
        search_text = label.get("search_text", "")
        parts.append(f"Rotulo: {search_text}")

    for ss in batch_result.get("screenshots", []):
        wines = ss.get("wines", [])
        if wines:
            names = [w.get("name", "?") for w in wines]
            parts.append(f"Screenshot: {', '.join(names)}")

    for shelf in batch_result.get("shelves", []):
        wines = shelf.get("wines", [])
        total = shelf.get("total_visible", len(wines))
        if wines:
            names = [w.get("name", "?") for w in wines]
            parts.append(f"Prateleira (~{total} garrafas): {', '.join(names)}")

    errors = batch_result.get("errors", [])
    if errors:
        parts.append(f"{len(errors)} imagem(ns) sem vinho")

    if not parts:
        return "[O usuario enviou fotos mas nenhum vinho foi identificado.]"

    wines_text = " | ".join(parts)
    return (
        f"[O usuario enviou {batch_result.get('image_count', 0)} foto(s). {wines_text}. "
        f"Use search_wine para buscar estes vinhos e responda sobre eles.]"
    )


def _process_media_context(data, message):
    """Detecta images/image/video/pdf no payload e gera contexto para o Claude."""
    # Multiple images (batch)
    images = data.get("images")
    if images and isinstance(images, list) and len(images) > 0:
        if len(images) == 1:
            ocr = process_image(images[0])
            context = _build_image_context(ocr)
        else:
            batch = process_images_batch(images)
            context = _build_batch_context(batch)
        return f"{context}\n\n{message}"

    # Single image (backward compatible)
    image_base64 = data.get("image")
    if image_base64:
        ocr = process_image(image_base64)
        context = _build_image_context(ocr)
        return f"{context}\n\n{message}"

    # Video
    video_base64 = data.get("video")
    if video_base64:
        result = process_video(video_base64)
        if result.get("status") == "success":
            desc = result.get("description", "")
            return (
                f"[O usuario enviou um video. {desc}. "
                f"Use search_wine para buscar estes vinhos e responda sobre eles.]\n\n{message}"
            )
        msg = result.get("message", "Nao foi possivel processar o video.")
        return f"[O usuario tentou enviar um video. {msg}]\n\n{message}"

    # PDF
    pdf_base64 = data.get("pdf")
    if pdf_base64:
        result = process_pdf(pdf_base64)
        if result.get("status") == "success":
            desc = result.get("description", "")
            return (
                f"[O usuario enviou um PDF (carta de vinhos/catalogo). {desc}. "
                f"Use search_wine para buscar estes vinhos e responda sobre eles.]\n\n{message}"
            )
        msg = result.get("message", "Nao foi possivel processar o PDF.")
        return f"[O usuario tentou enviar um PDF. {msg}]\n\n{message}"

    return message


@chat_bp.route('/chat', methods=['POST'])
@require_credits
def chat():
    """POST /api/chat — Envia mensagem e recebe resposta completa do Baco."""
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Campo 'message' e obrigatorio"}), 400

    message = data["message"]
    session_id = data.get("session_id", str(uuid.uuid4()))
    message = _process_media_context(data, message)

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
@require_credits
def chat_stream():
    """POST /api/chat/stream — SSE streaming da resposta do Baco."""
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Campo 'message' e obrigatorio"}), 400

    message = data["message"]
    session_id = data.get("session_id", str(uuid.uuid4()))
    message = _process_media_context(data, message)

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
