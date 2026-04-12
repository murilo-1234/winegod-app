"""Fase 2 — qwen3-vl-flash only, 10 fotos, 8 tecnicas de preprocessing/prompt.

Objetivo: mapear teto real de qualidade do flash em cenarios variados.
Fotos ordenadas por dificuldade crescente.
Ground truth gerado por Gemini 2.5 Flash + thinking.
"""

import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageEnhance, ImageFilter

sys.stdout.reconfigure(encoding="utf-8")

SANDBOX_DIR = Path(__file__).parent
load_dotenv(SANDBOX_DIR / ".env")
load_dotenv(Path(r"C:\winegod-app\backend\.env"))

PHOTOS_DIR = Path(r"C:\winegod\fotos-vinhos-testes")
PHOTO_NUMS = [9, 10, 15, 14, 24, 11, 8, 19, 7, 18]
MODEL = "qwen3-vl-flash"
IN_PRICE = 0.05
OUT_PRICE = 0.40

GT_PATH = SANDBOX_DIR / "results" / "ground_truth_10photos.json"
GT = json.loads(GT_PATH.read_text(encoding="utf-8"))


def get_client():
    return OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    )


CLIENT = get_client()


# ===========================================================================
# Scoring — fuzzy match flash output vs ground truth
# ===========================================================================
def normalize(s):
    import re
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\b(vinho|tinto|branco|tto|rose|750ml)\b", "", s)
    return " ".join(s.split())


def fuzzy_match_names(flash_names, gt_names):
    """Retorna (hits, matched_gt, unmatched_flash)."""
    gt_norm = [(normalize(n), n) for n in gt_names]
    matched_gt = set()
    unmatched = []
    for fn in flash_names:
        fn_norm = normalize(fn)
        if not fn_norm:
            continue
        best_sim = 0
        best_idx = -1
        for i, (gn, _) in enumerate(gt_norm):
            if i in matched_gt:
                continue
            # Token overlap ratio
            ft = set(fn_norm.split())
            gt_t = set(gn.split())
            if not ft or not gt_t:
                continue
            overlap = len(ft & gt_t)
            ratio = overlap / max(len(ft), len(gt_t))
            if ratio > best_sim:
                best_sim = ratio
                best_idx = i
        if best_sim >= 0.4 and best_idx >= 0:
            matched_gt.add(best_idx)
        else:
            unmatched.append(fn)
    return len(matched_gt), [gt_names[i] for i in matched_gt], unmatched


# ===========================================================================
# Prompt variants
# ===========================================================================
PROMPT_EN = """You are a wine-image analyst. Classify this image as ONE of: label, shelf, screenshot, not_wine.

If shelf: return JSON
{"type":"shelf","wines":[{"name":"...","producer":"...","line":"...","variety":"...","classification":"...","style":"red|white|rose|sparkling","price":"..."}],"total_visible":N}

Rules:
- Use full wine name as on the BOTTLE label (strip shelf-tag prefixes like "VINHO TTO", "750ML")
- Deduplicate same SKU
- UNIT price only (ignore per-liter)
- null for unknown fields
- Return ONLY JSON, no markdown, no fences

## MANDATORY PROCESS (internal, output only final JSON)
1. Count DISTINCT wine labels visible (different SKUs)
2. Scan LEFT to RIGHT, TOP to BOTTOM
3. Find price tag for each wine
4. Verify list matches count
5. If not matching, re-scan

## ANTI-HALLUCINATION
If you cannot clearly read a name, OMIT it. Never invent."""


PROMPT_PTBR = """Voce e um analista de imagens de vinho. Classifique esta imagem como: label, shelf, screenshot ou not_wine.

Para shelf retorne SOMENTE JSON valido neste formato:
{"type":"shelf","wines":[{"name":"nome completo do vinho","producer":"vinicola ou null","line":"linha ou null","variety":"uva ou null","classification":"reserva/gran reserva ou null","style":"red|white|rose|sparkling","price":"preco ou null"}],"total_visible":N}

Regras obrigatorias:
- Use o nome COMPLETO do vinho como impresso no ROTULO DA GARRAFA
- Remova prefixos de etiqueta de prateleira: "VINHO TTO", "VINHO TINTO", "V. TTO", "750ML"
- NAO duplique o mesmo vinho
- Preco UNITARIO da garrafa (ignore preco por litro)
- null para campos que voce nao consegue ler
- Retorne SOMENTE JSON puro, sem markdown, sem comentario

## PROCESSO OBRIGATORIO (interno — so retorne o JSON final)
1. Conte quantos rotulos DIFERENTES de vinho estao visiveis (SKUs distintos, nao garrafas)
2. Varra da ESQUERDA pra DIREITA, de CIMA pra BAIXO
3. Para cada vinho encontre a etiqueta de preco mais proxima
4. Confira que a quantidade de vinhos na lista bate com a contagem do passo 1
5. Se nao bater, varra novamente

## ANTI-ALUCINACAO
Se voce NAO consegue ler claramente o nome de um vinho, OMITA. Nunca invente."""


