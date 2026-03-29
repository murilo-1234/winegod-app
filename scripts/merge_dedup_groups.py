#!/usr/bin/env python3
"""
merge_dedup_groups.py — Merge 10 dedup group tables into wines_unique + dedup_quarantine.
"""

import psycopg2
import sys

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
TOTAL_BEFORE_DEDUP = 3_955_624

def get_conn():
    return psycopg2.connect(DB_URL)

def step1_verify_tables(cur):
    print("\n=== STEP 1: Verificando tabelas ===")
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name LIKE 'wines_unique_g%%'
        ORDER BY table_name;
    """)
    found_wu = [r[0] for r in cur.fetchall()]

    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name LIKE 'dedup_quarantine_g%%'
        ORDER BY table_name;
    """)
    found_dq = [r[0] for r in cur.fetchall()]

    expected_wu = [f"wines_unique_g{i}" for i in range(1, 11)]
    expected_dq = [f"dedup_quarantine_g{i}" for i in range(1, 11)]

    missing_wu = set(expected_wu) - set(found_wu)
    missing_dq = set(expected_dq) - set(found_dq)

    if missing_wu:
        print(f"ERRO: Faltam tabelas wines_unique: {sorted(missing_wu)}")
        sys.exit(1)
    if missing_dq:
        print(f"ERRO: Faltam tabelas dedup_quarantine: {sorted(missing_dq)}")
        sys.exit(1)

    print(f"  wines_unique_g1..g10: OK ({len(found_wu)} tabelas)")
    print(f"  dedup_quarantine_g1..g10: OK ({len(found_dq)} tabelas)")

def step2_show_counts(cur):
    print("\n=== STEP 2: Contagens por grupo ===")

    print("\n  wines_unique:")
    total_wu = 0
    for i in range(1, 11):
        cur.execute(f"SELECT COUNT(*) FROM wines_unique_g{i}")
        cnt = cur.fetchone()[0]
        total_wu += cnt
        print(f"    g{i:2d}: {cnt:>10,}")
    print(f"    TOTAL: {total_wu:>10,}")

    print("\n  dedup_quarantine:")
    total_dq = 0
    for i in range(1, 11):
        cur.execute(f"SELECT COUNT(*) FROM dedup_quarantine_g{i}")
        cnt = cur.fetchone()[0]
        total_dq += cnt
        print(f"    g{i:2d}: {cnt:>10,}")
    print(f"    TOTAL: {total_dq:>10,}")

    return total_wu, total_dq

def step3_create_wines_unique(cur):
    print("\n=== STEP 3: Criando wines_unique ===")

    cur.execute("DROP TABLE IF EXISTS wines_unique CASCADE")

    unions = " UNION ALL ".join(
        [f"SELECT * FROM wines_unique_g{i}" for i in range(1, 11)]
    )
    cur.execute(f"CREATE TABLE wines_unique AS {unions}")
    print("  Tabela criada com UNION ALL de g1..g10")

    # Reset IDs
    cur.execute("ALTER TABLE wines_unique ADD COLUMN new_id SERIAL")
    cur.execute("ALTER TABLE wines_unique DROP COLUMN id")
    cur.execute("ALTER TABLE wines_unique RENAME COLUMN new_id TO id")
    cur.execute("ALTER TABLE wines_unique ADD PRIMARY KEY (id)")
    print("  IDs resetados (sequenciais)")

    # Indices
    cur.execute("CREATE INDEX idx_wu_nome ON wines_unique (nome_normalizado)")
    cur.execute("CREATE INDEX idx_wu_produtor ON wines_unique (produtor_normalizado) WHERE produtor_normalizado IS NOT NULL")
    cur.execute("CREATE INDEX idx_wu_hash ON wines_unique (hash_dedup) WHERE hash_dedup IS NOT NULL")
    cur.execute("CREATE INDEX idx_wu_pais ON wines_unique (pais_tabela)")
    cur.execute("CREATE INDEX idx_wu_ean ON wines_unique (ean_gtin) WHERE ean_gtin IS NOT NULL")
    cur.execute("CREATE INDEX idx_wu_match ON wines_unique (match_type)")
    print("  6 indices criados")

def step4_create_dedup_quarantine(cur):
    print("\n=== STEP 4: Criando dedup_quarantine ===")

    cur.execute("DROP TABLE IF EXISTS dedup_quarantine CASCADE")

    unions = " UNION ALL ".join(
        [f"SELECT * FROM dedup_quarantine_g{i}" for i in range(1, 11)]
    )
    cur.execute(f"CREATE TABLE dedup_quarantine AS {unions}")
    print("  Tabela criada com UNION ALL de g1..g10")

