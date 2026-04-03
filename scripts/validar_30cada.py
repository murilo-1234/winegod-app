"""Validar 30 W aleatorios de cada IA contra Vivino."""
import sys, re, random, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import psycopg2

DIR = "C:/Users/muril/OneDrive/Documentos/Programa\u00e7\u00e3o/lotes-llm-db"

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

def parse_w_items(path):
    """Extrai todos os W de qualquer formato."""
    items = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            # Remover numero do inicio se tiver
            m = re.match(r'^\d+\.\s*', line)
            if m:
                line = line[m.end():]
            # Checar se e W
            if not line.startswith("W|") and not line.startswith("W |"):
                continue
            fields = line.split("|")
            if len(fields) < 5: continue
            prod = fields[1].strip().split("=")[0].strip()
            vin = fields[2].strip().split("=")[0].strip()
            is_dup = "=" in line
            if prod and prod != "??" and vin and not is_dup:
                items.append({"prod": prod, "vin": vin})
    return items

conn = psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                        user="postgres", password="postgres123",
                        options="-c client_encoding=UTF8")
cur = conn.cursor()

files = {
    "ChatGPT": "lotechatgpt.txt",
    "Claude 4.5": "loteclaude4.5.txt",
    "Gemini": "lotegemini.txt",
    "Gemini+Dedup": "lotegemini-com-dedup.txt",
    "Grok": "lotegrok.txt",
    "Mistral": "lotemistral.txt",
    "Qwen": "loteqwen.txt",
}

random.seed(42)
results = {}

for ia, fname in files.items():
    path = os.path.join(DIR, fname)
    all_w = parse_w_items(path)
    total_w = len(all_w)

    if total_w == 0:
        print(f"{ia}: 0 vinhos encontrados no arquivo")
        results[ia] = {"total_w": 0, "sample": 0, "match": 0, "pct": 0}
        continue

    sample = random.sample(all_w, min(30, total_w))
    match_ok = 0

    for w in sample:
        prod = norm(w["prod"])
        vin = norm(w["vin"])
        search = f"{prod} {vin}".strip()
        if len(search) < 4:
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

    pct = match_ok * 100 // len(sample)
    results[ia] = {"total_w": total_w, "sample": len(sample), "match": match_ok, "pct": pct}
    print(f"{ia}: {total_w} W total | amostra {len(sample)} | match {match_ok} ({pct}%)")

conn.close()

print(f"\n{'='*60}")
print(f"RANKING — 30 aleatorios de cada IA")
print(f"{'='*60}")
print(f"{'IA':<16} {'W total':>8} {'Amostra':>8} {'Match':>6} {'%':>5}")
print(f"{'-'*45}")
for name, r in sorted(results.items(), key=lambda x: -x[1]["pct"]):
    bar = "#" * (r["pct"] // 2)
    print(f"{name:<16} {r['total_w']:>8} {r['sample']:>8} {r['match']:>6} {r['pct']:>4}%  {bar}")
