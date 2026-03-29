"""
DEDUP GROUP 5 - AR, HK, MX
Deduplicacao em 3 niveis: deterministico + Splink probabilistico + quarentena
"""

import sys
import time
import psycopg2
import psycopg2.extras
import pandas as pd
import numpy as np
from collections import Counter

def to_python(val):
    """Convert numpy types to native Python types for psycopg2."""
    if val is None:
        return None
    if isinstance(val, (list, np.ndarray)):
        if isinstance(val, np.ndarray):
            return [int(x) for x in val.tolist()]
        return val
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        v = float(val)
        return None if np.isnan(v) else v
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, float) and np.isnan(val):
        return None
    try:
        if pd.isna(val):
            return None
    except (ValueError, TypeError):
        pass
    return val

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
COUNTRIES = ('ar', 'hk', 'mx')
GROUP = 5
MATCH_THRESHOLD = 0.80
REVIEW_THRESHOLD = 0.50
BATCH_SIZE = 5000

# ── Helpers ──

def first_non_null(group_df, col):
    vals = group_df[col].dropna()
    if len(vals) == 0:
        return None
    return vals.iloc[0]

def most_common(group_df, col):
    vals = group_df[col].dropna().tolist()
    if not vals:
        return None
    counter = Counter(vals)
    return counter.most_common(1)[0][0]

def merge_group(group_df):
    # Filter valid prices (non-null, > 0)
    valid_prices = group_df['preco'].dropna()
    valid_prices = valid_prices[valid_prices > 0]

    result = {
        'nome_limpo': group_df.loc[group_df['nome_limpo'].str.len().idxmax(), 'nome_limpo'],
        'nome_normalizado': group_df.iloc[0]['nome_normalizado'],
        'produtor': first_non_null(group_df, 'produtor_extraido'),
        'produtor_normalizado': first_non_null(group_df, 'produtor_normalizado'),
        'safra': first_non_null(group_df, 'safra'),
        'tipo': most_common(group_df, 'tipo'),
        'pais': first_non_null(group_df, 'pais'),
        'pais_tabela': group_df.iloc[0]['pais_tabela'],
        'regiao': first_non_null(group_df, 'regiao'),
        'sub_regiao': first_non_null(group_df, 'sub_regiao'),
        'uvas': first_non_null(group_df, 'uvas'),
        'rating_melhor': group_df['rating'].max() if group_df['rating'].notna().any() else None,
        'total_ratings_max': int(group_df['total_ratings'].max()) if group_df['total_ratings'].notna().any() else None,
        'preco_min_global': float(valid_prices.min()) if len(valid_prices) > 0 else None,
        'preco_max_global': float(valid_prices.max()) if len(valid_prices) > 0 else None,
        'moeda_referencia': most_common(group_df, 'moeda'),
        'url_imagem': first_non_null(group_df, 'url_imagem'),
        'hash_dedup': first_non_null(group_df, 'hash_dedup'),
        'ean_gtin': first_non_null(group_df, 'ean_gtin'),
        'total_copias': len(group_df),
        'clean_ids': [int(x) for x in group_df['id'].tolist()],
    }
    # Convert all numpy types to native Python
    return {k: to_python(v) for k, v in result.items()}

def validate_group(group_df):
    """Check if a group should be split or quarantined."""
    issues = []

    # Check mixed types
    types = group_df['tipo'].dropna().unique()
    if len(types) > 1:
        type_set = set(t.lower().strip() for t in types if t)
        conflicting = type_set & {'tinto', 'branco', 'rose', 'espumante'}
        if len(conflicting) > 1:
            issues.append(f"mixed_types:{','.join(conflicting)}")

    # Check price variation >10x
    valid_prices = group_df['preco'].dropna()
    valid_prices = valid_prices[valid_prices > 0]
    if len(valid_prices) >= 2:
        pmin, pmax = valid_prices.min(), valid_prices.max()
        if pmin > 0 and pmax / pmin > 10:
            issues.append(f"price_spread:{pmin:.2f}-{pmax:.2f}")

    # Check giant groups
    if len(group_df) > 100:
        issues.append(f"giant_group:{len(group_df)}")

    return issues


