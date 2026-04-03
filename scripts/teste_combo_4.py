"""
4 testes combinando as 3 tecnicas (A=few-shot, B=pg_trgm, C=uva+denom)
Todos nos mesmos 300 itens.
"""
import csv, os, time, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-lite"
BATCH_SIZE = 150
SCRIPT_DIR = os.path.dirname(__file__)

# === PROMPTS ===

FEWSHOT_INTRO = """Nosso banco armazena produtores e vinhos neste formato (exemplos reais):
  produtor: "chateau levangile"     vinho: "blason de levangile pomerol"
  produtor: "chateau lenclos"       vinho: "pomerol"
  produtor: "domaine de la romanee conti"  vinho: "romanee conti grand cru"
  produtor: "bodega catena zapata"  vinho: "catena alta malbec"
  produtor: "tenuta san guido"      vinho: "sassicaia"
  produtor: "penfolds"              vinho: "grange shiraz"
  produtor: "joseph phelps vineyards"  vinho: "insignia"
  produtor: "bodegas muga"          vinho: "prado enea gran reserva rioja"
  produtor: "marchesi antinori"     vinho: "tignanello toscana"
  produtor: "vina errazu"           vinho: "max reserva cabernet sauvignon"
"""

UVA_DENOM_FIELDS = """  - Uva = uva principal (ex: merlot, cabernet sauvignon, chardonnay). ?? se nao sabe
  - Denominacao = apelacao/DOC/AOC (ex: Pomerol, Barolo DOCG, Saint-Emilion Grand Cru, Napa Valley AVA). ?? se nao sabe"""

# A+B: few-shot + basico (pg_trgm na busca)
PROMPT_AB = FEWSHOT_INTRO + """
TAREFA: Classifique cada item.
- X = nao e vinho | S = destilado/spirit
- W = vinho: W|ProdBanco|VinhoBanco|Pais|Cor
  - ProdBanco = produtor no formato do banco: minusculo, sem acentos, sem apostrofos, l' junto, saint junto
  - VinhoBanco = vinho no formato do banco: mesma regra
  - Pais = 2 letras (??) | Cor: r/w/p/s/f/d
- =N se duplicata | NAO invente. ?? se nao sabe.

ITEMS:
"""

# A+C: few-shot + uva+denom (ILIKE na busca)
PROMPT_AC = FEWSHOT_INTRO + """
TAREFA: Classifique cada item.
- X = nao e vinho | S = destilado/spirit
- W = vinho: W|ProdBanco|VinhoBanco|Pais|Cor|Uva|Denominacao
  - ProdBanco = produtor no formato do banco: minusculo, sem acentos, sem apostrofos, l' junto, saint junto
  - VinhoBanco = vinho no formato do banco: mesma regra
  - Pais = 2 letras (??) | Cor: r/w/p/s/f/d
""" + UVA_DENOM_FIELDS + """
- =N se duplicata | NAO invente. ?? se nao sabe.

ITEMS:
"""

# B+C: basico + uva+denom (pg_trgm na busca)
PROMPT_BC = """TAREFA: Classifique cada item.
- X = nao e vinho | S = destilado/spirit
- W = vinho: W|Produtor|Vinho|Pais|Cor|Uva|Denominacao
  - Produtor = nome completo da vinicola
  - Vinho = nome do vinho SEM produtor
  - Pais = 2 letras (??) | Cor: r/w/p/s/f/d
""" + UVA_DENOM_FIELDS + """
- =N se duplicata | NAO invente. ?? se nao sabe.

ITEMS:
"""

# A+B+C: few-shot + uva+denom (pg_trgm na busca)
PROMPT_ABC = FEWSHOT_INTRO + """
TAREFA: Classifique cada item.
- X = nao e vinho | S = destilado/spirit
- W = vinho: W|ProdBanco|VinhoBanco|Pais|Cor|Uva|Denominacao
  - ProdBanco = produtor no formato do banco: minusculo, sem acentos, sem apostrofos, l' junto, saint junto
  - VinhoBanco = vinho no formato do banco: mesma regra
  - Pais = 2 letras (??) | Cor: r/w/p/s/f/d
""" + UVA_DENOM_FIELDS + """
- =N se duplicata | NAO invente. ?? se nao sabe.

ITEMS:
"""

