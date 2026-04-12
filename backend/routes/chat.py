import json
import time
import uuid
from flask import Blueprint, request, jsonify, Response
from services.baco import get_baco_response, stream_baco_response, MODEL
from tools.media import process_image, process_images_batch, process_video, process_pdf
from tools.resolver import resolve_wines_from_ocr, format_resolved_context
from services.tracing import RequestTrace
from routes.credits import require_credits

chat_bp = Blueprint('chat', __name__)

# Sessoes em memoria: {session_id: {"messages": [...], "last_access": timestamp}}
sessions = {}

SESSION_EXPIRY = 3600  # 1 hora
MAX_HISTORY = 10


def _get_session(session_id):
    """Retorna ou cria sessao, removendo expiradas."""
    now = time.time()

    expired = [sid for sid, s in sessions.items() if now - s["last_access"] > SESSION_EXPIRY]
    for sid in expired:
        del sessions[sid]

    if session_id not in sessions:
        sessions[session_id] = {"messages": [], "last_access": now}

    session = sessions[session_id]
    session["last_access"] = now
    return session


def _has_media(data):
    """Retorna True se o payload contem midia."""
    if data.get("images") and isinstance(data["images"], list) and len(data["images"]) > 0:
        return True
    if data.get("image"):
        return True
    if data.get("video"):
        return True
    if data.get("pdf"):
        return True
    return False


def _process_media(data, message, trace):
    """Processa midia com OCR + pre-resolve. Retorna (context_message, photo_mode).

    Imagens: OCR -> pre-resolve no banco -> contexto rico para o Claude.
    Video/PDF: OCR -> texto descritivo (sem pre-resolve, fica para o Claude buscar).
    """
    # --- Imagens (single ou batch) ---
    images = data.get("images")
    single_image = data.get("image")

    if images and isinstance(images, list) and len(images) > 0:
        if len(images) == 1:
            return _process_single_image(images[0], message, trace)
        else:
            return _process_batch_images(images, message, trace)

    if single_image:
        return _process_single_image(single_image, message, trace)

    # --- Video ---
    video_base64 = data.get("video")
    if video_base64:
        with trace.step("video_process"):
            result = process_video(video_base64)
        if result.get("status") == "success":
            desc = result.get("description", "")
            ctx = (
                f"[O usuario enviou um video. {desc}. "
                f"Use search_wine para buscar estes vinhos e responda sobre eles.]"
            )
            return f"{ctx}\n\n{message}", False
        msg = result.get("message", "Nao foi possivel processar o video.")
        return f"[O usuario tentou enviar um video. {msg}]\n\n{message}", False

    # --- PDF ---
    pdf_base64 = data.get("pdf")
    if pdf_base64:
        with trace.step("pdf_process"):
            result = process_pdf(pdf_base64)
        if result.get("status") == "success":
            desc = result.get("description", "")
            method = result.get("extraction_method", "unknown")
            was_truncated = result.get("was_truncated", False)
            pages = result.get("pages_processed", "?")

            # Contexto honesto: informar branch de extracao ao Baco
            if method == "native_text":
                source_note = "Texto extraido diretamente do PDF (alta confianca)"
            elif method == "native_text_chunked":
                source_note = (
                    "Texto extraido do PDF em partes apos falha do parse inicial "
                    "(confianca moderada — alguns trechos podem ter sido pulados)"
                )
            elif method == "visual_fallback":
                source_note = "PDF escaneado — leitura visual por OCR (confianca moderada)"
            else:
                source_note = "Leitura de PDF"

            truncation_note = ""
            if was_truncated:
                truncation_note = (
                    " ATENCAO: o PDF foi truncado por tamanho — "
                    "podem existir vinhos adicionais nao listados aqui."
                )

            ctx = (
                f"[O usuario enviou um PDF ({pages} paginas processadas). "
                f"{source_note}.{truncation_note}\n\n"
                f"{desc}\n\n"
                f"REGRAS CRITICAS DESTE PDF (siga sem excecao):\n\n"
                f"1) FONTE UNICA DA CARTA: a lista numerada acima e a UNICA fonte "
                f"sobre o que existe na carta do cliente. Se um vinho NAO aparece "
                f"textualmente nessa lista, ele NAO esta na carta. Ponto.\n\n"
                f"2) USO CORRETO DO search_wine: search_wine serve APENAS para "
                f"enriquecer, confirmar na base e trazer nota/score/dados adicionais "
                f"dos itens da lista acima. search_wine NAO serve para encontrar "
                f"alternativas, sugerir rotulos parecidos, trocar um produtor por "
                f"outro, nem trocar um vinho da carta por outro 'melhor' da base. "
                f"EFICIENCIA: faca NO MAXIMO UMA chamada de search_wine por item da "
                f"lista. NAO repita variantes do mesmo nome (ex: 'Brunello', "
                f"'Brunello Frescobaldi', 'Frescobaldi Brunello'). Quando o produtor "
                f"existir no PDF, passe-o no parametro 'produtor' do search_wine — "
                f"isso ajuda a achar match mais rapido. Se a primeira tentativa nao "
                f"retornar match compativel, marque o item como nao confirmado e siga "
                f"em frente sem reintentar.\n\n"
                f"3) IDENTIDADE DO ITEM: para considerar que um vinho do banco "
                f"corresponde a um item da carta, o nome sozinho NAO basta. O match "
                f"precisa ser compativel em produtor (quando o produtor existir no "
                f"PDF) e/ou regiao/denominacao quando isso diferenciar vinhos "
                f"parecidos. Se houver divergencia material de produtor, safra ou "
                f"regiao, trate como vinho DIFERENTE e FORA da carta. Exemplo: se o "
                f"PDF tem 'Brunello di Montalcino - Frescobaldi' e o search retorna "
                f"'Brunello di Montalcino - Tenuta Il Poggione', isso NAO e o mesmo "
                f"item da carta - NAO pode ser ranqueado nem recomendado como vinho "
                f"do PDF.\n\n"
                f"4) RANKING DA CARTA: para ranquear custo-beneficio 'da carta', use "
                f"APENAS itens da lista acima que tenham (a) match compativel na "
                f"base e (b) score real disponivel. Se nenhum item da lista preencher "
                f"isso, diga literalmente: 'Eu nao consigo ranquear o custo-beneficio "
                f"desta carta com seguranca porque os itens confirmados da carta nao "
                f"tem score suficiente na base.'\n\n"
                f"5) HONESTIDADE: se o banco trouxer vinhos similares mas nao "
                f"identicos, voce pode mencionar como observacao externa, mas SEMPRE "
                f"deixe claro 'isso existe na nossa base, mas NAO esta na carta do "
                f"seu PDF'. Nunca promova um vinho fora da carta a recomendacao da "
                f"carta.]"
            )
            return f"{ctx}\n\n{message}", False
        msg = result.get("message", "Nao foi possivel processar o PDF.")
        return f"[O usuario tentou enviar um PDF. {msg}]\n\n{message}", False

    return message, False


