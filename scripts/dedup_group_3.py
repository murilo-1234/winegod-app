#!/usr/bin/env python3
"""
DEDUP GROUP 3 -- GB, IT
Deduplicacao de vinhos em 3 niveis: deterministico + Splink + quarentena
Totalmente vectorizado com pandas (sem iterrows).
"""

import os
import sys
import time
import warnings

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

warnings.filterwarnings("ignore")

# -- Config --
DB_URL = os.getenv("WINEGOD_LOCAL_URL", "postgresql://postgres:postgres123@localhost:5432/winegod_db")
PAISES = ('gb', 'it')
GROUP = 3
TABLE_UNIQUE = f"wines_unique_g{GROUP}"
TABLE_QUARANTINE = f"dedup_quarantine_g{GROUP}"
BATCH_SIZE = 5000
MATCH_THRESHOLD = 0.80
REVIEW_THRESHOLD = 0.50

def log(msg):
    print(msg, flush=True)


def vectorized_merge(df, group_col, match_type, match_probability=1.0):
    """Merge groups vectorizado usando groupby.agg. Retorna DataFrame pronto para insert."""

    df = df.copy()
    df['preco_valid'] = df['preco'].where(df['preco'] > 0, np.nan)
    df['nome_limpo_len'] = df['nome_limpo'].fillna('').str.len()

    # Step 1: fast agg (no lambdas)
    agg = df.groupby(group_col).agg(
        nome_normalizado=('nome_normalizado', 'first'),
        pais=('pais', 'first'),
        pais_tabela=('pais_tabela', 'first'),
        regiao=('regiao', 'first'),
        sub_regiao=('sub_regiao', 'first'),
        uvas=('uvas', 'first'),
        produtor=('produtor_extraido', 'first'),
        produtor_normalizado=('produtor_normalizado', 'first'),
        safra=('safra', 'first'),
        tipo=('tipo', 'first'),
        rating_melhor=('rating', 'max'),
        total_ratings_max=('total_ratings', 'max'),
        preco_min_global=('preco_valid', 'min'),
        preco_max_global=('preco_valid', 'max'),
        moeda_referencia=('moeda', 'first'),
        url_imagem=('url_imagem', 'first'),
        hash_dedup=('hash_dedup', 'first'),
        ean_gtin=('ean_gtin', 'first'),
        total_copias=('id', 'count'),
    ).reset_index()

    # Step 2: clean_ids (collect lists)
    clean_ids = df.groupby(group_col)['id'].apply(lambda x: list(x.astype(int))).reset_index()
    clean_ids.columns = [group_col, 'clean_ids']
    agg = agg.merge(clean_ids, on=group_col, how='left')

    # Step 3: nome_limpo mais longo de cada grupo (vectorizado via sort+drop_duplicates)
    df_sorted = df.sort_values([group_col, 'nome_limpo_len'], ascending=[True, False])
    best_names = df_sorted.drop_duplicates(subset=[group_col], keep='first')[[group_col, 'nome_limpo']]
    agg = agg.merge(best_names, on=group_col, how='left')

    agg['match_type'] = match_type
    agg['match_probability'] = match_probability
    agg.drop(columns=[group_col], inplace=True, errors='ignore')

    # Converter NaN para None
    agg = agg.where(agg.notna(), None)

    # Converter total_ratings_max para int
    mask = agg['total_ratings_max'].notna()
    if mask.any():
        agg.loc[mask, 'total_ratings_max'] = agg.loc[mask, 'total_ratings_max'].astype(int)

    return agg


