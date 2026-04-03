"""Auditoria profunda da wines_clean — 22 checks."""
import psycopg2
import sys

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

def run():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    results = {}

    # ── CHECK 1 — Contagem total ──
    print("=== CHECK 1 — Contagem total ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean;")
    total_wc = cur.fetchone()[0]
    cur.execute("SELECT SUM(n_live_tup)::bigint FROM pg_stat_user_tables WHERE relname LIKE 'vinhos_%' AND relname NOT LIKE '%_fontes';")
    total_orig = cur.fetchone()[0] or 0
    diff_pct = abs(total_wc - total_orig) / max(total_orig, 1) * 100
    print(f"  wines_clean: {total_wc:,}")
    print(f"  tabelas originais (pg_stat): {total_orig:,}")
    print(f"  diferenca: {diff_pct:.1f}%")
    results[1] = f"{total_wc:,} vinhos | diff {diff_pct:.1f}% vs original ({total_orig:,})"

    # ── CHECK 2 — Todos os 50 paises presentes ──
    print("\n=== CHECK 2 — Paises presentes ===")
    cur.execute("SELECT pais_tabela, COUNT(*) FROM wines_clean GROUP BY pais_tabela ORDER BY COUNT(*) DESC;")
    paises = cur.fetchall()
    print(f"  {len(paises)} paises distintos:")
    for p, c in paises:
        print(f"    {p}: {c:,}")
    results[2] = f"{len(paises)} paises"

    # ── CHECK 3 — Campos obrigatorios NULL ──
    print("\n=== CHECK 3 — Campos obrigatorios NULL ===")
    cur.execute("""
        SELECT 'nome_limpo' as campo, COUNT(*) FROM wines_clean WHERE nome_limpo IS NULL OR nome_limpo = ''
        UNION ALL SELECT 'nome_normalizado', COUNT(*) FROM wines_clean WHERE nome_normalizado IS NULL OR nome_normalizado = ''
        UNION ALL SELECT 'pais_tabela', COUNT(*) FROM wines_clean WHERE pais_tabela IS NULL OR pais_tabela = ''
        UNION ALL SELECT 'id_original', COUNT(*) FROM wines_clean WHERE id_original IS NULL;
    """)
    nulls = cur.fetchall()
    total_nulls = sum(n for _, n in nulls)
    for campo, n in nulls:
        status = "OK" if n == 0 else "FALHA"
        print(f"  {campo}: {n} [{status}]")
    results[3] = f"{total_nulls} campos com NULL"

    # ── CHECK 4 — Encoding quebrado ──
    print("\n=== CHECK 4 — Encoding quebrado ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%\ufffd%';")
    enc1 = cur.fetchone()[0]
    print(f"  replacement char: {enc1}")
    results[4] = str(enc1)

    # ── CHECK 5 — HTML entities (CRITICO) ──
    print("\n=== CHECK 5 — HTML entities (CRITICO) ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%&#%';")
    html1 = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%&amp;%';")
    html2 = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%&nbsp;%';")
    html3 = cur.fetchone()[0]
    html_total = html1 + html2 + html3
    print(f"  &#: {html1} | &amp;: {html2} | &nbsp;: {html3} | TOTAL: {html_total}")
    results[5] = str(html_total)

    # ── CHECK 6 — Volume no nome (CRITICO) ──
    print("\n=== CHECK 6 — Volume no nome (CRITICO) ===")
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~* '\d+\s*ml\b';")
    vol_ml = cur.fetchone()[0]
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~* '\d+\s*cl\b';")
    vol_cl = cur.fetchone()[0]
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~* '\d[\.,]\d+\s*[lL]\b';")
    vol_l = cur.fetchone()[0]
    vol_total = vol_ml + vol_cl + vol_l
    vol_pct = vol_total / max(total_wc, 1) * 100
    print(f"  ml: {vol_ml} | cl: {vol_cl} | L: {vol_l} | TOTAL: {vol_total} ({vol_pct:.2f}%)")
    results[6] = f"{vol_total} ({vol_pct:.2f}%)"

    # ── CHECK 7 — Preco no nome (CRITICO) ──
    print("\n=== CHECK 7 — Preco no nome (CRITICO) ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~ '[$€£¥]' OR nome_limpo LIKE '%R$%';")
    preco = cur.fetchone()[0]
    preco_pct = preco / max(total_wc, 1) * 100
    print(f"  {preco} ({preco_pct:.3f}%)")
    results[7] = f"{preco} ({preco_pct:.3f}%)"

    # ── CHECK 8 — Itens nao-vinho ──
    print("\n=== CHECK 8 — Itens nao-vinho ===")
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(whisky|whiskey|vodka|tequila|cognac)\y';")
    nv1 = cur.fetchone()[0]
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(queijo|cheese|fromage|chocolate)\y';")
    nv2 = cur.fetchone()[0]
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(red bull|coca.cola|gift card|gutschein)\y';")
    nv3 = cur.fetchone()[0]
    nv_total = nv1 + nv2 + nv3
    print(f"  destilados: {nv1} | comida: {nv2} | outros: {nv3} | TOTAL: {nv_total}")
    results[8] = str(nv_total)

    # ── CHECK 9 — Produtores que sao dominios ──
    print("\n=== CHECK 9 — Produtores-dominio ===")
    cur.execute(r"""
        SELECT produtor_extraido, COUNT(*) FROM wines_clean
        WHERE produtor_extraido ~ '\.(com|net|cl|br|co|org|shop)'
        GROUP BY produtor_extraido ORDER BY COUNT(*) DESC LIMIT 20;
    """)
    dominios = cur.fetchall()
    print(f"  {len(dominios)} produtores-dominio encontrados:")
    for p, c in dominios:
        print(f"    {p}: {c}")
    results[9] = str(sum(c for _, c in dominios)) if dominios else "0"

    # ── CHECK 10 — Top 30 produtores ──
    print("\n=== CHECK 10 — Top 30 produtores ===")
    cur.execute("""
        SELECT produtor_extraido, COUNT(*) as cnt FROM wines_clean
        WHERE produtor_extraido IS NOT NULL
        GROUP BY produtor_extraido ORDER BY cnt DESC LIMIT 30;
    """)
    top_prod = cur.fetchall()
    problemas_prod = []
    suspect_words = ['vinho', 'wine', 'tinto', 'chianti', 'bordeaux', 'wines', 'vin', 'vino']
    for p, c in top_prod:
        flag = ""
        if p and p.lower().strip() in suspect_words:
            flag = " ← SUSPEITO"
            problemas_prod.append(p)
        print(f"    {p}: {c:,}{flag}")
    results[10] = f"{'PROBLEMAS: ' + ', '.join(problemas_prod) if problemas_prod else 'OK'}"

    # ── CHECK 11 — Safras absurdas ──
    print("\n=== CHECK 11 — Safras absurdas ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE safra IS NOT NULL AND (safra < 1900 OR safra > 2026);")
    safras_abs = cur.fetchone()[0]
    cur.execute("SELECT safra, COUNT(*) FROM wines_clean WHERE safra IS NOT NULL AND (safra < 1900 OR safra > 2026) GROUP BY safra ORDER BY COUNT(*) DESC LIMIT 10;")
    safras_det = cur.fetchall()
    print(f"  {safras_abs} safras absurdas")
    for s, c in safras_det:
        print(f"    safra {s}: {c}")
    results[11] = str(safras_abs)

    # ── CHECK 12 — Nomes muito curtos ou longos ──
    print("\n=== CHECK 12 — Nomes curtos/longos ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE LENGTH(nome_limpo) < 3;")
    curtos = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE LENGTH(nome_limpo) > 200;")
    longos = cur.fetchone()[0]
    cur.execute("SELECT nome_limpo FROM wines_clean WHERE LENGTH(nome_limpo) < 5 LIMIT 10;")
    exemplos_curtos = [r[0] for r in cur.fetchall()]
    print(f"  curtos (<3): {curtos} | longos (>200): {longos}")
    if exemplos_curtos:
        print(f"  exemplos curtos: {exemplos_curtos}")
    results[12] = f"curtos {curtos}, longos {longos}"

    # ── CHECK 13 — Duplicatas ──
    print("\n=== CHECK 13 — Duplicatas (pais_tabela + id_original) ===")
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT pais_tabela, id_original FROM wines_clean
            GROUP BY pais_tabela, id_original HAVING COUNT(*) > 1
        ) sub;
    """)
    dups = cur.fetchone()[0]
    print(f"  duplicatas: {dups}")
    results[13] = str(dups)

    # ── CHECK 14 — Nomes mais repetidos ──
    print("\n=== CHECK 14 — Nomes mais repetidos ===")
    cur.execute("SELECT nome_normalizado, COUNT(*) FROM wines_clean GROUP BY nome_normalizado ORDER BY COUNT(*) DESC LIMIT 20;")
    top_nomes = cur.fetchall()
    for n, c in top_nomes:
        print(f"    {n[:60]}: {c:,}")
    top5 = [(n[:40], c) for n, c in top_nomes[:5]]
    results[14] = f"Top 5: {top5}"

    # ── CHECK 15 — Amostragem visual 50 vinhos ──
    print("\n=== CHECK 15 — Amostragem 50 vinhos aleatorios ===")
    cur.execute("""
        SELECT pais_tabela, id_original, nome_original, nome_limpo,
               produtor_extraido, safra, nome_normalizado
        FROM wines_clean ORDER BY RANDOM() LIMIT 50
    """)
    mudaram = 0
    iguais = 0
    for row in cur.fetchall():
        pais, id_orig, nome_orig, nome_limpo, produtor, safra, nome_norm = row
        changed = nome_orig != nome_limpo
        if changed:
            mudaram += 1
        else:
            iguais += 1
        tag = "MUDOU" if changed else "igual"
        print(f"  [{pais}] {tag}")
        print(f"    ORIG:  {(nome_orig or '')[:100]}")
        print(f"    LIMPO: {(nome_limpo or '')[:100]}")
        print(f"    PROD:  {produtor or 'NULL'} | SAFRA: {safra}")
    print(f"  --- {mudaram} mudaram / {iguais} iguais ---")
    results[15] = f"{mudaram} mudaram / {iguais} iguais"

    # ── CHECK 16 — Safra duplicada no nome ──
    print("\n=== CHECK 16 — Safra duplicada no nome ===")
    cur.execute("""
        SELECT COUNT(*) FROM wines_clean
        WHERE safra IS NOT NULL
          AND nome_limpo ~ (safra::text || '\\s+' || safra::text);
    """)
    safra_dup = cur.fetchone()[0]
    print(f"  {safra_dup}")
    results[16] = str(safra_dup)

    # ── CHECK 17 — Nomes que sao APENAS uva ──
    print("\n=== CHECK 17 — Nome = so uva ===")
    cur.execute("""
        SELECT nome_limpo, COUNT(*) FROM wines_clean
        WHERE LOWER(nome_limpo) IN ('chardonnay','merlot','cabernet sauvignon','pinot noir','malbec','syrah','shiraz','sauvignon blanc','riesling','tempranillo','sangiovese','grenache','carmenere','tannat','prosecco','rose','brut','reserva','crianza','tinto','blanco','red','white')
        GROUP BY nome_limpo ORDER BY COUNT(*) DESC;
    """)
    uvas = cur.fetchall()
    uva_total = sum(c for _, c in uvas)
    for u, c in uvas:
        print(f"    {u}: {c}")
    print(f"  TOTAL: {uva_total}")
    results[17] = str(uva_total)

    # ── CHECK 18 — Distribuicao de tamanho ──
    print("\n=== CHECK 18 — Distribuicao de tamanho do nome ===")
    cur.execute("""
        SELECT
            CASE
                WHEN LENGTH(nome_limpo) < 5 THEN '<5'
                WHEN LENGTH(nome_limpo) < 10 THEN '5-9'
                WHEN LENGTH(nome_limpo) < 20 THEN '10-19'
                WHEN LENGTH(nome_limpo) < 40 THEN '20-39'
                WHEN LENGTH(nome_limpo) < 80 THEN '40-79'
                ELSE '80+'
            END as faixa,
            COUNT(*) as qtd
        FROM wines_clean GROUP BY 1 ORDER BY 1;
    """)
    faixas = cur.fetchall()
    faixa_str = []
    for f, q in faixas:
        print(f"    {f}: {q:,}")
        faixa_str.append(f"{f}={q:,}")
    results[18] = " | ".join(faixa_str)

    # ── CHECK 19 — Consistencia nome_normalizado ──
    print("\n=== CHECK 19 — nome_normalizado limpo ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_normalizado ~ '[^a-z0-9 ]';")
    norm_dirty = cur.fetchone()[0]
    print(f"  chars especiais em nome_normalizado: {norm_dirty}")
    if norm_dirty > 0:
        cur.execute("SELECT nome_normalizado FROM wines_clean WHERE nome_normalizado ~ '[^a-z0-9 ]' LIMIT 10;")
        for r in cur.fetchall():
            print(f"    exemplo: {r[0][:80]}")
    results[19] = str(norm_dirty)

    # ── CHECK 20 — Amostragem direcionada ──
    print("\n=== CHECK 20 — Amostragem direcionada 100 vinhos ===")
    categories = [
        ("HTML", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original LIKE '%&#%' ORDER BY RANDOM() LIMIT 20"),
        ("VOLUME", r"SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original ~* '\d+\s*ml' ORDER BY RANDOM() LIMIT 20"),
        ("PRECO", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original ~ '[$€£]' ORDER BY RANDOM() LIMIT 20"),
        ("PROD_CURTO", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE produtor_extraido IS NOT NULL AND LENGTH(produtor_extraido) < 3 ORDER BY RANDOM() LIMIT 20"),
        ("NAO_MUDOU", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original = nome_limpo AND nome_original LIKE '%ml%' ORDER BY RANDOM() LIMIT 20"),
    ]
    check20_results = {}
    for cat, query in categories:
        print(f"\n  --- {cat} ---")
        cur.execute(query)
        rows = cur.fetchall()
        ok = 0
        falha = 0
        for row in rows:
            orig, limpo, prod = row
            changed = orig != limpo
            if changed:
                ok += 1
            else:
                falha += 1
            tag = "LIMPO" if changed else "IGUAL"
            print(f"    [{tag}] ORIG: {(orig or '')[:80]}")
            print(f"           LIMPO: {(limpo or '')[:80]}")
            print(f"           PROD:  {prod or 'NULL'}")
        check20_results[cat] = (ok, falha, len(rows))
        print(f"  {cat}: {ok} limpos / {falha} iguais (de {len(rows)})")
    c20_str = " | ".join(f"{k}: {v[0]}ok/{v[1]}falha" for k, v in check20_results.items())
    results[20] = c20_str

    # ── CHECK 21 — Grappa e destilados ──
    print("\n=== CHECK 21 — Grappa/destilados ===")
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(grappa|aguardente|brandy|eau.de.vie|marc)\y';")
    grappa = cur.fetchone()[0]
    print(f"  {grappa}")
    results[21] = str(grappa)

    # ── CHECK 22 — Acessorios ──
    print("\n=== CHECK 22 — Acessorios e nao-produtos ===")
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(decanter|saca.?rolha|corkscrew|wine glass|taca|copa|abridor|aerador|balde|cooler|stopper|opener)\y';")
    acess = cur.fetchone()[0]
    print(f"  {acess}")
    results[22] = str(acess)

    # ── RESUMO FINAL ──
    print("\n" + "=" * 60)
    print("=== RESUMO DA AUDITORIA PROFUNDA ===")
    print("=" * 60)
    print(f"CHECK 1  Total:              {results[1]}")
    print(f"CHECK 2  Paises:             {results[2]}")
    print(f"CHECK 3  NULLs:              {results[3]}")
    print(f"CHECK 4  Encoding quebrado:  {results[4]}")
    print(f"CHECK 5  HTML entities:      {results[5]} ← CRITICO")
    print(f"CHECK 6  Volume no nome:     {results[6]} ← CRITICO")
    print(f"CHECK 7  Preco no nome:      {results[7]} ← CRITICO")
    print(f"CHECK 8  Itens nao-vinho:    {results[8]}")
    print(f"CHECK 9  Produtores-dominio: {results[9]}")
    print(f"CHECK 10 Top produtores:     {results[10]}")
    print(f"CHECK 11 Safras absurdas:    {results[11]}")
    print(f"CHECK 12 Nomes curtos/longos:{results[12]}")
    print(f"CHECK 13 Duplicatas:         {results[13]}")
    print(f"CHECK 14 Nomes repetidos:    {results[14]}")
    print(f"CHECK 15 Amostragem 50:      {results[15]}")
    print(f"CHECK 16 Safra duplicada:    {results[16]}")
    print(f"CHECK 17 Nome = so uva:      {results[17]}")
    print(f"CHECK 18 Distrib tamanho:    {results[18]}")
    print(f"CHECK 19 nome_norm limpo:    {results[19]}")
    print(f"CHECK 20 Amostragem direcio: {results[20]}")
    print(f"CHECK 21 Grappa/destilados:  {results[21]}")
    print(f"CHECK 22 Acessorios:         {results[22]}")

    # Veredicto
    print("\n--- VEREDICTO ---")
    falhas = []
    # CHECK 3, 4, 13, 19: DEVE ser 0
    if int(results[3].split()[0]) > 0: falhas.append("CHECK 3 NULLs")
    if int(results[4]) > 0: falhas.append("CHECK 4 Encoding")
    if int(results[13]) > 0: falhas.append("CHECK 13 Duplicatas")
    if int(results[19]) > 0: falhas.append("CHECK 19 nome_norm")
    # CHECK 5, 7, 22: DEVE ser 0
    if int(results[5]) > 0: falhas.append("CHECK 5 HTML entities")
    if int(results[7].split()[0]) > 0: falhas.append("CHECK 7 Preco no nome")
    if int(results[22]) > 0: falhas.append("CHECK 22 Acessorios")
    # CHECK 6: < 0.5%
    vol_n = int(results[6].split()[0])
    vol_p = float(results[6].split('(')[1].split('%')[0])
    if vol_p >= 0.5: falhas.append(f"CHECK 6 Volume ({vol_p:.2f}%)")
    # CHECK 8: < 500
    if int(results[8]) >= 500: falhas.append("CHECK 8 Nao-vinho")
    # CHECK 9: 0
    if int(results[9]) > 0: falhas.append("CHECK 9 Produtores-dominio")
    # CHECK 11: < 500
    if int(results[11]) >= 500: falhas.append("CHECK 11 Safras absurdas")
    # CHECK 12
    c12_parts = results[12].split(',')
    c12_curtos = int(c12_parts[0].split()[1])
    c12_longos = int(c12_parts[1].split()[1])
    if c12_curtos >= 50: falhas.append("CHECK 12 Nomes curtos")
    if c12_longos >= 100: falhas.append("CHECK 12 Nomes longos")
    # CHECK 16: 0
    if int(results[16]) > 0: falhas.append("CHECK 16 Safra duplicada")

    if falhas:
        print(f"REPROVADO — {len(falhas)} falha(s):")
        for f in falhas:
            print(f"  - {f}")
    else:
        print("APROVADO")

    cur.close()
    conn.close()

if __name__ == "__main__":
    run()
