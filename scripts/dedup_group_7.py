#!/usr/bin/env python3
"""
DEDUP GROUP 7 — Deduplicacao de vinhos: SG, CA, PH, AT, IE
3 niveis: deterministico + Splink probabilistico + quarentena

Each country is processed in a separate subprocess to avoid memory exhaustion
from Splink/DuckDB accumulation.
"""

import gc
import json
import os
import subprocess
import sys
import time
import traceback

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# ── Config ──
DB_URL = os.getenv("WINEGOD_LOCAL_URL", "postgresql://postgres:postgres123@localhost:5432/winegod_db")
GROUP = 7
PAISES = ['sg', 'ca', 'ph', 'at', 'ie']
BATCH_SIZE = 5000

MATCH_THRESHOLD = 0.80
REVIEW_THRESHOLD = 0.50


def log(msg):
    print(f"[X{GROUP}] {msg}", flush=True)


def get_conn():
    return psycopg2.connect(DB_URL)


# ── Criar tabelas de destino ──

def create_tables(conn):
    with conn.cursor() as cur:
        cur.execute("""
            DROP TABLE IF EXISTS wines_unique_g7 CASCADE;
            DROP TABLE IF EXISTS dedup_quarantine_g7 CASCADE;

            CREATE TABLE wines_unique_g7 (
                id SERIAL PRIMARY KEY,
                nome_limpo TEXT NOT NULL,
                nome_normalizado TEXT NOT NULL,
                produtor TEXT,
                produtor_normalizado TEXT,
                safra INTEGER,
                tipo TEXT,
                pais TEXT,
                pais_tabela VARCHAR(5),
                regiao TEXT,
                sub_regiao TEXT,
                uvas TEXT,
                rating_melhor REAL,
                total_ratings_max INTEGER,
                preco_min_global REAL,
                preco_max_global REAL,
                moeda_referencia VARCHAR(10),
                url_imagem TEXT,
                hash_dedup VARCHAR(64),
                ean_gtin VARCHAR(50),
                match_type VARCHAR(20) NOT NULL,
                match_probability REAL,
                total_copias INTEGER,
                clean_ids INTEGER[]
            );

            CREATE TABLE dedup_quarantine_g7 (
                id SERIAL PRIMARY KEY,
                clean_id_a INTEGER NOT NULL,
                clean_id_b INTEGER NOT NULL,
                nome_a TEXT,
                nome_b TEXT,
                match_probability REAL,
                motivo TEXT
            );
        """)
    conn.commit()
    log("Tabelas criadas")


def load_wines(conn, pais):
    query = """
        SELECT id, pais_tabela, id_original,
               nome_limpo, nome_normalizado,
               produtor_extraido, produtor_normalizado,
               safra, tipo, pais, regiao, sub_regiao, uvas,
               rating, total_ratings,
               preco, moeda, preco_min, preco_max,
               url_imagem, hash_dedup, ean_gtin,
               fontes, total_fontes
        FROM wines_clean
        WHERE pais_tabela = %s
    """
    return pd.read_sql(query, conn, params=(pais,))


# ── NIVEL 1 — Deterministico ──

def nivel1_assign_groups(df):
    df = df.copy()
    df['dedup_group'] = np.arange(len(df))

    def merge_by_key(df, key_cols, mask=None):
        subset = df[mask] if mask is not None else df
        if len(subset) == 0:
            return df
        mg = subset.groupby(key_cols)['dedup_group'].transform('min')
        if mask is not None:
            df.loc[mask, 'dedup_group'] = mg.values
        else:
            df['dedup_group'] = mg.values
        return df

    mask_hash = df['hash_dedup'].notna() & (df['hash_dedup'] != '')
    df = merge_by_key(df, ['pais_tabela', 'hash_dedup'], mask_hash)

    mask_ean = df['ean_gtin'].notna() & (df['ean_gtin'] != '')
    df = merge_by_key(df, ['pais_tabela', 'ean_gtin'], mask_ean)

    df['safra_key'] = df['safra'].fillna(-1).astype(int)
    df = merge_by_key(df, ['pais_tabela', 'nome_normalizado', 'safra_key'])
    df.drop(columns=['safra_key'], inplace=True)

    for _ in range(5):
        old = df['dedup_group'].copy()
        mm = df.groupby('dedup_group')['dedup_group'].min()
        df['dedup_group'] = df['dedup_group'].map(mm)
        if (df['dedup_group'] == old).all():
            break

    gs = df.groupby('dedup_group').size()
    return df, int((gs > 1).sum()), int((gs == 1).sum())


