"""
4 auditorias no formato do Nivel B:
  1. Matched saudavel (tem sources no Render)
  2. Matched sem source
  3. New saudavel (tem sources no Render)
  4. New sem source

Para cada caso: expected URLs do LOCAL vs actual URLs do RENDER.
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


def get_domain(url):
    try:
        d = urlparse(url).netloc.replace("www.", "")
        return d if d else None
    except:
        return None


def audit_matched(wine_id, label):
    """Audita um matched wine: y2_results.vivino_id -> clean_ids -> fontes vs Render."""
    print(f"\n{'=' * 80}")
    print(f"CASO: {label}")
    print(f"{'=' * 80}")

    # Info do wine no Render
    r.execute("""
        SELECT w.id, w.nome, w.produtor, w.vivino_id, w.vivino_rating, w.vivino_reviews, w.pais_nome
        FROM wines w WHERE w.id = %s
    """, (wine_id,))
    w = r.fetchone()
    if not w:
        print(f"  Wine {wine_id} nao encontrado no Render")
        return
    print(f"\n  Wine: {w[2]} - {w[1]}")
    print(f"  wine_id={w[0]} | vivino_id={w[3]} | pais={w[6]} | rating={w[4]} | reviews={(w[5] or 0):,}")

    # Actual sources no Render
    r.execute("""
        SELECT ws.url, s.dominio, s.pais, ws.preco, ws.moeda
        FROM wine_sources ws JOIN stores s ON s.id = ws.store_id
        WHERE ws.wine_id = %s
    """, (wine_id,))
    actual = r.fetchall()
    actual_urls = set(row[0] for row in actual)
    actual_doms = set(row[1] for row in actual if row[1])
    print(f"\n  Actual sources (Render): {len(actual)} URLs, {len(actual_doms)} dominios")

    # Buscar clean_ids via y2_results
    l.execute("SELECT clean_id FROM y2_results WHERE vivino_id = %s AND status = 'matched'", (wine_id,))
    clean_ids = [r[0] for r in l.fetchall()]
    print(f"  Clean_ids matched (y2): {len(clean_ids)}")

    if not clean_ids:
        print(f"  Nenhum clean_id matched -> 0 URLs esperadas do scraping")
        print(f"\n  RESULTADO:")
        print(f"    Expected (scraping):  0 URLs")
        print(f"    Actual (Render):      {len(actual)} URLs")
        print(f"    Origem:               100% nao-scraping (provavelmente base Vivino original)")
        return

    # Expected URLs do LOCAL
    expected = {}
    paises_origem = defaultdict(int)
    for cid in clean_ids:
        l.execute("SELECT pais_tabela, id_original FROM wines_clean WHERE id = %s", (cid,))
        row = l.fetchone()
        if not row or not row[0] or not re.match(r"^[a-z]{2}$", row[0]):
            continue
        pais, id_orig = row
        paises_origem[pais] += 1
        try:
            l.execute(
                f"SELECT url_original, preco, moeda FROM vinhos_{pais}_fontes "
                f"WHERE vinho_id = %s AND url_original IS NOT NULL",
                (id_orig,),
            )
            for url, preco, moeda in l.fetchall():
                dom = get_domain(url)
                expected[url] = {"dom": dom, "pais": pais, "preco": preco, "moeda": moeda}
        except:
            lc.rollback()

    expected_doms = set(e["dom"] for e in expected.values() if e["dom"])
    print(f"  Expected URLs (LOCAL):   {len(expected)} URLs, {len(expected_doms)} dominios")
    print(f"  Paises de origem:        {len(paises_origem)} ({', '.join(sorted(paises_origem)[:10])})")

    # Cruzamento
    overlap_u = set(expected.keys()) & actual_urls
    only_local_u = set(expected.keys()) - actual_urls
    only_render_u = actual_urls - set(expected.keys())

    overlap_d = expected_doms & actual_doms
    only_local_d = expected_doms - actual_doms
    only_render_d = actual_doms - expected_doms

    print(f"\n  CRUZAMENTO:")
    print(f"    {'':40} {'URLs':>6}  {'Doms':>6}")
    print(f"    {'Em AMBOS (scraping confirmado no Render)':<40} {len(overlap_u):>6}  {len(overlap_d):>6}")
    print(f"    {'So LOCAL (faltam no Render)':<40} {len(only_local_u):>6}  {len(only_local_d):>6}")
    print(f"    {'So RENDER (origem nao confirmada)':<40} {len(only_render_u):>6}  {len(only_render_d):>6}")

    if actual:
        print(f"\n  COMPOSICAO dos {len(actual)} sources no Render:")
        print(f"    Confirmados do scraping:  {len(overlap_u):>5}  ({len(overlap_u)/len(actual)*100:.1f}%)")
        print(f"    Origem nao confirmada:    {len(only_render_u):>5}  ({len(only_render_u)/len(actual)*100:.1f}%)")

    if expected:
        print(f"  Cobertura do scraping: {len(overlap_u)}/{len(expected)} ({len(overlap_u)/len(expected)*100:.1f}%)")
        print(f"  Perdidos:              {len(only_local_u)}/{len(expected)} ({len(only_local_u)/len(expected)*100:.1f}%)")

    if only_local_u:
        print(f"\n  URLs do scraping faltando no Render (amostra):")
        for url in sorted(only_local_u)[:5]:
            e = expected[url]
            print(f"    {e['dom']:<35} {e['pais']} {e['preco']} {e['moeda']}")


def audit_new(wine_id, label):
    """Audita um new wine: hash_dedup -> wines_clean -> fontes vs Render."""
    print(f"\n{'=' * 80}")
    print(f"CASO: {label}")
    print(f"{'=' * 80}")

    # Info do wine no Render
    r.execute("""
        SELECT w.id, w.nome, w.produtor, w.hash_dedup, w.pais_nome
        FROM wines w WHERE w.id = %s
    """, (wine_id,))
    w = r.fetchone()
    if not w:
        print(f"  Wine {wine_id} nao encontrado no Render")
        return
    print(f"\n  Wine: {w[2]} - {w[1]}")
    print(f"  wine_id={w[0]} | pais={w[4]} | hash={w[3][:25] if w[3] else 'NULL'}...")

    hdp = w[3]

    # Actual sources no Render
    r.execute("""
        SELECT ws.url, s.dominio, s.pais, ws.preco, ws.moeda
        FROM wine_sources ws JOIN stores s ON s.id = ws.store_id
        WHERE ws.wine_id = %s
    """, (wine_id,))
    actual = r.fetchall()
    actual_urls = set(row[0] for row in actual)
    actual_doms = set(row[1] for row in actual if row[1])
    print(f"\n  Actual sources (Render): {len(actual)} URLs, {len(actual_doms)} dominios")

    # Expected: hash_dedup -> wines_clean -> fontes
    if not hdp:
        print(f"  Hash NULL -> nao consigo resolver no local")
        return

    l.execute(
        "SELECT id, pais_tabela, id_original FROM wines_clean WHERE hash_dedup = %s AND id_original IS NOT NULL",
        (hdp,),
    )
    origens = l.fetchall()
    print(f"  Clean origens (por hash): {len(origens)}")

    expected = {}
    paises_origem = defaultdict(int)
    for cid, pais, id_orig in origens:
        if not pais or not re.match(r"^[a-z]{2}$", pais):
            continue
        paises_origem[pais] += 1
        try:
            l.execute(
                f"SELECT url_original, preco, moeda FROM vinhos_{pais}_fontes "
                f"WHERE vinho_id = %s AND url_original IS NOT NULL",
                (id_orig,),
            )
            for url, preco, moeda in l.fetchall():
                dom = get_domain(url)
                expected[url] = {"dom": dom, "pais": pais, "preco": preco, "moeda": moeda}
        except:
            lc.rollback()

    expected_doms = set(e["dom"] for e in expected.values() if e["dom"])
    print(f"  Expected URLs (LOCAL):   {len(expected)} URLs, {len(expected_doms)} dominios")
    if paises_origem:
        print(f"  Paises de origem:        {len(paises_origem)} ({', '.join(sorted(paises_origem)[:10])})")

    if not expected:
        print(f"\n  RESULTADO:")
        print(f"    0 URLs esperadas do scraping (hash sem fontes no local)")
        print(f"    {len(actual)} URLs no Render")
        return

    # Cruzamento
    overlap_u = set(expected.keys()) & actual_urls
    only_local_u = set(expected.keys()) - actual_urls
    only_render_u = actual_urls - set(expected.keys())

    overlap_d = expected_doms & actual_doms
    only_local_d = expected_doms - actual_doms
    only_render_d = actual_doms - expected_doms

    print(f"\n  CRUZAMENTO:")
    print(f"    {'':40} {'URLs':>6}  {'Doms':>6}")
    print(f"    {'Em AMBOS (scraping confirmado no Render)':<40} {len(overlap_u):>6}  {len(overlap_d):>6}")
    print(f"    {'So LOCAL (faltam no Render)':<40} {len(only_local_u):>6}  {len(only_local_d):>6}")
    print(f"    {'So RENDER (origem nao confirmada)':<40} {len(only_render_u):>6}  {len(only_render_d):>6}")

    if actual:
        print(f"\n  COMPOSICAO dos {len(actual)} sources no Render:")
        print(f"    Confirmados do scraping:  {len(overlap_u):>5}  ({len(overlap_u)/len(actual)*100:.1f}%)")
        print(f"    Origem nao confirmada:    {len(only_render_u):>5}  ({len(only_render_u)/len(actual)*100:.1f}%)")

    if expected:
        print(f"  Cobertura do scraping: {len(overlap_u)}/{len(expected)} ({len(overlap_u)/len(expected)*100:.1f}%)")
        print(f"  Perdidos:              {len(only_local_u)}/{len(expected)} ({len(only_local_u)/len(expected)*100:.1f}%)")

    if only_local_u:
        print(f"\n  URLs do scraping faltando no Render (amostra):")
        for url in sorted(only_local_u)[:5]:
            e = expected[url]
            print(f"    {e['dom']:<35} {e['pais']} {e['preco']} {e['moeda']}")


# ══════════════════════════════════════════════════════════════════════════════
# SELECIONAR OS 4 CANDIDATOS
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("SELECIONANDO 4 CANDIDATOS")
print("=" * 80)

# 1. Matched saudavel: vivino_id NOT NULL, tem muitos sources, produtor longo
print("\n--- Candidato 1: Matched saudavel ---")
r.execute("""
    SELECT w.id, w.nome, w.produtor, COUNT(ws.id) as cnt
    FROM wines w
    JOIN wine_sources ws ON ws.wine_id = w.id
    WHERE w.vivino_id IS NOT NULL
    AND LENGTH(w.produtor) > 15
    AND w.vivino_reviews > 5000
    GROUP BY w.id, w.nome, w.produtor
    HAVING COUNT(ws.id) BETWEEN 20 AND 100
    ORDER BY RANDOM()
    LIMIT 1
