"""Audit script for wines_clean (Phase 1)"""
import psycopg2

conn = psycopg2.connect("postgresql://postgres:postgres123@localhost:5432/winegod_db")
cur = conn.cursor()

print("=" * 60)
print("  AUDITORIA FASE 1 — wines_clean")
print("=" * 60)

# ── 1. CONTAGEM TOTAL ──
print("\n--- 1. CONTAGEM TOTAL ---")
cur.execute("SELECT COUNT(*) FROM wines_clean")
total_clean = cur.fetchone()[0]

cur.execute("""
    SELECT SUM(n_live_tup)::bigint FROM pg_stat_user_tables
    WHERE relname LIKE 'vinhos_%' AND relname NOT LIKE '%_fontes'
""")
total_original = cur.fetchone()[0] or 0

print(f"wines_clean: {total_clean:,}")
print(f"originais:   {total_original:,}")
diff = total_original - total_clean
diff_pct = abs(diff) / max(total_original, 1) * 100
print(f"diferenca:   {diff:,} ({diff_pct:.2f}%)")
if diff_pct > 1:
    print("ALERTA: diferenca > 1%")
else:
    print("OK: diferenca < 1%")

# ── 2. CONTAGEM POR PAIS ──
print("\n--- 2. CONTAGEM POR PAIS ---")
cur.execute("""
    SELECT pais_tabela, COUNT(*) as cnt
    FROM wines_clean
    GROUP BY pais_tabela
    ORDER BY cnt DESC
""")
paises_clean = dict(cur.fetchall())
print(f"Paises em wines_clean: {len(paises_clean)}")

cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name LIKE 'vinhos_%' AND table_name NOT LIKE '%_fontes'
""")
tabelas = [r[0] for r in cur.fetchall()]
print(f"Tabelas originais: {len(tabelas)}")

faltando = []
alertas_pais = []
for t in tabelas:
    pais = t.replace("vinhos_", "")
    if pais not in paises_clean:
        faltando.append(pais)
    else:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        orig = cur.fetchone()[0]
        clean = paises_clean.get(pais, 0)
        diff_pct2 = abs(orig - clean) / max(orig, 1) * 100
        if diff_pct2 > 5:
            alertas_pais.append(f"  {pais}: original {orig:,} vs clean {clean:,} (diff {diff_pct2:.1f}%)")

if faltando:
    print(f"ERRO CRITICO: Paises faltando: {faltando}")
else:
    print("OK: Todos os paises presentes")

if alertas_pais:
    print("ALERTAS de diferenca > 5%:")
    for a in alertas_pais:
        print(a)

# ── 3. CAMPOS OBRIGATORIOS ──
print("\n--- 3. CAMPOS OBRIGATORIOS ---")
erros_campo = []
for campo in ["nome_limpo", "nome_normalizado", "pais_tabela", "id_original"]:
    cur.execute(f"SELECT COUNT(*) FROM wines_clean WHERE {campo} IS NULL OR {campo}::text = ''")
    nulls = cur.fetchone()[0]
    status = "OK" if nulls == 0 else f"ERRO: {nulls:,} NULLs/vazios"
    if nulls > 0:
        erros_campo.append(campo)
    print(f"  {campo}: {status}")

# ── 4. ENCODING ──
print("\n--- 4. ENCODING ---")
cur.execute("""
    SELECT COUNT(*) FROM wines_clean
    WHERE nome_limpo LIKE '%\ufffd%'
""")
quebrados = cur.fetchone()[0]
enc_pct = quebrados / max(total_clean, 1) * 100
print(f"Encoding quebrado: {quebrados:,} ({enc_pct:.3f}%)")

# ── 5. PRODUTOR ──
print("\n--- 5. PRODUTOR ---")
cur.execute("SELECT COUNT(*) FROM wines_clean WHERE produtor_extraido IS NOT NULL")
com_produtor = cur.fetchone()[0]
print(f"Com produtor: {com_produtor:,} ({com_produtor/max(total_clean,1)*100:.1f}%)")

cur.execute("""
    SELECT produtor_extraido, COUNT(*) as cnt
    FROM wines_clean
    WHERE produtor_extraido LIKE '%.com%'
       OR produtor_extraido LIKE '%.br%'
       OR produtor_extraido LIKE '%.net%'
       OR produtor_extraido LIKE '%shop%'
       OR produtor_extraido LIKE '%store%'
       OR produtor_extraido LIKE '%wine.%'
    GROUP BY produtor_extraido
    ORDER BY cnt DESC
    LIMIT 20
""")
dominios = cur.fetchall()
if dominios:
    print("ALERTA: Produtores que parecem dominios de loja:")
    for d in dominios:
        print(f"  '{d[0]}' — {d[1]:,} vinhos")
else:
    print("OK: Nenhum produtor parece dominio de loja")

# ── 6. SAFRA ──
print("\n--- 6. SAFRA ---")
cur.execute("SELECT COUNT(*) FROM wines_clean WHERE safra IS NOT NULL AND (safra < 1900 OR safra > 2026)")
absurdos = cur.fetchone()[0]
print(f"Safras absurdas (<1900 ou >2026): {absurdos:,}")

cur.execute("""
    SELECT COUNT(*) FROM wines_clean
    WHERE safra IS NOT NULL
      AND nome_limpo LIKE '%' || safra::text || ' ' || safra::text || '%'
