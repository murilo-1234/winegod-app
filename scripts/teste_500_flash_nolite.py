"""
Teste 500 itens com Flash (nao-lite), batch=20.
Correcao de nome + dedup + few-shot + pg_trgm.
"""
import csv, os, time, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
BATCH_SIZE = 20
SD = os.path.dirname(__file__)

PROMPT = """Exemplos do nosso banco:
  produtor: "chateau levangile"  vinho: "pomerol"
  produtor: "clos mogador"  vinho: "priorat"
  produtor: "bodega catena zapata"  vinho: "catena alta malbec"
  produtor: "penfolds"  vinho: "grange shiraz"

TODOS os itens devem ter resposta. Uma linha por item. Sem markdown.

Formato:
1. X
2. S
3. W|NomeCorrigido|ProdBanco|VinhoBanco|Pais|Cor
4. W|NomeCorrigido|ProdBanco|VinhoBanco|Pais|Cor|=3

- NomeCorrigido = nome OFICIAL corrigido (typos, abreviacoes expandidas, ex: "cab sauv"->"Cabernet Sauvignon")
- ProdBanco/VinhoBanco = minusculo, sem acento, l' junto, saint junto
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
    items = load(os.path.join(SD, "teste_500_flash.csv"))
    print(f"Itens: {len(items)}")

    all_lines = {}
    sn = 1
    total_batches = -(-len(items)//BATCH_SIZE)

    for bs in range(0, len(items), BATCH_SIZE):
        batch = items[bs:bs+BATCH_SIZE]
        txt = "\n".join(f"{sn+i}. {it['loja_nome']}" for i,it in enumerate(batch))

        batch_num = bs//BATCH_SIZE+1
        if batch_num % 5 == 1 or batch_num == total_batches:
            print(f"  Batch {batch_num}/{total_batches}...", end=" ", flush=True)

        for attempt in range(5):
            try:
                r = model.generate_content(PROMPT+txt,
                    generation_config=genai.types.GenerationConfig(temperature=0.1,max_output_tokens=4096))
                lines = parse(r.text.strip())
                if len(lines) >= len(batch)*0.7:
                    break
                if attempt < 4:
                    time.sleep(2)
            except Exception as e:
                if attempt < 4: time.sleep(3)

        all_lines.update(lines)

        if batch_num % 5 == 0 or batch_num == total_batches:
            resp_so_far = len(all_lines)
            w_so_far = sum(1 for v in all_lines.values() if v.startswith("W"))
            print(f"progresso: {resp_so_far}/{sn+len(batch)-1} resp, {w_so_far} W")

        sn += len(batch)
        time.sleep(1)

    # Stats
    total = len(items)
    responded = len(all_lines)
    wines = [k for k,v in all_lines.items() if v.startswith("W")]
    dups = [k for k,v in all_lines.items() if "=" in v and v.startswith("W")]
    notwine = sum(1 for v in all_lines.values() if v.startswith("X"))
    spirits = sum(1 for v in all_lines.values() if v.startswith("S"))

    print(f"\n{'='*60}")
    print(f"COMPLETUDE: {responded}/{total} ({responded*100//total}%)")
    print(f"W={len(wines)} X={notwine} S={spirits}")
    print(f"DUPLICATAS MARCADAS: {len(dups)}")

    # Mostrar correcoes
    print(f"\n--- CORRECOES DE NOME (primeiros 20 W) ---")
    count = 0
    for i in range(total):
        llm = all_lines.get(i+1,"")
        if not llm.startswith("W"): continue
        parts = llm.split("|")
        nome_corrigido = parts[1] if len(parts)>1 else "?"
        original = items[i]['loja_nome']
        if original.lower().strip() != nome_corrigido.lower().strip():
            print(f"  {original[:40]:40} -> {nome_corrigido[:40]}")
            count += 1
            if count >= 20: break

    # Mostrar duplicatas
    print(f"\n--- DUPLICATAS MARCADAS (todos) ---")
    dup_count = 0
    for i in range(total):
        llm = all_lines.get(i+1,"")
        if "=" in llm and llm.startswith("W"):
            print(f"  #{i+1} {items[i]['loja_nome'][:45]:45} -> {llm[-15:]}")
            dup_count += 1
            if dup_count >= 30:
                remaining = len(dups) - 30
                if remaining > 0: print(f"  ... +{remaining} mais")
                break

    # Match pg_trgm
    print(f"\n--- MATCH VIVINO (pg_trgm) ---")
    conn = get_db(); cur = conn.cursor()
    ok = 0; no_m = 0

    for i in range(total):
        llm = all_lines.get(i+1,"")
        if not llm.startswith("W"): continue
        parts = llm.split("|")
        if len(parts)<6: no_m+=1; continue
        prod = norm(parts[2].strip().split("=")[0].strip())
        vin = norm(parts[3].strip().split("=")[0].strip())
        if not prod or prod=="??" or len(prod)<2: no_m+=1; continue

        cur.execute("""
            SELECT similarity(produtor_normalizado,%s)*0.5 + similarity(nome_normalizado,%s)*0.3 as sc
            FROM vivino_match WHERE produtor_normalizado %% %s
            ORDER BY similarity(produtor_normalizado,%s) DESC LIMIT 1
        """,(prod,vin,prod,prod))
        row = cur.fetchone()
        if row and row[0] >= 0.35: ok+=1
        else: no_m+=1

    conn.close()
    pct = ok*100//len(wines) if wines else 0
    print(f"  Match: {ok}/{len(wines)} ({pct}%)")

    print(f"\n{'='*60}")
    print(f"RESUMO FINAL")
    print(f"  Completude: {responded}/{total} ({responded*100//total}%)")
    print(f"  Vinhos: {len(wines)}")
    print(f"  Duplicatas: {len(dups)}")
    print(f"  Match Vivino: {ok}/{len(wines)} ({pct}%)")

if __name__=="__main__":
    main()