""")
c1 = r.fetchone()
print(f"  wine_id={c1[0]} | {c1[2]} - {c1[1][:40]} | {c1[3]} sources")

# 2. Matched sem source: vivino_id NOT NULL, 0 sources, mas TEM clean_ids no y2
print("\n--- Candidato 2: Matched sem source ---")
# Primeiro pegar matched owners do y2 que talvez nao tenham source
l.execute("""
    SELECT vivino_id, COUNT(*) as cnt
    FROM y2_results
    WHERE status = 'matched' AND vivino_id IS NOT NULL
    GROUP BY vivino_id
    HAVING COUNT(*) >= 3
    ORDER BY RANDOM()
    LIMIT 50
""")
candidatos_matched = l.fetchall()
c2 = None
for vid, cnt in candidatos_matched:
    r.execute("""
        SELECT w.id, w.nome, w.produtor,
               (SELECT COUNT(*) FROM wine_sources ws WHERE ws.wine_id = w.id) as src_cnt
        FROM wines w WHERE w.id = %s
    """, (int(vid),))
    row = r.fetchone()
    if row and row[3] == 0:
        c2 = row
        c2_y2_cnt = cnt
        break
if c2:
    print(f"  wine_id={c2[0]} | {c2[2]} - {c2[1][:40]} | {c2[3]} sources | {c2_y2_cnt} clean_ids no y2")
else:
    print(f"  Nenhum matched sem source encontrado com >=3 clean_ids")
    # Tentar com >=1
    for vid, cnt in candidatos_matched:
        r.execute("""
            SELECT w.id, w.nome, w.produtor,
                   (SELECT COUNT(*) FROM wine_sources ws WHERE ws.wine_id = w.id) as src_cnt
            FROM wines w WHERE w.id = %s
        """, (int(vid),))
        row = r.fetchone()
        if row and row[3] == 0:
            c2 = row
            c2_y2_cnt = cnt
            print(f"  wine_id={c2[0]} | {c2[2]} - {c2[1][:40]} | {c2[3]} sources | {c2_y2_cnt} clean_ids")
            break
    if not c2:
        # Buscar qualquer matched sem source
        l.execute("""
            SELECT vivino_id, COUNT(*) FROM y2_results
            WHERE status = 'matched' AND vivino_id IS NOT NULL
            GROUP BY vivino_id ORDER BY RANDOM() LIMIT 200
        """)
        for vid, cnt in l.fetchall():
            r.execute("SELECT COUNT(*) FROM wine_sources WHERE wine_id = %s", (int(vid),))
            if r.fetchone()[0] == 0:
                r.execute("SELECT id, nome, produtor FROM wines WHERE id = %s", (int(vid),))
                w = r.fetchone()
                if w:
                    c2 = (w[0], w[1], w[2], 0)
                    c2_y2_cnt = cnt
                    print(f"  wine_id={c2[0]} | {c2[2]} - {c2[1][:40]} | 0 sources | {c2_y2_cnt} clean_ids")
                    break
        if not c2:
            print(f"  NAO ENCONTRADO")

# 3. New saudavel: vivino_id IS NULL, tem sources, produtor longo
print("\n--- Candidato 3: New saudavel ---")
r.execute("""
    SELECT w.id, w.nome, w.produtor, COUNT(ws.id) as cnt
    FROM wines w
    JOIN wine_sources ws ON ws.wine_id = w.id
    WHERE w.vivino_id IS NULL
    AND w.produtor IS NOT NULL
    AND LENGTH(w.produtor) > 15
    GROUP BY w.id, w.nome, w.produtor
    HAVING COUNT(ws.id) BETWEEN 3 AND 20
    ORDER BY RANDOM()
    LIMIT 1
