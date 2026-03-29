"""
DEDUP GROUP 4 — DE, NL, DK
Deduplicacao de vinhos em 3 niveis: deterministico + Splink + quarentena.
Origem: wines_clean | Destino: wines_unique_g4 + dedup_quarantine_g4
"""

import sys
import os
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)
import time
import psycopg2
import psycopg2.extras
import pandas as pd
import numpy as np
from collections import Counter

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
PAISES = ('de', 'nl', 'dk')
BATCH_SIZE = 5000
GROUP_TAG = "X4"


# ── Helpers ──

def build_merged_df(df, group_col):
    """
    Agrupa df por group_col, merge campos.
    Usa APENAS agg nativas do pandas — sem apply(list).
    """
    print(f"[{GROUP_TAG}]   build_merged_df: {len(df):,} rows, {df[group_col].nunique():,} groups")
    t = time.time()

    g = df.groupby(group_col, sort=False)

    # clean_ids e total_copias via dict — MUITO mais rapido que apply(list)
    ids_dict = {}
    for row_id, grp_id in zip(df['id'], df[group_col]):
        ids_dict.setdefault(grp_id, []).append(int(row_id))

    # Agg rapidas nativas para tudo de uma vez
    agg_spec = {'id': 'count'}

    # first (pula NaN nativo)
    first_cols = ['nome_normalizado', 'pais_tabela']
    for col in ['produtor_extraido', 'produtor_normalizado', 'safra', 'pais',
                'regiao', 'sub_regiao', 'uvas', 'url_imagem',
                'hash_dedup', 'ean_gtin', 'tipo', 'moeda']:
        if col in df.columns:
            first_cols.append(col)

    for col in first_cols:
        agg_spec[col] = 'first'

    # Numericos: max
    if 'rating' in df.columns:
        agg_spec['rating'] = 'max'
    if 'total_ratings' in df.columns:
        agg_spec['total_ratings'] = 'max'

    result = g.agg(agg_spec)
    result.columns = [c if c != 'id' else 'total_copias' for c in result.columns]

    # nome_limpo: o mais longo — via idxmax
    df_temp = df[[group_col, 'nome_limpo']].copy()
    df_temp['_len'] = df_temp['nome_limpo'].str.len().fillna(0)
    idx_max = df_temp.groupby(group_col, sort=False)['_len'].idxmax()
    result['nome_limpo'] = df.loc[idx_max.values, 'nome_limpo'].values

    # Preco min/max (so positivos)
    df_preco = df[[group_col, 'preco']].copy()
    df_preco.loc[df_preco['preco'] <= 0, 'preco'] = np.nan
    gp = df_preco.groupby(group_col, sort=False)['preco']
    result['preco_min_global'] = gp.min().values
    result['preco_max_global'] = gp.max().values

    # clean_ids do dict
    result['clean_ids'] = [sorted(ids_dict.get(gid, [])) for gid in result.index]

    # Rename
    result.rename(columns={
        'produtor_extraido': 'produtor',
        'moeda': 'moeda_referencia',
        'rating': 'rating_melhor',
        'total_ratings': 'total_ratings_max',
    }, inplace=True)

    result.reset_index(drop=True, inplace=True)
    print(f"[{GROUP_TAG}]   build_merged_df concluido em {time.time()-t:.1f}s")
    return result


# ── Nivel 1: Deterministico (vetorizado) ──