PROMPT_PTBR_PRIMED = """Voce e um auditor especializado em prateleiras de vinhos em supermercados BRASILEIROS.
As etiquetas de preco estao em R$ (reais brasileiros). O formato tipico e "R$ XX,XX" na etiqueta abaixo ou ao lado da garrafa.
Os vinhos podem ser de qualquer pais mas os precos sao sempre em reais.

""" + PROMPT_PTBR


# ===========================================================================
# Image preprocessing functions
# ===========================================================================
def preprocess_basic(img_pil):
    """Fase 1 winner: contrast +20% + sharpen."""
    img = ImageEnhance.Contrast(img_pil).enhance(1.2)
    return img.filter(ImageFilter.SHARPEN)


def preprocess_clahe(img_pil):
    """CLAHE real via OpenCV."""
    arr = np.array(img_pil)
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    result = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    return Image.fromarray(result)


def preprocess_upscale(img_pil):
    """Upscale 2x via Lanczos."""
    w, h = img_pil.size
    return img_pil.resize((w * 2, h * 2), Image.LANCZOS)


def preprocess_sharp_forte(img_pil):
    """UnsharpMask forte."""
    return img_pil.filter(ImageFilter.UnsharpMask(radius=3, percent=200, threshold=2))


def preprocess_combo(img_pil):
    """CLAHE + upscale 1.5x + sharpen forte + contrast."""
    # CLAHE
    arr = np.array(img_pil)
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    result = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    img = Image.fromarray(result)
    # Upscale 1.5x
    w, h = img.size
    img = img.resize((int(w * 1.5), int(h * 1.5)), Image.LANCZOS)
    # Sharpen
    img = img.filter(ImageFilter.UnsharpMask(radius=3, percent=150, threshold=2))
    # Contrast
    img = ImageEnhance.Contrast(img).enhance(1.15)
    return img


def pil_to_b64(img_pil, quality=95):
    buf = io.BytesIO()
    img_pil.save(buf, "JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


# ===========================================================================
# Techniques
# ===========================================================================
TECHNIQUES = []


def tech(name, desc):
    def dec(fn):
        TECHNIQUES.append({"name": name, "desc": desc, "fn": fn})
        return fn
    return dec


@tech("T1_baseline", "Prompt EN, imagem original")
def t1(photo_num):
    img = Image.open(PHOTOS_DIR / f"{photo_num}.jpeg")
    b64 = pil_to_b64(img)
    return _call(b64, PROMPT_EN)


@tech("T2_preproc_basic", "Contrast+sharpen (winner fase1)")
def t2(photo_num):
    img = preprocess_basic(Image.open(PHOTOS_DIR / f"{photo_num}.jpeg"))
    b64 = pil_to_b64(img)
    return _call(b64, PROMPT_EN)


@tech("T3_clahe", "CLAHE real (OpenCV adaptive histogram)")
def t3(photo_num):
    img = preprocess_clahe(Image.open(PHOTOS_DIR / f"{photo_num}.jpeg"))
    b64 = pil_to_b64(img)
    return _call(b64, PROMPT_EN)


@tech("T4_upscale2x", "Upscale 2x Lanczos")
def t4(photo_num):
    img = preprocess_upscale(Image.open(PHOTOS_DIR / f"{photo_num}.jpeg"))
    b64 = pil_to_b64(img)
    return _call(b64, PROMPT_EN)


@tech("T5_sharp_forte", "UnsharpMask forte (radius=3, 200%)")
def t5(photo_num):
    img = preprocess_sharp_forte(Image.open(PHOTOS_DIR / f"{photo_num}.jpeg"))
    b64 = pil_to_b64(img)
    return _call(b64, PROMPT_EN)


@tech("T6_prompt_ptbr", "Prompt em PT-BR")
def t6(photo_num):
    img = Image.open(PHOTOS_DIR / f"{photo_num}.jpeg")
    b64 = pil_to_b64(img)
    return _call(b64, PROMPT_PTBR)


@tech("T7_ptbr_primed", "Prompt PT-BR + priming supermercado BR")
def t7(photo_num):
    img = Image.open(PHOTOS_DIR / f"{photo_num}.jpeg")
    b64 = pil_to_b64(img)
    return _call(b64, PROMPT_PTBR_PRIMED)


@tech("T8_combo_max", "CLAHE+upscale1.5+sharp+contrast + PT-BR primed + hi-res")
def t8(photo_num):
    img = preprocess_combo(Image.open(PHOTOS_DIR / f"{photo_num}.jpeg"))
    b64 = pil_to_b64(img)
    return _call(b64, PROMPT_PTBR_PRIMED)


def _call(b64, prompt):
    msgs = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text", "text": prompt},
    ]}]
    t0 = time.time()
    resp = CLIENT.chat.completions.create(
        model=MODEL,
        messages=msgs,
        temperature=0.0,
        extra_body={"vl_high_resolution_images": True},
    )
    elapsed = int((time.time() - t0) * 1000)
    u = resp.usage
    return {
        "content": resp.choices[0].message.content or "",
        "elapsed_ms": elapsed,
        "in_tokens": u.prompt_tokens,
        "out_tokens": u.completion_tokens,
        "cost": (u.prompt_tokens / 1e6) * IN_PRICE + (u.completion_tokens / 1e6) * OUT_PRICE,
    }


