"""
Auditoria Produttori del Barbaresco v2
3 niveis separados:
  A. Familia do produtor (todas as linhas)
  B. Owner especifico 10475
  C. Hashes vs linhas
"""
import os, sys, re
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

FILTRO_CLEAN = """
    nome_original ILIKE '%produttori del barbaresco%'
    OR nome_limpo ILIKE '%produttori del barbaresco%'
    OR (produtor_extraido ILIKE '%produttori%' AND nome_original ILIKE '%barbaresco%')
    OR (produtor_extraido ILIKE '%produttori%' AND nome_limpo ILIKE '%barbaresco%')
"""

# ══════════════════════════════════════════════════════════════════════════════
# NIVEL A: FAMILIA DO PRODUTOR
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("NIVEL A: FAMILIA TEXTUAL 'Produttori del Barbaresco'")
print("=" * 80)

# A1. vinhos_XX (registros brutos scrapados)
print("\n--- A1. Registros brutos em vinhos_XX ---")
l.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_name ~ '^vinhos_[a-z]{2}$' ORDER BY table_name
""")
tabelas_vxx = [r[0] for r in l.fetchall()]

total_vxx_linhas = 0
total_vxx_hashes = set()
vxx_por_pais = {}
for tab in tabelas_vxx:
    pais = tab.replace("vinhos_", "")
    try:
        l.execute(f"""
            SELECT id, hash_dedup FROM {tab}
            WHERE nome ILIKE '%produttori del barbaresco%'
            OR (vinicola_nome ILIKE '%produttori%' AND nome ILIKE '%barbaresco%')
        """)
        rows = l.fetchall()
        if rows:
            vxx_por_pais[pais] = len(rows)
            total_vxx_linhas += len(rows)
            for _, hdp in rows:
                if hdp:
                    total_vxx_hashes.add(hdp)
    except:
        lc.rollback()

print(f"  Linhas:          {total_vxx_linhas:,}")
print(f"  Hashes unicos:   {len(total_vxx_hashes):,}")
print(f"  Paises:          {len(vxx_por_pais)}")
print(f"  Dedup ratio:     {total_vxx_linhas / max(len(total_vxx_hashes), 1):.2f}x")

# A2. wines_clean
print("\n--- A2. wines_clean ---")
l.execute(f"SELECT id, pais_tabela, id_original, hash_dedup FROM wines_clean WHERE {FILTRO_CLEAN}")
clean_rows = l.fetchall()
clean_ids = [r[0] for r in clean_rows]
clean_map = {r[0]: r for r in clean_rows}
clean_hashes = set(r[3] for r in clean_rows if r[3])

print(f"  Linhas:          {len(clean_rows):,}")
print(f"  Hashes unicos:   {len(clean_hashes):,}")

# A3. Perda vinhos_XX -> wines_clean
hashes_perdidos = total_vxx_hashes - clean_hashes
hashes_em_ambos = total_vxx_hashes & clean_hashes
print(f"\n--- A3. Transicao vinhos_XX -> wines_clean ---")
print(f"  Hashes vXX:           {len(total_vxx_hashes):,}")
print(f"  Hashes clean:         {len(clean_hashes):,}")
print(f"  Hashes em ambos:      {len(hashes_em_ambos):,}")
print(f"  Hashes so em vXX:     {len(hashes_perdidos):,}  (nao chegaram ao clean)")
print(f"  Linhas vXX:           {total_vxx_linhas:,}")
print(f"  Linhas clean:         {len(clean_rows):,}")
print(f"  Linhas perdidas:      {total_vxx_linhas - len(clean_rows):,}  (dedup dentro do pais + hashes perdidos)")

# A4. y2_results
print("\n--- A4. y2_results ---")
status_counts = defaultdict(int)
y2_map = {}
for i in range(0, len(clean_ids), 5000):
    chunk = clean_ids[i:i+5000]
    l.execute("SELECT clean_id, status, vivino_id FROM y2_results WHERE clean_id = ANY(%s)", (chunk,))
    for cid, status, vid in l.fetchall():
        status_counts[status] += 1
        y2_map[cid] = (status, vid)

sem_y2 = len(clean_ids) - len(y2_map)
print(f"  Total com y2:    {len(y2_map):,}")
print(f"  Sem y2:          {sem_y2}")
print()
for status in sorted(status_counts, key=lambda x: -status_counts[x]):
    pct = status_counts[status] / max(len(y2_map), 1) * 100
    print(f"    {status:<15} {status_counts[status]:>6}  ({pct:.1f}%)")

# Hashes unicos por status
hashes_por_status = defaultdict(set)
for cid, (status, vid) in y2_map.items():
    row = clean_map.get(cid)
    if row and row[3]:
        hashes_por_status[status].add(row[3])

print(f"\n  Hashes unicos por status:")
for status in sorted(hashes_por_status, key=lambda x: -len(hashes_por_status[x])):
    print(f"    {status:<15} {len(hashes_por_status[status]):>6} hashes")

# A5. Matched por owner
print("\n--- A5. Matched -> owners no Render ---")
matched_by_vid = defaultdict(list)
for cid, (status, vid) in y2_map.items():
    if status == "matched" and vid is not None:
        matched_by_vid[vid].append(cid)

matched_linhas = sum(len(v) for v in matched_by_vid.values())
matched_hashes = set()
for cids in matched_by_vid.values():
    for cid in cids:
        row = clean_map.get(cid)
        if row and row[3]:
            matched_hashes.add(row[3])

print(f"  Linhas matched:      {matched_linhas:,}")
print(f"  Hashes matched:      {len(matched_hashes):,}")
print(f"  Owners (vivino_ids): {len(matched_by_vid)}")
print(f"  Media linhas/owner:  {matched_linhas / max(len(matched_by_vid), 1):.1f}")
print()

for vid in sorted(matched_by_vid, key=lambda x: -len(matched_by_vid[x]))[:15]:
    cids = matched_by_vid[vid]
    r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (int(vid),))
    wine = r.fetchone()
    nome_r = f"{wine[1]} - {(wine[0] or '')[:40]}" if wine else "???"
    # Contar hashes unicos deste owner
    owner_hashes = set()
    for cid in cids:
        row = clean_map.get(cid)
        if row and row[3]:
            owner_hashes.add(row[3])
    print(f"  owner={vid}: {len(cids)} linhas | {len(owner_hashes)} hashes | {nome_r}")

# A6. Resumo familia
print("\n--- A6. RESUMO FAMILIA ---")
print(f"  vinhos_XX:  {total_vxx_linhas:>6} linhas  {len(total_vxx_hashes):>6} hashes")
print(f"  wines_clean:{len(clean_rows):>6} linhas  {len(clean_hashes):>6} hashes")
print(f"  matched:    {matched_linhas:>6} linhas  {len(matched_hashes):>6} hashes  -> {len(matched_by_vid)} owners")
print(f"  duplicate:  {status_counts.get('duplicate',0):>6} linhas  {len(hashes_por_status.get('duplicate', set())):>6} hashes")
print(f"  new:        {status_counts.get('new',0):>6} linhas  {len(hashes_por_status.get('new', set())):>6} hashes")
print(f"  error:      {status_counts.get('error',0):>6} linhas  {len(hashes_por_status.get('error', set())):>6} hashes")
print(f"  not_wine:   {status_counts.get('not_wine',0):>6} linhas  {len(hashes_por_status.get('not_wine', set())):>6} hashes")

# ══════════════════════════════════════════════════════════════════════════════
# NIVEL B: OWNER ESPECIFICO 10475
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("NIVEL B: OWNER 10475 (Produttori del Barbaresco - Barbaresco)")
print("=" * 80)

r.execute("SELECT id, nome, produtor, vivino_id, vivino_rating, vivino_reviews FROM wines WHERE id = 10475")
w = r.fetchone()
print(f"\n  Wine: {w[2]} - {w[1]}")
print(f"  vivino_id={w[3]} | rating={w[4]} | reviews={w[5]:,}")

cids_owner = matched_by_vid.get(10475, [])
owner_hashes = set()
owner_paises = defaultdict(int)
for cid in cids_owner:
    row = clean_map.get(cid)
    if row:
        if row[3]: owner_hashes.add(row[3])
        owner_paises[row[1]] += 1

print(f"\n  Clean_ids matched:   {len(cids_owner)}")
print(f"  Hashes unicos:       {len(owner_hashes)}")
print(f"  Paises de origem:    {len(owner_paises)}")
for p in sorted(owner_paises, key=lambda x: -owner_paises[x])[:10]:
    print(f"    {p.upper()}: {owner_paises[p]}")

# B1. Expected URLs do LOCAL
print("\n--- B1. Expected URLs (LOCAL) ---")
expected = {}  # url -> info
for cid in cids_owner:
    row = clean_map.get(cid)
    if not row: continue
    pais, id_orig = row[1], row[2]
    if not pais or not re.match(r"^[a-z]{2}$", pais): continue
    try:
        l.execute(f"SELECT url_original, preco, moeda FROM vinhos_{pais}_fontes WHERE vinho_id = %s AND url_original IS NOT NULL", (id_orig,))
        for url, preco, moeda in l.fetchall():
            dom = urlparse(url).netloc.replace("www.", "") if url else None
            expected[url] = {"dom": dom, "pais": pais, "preco": preco, "moeda": moeda}
    except:
        lc.rollback()

expected_doms = set(e["dom"] for e in expected.values() if e["dom"])
print(f"  URLs:     {len(expected)}")
print(f"  Dominios: {len(expected_doms)}")

# B2. Actual sources RENDER
print("\n--- B2. Actual sources (RENDER) ---")
r.execute("""
    SELECT ws.url, s.dominio, s.pais, ws.preco, ws.moeda
    FROM wine_sources ws JOIN stores s ON s.id = ws.store_id
    WHERE ws.wine_id = 10475
