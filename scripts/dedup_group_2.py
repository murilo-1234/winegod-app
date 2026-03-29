"""
CHAT X2 — Deduplicacao de Vinhos (Grupo 2: BR, AU)
Algoritmo hibrido 3 niveis: deterministico + Splink + quarentena
VERSAO OTIMIZADA: montagem 100% SQL, sem iterrows
"""
import sys, time, gc
import psycopg2, psycopg2.extras
import pandas as pd
import numpy as np
import functools
from collections import Counter

print = functools.partial(print, flush=True)

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
PAISES = ('br', 'au')
BATCH_SIZE = 5000

def main():
    t0 = time.time()
    print("=" * 60)
    print("[X2] Deduplicacao Grupo 2 — BR, AU")
    print("=" * 60)

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # ── Criar tabelas ──
    cur.execute("""
        DROP TABLE IF EXISTS wines_unique_g2 CASCADE;
        CREATE TABLE wines_unique_g2 (
            id SERIAL PRIMARY KEY,
            nome_limpo TEXT NOT NULL,
            nome_normalizado TEXT NOT NULL,
            produtor TEXT, produtor_normalizado TEXT,
            safra INTEGER, tipo TEXT, pais TEXT,
            pais_tabela VARCHAR(5), regiao TEXT, sub_regiao TEXT, uvas TEXT,
            rating_melhor REAL, total_ratings_max INTEGER,
            preco_min_global REAL, preco_max_global REAL,
            moeda_referencia TEXT, url_imagem TEXT, hash_dedup TEXT, ean_gtin TEXT,
            match_type VARCHAR(30) NOT NULL, match_probability REAL,
            total_copias INTEGER, clean_ids INTEGER[]
        );
        DROP TABLE IF EXISTS dedup_quarantine_g2 CASCADE;
        CREATE TABLE dedup_quarantine_g2 (
            id SERIAL PRIMARY KEY,
            clean_id_a INTEGER NOT NULL, clean_id_b INTEGER NOT NULL,
            nome_a TEXT, nome_b TEXT, match_probability REAL, motivo TEXT
        );
    """)
    conn.commit()
    print("[X2] Tabelas criadas")

    # ── Carregar dados ──
    print("[X2] Carregando dados...")
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE pais_tabela IN ('br','au')")
    total_input = cur.fetchone()[0]
    print(f"[X2] Total: {total_input:,} vinhos (BR+AU)")

    cols = ['id','pais_tabela','nome_limpo','nome_normalizado',
            'produtor_extraido','produtor_normalizado','safra','tipo','pais',
            'regiao','sub_regiao','uvas','rating','total_ratings',
            'preco','moeda','url_imagem','hash_dedup','ean_gtin']
    cur.execute(f"""
        SELECT {','.join(cols)} FROM wines_clean
        WHERE pais_tabela IN ('br','au') ORDER BY id
    """)
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)
    print(f"  Carregados: {len(df):,}")

    # ══════════════════════════════════════════════
    # NIVEL 1: Deterministico
    # ══════════════════════════════════════════════
    t1 = time.time()
    print("\n[X2] === NIVEL 1: Deterministico ===")
    processed_ids = set()
    groups = []

    # 1a. hash_dedup
    df_h = df[df['hash_dedup'].notna() & (df['hash_dedup'] != '')]
    if len(df_h) > 0:
        hg = df_h.groupby(['pais_tabela','hash_dedup'])['id'].apply(list)
        multi = hg[hg.apply(len) > 1]
        for ids in multi:
            groups.append(ids)
            processed_ids.update(ids)
    print(f"  1a. hash: {len(groups):,} grupos")

    # 1b. ean_gtin
    n_before = len(groups)
    df_e = df[(df['ean_gtin'].notna()) & (df['ean_gtin'] != '') & (~df['id'].isin(processed_ids))]
    if len(df_e) > 0:
        eg = df_e.groupby(['pais_tabela','ean_gtin'])['id'].apply(list)
        multi = eg[eg.apply(len) > 1]
        for ids in multi:
            groups.append(ids)
            processed_ids.update(ids)
    print(f"  1b. ean: {len(groups)-n_before:,} grupos")

    # 1c. nome + safra
    n_before = len(groups)
    df_n = df[~df['id'].isin(processed_ids)].copy()
    df_n['safra_key'] = df_n['safra'].fillna(-1).astype(int)
    ng = df_n.groupby(['pais_tabela','nome_normalizado','safra_key'])['id'].apply(list)
    multi = ng[ng.apply(len) > 1]
    for ids in multi:
        groups.append(ids)
        processed_ids.update(ids)
    print(f"  1c. nome+safra: {len(groups)-n_before:,} grupos")
    print(f"  TOTAL N1: {len(groups):,} grupos, {len(processed_ids):,} IDs ({time.time()-t1:.0f}s)")

    # ══════════════════════════════════════════════
    # NIVEL 2: Splink
    # ══════════════════════════════════════════════
    t2 = time.time()
    print("\n[X2] === NIVEL 2: Splink ===")
    df_remaining = df[~df['id'].isin(processed_ids)]
    print(f"  Restantes: {len(df_remaining):,}")

    splink_groups = []
    quarantine_pairs = []

    for pais in PAISES:
        df_pais = df_remaining[df_remaining['pais_tabela'] == pais].copy()
        cols_sp = ['id','nome_normalizado','produtor_normalizado','safra','tipo','pais_tabela','regiao','uvas']
        df_sp = df_pais[cols_sp].copy().reset_index(drop=True)
        for c in ['nome_normalizado','produtor_normalizado','tipo','pais_tabela','regiao','uvas']:
            df_sp[c] = df_sp[c].where(df_sp[c].notna(), None)
        df_sp['safra'] = df_sp['safra'].astype('Int64')
        print(f"\n  Splink {pais.upper()}: {len(df_sp):,}")
        if len(df_sp) < 100:
            continue

        try:
            import splink.comparison_library as cl
            import splink.blocking_rule_library as brl
            from splink import DuckDBAPI, Linker, SettingsCreator, block_on
            import duckdb

            settings = SettingsCreator(
                link_type="dedupe_only", unique_id_column_name="id",
                comparisons=[
                    cl.JaroWinklerAtThresholds("nome_normalizado", [0.92, 0.80]),
                    cl.JaroWinklerAtThresholds("produtor_normalizado", [0.92, 0.80]),
                    cl.ExactMatch("safra"), cl.ExactMatch("tipo"), cl.ExactMatch("pais_tabela"),
                    cl.JaroWinklerAtThresholds("regiao", [0.88]),
                    cl.JaroWinklerAtThresholds("uvas", [0.88]),
                ],
                blocking_rules_to_generate_predictions=[
                    block_on("nome_normalizado"),
                    block_on("produtor_normalizado", "pais_tabela"),
                    brl.CustomRule("SUBSTR(l.nome_normalizado,1,15) = SUBSTR(r.nome_normalizado,1,15) AND l.pais_tabela = r.pais_tabela"),
                ],
                retain_matching_columns=True,
            )

            duck = duckdb.connect()
            duck.execute("SET memory_limit='2GB'")
            linker = Linker(df_sp, settings, DuckDBAPI(connection=duck))
            linker.training.estimate_probability_two_random_records_match(block_on("nome_normalizado"), recall=0.7)
            linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)
            linker.training.estimate_parameters_using_expectation_maximisation(block_on("nome_normalizado"), fix_u_probabilities=True)
            linker.training.estimate_parameters_using_expectation_maximisation(block_on("produtor_normalizado"), fix_u_probabilities=True)

            results = linker.inference.predict(threshold_match_probability=0.50)
            df_pred = results.as_pandas_dataframe()

            if len(df_pred) > 0:
                df_rev = df_pred[(df_pred["match_probability"] >= 0.50) & (df_pred["match_probability"] < 0.80)]
                for _, r in df_rev.iterrows():
                    quarantine_pairs.append((
                        int(r.get('id_l', r.get('unique_id_l', 0))),
                        int(r.get('id_r', r.get('unique_id_r', 0))),
                        float(r['match_probability']), 'splink_uncertain'
                    ))

                clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(results, threshold_match_probability=0.80)
                df_cl = clusters.as_pandas_dataframe()
                if len(df_cl) > 0:
                    ccol = 'cluster_id' if 'cluster_id' in df_cl.columns else df_cl.columns[-1]
                    cg = df_cl.groupby(ccol)['id'].apply(list)
                    for ids in cg[cg.apply(len) > 1]:
                        splink_groups.append([int(x) for x in ids])

            print(f"  {pais.upper()}: {len(splink_groups)} clusters, {len(quarantine_pairs)} quarentena")
            del linker, results, duck
            gc.collect()
        except Exception as e:
            print(f"  ERRO Splink {pais.upper()}: {e}")
            import traceback; traceback.print_exc()

    splink_ids = set()
    for g in splink_groups:
        splink_ids.update(g)
    print(f"\n  TOTAL N2: {len(splink_groups):,} grupos ({time.time()-t2:.0f}s)")

    # ══════════════════════════════════════════════
    # MONTAGEM — 100% SQL, sem loops Python
    # ══════════════════════════════════════════════
    t3 = time.time()
    print("\n[X2] === Montagem (SQL direto) ===")

    # Tabela temporaria: id -> group_id, match_type
    cur.execute("DROP TABLE IF EXISTS _dedup_map")
    cur.execute("CREATE TEMP TABLE _dedup_map (wine_id INTEGER PRIMARY KEY, group_id INTEGER, match_type VARCHAR(30), match_prob REAL)")
    conn.commit()

    gid = 0
    map_rows = []
    for g in groups:
        for vid in g:
            map_rows.append((vid, gid, 'deterministic', 1.0))
        gid += 1
    for g in splink_groups:
        for vid in g:
            map_rows.append((vid, gid, 'splink_high', 0.85))
        gid += 1

    # Singletons
    all_grouped = processed_ids | splink_ids
    singleton_ids = set(df['id']) - all_grouped
    for vid in singleton_ids:
        map_rows.append((vid, gid, 'singleton', None))
        gid += 1

    print(f"  Mapa: {len(map_rows):,} IDs -> {gid:,} grupos")

    # Insert map em batches
    for i in range(0, len(map_rows), 10000):
        batch = map_rows[i:i+10000]
        psycopg2.extras.execute_values(cur, "INSERT INTO _dedup_map (wine_id, group_id, match_type, match_prob) VALUES %s", batch, page_size=10000)
        conn.commit()
    print(f"  Mapa inserido ({time.time()-t3:.0f}s)")

    # Agora montar wines_unique_g2 com um unico INSERT...SELECT agrupado
    print("  INSERT...SELECT agrupado...")
    cur.execute("""
        INSERT INTO wines_unique_g2
            (nome_limpo, nome_normalizado, produtor, produtor_normalizado,
             safra, tipo, pais, pais_tabela, regiao, sub_regiao, uvas,
             rating_melhor, total_ratings_max, preco_min_global, preco_max_global,
             moeda_referencia, url_imagem, hash_dedup, ean_gtin,
             match_type, match_probability, total_copias, clean_ids)
        SELECT
            -- nome_limpo: o mais longo do grupo
            (ARRAY_AGG(w.nome_limpo ORDER BY LENGTH(w.nome_limpo) DESC))[1],
            (ARRAY_AGG(w.nome_normalizado))[1],
            -- primeiro nao-null
            (ARRAY_AGG(w.produtor_extraido ORDER BY w.produtor_extraido NULLS LAST))[1],
            (ARRAY_AGG(w.produtor_normalizado ORDER BY w.produtor_normalizado NULLS LAST))[1],
            (ARRAY_AGG(w.safra ORDER BY w.safra NULLS LAST))[1],
            -- tipo: moda (mais comum)
            MODE() WITHIN GROUP (ORDER BY w.tipo),
            (ARRAY_AGG(w.pais ORDER BY w.pais NULLS LAST))[1],
            (ARRAY_AGG(w.pais_tabela))[1],
            (ARRAY_AGG(w.regiao ORDER BY w.regiao NULLS LAST))[1],
            (ARRAY_AGG(w.sub_regiao ORDER BY w.sub_regiao NULLS LAST))[1],
            (ARRAY_AGG(w.uvas ORDER BY w.uvas NULLS LAST))[1],
            MAX(w.rating),
            MAX(w.total_ratings)::int,
            MIN(CASE WHEN w.preco > 0 THEN w.preco END),
            MAX(CASE WHEN w.preco > 0 THEN w.preco END),
            MODE() WITHIN GROUP (ORDER BY w.moeda),
            (ARRAY_AGG(w.url_imagem ORDER BY w.url_imagem NULLS LAST))[1],
            (ARRAY_AGG(w.hash_dedup ORDER BY w.hash_dedup NULLS LAST))[1],
            (ARRAY_AGG(w.ean_gtin ORDER BY w.ean_gtin NULLS LAST))[1],
            m.match_type,
            m.match_prob,
            COUNT(*)::int,
            ARRAY_AGG(w.id ORDER BY w.id)
        FROM wines_clean w
        JOIN _dedup_map m ON m.wine_id = w.id
        GROUP BY m.group_id, m.match_type, m.match_prob
    """)
    conn.commit()
    n_inserted = cur.rowcount
    print(f"  Inseridos: {n_inserted:,} vinhos unicos ({time.time()-t3:.0f}s)")

    # ── Quarentena ──
    print("\n[X2] === Quarentena ===")
    if quarantine_pairs:
        nome_lookup = dict(zip(df['id'], df['nome_limpo']))
        q_values = []
        for (id_a, id_b, prob, motivo) in quarantine_pairs:
            q_values.append((id_a, id_b, nome_lookup.get(id_a,''), nome_lookup.get(id_b,''), prob, motivo))
        for i in range(0, len(q_values), BATCH_SIZE):
            psycopg2.extras.execute_values(cur,
                "INSERT INTO dedup_quarantine_g2 (clean_id_a,clean_id_b,nome_a,nome_b,match_probability,motivo) VALUES %s",
                q_values[i:i+BATCH_SIZE], page_size=BATCH_SIZE)
            conn.commit()
        print(f"  Quarentena: {len(q_values):,} pares")
    else:
        print("  Quarentena: 0 pares")

    # ── Relatorio ──
    cur.execute("SELECT COUNT(*) FROM wines_unique_g2")
    total_unique = cur.fetchone()[0]
    cur.execute("SELECT match_type, COUNT(*) FROM wines_unique_g2 GROUP BY match_type ORDER BY count DESC")
    match_types = cur.fetchall()
    cur.execute("SELECT total_copias, COUNT(*) FROM wines_unique_g2 GROUP BY total_copias ORDER BY total_copias DESC LIMIT 10")
    copias_dist = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM dedup_quarantine_g2")
    total_q = cur.fetchone()[0]

    elapsed = time.time() - t0
    taxa = (1 - total_unique / total_input) * 100 if total_input > 0 else 0

    print("\n" + "=" * 60)
    print(f"=== GRUPO 2 CONCLUIDO ===")
    print(f"Paises: BR, AU")
    print(f"Input: {total_input:,} vinhos de wines_clean")
    print(f"Nivel 1 (deterministico): {len(groups):,} grupos")
    print(f"Nivel 2 (Splink): {len(splink_groups):,} grupos adicionais")
    print(f"Nivel 3 (quarentena): {len(quarantine_pairs):,} pares incertos")
    print(f"Output: {total_unique:,} vinhos unicos em wines_unique_g2")
    print(f"Taxa de dedup: {taxa:.1f}% (de {total_input:,} para {total_unique:,})")
    print(f"Tempo total: {elapsed:.0f}s")
    print("=" * 60)

    print("\nDistribuicao por match_type:")
    for mt, cnt in match_types:
        print(f"  {mt}: {cnt:,}")
    print("\nDistribuicao por total_copias (top 10):")
    for tc, cnt in copias_dist:
        print(f"  {tc} copias: {cnt:,} vinhos")

    print("\n--- 10 exemplos NIVEL 1 ---")
    cur.execute("SELECT nome_limpo,produtor,safra,tipo,pais_tabela,total_copias,clean_ids[1:5] FROM wines_unique_g2 WHERE match_type='deterministic' AND total_copias>1 ORDER BY total_copias DESC LIMIT 10")
    for r in cur.fetchall():
        print(f"  [{r[4].upper()}] {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[5]} copias")

    print("\n--- 10 exemplos NIVEL 2 ---")
    cur.execute("SELECT nome_limpo,produtor,safra,tipo,pais_tabela,total_copias,clean_ids[1:5] FROM wines_unique_g2 WHERE match_type='splink_high' AND total_copias>1 ORDER BY total_copias DESC LIMIT 10")
    rows = cur.fetchall()
    for r in rows:
        print(f"  [{r[4].upper()}] {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[5]} copias")
    if not rows:
        print("  (nenhum)")

    cur.execute("DROP TABLE IF EXISTS _dedup_map")
    conn.commit()
    conn.close()
    print("\n[X2] Finalizado!")

if __name__ == "__main__":
    main()