# ── Merge groups ──

def merge_to_unique(df, group_col, match_type_val, match_prob_val):
    if len(df) == 0:
        return pd.DataFrame(), []

    df = df.copy()
    df['preco_valid'] = df['preco'].where(df['preco'] > 0)
    df['nome_len'] = df['nome_limpo'].fillna('').str.len()
    g = group_col

    agg = df.groupby(g, sort=False).agg(
        nome_normalizado=('nome_normalizado', 'first'),
        safra=('safra', 'first'),
        pais=('pais', 'first'),
        pais_tabela=('pais_tabela', 'first'),
        regiao=('regiao', 'first'),
        sub_regiao=('sub_regiao', 'first'),
        uvas=('uvas', 'first'),
        rating_melhor=('rating', 'max'),
        total_ratings_max=('total_ratings', 'max'),
        preco_min_global=('preco_valid', 'min'),
        preco_max_global=('preco_valid', 'max'),
        total_copias=('id', 'count'),
        produtor=('produtor_extraido', 'first'),
        produtor_normalizado=('produtor_normalizado', 'first'),
        url_imagem=('url_imagem', 'first'),
        hash_dedup=('hash_dedup', 'first'),
        ean_gtin=('ean_gtin', 'first'),
    ).reset_index()

    cids = df.groupby(g, sort=False)['id'].apply(lambda x: list(x.astype(int))).reset_index()
    cids.columns = [g, 'clean_ids']
    agg = agg.merge(cids, on=g)

    idx_longest = df.groupby(g, sort=False)['nome_len'].idxmax()
    nb = df.loc[idx_longest, [g, 'nome_limpo']].drop_duplicates(subset=[g])
    agg = agg.merge(nb, on=g, how='left')

    tn = df.dropna(subset=['tipo'])
    if len(tn) > 0:
        tm = tn.groupby(g, sort=False)['tipo'].agg(lambda x: x.value_counts().index[0]).reset_index()
        tm.columns = [g, 'tipo']
        agg = agg.merge(tm, on=g, how='left')
    else:
        agg['tipo'] = None

    mn = df.dropna(subset=['moeda'])
    if len(mn) > 0:
        mm = mn.groupby(g, sort=False)['moeda'].agg(lambda x: x.value_counts().index[0]).reset_index()
        mm.columns = [g, 'moeda_referencia']
        agg = agg.merge(mm, on=g, how='left')
    else:
        agg['moeda_referencia'] = None

    agg['match_type'] = match_type_val
    agg['match_probability'] = match_prob_val
    agg.loc[agg['total_copias'] == 1, 'match_type'] = 'unique'
    agg.loc[agg['total_copias'] == 1, 'match_probability'] = None

    # Validation
    quarantine = []
    multi = agg[agg['total_copias'] > 1]
    bad_groups = set()

    if len(multi) > 0:
        tn2 = df.dropna(subset=['tipo'])
        if len(tn2) > 0:
            tc = tn2.groupby(g)['tipo'].nunique()
            for gid in tc[tc > 1].index:
                tipos = df[df[g] == gid]['tipo'].dropna().unique()
                core = [t for t in tipos if t in ('tinto', 'branco', 'rose', 'espumante')]
                if len(core) > 1:
                    bad_groups.add(gid)

        ps = df[df['preco'] > 0].groupby(g)['preco'].agg(['min', 'max'])
        ps['ratio'] = ps['max'] / ps['min'].replace(0, np.nan)
        bad_groups.update(ps[ps['ratio'] > 10].index)
        bad_groups.update(agg[agg['total_copias'] > 100][g].values)
        bad_groups = bad_groups & set(multi[g].values)

    if bad_groups:
        for gid in bad_groups:
            gdf = df[df[g] == gid]
            ids_list = list(gdf['id'].values)
            names_list = list(gdf['nome_limpo'].values)
            if len(ids_list) >= 2:
                quarantine.append({
                    'clean_id_a': int(ids_list[0]),
                    'clean_id_b': int(ids_list[1]),
                    'nome_a': names_list[0], 'nome_b': names_list[1],
                    'match_probability': 1.0, 'motivo': 'validation_failed',
                })

        # Split bad: each wine individually
        bad_df = df[df[g].isin(bad_groups)].copy()
        bad_df[g] = np.arange(len(bad_df)) + 999_000_000
        bad_recs, _ = merge_to_unique(bad_df, g, 'quarantine_split', None)
        agg = agg[~agg[g].isin(bad_groups)]
        if len(bad_recs) > 0:
            agg = pd.concat([agg, bad_recs], ignore_index=True)

    return agg, quarantine


