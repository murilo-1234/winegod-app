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


_MAX_MULTI_ITEMS = 8      # screenshot (itens mais limpos)
_MAX_SHELF_ITEMS = 3      # shelf (resolver poucos e bons)
_MIN_MATCH_SCORE = 0.4
_MAX_FALLBACK_PAIRS = 1

# Tokens genericos que nao distinguem um vinho especifico.
# NAO inclui classificacoes (reserva, crianza, classico, etc.) porque essas
# discriminam vinhos dentro do mesmo produtor.
_GENERIC_WINE_TOKENS = frozenset({
    # Tipos
    'tinto', 'blanco', 'branco', 'rosado', 'rose', 'red', 'white',
    'sparkling', 'espumante', 'dulce', 'seco', 'dry', 'sweet',
    # Marketing (nao discriminam entre vinhos)
    'premium', 'seleccion', 'selection', 'limited', 'edition',
    'single', 'vineyard',
    # Palavras genericas de vinho
    'vino', 'wine', 'vin', 'vinho', 'cuvee', 'blend', 'estate',
    'bodega', 'bodegas', 'chateau', 'domaine', 'tenuta', 'quinta',
    # Preposicoes comuns (len >= 3)
    'the', 'and', 'von', 'van', 'zum', 'sur', 'les', 'des', 'del',
    'los', 'las',
})


# Uvas: nao identificam linha/familia dentro do mesmo produtor
_GRAPE_TOKENS = frozenset({
    'cabernet', 'sauvignon', 'merlot', 'malbec', 'syrah', 'shiraz',
    'chardonnay', 'pinot', 'noir', 'grigio', 'gris',
    'tempranillo', 'garnacha', 'grenache',
    'carmenere', 'bonarda', 'tannat',
    'torrontes', 'viognier', 'riesling',
    'sangiovese', 'nebbiolo', 'barbera', 'primitivo', 'zinfandel',
    'mourvedre', 'verdejo', 'albarino', 'moscato',
    'blanc', 'rouge',
})

# Classificacoes: nao identificam linha especifica (mas discriminam dentro da linha)
_CLASSIFICATION_TOKENS = frozenset({
    'reserva', 'reserve', 'riserva',
    'gran', 'grand', 'grande',
    'crianza', 'roble', 'joven',
    'classico', 'classic', 'superior', 'especial',
})


def _extract_distinctive(name_norm):
    """Tokens distintivos: sem genericos, sem anos, len >= 3."""
    return [t for t in name_norm.split()
            if len(t) >= 3
            and t not in _GENERIC_WINE_TOKENS
            and not (len(t) == 4 and t.isdigit())]


def _extract_line_tokens(ocr_norm, prod_name):
    """Tokens de LINHA/FAMILIA: o que sobra apos remover produtor, uvas, classificacoes.

    Esses tokens identificam QUAL vinho dentro do mesmo produtor.
    Ex: 'Aura' em 'MontGras Aura Reserva Carmenere'.
    """
    prod_tokens = set(prod_name.split()) if prod_name else set()
    return [t for t in ocr_norm.split()
            if len(t) >= 3
            and t not in _GENERIC_WINE_TOKENS
            and t not in _GRAPE_TOKENS
            and t not in _CLASSIFICATION_TOKENS
            and t not in prod_tokens
            and not (len(t) == 4 and t.isdigit())]


