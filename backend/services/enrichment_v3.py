"""Enrichment v3: hibrido Gemini 2.5 Flash Lite + 3.1 Flash Lite Preview.

Modulo unico usado tanto pelo `discovery` quanto pelo `auto_create`:

1. monta bloco tabular de itens OCR
2. chama Gemini 2.5 Flash Lite com `thinking=0`
3. parseia a saida tabular (W|..., S, X, =N)
4. aplica heuristica local de escalacao
5. re-chama Gemini 3.1 Flash Lite Preview so para itens dificeis
6. devolve estrutura normalizada pronta para reuso

`thinking=0` e obrigatorio e validado em tempo de execucao via
`ThinkingLeakError` no helper em `tools/media.py`.
"""

from __future__ import annotations

import os
import time
from typing import Any

from tools.media import gemini_enrichment_generate, ThinkingLeakError

try:
    from config import Config
except ImportError:  # pragma: no cover - fallback for flat imports
    from backend.config import Config  # type: ignore

from utils.country_names import iso_to_name as _central_iso_to_name


_PROMPT_CACHE: dict[str, str] = {}
_CONTROLLED_ROLLOUT_WARNED = False


_ISO_TO_EN = {
    "ad": "Andorra", "al": "Albania", "am": "Armenia", "ar": "Argentina",
    "at": "Austria", "au": "Australia", "az": "Azerbaijan", "ba": "Bosnia and Herzegovina",
    "be": "Belgium", "bg": "Bulgaria", "bo": "Bolivia", "br": "Brazil",
    "ca": "Canada", "ch": "Switzerland", "cl": "Chile", "cn": "China",
    "co": "Colombia", "cr": "Costa Rica", "cy": "Cyprus", "cz": "Czech Republic",
    "de": "Germany", "dk": "Denmark", "dz": "Algeria", "ec": "Ecuador",
    "ee": "Estonia", "eg": "Egypt", "es": "Spain", "et": "Ethiopia",
    "fi": "Finland", "fr": "France", "gb": "United Kingdom", "ge": "Georgia",
    "gr": "Greece", "hr": "Croatia", "ht": "Haiti", "hu": "Hungary",
    "id": "Indonesia", "ie": "Ireland", "il": "Israel", "in": "India",
    "ir": "Iran", "it": "Italy", "jp": "Japan", "ke": "Kenya",
    "kr": "South Korea", "lb": "Lebanon", "lt": "Lithuania", "lu": "Luxembourg",
    "lv": "Latvia", "ma": "Morocco", "md": "Moldova", "me": "Montenegro",
    "mk": "North Macedonia", "mt": "Malta", "mu": "Mauritius", "mx": "Mexico",
    "na": "Namibia", "nl": "Netherlands", "no": "Norway", "np": "Nepal",
    "nz": "New Zealand", "pe": "Peru", "ph": "Philippines", "pl": "Poland",
    "ps": "Palestine", "pt": "Portugal", "py": "Paraguay", "ro": "Romania",
    "rs": "Serbia", "ru": "Russia", "sa": "Saudi Arabia", "se": "Sweden",
    "sg": "Singapore", "si": "Slovenia", "sk": "Slovakia", "sy": "Syria",
    "th": "Thailand", "tn": "Tunisia", "tr": "Turkey", "tw": "Taiwan",
    "ua": "Ukraine", "us": "United States", "uy": "Uruguay", "uz": "Uzbekistan",
    "ve": "Venezuela", "vn": "Vietnam", "xk": "Kosovo", "za": "South Africa",
}


def _iso_to_en(code):
    if not code:
        return None
    return _ISO_TO_EN.get(code.lower())


# --- campos do formato tabular W| ---
_W_FIELDS = (
    "producer",
    "wine_name",
    "country_code",
    "style_code",
    "grape",
    "region",
    "sub_region",
    "vintage",
    "abv",
    "classification",
    "body",
    "pairing",
    "sweetness",
    "size",
    "service_temp",
    "aging",
    "decant",
)


_STYLE_CODE_MAP = {
    "r": "tinto",
    "w": "branco",
    "p": "rose",
    "s": "espumante",
    "f": "fortificado",
    "d": "sobremesa",
}

_COUNTRY_NAMES = None  # Removido — usar _central_iso_to_name de utils.country_names


