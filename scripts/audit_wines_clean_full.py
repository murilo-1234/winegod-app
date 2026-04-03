"""Auditoria Profunda da wines_clean — 22 checks"""
import psycopg2

CONN = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

def run():
    conn = psycopg2.connect(CONN)
    cur = conn.cursor()

    print("=" * 60)
    print("AUDITORIA PROFUNDA — wines_clean")
    print("=" * 60)

    # ── CHECK 1 — Contagem total ──
    print("\n### CHECK 1 — Contagem total")
    cur.execute("SELECT COUNT(*) FROM wines_clean;")
    total_clean = cur.fetchone()[0]
    print(f"  wines_clean: {total_clean:,}")

    cur.execute("SELECT SUM(n_live_tup) FROM pg_stat_user_tables WHERE relname LIKE 'vinhos_%' AND relname NOT LIKE '%_fontes';")
    row = cur.fetchone()
    total_orig = int(row[0]) if row[0] else 0
    diff_pct = abs(total_clean - total_orig) / total_orig * 100 if total_orig > 0 else 0
    print(f"  Soma tabelas originais (pg_stat): {total_orig:,}")
    print(f"  Diferenca: {diff_pct:.1f}%  {'OK' if diff_pct < 3 else 'ALERTA'}")

    # ── CHECK 2 — Paises presentes ──
    print("\n### CHECK 2 — Todos os 50 paises presentes")
    cur.execute("SELECT pais_tabela, COUNT(*) FROM wines_clean GROUP BY pais_tabela ORDER BY COUNT(*) DESC;")
    paises = cur.fetchall()
    print(f"  Paises distintos: {len(paises)}")
    for p, c in paises:
        print(f"    {p}: {c:,}")

    # ── CHECK 3 — Campos obrigatorios NULL ──
    print("\n### CHECK 3 — Campos obrigatorios NULL")
    cur.execute("""
        SELECT 'nome_limpo' as campo, COUNT(*) FROM wines_clean WHERE nome_limpo IS NULL OR nome_limpo = ''
        UNION ALL SELECT 'nome_normalizado', COUNT(*) FROM wines_clean WHERE nome_normalizado IS NULL OR nome_normalizado = ''
        UNION ALL SELECT 'pais_tabela', COUNT(*) FROM wines_clean WHERE pais_tabela IS NULL OR pais_tabela = ''
        UNION ALL SELECT 'id_original', COUNT(*) FROM wines_clean WHERE id_original IS NULL;
    """)
    nulls_total = 0
    for campo, cnt in cur.fetchall():
        status = "OK" if cnt == 0 else "FALHA"
        print(f"  {campo}: {cnt} {status}")
        nulls_total += cnt

    # ── CHECK 4 — Encoding quebrado ──
    print("\n### CHECK 4 — Encoding quebrado")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%\ufffd%';")
    enc1 = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%\ufffd%';")
    enc2 = cur.fetchone()[0]
    enc_total = max(enc1, enc2)
    print(f"  Replacement chars: {enc_total}  {'OK' if enc_total == 0 else 'FALHA'}")

    # ── CHECK 5 — HTML entities (CRITICO) ──
    print("\n### CHECK 5 — HTML entities (CRITICO)")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%&#%';")
    html1 = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%&amp;%';")
    html2 = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%&nbsp;%';")
    html3 = cur.fetchone()[0]
    html_total = html1 + html2 + html3
    print(f"  &#: {html1} | &amp;: {html2} | &nbsp;: {html3} | Total: {html_total}  {'OK' if html_total == 0 else 'FALHA CRITICA'}")

    # ── CHECK 6 — Volume no nome (CRITICO) ──
    print("\n### CHECK 6 — Volume no nome (CRITICO)")
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~* '\d+\s*ml\b';")
    vol_ml = cur.fetchone()[0]
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~* '\d+\s*cl\b';")
    vol_cl = cur.fetchone()[0]
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~* '\d[\.,]\d+\s*[lL]\b';")
    vol_l = cur.fetchone()[0]
    vol_total = vol_ml + vol_cl + vol_l
    vol_pct = vol_total / total_clean * 100 if total_clean > 0 else 0
    print(f"  ml: {vol_ml} | cl: {vol_cl} | L: {vol_l} | Total: {vol_total} ({vol_pct:.2f}%)  {'OK' if vol_pct < 0.5 else 'FALHA CRITICA'}")

    # ── CHECK 7 — Preco no nome (CRITICO) ──
    print("\n### CHECK 7 — Preco no nome (CRITICO)")
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~ '[\$€£¥]' OR nome_limpo LIKE '%R$%';")
    preco = cur.fetchone()[0]
    preco_pct = preco / total_clean * 100 if total_clean > 0 else 0
    print(f"  Preco no nome: {preco} ({preco_pct:.3f}%)  {'OK' if preco_pct < 0.1 else 'FALHA CRITICA'}")

    # ── CHECK 8 — Itens nao-vinho ──
    print("\n### CHECK 8 — Itens nao-vinho")
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(whisky|whiskey|vodka|tequila|cognac)\y';")
    nv1 = cur.fetchone()[0]
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(queijo|cheese|fromage|chocolate)\y';")
    nv2 = cur.fetchone()[0]
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(red bull|coca.cola|gift card|gutschein)\y';")
    nv3 = cur.fetchone()[0]
    nv_total = nv1 + nv2 + nv3
    print(f"  Bebidas: {nv1} | Comida: {nv2} | Outros: {nv3} | Total: {nv_total}  {'OK' if nv_total < 500 else 'ALERTA'}")

    # ── CHECK 9 — Produtores que sao dominios ──
    print("\n### CHECK 9 — Produtores-dominio")
    cur.execute(r"""
        SELECT produtor_extraido, COUNT(*) FROM wines_clean
        WHERE produtor_extraido ~ '\.(com|net|cl|br|co|org|shop)'
        GROUP BY produtor_extraido ORDER BY COUNT(*) DESC LIMIT 20;
    """)
    dom_rows = cur.fetchall()
    print(f"  Produtores-dominio encontrados: {len(dom_rows)}  {'OK' if len(dom_rows) == 0 else 'FALHA'}")
    for p, c in dom_rows:
        print(f"    {p}: {c}")

    # ── CHECK 10 — Top 30 produtores ──
    print("\n### CHECK 10 — Top 30 produtores")
    cur.execute("""
        SELECT produtor_extraido, COUNT(*) as cnt FROM wines_clean
        WHERE produtor_extraido IS NOT NULL
        GROUP BY produtor_extraido ORDER BY cnt DESC LIMIT 30;
    """)
    top_prods = cur.fetchall()
    suspicious_words = {'vinho', 'wine', 'tinto', 'chianti', 'bordeaux', 'the', 'de', 'a', 'o', 'la', 'le', 'el'}
    for p, c in top_prods:
        flag = " ← SUSPEITO" if p and p.lower().strip() in suspicious_words else ""
        print(f"    {p}: {c:,}{flag}")

    # ── CHECK 11 — Safras absurdas ──
    print("\n### CHECK 11 — Safras absurdas")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE safra IS NOT NULL AND (safra < 1900 OR safra > 2026);")
    safra_abs = cur.fetchone()[0]
    print(f"  Safras fora 1900-2026: {safra_abs}  {'OK' if safra_abs < 500 else 'ALERTA'}")
    cur.execute("SELECT safra, COUNT(*) FROM wines_clean WHERE safra IS NOT NULL AND (safra < 1900 OR safra > 2026) GROUP BY safra ORDER BY COUNT(*) DESC LIMIT 10;")
    for s, c in cur.fetchall():
        print(f"    Safra {s}: {c}")

    # ── CHECK 12 — Nomes curtos/longos ──
    print("\n### CHECK 12 — Nomes curtos/longos")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE LENGTH(nome_limpo) < 3;")
    curtos = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE LENGTH(nome_limpo) > 200;")
    longos = cur.fetchone()[0]
    print(f"  Curtos (<3): {curtos}  {'OK' if curtos < 50 else 'ALERTA'}")
    print(f"  Longos (>200): {longos}  {'OK' if longos < 100 else 'ALERTA'}")
    cur.execute("SELECT nome_limpo FROM wines_clean WHERE LENGTH(nome_limpo) < 5 LIMIT 10;")
    for (n,) in cur.fetchall():
        print(f"    Curto: '{n}'")

    # ── CHECK 13 — Duplicatas (pais_tabela + id_original) ──
    print("\n### CHECK 13 — Duplicatas")
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT pais_tabela, id_original FROM wines_clean
            GROUP BY pais_tabela, id_original HAVING COUNT(*) > 1
        ) sub;
    """)
    dups = cur.fetchone()[0]
    print(f"  Duplicatas (pais+id): {dups}  {'OK' if dups == 0 else 'FALHA'}")

    # ── CHECK 14 — Nomes mais repetidos ──
    print("\n### CHECK 14 — Nomes mais repetidos")
    cur.execute("SELECT nome_normalizado, COUNT(*) FROM wines_clean GROUP BY nome_normalizado ORDER BY COUNT(*) DESC LIMIT 20;")
    for n, c in cur.fetchall():
        print(f"    '{n}': {c}")

    # ── CHECK 15 — Amostragem 50 aleatorios ──
    print("\n### CHECK 15 — Amostragem 50 vinhos aleatorios")
    cur.execute("""
        SELECT wc.pais_tabela, wc.id_original, wc.nome_original, wc.nome_limpo,
               wc.produtor_extraido, wc.safra, wc.nome_normalizado
        FROM wines_clean wc ORDER BY RANDOM() LIMIT 50
    """)
    changed_count = 0
    same_count = 0
    for row in cur.fetchall():
        pais, id_orig, nome_orig, nome_limpo, produtor, safra, nome_norm = row
        changed = "MUDOU" if nome_orig != nome_limpo else "igual"
        if nome_orig != nome_limpo:
            changed_count += 1
        else:
            same_count += 1
        print(f"  [{pais}] {changed}")
        print(f"    ORIG:  {(nome_orig or '')[:100]}")
        print(f"    LIMPO: {(nome_limpo or '')[:100]}")
        print(f"    PROD:  {produtor or 'NULL'} | SAFRA: {safra}")
        print()
    print(f"  Resumo amostragem: {changed_count} mudaram, {same_count} iguais")

    # ── CHECK 16 — Safra duplicada no nome ──
    print("\n### CHECK 16 — Safra duplicada no nome")
    cur.execute("""
        SELECT COUNT(*) FROM wines_clean
        WHERE safra IS NOT NULL
          AND nome_limpo ~ (safra::text || '\\s+' || safra::text);
    """)
    safra_dup = cur.fetchone()[0]
    print(f"  Safra duplicada: {safra_dup}  {'OK' if safra_dup == 0 else 'FALHA'}")

    # ── CHECK 17 — Nome = so uva ──
    print("\n### CHECK 17 — Nome = so uva")
    cur.execute("""
        SELECT nome_limpo, COUNT(*) FROM wines_clean
        WHERE LOWER(nome_limpo) IN ('chardonnay','merlot','cabernet sauvignon','pinot noir','malbec','syrah','shiraz','sauvignon blanc','riesling','tempranillo','sangiovese','grenache','carmenere','tannat','prosecco','rose','brut','reserva','crianza','tinto','blanco','red','white')
        GROUP BY nome_limpo ORDER BY COUNT(*) DESC;
    """)
    uva_rows = cur.fetchall()
    uva_total = sum(c for _, c in uva_rows)
    print(f"  Nomes = so uva: {uva_total}")
    for n, c in uva_rows:
        print(f"    '{n}': {c}")

    # ── CHECK 18 — Distribuicao tamanho ──
    print("\n### CHECK 18 — Distribuicao tamanho do nome")
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
    for faixa, qtd in cur.fetchall():
        print(f"    {faixa}: {qtd:,}")

    # ── CHECK 19 — nome_normalizado limpo ──
    print("\n### CHECK 19 — nome_normalizado limpo")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_normalizado ~ '[^a-z0-9 ]';")
    norm_dirty = cur.fetchone()[0]
    print(f"  Chars especiais em nome_normalizado: {norm_dirty}  {'OK' if norm_dirty == 0 else 'FALHA'}")

    # ── CHECK 20 — Amostragem direcionada ──
    print("\n### CHECK 20 — Amostragem direcionada (100 vinhos)")
    categories = [
        ("HTML", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original LIKE '%&#%' ORDER BY RANDOM() LIMIT 20"),
        ("VOLUME", r"SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original ~* '\d+\s*ml' ORDER BY RANDOM() LIMIT 20"),
        ("PRECO", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original ~ '[$€£]' ORDER BY RANDOM() LIMIT 20"),
        ("PROD_CURTO", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE produtor_extraido IS NOT NULL AND LENGTH(produtor_extraido) < 3 ORDER BY RANDOM() LIMIT 20"),
        ("NAO_MUDOU", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original = nome_limpo AND nome_original LIKE '%ml%' ORDER BY RANDOM() LIMIT 20"),
    ]
    for cat, query in categories:
        print(f"\n  === {cat} ===")
        cur.execute(query)
        rows = cur.fetchall()
        ok = 0
        falha = 0
        for row in rows:
            orig, limpo, prod = row
            changed = "LIMPO" if orig != limpo else "IGUAL"
            if orig != limpo:
                ok += 1
            else:
                falha += 1
            print(f"    [{changed}] ORIG: {(orig or '')[:80]}")
            print(f"           LIMPO: {(limpo or '')[:80]}")
            print(f"           PROD:  {prod or 'NULL'}")
        print(f"  {cat}: {ok} limpos, {falha} iguais (de {len(rows)} amostras)")

    # ── CHECK 21 — Grappa/destilados ──
    print("\n### CHECK 21 — Grappa/destilados")
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(grappa|aguardente|brandy|eau.de.vie|marc)\y';")
    grappa = cur.fetchone()[0]
    print(f"  Grappa/destilados: {grappa}")

    # ── CHECK 22 — Acessorios ──
    print("\n### CHECK 22 — Acessorios")
    cur.execute(r"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(decanter|saca.?rolha|corkscrew|wine glass|taca|copa|abridor|aerador|balde|cooler|stopper|opener)\y';")
    acessorios = cur.fetchone()[0]
    print(f"  Acessorios: {acessorios}  {'OK' if acessorios == 0 else 'FALHA'}")

    # ── RESUMO FINAL ──
    print("\n" + "=" * 60)
    print("=== RESUMO DA AUDITORIA PROFUNDA ===")
    print("=" * 60)
    print(f"CHECK 1  Total:              {total_clean:,} vinhos | diff {diff_pct:.1f}% vs original ({total_orig:,})")
    print(f"CHECK 2  Paises:             {len(paises)} paises")
    print(f"CHECK 3  NULLs:              {nulls_total}")
    print(f"CHECK 4  Encoding quebrado:  {enc_total}")
    print(f"CHECK 5  HTML entities:      {html_total} ← CRITICO")
    print(f"CHECK 6  Volume no nome:     {vol_total} ({vol_pct:.2f}%) ← CRITICO")
    print(f"CHECK 7  Preco no nome:      {preco} ({preco_pct:.3f}%) ← CRITICO")
    print(f"CHECK 8  Itens nao-vinho:    {nv_total}")
    print(f"CHECK 9  Produtores-dominio: {len(dom_rows)}")
    print(f"CHECK 10 Top produtores:     ver lista acima")
    print(f"CHECK 11 Safras absurdas:    {safra_abs}")
    print(f"CHECK 12 Nomes curtos/longos:curtos {curtos}, longos {longos}")
    print(f"CHECK 13 Duplicatas:         {dups}")
    print(f"CHECK 14 Nomes repetidos:    ver lista acima")
    print(f"CHECK 15 Amostragem 50:      {changed_count} mudaram / {same_count} iguais")
    print(f"CHECK 16 Safra duplicada:    {safra_dup}")
    print(f"CHECK 17 Nome = so uva:      {uva_total}")
    print(f"CHECK 18 Distribuicao:       ver tabela acima")
    print(f"CHECK 19 nome_norm limpo:    {norm_dirty} com chars especiais")
    print(f"CHECK 20 Amostragem direcio: ver detalhes acima")
    print(f"CHECK 21 Grappa/destilados:  {grappa}")
    print(f"CHECK 22 Acessorios:         {acessorios}")

    # Veredicto
    print("\n" + "-" * 60)
    falhas = []
    if nulls_total > 0: falhas.append(f"CHECK 3: {nulls_total} NULLs")
    if enc_total > 0: falhas.append(f"CHECK 4: {enc_total} encoding quebrado")
    if dups > 0: falhas.append(f"CHECK 13: {dups} duplicatas")
    if norm_dirty > 0: falhas.append(f"CHECK 19: {norm_dirty} chars especiais em nome_normalizado")
    if html_total > 0: falhas.append(f"CHECK 5: {html_total} HTML entities")
    if preco_pct >= 0.1: falhas.append(f"CHECK 7: {preco} precos no nome ({preco_pct:.3f}%)")
    if acessorios > 0: falhas.append(f"CHECK 22: {acessorios} acessorios")
    if vol_pct >= 0.5: falhas.append(f"CHECK 6: {vol_total} volumes ({vol_pct:.2f}%)")
    if nv_total >= 500: falhas.append(f"CHECK 8: {nv_total} itens nao-vinho")
    if len(dom_rows) > 0: falhas.append(f"CHECK 9: {len(dom_rows)} produtores-dominio")
    if safra_abs >= 500: falhas.append(f"CHECK 11: {safra_abs} safras absurdas")
    if curtos >= 50: falhas.append(f"CHECK 12: {curtos} nomes curtos")
    if longos >= 100: falhas.append(f"CHECK 12: {longos} nomes longos")
    if safra_dup > 0: falhas.append(f"CHECK 16: {safra_dup} safras duplicadas")

    if falhas:
        print("VEREDICTO: REPROVADO")
        for f in falhas:
            print(f"  - {f}")
    else:
        print("VEREDICTO: APROVADO")

    cur.close()
    conn.close()

if __name__ == "__main__":
    run()