def validate_groups_vectorized(df, group_col):
    """Retorna (ids_ok, quarantine_rows) baseado nas validacoes."""

    # Validacao 1: tipo deve bater
    tipo_counts = df.groupby(group_col)['tipo'].nunique()
    bad_tipo_groups = set(tipo_counts[tipo_counts > 1].index)

    # Validacao 2: preco nao pode variar >10x
    df_preco = df[df['preco'].notna() & (df['preco'] > 0)]
    preco_agg = df_preco.groupby(group_col)['preco'].agg(['min', 'max', 'count'])
    preco_agg = preco_agg[preco_agg['count'] >= 2]
    bad_preco_groups = set(preco_agg[preco_agg['max'] / preco_agg['min'] > 10].index)

    # Validacao 3: grupos gigantes
    group_sizes = df.groupby(group_col)['id'].count()
    bad_size_groups = set(group_sizes[group_sizes > 100].index)

    bad_groups = bad_tipo_groups | bad_preco_groups | bad_size_groups
    good_groups = set(df[group_col].unique()) - bad_groups

    # Gerar quarantine rows para bad groups
    quarantine_rows = []
    if bad_groups:
        df_bad = df[df[group_col].isin(bad_groups)]
        for gid, group in df_bad.groupby(group_col):
            if len(group) < 2:
                continue
            ids = group['id'].tolist()
            nomes = group['nome_limpo'].tolist()
            motivo_parts = []
            if gid in bad_tipo_groups:
                motivo_parts.append("tipos_diferentes")
            if gid in bad_preco_groups:
                motivo_parts.append("preco_variacao_10x")
            if gid in bad_size_groups:
                motivo_parts.append("grupo_gigante")
            motivo = ",".join(motivo_parts)
            for i in range(min(len(ids) - 1, 5)):
                quarantine_rows.append((int(ids[0]), int(ids[i+1]), nomes[0], nomes[i+1], 1.0, motivo))

    return good_groups, quarantine_rows


# -- Main --

