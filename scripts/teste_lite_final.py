"""
Teste DEFINITIVO: Flash-Lite + prompt corrigido + few-shot + pg_trgm.
3 lotes de 300, batch=100.
"""
import csv, os, time, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-lite"
BATCH_SIZE = 100
SD = os.path.dirname(__file__)

PROMPT = """Exemplos do formato do nosso banco:
  produtor: "chateau levangile"     vinho: "blason de levangile pomerol"
  produtor: "domaine de la romanee conti"  vinho: "romanee conti grand cru"
  produtor: "bodega catena zapata"  vinho: "catena alta malbec"
  produtor: "tenuta san guido"      vinho: "sassicaia"
  produtor: "penfolds"              vinho: "grange shiraz"
  produtor: "joseph phelps vineyards"  vinho: "insignia"

Para cada item numerado, responda no MESMO numero. TODOS os itens devem ter resposta. Uma linha por item. Sem markdown.

Formato exato:
1. X
2. S
3. W|NomeCorrigido|ProdBanco|VinhoBanco|Pais|Cor
4. W|NomeCorrigido|ProdBanco|VinhoBanco|Pais|Cor|=3

X=nao vinho. S=destilado. W=vinho.
- NomeCorrigido = nome oficial corrigido (typos, abreviacoes)
- ProdBanco = produtor formato banco: minusculo, sem acento, l' junto, saint junto
- VinhoBanco = vinho formato banco: mesma regra
- Pais=2 letras. Cor: r/w/p/s/f/d. =M=duplicata de M. ??=nao sabe.
Se comeca com regiao (val de loire, cotes du rhone), produtor esta DEPOIS.
NAO invente. Sem sentido = X.

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

def call_batch(model, items, sn):
    txt = "\n".join(f"{sn+i}. {it['loja_nome']}" for i,it in enumerate(items))
    for attempt in range(5):
        try:
            r = model.generate_content(PROMPT+txt,
                generation_config=genai.types.GenerationConfig(temperature=0.1,max_output_tokens=8192))
            lines = parse(r.text.strip())
            if len(lines) >= len(items)*0.5:
                return lines, len(lines), attempt+1
            print(f"(parcial {len(lines)}/{len(items)}, retry {attempt+1})", end=" ", flush=True)
        except Exception as e:
            print(f"(erro, retry {attempt+1})", end=" ", flush=True)
        time.sleep(3)
    return {}, 0, 5

def run_lote(name, csv_f, model):
    print(f"\n{'='*60}")
    print(f"LOTE {name}")
    print(f"{'='*60}")
    items = load(os.path.join(SD, csv_f))
    print(f"Itens: {len(items)}")

    all_lines = {}; sn = 1
    for bs in range(0, len(items), BATCH_SIZE):
        batch = items[bs:bs+BATCH_SIZE]
        print(f"  Batch {bs//BATCH_SIZE+1}/{-(-len(items)//BATCH_SIZE)} ...", end=" ", flush=True)
        lines, resp, att = call_batch(model, batch, sn)
        w=sum(1 for v in lines.values() if v.startswith("W"))
        x=sum(1 for v in lines.values() if v.startswith("X"))
        s=sum(1 for v in lines.values() if v.startswith("S") and "W|" not in v)
        dup=sum(1 for v in lines.values() if "=" in v)
        miss=len(batch)-resp
        all_lines.update(lines)
        r_str = f" (retries={att-1})" if att>1 else ""
        print(f"resp={resp} W={w} X={x} S={s} dup={dup} miss={miss}{r_str}")
        sn += len(batch)
        time.sleep(2)

    total=len(items); responded=len(all_lines)
    wines=sum(1 for v in all_lines.values() if v.startswith("W"))
    dups=sum(1 for v in all_lines.values() if "=" in v)
    print(f"\n  Completude: {responded}/{total} ({responded*100//total}%)")
    print(f"  W={wines} Dup={dups}")

    if wines==0:
        return 0, 0, dups, responded, total

    conn=get_db(); cur=conn.cursor()
    ok=0; no_m=0; ex_ok=[]; ex_no=[]

    for i in range(total):
        llm=all_lines.get(i+1,"")
        if not llm.startswith("W"): continue
        parts=llm.split("|")
        if len(parts)<6: no_m+=1; continue
        prod=norm(parts[2].strip().split("=")[0].strip())
        vin=norm(parts[3].strip().split("=")[0].strip())
        if not prod or prod=="??" or len(prod)<2:
            no_m+=1
            if len(ex_no)<8: ex_no.append((items[i]['loja_nome'][:35],"sem produtor"))
            continue
        cur.execute("""
            SELECT id,produtor_normalizado,nome_normalizado,
                   similarity(produtor_normalizado,%s) as ps,
                   similarity(nome_normalizado,%s) as ns
            FROM vivino_match WHERE produtor_normalizado %% %s
            ORDER BY similarity(produtor_normalizado,%s) DESC LIMIT 15
        """,(prod,vin,prod,prod))
        cands=cur.fetchall()
        if cands:
            best_sc=max(c[3]*0.5+c[4]*0.3 for c in cands)
            best_info = ""
            for c in cands:
                if c[3]*0.5+c[4]*0.3 == best_sc:
                    best_info = f"{c[1]} - {c[2]}"
                    break
            if best_sc>=0.35:
                ok+=1
                if len(ex_ok)<10: ex_ok.append((items[i]['loja_nome'][:30],parts[1][:22],best_info[:30],f"{best_sc:.2f}"))
            else:
                no_m+=1
                if len(ex_no)<8: ex_no.append((items[i]['loja_nome'][:35],f"score={best_sc:.2f}"))
        else:
            no_m+=1
            if len(ex_no)<8: ex_no.append((items[i]['loja_nome'][:35],"nao encontrado"))

    conn.close()
    pct=ok*100//wines if wines else 0
    print(f"  Match: {ok}/{wines} ({pct}%)")
    if ex_ok:
        print(f"\n  Matches:")
        for orig,corr,db,sc in ex_ok[:8]:
            print(f"    {orig:30} -> {corr:22} -> {db} ({sc})")
    if ex_no:
        print(f"  Sem match:")
        for orig,motivo in ex_no[:5]:
            print(f"    {orig:35} {motivo}")
    return pct, wines, dups, responded, total

def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)
    lotes = [("beau-ben","teste_lite2_1.csv"),("fal-far","teste_lite2_2.csv"),("tav-ter","teste_lite2_3.csv")]
    tw=0;tok=0;tdup=0;tresp=0;ttotal=0
    results={}
    for name,csv_f in lotes:
        pct,wines,dups,resp,total = run_lote(name,csv_f,model)
        results[name]=(pct,wines,dups,resp,total)
        tw+=wines;tok+=int(wines*pct/100);tdup+=dups;tresp+=resp;ttotal+=total
        time.sleep(5)
    print(f"\n\n{'='*60}")
    print("RESULTADO FINAL")
    print(f"{'='*60}")
    for name,(pct,wines,dups,resp,total) in results.items():
        bar="#"*(pct//2)
        print(f"  {name:<15} Match={pct:>3}% W={wines:>3} Dup={dups:>2} {resp}/{total}  {bar}")
    avg=tok*100//tw if tw else 0
    print(f"\n  {'TOTAL':<15} Match={avg:>3}% W={tw:>3} Dup={tdup:>2} {tresp}/{ttotal}")

if __name__=="__main__":
    main()
