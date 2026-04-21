import json
import time
import uuid
from flask import Blueprint, request, jsonify, Response
from services.baco import get_baco_response, stream_baco_response, MODEL
from tools.media import (
    process_image, process_images_batch, process_video, process_pdf,
    extract_wines_from_text, _text_looks_wine_related,
)
from tools.resolver import resolve_wines_from_ocr, format_resolved_context
from services.discovery import discover_unknowns, log_discovery
from services.new_wines import auto_create_unknowns
from services.tracing import RequestTrace
from routes.credits import require_credits
from routes.auth import get_current_user
from utils.i18n_locale import with_request_locale
from db.models_conversations import (
    create_conversation, get_conversation, update_conversation,
    delete_conversation, DuplicateConversationError,
)

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
        sessions[session_id] = {"messages": [], "clean_messages": [], "last_access": now}

    session = sessions[session_id]
    if "clean_messages" not in session:
        session["clean_messages"] = []
    session["last_access"] = now
    return session


def _sanitize_user_message(original_message, data):
    """Build a clean user-facing message for persistence.

    Adds a media type prefix when applicable.
    Never includes base64, blobs, or internal prompts.
    """
    prefix = ""
    if data.get("video"):
        prefix = "[Video] "
    elif data.get("pdf"):
        prefix = "[PDF] "
    elif data.get("images") or data.get("image"):
        prefix = "[Foto] "

    text = (original_message or "").strip()
    if prefix and not text:
        return prefix.strip()
    if prefix:
        return prefix + text
    return text


def _generate_title(user_text, assistant_text=None):
    """Generate conversation title from first user message or assistant response.

    Strips media prefixes before deriving title.
    Falls back to assistant response if user text is too short.
    """
    text = (user_text or "").strip()
    for pfx in ("[Foto] ", "[Video] ", "[PDF] ", "[Foto]", "[Video]", "[PDF]"):
        if text.startswith(pfx):
            remainder = text[len(pfx):].strip()
            text = remainder if remainder else ""
            break

    if text and len(text) > 3:
        return text[:100]

    if assistant_text:
        return assistant_text.strip()[:100]

    return "Nova conversa"


def _init_clean_messages(session, session_id, user_id):
    """Load clean_messages from DB if session is fresh (handles server restart).

    Only queries DB when clean_messages is empty and user is authenticated.
    """
    if session["clean_messages"]:
        return
    try:
        existing = get_conversation(session_id)
        if existing and existing["user_id"] == user_id:
            session["clean_messages"] = existing.get("messages", [])
    except Exception:
        pass


def _ensure_conversation_shell(session_id, user_id):
    """Create empty conversation shell if none exists for this session.

    Called at the start of the first authenticated chat for a new session_id.
    Returns True if a new shell was just created (needs cleanup on failure).
    Returns False if conversation already existed or creation was skipped.
    """
    try:
        existing = get_conversation(session_id)
        if existing:
            if existing["user_id"] != user_id:
                print(f"[conversation_shell] Foreign ownership: {session_id}", flush=True)
            return False
        try:
            create_conversation(session_id, user_id, title=None, messages=[])
            return True
        except DuplicateConversationError:
            recheck = get_conversation(session_id)
            if recheck and recheck["user_id"] != user_id:
                print(f"[conversation_shell] Foreign owner after race: {session_id}", flush=True)
            return False
    except Exception as e:
        print(f"[conversation_shell] Error: {type(e).__name__}: {e}", flush=True)
        return False


def _persist_conversation(session_id, user_id, clean_messages):
    """Update conversation with messages and title after successful response.

    If shell exists: updates messages; sets title only if still empty.
    If shell is missing (edge case): creates full conversation.
    Respects ownership on every path including race conditions.
    Errors are logged but never raised (chat must not break on DB failure).
    """
    try:
        title = None
        if clean_messages:
            first_user = next(
                (m["content"] for m in clean_messages if m["role"] == "user"), None
            )
            first_asst = next(
                (m["content"] for m in clean_messages if m["role"] == "assistant"), None
            )
            title = _generate_title(first_user, first_asst)

        existing = get_conversation(session_id)
        if existing:
            if existing["user_id"] != user_id:
                print(f"[persist_conversation] Ownership mismatch: {session_id}", flush=True)
                return
            new_title = title if not existing.get("title") else None
            update_conversation(session_id, title=new_title, messages=clean_messages)
        else:
            try:
                create_conversation(session_id, user_id, title=title, messages=clean_messages)
            except DuplicateConversationError:
                recheck = get_conversation(session_id)
                if not recheck or recheck["user_id"] != user_id:
                    print(f"[persist_conversation] Foreign owner after race: {session_id}", flush=True)
                    return
                update_conversation(session_id, title=title, messages=clean_messages)
    except Exception as e:
        print(f"[persist_conversation] Error: {type(e).__name__}: {e}", flush=True)