def main():
    t0 = time.time()
    log(f"=== DEDUP GRUPO {GROUP} -- Paises: {', '.join(p.upper() for p in PAISES)} ===\n")

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    # -- Criar tabelas de destino --
    log("[X3] Criando tabelas de destino...")
    cur.execute(f"DROP TABLE IF EXISTS {TABLE_UNIQUE} CASCADE;")
    cur.execute(f"DROP TABLE IF EXISTS {TABLE_QUARANTINE} CASCADE;")

    cur.execute(f"""
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
    """)

    cur.execute(f"""
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

    # -- Carregar dados --
    paises_str = ",".join(f"'{p}'" for p in PAISES)
    log(f"[X3] Carregando vinhos de wines_clean WHERE pais_tabela IN ({paises_str})...")

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
        WHERE pais_tabela IN ({paises_str})
    """
    df = pd.read_sql(query, conn)
    total_input = len(df)
    log(f"[X3] Carregados: {total_input:,} vinhos\n")

    if total_input == 0:
        log("[X3] Nenhum vinho encontrado. Saindo.")
        conn.close()
        return

    for pais in PAISES:
        count = len(df[df['pais_tabela'] == pais])
        log(f"  {pais.upper()}: {count:,} vinhos")
    log("")

    # -- NIVEL 1 -- Deterministico --
    log("=" * 60)
    log("NIVEL 1 -- Deterministico (100% certeza)")
    log("=" * 60)

    processed_ids = set()
    all_quarantine = []  # list of tuples (id_a, id_b, nome_a, nome_b, prob, motivo)

    # Build id->group_id mapping dict (simpler than DataFrame .loc assignment)
    id_to_det_group = {}
    next_group_id = 0

    # 1a. hash_dedup identico
    log("[X3] 1a. Agrupando por hash_dedup...")
    mask_hash = df['hash_dedup'].notna() & (df['hash_dedup'] != '')
    if mask_hash.any():
        df_hash = df[mask_hash].copy()
        hash_keys = df_hash['pais_tabela'] + '||' + df_hash['hash_dedup'].astype(str)
        hash_group_map = {k: i + next_group_id for i, k in enumerate(hash_keys.unique())}
        df_hash['_hg'] = hash_keys.map(hash_group_map)

        sizes = df_hash.groupby('_hg')['id'].transform('count')
        df_hash_multi = df_hash[sizes >= 2].copy()

        if len(df_hash_multi) > 0:
            good, quarantine = validate_groups_vectorized(df_hash_multi, '_hg')
            all_quarantine.extend(quarantine)

            df_good = df_hash_multi[df_hash_multi['_hg'].isin(good)]
            id_to_det_group.update(dict(zip(df_good['id'], df_good['_hg'])))
            processed_ids.update(df_good['id'].tolist())
            next_group_id += len(hash_group_map) + 1

            n_hash_groups_ok = len(good)
            n_hash_merged = len(df_good)
        else:
            n_hash_groups_ok = 0
            n_hash_merged = 0
    else:
        n_hash_groups_ok = 0
        n_hash_merged = 0

    log(f"  -> {n_hash_groups_ok:,} grupos por hash ({n_hash_merged:,} vinhos)")

    # 1b. ean_gtin identico
    log("[X3] 1b. Agrupando por ean_gtin...")
    mask_ean = (df['ean_gtin'].notna()) & (df['ean_gtin'] != '') & (~df['id'].isin(processed_ids))
    if mask_ean.any():
        df_ean = df[mask_ean].copy()
        ean_keys = df_ean['pais_tabela'] + '||' + df_ean['ean_gtin'].astype(str)
        ean_group_map = {k: i + next_group_id for i, k in enumerate(ean_keys.unique())}
        df_ean['_eg'] = ean_keys.map(ean_group_map)

        sizes = df_ean.groupby('_eg')['id'].transform('count')
        df_ean_multi = df_ean[sizes >= 2].copy()

        if len(df_ean_multi) > 0:
            good, quarantine = validate_groups_vectorized(df_ean_multi, '_eg')
            all_quarantine.extend(quarantine)

            df_good = df_ean_multi[df_ean_multi['_eg'].isin(good)]
            id_to_det_group.update(dict(zip(df_good['id'], df_good['_eg'])))
            processed_ids.update(df_good['id'].tolist())
            next_group_id += len(ean_group_map) + 1

            n_ean_groups_ok = len(good)
            n_ean_merged = len(df_good)
        else:
            n_ean_groups_ok = 0
            n_ean_merged = 0
    else:
        n_ean_groups_ok = 0
        n_ean_merged = 0

    log(f"  -> {n_ean_groups_ok:,} grupos por EAN ({n_ean_merged:,} vinhos)")

    # 1c. nome_normalizado + safra identicos
    log("[X3] 1c. Agrupando por nome_normalizado + safra...")
    mask_nome = ~df['id'].isin(processed_ids)
    df_nome = df[mask_nome].copy()
    df_nome['safra_key'] = df_nome['safra'].fillna(-1).astype(int).astype(str)
    nome_keys = df_nome['pais_tabela'] + '||' + df_nome['nome_normalizado'].fillna('') + '||' + df_nome['safra_key']
    nome_group_map = {k: i + next_group_id for i, k in enumerate(nome_keys.unique())}
    df_nome['_ng'] = nome_keys.map(nome_group_map)

    sizes = df_nome.groupby('_ng')['id'].transform('count')
    df_nome_multi = df_nome[sizes >= 2].copy()

    if len(df_nome_multi) > 0:
        good, quarantine = validate_groups_vectorized(df_nome_multi, '_ng')
        all_quarantine.extend(quarantine)

        df_good = df_nome_multi[df_nome_multi['_ng'].isin(good)]
        # Vectorized dict update via zip
        id_to_det_group.update(dict(zip(df_good['id'], df_good['_ng'])))
        processed_ids.update(df_good['id'].tolist())
        next_group_id += len(nome_group_map) + 1

        n_nome_groups_ok = len(good)
        n_nome_merged = len(df_good)
    else:
        n_nome_groups_ok = 0
        n_nome_merged = 0

    log(f"  -> {n_nome_groups_ok:,} grupos por nome+safra ({n_nome_merged:,} vinhos)")

    total_det_groups = n_hash_groups_ok + n_ean_groups_ok + n_nome_groups_ok
    total_det_merged = n_hash_merged + n_ean_merged + n_nome_merged
    log(f"\n  NIVEL 1 TOTAL: {total_det_groups:,} grupos ({total_det_merged:,} vinhos agrupados)")

    # -- Merge nivel 1 (vectorizado) --
    log("\n[X3] Merge vectorizado nivel 1...")
    df['det_group'] = df['id'].map(id_to_det_group).fillna(-1).astype(int)
    df_det = df[df['det_group'] >= 0].copy()
    if len(df_det) > 0:
        det_merged = vectorized_merge(df_det, 'det_group', 'deterministic', 1.0)
        log(f"  -> {len(det_merged):,} vinhos unicos do nivel 1")
    else:
        det_merged = pd.DataFrame()
        log("  -> 0 vinhos unicos do nivel 1")

    # -- NIVEL 2 -- Splink --
    log("\n" + "=" * 60)
    log("NIVEL 2 -- Probabilistico com Splink")
    log("=" * 60)

    df_remaining = df[~df['id'].isin(processed_ids)].copy()
    log(f"[X3] Vinhos restantes para nivel 2: {len(df_remaining):,}")

    splink_merged_dfs = []
    splink_groups = 0
    splink_merged_count = 0
    splink_quarantine = 0

    if len(df_remaining) >= 100:
        try:
            import splink.comparison_library as cl
            import splink.blocking_rule_library as brl
            from splink import DuckDBAPI, Linker, SettingsCreator, block_on

            for pais in PAISES:
                df_pais = df_remaining[df_remaining['pais_tabela'] == pais].copy()
                if len(df_pais) < 10:
                    log(f"  {pais.upper()}: {len(df_pais)} vinhos -- pulando (muito poucos)")
                    continue

                log(f"\n[X3] Splink para {pais.upper()}: {len(df_pais):,} vinhos...")

                df_splink = df_pais[['id', 'nome_normalizado', 'produtor_normalizado',
                                      'safra', 'tipo', 'pais_tabela', 'regiao', 'uvas']].copy()
                df_splink = df_splink.where(df_splink.notna(), None)

                training_block_nome = block_on("nome_normalizado")
                training_block_produtor = block_on("produtor_normalizado")

                prediction_blocking_rules = [
                    block_on("nome_normalizado"),
                    block_on("produtor_normalizado", "pais_tabela"),
                    brl.CustomRule(
                        "SUBSTR(l.nome_normalizado,1,10) = SUBSTR(r.nome_normalizado,1,10) "
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

                try:
                    db_api = DuckDBAPI()
                    linker = Linker(df_splink, settings, db_api)

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

                    if len(df_predictions) > 0:
                        # Quarentena (vectorizado)
                        df_review = df_predictions[
                            (df_predictions["match_probability"] >= REVIEW_THRESHOLD) &
                            (df_predictions["match_probability"] < MATCH_THRESHOLD)
                        ].copy()

                        if len(df_review) > 0:
                            if len(df_review) > 50000:
                                df_review = df_review.nlargest(50000, 'match_probability')

                            id_to_nome = df_pais.set_index('id')['nome_limpo'].to_dict()
                            id_l_col = 'id_l' if 'id_l' in df_review.columns else 'unique_id_l'
                            id_r_col = 'id_r' if 'id_r' in df_review.columns else 'unique_id_r'

                            q_tuples = list(zip(
                                df_review[id_l_col].astype(int),
                                df_review[id_r_col].astype(int),
                                df_review[id_l_col].astype(int).map(id_to_nome).fillna(''),
                                df_review[id_r_col].astype(int).map(id_to_nome).fillna(''),
                                df_review['match_probability'].astype(float),
                                ['splink_uncertain'] * len(df_review),
                            ))
                            all_quarantine.extend(q_tuples)
                            splink_quarantine += len(q_tuples)
                            log(f"  -> {pais.upper()}: {len(q_tuples):,} pares em quarentena")

                        # Clusterizar
                        clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
                            results, threshold_match_probability=MATCH_THRESHOLD,
                        )
                        df_clusters = clusters.as_pandas_dataframe()

                        if len(df_clusters) > 0:
                            cluster_col = 'cluster_id' if 'cluster_id' in df_clusters.columns else df_clusters.columns[-1]
                            id_col = 'id' if 'id' in df_clusters.columns else df_clusters.columns[0]

                            # Only multi-member clusters
                            sizes = df_clusters.groupby(cluster_col)[id_col].transform('count')
                            df_multi = df_clusters[sizes >= 2].copy()

                            if len(df_multi) > 0:
                                # Merge cluster info back to df_pais
                                cluster_map = df_multi.set_index(id_col)[cluster_col].to_dict()
                                df_pais_clustered = df_pais[df_pais['id'].isin(cluster_map.keys())].copy()
                                df_pais_clustered['splink_cluster'] = df_pais_clustered['id'].map(cluster_map)

                                # Validate clusters vectorized
                                good, quarantine = validate_groups_vectorized(df_pais_clustered, 'splink_cluster')
                                all_quarantine.extend(quarantine)

                                df_good = df_pais_clustered[df_pais_clustered['splink_cluster'].isin(good)]
                                if len(df_good) > 0:
                                    splink_m = vectorized_merge(df_good, 'splink_cluster', 'splink_high', MATCH_THRESHOLD)
                                    splink_merged_dfs.append(splink_m)
                                    n_multi = len(splink_m)
                                    n_wines = len(df_good)
                                    processed_ids.update(df_good['id'].tolist())
                                    splink_groups += n_multi
                                    splink_merged_count += n_wines
                                    log(f"  -> {pais.upper()}: {n_multi:,} clusters Splink ({n_wines:,} vinhos)")

                except Exception as e:
                    log(f"  [WARN] Splink falhou para {pais.upper()}: {e}")
                    import traceback
                    traceback.print_exc()

        except ImportError:
            log("[WARN] Splink nao instalado. Pulando nivel 2.")
            log("  Para instalar: pip install splink[duckdb]")
    else:
        log(f"  Poucos vinhos restantes ({len(df_remaining):,}). Pulando nivel 2.")

    log(f"\n  NIVEL 2 TOTAL: {splink_groups:,} grupos ({splink_merged_count:,} vinhos agrupados)")

    # -- Singletons (vectorizado) --
    log("\n[X3] Adicionando singletons (sem match)...")
    df_singletons = df[~df['id'].isin(processed_ids)].copy()
    n_singletons = len(df_singletons)

    if n_singletons > 0:
        sing = pd.DataFrame({
            'nome_limpo': df_singletons['nome_limpo'].values,
            'nome_normalizado': df_singletons['nome_normalizado'].values,
            'produtor': df_singletons['produtor_extraido'].values,
            'produtor_normalizado': df_singletons['produtor_normalizado'].values,
            'safra': df_singletons['safra'].values,
            'tipo': df_singletons['tipo'].values,
            'pais': df_singletons['pais'].values,
            'pais_tabela': df_singletons['pais_tabela'].values,
            'regiao': df_singletons['regiao'].values,
            'sub_regiao': df_singletons['sub_regiao'].values,
            'uvas': df_singletons['uvas'].values,
            'rating_melhor': df_singletons['rating'].values,
            'total_ratings_max': df_singletons['total_ratings'].values,
            'preco_min_global': df_singletons['preco'].where(df_singletons['preco'] > 0, np.nan).values,
            'preco_max_global': df_singletons['preco'].where(df_singletons['preco'] > 0, np.nan).values,
            'moeda_referencia': df_singletons['moeda'].values,
            'url_imagem': df_singletons['url_imagem'].values,
            'hash_dedup': df_singletons['hash_dedup'].values,
            'ean_gtin': df_singletons['ean_gtin'].values,
            'match_type': 'singleton',
            'match_probability': np.nan,
            'total_copias': 1,
            'clean_ids': [[int(x)] for x in df_singletons['id'].values],
        })
        sing['total_ratings_max'] = sing['total_ratings_max'].apply(
            lambda x: int(x) if pd.notna(x) else None
        )
        sing = sing.where(sing.notna(), None)
    else:
        sing = pd.DataFrame()

    log(f"  -> {n_singletons:,} singletons")

    # -- Concatenar tudo --
    all_dfs = []
    if len(det_merged) > 0:
        all_dfs.append(det_merged)
    for sm in splink_merged_dfs:
        if len(sm) > 0:
            all_dfs.append(sm)
    if len(sing) > 0:
        all_dfs.append(sing)

    cols = [
        'nome_limpo', 'nome_normalizado', 'produtor', 'produtor_normalizado',
        'safra', 'tipo', 'pais', 'pais_tabela', 'regiao', 'sub_regiao', 'uvas',
        'rating_melhor', 'total_ratings_max', 'preco_min_global', 'preco_max_global',
        'moeda_referencia', 'url_imagem', 'hash_dedup', 'ean_gtin',
        'match_type', 'match_probability', 'total_copias', 'clean_ids'
    ]

    if all_dfs:
        df_all = pd.concat(all_dfs, ignore_index=True)
        # Ensure column order
        for c in cols:
            if c not in df_all.columns:
                df_all[c] = None
        df_all = df_all[cols]
    else:
        df_all = pd.DataFrame(columns=cols)

    # -- INSERT wines_unique --
    log(f"\n[X3] Inserindo {len(df_all):,} registros em {TABLE_UNIQUE}...")

    insert_sql = f"""
        INSERT INTO {TABLE_UNIQUE} ({', '.join(cols)})
        VALUES %s
    """

    def row_to_tuple(row):
        vals = []
        for c in cols:
            v = row[c]
            if isinstance(v, float) and np.isnan(v):
                v = None
            elif c == 'clean_ids' and v is None:
                v = []
            vals.append(v)
        return tuple(vals)

    for i in range(0, len(df_all), BATCH_SIZE):
        batch = df_all.iloc[i:i+BATCH_SIZE]
        values = [row_to_tuple(row) for _, row in batch.iterrows()]
        execute_values(cur, insert_sql, values, page_size=BATCH_SIZE)
        conn.commit()
        if (i // BATCH_SIZE) % 20 == 0 or i + BATCH_SIZE >= len(df_all):
            log(f"  ... {min(i + BATCH_SIZE, len(df_all)):,}/{len(df_all):,}")

    # -- INSERT quarantine --
    if all_quarantine:
        log(f"\n[X3] Inserindo {len(all_quarantine):,} registros em {TABLE_QUARANTINE}...")
        q_sql = f"""
            INSERT INTO {TABLE_QUARANTINE} (clean_id_a, clean_id_b, nome_a, nome_b, match_probability, motivo)
            VALUES %s
        """
        for i in range(0, len(all_quarantine), BATCH_SIZE):
            batch = all_quarantine[i:i+BATCH_SIZE]
            execute_values(cur, q_sql, batch, page_size=BATCH_SIZE)
            conn.commit()
        log(f"  Inseridos {len(all_quarantine):,} registros de quarentena")
    else:
        log(f"\n[X3] Nenhum registro de quarentena.")

    # -- Verificacoes --
    log("\n[X3] Verificando...")
    cur.execute(f"SELECT COUNT(*) FROM {TABLE_UNIQUE};")
    total_unique = cur.fetchone()[0]

    cur.execute(f"SELECT match_type, COUNT(*) FROM {TABLE_UNIQUE} GROUP BY match_type ORDER BY COUNT(*) DESC;")
    match_types = cur.fetchall()

    cur.execute(f"""
        SELECT total_copias, COUNT(*)
        FROM {TABLE_UNIQUE}
        GROUP BY total_copias
        ORDER BY total_copias DESC
        LIMIT 10;
    """)
    copias_dist = cur.fetchall()

    cur.execute(f"SELECT COUNT(*) FROM {TABLE_QUARANTINE};")
    total_quarantine = cur.fetchone()[0]

    # -- Exemplos --
    log("\n" + "=" * 60)
    log("EXEMPLOS -- Merges Nivel 1 (deterministico)")
    log("=" * 60)
    cur.execute(f"""
        SELECT nome_limpo, produtor, safra, tipo, pais_tabela, total_copias, clean_ids
        FROM {TABLE_UNIQUE}
        WHERE match_type = 'deterministic' AND total_copias > 1
        ORDER BY total_copias DESC
        LIMIT 10;
    """)
    for row in cur.fetchall():
        nome, produtor, safra, tipo, pais, copias, ids = row
        log(f"  [{pais.upper()}] {nome} | {produtor or '?'} | {safra or '?'} | {tipo or '?'} | {copias} copias | IDs: {ids[:5]}{'...' if len(ids) > 5 else ''}")

    log("\n" + "=" * 60)
    log("EXEMPLOS -- Merges Nivel 2 (Splink)")
    log("=" * 60)
    cur.execute(f"""
        SELECT nome_limpo, produtor, safra, tipo, pais_tabela, total_copias, match_probability, clean_ids
        FROM {TABLE_UNIQUE}
        WHERE match_type = 'splink_high' AND total_copias > 1
        ORDER BY total_copias DESC
        LIMIT 10;
    """)
    splink_examples = cur.fetchall()
    if splink_examples:
        for row in splink_examples:
            nome, produtor, safra, tipo, pais, copias, prob, ids = row
            log(f"  [{pais.upper()}] {nome} | {produtor or '?'} | {safra or '?'} | prob={prob:.2f} | {copias} copias")
    else:
        log("  (nenhum merge Splink neste grupo)")

    # -- Relatorio final --
    elapsed = time.time() - t0

    log("\n" + "=" * 60)
    log(f"=== GRUPO {GROUP} CONCLUIDO ===")
    log("=" * 60)
    log(f"Paises: {', '.join(p.upper() for p in PAISES)}")
    log(f"Input: {total_input:,} vinhos de wines_clean")
    log(f"Nivel 1 (deterministico): {total_det_groups:,} grupos")
    log(f"Nivel 2 (Splink): {splink_groups:,} grupos adicionais")
    log(f"Nivel 3 (quarentena): {total_quarantine:,} pares incertos")
    log(f"Output: {total_unique:,} vinhos unicos em {TABLE_UNIQUE}")
    if total_input > 0:
        taxa = (1 - total_unique / total_input) * 100
        log(f"Taxa de dedup: {taxa:.1f}% (de {total_input:,} para {total_unique:,})")
    log(f"\nDistribuicao por match_type:")
    for mt, cnt in match_types:
        log(f"  {mt}: {cnt:,}")
    log(f"\nDistribuicao por total_copias (top 10):")
    for copias, cnt in copias_dist:
        log(f"  {copias} copias: {cnt:,} vinhos")
    log(f"\nTempo total: {elapsed:.1f}s")

    conn.close()
    log("\n[X3] Done!")


if __name__ == "__main__":
    main()