def nivel_1_deterministico(df):
    """Agrupa vinhos com certeza 100%. Retorna (df_merged, df_remaining, quarantine_records)."""
    t = time.time()
    print(f"[{GROUP_TAG}] Nivel 1: {len(df):,} vinhos para processar")

    # Atribuir grupo a cada vinho. -1 = sem grupo ainda
    df = df.copy()
    df['_group'] = -1
    next_group = 0
    quarantine = []

    # 1a. hash_dedup identico (nao NULL, nao vazio)
    mask_hash = df['hash_dedup'].notna() & (df['hash_dedup'] != '')
    df_hash = df[mask_hash].copy()
    if len(df_hash) > 0:
        # Criar chave de grupo
        df_hash['_key'] = df_hash['pais_tabela'] + '||' + df_hash['hash_dedup']
        # Contar membros por grupo
        counts = df_hash.groupby('_key')['id'].transform('count')
        # So manter grupos com 2+ membros
        df_hash_multi = df_hash[counts >= 2]
        if len(df_hash_multi) > 0:
            # Atribuir IDs de grupo sequenciais
            keys = df_hash_multi['_key']
            unique_keys = keys.unique()
            key_to_group = {k: i for i, k in enumerate(unique_keys)}
            group_ids = keys.map(key_to_group)
            df.loc[df_hash_multi.index, '_group'] = group_ids.values
            next_group = len(unique_keys)

    n_hash_groups = df[df['_group'] >= 0]['_group'].nunique()
    n_hash_wines = (df['_group'] >= 0).sum()
    print(f"[{GROUP_TAG}]   1a. hash_dedup: {n_hash_groups:,} grupos ({n_hash_wines:,} vinhos)")

    # 1b. ean_gtin identico (ainda nao agrupados)
    mask_unmatched = df['_group'] == -1
    mask_ean = mask_unmatched & df['ean_gtin'].notna() & (df['ean_gtin'] != '')
    df_ean = df[mask_ean].copy()
    if len(df_ean) > 0:
        df_ean['_key'] = df_ean['pais_tabela'] + '||' + df_ean['ean_gtin']
        counts = df_ean.groupby('_key')['id'].transform('count')
        df_ean_multi = df_ean[counts >= 2]
        if len(df_ean_multi) > 0:
            keys = df_ean_multi['_key']
            unique_keys = keys.unique()
            key_to_group = {k: i + next_group for i, k in enumerate(unique_keys)}
            group_ids = keys.map(key_to_group)
            df.loc[df_ean_multi.index, '_group'] = group_ids.values
            next_group += len(unique_keys)

    n_ean_groups = df[(df['_group'] >= 0)]['_group'].nunique() - n_hash_groups
    print(f"[{GROUP_TAG}]   1b. ean_gtin: {n_ean_groups:,} grupos adicionais")

    # 1c. nome_normalizado + safra identicos
    mask_unmatched = df['_group'] == -1
    df_remaining = df[mask_unmatched].copy()

    # Com safra
    df_with_safra = df_remaining[df_remaining['safra'].notna()].copy()
    if len(df_with_safra) > 0:
        df_with_safra['_key'] = (df_with_safra['pais_tabela'] + '||' +
                                  df_with_safra['nome_normalizado'] + '||' +
                                  df_with_safra['safra'].astype(int).astype(str))
        counts = df_with_safra.groupby('_key')['id'].transform('count')
        df_ws_multi = df_with_safra[counts >= 2]
        if len(df_ws_multi) > 0:
            keys = df_ws_multi['_key']
            unique_keys = keys.unique()
            key_to_group = {k: i + next_group for i, k in enumerate(unique_keys)}
            group_ids = keys.map(key_to_group)
            df.loc[df_ws_multi.index, '_group'] = group_ids.values
            next_group += len(unique_keys)

    # Sem safra
    mask_unmatched = df['_group'] == -1
    df_no_safra = df[mask_unmatched & df['safra'].isna()].copy()
    if len(df_no_safra) > 0:
        df_no_safra['_key'] = df_no_safra['pais_tabela'] + '||' + df_no_safra['nome_normalizado']
        counts = df_no_safra.groupby('_key')['id'].transform('count')
        df_ns_multi = df_no_safra[counts >= 2]
        if len(df_ns_multi) > 0:
            keys = df_ns_multi['_key']
            unique_keys = keys.unique()
            key_to_group = {k: i + next_group for i, k in enumerate(unique_keys)}
            group_ids = keys.map(key_to_group)
            df.loc[df_ns_multi.index, '_group'] = group_ids.values
            next_group += len(unique_keys)

    total_groups = df[df['_group'] >= 0]['_group'].nunique()
    total_grouped = (df['_group'] >= 0).sum()
    n_nome_groups = total_groups - n_hash_groups - n_ean_groups
    print(f"[{GROUP_TAG}]   1c. nome+safra: {n_nome_groups:,} grupos adicionais")

    # ── Validacoes de seguranca (vetorizado) ──
    print(f"[{GROUP_TAG}]   Validando {total_groups:,} grupos...")

    df_grouped = df[df['_group'] >= 0].copy()
    df_ungrouped = df[df['_group'] == -1].copy()

    if len(df_grouped) > 0:
        # Checar tipos mistos por grupo
        tipo_nunique = df_grouped.groupby('_group')['tipo'].nunique(dropna=True)
        bad_tipo_groups = tipo_nunique[tipo_nunique > 1].index

        if len(bad_tipo_groups) > 0:
            print(f"[{GROUP_TAG}]   {len(bad_tipo_groups):,} grupos com tipos mistos — separando")
            mask_bad = df_grouped['_group'].isin(bad_tipo_groups)
            df_bad = df_grouped[mask_bad].copy()
            df_grouped = df_grouped[~mask_bad].copy()

            # Re-agrupar por grupo + tipo
            df_bad['_key2'] = df_bad['_group'].astype(str) + '||' + df_bad['tipo'].fillna('none')
            counts2 = df_bad.groupby('_key2')['id'].transform('count')
            df_bad_multi = df_bad[counts2 >= 2].copy()
            df_bad_single = df_bad[counts2 < 2].copy()

            if len(df_bad_multi) > 0:
                unique_keys2 = df_bad_multi['_key2'].unique()
                key_to_group2 = {k: i + next_group for i, k in enumerate(unique_keys2)}
                df_bad_multi['_group'] = df_bad_multi['_key2'].map(key_to_group2)
                next_group += len(unique_keys2)
                df_grouped = pd.concat([df_grouped, df_bad_multi[df_grouped.columns]], ignore_index=True)

            if len(df_bad_single) > 0:
                df_bad_single['_group'] = -1
                df_ungrouped = pd.concat([df_ungrouped, df_bad_single[df_ungrouped.columns]], ignore_index=True)

        # Checar variacao de preco >10x
        df_gp = df_grouped.copy()
        df_gp.loc[df_gp['preco'] <= 0, 'preco'] = np.nan
        preco_stats = df_gp.groupby('_group')['preco'].agg(['min', 'max'])
        preco_stats = preco_stats.dropna()
        if len(preco_stats) > 0:
            preco_stats['ratio'] = preco_stats['max'] / preco_stats['min'].replace(0, np.nan)
            bad_preco_groups = preco_stats[preco_stats['ratio'] > 10].index
            if len(bad_preco_groups) > 0:
                print(f"[{GROUP_TAG}]   {len(bad_preco_groups):,} grupos com preco >10x — quarentena")
                mask_bad_p = df_grouped['_group'].isin(bad_preco_groups)
                df_quarantine_p = df_grouped[mask_bad_p]
                # Registrar em quarentena
                for gid, grp in df_quarantine_p.groupby('_group'):
                    if len(grp) >= 2:
                        quarantine.append({
                            'clean_id_a': int(grp.iloc[0]['id']),
                            'clean_id_b': int(grp.iloc[1]['id']),
                            'nome_a': grp.iloc[0]['nome_limpo'],
                            'nome_b': grp.iloc[1]['nome_limpo'],
                            'match_probability': 1.0,
                            'motivo': f"preco_10x: min={preco_stats.loc[gid, 'min']:.2f} max={preco_stats.loc[gid, 'max']:.2f}",
                        })
                df_grouped = df_grouped[~mask_bad_p]
                df_ungrouped = pd.concat([df_ungrouped, df_quarantine_p], ignore_index=True)
                df_ungrouped.loc[df_ungrouped.index[-len(df_quarantine_p):], '_group'] = -1

        # Checar grupos >100
        group_sizes = df_grouped.groupby('_group')['id'].transform('count')
        mask_giant = group_sizes > 100
        if mask_giant.any():
            # Verificar se nomes sao muito genericos
            df_giant = df_grouped[mask_giant]
            giant_groups = df_giant['_group'].unique()
            for gid in giant_groups:
                grp = df_giant[df_giant['_group'] == gid]
                avg_len = grp['nome_normalizado'].str.len().mean()
                if avg_len < 10:
                    quarantine.append({
                        'clean_id_a': int(grp.iloc[0]['id']),
                        'clean_id_b': int(grp.iloc[1]['id']),
                        'nome_a': grp.iloc[0]['nome_limpo'],
                        'nome_b': grp.iloc[1]['nome_limpo'],
                        'match_probability': 1.0,
                        'motivo': f"grupo_gigante_generico: {len(grp)} copias, nome medio {avg_len:.0f} chars",
                    })
                    df_grouped = df_grouped[df_grouped['_group'] != gid]

    # Construir merges via groupby vetorizado
    final_groups = df_grouped[df_grouped['_group'] >= 0]['_group'].nunique() if len(df_grouped) > 0 else 0
    final_grouped_wines = len(df_grouped[df_grouped['_group'] >= 0]) if len(df_grouped) > 0 else 0

    print(f"[{GROUP_TAG}] Nivel 1 validado: {final_groups:,} grupos, {final_grouped_wines:,} vinhos")

    # Merge via vectorized groupby
    if len(df_grouped) > 0 and final_groups > 0:
        df_merged = build_merged_df(df_grouped, '_group')
    else:
        df_merged = pd.DataFrame()

    df_left = df_ungrouped.drop(columns=['_group'], errors='ignore')
    # Tambem adicionar singletons do agrupamento original
    singletons_from_groups = df[df['_group'] == -1].drop(columns=['_group'], errors='ignore')
    # df_left ja contem esses — garantir que nao duplica
    all_left_ids = set(df_left['id'].tolist()) | set(singletons_from_groups['id'].tolist())
    df_left = df[df['id'].isin(all_left_ids)].drop(columns=['_group'], errors='ignore')

    print(f"[{GROUP_TAG}] Nivel 1 concluido em {time.time()-t:.1f}s")
    print(f"[{GROUP_TAG}] Restantes para nivel 2: {len(df_left):,} vinhos")

    return df_merged, df_left, quarantine