""")
c3 = r.fetchone()
print(f"  wine_id={c3[0]} | {c3[2]} - {c3[1][:40]} | {c3[3]} sources")

# 4. New sem source: vivino_id IS NULL, 0 sources, hash NOT NULL
print("\n--- Candidato 4: New sem source ---")
r.execute("""
    SELECT w.id, w.nome, w.produtor, w.hash_dedup
    FROM wines w
    LEFT JOIN wine_sources ws ON ws.wine_id = w.id
    WHERE w.vivino_id IS NULL
    AND w.hash_dedup IS NOT NULL
    AND w.produtor IS NOT NULL
    AND LENGTH(w.produtor) > 10
    AND ws.id IS NULL
    ORDER BY RANDOM()
    LIMIT 1
""")
c4 = r.fetchone()
print(f"  wine_id={c4[0]} | {c4[2]} - {c4[1][:40]} | 0 sources")

# ══════════════════════════════════════════════════════════════════════════════
# RODAR AS 4 AUDITORIAS
# ══════════════════════════════════════════════════════════════════════════════

audit_matched(c1[0], f"MATCHED SAUDAVEL (wine_id={c1[0]})")

if c2:
    audit_matched(c2[0], f"MATCHED SEM SOURCE (wine_id={c2[0]})")

audit_new(c3[0], f"NEW SAUDAVEL (wine_id={c3[0]})")

audit_new(c4[0], f"NEW SEM SOURCE (wine_id={c4[0]})")

# ══════════════════════════════════════════════════════════════════════════════
# RESUMO COMPARATIVO
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("RESUMO COMPARATIVO")
print("=" * 80)
print("""
  Os 4 casos mostram cenarios diferentes do pipeline.
  A conclusao de cada caso e local — nenhum valida ou invalida o diagnostico global.
""")

l.close(); lc.close()
r.close(); rc.close()