def _process_single_image(base64_image, message, trace):
    """OCR + pre-resolve para uma imagem."""
    with trace.step("ocr"):
        ocr = process_image(base64_image)

    image_type = ocr.get("image_type", "")

    # OCR falhou ou nao e vinho — devolver mensagem amigavel, sem photo_mode
    if image_type in ("not_wine", "error"):
        friendly = ocr.get("message", "Nao foi possivel identificar vinho na foto.")
        ctx = f"[O usuario enviou uma foto. {friendly}]"
        return f"{ctx}\n\n{message}", False

    with trace.step("pre_resolve"):
        resolved = resolve_wines_from_ocr(ocr)

    context = format_resolved_context(
        resolved["resolved_wines"], resolved["unresolved"],
        image_type, ocr,
        resolved_items=resolved.get("resolved_items"),
        unresolved_items=resolved.get("unresolved_items"),
    )

    # Preservar preco da foto no contexto (apenas label — shelf/screenshot ja tratam por item)
    if image_type == "label":
        ocr_data = ocr.get("ocr_result", {})
        price = ocr_data.get("price") if isinstance(ocr_data, dict) else None
        if price:
            context += f"\n[Preco visivel na foto: {price}]"

    return f"{context}\n\n{message}", True


def _process_batch_images(images, message, trace):
    """OCR batch + pre-resolve para multiplas imagens."""
    with trace.step("ocr_batch"):
        batch = process_images_batch(images)

    error_count = len(batch.get("errors", []))
    has_any_wine = bool(batch.get("labels") or batch.get("screenshots") or batch.get("shelves"))

    # Nenhuma imagem gerou vinho — devolver mensagem honesta, sem photo_mode
    if not has_any_wine:
        count = batch.get("image_count", 0)
        ctx = (
            f"[O usuario enviou {count} foto(s) mas nenhum vinho foi identificado. "
            f"Peca ao usuario para tentar outra foto com mais nitidez ou descrever o vinho.]"
        )
        return f"{ctx}\n\n{message}", False

    all_resolved_items = []
    all_unresolved_items = []

    with trace.step("pre_resolve_batch"):
        for label in batch.get("labels", []):
            r = resolve_wines_from_ocr(label)
            all_resolved_items.extend(r.get("resolved_items", []))
            all_unresolved_items.extend(r.get("unresolved_items", []))

        for group_key in ("screenshots", "shelves"):
            for item in batch.get(group_key, []):
                fake_ocr = {
                    "image_type": "screenshot" if group_key == "screenshots" else "shelf",
                    "wines": item.get("wines", []),
                    "total_visible": item.get("total_visible", 0),
                }
                r = resolve_wines_from_ocr(fake_ocr)
                all_resolved_items.extend(r.get("resolved_items", []))
                all_unresolved_items.extend(r.get("unresolved_items", []))

    # Dedup por id
    seen_ids = set()
    deduped_items = []
    for item in all_resolved_items:
        wid = item["wine"].get("id")
        if wid and wid not in seen_ids:
            seen_ids.add(wid)
            deduped_items.append(item)

    context = _build_batch_resolved_context(batch, deduped_items, all_unresolved_items, error_count)

    # Se nenhum vinho resolvido, photo_mode=False
    photo_mode = bool(deduped_items)
    return f"{context}\n\n{message}", photo_mode


