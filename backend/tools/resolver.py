"""Pre-resolve: resolve vinhos do OCR no backend antes de chamar o Claude."""

import time
from tools.search import search_wine
from tools.normalize import normalizar
from services.display import resolve_display

# Paises que o OCR pode devolver no campo "region" por engano
_KNOWN_COUNTRIES = {
    "argentina", "france", "italy", "spain", "chile", "portugal",
    "australia", "germany", "south africa", "new zealand", "united states",
    "usa", "brasil", "brazil", "uruguay", "greece", "austria", "hungary",
    "romania", "georgia", "lebanon", "israel", "canada", "mexico",
    "peru", "bolivia", "china", "japan", "india", "turkey", "croatia",
    "slovenia", "switzerland", "england", "uk",
}


def resolve_wines_from_ocr(ocr_result):
    """Dado resultado do OCR, tenta resolver vinhos no banco.

    Retorna dict com:
      - resolved_wines: lista de vinhos encontrados (compat retroativa)
      - unresolved: lista de nomes nao encontrados (compat retroativa)
      - resolved_items: [{"ocr": <item_ocr>, "wine": <wine_dict>}, ...]
      - unresolved_items: [{"ocr": <item_ocr>}, ...]
      - timing_ms: tempo de resolucao em ms
    """
    t0 = time.time()
    image_type = ocr_result.get("image_type", "")

    if image_type == "label":
        resolved, unresolved = _resolve_label(ocr_result)
        # Derivar resolved_items/unresolved_items para label (forward compat)
        ocr_data = ocr_result.get("ocr_result", {})
        resolved_items = [{"ocr": ocr_data, "wine": w} for w in resolved]
        unresolved_items = [{"ocr": {"name": n}} for n in unresolved]
    elif image_type in ("screenshot", "shelf"):
        resolved_items, unresolved_items = _resolve_multi(ocr_result)
        # Derivar resolved_wines/unresolved para callers existentes
        resolved = [item["wine"] for item in resolved_items]
        unresolved = [item["ocr"].get("name", "?") for item in unresolved_items]
    else:
        resolved, unresolved = [], []
        resolved_items, unresolved_items = [], []

    elapsed_ms = round((time.time() - t0) * 1000)

    return {
        "resolved_wines": resolved,
        "unresolved": unresolved,
        "resolved_items": resolved_items,
        "unresolved_items": unresolved_items,
        "timing_ms": elapsed_ms,
    }


def _resolve_label(ocr_result):
    """Resolve um unico vinho de rotulo.

    Estrategia fast-only: tentativas progressivas SEM fuzzy.
    Safra nunca e filtro duro — apenas hint para desempate posterior.
    """
    ocr = ocr_result.get("ocr_result", {})
    name = ocr.get("name", "")
    producer = ocr.get("producer")
    vintage = ocr.get("vintage")
    region = ocr.get("region")

    if not name:
        return [], []

    # Classificar region como pais ou regiao
    pais_kw = None
    regiao_kw = None
    if region:
        if region.strip().lower() in _KNOWN_COUNTRIES:
            pais_kw = region
        else:
            regiao_kw = region

    # Todas as tentativas usam allow_fuzzy=False — nunca pg_trgm no pre-resolve
    attempts = []

    # Tentativa 1: name + producer + pais (sem safra, sem regiao se era pais)
    kw1 = {}
    if producer:
        kw1["produtor"] = producer
    if pais_kw:
        kw1["pais"] = pais_kw
    if kw1:
        attempts.append(("name+producer+pais", name, kw1))

    # Tentativa 2: name + pais (sem producer)
    if pais_kw:
        attempts.append(("name+pais", name, {"pais": pais_kw}))

    # Tentativa 3: name sozinho (sem filtros)
    attempts.append(("name_only", name, {}))

    # Tentativa 4: producer sozinho (sem filtros)
    if producer:
        attempts.append(("producer_only", producer, {}))

    for attempt_name, query, kwargs in attempts:
        print(f"[resolver] attempt={attempt_name} START query={query!r} kwargs={kwargs}", flush=True)
        try:
            result = search_wine(query, limit=5, allow_fuzzy=False, **kwargs)
            wines = result.get("wines", [])
            layer = result.get("search_layer", "?")
            print(f"[resolver] attempt={attempt_name} DONE layer={layer} found={len(wines)}", flush=True)

            if wines:
                return wines, []
        except Exception as e:
            print(f"[resolver] attempt={attempt_name} FAIL {type(e).__name__}: {e}", flush=True)

    print(f"[resolver] label unresolved: {name!r}", flush=True)
    return [], [name]


_MAX_MULTI_ITEMS = 10


