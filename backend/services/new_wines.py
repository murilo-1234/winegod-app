"""Auto-cadastro online de vinhos novos para itens nao resolvidos.

Fluxo:
1. Classifica/enriquece OCR via prompt inspirado no pipeline Y2/Codex/Mistral
2. Pula itens que nao sao vinho ou estao com baixa confianca
3. Insere em `wines` de forma idempotente por `hash_dedup`
4. Retorna itens no formato `resolved_items` para o chat usar imediatamente
"""

import hashlib
import json
import time
from pathlib import Path
import sys

from db.connection import get_connection, release_connection
from tools.media import qwen_text_generate, gemini_text_generate
from tools.normalize import normalizar
from tools.resolver import _derive_item_status

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from pre_ingest_filter import should_skip_wine
from utils.country_names import iso_to_name as _central_iso_to_name

try:
    from config import Config
except ImportError:  # pragma: no cover
    from backend.config import Config  # type: ignore


MAX_SYNC_NEW_WINES = 2
MAX_BUDGET_MS = 8000
MIN_CONFIDENCE = 0.75

_COUNTRY_NAMES = None  # Removido — usar _central_iso_to_name de utils.country_names

def _normalize_style_key(s: str) -> str:
    """Normaliza chave: lowercase + remove acentos. 'Rosé' -> 'rose'."""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s).strip().lower())
        if unicodedata.category(c) != "Mn"
    )


_STYLE_MAP = {
    "tinto": "tinto",
    "red": "tinto",
    "branco": "branco",
    "white": "branco",
    "rose": "rose",
    "rosado": "rose",
    "rosato": "rose",
    "espumante": "espumante",
    "sparkling": "espumante",
    "fortificado": "fortificado",
    "fortified": "fortificado",
    "sobremesa": "sobremesa",
    "dessert": "sobremesa",
}

_FETCH_SQL = """
    SELECT id, nome, produtor, safra, tipo, pais, pais_nome, regiao, sub_regiao,
           uvas, teor_alcoolico, harmonizacao,
           vivino_rating, vivino_reviews, preco_min, preco_max, moeda,
           winegod_score, winegod_score_type, nota_wcf, nota_wcf_sample_size,
           confianca_nota
    FROM wines
    WHERE hash_dedup = %s
      AND suppressed_at IS NULL
    LIMIT 1
"""


AUTO_NEW_WINE_PROMPT = """You classify OCR-extracted possible wine items from a wine app.

For each item, decide whether it is:
- "wine"
- "spirit"
- "not_wine"
- "unknown"

Return ONLY valid JSON:
{{
  "items": [
    {{
      "index": 1,
      "kind": "wine",
      "full_name": "human-readable corrected wine name",
      "producer": "producer/winery name",
      "wine_name": "wine/cuvee name without producer",
      "country_code": "FR",
      "style": "tinto",
      "grape": "cabernet sauvignon",
      "region": "mendoza",
      "sub_region": null,
      "vintage": "2020",
      "abv": "13.5",
      "classification": "Reserva",
      "body": "medio",
      "pairing": "carne vermelha, cordeiro",
      "sweetness": "seco",
      "estimated_note": 4.1,
      "confidence": 0.90
    }}
  ]
}}

Rules:
- Do NOT invent facts. Use null when you do not know.
- Fortified wines (Porto, Sherry, Madeira, Marsala, Manzanilla, Fino, Oloroso) are "wine", not "spirit".
- If you are not reasonably confident this is a wine, use "unknown" or "not_wine".
- `country_code` must be ISO-2 uppercase or null.
- `style` must be one of: tinto, branco, rose, espumante, fortificado, sobremesa, null.
- `vintage` must be a 4-digit year or null.
- `abv` must be numeric text without % or null.
- `estimated_note` is optional. Use it only when the identification is reasonably confident.
- `confidence` must be between 0.0 and 1.0.
- Correct obvious OCR errors when they are clear.

Items:
{items_block}
"""


