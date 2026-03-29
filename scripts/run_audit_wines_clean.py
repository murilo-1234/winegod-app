"""Auditoria Profunda — wines_clean (22 checks, read-only)"""
import psycopg2, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

def main():
    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    results = {}

    # ── CHECK 1 — Contagem total ──
    print("=== CHECK 1 — Contagem total ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean;")
    total_clean = cur.fetchone()[0]
    cur.execute("SELECT SUM(n_live_tup) FROM pg_stat_user_tables WHERE relname LIKE 'vinhos_%' AND relname NOT LIKE '%_fontes';")
    total_orig = cur.fetchone()[0] or 0
    diff_pct = abs(total_clean - total_orig) / total_orig * 100 if total_orig else 0
    print(f"  wines_clean: {total_clean:,}")
    print(f"  originais:   {total_orig:,}")
    print(f"  diff:        {diff_pct:.1f}%")
    results[1] = f"{total_clean:,} vinhos | diff {diff_pct:.1f}% vs original"

    # ── CHECK 2 — Todos os 50 paises presentes ──
    print("\n=== CHECK 2 — Paises ===")
    cur.execute("SELECT pais_tabela, COUNT(*) FROM wines_clean GROUP BY pais_tabela ORDER BY COUNT(*) DESC;")
    paises = cur.fetchall()
    print(f"  {len(paises)} paises encontrados:")
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
    total_nulls = sum(r[1] for r in nulls)
    for campo, cnt in nulls:
        status = "OK" if cnt == 0 else "FALHA"
        print(f"  {campo}: {cnt} [{status}]")
    results[3] = f"{total_nulls} campos com NULL"

    # ── CHECK 4 — Encoding quebrado ──
    print("\n=== CHECK 4 — Encoding quebrado ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%\ufffd%';")
    enc1 = cur.fetchone()[0]
    print(f"  replacement char: {enc1}")
    results[4] = str(enc1)

    # ── CHECK 5 — HTML entities ──
    print("\n=== CHECK 5 — HTML entities (CRITICO) ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%&#%';")
    h1 = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%&amp;%';")
    h2 = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%&nbsp;%';")
    h3 = cur.fetchone()[0]
    html_total = h1 + h2 + h3
    print(f"  &#: {h1} | &amp;: {h2} | &nbsp;: {h3} | TOTAL: {html_total}")
    results[5] = str(html_total)

    # ── CHECK 6 — Volume no nome ──
    print("\n=== CHECK 6 — Volume no nome (CRITICO) ===")
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~* '\d+\s*ml\b';")
    v1 = cur.fetchone()[0]
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~* '\d+\s*cl\b';")
    v2 = cur.fetchone()[0]
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~* '\d[\.,]\d+\s*[lL]\b';")
    v3 = cur.fetchone()[0]
    vol_total = v1 + v2 + v3
    vol_pct = vol_total / total_clean * 100 if total_clean else 0
    print(f"  ml: {v1} | cl: {v2} | L: {v3} | TOTAL: {vol_total} ({vol_pct:.2f}%)")
    results[6] = f"{vol_total} ({vol_pct:.2f}%)"

    # ── CHECK 7 — Preco no nome ──
    print("\n=== CHECK 7 — Preco no nome (CRITICO) ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~ '[$\\u20ac\\u00a3\\u00a5]' OR nome_limpo LIKE '%R$%';")
    preco = cur.fetchone()[0]
    preco_pct = preco / total_clean * 100 if total_clean else 0
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
    print(f"  bebidas: {nv1} | comida: {nv2} | outros: {nv3} | TOTAL: {nv_total}")
    results[8] = str(nv_total)

    # ── CHECK 9 — Produtores que sao dominios ──
    print("\n=== CHECK 9 — Produtores-dominio ===")
    cur.execute(r"""SELECT produtor_extraido, COUNT(*) FROM wines_clean
        WHERE produtor_extraido ~ '\.(com|net|cl|br|co|org|shop)'
        GROUP BY produtor_extraido ORDER BY COUNT(*) DESC LIMIT 20;""")
    dominios = cur.fetchall()
    print(f"  {len(dominios)} produtores-dominio encontrados:")
    for p, c in dominios:
        print(f"    {p}: {c}")
    results[9] = str(sum(c for _, c in dominios)) if dominios else "0"

    # ── CHECK 10 — Top 30 produtores ──
    print("\n=== CHECK 10 — Top 30 produtores ===")
    cur.execute("""SELECT produtor_extraido, COUNT(*) as cnt FROM wines_clean
        WHERE produtor_extraido IS NOT NULL
        GROUP BY produtor_extraido ORDER BY cnt DESC LIMIT 30;""")
    top_prod = cur.fetchall()
    for p, c in top_prod:
        print(f"  {p}: {c:,}")
    results[10] = "ver lista acima"

    # ── CHECK 11 — Safras absurdas ──
    print("\n=== CHECK 11 — Safras absurdas ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE safra IS NOT NULL AND (safra < 1900 OR safra > 2026);")
    safras_abs = cur.fetchone()[0]
    cur.execute("SELECT safra, COUNT(*) FROM wines_clean WHERE safra IS NOT NULL AND (safra < 1900 OR safra > 2026) GROUP BY safra ORDER BY COUNT(*) DESC LIMIT 10;")
    safras_det = cur.fetchall()
    print(f"  Total: {safras_abs}")
    for s, c in safras_det:
        print(f"    {s}: {c}")
    results[11] = str(safras_abs)

    # ── CHECK 12 — Nomes curtos/longos ──
    print("\n=== CHECK 12 — Nomes curtos/longos ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE LENGTH(nome_limpo) < 3;")
    curtos = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE LENGTH(nome_limpo) > 200;")
    longos = cur.fetchone()[0]
    cur.execute("SELECT nome_limpo FROM wines_clean WHERE LENGTH(nome_limpo) < 5 LIMIT 10;")
    curtos_ex = cur.fetchall()
    print(f"  curtos (<3): {curtos} | longos (>200): {longos}")
    print(f"  exemplos curtos (<5): {[r[0] for r in curtos_ex]}")
    results[12] = f"curtos {curtos}, longos {longos}"

    # ── CHECK 13 — Duplicatas ──
    print("\n=== CHECK 13 — Duplicatas (pais_tabela + id_original) ===")
    cur.execute("""SELECT COUNT(*) FROM (
        SELECT pais_tabela, id_original FROM wines_clean
        GROUP BY pais_tabela, id_original HAVING COUNT(*) > 1
    ) sub;""")
    dups = cur.fetchone()[0]
    print(f"  {dups}")
    results[13] = str(dups)

    # ── CHECK 14 — Nomes mais repetidos ──
    print("\n=== CHECK 14 — Nomes mais repetidos ===")
    cur.execute("SELECT nome_normalizado, COUNT(*) FROM wines_clean GROUP BY nome_normalizado ORDER BY COUNT(*) DESC LIMIT 20;")
    reps = cur.fetchall()
    for n, c in reps:
        print(f"  {n}: {c}")
    results[14] = " | ".join(f"{n}:{c}" for n, c in reps[:5])

    # ── CHECK 15 — Amostragem 50 vinhos aleatorios ──
    print("\n=== CHECK 15 — Amostragem 50 vinhos aleatorios ===")
    cur.execute("""SELECT pais_tabela, id_original, nome_original, nome_limpo,
           produtor_extraido, safra, nome_normalizado
    FROM wines_clean ORDER BY RANDOM() LIMIT 50;""")
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
    print(f"\n  Resumo: {mudaram} mudaram, {iguais} iguais")
    results[15] = f"{mudaram} mudaram / {iguais} iguais"

    # ── CHECK 16 — Safra duplicada no nome ──
    print("\n=== CHECK 16 — Safra duplicada no nome ===")
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE safra IS NOT NULL AND nome_limpo ~ (safra::text || '\s+' || safra::text);")
    safra_dup = cur.fetchone()[0]
    print(f"  {safra_dup}")
    results[16] = str(safra_dup)

    # ── CHECK 17 — Nome = so uva ──
    print("\n=== CHECK 17 — Nome = so uva ===")
    cur.execute("""SELECT nome_limpo, COUNT(*) FROM wines_clean
        WHERE LOWER(nome_limpo) IN ('chardonnay','merlot','cabernet sauvignon','pinot noir','malbec','syrah','shiraz','sauvignon blanc','riesling','tempranillo','sangiovese','grenache','carmenere','tannat','prosecco','rose','brut','reserva','crianza','tinto','blanco','red','white')
        GROUP BY nome_limpo ORDER BY COUNT(*) DESC;""")
    uva_only = cur.fetchall()
    uva_total = sum(c for _, c in uva_only)
    for n, c in uva_only:
        print(f"  {n}: {c}")
    print(f"  TOTAL: {uva_total}")
    results[17] = str(uva_total)

    # ── CHECK 18 — Distribuicao de tamanho ──
    print("\n=== CHECK 18 — Distribuicao de tamanho do nome ===")
    cur.execute("""SELECT
        CASE
            WHEN LENGTH(nome_limpo) < 5 THEN '<5'
            WHEN LENGTH(nome_limpo) < 10 THEN '5-9'
            WHEN LENGTH(nome_limpo) < 20 THEN '10-19'
            WHEN LENGTH(nome_limpo) < 40 THEN '20-39'
            WHEN LENGTH(nome_limpo) < 80 THEN '40-79'
            ELSE '80+'
        END as faixa,
        COUNT(*) as qtd
    FROM wines_clean GROUP BY 1 ORDER BY 1;""")
    faixas = cur.fetchall()
    for f, q in faixas:
        print(f"  {f}: {q:,}")
    results[18] = " | ".join(f"{f}:{q:,}" for f, q in faixas)

    # ── CHECK 19 — Consistencia nome_normalizado ──
    print("\n=== CHECK 19 — nome_normalizado limpo ===")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_normalizado ~ '[^a-z0-9 ]';")
    norm_dirty = cur.fetchone()[0]
    print(f"  chars especiais em nome_normalizado: {norm_dirty}")
    results[19] = str(norm_dirty)

    # ── CHECK 20 — Amostragem direcionada ──
    print("\n=== CHECK 20 — Amostragem direcionada (100 vinhos) ===")
    categories = [
        ("HTML", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original LIKE '%&#%' ORDER BY RANDOM() LIMIT 20"),
        ("VOLUME", r"SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original ~* '\d+\s*ml' ORDER BY RANDOM() LIMIT 20"),
        ("PRECO", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original ~ '[$\u20ac\u00a3]' ORDER BY RANDOM() LIMIT 20"),
        ("PROD_CURTO", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE produtor_extraido IS NOT NULL AND LENGTH(produtor_extraido) < 3 ORDER BY RANDOM() LIMIT 20"),
        ("NAO_MUDOU", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original = nome_limpo AND nome_original LIKE '%ml%' ORDER BY RANDOM() LIMIT 20"),
    ]
    check20_results = {}
    for cat, query in categories:
        print(f"\n  --- {cat} ---")
        try:
            cur.execute(query)
            rows = cur.fetchall()
        except Exception as e:
            print(f"  ERRO: {e}")
            conn.rollback()
            check20_results[cat] = "ERRO"
            continue
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
        check20_results[cat] = f"{ok} ok/{falha} falha"
        print(f"  {cat}: {ok} limpos, {falha} iguais")
    results[20] = " | ".join(f"{k}: {v}" for k, v in check20_results.items())

    # ── CHECK 21 — Grappa e destilados ──
    print("\n=== CHECK 21 — Grappa/destilados ===")
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(grappa|aguardente|brandy|eau.de.vie|marc)\y';")
    grappa = cur.fetchone()[0]
    print(f"  {grappa}")
    results[21] = str(grappa)

    # ── CHECK 22 — Acessorios ──
    print("\n=== CHECK 22 — Acessorios ===")
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
    print(f"CHECK 5  HTML entities:      {results[5]} <- CRITICO")
    print(f"CHECK 6  Volume no nome:     {results[6]} <- CRITICO")
    print(f"CHECK 7  Preco no nome:      {results[7]} <- CRITICO")
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
    print(f"CHECK 18 Distrib. tamanho:   {results[18]}")
    print(f"CHECK 19 nome_norm limpo:    {results[19]}")
    print(f"CHECK 20 Amostragem direcio: {results[20]}")
    print(f"CHECK 21 Grappa/destilados:  {results[21]}")
    print(f"CHECK 22 Acessorios:         {results[22]}")

    # ── VEREDICTO ──
    fails = []
    # CHECK 3, 4, 13, 19: DEVE ser 0
    if total_nulls > 0: fails.append(f"CHECK 3: {total_nulls} NULLs")
    if enc1 > 0: fails.append(f"CHECK 4: {enc1} encoding quebrado")
    if dups > 0: fails.append(f"CHECK 13: {dups} duplicatas")
    if norm_dirty > 0: fails.append(f"CHECK 19: {norm_dirty} nome_norm sujos")
    # CHECK 5, 7, 22: DEVE ser 0
    if html_total > 0: fails.append(f"CHECK 5: {html_total} HTML entities")
    if preco > 0: fails.append(f"CHECK 7: {preco} precos no nome")
    if acess > 0: fails.append(f"CHECK 22: {acess} acessorios")
    # CHECK 6: < 0.5%
    if vol_pct >= 0.5: fails.append(f"CHECK 6: {vol_pct:.2f}% volume no nome (>= 0.5%)")
    # CHECK 8: < 500
    if nv_total >= 500: fails.append(f"CHECK 8: {nv_total} nao-vinho (>= 500)")
    # CHECK 9: 0
    if len(dominios) > 0: fails.append(f"CHECK 9: {sum(c for _, c in dominios)} produtores-dominio")
    # CHECK 11: < 500
    if safras_abs >= 500: fails.append(f"CHECK 11: {safras_abs} safras absurdas (>= 500)")
    # CHECK 12
    if curtos >= 50: fails.append(f"CHECK 12: {curtos} nomes curtos (>= 50)")
    if longos >= 100: fails.append(f"CHECK 12: {longos} nomes longos (>= 100)")
    # CHECK 16: 0
    if safra_dup > 0: fails.append(f"CHECK 16: {safra_dup} safra duplicada")

    print()
    if fails:
        print("VEREDICTO: REPROVADO")
        print("Motivos:")
        for f in fails:
            print(f"  - {f}")
    else:
        print("VEREDICTO: APROVADO")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
