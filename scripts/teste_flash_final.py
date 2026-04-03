"""
Teste FINAL com Gemini 2.5 Flash + prompt que forca formato simples.
3 lotes de 300, batch=100.
"""
import csv, os, time, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
BATCH_SIZE = 100
SD = os.path.dirname(__file__)

PROMPT = """Nosso banco armazena vinhos assim (exemplos reais):
  produtor: "chateau levangile"     vinho: "blason de levangile pomerol"
  produtor: "domaine de la romanee conti"  vinho: "romanee conti grand cru"
  produtor: "bodega catena zapata"  vinho: "catena alta malbec"
  produtor: "tenuta san guido"      vinho: "sassicaia"
  produtor: "penfolds"              vinho: "grange shiraz"
  produtor: "joseph phelps vineyards"  vinho: "insignia"

TAREFA: Classifique cada item. Responda APENAS no formato abaixo. Uma linha por item. Sem markdown, sem explicacao, sem bullet points.

Formato por linha:
  N. X                                          (nao e vinho)
  N. S                                          (destilado/spirit)
  N. W|NomeCorrigido|ProdBanco|VinhoBanco|Pais|Cor   (vinho)
  N. W|NomeCorrigido|ProdBanco|VinhoBanco|Pais|Cor|=M (duplicata do item M)

Campos:
- NomeCorrigido = nome oficial do vinho, corrigido (typos, abreviacoes)
- ProdBanco = produtor minusculo, sem acento, sem apostrofo, l' junto (levangile nao l evangile), saint junto (saintemilion). Se nao sabe: ??
- VinhoBanco = vinho minusculo, sem acento, mesma regra. Se nao sabe: ??
- Pais = 2 letras (?? se nao sabe)
- Cor: r=tinto w=branco p=rose s=espumante f=fortificado d=sobremesa
- =M se e duplicata de item M (mesmo vinho, safra/formato diferente)

Se o nome comeca com regiao (val de loire, cotes du rhone), o produtor esta DEPOIS.
NAO invente dados. Se nao faz sentido como vinho = X.

ITEMS:
"""

def load(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

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

def parse(text):
    m = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line: continue
        p = line.split(". ", 1)
        if len(p) == 2 and p[0].strip().isdigit():
            m[int(p[0].strip())] = p[1].strip()
    return m

def get_db():
    return psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                            user="postgres", password="postgres123",
                            options="-c client_encoding=UTF8")

def call_batch(model, items, start_num):
    txt = "\n".join(f"{start_num+i}. {it['loja_nome']}" for i, it in enumerate(items))
    for attempt in range(5):
        try:
            r = model.generate_content(PROMPT + txt,
                generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=4096))
            text = r.text.strip()
            lines = parse(text)
            if len(lines) >= len(items) * 0.5:
                return lines, len(lines), attempt + 1
            print(f"(parcial {len(lines)}/{len(items)}, retry {attempt+1})", end=" ", flush=True)
        except Exception as e:
            print(f"(erro: {str(e)[:40]}, retry {attempt+1})", end=" ", flush=True)
        time.sleep(3)
    return {}, 0, 5