def _score_match(ocr_name, candidate):
    """Score de qualidade do match OCR vs candidato do banco.

    Gate 0 (OBRIGATORIO): tokens de linha/familia do OCR devem TODOS
    estar presentes no nome do candidato (match por palavra inteira).
    Gate 1: token distintivo mais longo deve estar em nome+produtor.
    Primary: fracao de tokens distintivos no NOME (nao produtor).
    Matches apenas no produtor recebem 30% de peso.
    Tiebreaker: overlap de todos os tokens OCR com o nome do vinho.
    """
    ocr_norm = normalizar(ocr_name)
    cand_name = normalizar(candidate.get('nome', ''))
    prod_name = normalizar(candidate.get('produtor', ''))
    cand_full = cand_name + ' ' + prod_name

    # GATE 0 — LINHA/FAMILIA (obrigatorio, antes de tudo):
    # Se o OCR leu tokens de linha/familia, o candidato DEVE conter
    # TODOS eles no nome do vinho (match por PALAVRA, nao substring).
    # Produtor igual + uva igual NAO basta.
    # Ex: "MontGras Aura" nao casa com "MontGras Day One".
    # Ex: "Casa Silva Family Wines" nao casa com "Los Lingues Single Block".
    line_tokens = _extract_line_tokens(ocr_norm, prod_name)
    if line_tokens:
        cand_words = set(cand_name.split())
        if not all(t in cand_words for t in line_tokens):
            return 0.0

    distinctive = _extract_distinctive(ocr_norm)

    if not distinctive:
        return 1.0  # Tudo generico — aceitar qualquer resultado

    # Ordenar por tamanho desc (mais longo = mais distintivo)
    distinctive.sort(key=len, reverse=True)

    # Gate 1: top token deve estar em nome OU produtor
    if distinctive[0] not in cand_full:
        return 0.0

    # Contar matches no nome vs no produtor separadamente
    name_matched = sum(1 for t in distinctive if t in cand_name)
    full_matched = sum(1 for t in distinctive if t in cand_full)
    producer_only = full_matched - name_matched

    # Peso: nome = 100%, produtor-only = 30%
    weighted = name_matched + producer_only * 0.3
    primary = weighted / len(distinctive)

    # Tiebreaker: todos os tokens OCR significativos vs nome do vinho
    ocr_tokens = [t for t in ocr_norm.split() if len(t) >= 3]
    name_hits = sum(1 for t in ocr_tokens if t in cand_name) if ocr_tokens else 0
    tiebreak = (name_hits / len(ocr_tokens)) * 0.1 if ocr_tokens else 0

    return primary + tiebreak


def _pick_best(ocr_name, candidates, seen_ids):
    """Melhor candidato acima de MIN_MATCH_SCORE, ignorando seen_ids."""
    best = None
    best_score = _MIN_MATCH_SCORE

    for c in candidates:
        wid = c.get('id')
        if not wid or wid in seen_ids:
            continue
        s = _score_match(ocr_name, c)
        if s > best_score:
            best = c
            best_score = s

    return best


def _fast_resolve(name, producer, seen_ids):
    """Fase 1: single attempt, exact/prefix/producer, sem tokens, 1s timeout."""
    kwargs = {"produtor": producer} if producer else {}
    try:
        result = search_wine(name, limit=5, allow_fuzzy=False, skip_tokens=True, timeout_ms=1000, **kwargs)
        best = _pick_best(name, result.get("wines", []), seen_ids)
        if best:
            print(f"[resolver] multi_item phase=1 matched={best.get('id')}", flush=True)
            return best
    except Exception:
        pass
    return None


def _fallback_resolve(name, seen_ids):
    """Fase 2: 1 par de tokens distintivos, timeout 1.5s.

    Roda so quando Fase 1 falhou. Query curta (2 tokens) para token search rapido.
    """
    name_norm = normalizar(name)
    distinctive = _extract_distinctive(name_norm)
    if not distinctive:
        return None

    distinctive.sort(key=len, reverse=True)
    top = distinctive[0]

    sig_tokens = [t for t in name_norm.split()
                  if len(t) >= 3 and not (len(t) == 4 and t.isdigit())]

    tried = set()
    for other in sig_tokens:
        if other == top:
            continue
        pair = tuple(sorted([top, other]))
        if pair in tried:
            continue
        tried.add(pair)

        query = f"{top} {other}"
        try:
            result = search_wine(query, limit=5, allow_fuzzy=False, timeout_ms=1500)
            best = _pick_best(name, result.get("wines", []), seen_ids)
            if best:
                print(f"[resolver] multi_item phase=2 pair={pair} matched={best.get('id')}", flush=True)
                return best
        except Exception:
            continue

        if len(tried) >= _MAX_FALLBACK_PAIRS:
            break

    return None


