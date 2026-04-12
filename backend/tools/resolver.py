"""Pre-resolve: resolve vinhos do OCR no backend antes de chamar o Claude."""

import time
from tools.search import search_wine, search_wine_tokens
from tools.normalize import normalizar
from services.display import resolve_display

# Paises que o OCR pode devolver no campo "region" por engano
def _derive_item_status(wine):
    """Derive explicit item status from a resolved wine dict.

    Returns one of: 'confirmed_with_note', 'confirmed_no_note'.
    For unresolved items, callers set 'visual_only' directly.
    """
    d = resolve_display(wine)
    if d["display_note"] is not None:
        return "confirmed_with_note"
    return "confirmed_no_note"


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
        resolved_items = [
            {"ocr": ocr_data, "wine": w, "status": _derive_item_status(w)}
            for w in resolved
        ]
        unresolved_items = [{"ocr": {"name": n}, "status": "visual_only"} for n in unresolved]
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


_MAX_MULTI_ITEMS = 8       # screenshot (itens mais limpos)
_MAX_SHELF_TIER_A = 3      # shelf: confirmacao forte (fast-only)
_MAX_SHELF_TIER_B = 2      # shelf: confirmacao moderada (fast + fallback)
_MIN_MATCH_SCORE = 0.4
_MAX_FALLBACK_PAIRS = 2

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

# Variedades/estilos canonicos — frases completas, ordenadas por tamanho
# desc para greedy matching. Compostos primeiro ("cabernet sauvignon"
# antes de "cabernet") para nao quebrar frases em partes.
_CANONICAL_VARIETIES = sorted([
    # Uvas compostas
    'cabernet sauvignon', 'cabernet franc', 'sauvignon blanc',
    'pinot noir', 'pinot grigio', 'pinot gris', 'pinot blanc',
    'pinot meunier', 'chenin blanc', 'petit verdot', 'petit sirah',
    'blanc de blancs', 'blanc de noirs',
    # Estilos compostos
    'extra brut', 'brut nature', 'brut rose', 'demi sec',
    # Uvas simples
    'merlot', 'malbec', 'syrah', 'shiraz', 'chardonnay',
    'tempranillo', 'garnacha', 'grenache', 'carmenere',
    'bonarda', 'tannat', 'torrontes', 'viognier', 'riesling',
    'sangiovese', 'nebbiolo', 'barbera', 'primitivo', 'zinfandel',
    'mourvedre', 'verdejo', 'albarino', 'moscato',
    'montepulciano', 'chianti', 'gewurztraminer',
    # Estilos simples
    'rose', 'rosado', 'tinto', 'blanco', 'branco', 'red', 'white',
    'brut', 'nature', 'seco', 'dulce', 'sweet', 'dry',
    'espumante', 'sparkling',
], key=len, reverse=True)

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


def _extract_canonical_varieties(name_norm):
    """Extrai variedades/estilos canonicos de um nome normalizado.

    Greedy: frases mais longas primeiro. Tokens consumidos nao sao
    reutilizados, evitando que 'cabernet sauvignon' vire 'cabernet' + 'sauvignon'.
    """
    found = []
    remaining = name_norm
    for variety in _CANONICAL_VARIETIES:
        if variety in remaining:
            found.append(variety)
            remaining = remaining.replace(variety, ' ', 1)
    return found


def _collapse_initials(name_norm):
    """Collapse single-letter words into next word.

    'd eugenio' → 'deugenio', 'j p chenet' → 'jp chenet'.
    Ajuda match quando DB tem 'D.Eugenio' (→ 'deugenio') e OCR le 'D. Eugenio' (→ 'd eugenio').
    """
    tokens = name_norm.split()
    result = []
    i = 0
    while i < len(tokens):
        if len(tokens[i]) == 1 and i + 1 < len(tokens):
            result.append(tokens[i] + tokens[i + 1])
            i += 2
        else:
            result.append(tokens[i])
            i += 1
    return ' '.join(result)


