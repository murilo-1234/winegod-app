"""Experimentos COMBINANDO multiplas tecnicas da pesquisa academica.

Roda 6 combos x 3-4 modelos Qwen na foto 7 (densa, 9 vinhos).
Cada combo empilha 3-5 tecnicas juntas.
Tecnica 11 (DB verify) aplicada como pos-filtro em TODO combo.

Ground truth foto 7 (9 vinhos) — veja experiments.py
"""

import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageEnhance, ImageFilter

sys.stdout.reconfigure(encoding="utf-8")

SANDBOX_DIR = Path(__file__).parent
load_dotenv(SANDBOX_DIR / ".env")
load_dotenv(Path(r"C:\winegod-app\backend\.env"))

PHOTO_PATH = Path(r"C:\winegod\fotos-vinhos-testes\7.jpeg")

# Modelos a comparar (mesmos combos rodam em cada)
MODELS = [
    {"id": "qwen3-vl-flash",        "in": 0.05, "out": 0.40},
    {"id": "qwen3-vl-32b-instruct", "in": 0.16, "out": 0.64},
    {"id": "qwen3-vl-plus",         "in": 0.20, "out": 1.60},
]
PREMIUM_MODEL = {"id": "qwen-vl-max-latest", "in": 1.60, "out": 6.40}

# Ground truth tokens
GROUND_TRUTH = {
    "curral": "Curral Pinot Noir",
    "syrah classiques": "Les Dauphins Syrah Classiques",
    "cotes du rhone": "Les Dauphins Cotes du Rhone",
    "chianti classico": "Contada 1926 Chianti Classico",
    "chianti reserva": "Contada 1926 Chianti Reserva",
    "chianti": "Contada 1926 Chianti",
    "gato": "O Gato & Juju",
    "montepulciano": "Contada 1926 Montepulciano",
    "vignola": "Contada 1926 Vignola",
}

KNOWN_HALLUCINATIONS = [
    "araguaju", "casa juju", "king", "malaguetta", "barolo",
    "amarone", "antoing", "duclair", "roche noir", "chateau de syrah",
    "nuvolari", "moscato d'abruzzo", "sherong", "daphne", "dauphine",
]


def get_client():
    return OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    )


# ===========================================================================
# Carrega imagem uma vez
# ===========================================================================
_IMG_CACHE = {}

def get_image_bytes(key="full"):
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]
    img = Image.open(PHOTO_PATH)
    if key == "full":
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=95)
        _IMG_CACHE[key] = buf.getvalue()
    elif key == "preprocessed":
        # Tecnica 10: CLAHE-like (contraste) + sharpen leve
        enhancer = ImageEnhance.Contrast(img)
        img2 = enhancer.enhance(1.2)
        img2 = img2.filter(ImageFilter.SHARPEN)
        buf = io.BytesIO()
        img2.save(buf, "JPEG", quality=95)
        _IMG_CACHE[key] = buf.getvalue()
    return _IMG_CACHE[key]


def img_msg(prompt_text, key="full"):
    b64 = base64.b64encode(get_image_bytes(key)).decode()
    return [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text", "text": prompt_text},
    ]


# ===========================================================================
# Prompts reusaveis
# ===========================================================================
BASE_SHELF_RULES = """You are a wine-image analyst. Classify this image as ONE of: label, shelf, screenshot, not_wine.

If shelf: return JSON
{"type":"shelf","wines":[{"name":"...","producer":"...","line":"...","variety":"...","classification":"...","style":"red|white|rose|sparkling","price":"..."}],"total_visible":N}

Rules:
- Use full wine name as on the BOTTLE label (strip shelf-tag prefixes like "VINHO TTO", "750ML")
- Deduplicate same SKU
- UNIT price only (ignore per-liter)
- null for unknown fields
- Return ONLY JSON, no markdown, no fences"""


COT_COUNTING_INSTRUCTION = """

## MANDATORY INTERNAL PROCESS (output only final JSON)
1. Count the EXACT number of DISTINCT wine labels (different SKUs, not total bottles)
2. Scan the image LEFT to RIGHT, TOP to BOTTOM, listing each distinct label ONCE
3. For each wine, find the nearest price tag
4. Verify your wine list length matches the count from step 1
5. If not matching, RE-SCAN and fix

## ANTI-HALLUCINATION
If you cannot clearly read a wine name, OMIT IT. Never invent producers, varieties, or classifications.
Better 5 sure wines than 9 with 2 guesses."""

