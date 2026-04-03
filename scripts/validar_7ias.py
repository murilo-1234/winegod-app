"""Validar 50 aleatorios de cada IA contra Vivino."""
import sys, re, random, os
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

def parse_file(path):
    """Parseia arquivo de resposta. Retorna dict {num: {class, prod, vin, dup}}."""
    items = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            p = line.split(". ", 1)
            if len(p) < 2: continue
            try: num = int(p[0].strip())
            except: continue
            content = p[1].strip()

            if content == "X":
                items[num] = {"class": "X"}
            elif content == "S":
                items[num] = {"class": "S"}
            elif content.startswith("W|") or content.startswith("W |"):
                fields = content.split("|")
                is_dup = "=" in content
                prod = fields[1].strip() if len(fields) > 1 else "??"
                vin = fields[2].strip() if len(fields) > 2 else "??"
                # Limpar =N do final
                prod = prod.split("=")[0].strip()
                vin = vin.split("=")[0].strip()
                items[num] = {"class": "W", "prod": prod, "vin": vin, "dup": is_dup}
            else:
                items[num] = {"class": "?", "raw": content[:50]}
    return items

# Nomes originais
nomes = []
with open("C:/winegod-app/scripts/lote_1000.txt", encoding="utf-8") as f:
    nomes = [l.strip() for l in f if l.strip()]

# Conexao DB
conn = psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                        user="postgres", password="postgres123",
                        options="-c client_encoding=UTF8")
cur = conn.cursor()

# Arquivos
DIR = "C:/winegod-app/scripts/lotes_llm"
files = {
    "Grok": "lotegrok.txt",
    "ChatGPT": "lotechatgpt.txt",
    "Claude 4.5": "loteclaude4.5.txt",
    "Gemini": "lotegemini.txt",
    "Gemini+Dedup": "lotegemini-com-dedup.txt",
    "Mistral": "lotemistral.txt",
    "Qwen": "loteqwen.txt",
}

random.seed(42)
results = {}

for ia_name, filename in files.items():
    path = os.path.join(DIR, filename)
    if not os.path.exists(path):
        print(f"{ia_name}: ARQUIVO NAO ENCONTRADO")
        continue

    parsed = parse_file(path)
    total_lines = len(parsed)

    # Contar tipos
    w_count = sum(1 for v in parsed.values() if v["class"] == "W")
    x_count = sum(1 for v in parsed.values() if v["class"] == "X")
    s_count = sum(1 for v in parsed.values() if v["class"] == "S")
    dup_count = sum(1 for v in parsed.values() if v["class"] == "W" and v.get("dup"))
    err_count = sum(1 for v in parsed.values() if v["class"] == "?")

    # Pegar 50 W aleatorios (sem duplicatas)
    w_uniq = {k: v for k, v in parsed.items() if v["class"] == "W" and not v.get("dup")}
    sample_keys = random.sample(list(w_uniq.keys()), min(50, len(w_uniq)))

    match_ok = 0
    match_fail = 0

    for num in sample_keys:
        w = w_uniq[num]
        prod = norm(w["prod"])
        vin = norm(w["vin"])
        search = f"{prod} {vin}".strip()

        if not prod or prod == "??" or len(search) < 4:
            match_fail += 1
            continue

        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(texto_busca, %s) as ts
            FROM vivino_match WHERE texto_busca %% %s
            ORDER BY similarity(texto_busca, %s) DESC LIMIT 1
        """, (search, search, search))
        cand = cur.fetchone()

        if cand and cand[3] >= 0.30:
            match_ok += 1
        else:
            match_fail += 1

    pct = match_ok * 100 // max(len(sample_keys), 1)
    results[ia_name] = {
        "total": total_lines, "w": w_count, "x": x_count, "s": s_count,
        "dup": dup_count, "err": err_count, "uniq": len(w_uniq),
        "sample": len(sample_keys), "match": match_ok, "pct": pct
    }

conn.close()

# Ranking
print(f"\n{'='*80}")
print(f"RANKING — 7 IAs — 50 aleatorios de cada")
print(f"{'='*80}")
print(f"")
print(f"{'IA':<16} {'Total':>6} {'W':>5} {'X':>5} {'S':>4} {'Dup':>5} {'Uniq':>5} {'Amostra':>8} {'Match':>6} {'%':>5}")
print(f"{'-'*80}")

for name, r in sorted(results.items(), key=lambda x: -x[1]["pct"]):
    print(f"{name:<16} {r['total']:>6} {r['w']:>5} {r['x']:>5} {r['s']:>4} {r['dup']:>5} {r['uniq']:>5} {r['sample']:>8} {r['match']:>6} {r['pct']:>4}%")

print(f"\n{'='*80}")
print(f"CONCLUSAO")
print(f"{'='*80}")
best = max(results.items(), key=lambda x: x[1]["pct"])
print(f"Melhor: {best[0]} ({best[1]['pct']}% match)")
worst = min(results.items(), key=lambda x: x[1]["pct"])
print(f"Pior:   {worst[0]} ({worst[1]['pct']}% match)")
