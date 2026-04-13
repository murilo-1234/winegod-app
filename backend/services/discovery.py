"""Discovery pipeline: enrichment + second resolve for unresolved wines.

Recebe itens que o resolver nao encontrou (status='visual_only'),
tenta enriquecer via Qwen-turbo, e faz segunda busca no banco.
"""

import time
import json
from tools.media import qwen_text_generate
from tools.search import search_wine
from tools.resolver import _pick_best, _derive_item_status

# Limites operacionais
MAX_SYNC_UNKNOWNS = 2
MAX_ENRICHMENT_CALLS = 2
MAX_BUDGET_MS = 3000

ENRICHMENT_PROMPT = """Given this wine name from a photo/menu OCR, provide normalized/corrected information.

Wine as read: "{raw_name}"
Producer as read: "{raw_producer}"

Return ONLY a JSON object:
{{"name": "corrected full wine name", "producer": "winery/producer name", "country": "country", "region": "wine region", "grape": "main grape variety"}}

Rules:
- Correct obvious OCR errors (e.g., "Pontgras" -> "MontGras", "Trivento" stays as is)
- If producer is missing, infer from the wine name if clearly identifiable
- Use null for fields you cannot determine
- Do NOT guess or invent information
"""


def discover_unknowns(unresolved_items, trace=None, initial_seen_ids=None):
    """Enrichment + second resolve para itens nao resolvidos.

    Args:
        unresolved_items: lista de {"ocr": {...}, "status": "visual_only"}
        trace: RequestTrace opcional para timing
        initial_seen_ids: set de wine IDs ja resolvidos no pre-resolve
            (evita duplicatas contra itens previamente confirmados)

    Returns:
        dict com:
            newly_resolved: [{"ocr": {...}, "wine": {...}, "status": "confirmed_*", "enriched": True, "enriched_data": {...}}]
            still_unresolved: [{"ocr": {...}, "status": "visual_only"}]
            stats: {"enriched": N, "resolved_second": N, "budget_used_ms": N, "skipped": N}
    """
    if not unresolved_items:
        return {"newly_resolved": [], "still_unresolved": [], "stats": {}}

    t0 = time.time()
    to_enrich = unresolved_items[:MAX_SYNC_UNKNOWNS]
    skipped = unresolved_items[MAX_SYNC_UNKNOWNS:]

    newly_resolved = []
    still_unresolved = []
    enrichment_count = 0
    seen_ids = set(initial_seen_ids) if initial_seen_ids else set()

    for item in to_enrich:
        # Circuit breaker por tempo
        elapsed_ms = (time.time() - t0) * 1000
        if elapsed_ms > MAX_BUDGET_MS:
            print(f"[discovery] budget exceeded ({elapsed_ms:.0f}ms), stopping", flush=True)
            still_unresolved.append(item)
            continue

        if enrichment_count >= MAX_ENRICHMENT_CALLS:
            still_unresolved.append(item)
            continue

        ocr = item.get("ocr", {})
        raw_name = ocr.get("name", "")
        raw_producer = ocr.get("producer", "")

        if not raw_name:
            still_unresolved.append(item)
            continue

        # Enrichment via Qwen-turbo
        enriched = _enrich_wine(raw_name, raw_producer)
        enrichment_count += 1

        if not enriched:
            still_unresolved.append(item)
            continue

        # Segunda resolucao com dados enriquecidos
        matched = _second_resolve(enriched, raw_name, seen_ids)

        if matched:
            seen_ids.add(matched["id"])
            status = _derive_item_status(matched)
            newly_resolved.append({
                "ocr": ocr,
                "wine": matched,
                "status": status,
                "enriched": True,
                "enriched_data": enriched,
            })
        else:
            still_unresolved.append(item)

    # Itens alem do cap ficam untouched
    still_unresolved.extend(skipped)

    elapsed_ms = round((time.time() - t0) * 1000)
    stats = {
        "enriched": enrichment_count,
        "resolved_second": len(newly_resolved),
        "budget_used_ms": elapsed_ms,
        "skipped": len(skipped),
    }
    print(
        f"[discovery] done: enriched={enrichment_count} "
        f"resolved={len(newly_resolved)} "
        f"still_unresolved={len(still_unresolved)} "
        f"time={elapsed_ms}ms",
        flush=True,
    )
    return {
        "newly_resolved": newly_resolved,
        "still_unresolved": still_unresolved,
        "stats": stats,
    }


