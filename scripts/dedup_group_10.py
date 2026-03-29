#!/usr/bin/env python3
"""
DEDUP GROUP 10 — Deduplicacao de vinhos para:
CO, FI, HU, JP, LU, BG, RU, IL, GE, CZ, CN, AE, KR, NO, HR, TW, TR, TH

3 niveis: deterministico + Splink probabilistico + quarentena
"""

import sys
import time
import warnings
from collections import Counter

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

warnings.filterwarnings("ignore")

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
GROUP_COUNTRIES = ('co','fi','hu','jp','lu','bg','ru','il','ge','cz','cn','ae','kr','no','hr','tw','tr','th')
GROUP_LABEL = "X10"
TABLE_UNIQUE = "wines_unique_g10"
TABLE_QUARANTINE = "dedup_quarantine_g10"


# ── Helpers ──────────────────────────────────────────────────────────────────

def first_non_null(series):
    vals = series.dropna()
    return vals.iloc[0] if len(vals) > 0 else None

def most_common_val(series):
    vals = series.dropna().tolist()
    if not vals:
        return None
    return Counter(vals).most_common(1)[0][0]

def safe_int(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return int(v)

def safe_float(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return float(v)


# ── Database ─────────────────────────────────────────────────────────────────

def create_tables(conn):
    cur = conn.cursor()
    cur.execute(f"""
        DROP TABLE IF EXISTS {TABLE_UNIQUE} CASCADE;
        DROP TABLE IF EXISTS {TABLE_QUARANTINE} CASCADE;

        CREATE TABLE {TABLE_UNIQUE} (
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

        CREATE TABLE {TABLE_QUARANTINE} (
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
    cur.close()


def load_wines(conn):
    placeholders = ','.join([f"'{c}'" for c in GROUP_COUNTRIES])
    query = f"""
        SELECT id, pais_tabela, id_original,
               nome_limpo, nome_normalizado,
               produtor_extraido, produtor_normalizado,
               safra, tipo, pais, regiao, sub_regiao, uvas,
               rating, total_ratings,
               preco, moeda, preco_min, preco_max,
               url_imagem, hash_dedup, ean_gtin,
               fontes, total_fontes
        FROM wines_clean
        WHERE pais_tabela IN ({placeholders})
    """
    df = pd.read_sql(query, conn)
    print(f"[{GROUP_LABEL}] Loaded {len(df):,} wines from wines_clean")
    return df


# ── NIVEL 1: Deterministico (vectorized) ─────────────────────────────────────

def nivel1_dedup(df):
    """
    Deterministic dedup. Returns:
    - multi_groups: list of (group_key, DataFrame) for groups with >1 member
    - processed_ids: set of all IDs consumed by multi-member groups
    Stats are printed inline.
    """
    processed_ids = set()
    multi_groups = []  # only multi-member groups

    # ── 1a. hash_dedup ──
    df_hash = df[df['hash_dedup'].notna() & (df['hash_dedup'] != '')].copy()
    n1a = 0
    if len(df_hash) > 0:
        df_hash['_key'] = df_hash['pais_tabela'] + '||' + df_hash['hash_dedup']
        counts = df_hash.groupby('_key').size()
        multi_keys_set = set(counts[counts > 1].index)
        df_multi = df_hash[df_hash['_key'].isin(multi_keys_set)]

        for key, grp in df_multi.groupby('_key'):
            ids = set(grp['id'].tolist()) - processed_ids
            if len(ids) < 2:
                continue
            grp = grp[grp['id'].isin(ids)]
            processed_ids.update(ids)
            multi_groups.append(grp.drop(columns=['_key']))
            n1a += 1

    print(f"[{GROUP_LABEL}]   1a. hash_dedup: {n1a:,} multi-member groups ({len(processed_ids):,} wines)")

    # ── 1b. ean_gtin ──
    n1b = 0
    df_ean = df[~df['id'].isin(processed_ids) & df['ean_gtin'].notna() & (df['ean_gtin'] != '')].copy()
    if len(df_ean) > 0:
        df_ean['_key'] = df_ean['pais_tabela'] + '||' + df_ean['ean_gtin'].astype(str)
        counts = df_ean.groupby('_key').size()
        multi_keys_set = set(counts[counts > 1].index)
        df_multi = df_ean[df_ean['_key'].isin(multi_keys_set)]

        for key, grp in df_multi.groupby('_key'):
            ids = set(grp['id'].tolist()) - processed_ids
            if len(ids) < 2:
                continue
            grp = grp[grp['id'].isin(ids)]
            processed_ids.update(ids)
            multi_groups.append(grp.drop(columns=['_key']))
            n1b += 1

    print(f"[{GROUP_LABEL}]   1b. ean_gtin: {n1b:,} multi-member groups")

    # ── 1c. nome_normalizado + safra ──
    n1c = 0
    df_rem = df[~df['id'].isin(processed_ids)].copy()
    if len(df_rem) > 0:
        df_rem['_safra'] = df_rem['safra'].fillna(-1).astype(int).astype(str)
        df_rem['_key'] = df_rem['pais_tabela'] + '||' + df_rem['nome_normalizado'].fillna('') + '||' + df_rem['_safra']
        counts = df_rem.groupby('_key').size()
        multi_keys_set = set(counts[counts > 1].index)
        df_multi = df_rem[df_rem['_key'].isin(multi_keys_set)]

        for key, grp in df_multi.groupby('_key'):
            ids = set(grp['id'].tolist()) - processed_ids
            if len(ids) < 2:
                continue
            grp = grp[grp['id'].isin(ids)]
            processed_ids.update(ids)
            multi_groups.append(grp.drop(columns=['_safra', '_key']))
            n1c += 1

    n_remaining = len(df) - len(processed_ids)
    print(f"[{GROUP_LABEL}]   1c. nome+safra: {n1c:,} multi-member groups")
    print(f"[{GROUP_LABEL}]   Total N1: {len(multi_groups):,} multi-groups, {len(processed_ids):,} wines consumed, {n_remaining:,} singletons remaining")

    return multi_groups, processed_ids


# ── Merge & validate a multi-member group ────────────────────────────────────

def merge_and_validate(grp_df):
    """
    Merge a multi-member group into one row. Returns (row_tuple, quarantine_list).
    row_tuple is ready for INSERT. quarantine_list has dicts for quarantine table.
    """
    quarantine = []

    # Validation: mixed types → split
    tipos = grp_df['tipo'].dropna().unique()
    bad_types = set(tipos) & {'tinto', 'branco', 'rose', 'espumante'}
    if len(bad_types) > 1:
        # Split by type, return multiple rows
        results = []
        for tipo_val, sub in grp_df.groupby('tipo', dropna=False):
            row = _merge_single(sub, 'deterministic', 1.0)
            results.append(row)
        return results, quarantine

    # Validation: price 10x
    precos = grp_df['preco'].dropna()
    precos = precos[precos > 0]
    if len(precos) >= 2 and precos.max() / precos.min() > 10:
        ids = sorted(grp_df['id'].tolist())
        for i in range(len(ids) - 1):
            quarantine.append({
                'clean_id_a': int(ids[i]),
                'clean_id_b': int(ids[i+1]),
                'nome_a': grp_df[grp_df['id'] == ids[i]]['nome_limpo'].iloc[0],
                'nome_b': grp_df[grp_df['id'] == ids[i+1]]['nome_limpo'].iloc[0],
                'match_probability': 1.0,
                'motivo': f"price_10x:{precos.min():.2f}-{precos.max():.2f}",
            })

    row = _merge_single(grp_df, 'deterministic', 1.0)
    return [row], quarantine


def _merge_single(grp_df, match_type, match_prob):
    """Merge a group into a single INSERT-ready tuple."""
    nome_idx = grp_df['nome_limpo'].fillna('').str.len().idxmax()
    precos = grp_df['preco'].dropna()
    precos = precos[precos > 0]

    return (
        grp_df.loc[nome_idx, 'nome_limpo'],               # nome_limpo
        grp_df.iloc[0]['nome_normalizado'],                 # nome_normalizado
        first_non_null(grp_df['produtor_extraido']),        # produtor
        first_non_null(grp_df['produtor_normalizado']),     # produtor_normalizado
        safe_int(first_non_null(grp_df['safra'])),          # safra
        most_common_val(grp_df['tipo']),                    # tipo
        first_non_null(grp_df['pais']),                     # pais
        grp_df.iloc[0]['pais_tabela'],                      # pais_tabela
        first_non_null(grp_df['regiao']),                   # regiao
        first_non_null(grp_df['sub_regiao']),               # sub_regiao
        first_non_null(grp_df['uvas']),                     # uvas
        safe_float(grp_df['rating'].max()) if grp_df['rating'].notna().any() else None,
        safe_int(grp_df['total_ratings'].max()) if grp_df['total_ratings'].notna().any() else None,
        safe_float(precos.min()) if len(precos) > 0 else None,
        safe_float(precos.max()) if len(precos) > 0 else None,
        most_common_val(grp_df['moeda']),                   # moeda_referencia
        first_non_null(grp_df['url_imagem']),               # url_imagem
        first_non_null(grp_df['hash_dedup']),               # hash_dedup
        first_non_null(grp_df['ean_gtin']),                 # ean_gtin
        match_type,                                         # match_type
        match_prob,                                         # match_probability
        len(grp_df),                                        # total_copias
        sorted(grp_df['id'].tolist()),                      # clean_ids
    )


# ── Bulk insert singletons ───────────────────────────────────────────────────

def bulk_insert_singletons(conn, df, processed_ids):
    """Insert all non-grouped wines as singletons directly from DataFrame — fast."""
    df_singles = df[~df['id'].isin(processed_ids)].copy()
    if len(df_singles) == 0:
        return 0

    print(f"[{GROUP_LABEL}]   Inserting {len(df_singles):,} singletons...")

    cur = conn.cursor()
    insert_sql = f"""
        INSERT INTO {TABLE_UNIQUE} (
            nome_limpo, nome_normalizado, produtor, produtor_normalizado,
            safra, tipo, pais, pais_tabela, regiao, sub_regiao, uvas,
            rating_melhor, total_ratings_max, preco_min_global, preco_max_global,
            moeda_referencia, url_imagem, hash_dedup, ean_gtin,
            match_type, match_probability, total_copias, clean_ids
        ) VALUES %s
    """

    batch_size = 5000
    total = 0

    for start in range(0, len(df_singles), batch_size):
        batch = df_singles.iloc[start:start+batch_size]
        values = []
        for _, row in batch.iterrows():
            preco = row['preco']
            preco_val = float(preco) if pd.notna(preco) and preco > 0 else None

            values.append((
                row['nome_limpo'],
                row['nome_normalizado'],
                row['produtor_extraido'] if pd.notna(row['produtor_extraido']) else None,
                row['produtor_normalizado'] if pd.notna(row['produtor_normalizado']) else None,
                safe_int(row['safra']),
                row['tipo'] if pd.notna(row['tipo']) else None,
                row['pais'] if pd.notna(row['pais']) else None,
                row['pais_tabela'],
                row['regiao'] if pd.notna(row['regiao']) else None,
                row['sub_regiao'] if pd.notna(row['sub_regiao']) else None,
                row['uvas'] if pd.notna(row['uvas']) else None,
                safe_float(row['rating']),
                safe_int(row['total_ratings']),
                preco_val,
                preco_val,  # same min/max for singleton
                row['moeda'] if pd.notna(row['moeda']) else None,
                row['url_imagem'] if pd.notna(row['url_imagem']) else None,
                row['hash_dedup'] if pd.notna(row['hash_dedup']) else None,
                row['ean_gtin'] if pd.notna(row['ean_gtin']) else None,
                'singleton',    # match_type
                1.0,            # match_probability
                1,              # total_copias
                [int(row['id'])],  # clean_ids
            ))

        execute_values(cur, insert_sql, values, page_size=1000)
        total += len(values)
        if total % 50000 == 0:
            print(f"[{GROUP_LABEL}]     singletons: {total:,}/{len(df_singles):,}")

    conn.commit()
    cur.close()
    print(f"[{GROUP_LABEL}]   Singletons done: {total:,}")
    return total


# ── NIVEL 2: Splink ─────────────────────────────────────────────────────────

def nivel2_splink(df, processed_ids):
    """Probabilistic dedup on remaining wines. Returns (splink_groups, quarantine_df)."""
    df_remaining = df[~df['id'].isin(processed_ids)].copy()

    if len(df_remaining) < 100:
        print(f"[{GROUP_LABEL}]   Nivel 2: skipped ({len(df_remaining)} wines remaining)")
        return [], pd.DataFrame()

    print(f"[{GROUP_LABEL}]   Nivel 2: {len(df_remaining):,} remaining wines...")

    import splink.comparison_library as cl
    import splink.blocking_rule_library as brl
    from splink import DuckDBAPI, Linker, SettingsCreator, block_on

    cols = ['id', 'nome_normalizado', 'produtor_normalizado', 'safra',
            'tipo', 'pais_tabela', 'regiao', 'uvas']
    df_sp = df_remaining[cols].copy()
    df_sp = df_sp.where(df_sp.notna(), None)

    training_block_nome = block_on("nome_normalizado")
    training_block_produtor = block_on("produtor_normalizado")

    prediction_blocking_rules = [
        block_on("nome_normalizado"),
        block_on("produtor_normalizado", "pais_tabela"),
        brl.CustomRule(
            "SUBSTR(l.nome_normalizado,1,15) = SUBSTR(r.nome_normalizado,1,15) "
            "AND l.pais_tabela = r.pais_tabela"
        ),
    ]

    settings = SettingsCreator(
        link_type="dedupe_only",
        unique_id_column_name="id",
        comparisons=[
            cl.JaroWinklerAtThresholds("nome_normalizado", [0.92, 0.80]),
            cl.JaroWinklerAtThresholds("produtor_normalizado", [0.92, 0.80]),
            cl.ExactMatch("safra"),
            cl.ExactMatch("tipo"),
            cl.ExactMatch("pais_tabela"),
            cl.JaroWinklerAtThresholds("regiao", [0.88]),
            cl.JaroWinklerAtThresholds("uvas", [0.88]),
        ],
        blocking_rules_to_generate_predictions=prediction_blocking_rules,
        retain_matching_columns=True,
    )

    MATCH_TH = 0.80
    REVIEW_TH = 0.50

    all_groups = []
    all_quarantine = []
    id_to_nome = df_remaining.set_index('id')['nome_limpo'].to_dict()

    MAX_COUNTRY_TIME = 300  # 5 min max per country

    for country in sorted(df_remaining['pais_tabela'].unique()):
        df_c = df_sp[df_sp['pais_tabela'] == country].copy().reset_index(drop=True)
        if len(df_c) < 10:
            continue

        print(f"[{GROUP_LABEL}]     Splink {country.upper()}: {len(df_c):,}...", end=" ", flush=True)
        t_country = time.time()

        try:
            db_api = DuckDBAPI()
            linker = Linker(df_c, settings, db_api)
            linker.training.estimate_probability_two_random_records_match(training_block_nome, recall=0.7)
            linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)
            linker.training.estimate_parameters_using_expectation_maximisation(training_block_nome, fix_u_probabilities=True)
            linker.training.estimate_parameters_using_expectation_maximisation(training_block_produtor, fix_u_probabilities=True)

            if time.time() - t_country > MAX_COUNTRY_TIME:
                print(f"TIMEOUT after training ({time.time()-t_country:.0f}s)")
                continue

            results = linker.inference.predict(threshold_match_probability=REVIEW_TH)
            df_pred = results.as_pandas_dataframe()

            if len(df_pred) == 0:
                print("0 pairs")
                continue

            # Quarantine (0.50 - 0.80)
            df_review = df_pred[(df_pred["match_probability"] >= REVIEW_TH) & (df_pred["match_probability"] < MATCH_TH)]
            for _, row in df_review.iterrows():
                all_quarantine.append((
                    int(row['id_l']), int(row['id_r']),
                    id_to_nome.get(int(row['id_l']), ''),
                    id_to_nome.get(int(row['id_r']), ''),
                    float(row['match_probability']),
                    'splink_uncertain',
                ))

            if time.time() - t_country > MAX_COUNTRY_TIME:
                print(f"TIMEOUT after predict ({time.time()-t_country:.0f}s), {len(df_review)} quarantine")
                continue

            # Cluster
            clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(results, threshold_match_probability=MATCH_TH)
            df_cl = clusters.as_pandas_dataframe()

            if len(df_cl) > 0:
                multi = df_cl.groupby('cluster_id').filter(lambda x: len(x) > 1)
                n_cl = multi['cluster_id'].nunique() if len(multi) > 0 else 0
                for cid, cgrp in multi.groupby('cluster_id'):
                    cids = cgrp['id'].tolist()
                    grp = df_remaining[df_remaining['id'].isin(cids)]
                    if len(grp) > 1:
                        probs = df_pred[(df_pred['id_l'].isin(cids)) & (df_pred['id_r'].isin(cids)) & (df_pred['match_probability'] >= MATCH_TH)]['match_probability']
                        avg_p = float(probs.mean()) if len(probs) > 0 else MATCH_TH
                        all_groups.append((avg_p, grp))
                elapsed = time.time() - t_country
                print(f"{n_cl} clusters, {len(df_review)} quarantine ({elapsed:.0f}s)")
            else:
                print(f"0 clusters, {len(df_review)} quarantine")

        except Exception as e:
            print(f"ERROR: {e}")
            continue

    df_q = pd.DataFrame(all_quarantine, columns=['clean_id_a','clean_id_b','nome_a','nome_b','match_probability','motivo']) if all_quarantine else pd.DataFrame()
    return all_groups, df_q


# ── Save ─────────────────────────────────────────────────────────────────────

def save_multi_groups(conn, multi_groups, match_type_default='deterministic', prob_default=1.0):
    """Save multi-member groups (merged). Returns (count_inserted, quarantine_list)."""
    cur = conn.cursor()
    insert_sql = f"""
        INSERT INTO {TABLE_UNIQUE} (
            nome_limpo, nome_normalizado, produtor, produtor_normalizado,
            safra, tipo, pais, pais_tabela, regiao, sub_regiao, uvas,
            rating_melhor, total_ratings_max, preco_min_global, preco_max_global,
            moeda_referencia, url_imagem, hash_dedup, ean_gtin,
            match_type, match_probability, total_copias, clean_ids
        ) VALUES %s
    """

    all_rows = []
    all_quarantine = []

    for item in multi_groups:
        if isinstance(item, tuple) and len(item) == 2:
            prob, grp_df = item
            mt = 'splink_high'
        else:
            grp_df = item
            mt = match_type_default
            prob = prob_default

        rows, quar = merge_and_validate(grp_df)
        for r in rows:
            # Override match_type and probability from the tuple
            r_list = list(r)
            r_list[19] = mt   # match_type
            r_list[20] = prob # match_probability
            all_rows.append(tuple(r_list))
        all_quarantine.extend(quar)

    # Batch insert
    batch_size = 5000
    for i in range(0, len(all_rows), batch_size):
        batch = all_rows[i:i+batch_size]
        execute_values(cur, insert_sql, batch, page_size=1000)

    conn.commit()
    cur.close()
    print(f"[{GROUP_LABEL}]   Multi-groups saved: {len(all_rows):,} rows")
    return len(all_rows), all_quarantine


def save_quarantine(conn, df_q, extra_q):
    """Save quarantine pairs."""
    cur = conn.cursor()
    rows = []

    if len(df_q) > 0:
        for _, r in df_q.iterrows():
            rows.append((int(r['clean_id_a']), int(r['clean_id_b']),
                         r.get('nome_a',''), r.get('nome_b',''),
                         float(r['match_probability']), r.get('motivo','splink_uncertain')))

    for q in extra_q:
        rows.append((q['clean_id_a'], q['clean_id_b'],
                      q.get('nome_a',''), q.get('nome_b',''),
                      q['match_probability'], q['motivo']))

    if rows:
        execute_values(cur, f"""
            INSERT INTO {TABLE_QUARANTINE} (clean_id_a, clean_id_b, nome_a, nome_b, match_probability, motivo)
            VALUES %s
        """, rows, page_size=1000)

    conn.commit()
    cur.close()
    return len(rows)


# ── Show examples ────────────────────────────────────────────────────────────

def safe_print(text):
    """Print handling Unicode on Windows."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'))

def show_examples(conn):
    cur = conn.cursor()

    safe_print(f"\n{'='*80}")
    safe_print("EXEMPLOS DE MERGE - NIVEL 1 (deterministico)")
    safe_print(f"{'='*80}")
    cur.execute(f"""
        SELECT nome_limpo, produtor, safra, pais_tabela, total_copias, clean_ids
        FROM {TABLE_UNIQUE}
        WHERE match_type = 'deterministic' AND total_copias > 1
        ORDER BY total_copias DESC LIMIT 10
    """)
    for row in cur.fetchall():
        nome, prod, safra, pais, copias, ids = row
        safe_print(f"  {pais.upper()} | {nome} | {prod or '?'} | {safra or 'NV'} | {copias} copias | IDs: {ids[:5]}{'...' if len(ids)>5 else ''}")

    safe_print(f"\n{'='*80}")
    safe_print("EXEMPLOS DE MERGE - NIVEL 2 (Splink)")
    safe_print(f"{'='*80}")
    cur.execute(f"""
        SELECT nome_limpo, produtor, safra, pais_tabela, total_copias, clean_ids, match_probability
        FROM {TABLE_UNIQUE}
        WHERE match_type = 'splink_high' AND total_copias > 1
        ORDER BY total_copias DESC LIMIT 10
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            nome, prod, safra, pais, copias, ids, prob = row
            safe_print(f"  {pais.upper()} | {nome} | {prod or '?'} | {safra or 'NV'} | {copias} copias | prob={prob:.2f} | IDs: {ids[:5]}{'...' if len(ids)>5 else ''}")
    else:
        safe_print("  (nenhum match Splink com multiplas copias)")

    cur.close()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(f"[{GROUP_LABEL}] === DEDUP GROUP 10 ===")
    print(f"[{GROUP_LABEL}] Paises: {', '.join(c.upper() for c in GROUP_COUNTRIES)}")

    conn = psycopg2.connect(DB_URL)
    print(f"[{GROUP_LABEL}] Creating tables...")
    create_tables(conn)

    df = load_wines(conn)
    total_input = len(df)

    # ── NIVEL 1 ──
    print(f"\n[{GROUP_LABEL}] === NIVEL 1: Deterministico ===")
    t1 = time.time()
    multi_groups_n1, processed_ids_n1 = nivel1_dedup(df)
    n1_time = time.time() - t1
    print(f"[{GROUP_LABEL}]   Nivel 1 time: {n1_time:.1f}s")

    # ── NIVEL 2 ──
    print(f"\n[{GROUP_LABEL}] === NIVEL 2: Splink Probabilistico ===")
    t2 = time.time()
    splink_groups, df_quarantine = nivel2_splink(df, processed_ids_n1)
    n2_time = time.time() - t2

    # Collect splink IDs
    splink_ids = set()
    for _, grp in splink_groups:
        splink_ids.update(grp['id'].tolist())
    print(f"[{GROUP_LABEL}]   Nivel 2 time: {n2_time:.1f}s, {len(splink_groups):,} groups, {len(splink_ids):,} wines")

    # ── SAVE ──
    print(f"\n[{GROUP_LABEL}] === SAVING ===")
    t3 = time.time()

    # Save N1 multi-member groups
    n_multi, extra_q = save_multi_groups(conn, multi_groups_n1, 'deterministic', 1.0)

    # Save N2 splink groups
    n_splink, extra_q2 = save_multi_groups(conn, splink_groups, 'splink_high', 0.80)
    extra_q.extend(extra_q2)

    # Save singletons (bulk — fast)
    all_consumed = processed_ids_n1 | splink_ids
    n_singletons = bulk_insert_singletons(conn, df, all_consumed)

    # Save quarantine
    n_quarantine = save_quarantine(conn, df_quarantine, extra_q)

    print(f"[{GROUP_LABEL}]   Save time: {time.time()-t3:.1f}s")

    # ── VERIFY ──
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {TABLE_UNIQUE}")
    count_unique = cur.fetchone()[0]
    cur.execute(f"SELECT match_type, COUNT(*) FROM {TABLE_UNIQUE} GROUP BY match_type ORDER BY COUNT(*) DESC")
    match_types = cur.fetchall()
    cur.execute(f"SELECT total_copias, COUNT(*) FROM {TABLE_UNIQUE} GROUP BY total_copias ORDER BY total_copias DESC LIMIT 10")
    copy_dist = cur.fetchall()
    cur.execute(f"SELECT COUNT(*) FROM {TABLE_QUARANTINE}")
    count_quarantine = cur.fetchone()[0]
    cur.close()

    show_examples(conn)
    conn.close()

    # ── REPORT ──
    elapsed = time.time() - t0
    dedup_rate = (1 - count_unique / total_input) * 100 if total_input > 0 else 0

    print(f"\n{'='*60}")
    print(f"=== GRUPO 10 CONCLUIDO ===")
    print(f"{'='*60}")
    print(f"Paises: {', '.join(c.upper() for c in GROUP_COUNTRIES)}")
    print(f"Input: {total_input:,} vinhos de wines_clean")
    print(f"Nivel 1 (deterministico): {len(multi_groups_n1):,} grupos com >1 copia")
    print(f"Nivel 2 (Splink): {len(splink_groups):,} grupos adicionais")
    print(f"Nivel 3 (quarentena): {count_quarantine:,} pares incertos")
    print(f"Output: {count_unique:,} vinhos unicos em {TABLE_UNIQUE}")
    print(f"Taxa de dedup: {dedup_rate:.1f}% (de {total_input:,} para {count_unique:,})")
    print(f"Tempo total: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"\nDistribuicao por match_type:")
    for mt, cnt in match_types:
        print(f"  {mt}: {cnt:,}")
    print(f"\nDistribuicao por total_copias (top 10):")
    for tc, cnt in copy_dist:
        print(f"  {tc} copias: {cnt:,} vinhos")


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