def _warn_controlled_rollout_once(source_channel: str | None) -> None:
    global _CONTROLLED_ROLLOUT_WARNED
    if _CONTROLLED_ROLLOUT_WARNED or not Config.ENRICHMENT_V3_CONTROLLED_ONLY:
        return
    print(
        "[enrichment_v3] CONTROLLED ROLLOUT ONLY: activate first on text/pdf "
        f"and validate before broader release (channel={source_channel})",
        flush=True,
    )
    _CONTROLLED_ROLLOUT_WARNED = True


def load_prompt_template() -> str:
    """Carrega template do prompt v3; cache em memoria por caminho."""
    raw_path = Config.ENRICHMENT_V3_PROMPT_PATH
    cached = _PROMPT_CACHE.get(raw_path)
    if cached is not None:
        return cached

    candidates = [raw_path]
    if not os.path.isabs(raw_path):
        here = os.path.dirname(os.path.abspath(__file__))
        # backend/services/enrichment_v3.py -> backend/..
        backend_root = os.path.dirname(here)
        repo_root = os.path.dirname(backend_root)
        candidates.append(os.path.join(repo_root, raw_path))
        # path already carries "backend/..": also try from backend_root
        if raw_path.startswith("backend" + os.sep) or raw_path.startswith("backend/"):
            stripped = raw_path.split(os.sep, 1)[-1] if os.sep in raw_path else raw_path.split("/", 1)[-1]
            candidates.append(os.path.join(backend_root, stripped))

    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            _PROMPT_CACHE[raw_path] = text
            return text
        except FileNotFoundError:
            continue

    raise FileNotFoundError(
        f"enrichment v3 prompt not found. tried: {candidates}"
    )


def build_items_block(items: list[dict[str, Any]]) -> str:
    """Converte items OCR em linhas `N. texto` para o prompt tabular."""
    lines = []
    for idx, item in enumerate(items, start=1):
        ocr = item.get("ocr", {}) if isinstance(item, dict) else {}
        raw_name = (ocr.get("name") or "").strip()
        producer = (ocr.get("producer") or "").strip()
        vintage = (ocr.get("vintage") or "").strip()
        region = (ocr.get("region") or "").strip()
        grape = (ocr.get("grape") or ocr.get("variety") or "").strip()
        classification = (ocr.get("classification") or "").strip()
        line = (ocr.get("line") or "").strip()
        parts = []

        def _add_part(value: str) -> None:
            if not value:
                return
            current = " ".join(parts).lower()
            if value.lower() in current:
                return
            parts.append(value)

        _add_part(producer)
        _add_part(raw_name)
        _add_part(vintage)
        _add_part(classification)
        _add_part(line)
        _add_part(grape)
        _add_part(region)

        text = " ".join(parts).strip() or raw_name or "?"
        lines.append(f"{idx}. {text}")
    return "\n".join(lines)