def auto_create_unknowns(unresolved_items, source_channel="chat", session_id=None, initial_seen_ids=None):
    """Tenta classificar/enriquecer e cadastrar itens nao resolvidos no banco."""
    if not unresolved_items:
        return {"newly_resolved": [], "still_unresolved": [], "blocked_items": [], "stats": {}}

    t0 = time.time()
    to_process = unresolved_items[:MAX_SYNC_NEW_WINES]
    skipped = unresolved_items[MAX_SYNC_NEW_WINES:]

    use_v3 = (
        Config.ENRICHMENT_MODE == "gemini_hybrid_v3"
        and Config.ENRICHMENT_V3_ENABLE_AUTO_CREATE
    )
    if use_v3:
        payload = _classify_candidates_v3(to_process, source_channel)
    else:
        payload = _classify_candidates(to_process)

    if not payload:
        return {
            "newly_resolved": [],
            "still_unresolved": list(unresolved_items),
            "blocked_items": [],
            "stats": {"classified": 0, "created": 0, "skipped": len(skipped), "budget_used_ms": round((time.time() - t0) * 1000)},
        }

    by_index = {
        item.get("index"): item
        for item in payload.get("items", [])
        if isinstance(item, dict)
    }

    newly_resolved = []
    still_unresolved = []
    blocked_items = []
    created_count = 0
    classified_count = len(by_index)
    blocked_not_wine = 0
    seen_ids = set(initial_seen_ids or [])

    for idx, unresolved in enumerate(to_process, start=1):
        if (time.time() - t0) * 1000 > MAX_BUDGET_MS:
            still_unresolved.append(unresolved)
            continue

        enriched = by_index.get(idx)
        if not _is_insertable_wine(enriched):
            still_unresolved.append(unresolved)
            continue

        skip_reason = _get_pre_ingest_skip_reason(enriched, unresolved.get("ocr", {}))
        if skip_reason:
            blocked_not_wine += 1
            print(f"[new_wines] blocked by pre_ingest: {skip_reason}", flush=True)
            blocked_items.append({
                "ocr": unresolved.get("ocr", {}),
                "reason": skip_reason,
                "source_channel": source_channel,
            })
            continue

        wine = _insert_or_get_wine(enriched, unresolved.get("ocr", {}), source_channel, session_id)
        if not wine:
            still_unresolved.append(unresolved)
            continue
        wine_id = wine.get("id")
        if wine_id and wine_id in seen_ids:
            still_unresolved.append(unresolved)
            continue
        if wine_id:
            seen_ids.add(wine_id)

        created_count += 1
        newly_resolved.append({
            "ocr": unresolved.get("ocr", {}),
            "wine": wine,
            "status": _derive_item_status(wine),
            "auto_created": True,
            "enriched_data": enriched,
        })

    still_unresolved.extend(skipped)
    elapsed_ms = round((time.time() - t0) * 1000)
    return {
        "newly_resolved": newly_resolved,
        "still_unresolved": still_unresolved,
        "blocked_items": blocked_items,
        "stats": {
            "classified": classified_count,
            "created": created_count,
            "blocked_not_wine": blocked_not_wine,
            "skipped": len(skipped),
            "budget_used_ms": elapsed_ms,
        },
    }


def _classify_candidates(unresolved_items):
    """Chama IA com prompt multi-item e retorna o JSON parseado."""
    if not unresolved_items:
        return None

    items_block = []
    for idx, item in enumerate(unresolved_items, start=1):
        ocr = item.get("ocr", {})
        name = ocr.get("name") or ""
        producer = ocr.get("producer") or ""
        vintage = ocr.get("vintage") or ""
        region = ocr.get("region") or ""
        grape = ocr.get("grape") or ""
        price = ocr.get("price") or ""
        items_block.append(
            f'{idx}. OCR name="{name}"'
            f' | producer="{producer}"'
            f' | vintage="{vintage}"'
            f' | region="{region}"'
            f' | grape="{grape}"'
            f' | price="{price}"'
        )

    prompt = AUTO_NEW_WINE_PROMPT.format(items_block="\n".join(items_block))

    try:
        raw = qwen_text_generate(prompt)
        if not raw:
            raw = gemini_text_generate(prompt, thinking=False)
        if not raw:
            return None
        try:
            return _parse_llm_json(raw)
        except (json.JSONDecodeError, ValueError, KeyError):
            # Qwen returned invalid JSON — try Gemini
            raw = gemini_text_generate(prompt, thinking=False)
            if not raw:
                return None
            return _parse_llm_json(raw)
    except Exception as e:
        print(f"[new_wines] classify error: {type(e).__name__}: {e}", flush=True)
        return None