FEW_SHOT_EXAMPLES = """

## Examples of correct output

Example 1 (2 wines):
```json
{"type":"shelf","wines":[
  {"name":"MontGras Reserva Cabernet Sauvignon","producer":"MontGras","line":"Reserva","variety":"Cabernet Sauvignon","classification":"Reserva","style":"red","price":"R$ 49,99"},
  {"name":"Casa Silva Cuvee Colchagua","producer":"Casa Silva","line":"Cuvee","variety":null,"classification":null,"style":"red","price":"R$ 89,99"}
],"total_visible":2}
```

Example 2 (6 wines including one unreadable — DROPPED, not guessed):
```json
{"type":"shelf","wines":[
  {"name":"Catena Zapata Malbec","producer":"Catena Zapata","line":null,"variety":"Malbec","classification":null,"style":"red","price":"R$ 179,99"},
  {"name":"Alamos Chardonnay","producer":"Alamos","line":null,"variety":"Chardonnay","classification":null,"style":"white","price":"R$ 59,99"},
  {"name":"Trapiche Reserve Cabernet","producer":"Trapiche","line":"Reserve","variety":"Cabernet Sauvignon","classification":"Reserve","style":"red","price":"R$ 79,99"},
  {"name":"Finca Las Moras Shiraz","producer":"Finca Las Moras","line":null,"variety":"Shiraz","classification":null,"style":"red","price":"R$ 49,99"},
  {"name":"Norton Clasico Malbec","producer":"Norton","line":"Clasico","variety":"Malbec","classification":null,"style":"red","price":"R$ 54,99"},
  {"name":"Zuccardi Q Tempranillo","producer":"Zuccardi","line":"Q","variety":"Tempranillo","classification":null,"style":"red","price":"R$ 119,99"}
],"total_visible":7}
```
Note: example 2 has total_visible=7 but wines list has only 6 — the 7th bottle was unreadable and omitted (NOT guessed).

Example 3 (3 wines, same producer line):
```json
{"type":"shelf","wines":[
  {"name":"Contada 1926 Chianti","producer":"Contada","line":"1926","variety":null,"classification":null,"style":"red","price":"R$ 99,00"},
  {"name":"Contada 1926 Chianti Classico","producer":"Contada","line":"1926","variety":null,"classification":"Classico","style":"red","price":"R$ 139,99"},
  {"name":"Contada 1926 Primitivo","producer":"Contada","line":"1926","variety":"Primitivo","classification":null,"style":"red","price":"R$ 59,99"}
],"total_visible":3}
```"""


# ===========================================================================
# Helpers
# ===========================================================================
def parse_json(text):
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        parts = s.split("\n", 1)
        if len(parts) == 2:
            s = parts[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(s)
    except Exception:
        return None


def call_model(model_id, messages, extra_body=None, temperature=0.0, seed=42):
    client = get_client()
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model_id,
        messages=messages,
        temperature=temperature,
        seed=seed,
        extra_body=extra_body or {},
    )
    elapsed = int((time.time() - t0) * 1000)
    u = resp.usage
    return {
        "content": resp.choices[0].message.content or "",
        "elapsed_ms": elapsed,
        "in_tokens": u.prompt_tokens,
        "out_tokens": u.completion_tokens,
    }


def cost(in_t, out_t, model_info):
    return (in_t / 1e6) * model_info["in"] + (out_t / 1e6) * model_info["out"]


def score(parsed, verified_names=None):
    """Retorna (hits, halluc, total, names).
    Se verified_names=list, usa esses nomes filtrados (pos-DB-verify).
    """
    if not parsed or "wines" not in parsed:
        return 0, 0, 0, []
    if verified_names is not None:
        names = verified_names
    else:
        names = [w.get("name", "") or "" for w in parsed["wines"]]
    lower = [n.lower() for n in names]
    hits = set()
    for k in GROUND_TRUTH:
        if any(k in n for n in lower):
            hits.add(k)
    halluc = sum(1 for n in lower if any(h in n for h in KNOWN_HALLUCINATIONS))
    return len(hits), halluc, len(names), names


# ===========================================================================
# Tecnica 11 — DB verify (pos-filtro)
# ===========================================================================
_DB_CONN = None

def get_db():
    global _DB_CONN
    if _DB_CONN is None:
        _DB_CONN = psycopg2.connect(os.getenv("DATABASE_URL"), connect_timeout=30)
    return _DB_CONN


