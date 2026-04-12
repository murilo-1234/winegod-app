"""Experimentos de prompt engineering com qwen3-vl-flash na foto 7 (densa).

Testa 10+ tecnicas isoladas e mede: vinhos encontrados, acertos, alucinacoes,
latencia, tokens, custo.

Ground truth foto 7 (9 vinhos):
  1. Curral Pinot Noir - R$ 119,99
  2. Les Dauphins Syrah Classiques
  3. Les Dauphins Cotes du Rhone Reserve - R$ 76,99
  4. Contada 1926 Chianti
  5. Contada 1926 Chianti Classico - R$ 139,99
  6. Contada 1926 Chianti Reserva - R$ 99
  7. O Gato & Juju - R$ 69,99
  8. Contada 1926 Montepulciano d'Abruzzo - R$ 59
  9. Contada 1926 Vignola - R$ 59,99
"""

import base64
import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

SANDBOX_DIR = Path(__file__).parent
load_dotenv(SANDBOX_DIR / ".env")
load_dotenv(Path(r"C:\winegod-app\backend\.env"))

sys.stdout.reconfigure(encoding='utf-8')

PHOTO = Path(r"C:\winegod\fotos-vinhos-testes\7.jpeg")
MODEL = "qwen3-vl-flash"
IN_PRICE = 0.05
OUT_PRICE = 0.40

# Ground truth tokens (lowercase) para detectar acertos/alucinacoes
GROUND_TRUTH = {
    "curral": "Curral Pinot Noir",
    "syrah": "Les Dauphins Syrah",
    "cotes": "Les Dauphins Cotes du Rhone",
    "chianti classico": "Contada 1926 Chianti Classico",
    "chianti reserva": "Contada 1926 Chianti Reserva",
    "chianti": "Contada 1926 Chianti",
    "gato": "O Gato & Juju",
    "montepulciano": "Contada 1926 Montepulciano d'Abruzzo",
    "vignola": "Contada 1926 Vignola",
}

# Tokens que indicam ALUCINACAO (modelo inventou)
KNOWN_HALLUCINATIONS = [
    "araguaju", "casa juju", "king & juju", "malaguetta", "barolo",
    "amarone", "antoing", "duclair", "roche noir", "chateau de syrah",
]


def get_client():
    return OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    )


def encode_image():
    return base64.b64encode(PHOTO.read_bytes()).decode()


# --- O prompt de producao (baseline) ---
BASELINE_PROMPT = """You are a wine-image analyst. Classify this image as ONE of:

## Classification rules
"label" — One wine or SKU DOMINATES the scene visually.
"shelf" — MULTIPLE DIFFERENT wines together where no single wine dominates.
"screenshot" — digital interface.
"not_wine" — not wine.

## Output (JSON only)
If shelf: {"type":"shelf","wines":[{"name":"...","producer":"...","line":"...","variety":"...","classification":"...","style":"...","price":"..."}],"total_visible":N}

## Rules
- Use full wine name, deduplicate, null for unknown, UNIT price only (ignore per-liter)
- Return ONLY JSON, no markdown"""


def call_qwen(messages, temperature=0.0, seed=42):
    client = get_client()
    t0 = time.time()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
        seed=seed,
    )
    elapsed = int((time.time() - t0) * 1000)
    content = resp.choices[0].message.content or ""
    usage = resp.usage
    return {
        "content": content,
        "elapsed_ms": elapsed,
        "in_tokens": usage.prompt_tokens,
        "out_tokens": usage.completion_tokens,
        "cost": (usage.prompt_tokens / 1e6) * IN_PRICE + (usage.completion_tokens / 1e6) * OUT_PRICE,
    }


def parse_json(text):
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(s)
    except Exception:
        return None


def score_result(parsed):
    """Retorna (acertos, alucinacoes, total_reportado, nomes_reportados)."""
    if not parsed or "wines" not in parsed:
        return 0, 0, 0, []
    wines = parsed["wines"]
    names = [w.get("name", "") for w in wines]
    names_lower = [n.lower() for n in names]

    # Acertos: quantos ground truth foram cobertos
    hits = set()
    for key in GROUND_TRUTH:
        if any(key in n for n in names_lower):
            hits.add(key)

    # Alucinacoes conhecidas
    halluc = sum(1 for n in names_lower if any(h in n for h in KNOWN_HALLUCINATIONS))

    return len(hits), halluc, len(wines), names


def image_message_content(prompt_text, detail="high"):
    """Mensagem multimodal. Qwen suporta 'detail' via image_url."""
    return [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_image()}"}},
        {"type": "text", "text": prompt_text},
    ]


# ===========================================================================
# EXPERIMENTOS
# ===========================================================================

EXPERIMENTS = []


def exp(name, description):
    def decorator(fn):
        EXPERIMENTS.append({"name": name, "desc": description, "fn": fn})
        return fn
    return decorator