# ── NIVEL 2 — Splink ──

def nivel2_dedup(df_remaining, pais_tabela):
    if len(df_remaining) < 100:
        log(f"  Splink skip ({pais_tabela}): {len(df_remaining)} vinhos")
        return pd.DataFrame(columns=["id", "cluster_id"]), pd.DataFrame()

    try:
        import splink.comparison_library as cl
        import splink.blocking_rule_library as brl
        from splink import DuckDBAPI, Linker, SettingsCreator, block_on
    except ImportError:
        log("AVISO: Splink nao instalado")
        return pd.DataFrame(columns=["id", "cluster_id"]), pd.DataFrame()

    log(f"  Splink iniciando: {len(df_remaining)} vinhos")

    df_sp = df_remaining[['id', 'nome_normalizado', 'produtor_normalizado',
                          'safra', 'tipo', 'pais_tabela', 'regiao', 'uvas']].copy()
    df_sp = df_sp.where(df_sp.notna(), None)
    df_sp['id'] = df_sp['id'].astype(int)

    tbn = block_on("nome_normalizado")
    tbp = block_on("produtor_normalizado")

    settings = SettingsCreator(
        link_type="dedupe_only",
        unique_id_column_name="id",
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
            brl.CustomRule(
                "SUBSTR(l.nome_normalizado,1,10) = SUBSTR(r.nome_normalizado,1,10) "
                "AND l.pais_tabela = r.pais_tabela"
            ),
        ],
        retain_matching_columns=True,
    )

    try:
        db_api = DuckDBAPI()
        linker = Linker(df_sp, settings, db_api)
        linker.training.estimate_probability_two_random_records_match(tbn, recall=0.7)
        linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)
        linker.training.estimate_parameters_using_expectation_maximisation(tbn, fix_u_probabilities=True)
        linker.training.estimate_parameters_using_expectation_maximisation(tbp, fix_u_probabilities=True)

        results = linker.inference.predict(threshold_match_probability=REVIEW_THRESHOLD)
        df_pred = results.as_pandas_dataframe()

        if len(df_pred) == 0:
            log(f"  Splink: 0 pares")
            return pd.DataFrame(columns=["id", "cluster_id"]), pd.DataFrame()

        log(f"  Splink: {len(df_pred)} pares")

        df_review = df_pred[
            (df_pred["match_probability"] >= REVIEW_THRESHOLD) &
            (df_pred["match_probability"] < MATCH_THRESHOLD)
        ].copy()
        if 'id_l' in df_review.columns:
            df_review = df_review[["id_l", "id_r", "match_probability"]].copy()
        else:
            df_review = pd.DataFrame()

        clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
            results, threshold_match_probability=MATCH_THRESHOLD,
        )
        df_clusters = clusters.as_pandas_dataframe()
        log(f"  Splink: {df_clusters['cluster_id'].nunique()} clusters, {len(df_review)} incertos")

        # Cleanup Splink resources
        del linker, db_api, results, df_pred
        gc.collect()

        return df_clusters, df_review

    except Exception as e:
        log(f"  ERRO Splink: {e}")
        traceback.print_exc()
        return pd.DataFrame(columns=["id", "cluster_id"]), pd.DataFrame()


