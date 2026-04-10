"""
Auditoria completa: Produttori del Barbaresco
Filtro textual amplo, sem depender de produtor exato.
"""
import os
import sys
from collections import defaultdict
from urllib.parse import urlparse
import _env

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
RENDER_DB = os.environ["DATABASE_URL"]

lc = psycopg2.connect(**LOCAL_DB)
rc = psycopg2.connect(RENDER_DB, options="-c statement_timeout=300000")
l = lc.cursor()
r = rc.cursor()

print("=" * 80)
print("AUDITORIA COMPLETA: Produttori del Barbaresco")
print("Filtro: nome contendo 'produttori del barbaresco'")
print("        OU produtor~'produttori' + nome~'barbaresco'")
print("=" * 80)

# ── PASSO 1: wines_clean ─────────────────────────────────────────────────────
print("\n=== PASSO 1: wines_clean ===")
l.execute("""
    SELECT id, pais_tabela, id_original, nome_original, nome_limpo,
           produtor_extraido, hash_dedup, safra
    FROM wines_clean
    WHERE nome_original ILIKE '%produttori del barbaresco%'
    OR nome_limpo ILIKE '%produttori del barbaresco%'
    OR (produtor_extraido ILIKE '%produttori%' AND nome_original ILIKE '%barbaresco%')
    OR (produtor_extraido ILIKE '%produttori%' AND nome_limpo ILIKE '%barbaresco%')
""")
clean_rows = l.fetchall()
print(f"Total wines_clean: {len(clean_rows)}")

clean_por_pais = defaultdict(int)
for _, pais, *_ in clean_rows:
    clean_por_pais[pais] += 1
print(f"Paises: {len(clean_por_pais)}")
for p in sorted(clean_por_pais, key=lambda x: -clean_por_pais[x])[:15]:
    print(f"  {p.upper()}: {clean_por_pais[p]}")
if len(clean_por_pais) > 15:
    print(f"  ... +{len(clean_por_pais)-15} paises")

clean_ids = [r[0] for r in clean_rows]
clean_map = {r[0]: r for r in clean_rows}

# ── PASSO 2: y2_results ──────────────────────────────────────────────────────
print("\n=== PASSO 2: y2_results — distribuicao por status ===")
status_counts = defaultdict(int)
y2_map = {}

for i in range(0, len(clean_ids), 5000):
    chunk = clean_ids[i : i + 5000]
    l.execute("SELECT clean_id, status, vivino_id FROM y2_results WHERE clean_id = ANY(%s)", (chunk,))
    for cid, status, vid in l.fetchall():
        status_counts[status] += 1
        y2_map[cid] = (status, vid)

sem_y2 = len(clean_ids) - len(y2_map)
print(f"Com y2_results: {len(y2_map)}")
print(f"Sem y2_results: {sem_y2}")
print()
for status in sorted(status_counts, key=lambda x: -status_counts[x]):
    print(f"  {status:<15} {status_counts[status]:>6}")

# ── PASSO 3: matched — por vivino_id ─────────────────────────────────────────
print("\n=== PASSO 3: matched — por vivino_id (owner no Render) ===")
matched_by_vid = defaultdict(list)
for cid, (status, vid) in y2_map.items():
    if status == "matched" and vid:
        matched_by_vid[vid].append(cid)

total_matched = sum(len(v) for v in matched_by_vid.values())
print(f"Total matched: {total_matched}")
print(f"Distinct vivino_ids: {len(matched_by_vid)}")
print()

for vid in sorted(matched_by_vid, key=lambda x: -len(matched_by_vid[x]))[:25]:
    cids = matched_by_vid[vid]
    r.execute("SELECT id, nome, produtor FROM wines WHERE id = %s", (int(vid),))
    wine = r.fetchone()
    nome_render = f"{wine[2]} - {(wine[1] or '')[:45]}" if wine else "???"

    total_fontes = 0
    for cid in cids:
        row = clean_map.get(cid)
        if row:
            pais, id_orig = row[1], row[2]
            if pais:
                try:
                    l.execute(
                        f"SELECT COUNT(*) FROM vinhos_{pais}_fontes WHERE vinho_id = %s AND url_original IS NOT NULL",
                        (id_orig,),
                    )
                    total_fontes += l.fetchone()[0]
                except:
                    lc.rollback()

    r.execute("SELECT COUNT(*) FROM wine_sources WHERE wine_id = %s", (int(vid),))
    render_sources = r.fetchone()[0]

    print(f"  vivino_id={vid}: {len(cids)} clean | {total_fontes} fontes local | {render_sources} sources render")
    print(f"    {nome_render}")

# ── PASSO 4: owner 10475 — expected vs actual ────────────────────────────────
print("\n=== PASSO 4: owner 10475 — expected LOCAL vs actual RENDER ===")

# Tentar string e int (tipo pode variar)
cids_10475 = matched_by_vid.get("10475", matched_by_vid.get(10475, []))
print(f"Clean_ids matched para 10475: {len(cids_10475)}")
print(f"(keys no dict: tipos={set(type(k).__name__ for k in matched_by_vid.keys())})")

# 4a. Listar quais clean_ids sao
for cid in cids_10475:
    row = clean_map.get(cid)
    if row:
        print(f"  clean_id={cid} | pais={row[1]} | id_orig={row[2]} | {(row[3] or '')[:60]}")

