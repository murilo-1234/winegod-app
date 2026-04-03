"""
Teste das 3 solucoes + mescla:
  Sol 3: buscar no texto_busca (sem LLM extra)
  Sol 5: pedir ProdReal ao LLM
  Sol 8: 2 passos (LLM basico + LLM extra so pra quem falhou)
  Mescla: Sol 3 + Sol 5 juntas
"""
import csv, os, time, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
BATCH_SIZE = 20
THRESHOLD = 0.45
SD = os.path.dirname(__file__)

# === PROMPTS ===

# Sol 3: prompt basico (busca no texto_busca e feita no script)
PROMPT_3 = """Exemplos do nosso banco:
  produtor: "chateau levangile"  vinho: "pomerol"
  produtor: "campo viejo"  vinho: "reserva rioja"
  produtor: "penfolds"  vinho: "grange shiraz"

TODOS os itens. Uma linha por item. Sem markdown.

Formato:
1. X
2. S
3. W|ProdBanco|VinhoBanco|Pais|Cor
4. W|ProdBanco|VinhoBanco|Pais|Cor|=3

ProdBanco/VinhoBanco = minusculo, sem acento, l' junto, saint junto.
=M=duplicata. X=nao vinho. S=destilado. ??=nao sabe. NAO invente.

"""

# Sol 5: pedir ProdReal (quem FABRICA)
PROMPT_5 = """Exemplos do nosso banco:
  produtor: "chateau levangile"  vinho: "pomerol"
  produtor: "campo viejo"  vinho: "reserva rioja"
  produtor: "marchesi di gresy"  vinho: "camp gros martinenga barbaresco"
  produtor: "coppo"  vinho: "camp du rouss barbera dasti"

TODOS os itens. Uma linha por item. Sem markdown.

Formato:
1. X
2. S
3. W|ProdReal|VinhoBanco|Pais|Cor
4. W|ProdReal|VinhoBanco|Pais|Cor|=3

- ProdReal = quem FABRICA este vinho (a vinicola/bodega REAL, nao o nome do vinho ou da linha).
  Exemplos: "camp gros martinenga barbaresco" -> ProdReal = "marchesi di gresy" (nao "camp gros")
  "tignanello" -> ProdReal = "marchesi antinori" (nao "tignanello")
  Se nao sabe quem fabrica, use o nome que aparece no texto.
- VinhoBanco = vinho minusculo, sem acento
- Tudo minusculo, sem acento, l' junto, saint junto.
- =M=duplicata. X=nao vinho. S=destilado. ??=nao sabe. NAO invente.

"""

# Sol 8: passo 1 igual ao 3. Passo 2 e um prompt diferente so pra quem falhou.
PROMPT_8_STEP2 = """Para cada vinho abaixo, informe APENAS o nome da VINICOLA/BODEGA que fabrica este vinho.
Uma linha por item. Sem markdown. Se nao sabe, responda ??.

Formato:
1. nome da vinicola
2. ??
3. nome da vinicola

"""

# Mescla: prompt do Sol 5 (LLM da ProdReal) + busca do Sol 3 (texto_busca)
PROMPT_MESCLA = PROMPT_5  # mesmo prompt, busca diferente


# === HELPERS ===

def load(p):
    with open(p, encoding="utf-8") as f: return list(csv.DictReader(f))

def norm(s):
    s = s.lower().strip()
    for o,n in [("\u00e1","a"),("\u00e0","a"),("\u00e2","a"),("\u00e3","a"),("\u00e4","a"),
                ("\u00e9","e"),("\u00e8","e"),("\u00ea","e"),("\u00eb","e"),
                ("\u00ed","i"),("\u00ec","i"),("\u00ee","i"),("\u00ef","i"),
                ("\u00f3","o"),("\u00f2","o"),("\u00f4","o"),("\u00f5","o"),("\u00f6","o"),
                ("\u00fa","u"),("\u00f9","u"),("\u00fb","u"),("\u00fc","u"),
                ("\u00f1","n"),("\u00e7","c")]:
        s = s.replace(o,n)
    s = re.sub(r"['\u2019\u2018`]","",s)
    s = re.sub(r"-","",s)
    s = re.sub(r"[^a-z0-9 ]","",s)
    s = re.sub(r"\s+"," ",s).strip()
    return s

def parse(text):
    m = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line: continue
        p = line.split(". ", 1)
        if len(p)==2 and p[0].strip().isdigit():
            m[int(p[0].strip())] = p[1].strip()
    return m

def get_db():
    return psycopg2.connect(host="localhost",port=5432,dbname="winegod_db",
                            user="postgres",password="postgres123",
                            options="-c client_encoding=UTF8")

def call_llm_batches(model, prompt, items):
    all_lines = {}; sn = 1
    for bs in range(0, len(items), BATCH_SIZE):
        batch = items[bs:bs+BATCH_SIZE]
        txt = "\n".join(f"{sn+i}. {it['loja_nome']}" for i,it in enumerate(batch))
        for att in range(5):
            try:
                r = model.generate_content(prompt+txt,
                    generation_config=genai.types.GenerationConfig(temperature=0.1,max_output_tokens=4096))
                lines = parse(r.text.strip())
                if len(lines) >= len(batch)*0.7: break
            except: pass
            time.sleep(3)
        all_lines.update(lines)
        sn += len(batch)
        time.sleep(1.5)
    return all_lines

