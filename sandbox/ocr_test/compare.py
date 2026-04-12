"""Sandbox de comparacao de modelos de visao para fotos de prateleira de vinhos.

Roda o mesmo prompt (copiado de backend/tools/media.py) em varios modelos
e salva os resultados lado a lado.

ZERO impacto em producao: nao importa nada de backend/.

Uso:
    python compare.py                    # roda todos os modelos disponiveis
    python compare.py --only gemini      # so o gemini
    python compare.py --only qwen        # so os qwen
    python compare.py --photos 3,5,7     # fotos especificas (default: 3,5,7)
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# .env local do sandbox tem prioridade; cai no backend/.env como fallback
SANDBOX_DIR = Path(__file__).parent
load_dotenv(SANDBOX_DIR / ".env")
load_dotenv(Path(r"C:\winegod-app\backend\.env"))

PHOTOS_DIR = Path(r"C:\winegod\fotos-vinhos-testes")
RESULTS_DIR = SANDBOX_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Prompt — copia EXATA do IMAGE_UNIFIED_PROMPT em backend/tools/media.py
# Mantenha sincronizado manualmente para garantir comparacao justa.
# ---------------------------------------------------------------------------
IMAGE_UNIFIED_PROMPT = """You are a wine-image analyst. Classify this image as ONE of:

## Classification rules

"label" — One wine or SKU DOMINATES the scene visually. The label/bottle occupies most of the frame.
  - Use "label" even if there are 2-5 copies of the SAME wine side by side (e.g. supermarket facing).
  - Use "label" if one wine is clearly the main subject and background bottles are blurry or secondary.
  - Do NOT require a single isolated bottle. Visual dominance is the criterion, not bottle count.

"screenshot" — A screen capture or digital interface showing wine information (app, website, price list, search results).

"shelf" — A photo showing MULTIPLE DIFFERENT wines together on a shelf, display, rack, or table where no single wine dominates the frame.

"not_wine" — The image does not contain wine-related content.

## Output schemas (return ONLY valid JSON, no extra text)

If type is "label":
{"type": "label", "name": "full wine name", "producer": "winery or null", "vintage": "year or null", "region": "region or null", "grape": "grape variety or null", "price": "price with currency or null"}

If type is "screenshot":
{"type": "screenshot", "wines": [{"name": "wine name", "producer": "winery or null", "price": "price or null", "rating": "rating or null", "source": "app/site name or null"}]}

If type is "shelf":
{"type": "shelf", "wines": [{"name": "full wine name as read", "producer": "winery or null", "line": "wine line/range or null", "variety": "grape variety or null", "classification": "Reserva/Gran Reserva/etc or null", "style": "red/white/rosé/sparkling or null", "price": "price or null"}], "total_visible": 0}

If type is "not_wine":
{"type": "not_wine", "description": "brief description of what the image shows"}

## Price rules (CRITICAL for Brazilian supermarket labels)
Brazilian shelf price tags often show multiple values:
  - "PRECO R$T 1 L R$146.60" = price per liter — IGNORE this
  - "R$ 189,99" (larger, usually at bottom) = unit price of the bottle — USE THIS
  - Always extract the UNIT PRICE of the bottle (typically 750ml), never the per-liter price
  - If multiple price values are visible for the same wine, pick the one labeled as the bottle/unit price
  - If unsure which price is the unit price, return null rather than guessing
  - Preserve the original currency symbol (R$, $, €, etc.)

## Name cleanup rules
  - Use the FULL wine name as printed on the label, not abbreviated
  - Fix obvious OCR artifacts: if a letter is clearly wrong based on context, correct it
    (e.g. "PONTGRAS" on a Chilean wine shelf is almost certainly "MONTGRAS")
  - Include winery + wine line + variety when visible (e.g. "MontGras Aura Reserva Cabernet Sauvignon")
  - Do NOT invent or guess parts of the name you cannot read — use what is legible
  - Separate winery (producer) from wine name when both are clearly distinct on the label

## Grape variety rules
  - Only report grape varieties you can CLEARLY read on the label
  - If partially obscured or ambiguous, return null rather than guessing
  - Common confusions to avoid: Petit Verdot vs Petit Sirah, Grenache vs Garnacha (same grape, both acceptable), Syrah vs Shiraz (same grape, both acceptable)
  - If you see only 2-3 letters of a grape name, return null