def _enrich_wine(raw_name, raw_producer):
    """Chama Qwen-turbo para normalizar/corrigir dados do vinho."""
    prompt = ENRICHMENT_PROMPT.format(
        raw_name=raw_name,
        raw_producer=raw_producer or "unknown",
    )
    try:
        raw = qwen_text_generate(prompt)
        if not raw:
            return None
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)
    except Exception as e:
        print(f"[discovery] enrich error: {type(e).__name__}: {e}", flush=True)
        return None


def _second_resolve(enriched, original_name, seen_ids):
    """Tenta resolver o vinho enriquecido no banco COM quality gate.

    Usa _pick_best (threshold 0.4) do resolver para evitar matches errados.
    Tenta em ordem: enriched+filtros, enriched-only, original se mudou.
    """
    name = enriched.get("name") or original_name
    producer = enriched.get("producer")
    country = enriched.get("country")

    # Montar tentativas
    attempts = []
    kwargs1 = {}
    if producer:
        kwargs1["produtor"] = producer
    if country:
        kwargs1["pais"] = country
    if kwargs1:
        attempts.append(("enriched+filters", name, kwargs1))
    attempts.append(("enriched_only", name, {}))
    if name != original_name:
        attempts.append(("original", original_name, {}))

    # Scoring usa nome original (mais proximo do que o usuario viu)
    scoring_name = original_name

    for label, query, kwargs in attempts:
        try:
            result = search_wine(
                query, limit=5,
                allow_fuzzy=False, skip_tokens=False,
                timeout_ms=2000,
                **kwargs,
            )
            candidates = result.get("wines", [])
            if candidates:
                best = _pick_best(scoring_name, candidates, seen_ids)
                if best:
                    print(
                        f"[discovery] second_resolve: attempt={label} "
                        f"matched id={best.get('id')}",
                        flush=True,
                    )
                    return best
        except Exception:
            continue

    return None


# --- Logging ---

_STATUS_MAP = {
    "confirmed_with_note": "with_note",
    "confirmed_no_note": "without_note",
    "visual_only": "not_found",
}

_EXTRAS_KEYS = ("price", "vintage", "region", "grape", "variety")


def log_discovery(session_id, items, source_channel, latency_ms=None):
    """Persiste resultados de discovery na tabela discovery_log.

    Nao-bloqueante: erros sao logados mas nao propagados.
    """
    from db.connection import get_connection, release_connection

    if not items:
        return

    conn = get_connection()
    try:
        cur = conn.cursor()
        for item in items:
            ocr = item.get("ocr", {})
            wine = item.get("wine")
            status = item.get("status", "not_found")
            enriched_data = item.get("enriched_data")

            final_status = _STATUS_MAP.get(status, status)

            extras = {}
            for key in _EXTRAS_KEYS:
                val = ocr.get(key)
                if val:
                    extras[key] = val

            cur.execute(
                """INSERT INTO discovery_log
                   (session_id, source_channel, raw_name, raw_producer, extras,
                    enrichment_raw, resolved_wine_id, final_status, latency_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    session_id,
                    source_channel,
                    ocr.get("name", "?"),
                    ocr.get("producer"),
                    json.dumps(extras) if extras else None,
                    json.dumps(enriched_data) if enriched_data else None,
                    wine.get("id") if wine else None,
                    final_status,
                    latency_ms,
                ),
            )
        conn.commit()
    except Exception as e:
        print(f"[discovery_log] error: {type(e).__name__}: {e}", flush=True)
        conn.rollback()
    finally:
        release_connection(conn)