def _build_batch_resolved_context(batch, resolved_items, unresolved_items, error_count=0):
    """Contexto para batch com dados pre-resolvidos, preservando precos OCR por item.

    Usa campo 'status' explicito de cada item para separar em 3 niveis:
    confirmed_with_note, confirmed_no_note, visual_only.
    """
    from services.display import resolve_display

    parts = []
    count = batch.get("image_count", 0)
    parts.append(f"[O usuario enviou {count} foto(s).]")

    if error_count > 0:
        parts.append(f"[{error_count} imagem(ns) nao continham vinho identificavel.]")

    # Separar resolved por status
    items_with_note = [it for it in resolved_items if it.get("status") == "confirmed_with_note"]
    items_no_note = [it for it in resolved_items if it.get("status") == "confirmed_no_note"]

    counter = 1

    # Confirmados COM nota
    if items_with_note:
        parts.append(f"[{len(items_with_note)} vinho(s) CONFIRMADO(S) COM NOTA (apto a ranking/comparacao):]")
        for item in items_with_note:
            ocr_i = item["ocr"]
            w = item["wine"]
            d = resolve_display(w)

            ocr_parts = [f"Lido na imagem: {ocr_i.get('name', '?')}"]
            if ocr_i.get("price"):
                ocr_parts.append(f"Preco visivel na imagem: {ocr_i['price']}")
            if ocr_i.get("rating"):
                ocr_parts.append(f"Nota visivel: {ocr_i['rating']}")

            nota_str = f"{d['display_note']}"
            score_str = f"{d['display_score']}" if d['display_score_available'] else "sem score"

            parts.append(f"  {counter}. {' | '.join(ocr_parts)}")
            parts.append(
                f"     Banco: {w.get('nome', '?')} | {w.get('produtor', '?')} "
                f"| Nota: {nota_str} | Score: {score_str} "
                f"| Preco base: {w.get('preco_min', '?')}-{w.get('preco_max', '?')} {w.get('moeda', '')} "
                f"| ID: {w.get('id', '?')}"
            )
            counter += 1

    # Confirmados SEM nota
    if items_no_note:
        parts.append(f"[{len(items_no_note)} vinho(s) CONFIRMADO(S) SEM NOTA (NAO apto a ranking):]")
        for item in items_no_note:
            ocr_i = item["ocr"]
            w = item["wine"]

            ocr_parts = [f"Lido na imagem: {ocr_i.get('name', '?')}"]
            if ocr_i.get("price"):
                ocr_parts.append(f"Preco visivel na imagem: {ocr_i['price']}")
            if ocr_i.get("rating"):
                ocr_parts.append(f"Nota visivel: {ocr_i['rating']}")

            parts.append(f"  {counter}. {' | '.join(ocr_parts)}")
            parts.append(
                f"     Banco: {w.get('nome', '?')} | {w.get('produtor', '?')} "
                f"| Nota: sem nota | Score: sem score "
                f"| Preco base: {w.get('preco_min', '?')}-{w.get('preco_max', '?')} {w.get('moeda', '')} "
                f"| ID: {w.get('id', '?')}"
            )
            counter += 1

    if not resolved_items:
        parts.append("[Nenhum vinho foi encontrado no banco. Responda com o que sabe dos nomes identificados.]")

    # Nao encontrados (visual_only)
    if unresolved_items:
        parts.append("[NAO ENCONTRADO(S) no banco (apenas leitura visual):]")
        for item in unresolved_items:
            ocr_i = item["ocr"]
            ocr_parts = [ocr_i.get("name", "?")]
            if ocr_i.get("price"):
                ocr_parts.append(f"Preco visivel: {ocr_i['price']}")
            if ocr_i.get("rating"):
                ocr_parts.append(f"Nota visivel: {ocr_i['rating']}")
            parts.append(f"  {counter}. {' | '.join(ocr_parts)}")
            counter += 1

    # Regras de certeza — 3 niveis
    rules = ["[REGRAS DE CERTEZA (3 niveis):"]
    if items_with_note:
        rules.append(
            "  - CONFIRMADO COM NOTA: use nota, score e preco da base com confianca. "
            "Apto a ranking, comparacao e recomendacao."
        )
    if items_no_note:
        rules.append(
            "  - CONFIRMADO SEM NOTA: apresente dados do banco (produtor, preco). "
            "NAO invente nota, score ou qualidade. NAO inclua em ranking ou comparacao."
        )
    if unresolved_items:
        rules.append(
            "  - NAO ENCONTRADO (visual): cite nome e preco visivel. "
            "NAO atribua nota, score, ranking, custo-beneficio ou qualidade. "
            "Diga que ainda nao tem no acervo."
        )
    rules.append(
        "  Para ranking ou recomendacao, use APENAS vinhos CONFIRMADOS COM NOTA.]"
    )
    parts.append("\n".join(rules))

    return "\n".join(parts)