@exp("01_baseline", "Prompt de producao, temperature 0")
def e01():
    msgs = [{"role": "user", "content": image_message_content(BASELINE_PROMPT)}]
    return call_qwen(msgs)


@exp("02_role_expert", "Role prompting: auditor de planograma especializado em vinhos")
def e02():
    system = (
        "You are a professional planogram auditor for a premium Brazilian wine retailer. "
        "You have 15 years of experience reading wine labels in noisy supermarket environments. "
        "Your task is EXHAUSTIVE extraction — missing any distinct SKU is a critical failure. "
        "You MUST scan the entire image, including edges and partially visible bottles."
    )
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": image_message_content(BASELINE_PROMPT)},
    ]
    return call_qwen(msgs)


@exp("03_cot_explicit_counting", "Chain-of-thought com contagem explicita antes de listar")
def e03():
    prompt = BASELINE_PROMPT + """

## MANDATORY PROCESS (do internally, output only final JSON)
Step 1: Count the EXACT number of distinct wine labels visible (not bottles — different SKUs).
Step 2: Scan LEFT to RIGHT, TOP to BOTTOM, listing each distinct label once.
Step 3: For each, extract name + price from the nearest price tag.
Step 4: Verify your wine count matches Step 1. If not, re-scan.
Step 5: Output the final JSON."""
    msgs = [{"role": "user", "content": image_message_content(prompt)}]
    return call_qwen(msgs)


@exp("04_spatial_grid", "Prompt forca varredura em grid 3x3")
def e04():
    prompt = BASELINE_PROMPT + """

## SPATIAL SCAN PROTOCOL
Mentally divide the image into a 3x3 grid (9 cells).
For EACH cell, check for wine labels.
Include wines from every cell where they appear.
Do not skip cells — even if a wine is partially visible at an edge."""
    msgs = [{"role": "user", "content": image_message_content(prompt)}]
    return call_qwen(msgs)


@exp("05_strip_shelftag_prefix", "Avisa para NAO incluir prefixo de etiqueta 'VINHO TTO 750ML'")
def e05():
    prompt = BASELINE_PROMPT + """

## CRITICAL NAME CLEANUP
Brazilian shelf tags often prefix wine names with phrases like:
  - "VINHO TINTO"
  - "VINHO TTO"
  - "VINHO TTO 750ML"
  - "V. TINTO"
These are shelf-tag metadata, NOT part of the wine name.
You MUST strip these prefixes and give only the actual wine name as printed on the bottle label.
Example: "VINHO TTO CONTADA 750ML CHIANTI" -> "Contada 1926 Chianti"."""
    msgs = [{"role": "user", "content": image_message_content(prompt)}]
    return call_qwen(msgs)


@exp("06_few_shot", "Few-shot com 1 exemplo de output bom")
def e06():
    prompt = BASELINE_PROMPT + """

## Example of GOOD output (for a different shelf photo)
```json
{"type":"shelf","wines":[
  {"name":"MontGras Reserva Cabernet Sauvignon","producer":"MontGras","line":"Reserva","variety":"Cabernet Sauvignon","classification":"Reserva","style":"red","price":"R$ 49,99"},
  {"name":"Casa Silva Cuvee Colchagua","producer":"Casa Silva","line":"Cuvee","variety":null,"classification":null,"style":"red","price":"R$ 89,99"}
],"total_visible":2}
```
Note: names are clean (no "VINHO TTO" prefix), producer is separate, price is the BOTTLE price."""
    msgs = [{"role": "user", "content": image_message_content(prompt)}]
    return call_qwen(msgs)


@exp("07_no_hallucination_rule", "Regra forte anti-alucinacao")
def e07():
    prompt = BASELINE_PROMPT + """

## ANTI-HALLUCINATION RULE (CRITICAL)
If you CANNOT clearly read a wine name from the image, DO NOT include it.
It is FAR better to report 5 wines you are 100% sure about than 9 with 2 guesses.
Never invent producers, classifications, or varieties from context.
If unsure about ANY field, use null."""
    msgs = [{"role": "user", "content": image_message_content(prompt)}]
    return call_qwen(msgs)


@exp("08_chinese_prompt", "Mesmo prompt em chines (modelo nativo)")
def e08():
    prompt = """你是葡萄酒图像分析师。将此图像分类为以下之一：

"label" — 单个葡萄酒或SKU在视觉上占主导地位。
"shelf" — 多种不同的葡萄酒一起展示，没有单一葡萄酒占主导地位。
"screenshot" — 数字界面。
"not_wine" — 非葡萄酒。

对于货架图片，严格按此JSON格式返回（不要markdown）：
{"type":"shelf","wines":[{"name":"完整葡萄酒名","producer":"酒庄或null","line":"系列或null","variety":"葡萄品种或null","classification":"等级或null","style":"red/white/rose/sparkling","price":"价格或null"}],"total_visible":N}

关键规则：
- 使用葡萄酒的完整名称
- 去除重复
- 未知字段使用null
- 价格必须是单瓶价格（不是每升价格）
- 只返回JSON，不要任何其他文字
- 去除货架标签前缀如"VINHO TTO"
- 不要虚构任何信息

在巴西葡萄酒货架上，价格标签格式为"R$ XX,XX"。"""
    msgs = [{"role": "user", "content": image_message_content(prompt)}]
    return call_qwen(msgs)