def parse_tabular_output(raw_text: str, total_items: int) -> list[dict[str, Any]]:
    """Parseia as linhas do formato tabular.

    Retorna uma lista com `total_items` dicts, uma para cada indice de entrada.
    Linhas faltantes produzem `{kind: "unknown"}`.
    """
    results: dict[int, dict[str, Any]] = {}
    idx = 0
    for line in (raw_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        idx += 1
        if idx > total_items:
            break
        results[idx] = _parse_single_line(stripped, idx)

    normalized = []
    for i in range(1, total_items + 1):
        if i in results:
            normalized.append(results[i])
        else:
            normalized.append({
                "index": i,
                "kind": "unknown",
                "raw_line": None,
            })
    return normalized


def _parse_single_line(line: str, index: int) -> dict[str, Any]:
    line_clean = line.strip()

    if line_clean.upper() == "X":
        return {"index": index, "kind": "not_wine", "raw_line": line_clean}
    if line_clean.upper() == "S":
        return {"index": index, "kind": "spirit", "raw_line": line_clean}

    if not line_clean.upper().startswith("W|"):
        return {"index": index, "kind": "unknown", "raw_line": line_clean}

    parts = line_clean.split("|")
    # drop leading "W"
    parts = parts[1:]

    duplicate_of = None
    if parts and parts[-1].strip().startswith("="):
        tail = parts.pop().strip()
        try:
            duplicate_of = int(tail.lstrip("="))
        except ValueError:
            duplicate_of = None

    fields: dict[str, Any] = {name: None for name in _W_FIELDS}
    for i, name in enumerate(_W_FIELDS):
        if i >= len(parts):
            break
        value = parts[i].strip()
        if not value or value == "??":
            continue
        fields[name] = value

    style_code = (fields.get("style_code") or "").lower()
    style = _STYLE_CODE_MAP.get(style_code) if style_code else None

    full_name = _compose_full_name(fields.get("producer"), fields.get("wine_name"))

    return {
        "index": index,
        "kind": "wine",
        "producer": fields.get("producer"),
        "wine_name": fields.get("wine_name"),
        "full_name": full_name,
        "country_code": _normalize_country_code(fields.get("country_code")),
        "style": style,
        "style_code": style_code or None,
        "grape": fields.get("grape"),
        "region": fields.get("region"),
        "sub_region": fields.get("sub_region"),
        "vintage": _normalize_vintage(fields.get("vintage")),
        "abv": fields.get("abv"),
        "classification": fields.get("classification"),
        "body": fields.get("body"),
        "pairing": fields.get("pairing"),
        "sweetness": fields.get("sweetness"),
        "size": fields.get("size"),
        "service_temp": fields.get("service_temp"),
        "aging": fields.get("aging"),
        "decant": fields.get("decant"),
        "duplicate_of": duplicate_of,
        "raw_line": line_clean,
    }


def _compose_full_name(producer: str | None, wine_name: str | None) -> str | None:
    prod = (producer or "").strip()
    wine = (wine_name or "").strip()
    if not prod and not wine:
        return None
    if not prod:
        return wine
    if not wine:
        return prod
    if wine.lower().startswith(prod.lower()):
        return wine
    return f"{prod} {wine}".strip()


def _normalize_country_code(value: str | None) -> str | None:
    if not value:
        return None
    code = value.strip().lower()
    return code if len(code) == 2 and code.isalpha() else None


def _normalize_vintage(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if text.upper() == "NV":
        return "NV"
    if len(text) == 4 and text.isdigit():
        return text
    return None


# --- heuristica de escalacao 2.5 -> 3.1 ---

def needs_escalation(parsed: dict[str, Any], ocr_name: str | None) -> bool:
    kind = parsed.get("kind")
    if kind == "unknown":
        if ocr_name and _looks_like_wine_text(ocr_name):
            return True
        return False
    if kind != "wine":
        return False
    producer = (parsed.get("producer") or "").strip()
    wine = (parsed.get("wine_name") or "").strip()
    region = (parsed.get("region") or "").strip()
    country = (parsed.get("country_code") or "").strip()
    classification = (parsed.get("classification") or "").strip()

    # 1. produtor ausente, mas nome OCR sugere vinho estruturado
    if not producer and ocr_name and _ocr_has_hidden_producer_signal(ocr_name):
        return True
    # 2. nome vazio
    if not wine:
        return True
    # 3. regiao+pais vazios ao mesmo tempo
    if not region and not country:
        return True
    # 4. OCR carrega DO/AOC/DOC/DOCG/IGT/IGP e a saida veio sem classificacao
    if ocr_name and _mentions_classification(ocr_name) and not classification:
        return True
    return False


_WINE_SIGNAL_WORDS = (
    "vinho", "wine", "vino", "vintage", "safra",
    "doc", "docg", "aoc", "igt", "igp", "dop", "avaliacao",
    "cabernet", "merlot", "syrah", "malbec", "pinot",
    "chardonnay", "sauvignon", "riesling", "tempranillo",
    "rioja", "douro", "bordeaux", "chianti", "mendoza",
    "tinto", "branco", "rose", "espumante", "champagne",
)


def _looks_like_wine_text(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in _WINE_SIGNAL_WORDS)


def _ocr_has_hidden_producer_signal(text: str) -> bool:
    """Sinal minimo: a string tem >=2 tokens alfabeticos,
    nao e so numero/codigo, e nao e uma unica palavra curta."""
    tokens = [t for t in text.split() if any(c.isalpha() for c in t)]
    if len(tokens) < 2:
        return False
    if len(text.strip()) < 5:
        return False
    return True


def _mentions_classification(text: str) -> bool:
    lower = text.lower()
    markers = (
        "docg", "doca", "docca", "aoc", "igt", "igp", "dop",
        "gran reserva", "reserva", "riserva", "grand cru",
        "premier cru", "crianza",
    )
    return any(m in lower for m in markers)


# --- interface publica ---

def enrich_items_v3(
    items: list[dict[str, Any]],
    source_channel: str | None = None,
    trace: Any | None = None,
) -> dict[str, Any]:
    """Ponto de entrada unico do enrichment v3.

    Args:
        items: lista `unresolved_items` no padrao `{"ocr": {...}}`
        source_channel: canal para logging (pdf, video, text, image, shelf)
        trace: RequestTrace opcional (ignorado hoje; reservado para steps)

    Returns dict com:
        items: lista paralela ao input, cada elemento com estrutura normalizada
        raw_primary/raw_escalated: saida bruta por modelo
        stats: batch_size, escalated, tempo, tokens
    """
    stats = {
        "source_channel": source_channel,
        "model_primary": Config.ENRICHMENT_GEMINI_25_MODEL,
        "model_escalated": Config.ENRICHMENT_GEMINI_31_MODEL,
        "total_items": len(items),
        "escalated_items": 0,
        "prompt_tokens": 0,
        "output_tokens": 0,
        "thought_tokens": 0,
        "latency_ms": 0,
        "fallback_used": False,
        "fallback_reason": None,
        "fallback_model": None,
    }

    if not items:
        return {"items": [], "raw_primary": "", "raw_escalated": "", "stats": stats}

    t0 = time.time()
    _warn_controlled_rollout_once(source_channel)

    prompt_template = load_prompt_template()
    items_block = build_items_block(items)
    prompt_primary = prompt_template.replace("{items_block}", items_block)

    primary_model = Config.ENRICHMENT_GEMINI_25_MODEL
    try:
        primary = gemini_enrichment_generate(prompt_primary, model=primary_model)
    except ThinkingLeakError:
        # nunca silenciar leak de thinking: custo/privacidade real
        raise
    except Exception as e:
        reason = f"{type(e).__name__}: {e}"
        print(f"[enrichment_v3] primary failed: {reason}", flush=True)
        if not Config.ENRICHMENT_V3_FALLBACK_ENABLED:
            stats["latency_ms"] = round((time.time() - t0) * 1000)
            return {
                "items": [{"index": i + 1, "kind": "unknown"} for i in range(len(items))],
                "raw_primary": "",
                "raw_escalated": "",
                "stats": stats,
            }
        fb_model = Config.ENRICHMENT_V3_FALLBACK_MODEL
        print(
            f"[enrichment_v3] falling back to pure {fb_model} (reason={reason})",
            flush=True,
        )
        try:
            primary = gemini_enrichment_generate(prompt_primary, model=fb_model)
        except ThinkingLeakError:
            raise
        except Exception as e2:
            fb_reason = f"{type(e2).__name__}: {e2}"
            print(f"[enrichment_v3] fallback also failed: {fb_reason}", flush=True)
            stats["fallback_used"] = True
            stats["fallback_reason"] = reason
            stats["fallback_model"] = fb_model
            stats["latency_ms"] = round((time.time() - t0) * 1000)
            return {
                "items": [{"index": i + 1, "kind": "unknown"} for i in range(len(items))],
                "raw_primary": "",
                "raw_escalated": "",
                "stats": stats,
            }
        stats["fallback_used"] = True
        stats["fallback_reason"] = reason
        stats["fallback_model"] = fb_model
        primary_model = fb_model

    stats["prompt_tokens"] += primary["prompt_tokens"]
    stats["output_tokens"] += primary["output_tokens"]
    stats["thought_tokens"] += primary["thought_tokens"]

    parsed = parse_tabular_output(primary["text"], len(items))
    for p in parsed:
        p["source_model"] = primary_model
        p["escalated"] = False

    # decidir escalacao
    to_escalate_indexes = []
    for idx, item in enumerate(items, start=1):
        ocr_name = (item.get("ocr", {}) or {}).get("name")
        if needs_escalation(parsed[idx - 1], ocr_name):
            to_escalate_indexes.append(idx)

    raw_escalated = ""
    if to_escalate_indexes:
        escalated_items = [items[i - 1] for i in to_escalate_indexes]
        escalated_block = build_items_block(escalated_items)
        prompt_escalated = prompt_template.replace("{items_block}", escalated_block)
        try:
            escalated = gemini_enrichment_generate(
                prompt_escalated, model=Config.ENRICHMENT_GEMINI_31_MODEL
            )
            raw_escalated = escalated["text"]
            stats["prompt_tokens"] += escalated["prompt_tokens"]
            stats["output_tokens"] += escalated["output_tokens"]
            stats["thought_tokens"] += escalated["thought_tokens"]

            parsed_escalated = parse_tabular_output(
                raw_escalated, len(escalated_items)
            )
            for local_idx, original_idx in enumerate(to_escalate_indexes, start=1):
                new_parsed = parsed_escalated[local_idx - 1]
                if new_parsed.get("kind") == "unknown":
                    continue
                new_parsed["index"] = original_idx
                new_parsed["source_model"] = Config.ENRICHMENT_GEMINI_31_MODEL
                new_parsed["escalated"] = True
                parsed[original_idx - 1] = new_parsed
            stats["escalated_items"] = len(to_escalate_indexes)
        except ThinkingLeakError:
            # nunca silenciar leak de thinking, mesmo na escalacao
            raise
        except Exception as e:
            print(
                f"[enrichment_v3] escalation failed: {type(e).__name__}: {e}",
                flush=True,
            )
            # mantem resultado do primary sem escalar

    stats["latency_ms"] = round((time.time() - t0) * 1000)

    print(
        f"[enrichment_v3] channel={source_channel} "
        f"items={stats['total_items']} escalated={stats['escalated_items']} "
        f"tokens_p={stats['prompt_tokens']} tokens_o={stats['output_tokens']} "
        f"thoughts={stats['thought_tokens']} ms={stats['latency_ms']} "
        f"fallback={stats['fallback_used']}",
        flush=True,
    )

    return {
        "items": parsed,
        "raw_primary": primary["text"],
        "raw_escalated": raw_escalated,
        "stats": stats,
    }


# --- Adaptadores para reuso em discovery/new_wines ---

def to_discovery_enriched(parsed: dict[str, Any]) -> dict[str, Any] | None:
    """Converte item v3 para o formato esperado por `_second_resolve`.

    Retorna None se o item nao for vinho (spirit/not_wine/unknown).
    """
    if parsed.get("kind") != "wine":
        return None
    country_code = parsed.get("country_code")
    return {
        "name": parsed.get("full_name") or parsed.get("wine_name"),
        "producer": parsed.get("producer"),
        "country": _iso_to_en(country_code),
        "region": parsed.get("region"),
        "grape": parsed.get("grape"),
    }


def to_auto_create_enriched(parsed: dict[str, Any]) -> dict[str, Any]:
    """Converte item v3 para o formato esperado por `_insert_or_get_wine`.

    O modulo `new_wines` espera chaves: kind, full_name, producer, wine_name,
    country_code, style, grape, region, sub_region, vintage, abv, classification,
    body, pairing, sweetness, estimated_note, confidence.
    """
    kind = parsed.get("kind", "unknown")
    confidence = _confidence_from_parsed(parsed)
    return {
        "index": parsed.get("index"),
        "kind": kind,
        "full_name": parsed.get("full_name"),
        "producer": parsed.get("producer"),
        "wine_name": parsed.get("wine_name"),
        "country_code": (parsed.get("country_code") or "").upper() or None,
        "style": parsed.get("style"),
        "grape": parsed.get("grape"),
        "region": parsed.get("region"),
        "sub_region": parsed.get("sub_region"),
        "vintage": parsed.get("vintage"),
        "abv": parsed.get("abv"),
        "classification": parsed.get("classification"),
        "body": parsed.get("body"),
        "pairing": parsed.get("pairing"),
        "sweetness": parsed.get("sweetness"),
        # nota conservadora: v3 NAO devolve nota; mantemos None.
        "estimated_note": None,
        "confidence": confidence,
        "duplicate_of": parsed.get("duplicate_of"),
        "source_model": parsed.get("source_model"),
        "escalated": parsed.get("escalated", False),
    }


def _confidence_from_parsed(parsed: dict[str, Any]) -> float | None:
    """Sinal derivado: v3 nao emite numero de confianca, entao derivamos
    um valor conservador baseado em campos-chave presentes."""
    if parsed.get("kind") != "wine":
        return None
    producer = parsed.get("producer")
    wine = parsed.get("wine_name")
    if not producer or not wine:
        return 0.6
    country = parsed.get("country_code")
    region = parsed.get("region")
    if country and region:
        return 0.9
    if country or region:
        return 0.8
    return 0.75