def step5_audit(cur):
    print("\n=== STEP 5: Auditoria ===")

    cur.execute("SELECT COUNT(*) FROM wines_unique")
    total_u = cur.fetchone()[0]
    print(f"\n  Total vinhos unicos: {total_u:,}")

    cur.execute("SELECT COUNT(*) FROM dedup_quarantine")
    total_q = cur.fetchone()[0]
    print(f"  Total quarentena: {total_q:,}")

    # Por tipo de match
    print("\n  Por match_type:")
    cur.execute("""
        SELECT match_type, COUNT(*), ROUND(AVG(match_probability)::numeric, 2) as prob_media
        FROM wines_unique GROUP BY match_type ORDER BY COUNT(*) DESC
    """)
    match_counts = {}
    for row in cur.fetchall():
        mt, cnt, prob = row
        match_counts[mt] = cnt
        print(f"    {mt}: {cnt:,} (prob media: {prob})")

    # Por pais
    print("\n  Por pais (top 20):")
    cur.execute("""
        SELECT pais_tabela, COUNT(*) FROM wines_unique
        GROUP BY pais_tabela ORDER BY COUNT(*) DESC LIMIT 20
    """)
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]:,}")

    # Distribuicao de copias
    print("\n  Distribuicao de copias (top 15):")
    cur.execute("""
        SELECT total_copias, COUNT(*) FROM wines_unique
        GROUP BY total_copias ORDER BY total_copias DESC LIMIT 15
    """)
    for row in cur.fetchall():
        print(f"    {row[0]} copias: {row[1]:,} vinhos")

    # Grupos muito grandes
    print("\n  Grupos >50 copias (suspeitos):")
    cur.execute("""
        SELECT id, nome_limpo, total_copias, match_type
        FROM wines_unique WHERE total_copias > 50
        ORDER BY total_copias DESC LIMIT 20
    """)
    big_groups = cur.fetchall()
    if big_groups:
        for row in big_groups:
            print(f"    ID {row[0]}: {row[1]} ({row[2]} copias, {row[3]})")
    else:
        print("    Nenhum grupo >50 copias")

    # Amostra deterministicos
    print("\n  Amostra de 20 merges deterministicos:")
    cur.execute("""
        SELECT nome_limpo, produtor, safra, total_copias, match_type
        FROM wines_unique WHERE match_type = 'deterministic'
        ORDER BY RANDOM() LIMIT 20
    """)
    for row in cur.fetchall():
        print(f"    {row[0]} | {row[1]} | {row[2]} | {row[3]} copias")

    # Amostra Splink
    print("\n  Amostra de 20 merges Splink:")
    cur.execute("""
        SELECT nome_limpo, produtor, safra, total_copias, match_type, match_probability
        FROM wines_unique WHERE match_type = 'splink_high'
        ORDER BY RANDOM() LIMIT 20
    """)
    for row in cur.fetchall():
        print(f"    {row[0]} | {row[1]} | {row[2]} | {row[3]} copias | prob {row[5]}")

    # Quarentena amostras
    print("\n  Amostra de 20 quarentena:")
    cur.execute("""
        SELECT nome_a, nome_b, match_probability, motivo
        FROM dedup_quarantine ORDER BY RANDOM() LIMIT 20
    """)
    for row in cur.fetchall():
        print(f"    {row[0]} vs {row[1]} | prob {row[2]} | {row[3]}")

    return total_u, total_q, match_counts, len(big_groups)

def step6_drop_temp(cur, audit_ok):
    print("\n=== STEP 6: Limpeza de tabelas temporarias ===")
    if not audit_ok:
        print("  PULANDO DROP — auditoria mostrou problemas. Verificar manualmente.")
        return

    cur.execute("""
        DROP TABLE IF EXISTS wines_unique_g1, wines_unique_g2, wines_unique_g3,
            wines_unique_g4, wines_unique_g5
    """)
    cur.execute("""
        DROP TABLE IF EXISTS wines_unique_g6, wines_unique_g7, wines_unique_g8,
            wines_unique_g9, wines_unique_g10
    """)
    cur.execute("""
        DROP TABLE IF EXISTS dedup_quarantine_g1, dedup_quarantine_g2, dedup_quarantine_g3,
            dedup_quarantine_g4, dedup_quarantine_g5
    """)
    cur.execute("""
        DROP TABLE IF EXISTS dedup_quarantine_g6, dedup_quarantine_g7, dedup_quarantine_g8,
            dedup_quarantine_g9, dedup_quarantine_g10
    """)
    print("  20 tabelas temporarias removidas")

def step7_report(total_u, total_q, match_counts, big_groups_count):
    print("\n" + "=" * 50)
    print("=== MERGE CONCLUIDO ===")
    print("=" * 50)
    print(f"Total vinhos unicos: {total_u:,}")
    print(f"Total quarentena: {total_q:,}")

    det = match_counts.get('deterministic', 0)
    sp_h = match_counts.get('splink_high', 0)
    sp_m = match_counts.get('splink_medium', 0)
    print(f"Por match_type: deterministico {det:,} | splink_high {sp_h:,} | splink_medium {sp_m:,}")

    if TOTAL_BEFORE_DEDUP > 0:
        reducao = (1 - total_u / TOTAL_BEFORE_DEDUP) * 100
        print(f"Taxa de dedup global: de {TOTAL_BEFORE_DEDUP:,} para {total_u:,} ({reducao:.1f}% reducao)")

    print(f"Grupos >50 copias: {big_groups_count} (verificar se sao suspeitos)")
    print("=" * 50)

def main():
    print("=" * 50)
    print("MERGE DEDUP GROUPS — wines_unique + dedup_quarantine")
    print("=" * 50)

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        step1_verify_tables(cur)
        step2_show_counts(cur)
        step3_create_wines_unique(cur)
        step4_create_dedup_quarantine(cur)

        total_u, total_q, match_counts, big_groups_count = step5_audit(cur)

        # Considerar auditoria OK se total > 0 e sem problemas graves
        audit_ok = total_u > 0 and big_groups_count < 50
        step6_drop_temp(cur, audit_ok)

        conn.commit()
        print("\n  COMMIT realizado com sucesso!")

        step7_report(total_u, total_q, match_counts, big_groups_count)

    except Exception as e:
        conn.rollback()
        print(f"\nERRO: {e}")
        print("ROLLBACK realizado. Nenhuma alteracao foi salva.")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
