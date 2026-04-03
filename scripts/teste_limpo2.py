"""
Teste limpo v2: sem NomeCorrigido, threshold 0.45, batch=20, Flash nao-lite.
300 itens novos (camp-car).
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

PROMPT = """Exemplos do nosso banco:
  produtor: "chateau levangile"  vinho: "pomerol"
  produtor: "campo viejo"  vinho: "reserva rioja"
  produtor: "bodega catena zapata"  vinho: "catena alta malbec"
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
    items = load(os.path.join(SD, "teste_limpo2_300.csv"))
    print(f"Itens: {len(items)}\n")

    all_lines = {}; sn = 1
    total_b = -(-len(items)//BATCH_SIZE)

    for bs in range(0, len(items), BATCH_SIZE):
        batch = items[bs:bs+BATCH_SIZE]
        txt = "\n".join(f"{sn+i}. {it['loja_nome']}" for i,it in enumerate(batch))
        bn = bs//BATCH_SIZE+1

        if bn % 3 == 1 or bn == total_b:
            print(f"  Batch {bn}/{total_b} ...", end=" ", flush=True)

        for att in range(5):
            try:
                r = model.generate_content(PROMPT+txt,
                    generation_config=genai.types.GenerationConfig(temperature=0.1,max_output_tokens=4096))
                lines = parse(r.text.strip())
                if len(lines) >= len(batch)*0.7: break
                if att < 4: time.sleep(3)
            except:
                if att < 4: time.sleep(3)

        all_lines.update(lines)

        if bn % 3 == 0 or bn == total_b:
            r_sf = len(all_lines)
            w_sf = sum(1 for v in all_lines.values() if v.startswith("W"))
            d_sf = sum(1 for v in all_lines.values() if "=" in v and v.startswith("W"))
            print(f"progresso: {r_sf}/{sn+len(batch)-1} resp, W={w_sf}, dup={d_sf}")

        sn += len(batch)
        time.sleep(1.5)

    total = len(items)
    responded = len(all_lines)
    wines_idx = [k for k,v in all_lines.items() if v.startswith("W")]
    dups_idx = [k for k,v in all_lines.items() if "=" in v and v.startswith("W")]
    notwine = sum(1 for v in all_lines.values() if v.startswith("X"))
    spirits = sum(1 for v in all_lines.values() if v.startswith("S"))

    print(f"\n{'='*60}")
    print(f"COMPLETUDE: {responded}/{total} ({responded*100//total}%)")
    print(f"W={len(wines_idx)} X={notwine} S={spirits} Dup={len(dups_idx)}")

    # Duplicatas
    if dups_idx:
        print(f"\n--- DUPLICATAS ({len(dups_idx)}) ---")
        for k in dups_idx[:25]:
            orig = items[k-1]['loja_nome'][:45]
            ref = all_lines[k].split("=")[-1] if "=" in all_lines[k] else "?"
            # Achar o item referenciado
            ref_num = int(ref) if ref.isdigit() else 0
            ref_nome = items[ref_num-1]['loja_nome'][:40] if ref_num > 0 and ref_num <= total else "?"
            print(f"  #{k:>3} {orig:45} = #{ref_num} {ref_nome}")
        if len(dups_idx) > 25:
            print(f"  ... +{len(dups_idx)-25} mais")

    # Match pg_trgm
    print(f"\n--- MATCH VIVINO (threshold={THRESHOLD}) ---")
    conn = get_db(); cur = conn.cursor()
    ok = 0; no_m = 0; ex_ok = []; ex_no = []

    for i in range(total):
        llm = all_lines.get(i+1,"")
        if not llm.startswith("W"): continue
        parts = llm.split("|")
        if len(parts)<5: no_m+=1; continue
        prod = norm(parts[1].strip().split("=")[0].strip())
        vin = norm(parts[2].strip().split("=")[0].strip())
        if not prod or prod=="??" or len(prod)<2:
            no_m+=1; continue

        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(produtor_normalizado,%s) as ps,
                   similarity(nome_normalizado,%s) as ns
            FROM vivino_match WHERE produtor_normalizado %% %s
            ORDER BY similarity(produtor_normalizado,%s) DESC LIMIT 5
        """,(prod,vin,prod,prod))
        cands = cur.fetchall()
        if cands:
            best_sc=0; best_r=None
            for r in cands:
                sc = r[3]*0.5 + r[4]*0.3
                if sc > best_sc: best_sc=sc; best_r=r
            if best_sc >= THRESHOLD:
                ok+=1
                if len(ex_ok)<15:
                    ex_ok.append((items[i]['loja_nome'][:35], f"{prod}|{vin}"[:30], f"{best_r[1]} - {best_r[2]}"[:35], f"{best_sc:.2f}"))
            else:
                no_m+=1
                if len(ex_no)<10: ex_no.append((items[i]['loja_nome'][:40], f"sc={best_sc:.2f} -> {best_r[1][:15]}"))
        else:
            no_m+=1
            if len(ex_no)<10: ex_no.append((items[i]['loja_nome'][:40], "nao encontrado"))

    conn.close()
    nw = len(wines_idx)
    pct = ok*100//nw if nw else 0

    print(f"  Match: {ok}/{nw} ({pct}%) | Sem: {no_m}")
    print(f"\n  Matches:")
    for orig,llm_d,db,sc in ex_ok[:15]:
        print(f"    {orig:35} {llm_d:30} -> {db} ({sc})")
    print(f"\n  Sem match:")
    for orig,motivo in ex_no[:10]:
        print(f"    {orig:40} {motivo}")

    # Vinhos unicos apos dedup
    uniq_wines = nw - len(dups_idx)
    print(f"\n{'='*60}")
    print(f"RESUMO FINAL")
    print(f"  Completude:    {responded}/{total} ({responded*100//total}%)")
    print(f"  Vinhos:        {nw}")
    print(f"  Duplicatas:    {len(dups_idx)}")
    print(f"  Vinhos unicos: {uniq_wines}")
    print(f"  Match Vivino:  {ok}/{nw} ({pct}%)")

if __name__=="__main__":
    main()