def run_lote(name, csv_file, model):
    print(f"\n{'='*60}")
    print(f"LOTE {name}")
    print(f"{'='*60}")
    items = load(os.path.join(SD, csv_file))
    print(f"Itens: {len(items)}")

    all_lines = {}
    sn = 1
    for bs in range(0, len(items), BATCH_SIZE):
        batch = items[bs:bs+BATCH_SIZE]
        print(f"  Batch {bs//BATCH_SIZE+1}/{-(-len(items)//BATCH_SIZE)} ({len(batch)} itens)...", end=" ", flush=True)
        lines, responded, attempts = call_batch(model, batch, sn)
        w = sum(1 for v in lines.values() if v.startswith("W"))
        x = sum(1 for v in lines.values() if v.startswith("X"))
        s = sum(1 for v in lines.values() if v.startswith("S"))
        dup = sum(1 for v in lines.values() if "=" in v)
        miss = len(batch) - responded
        all_lines.update(lines)
        retries_str = f" (retries={attempts-1})" if attempts > 1 else ""
        print(f"W={w} X={x} S={s} dup={dup} miss={miss}{retries_str}")
        sn += len(batch)
        time.sleep(2)

    total = len(items)
    responded = len(all_lines)
    wines = sum(1 for v in all_lines.values() if v.startswith("W"))
    notwine = sum(1 for v in all_lines.values() if v.startswith("X"))
    spirits = sum(1 for v in all_lines.values() if v.startswith("S"))
    dups = sum(1 for v in all_lines.values() if "=" in v)
    print(f"\n  Completude: {responded}/{total} ({responded*100//total}%)")
    print(f"  W={wines} X={notwine} S={spirits} Dup={dups}")

    if wines == 0:
        return 0, 0, dups, responded, total

    # Match pg_trgm
    conn = get_db(); cur = conn.cursor()
    ok = 0; no_m = 0
    ex_ok = []; ex_no = []

    for i in range(total):
        llm = all_lines.get(i+1, "")
        if not llm.startswith("W"): continue
        parts = llm.split("|")
        # W|NomeCorrigido|ProdBanco|VinhoBanco|Pais|Cor
        if len(parts) < 6: no_m += 1; continue

        prod = norm(parts[2].strip().split("=")[0].strip())
        vin = norm(parts[3].strip().split("=")[0].strip())
        if not prod or prod == "??" or len(prod) < 2:
            no_m += 1
            if len(ex_no) < 8: ex_no.append((items[i]['loja_nome'], parts[1][:25], "sem produtor"))
            continue

        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(produtor_normalizado, %s) as ps,
                   similarity(nome_normalizado, %s) as ns
            FROM vivino_match WHERE produtor_normalizado %% %s
            ORDER BY similarity(produtor_normalizado, %s) DESC LIMIT 15
        """, (prod, vin, prod, prod))
        cands = cur.fetchall()
        if cands:
            best_sc = 0; best_info = ""
            for cid, cprod, cnome, ps, ns in cands:
                sc = ps * 0.5 + ns * 0.3
                if sc > best_sc: best_sc = sc; best_info = f"{cprod} - {cnome}"
            if best_sc >= 0.35:
                ok += 1
                if len(ex_ok) < 10: ex_ok.append((items[i]['loja_nome'], parts[1][:25], best_info[:35], f"{best_sc:.2f}"))
            else:
                no_m += 1
                if len(ex_no) < 8: ex_no.append((items[i]['loja_nome'], parts[1][:25], f"score={best_sc:.2f}"))
        else:
            no_m += 1
            if len(ex_no) < 8: ex_no.append((items[i]['loja_nome'], parts[1][:25], "nao encontrado"))

    conn.close()
    pct = ok * 100 // wines if wines else 0
    print(f"  Match: {ok}/{wines} ({pct}%)")

    print(f"\n  Matches (top 10):")
    for orig, corr, db, sc in ex_ok[:10]:
        print(f"    {orig[:30]:30} -> {corr[:22]:22} -> {db} ({sc})")
    print(f"  Sem match (top 8):")
    for orig, corr, motivo in ex_no[:8]:
        print(f"    {orig[:30]:30} -> {corr[:22]:22} {motivo}")

    return pct, wines, dups, responded, total


def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)

    lotes = [
        ("mou-mur", "teste_flash_1.csv"),
        ("per-pes", "teste_flash_2.csv"),
        ("sou-spi", "teste_flash_3.csv"),
    ]

    results = {}
    tw = 0; tok = 0; tdup = 0; tresp = 0; ttotal = 0

    for name, csv_f in lotes:
        pct, wines, dups, resp, total = run_lote(name, csv_f, model)
        results[name] = (pct, wines, dups, resp, total)
        tw += wines; tok += int(wines*pct/100); tdup += dups; tresp += resp; ttotal += total
        time.sleep(5)

    print(f"\n\n{'='*60}")
    print("RESULTADO FINAL — Gemini 2.5 Flash + formato forcado")
    print(f"{'='*60}")
    for name, (pct, wines, dups, resp, total) in results.items():
        bar = "#" * (pct // 2)
        print(f"  {name:<15} Match={pct:>3}% W={wines:>3} Dup={dups:>2} Completude={resp}/{total}  {bar}")
    avg = tok*100//tw if tw else 0
    print(f"\n  {'TOTAL':<15} Match={avg:>3}% W={tw:>3} Dup={tdup:>2} Completude={tresp}/{ttotal}")


if __name__ == "__main__":
    main()