## Shelf and screenshot producer rules
  - For each wine, extract "producer" (winery) separately when clearly visible
  - Keep the FULL wine name in "name" including winery prefix if that is how it reads (e.g. name: "MontGras Reserva Cabernet", producer: "MontGras")
  - Use null for producer if not legible — do NOT guess or infer from the wine name

## Shelf-specific rules
  - "wines" list: include only wines whose names you can confidently read
  - Deduplicate: if the same wine appears multiple times on the shelf, list it only ONCE
  - "total_visible": estimate the number of DISTINCT wine labels/SKUs visible (not total physical bottles). 10 copies of the same wine = 1 SKU. Be conservative — when uncertain, estimate lower.
  - For each wine in the list, extract price if a price tag is clearly associated with it

## Shelf structured fields (for each wine)
  - "name": keep the FULL wine name as printed (winery + line + variety + classification). This is the primary field — always fill it.
  - "line": the wine LINE or RANGE within the producer. Examples: "Aura" in "MontGras Aura Reserva Carmenere", "Family Wines" in "Casa Silva Family Wines Cabernet Sauvignon", "Day One" in "MontGras Day One Carmenere". Use null if not identifiable or if the wine has no distinct line name.
  - "variety": grape variety when clearly readable (e.g. "Carmenere", "Cabernet Sauvignon", "Merlot", "Chardonnay"). Use null if not visible.
  - "classification": quality tier when visible (e.g. "Reserva", "Gran Reserva", "Crianza"). Use null if not visible.
  - "style": overall wine style — use exactly one of: "red", "white", "rosé", "sparkling". Use null if not determinable from the label.
  - Do NOT guess or infer structured fields from context — only extract what you can clearly read.