""")
actual = r.fetchall()
actual_urls = set(row[0] for row in actual)
actual_doms = set(row[1] for row in actual if row[1])
print(f"  URLs:     {len(actual)}")
print(f"  Dominios: {len(actual_doms)}")

# B3. Cruzamento
overlap_u = set(expected.keys()) & actual_urls
only_local_u = set(expected.keys()) - actual_urls
only_render_u = actual_urls - set(expected.keys())

overlap_d = expected_doms & actual_doms
only_local_d = expected_doms - actual_doms
only_render_d = actual_doms - expected_doms

print(f"\n--- B3. Cruzamento ---")
print(f"  {'':30} {'URLs':>8}  {'Dominios':>8}")
print(f"  {'Em AMBOS (scraping no Render)':<30} {len(overlap_u):>8}  {len(overlap_d):>8}")
print(f"  {'So LOCAL (faltam no Render)':<30} {len(only_local_u):>8}  {len(only_local_d):>8}")
print(f"  {'So RENDER (base Vivino)':<30} {len(only_render_u):>8}  {len(only_render_d):>8}")

print(f"\n  ORIGEM dos {len(actual)} sources no Render:")
print(f"    Scraping:  {len(overlap_u):>5}  ({len(overlap_u)/max(len(actual),1)*100:.1f}%)")
print(f"    Vivino:    {len(only_render_u):>5}  ({len(only_render_u)/max(len(actual),1)*100:.1f}%)")
print(f"  Scraping perdido: {len(only_local_u)} de {len(expected)} ({len(only_local_u)/max(len(expected),1)*100:.1f}%)")

# ══════════════════════════════════════════════════════════════════════════════
# NIVEL C: HASHES vs LINHAS
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("NIVEL C: HASHES vs LINHAS (onde cada contagem vem)")
print("=" * 80)

print(f"""
  O funil tem 2 eixos de contagem que nao devem ser misturados:

  LINHAS (registros individuais):
    vinhos_XX    {total_vxx_linhas:>6}  cada linha = 1 produto numa loja
    wines_clean  {len(clean_rows):>6}  dedup por hash dentro de cada pais
    y2 matched   {matched_linhas:>6}  linhas classificadas como matched
    y2 duplicate {status_counts.get('duplicate',0):>6}  linhas descartadas como duplicata
    y2 new       {status_counts.get('new',0):>6}  linhas sem match Vivino
    y2 error     {status_counts.get('error',0):>6}  linhas com erro de classificacao
    y2 not_wine  {status_counts.get('not_wine',0):>6}  nao e vinho

  HASHES (vinhos logicamente distintos):
    vinhos_XX    {len(total_vxx_hashes):>6}  hashes unicos em todas as lojas
    wines_clean  {len(clean_hashes):>6}  hashes no clean (subconjunto dos de vXX)
    matched      {len(matched_hashes):>6}  hashes que deram match
    duplicate    {len(hashes_por_status.get('duplicate', set())):>6}  hashes marcados duplicata
    new          {len(hashes_por_status.get('new', set())):>6}  hashes sem match
    error        {len(hashes_por_status.get('error', set())):>6}  hashes com erro

  OWNERS (vinhos finais no Render):
    matched      {len(matched_by_vid):>6}  vivino_ids distintos

  REDUCOES:
    vXX linhas -> vXX hashes:    {total_vxx_linhas:>6} -> {len(total_vxx_hashes):>6}  (mesma loja, mesmo hash)
    vXX hashes -> clean hashes:  {len(total_vxx_hashes):>6} -> {len(clean_hashes):>6}  ({len(hashes_perdidos)} hashes nao chegaram ao clean)
    clean linhas -> clean hashes:{len(clean_rows):>6} -> {len(clean_hashes):>6}  (mesmo hash em paises diferentes = linhas distintas)
    matched hashes -> owners:    {len(matched_hashes):>6} -> {len(matched_by_vid):>6}  (hashes diferentes = mesmo vinho Vivino)
