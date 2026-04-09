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
      - resolved_wines: lista de vinhos encontrados (com dados completos)
      - unresolved: lista de nomes que nao foram encontrados
      - timing_ms: tempo de resolucao em ms
    """
    t0 = time.time()
    image_type = ocr_result.get("image_type", "")

    if image_type == "label":
        resolved, unresolved = _resolve_label(ocr_result)
    elif image_type in ("screenshot", "shelf"):
        resolved, unresolved = _resolve_multi(ocr_result)
    else:
        resolved, unresolved = [], []

    elapsed_ms = round((time.time() - t0) * 1000)

    return {
        "resolved_wines": resolved,
        "unresolved": unresolved,
        "timing_ms": elapsed_ms,
    }


def _resolve_label(ocr_result):
    """Resolve um unico vinho de rotulo."""
    ocr = ocr_result.get("ocr_result", {})
    name = ocr.get("name", "")
    producer = ocr.get("producer")
    vintage = ocr.get("vintage")
    region = ocr.get("region")

    if not name:
        return [], []

    # Buscar com filtros estruturados quando disponiveis
    kwargs = {}
    if producer:
        kwargs["produtor"] = producer
    if region:
        # OCR frequentemente devolve pais no campo region (ex: "Argentina")
        if region.strip().lower() in _KNOWN_COUNTRIES:
            kwargs["pais"] = region
        else:
            kwargs["regiao"] = region
    if vintage:
        try:
            kwargs["safra"] = int(vintage)
        except (ValueError, TypeError):
            pass

    result = search_wine(name, limit=5, **kwargs)
    wines = result.get("wines", [])

    if wines:
        return wines, []

    # Fallback: buscar so pelo nome sem filtros
    if kwargs:
        result = search_wine(name, limit=5)
        wines = result.get("wines", [])
        if wines:
            return wines, []

    # Fallback: buscar pelo produtor
    if producer:
        result = search_wine(producer, limit=5)
        wines = result.get("wines", [])
        if wines:
            return wines, []

    return [], [name]


def _resolve_multi(ocr_result):
    """Resolve multiplos vinhos de screenshot/shelf."""
    wines_list = ocr_result.get("wines", [])
    if not wines_list:
        return [], []

    all_resolved = []
    unresolved = []
    seen_ids = set()

    for w in wines_list:
        name = w.get("name", "")
        if not name:
            continue

        result = search_wine(name, limit=3)
        matches = result.get("wines", [])

        if matches:
            for m in matches:
                wid = m.get("id")
                if wid and wid not in seen_ids:
                    seen_ids.add(wid)
                    all_resolved.append(m)
                    break
        else:
            unresolved.append(name)

    return all_resolved, unresolved


def format_resolved_context(resolved_wines, unresolved, image_type, ocr_result):
    """Formata o resultado do pre-resolve em contexto para o Claude.

    Ao contrario do fluxo antigo (que mandava texto solto e pedia ao Claude
    para chamar search_wine), aqui ja entrega os dados resolvidos.
    """
    parts = []

    if image_type == "label":
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
            if len(resolved_wines) > 1:
                others = [f"{r.get('nome', '?')} (ID:{r.get('id', '?')})" for r in resolved_wines[1:4]]
                parts.append(f"[Outros candidatos: {', '.join(others)}]")
            parts.append("[Responda sobre este vinho. Use get_wine_details ou get_prices se precisar de mais dados.]")
        else:
            parts.append("[Vinho NAO encontrado no banco. Responda com o que sabe e avise que nao temos dados completos.]")

    elif image_type in ("screenshot", "shelf"):
        wine_names = [w.get("name", "?") for w in ocr_result.get("wines", [])]
        total = ocr_result.get("total_visible", len(wine_names))
        parts.append(f"[O usuario enviou foto de {'prateleira' if image_type == 'shelf' else 'screenshot'} com ~{total} vinhos.]")

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
        parts.append("[Responda sobre os vinhos encontrados. Use get_wine_details ou get_prices para dados extras.]")

    return "\n".join(parts)