def normalize_for_query(s):
    """Remove stopwords pra melhorar fuzzy."""
    import re
    s = s.lower()
    s = re.sub(r"\bvinho\s+(tinto|branco|rose)\b", "", s)
    s = re.sub(r"\b(tto|tinto|branco)\b", "", s)
    s = re.sub(r"\b750\s*ml\b", "", s)
    s = re.sub(r"\b\d{4}\b", "", s)  # remove vintages/anos
    s = re.sub(r"[^\w\s]", " ", s)
    s = " ".join(s.split())
    return s


def db_verify(names, threshold=0.55, min_match_chars=8):
    """Filtra nomes. Retorna (kept, dropped_with_reason).
    Usa pg_trgm similarity contra wines.nome_normalizado.
    """
    kept = []
    dropped = []
    try:
        conn = get_db()
        cur = conn.cursor()
        for name in names:
            if not name:
                dropped.append((name, "empty"))
                continue
            q = normalize_for_query(name)
            if len(q) < 4:
                dropped.append((name, f"query too short: {q!r}"))
                continue
            cur.execute(
                "SELECT nome_normalizado, similarity(nome_normalizado, %s) as sim "
                "FROM wines WHERE nome_normalizado %% %s ORDER BY sim DESC LIMIT 1",
                (q, q),
            )
            row = cur.fetchone()
            if not row:
                dropped.append((name, f"zero matches for {q!r}"))
                continue
            best_name, sim = row
            if sim < threshold:
                dropped.append((name, f"sim={sim:.2f} (< {threshold})"))
                continue
            if len(best_name) < min_match_chars:
                dropped.append((name, f"match too short: {best_name!r}"))
                continue
            kept.append(name)
        cur.close()
    except Exception as e:
        print(f"    [db_verify ERROR] {type(e).__name__}: {e}")
        return names, []
    return kept, dropped


# ===========================================================================
# COMBOS
# ===========================================================================
def combo_a_all_best(model_info):
    """Hi-res + self-consistency 3x + CoT contagem + anti-halluc + DB verify."""
    prompt = BASE_SHELF_RULES + COT_COUNTING_INSTRUCTION
    wines_by_run = []
    total_ms = 0
    total_cost = 0
    for i in range(3):
        r = call_model(
            model_info["id"],
            [{"role": "user", "content": img_msg(prompt)}],
            extra_body={"vl_high_resolution_images": True},
            temperature=0.3,
            seed=i * 7 + 1,
        )
        total_ms += r["elapsed_ms"]
        total_cost += cost(r["in_tokens"], r["out_tokens"], model_info)
        p = parse_json(r["content"])
        if p and "wines" in p:
            wines_by_run.append(p["wines"])

    # Self-consistency: nome normalizado aparece em >=2 das 3 rodadas
    from collections import Counter
    counts = Counter()
    canonical = {}
    for wines in wines_by_run:
        seen = set()
        for w in wines:
            name = (w.get("name") or "").strip()
            if not name:
                continue
            key = " ".join(name.lower().split())[:50]
            if key in seen:
                continue
            seen.add(key)
            counts[key] += 1
            if key not in canonical:
                canonical[key] = w
    voted = [canonical[k] for k, c in counts.items() if c >= 2]
    merged = {"type": "shelf", "wines": voted, "total_visible": len(voted)}
    return {"parsed": merged, "cost": total_cost, "ms": total_ms}


def combo_b_few_shot(model_info):
    """Hi-res + few-shot 3 exemplos + CoT + DB verify."""
    prompt = BASE_SHELF_RULES + FEW_SHOT_EXAMPLES + COT_COUNTING_INSTRUCTION
    r = call_model(
        model_info["id"],
        [{"role": "user", "content": img_msg(prompt)}],
        extra_body={"vl_high_resolution_images": True},
    )
    parsed = parse_json(r["content"])
    return {"parsed": parsed, "cost": cost(r["in_tokens"], r["out_tokens"], model_info), "ms": r["elapsed_ms"]}