def _resolve_multi(ocr_result):
    """Resolve multiplos vinhos de screenshot/shelf.

    Shelf: resolve amostra pequena (3 itens fortes), fast-only, sem fallback.
    Screenshot: mais permissivo (8 itens), com fallback.
    Itens alem do cap vao direto para unresolved (vistos mas nao verificados).
    """
    wines_list = ocr_result.get("wines", [])
    if not wines_list:
        return [], []

    image_type = ocr_result.get("image_type", "screenshot")
    is_shelf = image_type == "shelf"

    # Cap e estrategia por tipo
    max_items = _MAX_SHELF_ITEMS if is_shelf else _MAX_MULTI_ITEMS
    use_fallback = not is_shelf  # shelf: fast-only, screenshot: fast + fallback

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
    deduped.sort(key=lambda w: (
        0 if w.get("price") else 1,
        -len((w.get("name") or "").split()),
    ))

    # 4. Cap: resolver apenas os mais fortes, resto vai para unresolved
    selected = deduped[:max_items]
    skipped = deduped[max_items:]

    print(
        f"[resolver] multi: type={image_type} ocr={len(wines_list)} valid={len(valid)} "
        f"deduped={len(deduped)} selected={len(selected)} skipped={len(skipped)}",
        flush=True,
    )

    # 5. Resolver cada item selecionado
    resolved_items = []
    unresolved_items = []
    seen_ids = set()

    for w in selected:
        name = (w.get("name") or "").strip()
        producer = (w.get("producer") or "").strip() or None

        # Fase 1: Fast (exact/prefix/producer, sem token LIKE)
        matched = _fast_resolve(name, producer, seen_ids)

        # Fase 2: Fallback (apenas screenshot — shelf pula)
        if not matched and use_fallback:
            matched = _fallback_resolve(name, seen_ids)

        if matched:
            seen_ids.add(matched['id'])
            resolved_items.append({"ocr": w, "wine": matched})
        else:
            unresolved_items.append({"ocr": w})

    # 6. Itens alem do cap: unresolved direto (vistos, nao verificados)
    for w in skipped:
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

            # Instrucao final com niveis de certeza
            if resolved_items and _unresolved:
                # Caso misto: alguns confirmados, alguns apenas visuais
                parts.append(
                    "[REGRAS DE CERTEZA: "
                    "Itens marcados 'Banco:' estao CONFIRMADOS — use nota, score e preco da base com confianca. "
                    "Itens em 'Nao encontrado(s)' sao APENAS LEITURA VISUAL — cite nome e preco visivel, mas NAO atribua nota, score, ranking, custo-beneficio ou qualidade. "
                    "Para ranking ou recomendacao, compare APENAS os confirmados. "
                    "Dos nao confirmados, diga que ainda nao tem no acervo.]"
                )
            elif resolved_items:
                # Todos confirmados
                parts.append(
                    "[Todos os vinhos foram confirmados na base. "
                    "Responda com os dados ja fornecidos (nota, score, preco). "
                    "NAO chame get_wine_details nem get_prices — os dados essenciais ja estao aqui.]"
                )
            else:
                # Nenhum confirmado
                parts.append(
                    "[Nenhum destes vinhos foi confirmado na base ainda. "
                    "Apresente com confianca os nomes e precos claramente lidos na imagem — sao dados visuais seguros. "
                    "NAO invente nota, score, perfil sensorial, qualidade ou reputacao. "
                    "NAO faca ranking ou custo-beneficio sem dados da base. "
                    "Diga que ainda nao tem esses vinhos no acervo e ofereca buscar mais informacoes.]"
                )

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