""")

# Verificar overlap de hashes entre matched e duplicate
overlap_m_d = matched_hashes & hashes_por_status.get("duplicate", set())
print(f"  Hashes em matched E duplicate: {len(overlap_m_d)}")
if overlap_m_d:
    print(f"    (IA classificou o mesmo hash como matched em uma linha e duplicate em outra)")

overlap_m_n = matched_hashes & hashes_por_status.get("new", set())
print(f"  Hashes em matched E new:       {len(overlap_m_n)}")

print("\n" + "=" * 80)
print("CONCLUSAO FINAL")
print("=" * 80)
print(f"""
  Para a familia 'Produttori del Barbaresco':

  1. SCRAPING capturou {total_vxx_linhas:,} registros em {len(vxx_por_pais)} paises
     Representam {len(total_vxx_hashes):,} produtos unicos (por hash)

  2. WINES_CLEAN consolidou em {len(clean_rows):,} linhas ({len(clean_hashes):,} hashes)
     Perda: {len(hashes_perdidos)} hashes ({len(hashes_perdidos)/max(len(total_vxx_hashes),1)*100:.1f}%)

  3. Y2_RESULTS classificou:
     - {matched_linhas:,} linhas matched ({len(matched_hashes)} hashes -> {len(matched_by_vid)} owners Vivino)
     - {status_counts.get('duplicate',0)} duplicatas | {status_counts.get('new',0)} new | {status_counts.get('error',0)} erros

  4. OWNER 10475 (Barbaresco base):
     - {len(cids_owner)} linhas matched de {len(owner_paises)} paises
     - {len(expected)} URLs esperadas do scraping
     - {len(actual)} sources no Render
     - {len(overlap_u)} do scraping ({len(overlap_u)/max(len(actual),1)*100:.1f}%) + {len(only_render_u)} do Vivino ({len(only_render_u)/max(len(actual),1)*100:.1f}%)
     - Perdido: {len(only_local_u)} URLs ({len(only_local_u)/max(len(expected),1)*100:.1f}%)
""")

l.close(); lc.close()
r.close(); rc.close()