def _resolve_multi(ocr_result):
    """Resolve multiplos vinhos de screenshot/shelf.

    Retorna (resolved_items, unresolved_items) preservando vinculo OCR -> banco.
    resolved_items: [{"ocr": <item_ocr_original>, "wine": <wine_dict>}, ...]
    unresolved_items: [{"ocr": <item_ocr_original>}, ...]
    """
    wines_list = ocr_result.get("wines", [])
    if not wines_list:
        return [], []

    # 1. Filtrar itens sem nome
    valid = [w for w in wines_list if (w.get("name") or "").strip()]

    # 2. Deduplicar itens OCR por nome normalizado
    seen_names = set()
    deduped = []
    for w in valid:
        key = (w.get("name") or "").strip().lower()
        if key not in seen_names:
            seen_names.add(key)
            deduped.append(w)

    # 3. Priorizar: com preco > nome mais completo > ordem original
    # sort estavel — itens com mesma prioridade mantem ordem do OCR
    deduped.sort(key=lambda w: (
        0 if w.get("price") else 1,
        -len((w.get("name") or "").split()),
    ))

    # 4. Cap apos priorizacao
    selected = deduped[:_MAX_MULTI_ITEMS]

    print(
        f"[resolver] multi: ocr={len(wines_list)} valid={len(valid)} "
        f"deduped={len(deduped)} selected={len(selected)}",
        flush=True,
    )

    # 5. Resolver cada item contra o banco
    resolved_items = []
    unresolved_items = []
    seen_ids = set()

    for w in selected:
        name = (w.get("name") or "").strip()
        producer = (w.get("producer") or "").strip() or None

        # Tentativas progressivas (producer so se existir no OCR)
        attempts = []
        if producer:
            attempts.append(("name+producer", name, {"produtor": producer}))
        attempts.append(("name_only", name, {}))
        if producer:
            attempts.append(("producer_only", producer, {}))

        matched = None
        for attempt_name, query, kwargs in attempts:
            try:
                result = search_wine(query, limit=3, allow_fuzzy=False, **kwargs)
                for m in result.get("wines", []):
                    wid = m.get("id")
                    if wid and wid not in seen_ids:
                        seen_ids.add(wid)
                        matched = m
                        break
                if matched:
                    break
            except Exception:
                continue

        if matched:
            resolved_items.append({"ocr": w, "wine": matched})
        else:
            unresolved_items.append({"ocr": w})

    print(
        f"[resolver] multi: resolved={len(resolved_items)} "
        f"unresolved={len(unresolved_items)}",
        flush=True,
    )

    return resolved_items, unresolved_items


