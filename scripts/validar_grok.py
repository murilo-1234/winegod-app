"""Validar resposta do Grok (1000 itens) contra Vivino."""
import sys, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import psycopg2

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

# Ler resposta Grok
with open("C:/winegod-app/scripts/lotegrok.txt", encoding="utf-8") as f:
    grok_lines = f.readlines()

# Ler nomes originais
with open("C:/winegod-app/scripts/lote_1000.txt", encoding="utf-8") as f:
    nomes = [l.strip() for l in f if l.strip()]

# Parsear
wines = 0; not_wine = 0; spirits = 0; dups = 0; errs = 0
w_items = []

for line in grok_lines:
    line = line.strip()
    if not line: continue
    parts = line.split(". ", 1)
    if len(parts) < 2: continue
    try: num = int(parts[0].strip())
    except: continue
    content = parts[1].strip()

    if content == "X": not_wine += 1
    elif content == "S": spirits += 1
    elif content.startswith("W|"):
        wines += 1
        is_dup = "=" in content
        if is_dup: dups += 1
        fields = content.split("|")
        if len(fields) >= 5:
            w_items.append({
                "num": num,
                "prod": fields[1].strip(),
                "vin": fields[2].strip(),
                "orig": nomes[num-1] if num <= len(nomes) else "?",
                "dup": is_dup
            })
    else: errs += 1

total = wines + not_wine + spirits + errs
print(f"RESUMO GROK — {len(grok_lines)} linhas")
print(f"=" * 50)
print(f"Vinhos (W):    {wines} ({wines*100//(total or 1)}%)")
print(f"Nao-vinho (X): {not_wine} ({not_wine*100//(total or 1)}%)")
print(f"Destilados (S):{spirits} ({spirits*100//(total or 1)}%)")
print(f"Duplicatas:    {dups}")
print(f"Vinhos unicos: {wines - dups}")
print(f"Erros parse:   {errs}")
print()

# Validar contra Vivino
conn = psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                        user="postgres", password="postgres123",
                        options="-c client_encoding=UTF8")
cur = conn.cursor()

uniq = [w for w in w_items if not w["dup"]]
match_ok = 0; match_wrong = 0; match_fail = 0
ex_ok = []; ex_wrong = []; ex_fail = []

for w in uniq:
    prod = norm(w["prod"])
    vin = norm(w["vin"])
    search = f"{prod} {vin}".strip()

    if not prod or prod == "??" or len(search) < 4:
        match_fail += 1
        if len(ex_fail) < 10: ex_fail.append((w["orig"][:40], w["prod"], w["vin"], "sem dados"))
        continue

    cur.execute("""
        SELECT id, produtor_normalizado, nome_normalizado,
               similarity(texto_busca, %s) as ts
        FROM vivino_match WHERE texto_busca %% %s
        ORDER BY similarity(texto_busca, %s) DESC LIMIT 1
    """, (search, search, search))
    cand = cur.fetchone()

    if cand and cand[3] >= 0.30:
        prod_w = set(prod.split()) - {"de","du","la","le","les","des","del","di","the","et","fils","domaine","chateau","maison"}
        db_w = set(cand[1].split()) - {"de","du","la","le","les","des","del","di","the","et","fils","domaine","chateau","maison"}
        overlap = len(prod_w & db_w)

        if overlap >= 1 or cand[3] >= 0.50:
            match_ok += 1
            if len(ex_ok) < 15: ex_ok.append((w["orig"][:35], f'{w["prod"]}|{w["vin"]}'[:30], f'{cand[1]} - {cand[2]}'[:35], f'{cand[3]:.2f}'))
        else:
            match_wrong += 1
            if len(ex_wrong) < 15: ex_wrong.append((w["orig"][:35], f'{w["prod"]}|{w["vin"]}'[:30], f'{cand[1]} - {cand[2]}'[:35], f'{cand[3]:.2f}'))
    else:
        match_fail += 1
        if len(ex_fail) < 10: ex_fail.append((w["orig"][:40], w["prod"], w["vin"], "nao encontrado"))

conn.close()

nu = len(uniq) or 1
print(f"VALIDACAO VIVINO — {len(uniq)} vinhos unicos")
print(f"=" * 50)
print(f"MATCH CORRETO:  {match_ok} ({match_ok*100//nu}%)")
print(f"MATCH ERRADO:   {match_wrong} ({match_wrong*100//nu}%)")
print(f"SEM MATCH:      {match_fail} ({match_fail*100//nu}%)")
print()
print(f"PRO RENDER:")
print(f"  Com vivino_id:  {match_ok}")
print(f"  Vinhos novos:   {match_fail}")
print(f"  Descartados:    {match_wrong}")
print(f"  Duplicatas:     {dups}")
print(f"  Nao-vinhos:     {not_wine}")
print(f"  Destilados:     {spirits}")

print(f"\n--- MATCH CORRETO (15 ex) ---")
for orig,llm,db,sc in ex_ok:
    print(f"  {orig:35} {llm:30} -> {db} ({sc})")

print(f"\n--- MATCH ERRADO ({match_wrong}, 15 ex) ---")
for orig,llm,db,sc in ex_wrong:
    print(f"  {orig:35} {llm:30} -> {db} ({sc})")

print(f"\n--- SEM MATCH ({match_fail}, 10 ex) ---")
for orig,prod,vin,m in ex_fail:
    print(f"  {orig:40} {prod}|{vin} -- {m}")