def parse_json(text):
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(s)
    except Exception:
        return None


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    results = []
    print(f"Fase 2: {len(TECHNIQUES)} tecnicas x {len(PHOTO_NUMS)} fotos = {len(TECHNIQUES)*len(PHOTO_NUMS)} runs\n")

    for photo_num in PHOTO_NUMS:
        gt_data = GT.get(str(photo_num), {})
        gt_names = gt_data.get("wine_names", [])
        gt_count = len(gt_names)
        print(f"\n{'='*72}")
        print(f"FOTO {photo_num}.jpeg — ground truth: {gt_count} vinhos")
        print(f"{'='*72}")

        for tech_info in TECHNIQUES:
            tname = tech_info["name"]
            print(f"  [{tname}]... ", end="", flush=True)
            try:
                r = tech_info["fn"](photo_num)
                parsed = parse_json(r["content"])
                flash_names = [w.get("name", "") for w in (parsed or {}).get("wines", [])]
                hits, matched, unmatched = fuzzy_match_names(flash_names, gt_names)
                pct = int(hits / gt_count * 100) if gt_count > 0 else 0
                print(f"{hits}/{gt_count} ({pct}%) | total={len(flash_names)} | {r['elapsed_ms']}ms | ${r['cost']:.4f}")
                results.append({
                    "photo": photo_num,
                    "technique": tname,
                    "gt_count": gt_count,
                    "hits": hits,
                    "pct": pct,
                    "flash_total": len(flash_names),
                    "flash_names": flash_names,
                    "matched_gt": matched,
                    "unmatched_flash": unmatched,
                    "elapsed_ms": r["elapsed_ms"],
                    "cost": r["cost"],
                })
            except Exception as e:
                print(f"ERRO: {type(e).__name__}: {str(e)[:150]}")
                results.append({"photo": photo_num, "technique": tname, "error": str(e)[:200]})

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = SANDBOX_DIR / "results" / f"phase2_{timestamp}.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nJSON: {out_path}")

    # Tabela resumo por tecnica (media de acerto)
    print(f"\n{'='*80}")
    print("RESUMO POR TECNICA (media de acerto em 10 fotos)")
    print(f"{'='*80}")
    from collections import defaultdict
    tech_stats = defaultdict(list)
    for r in results:
        if "error" not in r:
            tech_stats[r["technique"]].append(r["pct"])
    for tname, pcts in sorted(tech_stats.items(), key=lambda x: -sum(x[1]) / len(x[1])):
        avg = sum(pcts) / len(pcts)
        print(f"  {tname:<22} media={avg:.0f}%  {pcts}")

    # Tabela resumo por foto (melhor tecnica)
    print(f"\n{'='*80}")
    print("MELHOR TECNICA POR FOTO")
    print(f"{'='*80}")
    from itertools import groupby
    by_photo = defaultdict(list)
    for r in results:
        if "error" not in r:
            by_photo[r["photo"]].append(r)
    for pnum in PHOTO_NUMS:
        rows = by_photo.get(pnum, [])
        if not rows:
            continue
        best = max(rows, key=lambda x: (x["hits"], -x["elapsed_ms"]))
        print(f"  {pnum}.jpeg: {best['hits']}/{best['gt_count']} ({best['pct']}%) — {best['technique']}")


if __name__ == "__main__":
    main()