# === HELPERS ===

def load_items(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def call_llm(model, prompt, text):
    try:
        r = model.generate_content(prompt + text,
            generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=8192))
        return r.text.strip()
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

def normalize(s):
    s = s.lower().strip()
    for o, n in [("\u00e1","a"),("\u00e0","a"),("\u00e2","a"),("\u00e3","a"),("\u00e4","a"),
                 ("\u00e9","e"),("\u00e8","e"),("\u00ea","e"),("\u00eb","e"),
                 ("\u00ed","i"),("\u00ec","i"),("\u00ee","i"),("\u00ef","i"),
                 ("\u00f3","o"),("\u00f2","o"),("\u00f4","o"),("\u00f5","o"),("\u00f6","o"),
                 ("\u00fa","u"),("\u00f9","u"),("\u00fb","u"),("\u00fc","u"),
                 ("\u00f1","n"),("\u00e7","c")]:
        s = s.replace(o, n)
    s = re.sub(r"['\u2019\u2018`]", "", s)
    s = re.sub(r"-", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def get_db():
    return psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                            user="postgres", password="postgres123",
                            options="-c client_encoding=UTF8")

def run_llm_batches(model, prompt, items):
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


def match_trgm(cur, prod, vin, uva="", denom=""):
    """Busca com pg_trgm. Retorna (found, score)."""
    cur.execute("""
        SELECT id, produtor_normalizado, nome_normalizado,
               similarity(produtor_normalizado, %s) as ps,
               similarity(nome_normalizado, %s) as ns
        FROM vivino_match WHERE produtor_normalizado %% %s
        ORDER BY similarity(produtor_normalizado, %s) DESC LIMIT 15
    """, (prod, vin, prod, prod))
    cands = cur.fetchall()
    if not cands:
        return False, 0

    best_score = 0
    for cid, cprod, cnome, ps, ns in cands:
        score = ps * 0.5 + ns * 0.3
        # Bonus uva
        if uva and uva != "??" and uva in cnome:
            score += 0.1
        # Bonus denominacao
        if denom and denom != "??" and denom in cnome:
            score += 0.1
        if score > best_score:
            best_score = score

    return best_score >= 0.35, best_score


def match_ilike(cur, prod, vin, uva="", denom=""):
    """Busca com ILIKE exato + fallback contem."""
    # Exato
    cur.execute("SELECT id, nome_normalizado FROM vivino_match WHERE produtor_normalizado = %s", (prod,))
    cands = cur.fetchall()
    if not cands:
        cur.execute("SELECT id, nome_normalizado FROM vivino_match WHERE produtor_normalizado ILIKE %s LIMIT 20", (f"%{prod}%",))
        cands = cur.fetchall()
    if not cands:
        return False, 0

    vin_words = set(vin.split()) - {"de","du","la","le","les","des","del","di","the"}
    best_score = 0
    for cid, cnome in cands:
        cn_words = set(cnome.split()) - {"de","du","la","le","les","des","del","di","the"}
        if vin_words and cn_words:
            overlap = len(vin_words & cn_words) / max(len(vin_words), len(cn_words))
        elif vin in cnome or cnome in vin:
            overlap = 0.7
        else:
            overlap = 0
        score = 0.5 + overlap * 0.3  # produtor ja bateu = 0.5 base
        if uva and uva != "??" and uva in cnome: score += 0.1
        if denom and denom != "??" and denom in cnome: score += 0.1
        if score > best_score:
            best_score = score

    return best_score >= 0.55, best_score


