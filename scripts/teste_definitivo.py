"""
Teste DEFINITIVO: 4 combinacoes, 4 lotes diferentes, zero cache.
A=few-shot B=pg_trgm C=uva+denom
"""
import csv, os, time, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-lite"
BATCH_SIZE = 150
SD = os.path.dirname(__file__)

FEWSHOT = """Nosso banco armazena produtores e vinhos neste formato (exemplos reais):
  produtor: "chateau levangile"     vinho: "blason de levangile pomerol"
  produtor: "chateau lenclos"       vinho: "pomerol"
  produtor: "domaine de la romanee conti"  vinho: "romanee conti grand cru"
  produtor: "bodega catena zapata"  vinho: "catena alta malbec"
  produtor: "tenuta san guido"      vinho: "sassicaia"
  produtor: "penfolds"              vinho: "grange shiraz"
  produtor: "joseph phelps vineyards"  vinho: "insignia"
  produtor: "bodegas muga"          vinho: "prado enea gran reserva rioja"
  produtor: "marchesi antinori"     vinho: "tignanello toscana"
  produtor: "vina errazuriz"        vinho: "max reserva cabernet sauvignon"
"""

UVA = """  - Uva = uva principal (ex: merlot, cabernet sauvignon, chardonnay). ?? se nao sabe
  - Denominacao = apelacao/DOC/AOC (ex: Pomerol, Barolo DOCG, Napa Valley). ?? se nao sabe"""

# A+B: few-shot + pg_trgm (sem uva)
P_AB = FEWSHOT + """TAREFA: Classifique.
- X = nao vinho | S = destilado
- W = W|ProdBanco|VinhoBanco|Pais|Cor
  ProdBanco/VinhoBanco = formato banco: minusculo, sem acento, l' junto, saint junto
- =N duplicata | ?? se nao sabe | NAO invente

ITEMS:
"""

# A+C: few-shot + uva+denom (ILIKE)
P_AC = FEWSHOT + """TAREFA: Classifique.
- X = nao vinho | S = destilado
- W = W|ProdBanco|VinhoBanco|Pais|Cor|Uva|Denominacao
  ProdBanco/VinhoBanco = formato banco: minusculo, sem acento, l' junto, saint junto
""" + UVA + """
- =N duplicata | ?? se nao sabe | NAO invente

ITEMS:
"""

# B+C: basico + uva+denom (pg_trgm)
P_BC = """TAREFA: Classifique.
- X = nao vinho | S = destilado
- W = W|Produtor|Vinho|Pais|Cor|Uva|Denominacao
  Produtor = nome completo vinicola | Vinho = sem produtor
""" + UVA + """
- =N duplicata | ?? se nao sabe | NAO invente

ITEMS:
"""

# A+B+C: tudo
P_ABC = FEWSHOT + """TAREFA: Classifique.
- X = nao vinho | S = destilado
- W = W|ProdBanco|VinhoBanco|Pais|Cor|Uva|Denominacao
  ProdBanco/VinhoBanco = formato banco: minusculo, sem acento, l' junto, saint junto
""" + UVA + """
- =N duplicata | ?? se nao sabe | NAO invente

ITEMS:
"""


def load(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def llm_call(model, prompt, text):
    try:
        r = model.generate_content(prompt + text,
            generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=8192))
        return r.text.strip()
    except Exception as e:
        print(f"  ERRO: {e}")
        return ""

def parse(text):
    m = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line: continue
        p = line.split(". ", 1)
        if len(p) == 2 and p[0].strip().isdigit():
            m[int(p[0].strip())] = p[1].strip()
    return m

def norm(s):
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