def _classify_candidates_v3(unresolved_items, source_channel):
    """Classificador via enrichment v3 hibrido (Gemini 2.5 + 3.1).

    Retorna payload compativel com o formato JSON do legado
    (`{"items": [{...}]}`) para que `_is_insertable_wine()` e
    `_insert_or_get_wine()` sigam funcionando sem mudanca de contrato.
    """
    if not unresolved_items:
        return None

    from services.enrichment_v3 import enrich_items_v3, to_auto_create_enriched

    try:
        v3 = enrich_items_v3(
            unresolved_items, source_channel=f"auto_create_{source_channel}"
        )
    except Exception as e:
        print(f"[new_wines] v3 classify error: {type(e).__name__}: {e}", flush=True)
        return None

    items = [to_auto_create_enriched(parsed) for parsed in v3.get("items", [])]
    return {"items": items, "v3_stats": v3.get("stats")}


def _parse_llm_json(raw_text):
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def _is_insertable_wine(enriched):
    if not enriched or enriched.get("kind") != "wine":
        return False
    confidence = _safe_float(enriched.get("confidence"))
    if confidence is None or confidence < MIN_CONFIDENCE:
        return False
    producer = (enriched.get("producer") or "").strip()
    full_name = (enriched.get("full_name") or "").strip()
    if not producer or not full_name:
        return False
    return True


def _get_pre_ingest_skip_reason(enriched, ocr=None):
    candidates = []

    if enriched:
        full_name = _clean_text(enriched.get("full_name"))
        producer = _clean_text(enriched.get("producer"))
        wine_name = _compose_wine_name(enriched)
        if full_name or wine_name or producer:
            candidates.append((full_name or wine_name or "", producer or ""))

    if ocr:
        ocr_name = _clean_text(ocr.get("name"))
        ocr_producer = _clean_text(ocr.get("producer"))
        if ocr_name or ocr_producer:
            candidates.append((ocr_name or "", ocr_producer or ""))

    seen = set()
    for nome, produtor in candidates:
        key = (nome, produtor)
        if key in seen:
            continue
        seen.add(key)
        skip, reason = should_skip_wine(nome, produtor)
        if skip:
            return reason

    return None