def _build_scoring_name(w):
    """Build a clean name from OCR structured fields for scoring.

    Remove region/origin info (e.g. 'La Mancha') que viraria false line token.
    Usa campos estruturados quando disponiveis, senao o name raw.
    """
    producer = (w.get("producer") or "").strip()
    line = (w.get("line") or "").strip()
    variety = (w.get("variety") or "").strip()
    classification = (w.get("classification") or "").strip()
    name = (w.get("name") or "").strip()

    if line or variety:
        parts = []
        if producer:
            parts.append(producer)
        if line:
            parts.append(line)
        if classification and classification.lower() != (line or "").lower():
            parts.append(classification)
        if variety:
            parts.append(variety)
        built = " ".join(parts)
        if built:
            return built

    return name


def _score_match(ocr_name, candidate):
    """Score de qualidade do match OCR vs candidato do banco.

    Gate 0 (OBRIGATORIO): tokens de linha/familia do OCR devem TODOS
    estar presentes no nome do candidato (match por palavra inteira).
    Gate 1: token distintivo mais longo deve estar em nome+produtor.
    Primary: fracao de tokens distintivos no NOME (nao produtor).
    Matches apenas no produtor recebem 30% de peso.
    Tiebreaker: overlap de todos os tokens OCR com o nome do vinho.
    """
    ocr_norm = _collapse_initials(normalizar(ocr_name))
    cand_name = _collapse_initials(normalizar(candidate.get('nome', '')))
    prod_name = _collapse_initials(normalizar(candidate.get('produtor', '')))
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

        # Guard: se o candidato tem MUITO mais tokens de linha que o OCR,
        # os tokens podem ser coincidencia (e.g. "Cuatro Vientos"
        # como frase em "Griten a los Cuatro Vientos Los Ninos Tienen Derechos").
        cand_line_tokens = _extract_line_tokens(cand_name, prod_name)
        if cand_line_tokens and len(line_tokens) / len(cand_line_tokens) < 0.4:
            return 0.0

    # GATE V — VARIEDADE/ESTILO (comparacao por frase canonica):
    # Extrai variedades como frases completas ("cabernet sauvignon", nao
    # "cabernet" + "sauvignon"). Se OCR tem variedade canonica, a frase
    # inteira deve aparecer no nome do candidato.
    # Ex: "Sauvignon Blanc" nao casa com "Cabernet Sauvignon".
    # Ex: "Tinto" nao casa com "Chardonnay".
    ocr_varieties = _extract_canonical_varieties(ocr_norm)
    if ocr_varieties:
        if not any(v in cand_name for v in ocr_varieties):
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


def _fast_resolve(name, producer, seen_ids, scoring_name=None, timeout_ms=1500, limit=10):
    """Fase 1: exact/prefix/producer, sem tokens.

    scoring_name: nome limpo (sem regiao) para avaliacao nos gates.
    Se o nome tem iniciais colapsiveis ('D. Eugenio' → 'deugenio'),
    pula a query original (que vai estourar timeout no prefix 'd%')
    e vai direto para a forma colapsada.
    """
    eval_name = scoring_name or name
    kwargs = {"produtor": producer} if producer else {}

    name_norm = normalizar(name)
    collapsed = _collapse_initials(name_norm)
    has_initials = collapsed != name_norm

    # Query original: pula se nome tem iniciais (prefix 'd%' estoura timeout)
    if not has_initials:
        try:
            result = search_wine(name, limit=limit, allow_fuzzy=False, skip_tokens=True, timeout_ms=timeout_ms, **kwargs)
            best = _pick_best(eval_name, result.get("wines", []), seen_ids)
            if best:
                print(f"[resolver] multi_item phase=fast matched={best.get('id')}", flush=True)
                return best
        except Exception:
            pass

    # Forma colapsada: 'd eugenio' → 'deugenio' (prefix mais especifico, rapido)
    if has_initials:
        try:
            result = search_wine(collapsed, limit=limit, allow_fuzzy=False, skip_tokens=True, timeout_ms=timeout_ms)
            best = _pick_best(eval_name, result.get("wines", []), seen_ids)
            if best:
                print(f"[resolver] multi_item phase=fast_collapsed matched={best.get('id')}", flush=True)
                return best
        except Exception:
            pass

    return None