def extract_wines(all_lines, items):
    """Extrai vinhos W com produtor e vinho normalizados."""
    wines = []
    for i in range(len(items)):
        llm = all_lines.get(i+1,"")
        if not llm.startswith("W"): continue
        parts = llm.split("|")
        if len(parts)<5: continue
        prod = norm(parts[1].strip().split("=")[0].strip())
        vin = norm(parts[2].strip().split("=")[0].strip())
        is_dup = "=" in llm
        wines.append({"idx": i, "loja": items[i]["loja_nome"], "prod": prod, "vin": vin, "dup": is_dup})
    return wines


# === MATCH FUNCTIONS ===

def match_by_producer(cur, prod, vin):
    """Match padrao: pg_trgm no produtor."""
    cur.execute("""
        SELECT id, produtor_normalizado, nome_normalizado,
               similarity(produtor_normalizado,%s) as ps,
               similarity(nome_normalizado,%s) as ns
        FROM vivino_match WHERE produtor_normalizado %% %s
        ORDER BY similarity(produtor_normalizado,%s) DESC LIMIT 5
    """,(prod,vin,prod,prod))
    cands = cur.fetchall()
    if cands:
        best_sc = max(r[3]*0.5+r[4]*0.3 for r in cands)
        best_r = max(cands, key=lambda r: r[3]*0.5+r[4]*0.3)
        if best_sc >= THRESHOLD:
            return True, best_sc, f"{best_r[1]} - {best_r[2]}"
    return False, 0, ""