@chat_bp.route('/chat', methods=['POST'])
@require_credits
def chat():
    """POST /api/chat — Envia mensagem e recebe resposta completa do Baco."""
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Campo 'message' e obrigatorio"}), 400

    message = data["message"]
    session_id = data.get("session_id", str(uuid.uuid4()))

    trace = RequestTrace(request_id=session_id)
    has_media = _has_media(data)
    photo_mode = False

    if has_media:
        try:
            message, photo_mode = _process_media(data, message, trace)
        except Exception as e:
            print(f"[chat] _process_media failed: {type(e).__name__}: {e}", flush=True)
            trace.log()
            message = (
                f"[O usuario enviou uma foto mas ocorreu um erro ao processar: {e}. "
                f"Peca desculpas e ofereca alternativa (descrever o vinho).]\n\n{message}"
            )

    session = _get_session(session_id)
    history = session["messages"][-MAX_HISTORY:]

    try:
        with trace.step("baco_response"):
            response_text, model = get_baco_response(
                message, session_id, history,
                photo_mode=photo_mode, trace=trace,
            )
    except Exception as e:
        trace.log()
        return jsonify({"error": f"Erro ao chamar Claude API: {str(e)}"}), 500

    trace.log()

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
    """POST /api/chat/stream — SSE streaming da resposta do Baco.
    Emite status imediato antes do OCR para feedback de usuario."""
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Campo 'message' e obrigatorio"}), 400

    message = data["message"]
    session_id = data.get("session_id", str(uuid.uuid4()))
    has_media = _has_media(data)

    session = _get_session(session_id)
    history = session["messages"][-MAX_HISTORY:]

    def generate():
        trace = RequestTrace(request_id=session_id)
        photo_mode = False
        msg = message

        yield f"data: {json.dumps({'type': 'start'})}\n\n"

        if has_media:
            # Feedback imediato ANTES do OCR pesado — mensagem adequada ao tipo
            if data.get("video"):
                status_msg = "Analisando seu video..."
            elif data.get("pdf"):
                status_msg = "Analisando seu PDF..."
            else:
                status_msg = "Analisando sua foto..."
            yield f"data: {json.dumps({'type': 'status', 'content': status_msg})}\n\n"

            try:
                msg, photo_mode = _process_media(data, message, trace)
            except Exception as e:
                print(f"[chat_stream] _process_media failed: {type(e).__name__}: {e}", flush=True)
                msg = (
                    f"[O usuario enviou uma foto mas ocorreu um erro ao processar: {e}. "
                    f"Peca desculpas e ofereca alternativa (descrever o vinho).]\n\n{message}"
                )

            yield f"data: {json.dumps({'type': 'status', 'content': 'Buscando informacoes...'})}\n\n"

        full_response = []
        try:
            with trace.step("baco_stream"):
                for chunk in stream_baco_response(
                    msg, session_id, history,
                    photo_mode=photo_mode, trace=trace,
                ):
                    full_response.append(chunk)
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            trace.log()
            return

        trace.log()
        yield f"data: {json.dumps({'type': 'end', 'model': MODEL})}\n\n"

        session["messages"].append({"role": "user", "content": msg})
        session["messages"].append({"role": "assistant", "content": "".join(full_response)})

    return Response(generate(), mimetype='text/event-stream',
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