def _structured_resolve(w, seen_ids, scoring_name=None):
    """Busca usando campos estruturados do OCR (line, variety).

    Forma queries curtas e especificas que o prefix/exact pode encontrar
    mesmo quando o name completo falha.
    Ex: producer='Freixenet', line='ICE' → query 'Freixenet ICE'
    Ex: line='Aura', variety='Carmenere' → query 'Aura Carmenere'
    """
    name = (w.get("name") or "").strip()
    producer = (w.get("producer") or "").strip() or None
    line = (w.get("line") or "").strip() or None
    variety = (w.get("variety") or "").strip() or None

    if not line and not variety:
        return None

    eval_name = scoring_name or name
    queries = []

    # Query 1: line + variety (mais especifica)
    if line and variety:
        q = f"{line} {variety}"
        if producer:
            queries.append((q, {"produtor": producer}))
        queries.append((q, {}))

    # Query 2: producer + line (para vinhos como 'Freixenet ICE')
    if producer and line:
        queries.append((f"{producer} {line}", {}))

    # Query 3: line sozinha (para linhas com nome forte)
    if line and len(line.split()) >= 2:
        queries.append((line, {}))

    for query, kwargs in queries:
        try:
            result = search_wine(query, limit=10, allow_fuzzy=False, skip_tokens=True, timeout_ms=1500, **kwargs)
            best = _pick_best(eval_name, result.get("wines", []), seen_ids)
            if best:
                print(f"[resolver] multi_item phase=structured q={query!r} matched={best.get('id')}", flush=True)
                return best
        except Exception:
            continue

    return None


def _token_resolve(name, producer, seen_ids, scoring_name=None, timeout_ms=3000, prefer_broad=False):
    """Busca direta por tokens, bypassa exact/prefix/producer.

    Path rapido para casos de normalizacao divergente (D.Eugenio, Cuatro Vientos).
    Extrai 2-3 tokens mais distintivos e faz LIKE AND direto no banco.
    Inclui tokens da variante colapsada para cobrir 'deugenio'.
    Quando producer e fornecido, filtra por produtor (impede cross-producer).
    prefer_broad: inverte ordem — tenta sem producer e menos tokens PRIMEIRO.
    Usado para initials onde o producer do OCR nao bate com o DB.
    """
    eval_name = scoring_name or name
    name_norm = normalizar(name)
    collapsed = _collapse_initials(name_norm)

    # Coletar tokens de ambas as variantes
    all_tokens = set()
    for variant in [name_norm, collapsed]:
        for t in variant.split():
            if (len(t) >= 3
                    and t not in _GENERIC_WINE_TOKENS
                    and t not in _CLASSIFICATION_TOKENS
                    and not (len(t) == 4 and t.isdigit())):
                all_tokens.add(t)

    if len(all_tokens) < 2:
        return None

    # Top 3 por tamanho (mais distintivos)
    search_tokens = sorted(all_tokens, key=len, reverse=True)[:3]

    # Tentar combinacoes: [3 tokens, 2 tokens] x [com producer, sem producer]
    # Default: mais tokens com producer primeiro (mais seguro)
    # prefer_broad: inverte — sem producer e menos tokens primeiro (mais rapido para initials)
    producers = [producer, None] if producer else [None]
    token_counts = [len(search_tokens)]
    if len(search_tokens) > 2:
        token_counts.append(2)

    if prefer_broad:
        producers = list(reversed(producers))
        token_counts = list(reversed(token_counts))

    for p in producers:
        for n in token_counts:
            try:
                result = search_wine_tokens(search_tokens[:n], limit=10, timeout_ms=timeout_ms, produtor=p)
                best = _pick_best(eval_name, result.get("wines", []), seen_ids)
                if best:
                    label = f"tokens={search_tokens[:n]} prod={'yes' if p else 'no'}"
                    print(f"[resolver] multi_item phase=token_direct {label} matched={best.get('id')}", flush=True)
                    return best
            except Exception:
                continue

    return None