def match_by_texto_busca(cur, prod, vin, loja_nome):
    """Sol 3: pg_trgm no texto_busca (produtor+nome combinados)."""
    search = f"{prod} {vin}".strip()
    if len(search) < 4: return False, 0, ""
    cur.execute("""
        SELECT id, produtor_normalizado, nome_normalizado,
               similarity(texto_busca,%s) as ts
        FROM vivino_match WHERE texto_busca %% %s
        ORDER BY similarity(texto_busca,%s) DESC LIMIT 5
    """,(search,search,search))
    cands = cur.fetchall()
    if cands:
        best = cands[0]
        if best[3] >= 0.30:  # threshold mais baixo porque texto_busca e mais longo
            return True, best[3], f"{best[1]} - {best[2]}"
    # Fallback: nome original da loja
    loja_norm = norm(loja_nome)
    if len(loja_norm) >= 6:
        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(texto_busca,%s) as ts
            FROM vivino_match WHERE texto_busca %% %s
            ORDER BY similarity(texto_busca,%s) DESC LIMIT 3
        """,(loja_norm,loja_norm,loja_norm))
        cands2 = cur.fetchall()
        if cands2 and cands2[0][3] >= 0.30:
            return True, cands2[0][3], f"{cands2[0][1]} - {cands2[0][2]}"
    return False, 0, ""


def run_test(name, csv_file, prompt, match_fn, model):
    print(f"\n{'='*60}")
    print(f"TESTE: {name}")
    print(f"{'='*60}")

    items = load(os.path.join(SD, csv_file))
    print(f"Itens: {len(items)}")

    # LLM
    print("  LLM...", end=" ", flush=True)
    all_lines = call_llm_batches(model, prompt, items)
    wines = extract_wines(all_lines, items)
    uniq = [w for w in wines if not w["dup"]]
    dups = [w for w in wines if w["dup"]]
    responded = len(all_lines)
    print(f"resp={responded} W={len(wines)} uniq={len(uniq)} dup={len(dups)}")

    # Match
    conn = get_db(); cur = conn.cursor()
    ok = 0; no_m = 0; ex_ok = []; ex_no = []

    for w in uniq:
        found, sc, info = match_fn(cur, w["prod"], w["vin"], w["loja"])
        if found:
            ok += 1
            if len(ex_ok)<10: ex_ok.append((w["loja"][:35], f"{w['prod']}|{w['vin']}"[:30], info[:35], f"{sc:.2f}"))
        else:
            no_m += 1
            if len(ex_no)<10: ex_no.append((w["loja"][:40], f"{w['prod']}|{w['vin']}"[:25], f"sc={sc:.2f}"))

    conn.close()
    nu = len(uniq) or 1
    pct = ok*100//nu
    print(f"\n  UNICOS: {len(uniq)} | Match: {ok} ({pct}%) | Sem: {no_m} | Dup: {len(dups)}")
    print(f"\n  Matches:")
    for orig,llm_d,db,sc in ex_ok[:8]:
        print(f"    {orig:35} {llm_d:30} -> {db} ({sc})")
    print(f"  Sem match:")
    for orig,llm_d,sc in ex_no[:8]:
        print(f"    {orig:40} {llm_d:25} {sc}")

    return pct, len(uniq), len(dups), ok, responded, len(items)


def run_sol8(csv_file, model):
    """Sol 8: 2 passos."""
    print(f"\n{'='*60}")
    print(f"TESTE: Sol 8 (2 passos)")
    print(f"{'='*60}")

    items = load(os.path.join(SD, csv_file))
    print(f"Itens: {len(items)}")

    # Passo 1: classificar
    print("  Passo 1 (classificar)...", end=" ", flush=True)
    all_lines = call_llm_batches(model, PROMPT_3, items)
    wines = extract_wines(all_lines, items)
    uniq = [w for w in wines if not w["dup"]]
    dups = [w for w in wines if w["dup"]]
    print(f"W={len(wines)} uniq={len(uniq)} dup={len(dups)}")

    # Passo 1 match
    conn = get_db(); cur = conn.cursor()
    matched = []; failed = []
    for w in uniq:
        found, sc, info = match_by_producer(cur, w["prod"], w["vin"])
        if found:
            matched.append((w, sc, info))
        else:
            failed.append(w)

    print(f"  Passo 1 match: {len(matched)}/{len(uniq)} | Falharam: {len(failed)}")

    # Passo 2: LLM identifica produtor real dos que falharam
    if failed:
        print(f"  Passo 2 ({len(failed)} itens)...", end=" ", flush=True)
        failed_lines = {}; sn = 1
        for bs in range(0, len(failed), BATCH_SIZE):
            batch = failed[bs:bs+BATCH_SIZE]
            txt = "\n".join(f"{sn+i}. {f['loja']}" for i,f in enumerate(batch))
            for att in range(5):
                try:
                    r = model.generate_content(PROMPT_8_STEP2+txt,
                        generation_config=genai.types.GenerationConfig(temperature=0.1,max_output_tokens=2048))
                    lines = parse(r.text.strip())
                    if len(lines) >= len(batch)*0.5: break
                except: pass
                time.sleep(3)
            failed_lines.update(lines)
            sn += len(batch)
            time.sleep(1.5)

        # Re-match com produtor real
        extra_ok = 0
        ex_ok2 = []
        for i, w in enumerate(failed):
            prod_real = norm(failed_lines.get(i+1, "??"))
            if prod_real and prod_real != "??" and len(prod_real) >= 3:
                found, sc, info = match_by_producer(cur, prod_real, w["vin"])
                if found:
                    extra_ok += 1
                    matched.append((w, sc, info))
                    if len(ex_ok2)<8: ex_ok2.append((w["loja"][:35], f"{w['prod']}->{prod_real}"[:30], info[:30], f"{sc:.2f}"))

        print(f"match extra: +{extra_ok}")
        if ex_ok2:
            print(f"  Exemplos passo 2:")
            for orig,prod_change,db,sc in ex_ok2:
                print(f"    {orig:35} {prod_change:30} -> {db} ({sc})")

    conn.close()
    nu = len(uniq) or 1
    total_ok = len(matched)
    pct = total_ok*100//nu
    print(f"\n  RESULTADO: {total_ok}/{nu} ({pct}%) | Dup: {len(dups)}")
    return pct, len(uniq), len(dups), total_ok, len(all_lines), len(items)


def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)

    results = {}

    # Sol 3: texto_busca
    pct,uniq,dups,ok,resp,total = run_test("Sol 3: texto_busca", "teste_sol3.csv", PROMPT_3,
        lambda cur,p,v,l: match_by_texto_busca(cur,p,v,l), model)
    results["Sol 3 texto_busca"] = (pct,uniq,dups,ok)
    time.sleep(8)

    # Sol 5: ProdReal
    pct,uniq,dups,ok,resp,total = run_test("Sol 5: ProdReal", "teste_sol5.csv", PROMPT_5,
        lambda cur,p,v,l: match_by_producer(cur,p,v), model)
    results["Sol 5 ProdReal"] = (pct,uniq,dups,ok)
    time.sleep(8)

    # Sol 8: 2 passos
    pct,uniq,dups,ok,resp,total = run_sol8("teste_sol8.csv", model)
    results["Sol 8 dois passos"] = (pct,uniq,dups,ok)
    time.sleep(8)

    # Mescla: ProdReal + texto_busca
    def match_mescla(cur, prod, vin, loja):
        # Tentar primeiro por produtor
        found, sc, info = match_by_producer(cur, prod, vin)
        if found: return found, sc, info
        # Fallback: texto_busca
        return match_by_texto_busca(cur, prod, vin, loja)

    pct,uniq,dups,ok,resp,total = run_test("Mescla: ProdReal+texto", "teste_mescla.csv", PROMPT_MESCLA,
        match_mescla, model)
    results["Mescla ProdReal+texto"] = (pct,uniq,dups,ok)

    # Resumo
    print(f"\n\n{'='*60}")
    print("RANKING — 4 SOLUCOES")
    print(f"{'='*60}")
    for name,(pct,uniq,dups,ok) in sorted(results.items(), key=lambda x:-x[1][0]):
        bar = "#"*(pct//2)
        print(f"  {name:<30} {pct:>3}% ({ok}/{uniq} unicos, {dups} dup)  {bar}")


if __name__=="__main__":
    main()
