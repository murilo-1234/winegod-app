"""
Teste limpo: sem NomeCorrigido, threshold 0.45, batch=50, Flash nao-lite.
"""
import csv, os, time, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
BATCH_SIZE = 50
THRESHOLD = 0.45
SD = os.path.dirname(__file__)

PROMPT = """Exemplos do nosso banco:
  produtor: "chateau levangile"  vinho: "pomerol"
  produtor: "marques de murrieta"  vinho: "castillo ygay gran reserva especial rioja"
  produtor: "bodega catena zapata"  vinho: "catena alta malbec"
  produtor: "tenuta san guido"  vinho: "sassicaia"
  produtor: "penfolds"  vinho: "grange shiraz"

TODOS os itens. Uma linha por item. Sem markdown.

Formato:
1. X
2. S
3. W|ProdBanco|VinhoBanco|Pais|Cor
4. W|ProdBanco|VinhoBanco|Pais|Cor|=3

- ProdBanco = produtor minusculo, sem acento, l' junto, saint junto
- VinhoBanco = vinho minusculo, sem acento, mesma regra
- =M = duplicata de M (mesmo vinho, safra/formato diferente)
- X=nao vinho. S=destilado. Pais=2 letras. Cor: r/w/p/s/f/d. ??=nao sabe. NAO invente.

"""

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

def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)
    items = load(os.path.join(SD, "teste_limpo_300.csv"))
    print(f"Itens: {len(items)}\n")

    all_lines = {}; sn = 1
    total_b = -(-len(items)//BATCH_SIZE)

    for bs in range(0, len(items), BATCH_SIZE):
        batch = items[bs:bs+BATCH_SIZE]
        txt = "\n".join(f"{sn+i}. {it['loja_nome']}" for i,it in enumerate(batch))
        bn = bs//BATCH_SIZE+1
        print(f"  Batch {bn}/{total_b} ...", end=" ", flush=True)

        for att in range(5):
            try:
                r = model.generate_content(PROMPT+txt,
                    generation_config=genai.types.GenerationConfig(temperature=0.1,max_output_tokens=4096))
                lines = parse(r.text.strip())
                if len(lines) >= len(batch)*0.7: break
                print(f"(parcial {len(lines)}/{len(batch)}, retry)", end=" ", flush=True)
            except Exception as e:
                print(f"(erro, retry)", end=" ", flush=True)
            time.sleep(3)

        w = sum(1 for v in lines.values() if v.startswith("W"))
        x = sum(1 for v in lines.values() if v.startswith("X"))
        s = sum(1 for v in lines.values() if v.startswith("S") and "W|" not in v)
        dup = sum(1 for v in lines.values() if "=" in v)
        miss = len(batch) - len(lines)
        all_lines.update(lines)
        print(f"resp={len(lines)} W={w} X={x} S={s} dup={dup} miss={miss}")
        sn += len(batch)
        time.sleep(2)

    # Stats
    total = len(items)
    responded = len(all_lines)
    wines_idx = [k for k,v in all_lines.items() if v.startswith("W")]
    dups_idx = [k for k,v in all_lines.items() if "=" in v and v.startswith("W")]

    print(f"\n{'='*60}")
    print(f"COMPLETUDE: {responded}/{total} ({responded*100//total}%)")
    print(f"W={len(wines_idx)} | Dup={len(dups_idx)}")

    # Duplicatas
    if dups_idx:
        print(f"\n--- DUPLICATAS ({len(dups_idx)}) ---")
        for k in dups_idx[:20]:
            print(f"  #{k} {items[k-1]['loja_nome'][:45]:45} -> {all_lines[k][-20:]}")
        if len(dups_idx) > 20:
            print(f"  ... +{len(dups_idx)-20} mais")

    # Match pg_trgm com threshold 0.45
    print(f"\n--- MATCH VIVINO (threshold={THRESHOLD}) ---")
    conn = get_db(); cur = conn.cursor()
    ok = 0; no_m = 0
    ex_ok = []; ex_no = []; ex_wrong = []

    for i in range(total):
        llm = all_lines.get(i+1,"")
        if not llm.startswith("W"): continue
        parts = llm.split("|")
        if len(parts)<5: no_m+=1; continue
        prod = norm(parts[1].strip().split("=")[0].strip())
        vin = norm(parts[2].strip().split("=")[0].strip())
        if not prod or prod=="??" or len(prod)<2:
            no_m+=1
            if len(ex_no)<5: ex_no.append((items[i]['loja_nome'][:40], "sem produtor"))
            continue

        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(produtor_normalizado,%s) as ps,
                   similarity(nome_normalizado,%s) as ns
            FROM vivino_match WHERE produtor_normalizado %% %s
            ORDER BY similarity(produtor_normalizado,%s) DESC LIMIT 5
        """,(prod,vin,prod,prod))
        cands = cur.fetchall()

        if cands:
            best_sc = 0; best_r = None
            for r in cands:
                sc = r[3]*0.5 + r[4]*0.3
                if sc > best_sc: best_sc=sc; best_r=r
            if best_sc >= THRESHOLD:
                ok+=1
                prod_match = prod in best_r[1] or best_r[1] in prod
                if len(ex_ok)<15:
                    ex_ok.append((items[i]['loja_nome'][:35], f"{prod}|{vin}", f"{best_r[1]} - {best_r[2]}", f"{best_sc:.2f}", "PROD_OK" if prod_match else "PROD_??"))
            else:
                no_m+=1
                if len(ex_no)<8: ex_no.append((items[i]['loja_nome'][:40], f"score={best_sc:.2f} best={best_r[1][:15]}"))
        else:
            no_m+=1
            if len(ex_no)<8: ex_no.append((items[i]['loja_nome'][:40], "nao encontrado"))

    conn.close()
    nw = len(wines_idx)
    pct = ok*100//nw if nw else 0

    print(f"  Match: {ok}/{nw} ({pct}%) | Sem: {no_m}")

    print(f"\n  Matches (top 15):")
    for orig, llm_data, db, sc, prod_ok in ex_ok:
        print(f"    {orig:35} LLM:{llm_data[:25]:25} DB:{db[:30]:30} {sc} {prod_ok}")

    print(f"\n  Sem match (top 8):")
    for orig, motivo in ex_no:
        print(f"    {orig:40} {motivo}")

    print(f"\n{'='*60}")
    print(f"RESUMO")
    print(f"  Completude: {responded}/{total} ({responded*100//total}%)")
    print(f"  Vinhos: {nw}")
    print(f"  Duplicatas: {len(dups_idx)}")
    print(f"  Match (threshold {THRESHOLD}): {ok}/{nw} ({pct}%)")

if __name__=="__main__":
    main()