""")
dups_safra = cur.fetchone()[0]
print(f"Safra duplicada no nome: {dups_safra:,}")

# ── 7. NOMES CURTOS ──
print("\n--- 7. NOMES CURTOS ---")
cur.execute("SELECT COUNT(*) FROM wines_clean WHERE LENGTH(nome_limpo) < 3")
curtos = cur.fetchone()[0]
print(f"Nomes <3 chars: {curtos:,}")

cur.execute("""
    SELECT nome_limpo, COUNT(*) FROM wines_clean
    WHERE LENGTH(nome_limpo) < 5
    GROUP BY nome_limpo ORDER BY COUNT(*) DESC LIMIT 10
""")
for r in cur.fetchall():
    print(f"  '{r[0]}' — {r[1]:,}x")

# ── 8. DUPLICATAS ──
print("\n--- 8. DUPLICATAS ---")
cur.execute("""
    SELECT COUNT(*) FROM (
        SELECT pais_tabela, id_original, COUNT(*)
        FROM wines_clean
        GROUP BY pais_tabela, id_original
        HAVING COUNT(*) > 1
    ) sub
""")
dups = cur.fetchone()[0]
print(f"Duplicatas (pais_tabela + id_original): {dups:,}")

# ── 9. AMOSTRAGEM ──
print("\n--- 9. AMOSTRAGEM (20 vinhos aleatorios) ---")
cur.execute("""
    SELECT pais_tabela, id_original, nome_original, nome_limpo, produtor_extraido, safra
    FROM wines_clean ORDER BY RANDOM() LIMIT 20
""")
amostras = cur.fetchall()
for a in amostras:
    pais, id_orig, nome_orig, nome_limpo, produtor, safra = a
    try:
        cur.execute(f"SELECT nome, vinicola_nome FROM vinhos_{pais} WHERE id = %s", (id_orig,))
        orig = cur.fetchone()
        if orig:
            print(f"  ORIGINAL:  {(orig[0] or '')[:80]}")
            print(f"  LIMPO:     {(nome_limpo or '')[:80]}")
            print(f"  PRODUTOR:  {produtor or 'NULL'} (loja: {(orig[1] or '')[:30]})")
            print(f"  SAFRA:     {safra}")
            print()
        else:
            print(f"  ERRO: vinhos_{pais} id={id_orig} nao encontrado!")
    except Exception as e:
        print(f"  ERRO ao buscar vinhos_{pais} id={id_orig}: {e}")
        conn.rollback()

# ── 10. HASH DEDUP ──
print("\n--- 10. HASH DEDUP ---")
cur.execute("SELECT COUNT(*) FROM wines_clean WHERE hash_dedup IS NOT NULL AND hash_dedup != ''")
com_hash = cur.fetchone()[0]
hash_pct = com_hash / max(total_clean, 1) * 100
print(f"Hash dedup: {com_hash:,} ({hash_pct:.1f}%)")

# ── RESUMO FINAL ──
print("\n" + "=" * 60)
print("  RESUMO DA AUDITORIA")
print("=" * 60)
print(f"Total wines_clean: {total_clean:,}")
print(f"Total originais:   {total_original:,}")
print(f"Diferenca:         {total_original - total_clean:,} ({abs(total_original - total_clean)/max(total_original,1)*100:.2f}%)")
print(f"Paises faltando:   {faltando if faltando else 'nenhum'}")
print(f"Campos NULL:       {erros_campo if erros_campo else 'nenhum'}")
print(f"Encoding quebrado: {quebrados:,}")
print(f"Produtores-dominio: {len(dominios)}")
print(f"Safras absurdas:   {absurdos:,}")
print(f"Nomes curtos (<3): {curtos:,}")
print(f"Duplicatas:        {dups:,}")
print(f"Hash dedup:        {hash_pct:.1f}%")

# Veredicto
problemas = []
if faltando:
    problemas.append(f"Paises faltando: {faltando}")
if erros_campo:
    problemas.append(f"Campos obrigatorios com NULL: {erros_campo}")
if dups > 0:
    problemas.append(f"{dups:,} duplicatas")
if diff_pct > 5:
    problemas.append(f"Diferenca total > 5% ({diff_pct:.1f}%)")
if enc_pct > 0.1:
    problemas.append(f"Encoding quebrado > 0.1% ({enc_pct:.3f}%)")

if problemas:
    print(f"\nVEREDICTO: REPROVADO")
    for p in problemas:
        print(f"  - {p}")
else:
    print(f"\nVEREDICTO: APROVADO")

conn.close()
print("\nAuditoria concluida.")