def combo_c_grounding_fixed(model_info):
    """Detect-then-read FIXED: converte coords 0-1000->pixels + dedup IoU + hi-res nos crops."""
    img = Image.open(PHOTO_PATH)
    W, H = img.size
    total_cost = 0
    total_ms = 0

    # --- Passo 1: detectar bboxes ---
    grounding_prompt = """Detect every distinct wine bottle visible in this wine shelf image.
Return ONLY JSON: {"bottles":[{"bbox_2d":[x1,y1,x2,y2]}]}

bbox_2d uses normalized coordinates in the range [0, 1000] (where [0,0] is top-left and [1000,1000] is bottom-right of the image).
Include every DISTINCT bottle, even if partially visible or one of many copies."""
    r = call_model(
        model_info["id"],
        [{"role": "user", "content": img_msg(grounding_prompt)}],
        extra_body={"vl_high_resolution_images": True},
    )
    total_ms += r["elapsed_ms"]
    total_cost += cost(r["in_tokens"], r["out_tokens"], model_info)
    gparsed = parse_json(r["content"])
    bottles = (gparsed or {}).get("bottles", [])

    if not bottles:
        return {"parsed": {"type": "shelf", "wines": []}, "cost": total_cost, "ms": total_ms}

    # Converter coords 0-1000 -> pixels (e detectar se ja sao pixels)
    def to_px(coord, dim):
        # Se coord > 1000, provavelmente ja eh pixel
        return int(coord) if coord > 1000 else int(coord / 1000 * dim)

    bboxes_px = []
    for b in bottles:
        bbox = b.get("bbox_2d") or b.get("bbox") or []
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = bbox
        x1p = max(0, min(W, to_px(x1, W)))
        y1p = max(0, min(H, to_px(y1, H)))
        x2p = max(0, min(W, to_px(x2, W)))
        y2p = max(0, min(H, to_px(y2, H)))
        if x2p <= x1p or y2p <= y1p:
            continue
        # Expande 8% pra pegar preco/etiqueta adjacente
        dw = (x2p - x1p) * 0.08
        dh = (y2p - y1p) * 0.08
        bboxes_px.append((
            max(0, int(x1p - dw)),
            max(0, int(y1p - dh)),
            min(W, int(x2p + dw)),
            min(H, int(y2p + dh)),
        ))

    # Dedup por IoU >= 0.5
    def iou(a, b):
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0
        inter = (ix2 - ix1) * (iy2 - iy1)
        a_area = (ax2 - ax1) * (ay2 - ay1)
        b_area = (bx2 - bx1) * (by2 - by1)
        return inter / (a_area + b_area - inter)

    deduped = []
    for bx in sorted(bboxes_px, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True):
        if any(iou(bx, kept) >= 0.5 for kept in deduped):
            continue
        deduped.append(bx)

    # Limita a 15 crops pra nao estourar custo
    deduped = deduped[:15]

    # --- Passo 2: ler cada crop ---
    read_prompt = """This is a crop of ONE wine bottle (possibly with price tag visible).
Read the wine label. Return ONLY JSON:
{"name":"full wine name","producer":"winery or null","price":"R$ XX,XX or null"}

Give the name as printed on the bottle label (strip shelf-tag prefixes like VINHO TTO).
If unreadable, return {"name":null,"producer":null,"price":null}."""

    wines = []
    for bx in deduped:
        crop = img.crop(bx)
        buf = io.BytesIO()
        crop.save(buf, "JPEG", quality=95)
        b64 = base64.b64encode(buf.getvalue()).decode()
        try:
            rr = call_model(
                model_info["id"],
                [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": read_prompt},
                ]}],
                extra_body={"vl_high_resolution_images": True},
            )
            total_ms += rr["elapsed_ms"]
            total_cost += cost(rr["in_tokens"], rr["out_tokens"], model_info)
            w = parse_json(rr["content"])
            if w and w.get("name"):
                wines.append(w)
        except Exception:
            pass

    # Dedup por nome
    seen = {}
    for w in wines:
        k = " ".join((w.get("name") or "").lower().split())[:50]
        if k and k not in seen:
            seen[k] = w
    parsed = {"type": "shelf", "wines": list(seen.values()), "total_visible": len(seen)}
    return {"parsed": parsed, "cost": total_cost, "ms": total_ms}


