"""
Re-rodar os 3 testes que falharam com faixas melhores.
"""
import csv, os, time, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-lite"
BATCH_SIZE = 150
SCRIPT_DIR = os.path.dirname(__file__)

def load_items(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def call_llm(model, prompt, items_text):
    try:
        resp = model.generate_content(prompt + items_text,
            generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=8192))
        return resp.text.strip()
    except Exception as e:
        print(f"  ERRO: {e}")
        return ""

def parse_lines(text):
    m = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line: continue
        parts = line.split(". ", 1)
        if len(parts) == 2 and parts[0].strip().isdigit():
            m[int(parts[0].strip())] = parts[1].strip()
    return m

def get_db():
    return psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                            user="postgres", password="postgres123",
                            options="-c client_encoding=UTF8")

def normalize_script(s):
    s = s.lower().strip()
    for old, new in [("a\u0301","a"),("e\u0301","e"),("i\u0301","i"),("o\u0301","o"),("u\u0301","u"),
                     ("\u00e1","a"),("\u00e0","a"),("\u00e2","a"),("\u00e3","a"),("\u00e4","a"),
                     ("\u00e9","e"),("\u00e8","e"),("\u00ea","e"),("\u00eb","e"),
                     ("\u00ed","i"),("\u00ec","i"),("\u00ee","i"),("\u00ef","i"),
                     ("\u00f3","o"),("\u00f2","o"),("\u00f4","o"),("\u00f5","o"),("\u00f6","o"),
                     ("\u00fa","u"),("\u00f9","u"),("\u00fb","u"),("\u00fc","u"),
                     ("\u00f1","n"),("\u00e7","c")]:
        s = s.replace(old, new)
    s = re.sub(r"['`\u2019\u2018]", "", s)
    s = re.sub(r"-", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def run_llm(model, prompt, items):
    all_lines = {}
    sn = 1
    for bs in range(0, len(items), BATCH_SIZE):
        batch = items[bs:bs+BATCH_SIZE]
        txt = "\n".join(f"{sn+i}. {it['loja_nome']}" for i, it in enumerate(batch))
        print(f"  Lote {bs//BATCH_SIZE+1}...", end=" ", flush=True)
        text = call_llm(model, prompt, txt)
        lines = parse_lines(text)
        w = sum(1 for v in lines.values() if v.startswith("W"))
        print(f"W={w}")
        all_lines.update(lines)
        sn += len(batch)
        if bs + BATCH_SIZE < len(items): time.sleep(5)
    return all_lines


# ============================================================
# TESTE 7+8: pg_trgm
# ============================================================
def test_trgm(items, model):
    print(f"\n{'='*60}")
    print("TESTE 7+8: pg_trgm no produtor + vinho")
    print(f"{'='*60}")

    prompt = "TAREFA: Classifique.\n- X = nao vinho | S = destilado\n- W = vinho: W|Produtor|Vinho|Pais|Cor\n- =N duplicata | ?? se nao sabe\n\nITEMS:\n"
    lines = run_llm(model, prompt, items)
    conn = get_db(); cur = conn.cursor()
    ok = 0; no = 0; tw = 0

    for i, item in enumerate(items):
        llm = lines.get(i+1, "")
        if not llm.startswith("W"): continue
        tw += 1
        parts = llm.split("|")
        if len(parts) < 5: no += 1; continue
        prod = normalize_script(parts[1])
        vin = normalize_script(parts[2].split("=")[0])
        if not prod or prod == "??": no += 1; continue

        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(produtor_normalizado, %s) as ps,
                   similarity(nome_normalizado, %s) as ns
            FROM vivino_match WHERE produtor_normalizado %% %s
            ORDER BY similarity(produtor_normalizado, %s) DESC LIMIT 10
        """, (prod, vin, prod, prod))
        cands = cur.fetchall()
        if cands:
            best = max(cands, key=lambda c: c[3]*0.6 + c[4]*0.4)
            if best[3]*0.6 + best[4]*0.4 >= 0.35: ok += 1
            else: no += 1
        else: no += 1

    conn.close()
    pct = ok*100//tw if tw else 0
    print(f"\n  W={tw} | Match={ok} ({pct}%) | Sem={no}")
    return pct


# ============================================================
# TESTE 15+16: script norm
# ============================================================
def test_norm(items, model):
    print(f"\n{'='*60}")
    print("TESTE 15+16: Normalizacao no script + pg_trgm")
    print(f"{'='*60}")

    prompt = "TAREFA: Classifique.\n- X = nao vinho | S = destilado\n- W = vinho: W|Produtor|Vinho|Pais|Cor\n  Produtor = nome COMPLETO original (com acentos)\n- =N duplicata | ?? se nao sabe\n\nITEMS:\n"
    lines = run_llm(model, prompt, items)
    conn = get_db(); cur = conn.cursor()
    ok = 0; no = 0; tw = 0

    for i, item in enumerate(items):
        llm = lines.get(i+1, "")
        if not llm.startswith("W"): continue
        tw += 1
        parts = llm.split("|")
        if len(parts) < 5: no += 1; continue
        prod = normalize_script(parts[1])
        vin = normalize_script(parts[2].split("=")[0])
        if not prod or prod == "??": no += 1; continue

        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(produtor_normalizado, %s) as ps,
                   similarity(nome_normalizado, %s) as ns
            FROM vivino_match WHERE produtor_normalizado %% %s
            ORDER BY similarity(produtor_normalizado, %s) DESC LIMIT 10
        """, (prod, vin, prod, prod))
        cands = cur.fetchall()
        if cands:
            best = max(cands, key=lambda c: c[3]*0.6 + c[4]*0.4)
            if best[3]*0.6 + best[4]*0.4 >= 0.35: ok += 1
            else: no += 1
        else: no += 1

    conn.close()
    pct = ok*100//tw if tw else 0
    print(f"\n  W={tw} | Match={ok} ({pct}%) | Sem={no}")
    return pct