@exp("09_all_best_combined", "Combina: role + CoT + anti-halluc + shelftag strip")
def e09():
    system = (
        "You are a professional planogram auditor for a premium Brazilian wine retailer. "
        "You have 15 years of experience reading wine labels in noisy supermarket environments. "
        "Exhaustive extraction — missing any distinct SKU is a critical failure."
    )
    prompt = BASELINE_PROMPT + """

## MANDATORY PROCESS (internal)
Step 1: Count distinct wine labels (different SKUs, not bottles).
Step 2: Scan left-to-right, top-to-bottom.
Step 3: For each label, extract name + price from nearest price tag.
Step 4: Verify count matches Step 1.

## ANTI-HALLUCINATION
If you cannot clearly read a name — omit it. Never invent producers, classifications, varieties.

## SHELF-TAG CLEANUP
Brazilian shelf tags prefix wine names with "VINHO TTO", "VINHO TINTO", "V. TTO", "750ML".
STRIP these prefixes. Return the actual wine name as printed on the bottle label only.

## OUTPUT
Only JSON, no markdown fences, no commentary."""
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": image_message_content(prompt)},
    ]
    return call_qwen(msgs)


@exp("10_self_consistency_3x", "Roda 3x com temp=0.3 e escolhe vinhos que aparecem >=2x")
def e10():
    results = []
    total_cost = 0
    total_ms = 0
    msgs = [{"role": "user", "content": image_message_content(BASELINE_PROMPT)}]
    for i in range(3):
        r = call_qwen(msgs, temperature=0.3, seed=i * 7 + 1)
        total_cost += r["cost"]
        total_ms += r["elapsed_ms"]
        p = parse_json(r["content"])
        if p and "wines" in p:
            results.append(p["wines"])

    # Vota: vinho aparece em >=2 das 3 rodadas
    from collections import Counter
    name_counts = Counter()
    canonical = {}  # lowercase_key -> first full name seen
    for wines in results:
        seen_in_run = set()
        for w in wines:
            name = (w.get("name") or "").strip()
            if not name:
                continue
            # normaliza para chave
            key = " ".join(name.lower().split())[:40]
            if key in seen_in_run:
                continue
            seen_in_run.add(key)
            name_counts[key] += 1
            if key not in canonical:
                canonical[key] = w

    winners = [canonical[k] for k, c in name_counts.items() if c >= 2]
    merged = {"type": "shelf", "wines": winners, "total_visible": len(winners)}

    return {
        "content": json.dumps(merged, ensure_ascii=False),
        "elapsed_ms": total_ms,
        "in_tokens": 0,  # aggregated
        "out_tokens": 0,
        "cost": total_cost,
    }


# ===========================================================================
# RUN
# ===========================================================================
def main():
    print(f"Rodando {len(EXPERIMENTS)} experimentos em {PHOTO.name} com {MODEL}\n")
    results = []
    for exp_info in EXPERIMENTS:
        name = exp_info["name"]
        print(f"  [{name}] {exp_info['desc']}")
        try:
            r = exp_info["fn"]()
            parsed = parse_json(r["content"])
            hits, halluc, total, names = score_result(parsed)
            print(f"    -> {hits}/9 acertos | {halluc} alucinacoes | total={total} | {r['elapsed_ms']}ms | ${r['cost']:.4f}")
            results.append({
                "name": name,
                "desc": exp_info["desc"],
                "hits": hits,
                "halluc": halluc,
                "total_reported": total,
                "wine_names": names,
                "elapsed_ms": r["elapsed_ms"],
                "cost": r["cost"],
                "parsed": parsed,
                "raw": r["content"],
            })
        except Exception as e:
            print(f"    ERRO: {type(e).__name__}: {e}")
            results.append({"name": name, "error": str(e)})

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out = SANDBOX_DIR / "results" / f"experiments_{timestamp}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nJSON: {out}")

    # Tabela resumo
    print(f"\n{'='*90}")
    print(f"{'Experimento':<35} {'Acertos':<10} {'Halluc':<8} {'Total':<7} {'Tempo':<10} {'Custo'}")
    print("=" * 90)
    for r in results:
        if "error" in r:
            print(f"{r['name']:<35} ERRO: {r['error'][:40]}")
            continue
        print(f"{r['name']:<35} {r['hits']}/9        {r['halluc']}        {r['total_reported']}       {r['elapsed_ms']}ms    ${r['cost']:.4f}")


if __name__ == "__main__":
    main()