# ── INSERT ──

INSERT_COLS = ['nome_limpo', 'nome_normalizado', 'produtor', 'produtor_normalizado',
               'safra', 'tipo', 'pais', 'pais_tabela', 'regiao', 'sub_regiao', 'uvas',
               'rating_melhor', 'total_ratings_max', 'preco_min_global', 'preco_max_global',
               'moeda_referencia', 'url_imagem', 'hash_dedup', 'ean_gtin',
               'match_type', 'match_probability', 'total_copias', 'clean_ids']


def clean_val(v):
    if v is None:
        return None
    if isinstance(v, float) and (pd.isna(v) or np.isnan(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


def insert_unique_df(conn, agg_df):
    if agg_df is None or len(agg_df) == 0:
        return
    sql = f"INSERT INTO wines_unique_g7 ({', '.join(INSERT_COLS)}) VALUES %s"
    template = "(" + ", ".join(["%s"] * len(INSERT_COLS)) + ")"
    with conn.cursor() as cur:
        for i in range(0, len(agg_df), BATCH_SIZE):
            batch = agg_df.iloc[i:i+BATCH_SIZE]
            values = [tuple(clean_val(row.get(c)) for c in INSERT_COLS) for _, row in batch.iterrows()]
            execute_values(cur, sql, values, template=template)
    conn.commit()


def insert_quarantine(conn, records):
    if not records:
        return
    sql = "INSERT INTO dedup_quarantine_g7 (clean_id_a, clean_id_b, nome_a, nome_b, match_probability, motivo) VALUES %s"
    with conn.cursor() as cur:
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i:i+BATCH_SIZE]
            values = [(r['clean_id_a'], r['clean_id_b'], r['nome_a'], r['nome_b'],
                        r['match_probability'], r['motivo']) for r in batch]
            execute_values(cur, sql, values)
    conn.commit()


# ── Process single country (called as subprocess or directly) ──

def process_country(pais):
    """Process one country completely. Returns stats dict via stdout JSON."""
    tp = time.time()
    log(f"Carregando {pais.upper()}...")
    conn = get_conn()
    df = load_wines(conn, pais)

    if len(df) == 0:
        log(f"  {pais.upper()}: 0 vinhos")
        result = {'input': 0, 'output': 0, 'nivel1_groups': 0, 'nivel2_groups': 0,
                  'quarantine': 0, 'examples_n1': [], 'examples_n2': []}
        print("RESULT:" + json.dumps(result), flush=True)
        conn.close()
        return

    n_input = len(df)
    log(f"  {pais.upper()}: {n_input:,} vinhos")

    # NIVEL 1
    t1 = time.time()
    df_grouped, n_multi, n_single = nivel1_assign_groups(df)
    log(f"  N1: {n_multi:,} dup, {n_single:,} unicos ({time.time()-t1:.1f}s)")

    # Merge
    t1 = time.time()
    agg_df, quar_recs = merge_to_unique(df_grouped, 'dedup_group', 'deterministic', 1.0)
    log(f"  Merge: {len(agg_df):,} ({time.time()-t1:.1f}s)")

    examples_n1 = []
    det = agg_df[(agg_df['total_copias'] > 1) & (agg_df['match_type'] == 'deterministic')]
    for _, row in det.head(5).iterrows():
        examples_n1.append({'pais': pais.upper(), 'nome': str(row['nome_limpo']), 'copias': int(row['total_copias'])})

    # NIVEL 2
    singletons = agg_df[agg_df['match_type'] == 'unique']
    singleton_ids = set()
    for _, row in singletons.iterrows():
        cids = row['clean_ids']
        if isinstance(cids, list) and len(cids) == 1:
            singleton_ids.add(cids[0])

    df_remaining = df[df['id'].isin(singleton_ids)].copy()
    log(f"  Splink restantes: {len(df_remaining):,}")

    n2_groups = 0
    examples_n2 = []

    if len(df_remaining) >= 100:
        df_clusters, df_review = nivel2_dedup(df_remaining, pais)

        if len(df_clusters) > 0 and 'cluster_id' in df_clusters.columns:
            csizes = df_clusters.groupby('cluster_id').size()
            multi_cl = csizes[csizes > 1].index

            if len(multi_cl) > 0:
                df_multi = df_clusters[df_clusters['cluster_id'].isin(multi_cl)]
                multi_ids = set(df_multi['id'].astype(int).values)

                # Remove singletons that Splink grouped
                agg_df = agg_df[~(
                    (agg_df['match_type'] == 'unique') &
                    agg_df['clean_ids'].apply(lambda x: isinstance(x, list) and len(x) == 1 and x[0] in multi_ids)
                )]

                df_for_merge = df_remaining[df_remaining['id'].isin(multi_ids)].copy()
                id_to_cl = dict(zip(df_multi['id'].astype(int), df_multi['cluster_id']))
                df_for_merge['splink_cluster'] = df_for_merge['id'].map(id_to_cl)

                splink_agg, splink_quar = merge_to_unique(df_for_merge, 'splink_cluster', 'splink_high', MATCH_THRESHOLD)
                n2_groups = len(splink_agg[splink_agg['total_copias'] > 1]) if len(splink_agg) > 0 else 0

                for _, row in splink_agg[splink_agg['total_copias'] > 1].head(5).iterrows():
                    examples_n2.append({'pais': pais.upper(), 'nome': str(row['nome_limpo']), 'copias': int(row['total_copias'])})

                agg_df = pd.concat([agg_df, splink_agg], ignore_index=True)
                quar_recs.extend(splink_quar)

        # Quarantine nivel 3
        if len(df_review) > 0 and 'id_l' in df_review.columns:
            name_lookup = dict(zip(df_remaining['id'].astype(int), df_remaining['nome_limpo']))
            for _, pair in df_review.iterrows():
                id_a, id_b = int(pair['id_l']), int(pair['id_r'])
                quar_recs.append({
                    'clean_id_a': id_a, 'clean_id_b': id_b,
                    'nome_a': name_lookup.get(id_a), 'nome_b': name_lookup.get(id_b),
                    'match_probability': float(pair['match_probability']),
                    'motivo': 'splink_uncertain',
                })

    # INSERT
    n_unique = len(agg_df)
    n_quar = len(quar_recs)
    log(f"  Inserindo {n_unique:,} unicos + {n_quar:,} quarentena...")
    insert_unique_df(conn, agg_df)
    insert_quarantine(conn, quar_recs)

    elapsed = time.time() - tp
    log(f"  {pais.upper()} CONCLUIDO em {elapsed:.1f}s ({n_input:,} -> {n_unique:,})")

    conn.close()

    result = {
        'input': n_input,
        'output': n_unique,
        'nivel1_groups': n_multi,
        'nivel2_groups': n2_groups,
        'quarantine': n_quar,
        'examples_n1': examples_n1,
        'examples_n2': examples_n2,
    }
    print("RESULT:" + json.dumps(result), flush=True)


# ── MAIN ──

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--country':
        # Subprocess mode: process single country
        pais = sys.argv[2]
        process_country(pais)
        return

    # Main orchestrator mode
    t0 = time.time()
    log(f"Iniciando dedup grupo {GROUP}: {', '.join(p.upper() for p in PAISES)}")

    conn = get_conn()
    create_tables(conn)
    conn.close()

    stats = {
        'input_total': 0, 'nivel1_groups': 0, 'nivel2_groups': 0,
        'quarantine_pairs': 0, 'output_unique': 0,
    }
    all_examples_n1 = []
    all_examples_n2 = []

    for pais in PAISES:
        log(f"=== Processando {pais.upper()} (subprocess) ===")
        try:
            result = subprocess.run(
                [sys.executable, __file__, '--country', pais],
                capture_output=False,
                timeout=600,
            )
            if result.returncode != 0:
                log(f"ERRO: {pais.upper()} retornou codigo {result.returncode}")
                continue
        except subprocess.TimeoutExpired:
            log(f"TIMEOUT: {pais.upper()} excedeu 10 minutos")
            continue
        except Exception as e:
            log(f"ERRO subprocess {pais.upper()}: {e}")
            continue

    # Final verification
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM wines_unique_g7")
        count_unique = cur.fetchone()[0]
        cur.execute("SELECT match_type, COUNT(*) FROM wines_unique_g7 GROUP BY match_type ORDER BY COUNT(*) DESC")
        match_types = cur.fetchall()
        cur.execute("SELECT total_copias, COUNT(*) FROM wines_unique_g7 GROUP BY total_copias ORDER BY total_copias DESC LIMIT 10")
        copias_dist = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM dedup_quarantine_g7")
        count_quarantine = cur.fetchone()[0]
        cur.execute("SELECT pais_tabela, COUNT(*) FROM wines_unique_g7 GROUP BY pais_tabela ORDER BY COUNT(*) DESC")
        pais_counts = cur.fetchall()

        # Count input
        cur.execute("SELECT COUNT(*) FROM wines_clean WHERE pais_tabela IN ('sg','ca','ph','at','ie')")
        input_total = cur.fetchone()[0]

        # Sample examples
        cur.execute("""
            SELECT nome_limpo, pais_tabela, total_copias, match_type
            FROM wines_unique_g7
            WHERE total_copias > 1 AND match_type = 'deterministic'
            ORDER BY total_copias DESC LIMIT 10
        """)
        ex_n1 = cur.fetchall()

        cur.execute("""
            SELECT nome_limpo, pais_tabela, total_copias, match_type
            FROM wines_unique_g7
            WHERE total_copias > 1 AND match_type = 'splink_high'
            ORDER BY total_copias DESC LIMIT 10
        """)
        ex_n2 = cur.fetchall()

    conn.close()

    elapsed_total = time.time() - t0
    taxa = (1 - count_unique / input_total) * 100 if input_total > 0 else 0

    print("\n" + "=" * 60)
    print(f"=== GRUPO {GROUP} CONCLUIDO ===")
    print(f"Paises: {', '.join(p.upper() for p in PAISES)}")
    print(f"Input: {input_total:,} vinhos de wines_clean")
    n1_det = sum(cnt for mt, cnt in match_types if mt == 'deterministic')
    n2_sp = sum(cnt for mt, cnt in match_types if mt == 'splink_high')
    print(f"Nivel 1 (deterministico): {n1_det:,} grupos")
    print(f"Nivel 2 (Splink): {n2_sp:,} grupos adicionais")
    print(f"Nivel 3 (quarentena): {count_quarantine:,} pares incertos")
    print(f"Output: {count_unique:,} vinhos unicos em wines_unique_g7")
    print(f"Taxa de dedup: {taxa:.1f}% (de {input_total:,} para {count_unique:,})")
    print(f"Tempo total: {elapsed_total:.1f}s")
    print("=" * 60)

    print(f"\nVerificacao DB:")
    print(f"  wines_unique_g7: {count_unique:,} registros")
    print(f"  Por pais:")
    for pt, cnt in pais_counts:
        print(f"    {pt.upper()}: {cnt:,}")
    print(f"  Match types:")
    for mt, cnt in match_types:
        print(f"    {mt}: {cnt:,}")
    print(f"  Top copias:")
    for tc, cnt in copias_dist:
        print(f"    {tc} copias: {cnt:,} vinhos")
    print(f"  dedup_quarantine_g7: {count_quarantine:,} pares")

    if ex_n1:
        print(f"\n--- Exemplos Nivel 1 (deterministico) ---")
        for i, (nome, pt, tc, mt) in enumerate(ex_n1, 1):
            print(f"  {i}. [{pt.upper()}] {nome} ({tc} copias)")

    if ex_n2:
        print(f"\n--- Exemplos Nivel 2 (Splink) ---")
        for i, (nome, pt, tc, mt) in enumerate(ex_n2, 1):
            print(f"  {i}. [{pt.upper()}] {nome} ({tc} copias)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERRO FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