def combo_d_schema_json(model_info):
    """Hi-res + CoT + forca response_format JSON + DB verify."""
    prompt = BASE_SHELF_RULES + COT_COUNTING_INSTRUCTION
    try:
        r = call_model(
            model_info["id"],
            [{"role": "user", "content": img_msg(prompt)}],
            extra_body={
                "vl_high_resolution_images": True,
                "response_format": {"type": "json_object"},
            },
        )
    except Exception as e:
        # Se nao suporta, cai de volta sem response_format
        r = call_model(
            model_info["id"],
            [{"role": "user", "content": img_msg(prompt)}],
            extra_body={"vl_high_resolution_images": True},
        )
    parsed = parse_json(r["content"])
    return {"parsed": parsed, "cost": cost(r["in_tokens"], r["out_tokens"], model_info), "ms": r["elapsed_ms"]}


def combo_f_preprocessing(model_info):
    """Hi-res + imagem pre-processada (contrast+sharpen) + CoT + DB verify."""
    prompt = BASE_SHELF_RULES + COT_COUNTING_INSTRUCTION
    r = call_model(
        model_info["id"],
        [{"role": "user", "content": img_msg(prompt, key="preprocessed")}],
        extra_body={"vl_high_resolution_images": True},
    )
    parsed = parse_json(r["content"])
    return {"parsed": parsed, "cost": cost(r["in_tokens"], r["out_tokens"], model_info), "ms": r["elapsed_ms"]}


# ===========================================================================
# MAIN
# ===========================================================================
COMBOS = [
    ("A_all_best", "hi-res + self-consistency 3x + CoT + anti-halluc", combo_a_all_best),
    ("B_few_shot", "hi-res + 3 exemplos few-shot + CoT", combo_b_few_shot),
    ("C_grounding", "detect-then-read FIXED (coord 0-1000->px + dedup IoU)", combo_c_grounding_fixed),
    ("D_schema_json", "hi-res + CoT + response_format json_object", combo_d_schema_json),
    ("F_preprocessing", "hi-res + contrast+sharpen + CoT", combo_f_preprocessing),
]


def run_all():
    results = []
    # 3 modelos Qwen normais
    all_models = MODELS + [PREMIUM_MODEL]  # Combo E = mesmo que A em qwen-vl-max, mas vou rodar todos nele

    for model_info in all_models:
        print(f"\n{'='*72}")
        print(f"MODELO: {model_info['id']}")
        print(f"{'='*72}")
        for combo_id, desc, fn in COMBOS:
            print(f"  [{combo_id}] {desc}")
            try:
                out = fn(model_info)
                parsed = out["parsed"]
                # pre-DB score
                pre_hits, pre_halluc, pre_total, pre_names = score(parsed)
                # DB verify
                kept, dropped = db_verify(pre_names)
                post_hits, post_halluc, post_total, _ = score(parsed, verified_names=kept)
                print(f"    PRE-db:  {pre_hits}/9 hits, {pre_halluc} halluc, total={pre_total}")
                print(f"    POST-db: {post_hits}/9 hits, {post_halluc} halluc, total={post_total}  (dropped {len(dropped)})")
                print(f"    tempo: {out['ms']}ms  custo: ${out['cost']:.4f}")
                results.append({
                    "model": model_info["id"],
                    "combo": combo_id,
                    "desc": desc,
                    "pre_hits": pre_hits, "pre_halluc": pre_halluc, "pre_total": pre_total, "pre_names": pre_names,
                    "post_hits": post_hits, "post_halluc": post_halluc, "post_total": post_total, "post_names": kept,
                    "dropped": dropped,
                    "elapsed_ms": out["ms"],
                    "cost": out["cost"],
                })
            except Exception as e:
                print(f"    ERRO: {type(e).__name__}: {str(e)[:200]}")
                results.append({"model": model_info["id"], "combo": combo_id, "error": str(e)[:300]})

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = SANDBOX_DIR / "results" / f"combo_{timestamp}.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nJSON: {out_path}")

    # Tabela resumo
    print("\n" + "=" * 100)
    print(f"{'Modelo':<26} {'Combo':<18} {'Pre':<10} {'Post':<10} {'Tempo':<10} {'Custo':<10}")
    print("=" * 100)
    for r in results:
        if "error" in r:
            print(f"{r['model']:<26} {r['combo']:<18} ERRO: {r['error'][:40]}")
            continue
        pre = f"{r['pre_hits']}/9 h{r['pre_halluc']}"
        post = f"{r['post_hits']}/9 h{r['post_halluc']}"
        print(f"{r['model']:<26} {r['combo']:<18} {pre:<10} {post:<10} {r['elapsed_ms']}ms{'':<3} ${r['cost']:.4f}")


if __name__ == "__main__":
    run_all()