def run_test(name, items, llm_lines, use_trgm, has_uva):
    """Roda matching e retorna % match."""
    conn = get_db(); cur = conn.cursor()
    ok = 0; no = 0; tw = 0

    for i in range(len(items)):
        llm = llm_lines.get(i+1, "")
        if not llm.startswith("W"): continue
        tw += 1
        parts = llm.split("|")
        if len(parts) < 5: no += 1; continue

        prod_raw = parts[1].strip().split("=")[0].strip()
        vin_raw = parts[2].strip().split("=")[0].strip()
        prod = normalize(prod_raw)
        vin = normalize(vin_raw)

        uva = ""
        denom = ""
        if has_uva and len(parts) >= 7:
            uva = normalize(parts[5].split("=")[0].strip())
            denom = normalize(parts[6].split("=")[0].strip())

        if not prod or prod == "??" or len(prod) < 2:
            no += 1; continue

        if use_trgm:
            found, score = match_trgm(cur, prod, vin, uva, denom)
        else:
            found, score = match_ilike(cur, prod, vin, uva, denom)

        if found: ok += 1
        else: no += 1

    conn.close()
    pct = ok * 100 // tw if tw else 0
    print(f"  {name:<35} W={tw:>3} | Match={ok:>3} ({pct}%)")
    return pct, tw


def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)

    items = load_items(os.path.join(SCRIPT_DIR, "teste_combo_300.csv"))
    print(f"Carregados {len(items)} itens\n")

    results = {}

    # 1. A+B: few-shot prompt + pg_trgm search
    print("--- Rodando prompt A+B (few-shot) ---")
    lines_ab = run_llm_batches(model, PROMPT_AB, items)
    time.sleep(5)

    # 2. A+C: few-shot + uva+denom prompt + ILIKE search
    print("\n--- Rodando prompt A+C (few-shot + uva+denom) ---")
    lines_ac = run_llm_batches(model, PROMPT_AC, items)
    time.sleep(5)

    # 3. B+C: basico + uva+denom prompt + pg_trgm search
    print("\n--- Rodando prompt B+C (uva+denom) ---")
    lines_bc = run_llm_batches(model, PROMPT_BC, items)
    time.sleep(5)

    # 4. A+B+C: few-shot + uva+denom + pg_trgm
    print("\n--- Rodando prompt A+B+C (tudo junto) ---")
    lines_abc = run_llm_batches(model, PROMPT_ABC, items)

    # === MATCHING ===
    print(f"\n{'='*60}")
    print("RESULTADOS")
    print(f"{'='*60}\n")

    pct, tw = run_test("A+B: few-shot + pg_trgm", items, lines_ab, use_trgm=True, has_uva=False)
    results["A+B few-shot + pg_trgm"] = (pct, tw)

    pct, tw = run_test("A+C: few-shot + uva+denom (ILIKE)", items, lines_ac, use_trgm=False, has_uva=True)
    results["A+C few-shot + uva+denom"] = (pct, tw)

    pct, tw = run_test("B+C: pg_trgm + uva+denom", items, lines_bc, use_trgm=True, has_uva=True)
    results["B+C pg_trgm + uva+denom"] = (pct, tw)

    pct, tw = run_test("A+B+C: TUDO JUNTO", items, lines_abc, use_trgm=True, has_uva=True)
    results["A+B+C TUDO JUNTO"] = (pct, tw)

    # Bonus: rodar A+C com pg_trgm tb (few-shot + uva + trgm = quase ABC)
    pct, tw = run_test("A+C+trgm: few-shot+uva+trgm", items, lines_ac, use_trgm=True, has_uva=True)
    results["A+C+trgm bonus"] = (pct, tw)

    # === RESUMO ===
    print(f"\n{'='*60}")
    print("RANKING FINAL")
    print(f"{'='*60}")
    for name, (pct, tw) in sorted(results.items(), key=lambda x: -x[1][0]):
        bar = "#" * (pct // 2)
        print(f"  {name:<35} {pct:>3}% (n={tw:>3})  {bar}")


if __name__ == "__main__":
    main()