## General rules
  - Always use null for fields you truly cannot determine
  - Return ONLY valid parseable JSON — no markdown, no commentary, no extra text
  - Do not wrap JSON in code fences"""


# ---------------------------------------------------------------------------
# Modelos a comparar (ordem: mais barato -> mais caro)
# ---------------------------------------------------------------------------
QWEN_MODELS = [
    {"id": "qwen-vl-ocr",            "in_per_1m": 0.07, "out_per_1m": 0.16},
    {"id": "qwen3-vl-flash",         "in_per_1m": 0.05, "out_per_1m": 0.40},
    {"id": "qwen3-vl-32b-instruct",  "in_per_1m": 0.16, "out_per_1m": 0.64},
    {"id": "qwen3-vl-plus",          "in_per_1m": 0.20, "out_per_1m": 1.60},
    {"id": "qwen3.6-plus",           "in_per_1m": 0.50, "out_per_1m": 3.00},
]

GEMINI_MODEL = {"id": "gemini-2.5-flash", "in_per_1m": 0.30, "out_per_1m": 2.50}


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
def run_gemini(image_path: Path) -> dict:
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set"}

    client = genai.Client(api_key=api_key)
    image_bytes = image_path.read_bytes()

    t0 = time.time()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL["id"],
            contents=[
                {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_bytes).decode()}},
                IMAGE_UNIFIED_PROMPT,
            ],
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        text = response.text
        usage = getattr(response, "usage_metadata", None)
        in_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        out_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
        return {
            "raw_text": text,
            "parsed": _try_parse_json(text),
            "elapsed_ms": elapsed_ms,
            "in_tokens": in_tokens,
            "out_tokens": out_tokens,
            "cost_usd": _cost(in_tokens, out_tokens, GEMINI_MODEL),
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "elapsed_ms": int((time.time() - t0) * 1000)}


def run_qwen(image_path: Path, model_info: dict) -> dict:
    from openai import OpenAI

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return {"error": "DASHSCOPE_API_KEY not set"}

    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)

    image_b64 = base64.b64encode(image_path.read_bytes()).decode()
    data_url = f"data:image/jpeg;base64,{image_b64}"

    t0 = time.time()
    try:
        response = client.chat.completions.create(
            model=model_info["id"],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": IMAGE_UNIFIED_PROMPT},
                    ],
                }
            ],
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        text = response.choices[0].message.content or ""
        usage = response.usage
        in_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        out_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        return {
            "raw_text": text,
            "parsed": _try_parse_json(text),
            "elapsed_ms": elapsed_ms,
            "in_tokens": in_tokens,
            "out_tokens": out_tokens,
            "cost_usd": _cost(in_tokens, out_tokens, model_info),
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "elapsed_ms": int((time.time() - t0) * 1000)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _try_parse_json(text: str):
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def _cost(in_tokens: int, out_tokens: int, model_info: dict) -> float:
    return round(
        (in_tokens / 1_000_000) * model_info["in_per_1m"]
        + (out_tokens / 1_000_000) * model_info["out_per_1m"],
        6,
    )


def _short_summary(parsed) -> str:
    if not parsed:
        return "(parse failed)"
    t = parsed.get("type", "?")
    if t == "label":
        return f"label: {parsed.get('name', '?')}"
    if t == "shelf":
        wines = parsed.get("wines", [])
        return f"shelf: {len(wines)} wines, total_visible={parsed.get('total_visible', '?')}"
    if t == "screenshot":
        return f"screenshot: {len(parsed.get('wines', []))} wines"
    return t


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--photos", default="3,5,7", help="Numeros das fotos (ex: 3,5,7)")
    parser.add_argument("--only", choices=["gemini", "qwen", "all"], default="all")
    args = parser.parse_args()

    photo_nums = [p.strip() for p in args.photos.split(",")]
    photos = []
    for n in photo_nums:
        p = PHOTOS_DIR / f"{n}.jpeg"
        if not p.exists():
            print(f"[ERRO] Foto nao encontrada: {p}")
            sys.exit(1)
        photos.append(p)

    print(f"\nFotos: {[p.name for p in photos]}")
    print(f"Modo: {args.only}\n")

    results = {}  # results[photo_name][model_id] = result_dict

    for photo in photos:
        print(f"\n{'='*60}\nFoto: {photo.name}\n{'='*60}")
        results[photo.name] = {}

        if args.only in ("gemini", "all"):
            print(f"  -> {GEMINI_MODEL['id']}...", end=" ", flush=True)
            r = run_gemini(photo)
            results[photo.name][GEMINI_MODEL["id"]] = r
            if "error" in r:
                print(f"ERRO: {r['error']}")
            else:
                print(f"{r['elapsed_ms']}ms ${r['cost_usd']:.4f} | {_short_summary(r['parsed'])}")

        if args.only in ("qwen", "all"):
            for model_info in QWEN_MODELS:
                print(f"  -> {model_info['id']}...", end=" ", flush=True)
                r = run_qwen(photo, model_info)
                results[photo.name][model_info["id"]] = r
                if "error" in r:
                    print(f"ERRO: {r['error']}")
                else:
                    print(f"{r['elapsed_ms']}ms ${r['cost_usd']:.4f} | {_short_summary(r['parsed'])}")

    # Salva JSON completo
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = RESULTS_DIR / f"results_{timestamp}.json"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[OK] JSON salvo em {json_path}")

    # Gera markdown comparativo
    md_path = RESULTS_DIR / f"comparison_{timestamp}.md"
    _write_markdown(results, md_path)
    print(f"[OK] Markdown salvo em {md_path}")


def _write_markdown(results: dict, path: Path):
    lines = ["# Comparacao de modelos OCR — fotos de vinhos\n"]
    lines.append(f"Gerado em {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    for photo_name, models in results.items():
        lines.append(f"## {photo_name}\n\n")
        lines.append("| Modelo | Latencia | Custo | Tipo | Resumo |\n")
        lines.append("|---|---|---|---|---|\n")
        for model_id, r in models.items():
            if "error" in r:
                lines.append(f"| {model_id} | {r.get('elapsed_ms', '-')}ms | - | ERRO | {r['error']} |\n")
                continue
            parsed = r.get("parsed") or {}
            t = parsed.get("type", "?")
            summary = _short_summary(parsed).replace("|", "\\|")
            lines.append(f"| {model_id} | {r['elapsed_ms']}ms | ${r['cost_usd']:.4f} | {t} | {summary} |\n")
        lines.append("\n")

        # Detalhes por modelo
        for model_id, r in models.items():
            lines.append(f"### {photo_name} — {model_id}\n\n")
            if "error" in r:
                lines.append(f"```\nERRO: {r['error']}\n```\n\n")
                continue
            parsed = r.get("parsed")
            if parsed:
                lines.append("```json\n")
                lines.append(json.dumps(parsed, indent=2, ensure_ascii=False))
                lines.append("\n```\n\n")
            else:
                lines.append("Parse falhou. Raw output:\n\n```\n")
                lines.append((r.get("raw_text") or "")[:2000])
                lines.append("\n```\n\n")

    path.write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