def _insert_or_get_wine(enriched, ocr, source_channel, session_id):
    skip_reason = _get_pre_ingest_skip_reason(enriched, ocr)
    if skip_reason:
        print(f"[new_wines] insert blocked by pre_ingest: {skip_reason}", flush=True)
        return None

    conn = get_connection()
    try:
        wine_name = _compose_wine_name(enriched)
        producer = (enriched.get("producer") or "").strip()
        if not wine_name or not producer:
            return None
        nome_normalizado = normalizar(wine_name)
        produtor_normalizado = normalizar(producer)
        vintage = _clean_vintage(enriched.get("vintage"))
        hash_dedup = _generate_hash_dedup(nome_normalizado, produtor_normalizado, vintage)

        pais = _clean_country_code(enriched.get("country_code"))
        pais_nome = _central_iso_to_name(pais) if pais else None
        estilo = _clean_style(enriched.get("style"))
        uvas_json = _to_jsonb_list(enriched.get("grape"))
        abv = _parse_abv(enriched.get("abv"))
        harmonizacao = _clean_text(enriched.get("pairing"))
        classification = _clean_text(enriched.get("classification"))
        body = _clean_text(enriched.get("body"))
        sweetness = _clean_text(enriched.get("sweetness"))
        region = _clean_text(enriched.get("region"))
        sub_region = _clean_text(enriched.get("sub_region"))
        estimated_note = _safe_float(enriched.get("estimated_note"))
        confidence = _safe_float(enriched.get("confidence"))

        description_parts = []
        if classification:
            description_parts.append(classification)
        if body:
            description_parts.append(f"corpo {body}")
        if sweetness:
            description_parts.append(sweetness)
        description = " | ".join(description_parts) if description_parts else None

        nota_wcf = None
        confianca_nota = None
        if estimated_note is not None and confidence is not None and confidence >= MIN_CONFIDENCE:
            nota_wcf = round(estimated_note, 2)
            confianca_nota = min(max(confidence, 0.0), 1.0)

        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO wines
                   (hash_dedup, nome, nome_normalizado, produtor, produtor_normalizado,
                    safra, tipo, pais, pais_nome, regiao, sub_regiao,
                    uvas, teor_alcoolico, descricao, harmonizacao,
                    total_fontes, fontes, descoberto_em, atualizado_em,
                    nota_wcf, confianca_nota)
                   VALUES
                   (%s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s, %s, %s,
                    %s, %s::jsonb, NOW(), NOW(),
                    %s, %s)
                   ON CONFLICT (hash_dedup) WHERE hash_dedup IS NOT NULL AND hash_dedup != '' DO NOTHING""",
                (
                    hash_dedup,
                    wine_name,
                    nome_normalizado,
                    producer,
                    produtor_normalizado,
                    vintage,
                    estilo,
                    pais,
                    pais_nome,
                    region,
                    sub_region,
                    uvas_json,
                    abv,
                    description,
                    harmonizacao,
                    0,
                    json.dumps([f"chat_auto_{source_channel}"]),
                    nota_wcf,
                    confianca_nota,
                ),
            )

            cur.execute(_FETCH_SQL, (hash_dedup,))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None

            columns = [desc[0] for desc in cur.description]
            wine = dict(zip(columns, row))
            for key, value in list(wine.items()):
                if hasattr(value, "as_integer_ratio"):
                    wine[key] = float(value)
        conn.commit()
        return wine
    except Exception as e:
        print(f"[new_wines] insert error: {type(e).__name__}: {e}", flush=True)
        conn.rollback()
        return None
    finally:
        release_connection(conn)


def _compose_wine_name(enriched):
    wine_name = _clean_text(enriched.get("wine_name"))
    producer = _clean_text(enriched.get("producer"))
    full_name = _clean_text(enriched.get("full_name"))

    if wine_name:
        return wine_name
    if full_name and producer:
        lowered_full = full_name.casefold()
        lowered_prod = producer.casefold()
        if lowered_full == lowered_prod:
            return full_name
        if lowered_full.startswith(lowered_prod):
            stripped = full_name[len(producer):].strip(" -|/")
            if stripped:
                return stripped
    return full_name or producer or ""


def _generate_hash_dedup(nome_normalizado, produtor_normalizado, safra):
    chave = f"{produtor_normalizado or ''}|{nome_normalizado or ''}|{safra or ''}"
    return hashlib.md5(chave.encode()).hexdigest()


def _clean_country_code(value):
    if not value:
        return None
    code = str(value).strip().lower()
    if len(code) != 2:
        return None
    return code


def _clean_style(value):
    if not value:
        return None
    return _STYLE_MAP.get(_normalize_style_key(value))


def _clean_vintage(value):
    if value is None:
        return None
    text = str(value).strip()
    if len(text) == 4 and text.isdigit():
        return text
    return None


def _parse_abv(value):
    if value is None:
        return None
    try:
        text = str(value).replace("%", "").replace(",", ".").strip()
        parsed = float(text)
        if 0 <= parsed <= 100:
            return parsed
    except Exception:
        return None
    return None


def _to_jsonb_list(value):
    if not value:
        return None
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
    else:
        parts = [v.strip() for v in str(value).split(",") if v.strip()]
    if not parts:
        return None
    return json.dumps(parts)


def _safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "null":
        return None
    return text