# ── Database setup ──

def create_tables(conn):
    cur = conn.cursor()
    cur.execute(f"""
        DROP TABLE IF EXISTS wines_unique_g{GROUP} CASCADE;
        DROP TABLE IF EXISTS dedup_quarantine_g{GROUP} CASCADE;

        CREATE TABLE wines_unique_g{GROUP} (
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

        CREATE TABLE dedup_quarantine_g{GROUP} (
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
    placeholders = ','.join(['%s'] * len(COUNTRIES))
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
    df = pd.read_sql(query, conn, params=list(COUNTRIES))
    return df


def insert_unique_batch(conn, rows):
    if not rows:
        return
    cur = conn.cursor()
    cols = [
        'nome_limpo', 'nome_normalizado', 'produtor', 'produtor_normalizado',
        'safra', 'tipo', 'pais', 'pais_tabela', 'regiao', 'sub_regiao', 'uvas',
        'rating_melhor', 'total_ratings_max', 'preco_min_global', 'preco_max_global',
        'moeda_referencia', 'url_imagem', 'hash_dedup', 'ean_gtin',
        'match_type', 'match_probability', 'total_copias', 'clean_ids'
    ]
    placeholders = ','.join(['%s'] * len(cols))
    sql = f"INSERT INTO wines_unique_g{GROUP} ({','.join(cols)}) VALUES ({placeholders})"

    batch = []
    for r in rows:
        batch.append(tuple(r[c] for c in cols))

    psycopg2.extras.execute_batch(cur, sql, batch, page_size=BATCH_SIZE)
    conn.commit()
    cur.close()


def insert_quarantine_batch(conn, rows):
    if not rows:
        return
    cur = conn.cursor()
    sql = f"""INSERT INTO dedup_quarantine_g{GROUP}
              (clean_id_a, clean_id_b, nome_a, nome_b, match_probability, motivo)
              VALUES (%s, %s, %s, %s, %s, %s)"""
    psycopg2.extras.execute_batch(cur, sql, rows, page_size=BATCH_SIZE)
    conn.commit()
    cur.close()


# ── NIVEL 1: Deterministico ──

def nivel_1_dedup(df):
    """Deterministic dedup: hash, EAN, exact name+vintage."""
    processed_ids = set()
    groups = []
    quarantine_pairs = []

    print(f"[X{GROUP}] NIVEL 1 - Deterministico")

    # 1a. hash_dedup
    df_hash = df[df['hash_dedup'].notna() & (df['hash_dedup'] != '')].copy()
    hash_groups = df_hash.groupby(['pais_tabela', 'hash_dedup'])
    n_hash = 0
    for (pais, hash_val), gdf in hash_groups:
        if len(gdf) < 2:
            continue
        ids = set(gdf['id'].tolist())
        if ids & processed_ids:
            gdf = gdf[~gdf['id'].isin(processed_ids)]
            if len(gdf) < 2:
                continue
        issues = validate_group(gdf)
        if 'mixed_types' in str(issues):
            # Split by type
            for tipo, subg in gdf.groupby('tipo'):
                if len(subg) >= 2:
                    merged = merge_group(subg)
                    merged['match_type'] = 'deterministic'
                    merged['match_probability'] = 1.0
                    groups.append(merged)
                    processed_ids.update(subg['id'].tolist())
                    n_hash += 1
        else:
            if any('price_spread' in i for i in issues):
                # Quarantine price outliers but still group
                for idx_a, row_a in gdf.iterrows():
                    for idx_b, row_b in gdf.iterrows():
                        if idx_a < idx_b:
                            quarantine_pairs.append((
                                int(row_a['id']), int(row_b['id']),
                                row_a['nome_limpo'], row_b['nome_limpo'],
                                1.0, f"price_spread_hash:{issues}"
                            ))
            merged = merge_group(gdf)
            merged['match_type'] = 'deterministic'
            merged['match_probability'] = 1.0
            groups.append(merged)
            processed_ids.update(gdf['id'].tolist())
            n_hash += 1

    print(f"  1a. hash_dedup: {n_hash} grupos ({len(processed_ids)} vinhos)")

    # 1b. ean_gtin
    df_ean = df[df['ean_gtin'].notna() & (df['ean_gtin'] != '') & (~df['id'].isin(processed_ids))].copy()
    ean_groups = df_ean.groupby(['pais_tabela', 'ean_gtin'])
    n_ean = 0
    for (pais, ean_val), gdf in ean_groups:
        if len(gdf) < 2:
            continue
        ids = set(gdf['id'].tolist())
        if ids & processed_ids:
            gdf = gdf[~gdf['id'].isin(processed_ids)]
            if len(gdf) < 2:
                continue
        issues = validate_group(gdf)
        if 'mixed_types' in str(issues):
            for tipo, subg in gdf.groupby('tipo'):
                if len(subg) >= 2:
                    merged = merge_group(subg)
                    merged['match_type'] = 'deterministic'
                    merged['match_probability'] = 1.0
                    groups.append(merged)
                    processed_ids.update(subg['id'].tolist())
                    n_ean += 1
        else:
            merged = merge_group(gdf)
            merged['match_type'] = 'deterministic'
            merged['match_probability'] = 1.0
            groups.append(merged)
            processed_ids.update(gdf['id'].tolist())
            n_ean += 1

    print(f"  1b. ean_gtin: {n_ean} grupos ({len(processed_ids)} vinhos)")

    # 1c. nome_normalizado + safra
    df_remaining = df[~df['id'].isin(processed_ids)].copy()
    # For wines with safra
    df_with_safra = df_remaining[df_remaining['safra'].notna()].copy()
    name_safra_groups = df_with_safra.groupby(['pais_tabela', 'nome_normalizado', 'safra'])
    n_name = 0
    for (pais, nome, safra), gdf in name_safra_groups:
        if len(gdf) < 2:
            continue
        issues = validate_group(gdf)
        if 'mixed_types' in str(issues):
            for tipo, subg in gdf.groupby('tipo'):
                if len(subg) >= 2:
                    merged = merge_group(subg)
                    merged['match_type'] = 'deterministic'
                    merged['match_probability'] = 1.0
                    groups.append(merged)
                    processed_ids.update(subg['id'].tolist())
                    n_name += 1
        else:
            merged = merge_group(gdf)
            merged['match_type'] = 'deterministic'
            merged['match_probability'] = 1.0
            groups.append(merged)
            processed_ids.update(gdf['id'].tolist())
            n_name += 1

    # For wines without safra - group by nome_normalizado only (safra IS NULL)
    df_no_safra = df_remaining[df_remaining['safra'].isna() & (~df_remaining['id'].isin(processed_ids))].copy()
    name_only_groups = df_no_safra.groupby(['pais_tabela', 'nome_normalizado'])
    n_name_nosafra = 0
    for (pais, nome), gdf in name_only_groups:
        if len(gdf) < 2:
            continue
        issues = validate_group(gdf)
        if 'mixed_types' in str(issues):
            for tipo, subg in gdf.groupby('tipo'):
                if len(subg) >= 2:
                    merged = merge_group(subg)
                    merged['match_type'] = 'deterministic'
                    merged['match_probability'] = 1.0
                    groups.append(merged)
                    processed_ids.update(subg['id'].tolist())
                    n_name_nosafra += 1
        else:
            merged = merge_group(gdf)
            merged['match_type'] = 'deterministic'
            merged['match_probability'] = 1.0
            groups.append(merged)
            processed_ids.update(gdf['id'].tolist())
            n_name_nosafra += 1

    print(f"  1c. nome+safra: {n_name} grupos | nome (sem safra): {n_name_nosafra} grupos ({len(processed_ids)} vinhos total)")

    return groups, processed_ids, quarantine_pairs


# ── NIVEL 2: Splink probabilistico ──

def nivel_2_dedup(df, processed_ids):
    """Probabilistic dedup using Splink."""
    print(f"\n[X{GROUP}] NIVEL 2 - Splink probabilistico")

    df_remaining = df[~df['id'].isin(processed_ids)].copy()
    print(f"  Vinhos restantes: {len(df_remaining)}")

    if len(df_remaining) < 100:
        print("  Poucos vinhos restantes, pulando Splink")
        return [], pd.DataFrame()

    # Prepare data for Splink
    splink_cols = ['id', 'nome_normalizado', 'produtor_normalizado', 'safra',
                   'tipo', 'pais_tabela', 'regiao', 'uvas']
    df_splink = df_remaining[splink_cols].copy()

    # Replace NaN with None for Splink
    df_splink = df_splink.where(df_splink.notna(), None)

    # Ensure safra is integer or None
    df_splink['safra'] = df_splink['safra'].apply(lambda x: int(x) if x is not None and pd.notna(x) else None)

    # Process per country to manage memory
    all_clusters = []
    all_review = []

    for pais in COUNTRIES:
        df_pais = df_splink[df_splink['pais_tabela'] == pais].copy().reset_index(drop=True)
        if len(df_pais) < 100:
            print(f"  [{pais.upper()}] Poucos vinhos ({len(df_pais)}), pulando Splink")
            continue

        print(f"  [{pais.upper()}] Processando {len(df_pais)} vinhos com Splink...")
        try:
            clusters, review = run_splink_dedup(df_pais)
            if len(clusters) > 0:
                all_clusters.append(clusters)
            if len(review) > 0:
                all_review.append(review)
            print(f"  [{pais.upper()}] Clusters: {clusters['cluster_id'].nunique() if len(clusters) > 0 else 0} | Review pairs: {len(review)}")
        except Exception as e:
            print(f"  [{pais.upper()}] ERRO Splink: {e}")
            import traceback
            traceback.print_exc()

    df_all_clusters = pd.concat(all_clusters, ignore_index=True) if all_clusters else pd.DataFrame(columns=['id', 'cluster_id'])
    df_all_review = pd.concat(all_review, ignore_index=True) if all_review else pd.DataFrame()

    return df_all_clusters, df_all_review


def run_splink_dedup(df_remaining):
    """Run Splink on a DataFrame. Returns (df_clusters, df_review_pairs)."""
    import splink.comparison_library as cl
    import splink.blocking_rule_library as brl
    from splink import DuckDBAPI, Linker, SettingsCreator, block_on

    if len(df_remaining) < 10:
        return pd.DataFrame(columns=["id", "cluster_id"]), pd.DataFrame()

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
            cl.JaroWinklerAtThresholds(
                col_name="nome_normalizado",
                score_threshold_or_thresholds=[0.92, 0.80],
            ),
            cl.JaroWinklerAtThresholds(
                col_name="produtor_normalizado",
                score_threshold_or_thresholds=[0.92, 0.80],
            ),
            cl.ExactMatch("safra"),
            cl.ExactMatch("tipo"),
            cl.ExactMatch("pais_tabela"),
            cl.JaroWinklerAtThresholds(
                col_name="regiao",
                score_threshold_or_thresholds=[0.88],
            ),
            cl.JaroWinklerAtThresholds(
                col_name="uvas",
                score_threshold_or_thresholds=[0.88],
            ),
        ],
        blocking_rules_to_generate_predictions=prediction_blocking_rules,
        retain_matching_columns=True,
    )

    db_api = DuckDBAPI()
    linker = Linker(df_remaining, settings, db_api)

    linker.training.estimate_probability_two_random_records_match(
        training_block_nome, recall=0.7,
    )

    linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)

    linker.training.estimate_parameters_using_expectation_maximisation(
        training_block_nome, fix_u_probabilities=True,
    )
    linker.training.estimate_parameters_using_expectation_maximisation(
        training_block_produtor, fix_u_probabilities=True,
    )

    results = linker.inference.predict(threshold_match_probability=REVIEW_THRESHOLD)
    df_predictions = results.as_pandas_dataframe()

    if len(df_predictions) == 0:
        return pd.DataFrame(columns=["id", "cluster_id"]), pd.DataFrame()

    # Review pairs (quarantine)
    df_review = df_predictions[
        (df_predictions["match_probability"] >= REVIEW_THRESHOLD) &
        (df_predictions["match_probability"] < MATCH_THRESHOLD)
    ].copy()

    if len(df_review) > 0:
        # Get the right column names for IDs
        id_l_col = [c for c in df_review.columns if c.endswith('_l') and 'id' in c.lower()]
        id_r_col = [c for c in df_review.columns if c.endswith('_r') and 'id' in c.lower()]
        if id_l_col and id_r_col:
            df_review = df_review[[id_l_col[0], id_r_col[0], 'match_probability']].copy()
            df_review.columns = ['id_l', 'id_r', 'match_probability']
        else:
            df_review = df_review[['id_l', 'id_r', 'match_probability']].copy()

    # Cluster high-confidence matches
    clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
        results, threshold_match_probability=MATCH_THRESHOLD,
    )
    df_clusters = clusters.as_pandas_dataframe()

    return df_clusters, df_review


# ── Main pipeline ──

def main():
    t0 = time.time()
    print(f"=== DEDUP GRUPO {GROUP} - Paises: {', '.join(c.upper() for c in COUNTRIES)} ===\n")

    conn = psycopg2.connect(DB_URL)

    # Create destination tables
    print("Criando tabelas de destino...")
    create_tables(conn)

    # Load data
    print("Carregando vinhos...")
    df = load_wines(conn)
    total_input = len(df)
    print(f"Total: {total_input:,} vinhos\n")

    for pais in COUNTRIES:
        n = len(df[df['pais_tabela'] == pais])
        print(f"  {pais.upper()}: {n:,}")
    print()

    # ── NIVEL 1 ──
    t1 = time.time()
    det_groups, processed_ids, quarantine_pairs = nivel_1_dedup(df)
    print(f"\n  Nivel 1 total: {len(det_groups):,} grupos, {len(processed_ids):,} vinhos agrupados ({time.time()-t1:.1f}s)")

    # Save deterministic groups
    print("\n  Salvando grupos deterministicos...")
    insert_unique_batch(conn, det_groups)
    if quarantine_pairs:
        insert_quarantine_batch(conn, quarantine_pairs)

    # Singletons from nivel 1 - wines not matched
    n1_singletons = df[~df['id'].isin(processed_ids)]
    print(f"  Singletons apos nivel 1: {len(n1_singletons):,}")

    # ── NIVEL 2 ──
    t2 = time.time()
    df_clusters, df_review = nivel_2_dedup(df, processed_ids)

    splink_groups = []
    splink_processed_ids = set()
    quarantine_splink = []

    if len(df_clusters) > 0:
        print("  Processando clusters Splink...")
        # Detect ID column
        id_col = 'id' if 'id' in df_clusters.columns else df_clusters.columns[0]
        cluster_col = 'cluster_id'

        # Build id->row lookup for fast access
        df_indexed = df.set_index('id')

        # Find multi-member clusters
        cluster_counts = df_clusters[cluster_col].value_counts()
        multi_clusters = cluster_counts[cluster_counts > 1]
        print(f"  Multi-member clusters: {len(multi_clusters):,}")

        # Group all cluster assignments at once
        cluster_groups = df_clusters[df_clusters[cluster_col].isin(multi_clusters.index)].groupby(cluster_col)[id_col]

        n_processed = 0
        for cid, ids_series in cluster_groups:
            cluster_ids = ids_series.tolist()
            cluster_df = df_indexed.loc[df_indexed.index.isin(cluster_ids)].reset_index()
            if len(cluster_df) < 2:
                continue

            issues = validate_group(cluster_df)
            if 'mixed_types' in str(issues):
                for tipo, subg in cluster_df.groupby('tipo'):
                    if len(subg) >= 2:
                        merged = merge_group(subg)
                        merged['match_type'] = 'splink_high'
                        merged['match_probability'] = 0.85
                        splink_groups.append(merged)
                        splink_processed_ids.update(subg['id'].tolist())
            else:
                merged = merge_group(cluster_df)
                merged['match_type'] = 'splink_high'
                merged['match_probability'] = 0.85
                splink_groups.append(merged)
                splink_processed_ids.update(cluster_df['id'].tolist())

            n_processed += 1
            if n_processed % 5000 == 0:
                print(f"    Clusters processados: {n_processed:,}/{len(multi_clusters):,}")

    # Quarantine from Splink - vectorized
    if len(df_review) > 0:
        print(f"  Processando {len(df_review):,} pares para quarentena...")
        # Build name lookup
        id_to_nome = df.set_index('id')['nome_limpo'].to_dict()
        for _, row in df_review.iterrows():
            id_a = int(row['id_l'])
            id_b = int(row['id_r'])
            quarantine_splink.append((
                id_a, id_b,
                id_to_nome.get(id_a),
                id_to_nome.get(id_b),
                float(row['match_probability']),
                'splink_uncertain'
            ))

    print(f"\n  Nivel 2: {len(splink_groups):,} grupos, {len(splink_processed_ids):,} vinhos agrupados ({time.time()-t2:.1f}s)")

    # Save Splink groups
    if splink_groups:
        print("  Salvando grupos Splink...")
        insert_unique_batch(conn, splink_groups)
    if quarantine_splink:
        print(f"  Salvando {len(quarantine_splink):,} pares em quarentena...")
        insert_quarantine_batch(conn, quarantine_splink)

    # ── Singletons (vinhos sem match) ──
    all_processed = processed_ids | splink_processed_ids
    singletons = df[~df['id'].isin(all_processed)]
    print(f"\n  Singletons finais: {len(singletons):,}")

    # Save singletons as unique wines (1 copy each) - bulk INSERT via SQL
    print("  Salvando singletons via INSERT direto...")
    cur = conn.cursor()
    singleton_sql = f"""
        INSERT INTO wines_unique_g{GROUP}
            (nome_limpo, nome_normalizado, produtor, produtor_normalizado,
             safra, tipo, pais, pais_tabela, regiao, sub_regiao, uvas,
             rating_melhor, total_ratings_max, preco_min_global, preco_max_global,
             moeda_referencia, url_imagem, hash_dedup, ean_gtin,
             match_type, match_probability, total_copias, clean_ids)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'singleton', NULL, 1, ARRAY[%s])
    """
    singleton_batch = []
    for row in singletons.itertuples(index=False):
        valid_price = row.preco if pd.notna(row.preco) and row.preco > 0 else None
        singleton_batch.append((
            to_python(row.nome_limpo),
            to_python(row.nome_normalizado),
            to_python(row.produtor_extraido),
            to_python(row.produtor_normalizado),
            int(row.safra) if pd.notna(row.safra) else None,
            to_python(row.tipo),
            to_python(row.pais),
            to_python(row.pais_tabela),
            to_python(row.regiao),
            to_python(row.sub_regiao),
            to_python(row.uvas),
            float(row.rating) if pd.notna(row.rating) else None,
            int(row.total_ratings) if pd.notna(row.total_ratings) else None,
            float(valid_price) if valid_price else None,
            float(valid_price) if valid_price else None,
            to_python(row.moeda),
            to_python(row.url_imagem),
            to_python(row.hash_dedup),
            to_python(row.ean_gtin),
            int(row.id),
        ))
        if len(singleton_batch) >= BATCH_SIZE:
            psycopg2.extras.execute_batch(cur, singleton_sql, singleton_batch, page_size=BATCH_SIZE)
            conn.commit()
            singleton_batch = []
    if singleton_batch:
        psycopg2.extras.execute_batch(cur, singleton_sql, singleton_batch, page_size=BATCH_SIZE)
        conn.commit()
    cur.close()
    singleton_rows = []  # not needed anymore

    # ── Stats ──
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM wines_unique_g{GROUP}")
    total_unique = cur.fetchone()[0]
    cur.execute(f"SELECT match_type, COUNT(*) FROM wines_unique_g{GROUP} GROUP BY match_type ORDER BY COUNT(*) DESC")
    type_counts = cur.fetchall()
    cur.execute(f"SELECT COUNT(*) FROM dedup_quarantine_g{GROUP}")
    total_quarantine = cur.fetchone()[0]
    cur.execute(f"SELECT total_copias, COUNT(*) FROM wines_unique_g{GROUP} WHERE total_copias > 1 GROUP BY total_copias ORDER BY total_copias DESC LIMIT 10")
    copies_dist = cur.fetchall()
    cur.close()

    elapsed = time.time() - t0

    # ── Print examples ──
    print(f"\n{'='*60}")
    print(f"  10 EXEMPLOS - NIVEL 1 (deterministico)")
    print(f"{'='*60}")
    cur = conn.cursor()
    cur.execute(f"""
        SELECT nome_limpo, produtor, safra, total_copias, pais_tabela, clean_ids
        FROM wines_unique_g{GROUP}
        WHERE match_type = 'deterministic' AND total_copias > 1
        ORDER BY total_copias DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        nome, prod, safra, copies, pais, ids = row
        prod_str = f" | {prod}" if prod else ""
        safra_str = f" {safra}" if safra else ""
        print(f"  [{pais.upper()}] {nome}{safra_str}{prod_str} -> {copies} copias (IDs: {ids[:5]}{'...' if len(ids)>5 else ''})")

    cur.execute(f"""
        SELECT nome_limpo, produtor, safra, total_copias, pais_tabela, match_probability
        FROM wines_unique_g{GROUP}
        WHERE match_type = 'splink_high'
        ORDER BY total_copias DESC
        LIMIT 10
    """)
    splink_examples = cur.fetchall()
    if splink_examples:
        print(f"\n{'='*60}")
        print(f"  10 EXEMPLOS - NIVEL 2 (Splink)")
        print(f"{'='*60}")
        for row in splink_examples:
            nome, prod, safra, copies, pais, prob = row
            prod_str = f" | {prod}" if prod else ""
            safra_str = f" {safra}" if safra else ""
            print(f"  [{pais.upper()}] {nome}{safra_str}{prod_str} -> {copies} copias (prob: {prob:.2f})")
    cur.close()

    # ── Final report ──
    dedup_pct = (1 - total_unique / total_input) * 100 if total_input > 0 else 0

    print(f"\n{'='*60}")
    print(f"=== GRUPO {GROUP} CONCLUIDO ===")
    print(f"{'='*60}")
    print(f"Paises: {', '.join(c.upper() for c in COUNTRIES)}")
    print(f"Input: {total_input:,} vinhos de wines_clean")
    print(f"Nivel 1 (deterministico): {len(det_groups):,} grupos")
    print(f"Nivel 2 (Splink): {len(splink_groups):,} grupos adicionais")
    print(f"Nivel 3 (quarentena): {total_quarantine:,} pares incertos")
    print(f"Output: {total_unique:,} vinhos unicos em wines_unique_g{GROUP}")
    print(f"Taxa de dedup: {dedup_pct:.1f}% (de {total_input:,} para {total_unique:,})")
    print(f"Tempo: {elapsed:.1f}s")
    print()

    for mt, cnt in type_counts:
        print(f"  {mt}: {cnt:,}")
    print()
    if copies_dist:
        print("Distribuicao de copias (top 10):")
        for copies, cnt in copies_dist:
            print(f"  {copies} copias: {cnt:,} vinhos")

    conn.close()


if __name__ == '__main__':
    main()