# ============================================================
# TESTE 11: DB candidatos, LLM confirma
# ============================================================
def test_reverse(items, model):
    print(f"\n{'='*60}")
    print("TESTE 11: DB candidatos -> LLM confirma")
    print(f"{'='*60}")

    prompt_cls = "TAREFA: Classifique.\n- X = nao vinho | S = destilado\n- W = vinho: W|Produtor|Vinho|Pais|Cor\n- =N duplicata | ?? se nao sabe\n\nITEMS:\n"
    lines = run_llm(model, prompt_cls, items)

    conn = get_db(); cur = conn.cursor()
    pairs = []
    tw = 0

    for i, item in enumerate(items):
        llm = lines.get(i+1, "")
        if not llm.startswith("W"): continue
        tw += 1
        parts = llm.split("|")
        if len(parts) < 5: continue
        prod = normalize_script(parts[1])
        if not prod or prod == "??": continue

        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado
            FROM vivino_match WHERE produtor_normalizado %% %s
            ORDER BY similarity(produtor_normalizado, %s) DESC LIMIT 3
        """, (prod, prod))
        cands = cur.fetchall()
        if cands:
            # Pegar o melhor candidato
            pairs.append({
                "loja": item["loja_nome"],
                "cand_prod": cands[0][1],
                "cand_nome": cands[0][2],
            })
    conn.close()

    print(f"\n  W={tw} | Candidatos encontrados={len(pairs)}")
    if not pairs:
        return 0

    # LLM confirma
    prompt_confirm = """Para cada par, responda S (sim, mesmo vinho), N (nao), P (provavelmente).
APENAS S, N ou P.

PARES:
"""
    ok = 0
    for bs in range(0, len(pairs), BATCH_SIZE):
        batch = pairs[bs:bs+BATCH_SIZE]
        txt = "\n".join(f"{j+1}. LOJA: \"{p['loja']}\" | VIVINO: \"{p['cand_prod']} - {p['cand_nome']}\"" for j, p in enumerate(batch))
        print(f"  Confirmacao lote {bs//BATCH_SIZE+1}...", end=" ", flush=True)
        text = call_llm(model, prompt_confirm, txt)
        cl = parse_lines(text)
        s = sum(1 for v in cl.values() if v.strip().upper() in ("S","P"))
        n = sum(1 for v in cl.values() if v.strip().upper() == "N")
        ok += s
        print(f"S/P={s} N={n}")
        if bs + BATCH_SIZE < len(pairs): time.sleep(5)

    pct = ok*100//tw if tw else 0
    print(f"\n  W={tw} | Match confirmado={ok} ({pct}%)")
    return pct


def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)

    tests = [
        ("7+8 pg_trgm", "teste_test1b.csv", test_trgm),
        ("15+16 script norm", "teste_test4b.csv", test_norm),
        ("11 DB->LLM confirma", "teste_test5b.csv", test_reverse),
    ]

    results = {}
    # Resultados anteriores
    results["1+2 uva+denom"] = 76  # (26 vinhos, amostra pequena)
    results["6 few-shot"] = 70     # (289 vinhos)

    for name, filename, func in tests:
        path = os.path.join(SCRIPT_DIR, filename)
        items = load_items(path)
        print(f"\n\nCarregados {len(items)} para {name}")
        results[name] = func(items, model)
        time.sleep(5)

    print(f"\n\n{'='*60}")
    print("RESUMO FINAL - 5 ABORDAGENS")
    print(f"{'='*60}")
    for name, pct in sorted(results.items(), key=lambda x: -x[1]):
        bar = "#" * (pct // 2)
        print(f"  {name:<30} {pct:>3}%  {bar}")


if __name__ == "__main__":
    main()