def format_resolved_context(resolved_wines, unresolved, image_type, ocr_result,
                            resolved_items=None, unresolved_items=None):
    """Formata o resultado do pre-resolve em contexto para o Claude.

    resolved_items/unresolved_items: estruturas vinculadas OCR->banco (shelf/screenshot).
    Quando fornecidos, o contexto inclui precos e dados do OCR por item.
    """
    parts = []

    if image_type == "label":
        # --- Label: sem mudancas ---
        ocr = ocr_result.get("ocr_result", {})
        search_text = ocr_result.get("search_text", "")
        parts.append(f"[O usuario enviou foto de um rotulo. OCR identificou: {search_text}.]")

        if resolved_wines:
            w = resolved_wines[0]
            d = resolve_display(w)
            nota_str = f"{d['display_note']}" if d['display_note'] else "sem nota"
            nota_tipo_str = f"({d['display_note_type']})" if d['display_note_type'] else ""
            score_str = f"{d['display_score']}" if d['display_score_available'] else "sem score"
            parts.append(
                f"[Vinho encontrado no banco: {w.get('nome', '?')} "
                f"| Produtor: {w.get('produtor', '?')} "
                f"| Pais: {w.get('pais_nome', '?')} "
                f"| Regiao: {w.get('regiao', '?')} "
                f"| Nota: {nota_str} {nota_tipo_str} "
                f"| Score: {score_str} "
                f"| Preco: {w.get('preco_min', '?')}-{w.get('preco_max', '?')} {w.get('moeda', '')} "
                f"| ID: {w.get('id', '?')}]"
            )
            wine_name = w.get('nome', '?')
            if len(resolved_wines) == 1:
                parts.append(f"[IMPORTANTE: comece sua resposta dizendo explicitamente o nome do vinho identificado na foto: {wine_name}.]")
            else:
                others = [f"{r.get('nome', '?')} (ID:{r.get('id', '?')})" for r in resolved_wines[1:4]]
                parts.append(f"[Outros candidatos: {', '.join(others)}]")
                parts.append(f"[IMPORTANTE: comece dizendo que o candidato mais provavel e {wine_name}, sem afirmar certeza absoluta.]")
            parts.append("[Responda sobre este vinho. Use get_wine_details ou get_prices se precisar de mais dados.]")
        else:
            parts.append("[Vinho NAO encontrado no banco. Responda com o que sabe e avise que nao temos dados completos.]")

    elif image_type in ("screenshot", "shelf"):
        type_label = "prateleira" if image_type == "shelf" else "screenshot"

        if resolved_items is not None:
            # --- Novo formato: vinculo OCR -> banco ---
            _unresolved = unresolved_items or []
            total_read = len(resolved_items) + len(_unresolved)

            parts.append(f"[O usuario enviou foto de {type_label}.]")
            if total_read > 0:
                parts.append(f"[OCR identificou {total_read} vinho(s) por nome. Pode haver outros na imagem nao legiveis.]")

            # Vinhos resolvidos
            if resolved_items:
                parts.append(f"[{len(resolved_items)} vinho(s) encontrado(s) no banco:]")
                for i, item in enumerate(resolved_items, 1):
                    ocr_i = item["ocr"]
                    w = item["wine"]
                    d = resolve_display(w)

                    ocr_parts = [f"Lido na imagem: {ocr_i.get('name', '?')}"]
                    if ocr_i.get("price"):
                        ocr_parts.append(f"Preco visivel na imagem: {ocr_i['price']}")
                    if image_type == "screenshot" and ocr_i.get("rating"):
                        ocr_parts.append(f"Nota visivel no screenshot: {ocr_i['rating']}")

                    nota_str = f"{d['display_note']}" if d['display_note'] else "sem nota"
                    nota_tipo_str = f"({d['display_note_type']})" if d['display_note_type'] else ""
                    score_str = f"{d['display_score']}" if d['display_score_available'] else "sem score"

                    parts.append(f"  {i}. {' | '.join(ocr_parts)}")
                    parts.append(
                        f"     Banco: {w.get('nome', '?')} | {w.get('produtor', '?')} "
                        f"| Nota: {nota_str} {nota_tipo_str} "
                        f"| Score: {score_str} "
                        f"| Preco base: {w.get('preco_min', '?')}-{w.get('preco_max', '?')} {w.get('moeda', '')} "
                        f"| ID: {w.get('id', '?')}"
                    )

            # Vinhos nao resolvidos
            if _unresolved:
                parts.append("[Nao encontrado(s) no banco:]")
                start = len(resolved_items) + 1
                for i, item in enumerate(_unresolved, start):
                    ocr_i = item["ocr"]
                    ocr_parts = [ocr_i.get("name", "?")]
                    if ocr_i.get("price"):
                        ocr_parts.append(f"Preco visivel: {ocr_i['price']}")
                    if image_type == "screenshot" and ocr_i.get("rating"):
                        ocr_parts.append(f"Nota visivel: {ocr_i['rating']}")
                    parts.append(f"  {i}. {' | '.join(ocr_parts)}")

            # Instrucao final condicional
            if resolved_items:
                parts.append("[Responda sobre os vinhos listados acima. Use get_wine_details ou get_prices para dados extras.]")
            else:
                parts.append("[Nenhum vinho encontrado no banco. Responda com base apenas nos nomes e precos identificados na imagem. Nao invente dados.]")

        else:
            # --- Fallback: formato antigo (callers sem resolved_items) ---
            parts.append(f"[O usuario enviou foto de {type_label}.]")
            if resolved_wines:
                parts.append(f"[{len(resolved_wines)} vinho(s) encontrado(s) no banco:]")
                for i, w in enumerate(resolved_wines, 1):
                    d = resolve_display(w)
                    nota_str = f"{d['display_note']}" if d['display_note'] else "sem nota"
                    nota_tipo_str = f"({d['display_note_type']})" if d['display_note_type'] else ""
                    score_str = f"{d['display_score']}" if d['display_score_available'] else "sem score"
                    parts.append(
                        f"  {i}. {w.get('nome', '?')} | {w.get('produtor', '?')} "
                        f"| Nota: {nota_str} {nota_tipo_str} "
                        f"| Score: {score_str} "
                        f"| Preco: {w.get('preco_min', '?')}-{w.get('preco_max', '?')} {w.get('moeda', '')} "
                        f"| ID: {w.get('id', '?')}"
                    )
            if unresolved:
                parts.append(f"[Nao encontrados no banco: {', '.join(unresolved)}]")
            if resolved_wines:
                parts.append("[Responda sobre os vinhos encontrados. Use get_wine_details ou get_prices para dados extras.]")
            else:
                parts.append("[Nenhum vinho encontrado no banco. Responda com base nos nomes identificados na imagem. Nao invente dados.]")

    return "\n".join(parts)