# ── Nivel 2: Splink ──

def nivel_2_splink(df_remaining, pais_tabela_label="all"):
    """Dedup probabilistico com Splink."""
    import splink.comparison_library as cl
    import splink.blocking_rule_library as brl
    from splink import DuckDBAPI, Linker, SettingsCreator, block_on

    if len(df_remaining) < 100:
        print(f"[{GROUP_TAG}] Nivel 2: poucos vinhos ({len(df_remaining)}), pulando Splink para {pais_tabela_label}")
        return pd.DataFrame(columns=["id", "cluster_id"]), pd.DataFrame()

    print(f"[{GROUP_TAG}] Nivel 2: {len(df_remaining):,} vinhos restantes para Splink ({pais_tabela_label})")

    df_splink = df_remaining[['id', 'nome_normalizado', 'produtor_normalizado',
                               'safra', 'tipo', 'pais_tabela', 'regiao', 'uvas']].copy()

    # nome_normalizado e pais_tabela sempre devem ter valor (sao chave)
    # Outros campos: manter None para que Splink ignore em blocking
    df_splink['nome_normalizado'] = df_splink['nome_normalizado'].fillna('')
    df_splink['pais_tabela'] = df_splink['pais_tabela'].fillna('')
    # NAO preencher produtor_normalizado com '' — senao Splink bloca todos sem produtor juntos
    df_splink['safra'] = df_splink['safra'].where(df_splink['safra'].notna(), None)

    training_block_nome = block_on("nome_normalizado")
    # Treinar produtor apenas quando ambos tem valor (nao NULL)
    training_block_produtor = brl.CustomRule(
        "l.produtor_normalizado = r.produtor_normalizado "
        "AND l.produtor_normalizado IS NOT NULL "
        "AND l.produtor_normalizado != ''"
    )

    prediction_blocking_rules = [
        block_on("nome_normalizado"),
        brl.CustomRule(
            "l.produtor_normalizado = r.produtor_normalizado "
            "AND l.pais_tabela = r.pais_tabela "
            "AND l.produtor_normalizado IS NOT NULL "
            "AND l.produtor_normalizado != ''"
        ),
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

    match_threshold = 0.80
    review_threshold = 0.50

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

        results = linker.inference.predict(threshold_match_probability=review_threshold)
        df_predictions = results.as_pandas_dataframe()

        if len(df_predictions) == 0:
            print(f"[{GROUP_TAG}]   Splink: nenhum par encontrado para {pais_tabela_label}")
            return pd.DataFrame(columns=["id", "cluster_id"]), pd.DataFrame()

        # Pares para quarentena
        prob_col = 'match_probability' if 'match_probability' in df_predictions.columns else 'match_weight'
        id_l_col = [c for c in df_predictions.columns if c.startswith('id') and ('_l' in c or c == 'id_l')]
        id_r_col = [c for c in df_predictions.columns if c.startswith('id') and ('_r' in c or c == 'id_r')]

        if id_l_col and id_r_col:
            id_l_col = id_l_col[0]
            id_r_col = id_r_col[0]
        else:
            print(f"[{GROUP_TAG}]   Colunas Splink: {df_predictions.columns.tolist()}")
            id_l_col = 'id_l'
            id_r_col = 'id_r'

        df_review = df_predictions[
            (df_predictions[prob_col] >= review_threshold) &
            (df_predictions[prob_col] < match_threshold)
        ][[id_l_col, id_r_col, prob_col]].copy()
        df_review.columns = ['id_l', 'id_r', 'match_probability']

        clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
            results, threshold_match_probability=match_threshold,
        )
        df_clusters = clusters.as_pandas_dataframe()

        print(f"[{GROUP_TAG}]   Splink {pais_tabela_label}: {df_clusters['cluster_id'].nunique() if 'cluster_id' in df_clusters.columns else 0} clusters, "
              f"{len(df_review)} pares quarentena")

        return df_clusters, df_review

    except Exception as e:
        print(f"[{GROUP_TAG}]   ERRO Splink ({pais_tabela_label}): {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame(columns=["id", "cluster_id"]), pd.DataFrame()


# ── Insert em batch ──

def insert_unique_wines(conn, df_wines, match_type, match_probability=None):
    """Insere DataFrame de vinhos unicos em wines_unique_g4."""
    if df_wines is None or len(df_wines) == 0:
        return 0

    cur = conn.cursor()
    count = 0

    cols = ['nome_limpo', 'nome_normalizado', 'produtor', 'produtor_normalizado',
            'safra', 'tipo', 'pais', 'pais_tabela', 'regiao', 'sub_regiao', 'uvas',
            'rating_melhor', 'total_ratings_max', 'preco_min_global', 'preco_max_global',
            'moeda_referencia', 'url_imagem', 'hash_dedup', 'ean_gtin',
            'total_copias', 'clean_ids']

    for i in range(0, len(df_wines), BATCH_SIZE):
        batch = df_wines.iloc[i:i+BATCH_SIZE]
        values = []
        for _, row in batch.iterrows():
            safra_val = int(row['safra']) if pd.notna(row.get('safra')) else None
            tr_val = int(row['total_ratings_max']) if pd.notna(row.get('total_ratings_max')) else None
            rating_val = float(row['rating_melhor']) if pd.notna(row.get('rating_melhor')) else None
            pmin = float(row['preco_min_global']) if pd.notna(row.get('preco_min_global')) else None
            pmax = float(row['preco_max_global']) if pd.notna(row.get('preco_max_global')) else None
            clean_ids = row['clean_ids'] if isinstance(row.get('clean_ids'), list) else [int(row.get('clean_ids', 0))]

            values.append((
                row.get('nome_limpo'), row.get('nome_normalizado'),
                row.get('produtor'), row.get('produtor_normalizado'),
                safra_val, row.get('tipo'),
                row.get('pais'), row.get('pais_tabela'),
                row.get('regiao'), row.get('sub_regiao'), row.get('uvas'),
                rating_val, tr_val, pmin, pmax,
                row.get('moeda_referencia'), row.get('url_imagem'),
                row.get('hash_dedup'), row.get('ean_gtin'),
                match_type,
                match_probability if match_probability else 1.0,
                int(row.get('total_copias', 1)),
                clean_ids,
            ))

        psycopg2.extras.execute_batch(cur, """
            INSERT INTO wines_unique_g4
            (nome_limpo, nome_normalizado, produtor, produtor_normalizado,
             safra, tipo, pais, pais_tabela, regiao, sub_regiao, uvas,
             rating_melhor, total_ratings_max, preco_min_global, preco_max_global,
             moeda_referencia, url_imagem, hash_dedup, ean_gtin,
             match_type, match_probability, total_copias, clean_ids)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, values, page_size=BATCH_SIZE)
        count += len(batch)

    conn.commit()
    return count


def insert_singletons(conn, df_left, match_type='singleton'):
    """Insere vinhos que nao foram agrupados como singletons."""
    if df_left is None or len(df_left) == 0:
        return 0

    cur = conn.cursor()
    count = 0

    for i in range(0, len(df_left), BATCH_SIZE):
        batch = df_left.iloc[i:i+BATCH_SIZE]
        values = []
        for _, row in batch.iterrows():
            safra_val = int(row['safra']) if pd.notna(row.get('safra')) else None
            tr_val = int(row['total_ratings']) if pd.notna(row.get('total_ratings')) else None
            rating_val = float(row['rating']) if pd.notna(row.get('rating')) else None
            preco = row.get('preco')
            pmin = float(preco) if pd.notna(preco) and preco and preco > 0 else None
            pmax = pmin

            values.append((
                row.get('nome_limpo'), row.get('nome_normalizado'),
                row.get('produtor_extraido'), row.get('produtor_normalizado'),
                safra_val, row.get('tipo'),
                row.get('pais'), row.get('pais_tabela'),
                row.get('regiao'), row.get('sub_regiao'), row.get('uvas'),
                rating_val, tr_val, pmin, pmax,
                row.get('moeda'), row.get('url_imagem'),
                row.get('hash_dedup'), row.get('ean_gtin'),
                match_type, None,
                1, [int(row['id'])],
            ))

        psycopg2.extras.execute_batch(cur, """
            INSERT INTO wines_unique_g4
            (nome_limpo, nome_normalizado, produtor, produtor_normalizado,
             safra, tipo, pais, pais_tabela, regiao, sub_regiao, uvas,
             rating_melhor, total_ratings_max, preco_min_global, preco_max_global,
             moeda_referencia, url_imagem, hash_dedup, ean_gtin,
             match_type, match_probability, total_copias, clean_ids)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, values, page_size=BATCH_SIZE)
        count += len(batch)

    conn.commit()
    return count


def insert_quarantine(conn, records):
    """Insere pares incertos em dedup_quarantine_g4."""
    if not records:
        return 0

    cur = conn.cursor()
    values = [(r['clean_id_a'], r['clean_id_b'], r.get('nome_a', ''),
               r.get('nome_b', ''), r.get('match_probability', 0.0),
               r.get('motivo', '')) for r in records]

    psycopg2.extras.execute_batch(cur, """
        INSERT INTO dedup_quarantine_g4
        (clean_id_a, clean_id_b, nome_a, nome_b, match_probability, motivo)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, values, page_size=BATCH_SIZE)
    conn.commit()
    return len(values)


# ── Main ──

def main():
    t0 = time.time()
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # Criar tabelas de destino
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wines_unique_g4 (
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dedup_quarantine_g4 (
            id SERIAL PRIMARY KEY,
            clean_id_a INTEGER NOT NULL,
            clean_id_b INTEGER NOT NULL,
            nome_a TEXT,
            nome_b TEXT,
            match_probability REAL,
            motivo TEXT
        );
    """)
    cur.execute("TRUNCATE wines_unique_g4 RESTART IDENTITY CASCADE;")
    cur.execute("TRUNCATE dedup_quarantine_g4 RESTART IDENTITY CASCADE;")
    conn.commit()

    # Carregar dados
    paises_str = ','.join(f"'{p}'" for p in PAISES)
    print(f"[{GROUP_TAG}] Carregando vinhos de wines_clean para paises: {', '.join(PAISES)}")

    df = pd.read_sql(f"""
        SELECT id, pais_tabela, id_original, nome_limpo, nome_normalizado,
               produtor_extraido, produtor_normalizado, safra, tipo, pais,
               regiao, sub_regiao, uvas, rating, total_ratings,
               preco, moeda, preco_min, preco_max, url_imagem,
               hash_dedup, ean_gtin, fontes, total_fontes
        FROM wines_clean
        WHERE pais_tabela IN ({paises_str})
    """, conn)

    total_input = len(df)
    print(f"[{GROUP_TAG}] Total carregado: {total_input:,} vinhos")

    for pt in PAISES:
        n = len(df[df['pais_tabela'] == pt])
        print(f"[{GROUP_TAG}]   {pt.upper()}: {n:,} vinhos")

    # ── NIVEL 1 ──
    df_merged_n1, df_remaining, quarantine_n1 = nivel_1_deterministico(df)
    n1_groups = len(df_merged_n1) if df_merged_n1 is not None and len(df_merged_n1) > 0 else 0

    # ── NIVEL 2 — Splink ──
    t2 = time.time()
    all_splink_clusters = pd.DataFrame(columns=["id", "cluster_id"])
    all_splink_review = pd.DataFrame()
    wines_n2 = pd.DataFrame()
    n2_groups = 0

    if len(df_remaining) >= 100:
        for pt in PAISES:
            df_pt = df_remaining[df_remaining['pais_tabela'] == pt].copy()
            if len(df_pt) < 100:
                print(f"[{GROUP_TAG}]   {pt.upper()}: {len(df_pt)} vinhos — poucos, pulando Splink")
                continue

            df_clusters, df_review = nivel_2_splink(df_pt, pais_tabela_label=pt.upper())

            if len(df_clusters) > 0:
                all_splink_clusters = pd.concat([all_splink_clusters, df_clusters], ignore_index=True)
            if len(df_review) > 0:
                all_splink_review = pd.concat([all_splink_review, df_review], ignore_index=True)

    # Processar clusters Splink
    splink_processed_ids = set()

    if len(all_splink_clusters) > 0 and 'cluster_id' in all_splink_clusters.columns:
        print(f"[{GROUP_TAG}]   Splink clusters columns: {all_splink_clusters.columns.tolist()}")
        # Pegar so id e cluster_id do Splink
        cluster_map = all_splink_clusters[['id', 'cluster_id']].copy()
        # Filtrar clusters com 2+ membros
        cluster_sizes = cluster_map.groupby('cluster_id')['id'].transform('count')
        multi_clusters = cluster_map[cluster_sizes >= 2].copy()

        if len(multi_clusters) > 0:
            # Merge com dados originais do df_remaining
            multi_clusters_with_data = multi_clusters[['id', 'cluster_id']].merge(
                df_remaining, on='id', how='left', suffixes=('', '_orig')
            )
            print(f"[{GROUP_TAG}]   Merged columns: {multi_clusters_with_data.columns.tolist()[:10]}...")
            merged_n2 = build_merged_df(multi_clusters_with_data, 'cluster_id')
            wines_n2 = merged_n2
            n2_groups = len(merged_n2)
            splink_processed_ids = set(multi_clusters['id'].tolist())

    print(f"[{GROUP_TAG}] Nivel 2 concluido em {time.time()-t2:.1f}s")
    print(f"[{GROUP_TAG}]   Splink: {n2_groups} grupos, {len(splink_processed_ids)} vinhos agrupados")

    # Singletons finais
    df_singletons = df_remaining[~df_remaining['id'].isin(splink_processed_ids)]
    print(f"[{GROUP_TAG}] Singletons: {len(df_singletons):,} vinhos")

    # ── NIVEL 3 — Quarentena ──
    quarantine_n3 = []
    if len(all_splink_review) > 0:
        id_to_nome = df.set_index('id')['nome_limpo'].to_dict()
        for _, row in all_splink_review.iterrows():
            quarantine_n3.append({
                'clean_id_a': int(row['id_l']),
                'clean_id_b': int(row['id_r']),
                'nome_a': id_to_nome.get(int(row['id_l']), ''),
                'nome_b': id_to_nome.get(int(row['id_r']), ''),
                'match_probability': float(row['match_probability']),
                'motivo': 'splink_uncertain',
            })

    # ── INSERT ──
    print(f"\n[{GROUP_TAG}] Inserindo resultados...")

    n1_inserted = insert_unique_wines(conn, df_merged_n1, 'deterministic', 1.0)
    print(f"[{GROUP_TAG}]   Nivel 1 (deterministico): {n1_inserted:,} vinhos unicos inseridos")

    n2_inserted = insert_unique_wines(conn, wines_n2, 'splink_high', 0.80) if len(wines_n2) > 0 else 0
    print(f"[{GROUP_TAG}]   Nivel 2 (Splink): {n2_inserted:,} vinhos unicos inseridos")

    n_sing = insert_singletons(conn, df_singletons)
    print(f"[{GROUP_TAG}]   Singletons: {n_sing:,} vinhos inseridos")

    all_quarantine = quarantine_n1 + quarantine_n3
    n_q = insert_quarantine(conn, all_quarantine)
    print(f"[{GROUP_TAG}]   Quarentena: {n_q:,} registros inseridos")

    # ── Verificacoes ──
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM wines_unique_g4;")
    total_unique = cur.fetchone()[0]

    cur.execute("SELECT match_type, COUNT(*) FROM wines_unique_g4 GROUP BY match_type;")
    match_types = cur.fetchall()

    cur.execute("SELECT total_copias, COUNT(*) FROM wines_unique_g4 GROUP BY total_copias ORDER BY total_copias DESC LIMIT 10;")
    copias_dist = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM dedup_quarantine_g4;")
    total_quarantine = cur.fetchone()[0]

    elapsed = time.time() - t0
    taxa_dedup = (1 - total_unique / total_input) * 100 if total_input > 0 else 0

    # ── Relatorio ──
    print(f"\n{'='*50}")
    print(f"=== GRUPO 4 CONCLUIDO ===")
    print(f"{'='*50}")
    print(f"Paises: DE, NL, DK")
    print(f"Input: {total_input:,} vinhos de wines_clean")
    print(f"Nivel 1 (deterministico): {n1_groups:,} grupos")
    print(f"Nivel 2 (Splink): {n2_groups:,} grupos adicionais")
    print(f"Nivel 3 (quarentena): {len(all_quarantine):,} pares incertos")
    print(f"Output: {total_unique:,} vinhos unicos em wines_unique_g4")
    print(f"Taxa de dedup: {taxa_dedup:.1f}% (de {total_input:,} para {total_unique:,})")
    print(f"Tempo total: {elapsed:.1f}s")

    print(f"\nDistribuicao por match_type:")
    for mt, cnt in match_types:
        print(f"  {mt}: {cnt:,}")

    print(f"\nDistribuicao por total_copias (top 10):")
    for tc, cnt in copias_dist:
        print(f"  {tc} copias: {cnt:,} vinhos")

    # Exemplos
    print(f"\n--- 10 exemplos de merge NIVEL 1 (deterministico) ---")
    cur.execute("""
        SELECT nome_limpo, produtor, safra, pais_tabela, total_copias, clean_ids
        FROM wines_unique_g4
        WHERE match_type = 'deterministic' AND total_copias >= 2
        ORDER BY total_copias DESC
        LIMIT 10;
    """)
    for row in cur.fetchall():
        nome, produtor, safra, pt, copias, ids = row
        safra_str = str(safra) if safra else "NV"
        prod_str = produtor if produtor else "?"
        ids_str = str(ids[:5]) + ('...' if len(ids) > 5 else '')
        print(f"  [{pt.upper()}] {nome} | {prod_str} | {safra_str} | {copias} copias | IDs: {ids_str}")

    print(f"\n--- 10 exemplos de merge NIVEL 2 (Splink) ---")
    cur.execute("""
        SELECT nome_limpo, produtor, safra, pais_tabela, total_copias, clean_ids
        FROM wines_unique_g4
        WHERE match_type = 'splink_high' AND total_copias >= 2
        ORDER BY total_copias DESC
        LIMIT 10;
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            nome, produtor, safra, pt, copias, ids = row
            safra_str = str(safra) if safra else "NV"
            prod_str = produtor if produtor else "?"
            ids_str = str(ids[:5]) + ('...' if len(ids) > 5 else '')
            print(f"  [{pt.upper()}] {nome} | {prod_str} | {safra_str} | {copias} copias | IDs: {ids_str}")
    else:
        print("  (nenhum merge Splink com 2+ copias)")

    conn.close()
    print(f"\n[{GROUP_TAG}] Tudo pronto!")


if __name__ == "__main__":
    main()