def run_test(name, csv_file, prompt, use_trgm, has_uva, model):
    print(f"\n{'='*60}")
    print(f"TESTE: {name}")
    print(f"Arquivo: {csv_file} | trgm={use_trgm} | uva={has_uva}")
    print(f"{'='*60}")

    items = load(os.path.join(SD, csv_file))
    print(f"Itens: {len(items)}")

    # LLM
    all_lines = {}
    sn = 1
    for bs in range(0, len(items), BATCH_SIZE):
        batch = items[bs:bs+BATCH_SIZE]
        txt = "\n".join(f"{sn+i}. {it['loja_nome']}" for i, it in enumerate(batch))
        print(f"  Lote {bs//BATCH_SIZE+1}...", end=" ", flush=True)
        text = llm_call(model, prompt, txt)
        lines = parse(text)
        w = sum(1 for v in lines.values() if v.startswith("W"))
        x = sum(1 for v in lines.values() if v.startswith("X"))
        s = sum(1 for v in lines.values() if v.startswith("S"))
        dup = sum(1 for v in lines.values() if "=" in v and v.startswith("W"))
        print(f"W={w} X={x} S={s} dup={dup}")
        all_lines.update(lines)
        sn += len(batch)
        if bs + BATCH_SIZE < len(items): time.sleep(5)

    # Match
    conn = get_db(); cur = conn.cursor()
    ok = 0; no = 0; tw = 0
    total_dup = sum(1 for v in all_lines.values() if "=" in v and v.startswith("W"))

    for i in range(len(items)):
        llm = all_lines.get(i+1, "")
        if not llm.startswith("W"): continue
        tw += 1
        parts = llm.split("|")
        if len(parts) < 5: no += 1; continue

        prod = norm(parts[1].split("=")[0].strip())
        vin = norm(parts[2].split("=")[0].strip())

        uva = ""
        denom = ""
        if has_uva and len(parts) >= 7:
            uva = norm(parts[5].split("=")[0].strip())
            denom = norm(parts[6].split("=")[0].strip())

        if not prod or prod == "??" or len(prod) < 2:
            no += 1; continue

        if use_trgm:
            cur.execute("""
                SELECT id, produtor_normalizado, nome_normalizado,
                       similarity(produtor_normalizado, %s) as ps,
                       similarity(nome_normalizado, %s) as ns
                FROM vivino_match WHERE produtor_normalizado %% %s
                ORDER BY similarity(produtor_normalizado, %s) DESC LIMIT 15
            """, (prod, vin, prod, prod))
            cands = cur.fetchall()
            if cands:
                best = 0
                for _, _, cnome, ps, ns in cands:
                    sc = ps * 0.5 + ns * 0.3
                    if uva and uva != "??" and uva in cnome: sc += 0.1
                    if denom and denom != "??" and denom in cnome: sc += 0.1
                    if sc > best: best = sc
                if best >= 0.35: ok += 1
                else: no += 1
            else: no += 1
        else:
            # ILIKE
            cur.execute("SELECT id, nome_normalizado FROM vivino_match WHERE produtor_normalizado = %s", (prod,))
            cands = cur.fetchall()
            if not cands:
                cur.execute("SELECT id, nome_normalizado FROM vivino_match WHERE produtor_normalizado ILIKE %s LIMIT 20", (f"%{prod}%",))
                cands = cur.fetchall()
            if not cands: no += 1; continue

            vw = set(vin.split()) - {"de","du","la","le","les","des","del","di","the"}
            best = 0
            for _, cnome in cands:
                cw = set(cnome.split()) - {"de","du","la","le","les","des","del","di","the"}
                if vw and cw:
                    ov = len(vw & cw) / max(len(vw), len(cw))
                elif vin in cnome or cnome in vin:
                    ov = 0.7
                else: ov = 0
                sc = 0.5 + ov * 0.3
                if uva and uva != "??" and uva in cnome: sc += 0.1
                if denom and denom != "??" and denom in cnome: sc += 0.1
                if sc > best: best = sc
            if best >= 0.55: ok += 1
            else: no += 1

    conn.close()
    pct = ok * 100 // tw if tw else 0
    print(f"\n  RESULTADO: W={tw} | Match={ok} ({pct}%) | Sem={no} | Dup={total_dup}")
    return pct, tw, total_dup


def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)

    tests = [
        ("A+B: few-shot + pg_trgm",       "teste_combo_ab.csv",  P_AB,  True,  False),
        ("A+C: few-shot + uva (ILIKE)",    "teste_combo_ac.csv",  P_AC,  False, True),
        ("B+C: pg_trgm + uva",            "teste_combo_bc.csv",  P_BC,  True,  True),
        ("A+B+C: TUDO JUNTO",             "teste_combo_abc.csv", P_ABC, True,  True),
    ]

    results = {}
    for name, csv_f, prompt, trgm, uva in tests:
        pct, tw, dup = run_test(name, csv_f, prompt, trgm, uva, model)
        results[name] = (pct, tw, dup)
        time.sleep(8)  # pausa maior entre testes pra evitar rate limit

    print(f"\n\n{'='*60}")
    print("RANKING DEFINITIVO (lotes diferentes, zero cache)")
    print(f"{'='*60}")
    for name, (pct, tw, dup) in sorted(results.items(), key=lambda x: -x[1][0]):
        bar = "#" * (pct // 2)
        print(f"  {name:<35} {pct:>3}% (W={tw:>3}, dup={dup:>2})  {bar}")


if __name__ == "__main__":
    main()