def _fallback_resolve(name, seen_ids, scoring_name=None):
    """Fase fallback: token pairs, timeout 2s, limit 10.

    Roda so quando fast e structured falharam. Queries curtas (2 tokens)
    que ativam o token LIKE search no search_wine.
    """
    eval_name = scoring_name or name
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
            result = search_wine(query, limit=10, allow_fuzzy=False, timeout_ms=2000)
            best = _pick_best(eval_name, result.get("wines", []), seen_ids)
            if best:
                print(f"[resolver] multi_item phase=fallback pair={pair} matched={best.get('id')}", flush=True)
                return best
        except Exception:
            continue

        if len(tried) >= _MAX_FALLBACK_PAIRS:
            break

    return None


def _resolve_multi(ocr_result):
    """Resolve multiplos vinhos de screenshot/shelf.

    Shelf: resolve em 2 camadas com mesmos gates de qualidade.
      Tier A (3 itens): fast-only (exact/prefix/producer).
      Tier B (2 itens): fast + fallback (token pairs).
      Tier C (resto): visual only, sem resolucao.
    Screenshot: mais permissivo (8 itens), fast + fallback.
    """
    wines_list = ocr_result.get("wines", [])
    if not wines_list:
        return [], []

    image_type = ocr_result.get("image_type", "screenshot")
    is_shelf = image_type == "shelf"

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

    # 4. Dividir em tiers (shelf) ou cap unico (screenshot)
    if is_shelf:
        tier_a = deduped[:_MAX_SHELF_TIER_A]
        tier_b = deduped[_MAX_SHELF_TIER_A:_MAX_SHELF_TIER_A + _MAX_SHELF_TIER_B]
        skipped = deduped[_MAX_SHELF_TIER_A + _MAX_SHELF_TIER_B:]
    else:
        tier_a = deduped[:_MAX_MULTI_ITEMS]
        tier_b = []
        skipped = deduped[_MAX_MULTI_ITEMS:]

    total_selected = len(tier_a) + len(tier_b)

    print(
        f"[resolver] multi: type={image_type} ocr={len(wines_list)} valid={len(valid)} "
        f"deduped={len(deduped)} selected={total_selected} skipped={len(skipped)}",
        flush=True,
    )

    # 5. Resolver cada tier
    resolved_items = []
    unresolved_items = []
    seen_ids = set()

    # Tier A: fast + structured + token_direct (shelf) ou fast+fallback (screenshot)
    use_fallback_a = not is_shelf
    for w in tier_a:
        name = (w.get("name") or "").strip()
        producer = (w.get("producer") or "").strip() or None
        scoring_name = _build_scoring_name(w)

        # Detectar initials colapsiveis: pular fast/structured (desperdicam
        # tempo em prefix timeout) e ir direto para token com ordem invertida
        _has_init = _collapse_initials(normalizar(name)) != normalizar(name)

        if _has_init:
            matched = _token_resolve(name, producer, seen_ids, scoring_name=scoring_name, prefer_broad=True)
        else:
            matched = _fast_resolve(name, producer, seen_ids, scoring_name=scoring_name)
            if not matched and is_shelf:
                matched = _structured_resolve(w, seen_ids, scoring_name=scoring_name)
            if not matched and is_shelf:
                matched = _token_resolve(name, producer, seen_ids, scoring_name=scoring_name)
            if not matched and use_fallback_a:
                matched = _fallback_resolve(name, seen_ids, scoring_name=scoring_name)

        if matched:
            seen_ids.add(matched['id'])
            resolved_items.append({"ocr": w, "wine": matched, "status": _derive_item_status(matched)})
        else:
            unresolved_items.append({"ocr": w, "status": "visual_only"})

    # Tier B: fast + structured + token_direct (shelf — recall ampliado, mesmos gates)
    for w in tier_b:
        name = (w.get("name") or "").strip()
        producer = (w.get("producer") or "").strip() or None
        scoring_name = _build_scoring_name(w)

        _has_init = _collapse_initials(normalizar(name)) != normalizar(name)

        if _has_init:
            matched = _token_resolve(name, producer, seen_ids, scoring_name=scoring_name, prefer_broad=True)
        else:
            matched = _fast_resolve(name, producer, seen_ids, scoring_name=scoring_name)
            if not matched:
                matched = _structured_resolve(w, seen_ids, scoring_name=scoring_name)
            if not matched:
                matched = _token_resolve(name, producer, seen_ids, scoring_name=scoring_name)

        if matched:
            seen_ids.add(matched['id'])
            resolved_items.append({"ocr": w, "wine": matched, "status": _derive_item_status(matched)})
        else:
            unresolved_items.append({"ocr": w, "status": "visual_only"})

    # Tier C: visual only — unresolved direto
    for w in skipped:
        unresolved_items.append({"ocr": w, "status": "visual_only"})

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
        # --- Label ---
        ocr = ocr_result.get("ocr_result", {})
        search_text = ocr_result.get("search_text", "")
        parts.append(f"[O usuario enviou foto de um rotulo. OCR identificou: {search_text}.]")

        if resolved_wines:
            w = resolved_wines[0]
            d = resolve_display(w)
            item_status = resolved_items[0].get("status", "confirmed_no_note") if resolved_items else _derive_item_status(w)
            nota_str = f"{d['display_note']}" if d['display_note'] else "sem nota"
            nota_tipo_str = f"({d['display_note_type']})" if d['display_note_type'] else ""
            # Score so aparece se confirmed_with_note; confirmed_no_note nunca expoe score numerico
            if item_status == "confirmed_with_note":
                score_str = f"{d['display_score']}" if d['display_score_available'] else "sem score"
            else:
                score_str = "sem score"
            parts.append(
                f"[Vinho encontrado no banco (status: {item_status}): {w.get('nome', '?')} "
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
            if item_status == "confirmed_with_note":
                parts.append("[Responda sobre este vinho. Use get_wine_details ou get_prices se precisar de mais dados.]")
            else:
                parts.append(
                    "[Vinho confirmado na base mas SEM nota de qualidade. "
                    "Apresente dados do banco (produtor, pais, regiao, preco). "
                    "NAO invente nota, score, ranking ou qualidade. "
                    "Use get_wine_details ou get_prices se precisar de mais dados.]"
                )
        else:
            # visual_only — label nao confirmado
            parts.append(
                "[Vinho NAO encontrado no banco (status: visual_only). "
                "Responda com o que sabe e avise que nao temos dados completos. "
                "NAO invente nota, score ou qualidade.]"
            )

    elif image_type in ("screenshot", "shelf"):
        type_label = "prateleira" if image_type == "shelf" else "screenshot"

        if resolved_items is not None:
            # --- Formato com vinculo OCR -> banco + status explicito ---
            _unresolved = unresolved_items or []
            total_read = len(resolved_items) + len(_unresolved)

            # Separar confirmados por status para instrucoes finais
            items_with_note = [it for it in resolved_items if it.get("status") == "confirmed_with_note"]
            items_no_note = [it for it in resolved_items if it.get("status") == "confirmed_no_note"]

            parts.append(f"[O usuario enviou foto de {type_label}.]")
            if total_read > 0:
                parts.append(f"[OCR identificou {total_read} vinho(s) por nome. Pode haver outros na imagem nao legiveis.]")

            # Vinhos confirmados COM nota (aptos a ranking)
            counter = 1
            if items_with_note:
                parts.append(f"[{len(items_with_note)} vinho(s) CONFIRMADO(S) COM NOTA (apto a ranking/comparacao):]")
                for item in items_with_note:
                    ocr_i = item["ocr"]
                    w = item["wine"]
                    d = resolve_display(w)

                    ocr_parts = [f"Lido na imagem: {ocr_i.get('name', '?')}"]
                    if ocr_i.get("price"):
                        ocr_parts.append(f"Preco visivel na imagem: {ocr_i['price']}")
                    if image_type == "screenshot" and ocr_i.get("rating"):
                        ocr_parts.append(f"Nota visivel no screenshot: {ocr_i['rating']}")

                    nota_str = f"{d['display_note']}"
                    nota_tipo_str = f"({d['display_note_type']})" if d['display_note_type'] else ""
                    score_str = f"{d['display_score']}" if d['display_score_available'] else "sem score"

                    parts.append(f"  {counter}. {' | '.join(ocr_parts)}")
                    parts.append(
                        f"     Banco: {w.get('nome', '?')} | {w.get('produtor', '?')} "
                        f"| Nota: {nota_str} {nota_tipo_str} "
                        f"| Score: {score_str} "
                        f"| Preco base: {w.get('preco_min', '?')}-{w.get('preco_max', '?')} {w.get('moeda', '')} "
                        f"| ID: {w.get('id', '?')}"
                    )
                    counter += 1

            # Vinhos confirmados SEM nota (dados de banco, mas nao aptos a ranking)
            if items_no_note:
                parts.append(f"[{len(items_no_note)} vinho(s) CONFIRMADO(S) SEM NOTA (dados de banco, mas NAO apto a ranking):]")
                for item in items_no_note:
                    ocr_i = item["ocr"]
                    w = item["wine"]

                    ocr_parts = [f"Lido na imagem: {ocr_i.get('name', '?')}"]
                    if ocr_i.get("price"):
                        ocr_parts.append(f"Preco visivel na imagem: {ocr_i['price']}")
                    if image_type == "screenshot" and ocr_i.get("rating"):
                        ocr_parts.append(f"Nota visivel no screenshot: {ocr_i['rating']}")

                    parts.append(f"  {counter}. {' | '.join(ocr_parts)}")
                    parts.append(
                        f"     Banco: {w.get('nome', '?')} | {w.get('produtor', '?')} "
                        f"| Nota: sem nota | Score: sem score "
                        f"| Preco base: {w.get('preco_min', '?')}-{w.get('preco_max', '?')} {w.get('moeda', '')} "
                        f"| ID: {w.get('id', '?')}"
                    )
                    counter += 1

            # Vinhos nao resolvidos (visual_only)
            if _unresolved:
                parts.append("[NAO ENCONTRADO(S) no banco (apenas leitura visual):]")
                for item in _unresolved:
                    ocr_i = item["ocr"]
                    ocr_parts = [ocr_i.get("name", "?")]
                    if ocr_i.get("price"):
                        ocr_parts.append(f"Preco visivel: {ocr_i['price']}")
                    if image_type == "screenshot" and ocr_i.get("rating"):
                        ocr_parts.append(f"Nota visivel: {ocr_i['rating']}")
                    parts.append(f"  {counter}. {' | '.join(ocr_parts)}")
                    counter += 1

            # Instrucao final com 3 niveis explicitos de certeza
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
            if _unresolved:
                rules.append(
                    "  - NAO ENCONTRADO (visual): cite nome e preco visivel. "
                    "NAO atribua nota, score, ranking, custo-beneficio ou qualidade. "
                    "Diga que ainda nao tem no acervo."
                )
            rules.append(
                "  Para ranking ou recomendacao, use APENAS vinhos CONFIRMADOS COM NOTA.]"
            )
            parts.append("\n".join(rules))

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