def _cleanup_conversation_shell(session_id, user_id):
    """Delete empty conversation shell on failed response. Respects ownership."""
    try:
        existing = get_conversation(session_id)
        if (existing
                and existing["user_id"] == user_id
                and not existing.get("messages")):
            delete_conversation(session_id)
    except Exception:
        pass


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


def _process_media(data, message, trace, session_id=None):
    """Processa midia com OCR + pre-resolve. Retorna (context_message, photo_mode).

    Imagens: OCR -> pre-resolve no banco -> contexto rico para o Claude.
    Video/PDF: OCR -> pre-resolve + discovery -> contexto rico para o Claude.
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
            video_wines = result.get("wines", [])
            desc = result.get("description", "")
            frames = result.get("frames_analyzed", "?")

            resolved = None
            if video_wines:
                with trace.step("video_pre_resolve"):
                    resolved = _resolve_wine_list(video_wines, source_type="video")
                _apply_discovery(resolved, trace, "video_discovery")
                _apply_auto_create(resolved, trace, "video_auto_create", source_channel="video", session_id=session_id)

            if resolved and (resolved["resolved_items"] or resolved["unresolved_items"]):
                header = f"[O usuario enviou um video ({frames} frames analisados). {desc}]"
                rich_context = format_resolved_context(
                    resolved["resolved_wines"], resolved["unresolved"],
                    "video",
                    {"image_type": "video", "wines": video_wines, "total_visible": len(video_wines)},
                    resolved_items=resolved.get("resolved_items"),
                    unresolved_items=resolved.get("unresolved_items"),
                    header_override=header,
                    ocr_label="no video",
                )
                # Suplemento: detalhes OCR dos nao encontrados (producer, vintage, etc)
                ocr_supplement = _format_unresolved_ocr_details(resolved.get("unresolved_items"))
                if ocr_supplement:
                    rich_context += "\n" + ocr_supplement

                rich_context += (
                    "\n[Para vinhos NAO ENCONTRADOS, use search_wine UMA VEZ por item. "
                    "Se nao retornar match compativel, diga que nao temos no acervo.]"
                )
                # Log discovery state
                all_items = resolved.get("resolved_items", []) + resolved.get("unresolved_items", [])
                log_discovery(session_id, all_items, "video")
                return f"{rich_context}\n\n{message}", False
            else:
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
            pdf_wines = result.get("wines", [])

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

            # --- Pre-resolve dos vinhos extraidos ---
            resolved = None
            if pdf_wines:
                with trace.step("pdf_pre_resolve"):
                    resolved = _resolve_wine_list(pdf_wines)
                _apply_discovery(resolved, trace, "pdf_discovery")
                _apply_auto_create(resolved, trace, "pdf_auto_create", source_channel="pdf", session_id=session_id)

            if resolved and (resolved["resolved_items"] or resolved["unresolved_items"]):
                header = (
                    f"[O usuario enviou um PDF ({pages} paginas processadas). "
                    f"{source_note}.{truncation_note}]"
                )
                rich_context = format_resolved_context(
                    resolved["resolved_wines"], resolved["unresolved"],
                    "pdf",
                    {"image_type": "pdf", "wines": pdf_wines, "total_visible": len(pdf_wines)},
                    resolved_items=resolved.get("resolved_items"),
                    unresolved_items=resolved.get("unresolved_items"),
                    header_override=header,
                    ocr_label="no PDF",
                )

                # Suplemento: detalhes OCR dos nao encontrados (producer, vintage, etc)
                ocr_supplement = _format_unresolved_ocr_details(resolved.get("unresolved_items"))
                if ocr_supplement:
                    rich_context += "\n" + ocr_supplement

                pdf_rules = (
                    "\n[REGRAS CRITICAS DESTE PDF (siga sem excecao):\n"
                    "1) FONTE UNICA DA CARTA: a lista acima e a UNICA fonte "
                    "sobre o que existe na carta do cliente. Se um vinho NAO aparece "
                    "nessa lista, ele NAO esta na carta.\n"
                    "2) RANKING: use APENAS vinhos CONFIRMADOS COM NOTA para ranking. "
                    "Se NENHUM item da carta tem nota, diga que nao pode ranquear.\n"
                    "3) HONESTIDADE: se o banco trouxer vinhos similares mas nao "
                    "identicos, mencione como observacao externa, mas SEMPRE "
                    "diga 'isso nao esta na carta do seu PDF'.\n"
                    "4) Para vinhos NAO ENCONTRADOS da lista, use search_wine UMA VEZ "
                    "por item para tentar confirmar. Quando o produtor existir no PDF, "
                    "passe-o no parametro 'produtor'. Se nao retornar match compativel, "
                    "marque como nao confirmado e siga em frente.]"
                )

                # Log discovery state
                all_items = resolved.get("resolved_items", []) + resolved.get("unresolved_items", [])
                log_discovery(session_id, all_items, "pdf")
                return f"{rich_context}{pdf_rules}\n\n{message}", False
            else:
                # Fallback: 0 vinhos ou resolver falhou — comportamento ORIGINAL
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
                    f"4) RANKING DA CARTA — 2 caminhos mutuamente exclusivos:\n"
                    f"   CASO A: se PELO MENOS 1 item da carta tem match + score real "
                    f"na base, RANQUEIE esses itens pelo score. Nao diga que nao pode.\n"
                    f"   CASO B: se NENHUM item tem score real, diga literalmente: "
                    f"'Eu nao consigo ranquear o custo-beneficio desta carta com "
                    f"seguranca porque os itens confirmados da carta nao tem score "
                    f"suficiente na base.' E PARE — sem ranking alternativo (nem visual, "
                    f"nem por preco, nem por regiao). Sem usar 'melhor custo-beneficio', "
                    f"'achado', 'vale a pena' sem score real. Os 2 casos NAO combinam.\n\n"
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


def _format_unresolved_ocr_details(unresolved_items):
    """Formata detalhes OCR dos itens nao resolvidos para contexto do Baco.

    O format_resolved_context so mostra name+price para unresolved.
    Este suplemento adiciona producer/vintage/region/grape quando disponiveis,
    para que o Baco (e o search_wine) tenha informacao completa.
    Retorna string ou None se nao ha detalhes extras a adicionar.
    """
    if not unresolved_items:
        return None

    _DETAIL_FIELDS = [
        ("producer", "Produtor"),
        ("vintage", "Safra"),
        ("region", "Regiao"),
        ("grape", "Uva"),
        ("price", "Preco"),
    ]

    lines = []
    for item in unresolved_items:
        ocr = item.get("ocr", {})
        name = ocr.get("name", "?")
        details = []
        for key, label in _DETAIL_FIELDS:
            val = ocr.get(key)
            if val:
                details.append(f"{label}: {val}")
        if details:
            lines.append(f"  - {name} | {' | '.join(details)}")

    if not lines:
        return None

    return "[Detalhes extraidos dos nao encontrados (use para refinar search_wine):]\n" + "\n".join(lines)


def _resolve_wine_list(wines, source_type="pdf"):
    """Resolve lista de vinhos de qualquer canal via resolver existente.

    source_type: "pdf" ou "video" — ambos usam fast-only, ate 20.
    Manda a lista inteira — o cap interno e feito pelo resolver.
    """
    if not wines:
        return None
    fake_ocr = {
        "image_type": source_type,
        "wines": wines,
        "total_visible": len(wines),
    }
    return resolve_wines_from_ocr(fake_ocr)


def _apply_discovery(resolved, trace, step_name="discovery"):
    """Aplica enrichment nos itens nao resolvidos e mescla resultados.

    Modifica `resolved` in-place: newly_resolved vao para resolved_items/resolved_wines,
    still_unresolved substituem unresolved_items/unresolved.
    Passa IDs ja resolvidos no pre-resolve para evitar duplicatas.
    """
    if not resolved or not resolved.get("unresolved_items"):
        return
    # Coletar IDs ja resolvidos para que discovery nao duplique
    pre_resolved_ids = {
        item["wine"]["id"]
        for item in resolved.get("resolved_items", [])
        if item.get("wine", {}).get("id")
    }
    with trace.step(step_name):
        discovery = discover_unknowns(
            resolved["unresolved_items"],
            trace=trace,
            initial_seen_ids=pre_resolved_ids,
        )
    if discovery["newly_resolved"]:
        resolved["resolved_items"].extend(discovery["newly_resolved"])
        resolved["resolved_wines"].extend([r["wine"] for r in discovery["newly_resolved"]])
        resolved["unresolved_items"] = discovery["still_unresolved"]
        resolved["unresolved"] = [
            item["ocr"].get("name", "?") for item in discovery["still_unresolved"]
        ]


def _apply_auto_create(resolved, trace, step_name="auto_create", source_channel="chat", session_id=None):
    """Auto-cadastra ate 2 itens nao resolvidos e mescla no payload resolved."""
    if not resolved or not resolved.get("unresolved_items"):
        return
    pre_resolved_ids = {
        item["wine"]["id"]
        for item in resolved.get("resolved_items", [])
        if item.get("wine", {}).get("id")
    }
    with trace.step(step_name):
        created = auto_create_unknowns(
            resolved["unresolved_items"],
            source_channel=source_channel,
            session_id=session_id,
            initial_seen_ids=pre_resolved_ids,
        )
    if created["newly_resolved"]:
        resolved["resolved_items"].extend(created["newly_resolved"])
        resolved["resolved_wines"].extend([r["wine"] for r in created["newly_resolved"]])
    # Sempre substituir a lista: o auto-create tambem pode descartar NOT_WINE
    # bloqueado pelo pre-ingest sem criar nenhum vinho novo.
    resolved["unresolved_items"] = created["still_unresolved"]
    resolved["unresolved"] = [
        item["ocr"].get("name", "?") for item in created["still_unresolved"]
    ]


def _try_text_wine_extraction(message, trace, session_id=None):
    """Detecta e extrai vinhos de texto longo. Retorna (new_message, photo_mode) ou None.

    Chamado em AMBOS chat() e chat_stream() quando has_media=False.
    Skip para mensagens curtas e texto nao relacionado a vinho.
    """
    if len(message) <= 150:
        return None
    if not _text_looks_wine_related(message, min_matches=3):
        return None

    with trace.step("text_wine_extract"):
        text_result = extract_wines_from_text(message)

    if text_result.get("status") != "success" or not text_result.get("wines"):
        return None

    text_wines = text_result["wines"]
    with trace.step("text_pre_resolve"):
        resolved = _resolve_wine_list(text_wines, source_type="text")
    _apply_discovery(resolved, trace, "text_discovery")
    _apply_auto_create(resolved, trace, "text_auto_create", source_channel="text", session_id=session_id)

    if not resolved or not (resolved["resolved_items"] or resolved["unresolved_items"]):
        return None

    header = f"[O usuario colou uma lista/carta de vinhos. {len(text_wines)} vinhos extraidos.]"
    rich_context = format_resolved_context(
        resolved["resolved_wines"], resolved["unresolved"],
        "text",
        {"image_type": "text", "wines": text_wines, "total_visible": len(text_wines)},
        resolved_items=resolved.get("resolved_items"),
        unresolved_items=resolved.get("unresolved_items"),
        header_override=header,
        ocr_label="no texto",
    )

    # Suplemento: detalhes OCR dos nao encontrados
    ocr_supplement = _format_unresolved_ocr_details(resolved.get("unresolved_items"))
    if ocr_supplement:
        rich_context += "\n" + ocr_supplement

    rich_context += (
        "\n[Para vinhos NAO ENCONTRADOS, use search_wine UMA VEZ por item. "
        "Se nao retornar match compativel, diga que nao temos no acervo.]"
    )

    # Log discovery state
    all_items = resolved.get("resolved_items", []) + resolved.get("unresolved_items", [])
    log_discovery(session_id, all_items, "text")

    return f"{rich_context}\n\n{message}", False


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
    _apply_discovery(resolved, trace, "image_discovery")
    _apply_auto_create(resolved, trace, "image_auto_create", source_channel="image")

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

    auto_create_payload = {
        "resolved_wines": [it["wine"] for it in all_resolved_items],
        "unresolved": [it["ocr"].get("name", "?") for it in all_unresolved_items],
        "resolved_items": all_resolved_items,
        "unresolved_items": all_unresolved_items,
    }
    _apply_discovery(auto_create_payload, trace, "batch_image_discovery")
    _apply_auto_create(auto_create_payload, trace, "batch_image_auto_create", source_channel="image")
    all_resolved_items = auto_create_payload.get("resolved_items", [])
    all_unresolved_items = auto_create_payload.get("unresolved_items", [])

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
            nota_tipo_str = f"({d['display_note_type']})" if d.get('display_note_type') else ""
            score_str = f"{d['display_score']}" if d['display_score_available'] else "sem score"
            bucket_str = f" | Avaliacoes: {d['public_ratings_bucket']}" if d.get('public_ratings_bucket') else ""

            parts.append(f"  {counter}. {' | '.join(ocr_parts)}")
            parts.append(
                f"     Banco: {w.get('nome', '?')} | {w.get('produtor', '?')} "
                f"| Nota: {nota_str} {nota_tipo_str}{bucket_str} | Score: {score_str} "
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
@with_request_locale
@require_credits
def chat():
    """POST /api/chat — Envia mensagem e recebe resposta completa do Baco."""
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Campo 'message' e obrigatorio"}), 400

    message = data["message"]
    session_id = data.get("session_id", str(uuid.uuid4()))
    current_user = get_current_user(request)

    trace = RequestTrace(request_id=session_id)
    has_media = _has_media(data)
    photo_mode = False

    if has_media:
        try:
            message, photo_mode = _process_media(data, message, trace, session_id=session_id)
        except Exception as e:
            print(f"[chat] _process_media failed: {type(e).__name__}: {e}", flush=True)
            trace.log()
            message = (
                f"[O usuario enviou uma foto mas ocorreu um erro ao processar: {e}. "
                f"Peca desculpas e ofereca alternativa (descrever o vinho).]\n\n{message}"
            )

    # --- Deteccao de texto com vinhos (quando NAO tem midia) ---
    if not has_media:
        text_result = _try_text_wine_extraction(message, trace, session_id=session_id)
        if text_result:
            message, photo_mode = text_result

    session = _get_session(session_id)
    shell_created = False
    if current_user:
        _init_clean_messages(session, session_id, current_user["id"])
        shell_created = _ensure_conversation_shell(session_id, current_user["id"])
    history = session["messages"][-MAX_HISTORY:]

    try:
        with trace.step("baco_response"):
            response_text, model = get_baco_response(
                message, session_id, history,
                photo_mode=photo_mode, trace=trace,
            )
    except Exception as e:
        trace.log()
        if shell_created:
            _cleanup_conversation_shell(session_id, current_user["id"])
        return jsonify({"error": f"Erro ao chamar Claude API: {str(e)}"}), 500

    trace.log()

    session["messages"].append({"role": "user", "content": message})
    session["messages"].append({"role": "assistant", "content": response_text})

    if current_user:
        clean_msg = _sanitize_user_message(data["message"], data)
        session["clean_messages"].append({"role": "user", "content": clean_msg})
        session["clean_messages"].append({"role": "assistant", "content": response_text})
        _persist_conversation(session_id, current_user["id"], session["clean_messages"])

    return jsonify({
        "response": response_text,
        "session_id": session_id,
        "model": model,
    })


@chat_bp.route('/chat/stream', methods=['POST'])
@with_request_locale
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
    current_user = get_current_user(request)

    session = _get_session(session_id)
    shell_created = False
    if current_user:
        _init_clean_messages(session, session_id, current_user["id"])
        shell_created = _ensure_conversation_shell(session_id, current_user["id"])
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
                msg, photo_mode = _process_media(data, message, trace, session_id=session_id)
            except Exception as e:
                print(f"[chat_stream] _process_media failed: {type(e).__name__}: {e}", flush=True)
                msg = (
                    f"[O usuario enviou uma foto mas ocorreu um erro ao processar: {e}. "
                    f"Peca desculpas e ofereca alternativa (descrever o vinho).]\n\n{message}"
                )

            yield f"data: {json.dumps({'type': 'status', 'content': 'Buscando informacoes...'})}\n\n"

        # --- Deteccao de texto com vinhos (quando NAO tem midia) ---
        if not has_media:
            text_result = _try_text_wine_extraction(msg, trace, session_id=session_id)
            if text_result:
                msg, photo_mode = text_result

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
            if shell_created:
                _cleanup_conversation_shell(session_id, current_user["id"])
            return

        response_text = "".join(full_response)
        session["messages"].append({"role": "user", "content": msg})
        session["messages"].append({"role": "assistant", "content": response_text})

        if current_user:
            clean_msg = _sanitize_user_message(message, data)
            session["clean_messages"].append({"role": "user", "content": clean_msg})
            session["clean_messages"].append({"role": "assistant", "content": response_text})
            _persist_conversation(session_id, current_user["id"], session["clean_messages"])

        trace.log()
        yield f"data: {json.dumps({'type': 'end', 'model': MODEL})}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