# 4b. Expected URLs
expected_urls = {}
for cid in cids_10475:
    row = clean_map.get(cid)
    if not row:
        continue
    pais, id_orig = row[1], row[2]
    if not pais:
        continue
    try:
        l.execute(
            f"SELECT url_original, preco, moeda FROM vinhos_{pais}_fontes WHERE vinho_id = %s AND url_original IS NOT NULL",
            (id_orig,),
        )
        for url, preco, moeda in l.fetchall():
            dom = urlparse(url).netloc.replace("www.", "") if url else None
            expected_urls[url] = {"pais": pais, "preco": preco, "moeda": moeda, "dominio": dom, "clean_id": cid}
    except:
        lc.rollback()

expected_domains = set(e["dominio"] for e in expected_urls.values() if e["dominio"])
print(f"\nExpected URLs do LOCAL: {len(expected_urls)}")
print(f"Expected dominios: {len(expected_domains)}")
if expected_urls:
    for url, e in list(expected_urls.items()):
        print(f"  {e['dominio']:<40} {e['pais']} | {e['preco']} {e['moeda']}")
        print(f"    {url[:80]}")

# 4c. Actual sources no Render
r.execute("SELECT id, nome, produtor, vivino_id FROM wines WHERE id = 10475")
wine_10475 = r.fetchone()
print(f"\nWine 10475: {wine_10475[2]} - {wine_10475[1]} (vivino_id={wine_10475[3]})")

r.execute("""
    SELECT ws.url, s.dominio, s.pais, ws.preco, ws.moeda
    FROM wine_sources ws
    JOIN stores s ON s.id = ws.store_id
    WHERE ws.wine_id = 10475
""")
actual_sources = r.fetchall()
actual_urls = set(row[0] for row in actual_sources)
actual_domains = set(row[1] for row in actual_sources if row[1])
print(f"Actual sources no Render: {len(actual_sources)}")
print(f"Actual dominios: {len(actual_domains)}")

# 4d. Comparar
overlap_urls = set(expected_urls.keys()) & actual_urls
only_local = set(expected_urls.keys()) - actual_urls
only_render = actual_urls - set(expected_urls.keys())

overlap_domains = expected_domains & actual_domains
only_local_domains = expected_domains - actual_domains
only_render_domains = actual_domains - expected_domains

print(f"\n--- COMPARACAO URLs ---")
print(f"  URLs em AMBOS:       {len(overlap_urls)}")
print(f"  So no LOCAL:         {len(only_local)} (deveriam estar no Render)")
print(f"  So no RENDER:        {len(only_render)} (vieram de outra fonte)")

print(f"\n--- COMPARACAO DOMINIOS ---")
print(f"  Dominios em AMBOS:   {len(overlap_domains)}")
print(f"  So no LOCAL:         {len(only_local_domains)}")
print(f"  So no RENDER:        {len(only_render_domains)}")

if overlap_urls:
    print(f"\n  URLs do scraping JA no Render:")
    for url in sorted(overlap_urls):
        e = expected_urls[url]
        print(f"    {e['dominio']:<35} {e['preco']} {e['moeda']}")

if only_local:
    print(f"\n  URLs do scraping FALTANDO no Render:")
    for url in sorted(only_local):
        e = expected_urls[url]
        print(f"    {e['dominio']:<35} {e['preco']} {e['moeda']}")
        print(f"      {url[:80]}")

if only_render_domains:
    print(f"\n  Dominios so no Render (top 15 — base Vivino?):")
    dom_counts = defaultdict(int)
    for row in actual_sources:
        if row[1] and row[0] not in expected_urls:
            dom_counts[row[1]] += 1
    for dom in sorted(dom_counts, key=lambda x: -dom_counts[x])[:15]:
        print(f"    {dom:<40} {dom_counts[dom]} links")

# ── PASSO 5: Conclusao ───────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("CONCLUSAO")
print("=" * 80)

print(f"\n  wines_clean com 'produttori del barbaresco': {len(clean_rows)}")
print(f"  Distribuicao y2:")
for status in sorted(status_counts, key=lambda x: -status_counts[x]):
    pct = status_counts[status] / len(y2_map) * 100 if y2_map else 0
    print(f"    {status:<15} {status_counts[status]:>6}  ({pct:.1f}%)")
print(f"  Sem y2: {sem_y2}")

print(f"\n  Matched -> {len(matched_by_vid)} vivino_ids distintos")
print(f"  Owner 10475 (Barbaresco base):")
print(f"    Clean_ids matched:    {len(cids_10475)}")
print(f"    Expected URLs local:  {len(expected_urls)}")
print(f"    Actual sources Render:{len(actual_sources)}")

if actual_sources:
    pct_scraping = len(overlap_urls) / len(actual_sources) * 100
    pct_vivino = len(only_render) / len(actual_sources) * 100
    pct_perdido = len(only_local) / max(len(expected_urls), 1) * 100

    print(f"\n  ORIGEM DOS {len(actual_sources)} LINKS NO RENDER:")
    print(f"    Do nosso scraping:    {len(overlap_urls):>5} ({pct_scraping:.1f}%)")
    print(f"    Da base Vivino:       {len(only_render):>5} ({pct_vivino:.1f}%)")
    print(f"\n  LINKS DO SCRAPING PERDIDOS: {len(only_local)} de {len(expected_urls)} ({pct_perdido:.1f}%)")

l.close()
lc.close()
r.close()
rc.close()
