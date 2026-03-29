"""
Deduplicacao de Vinhos — Grupo 6 (PT, FR, NZ, ES)
3 niveis: deterministico + Splink probabilistico + quarentena
"""

import sys
import time
import traceback
import warnings
import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
warnings.filterwarnings("ignore")

# ── Config ──
DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
PAISES = ('pt', 'fr', 'nz', 'es')
GROUP = 6
BATCH_SIZE = 5000
MATCH_THRESHOLD = 0.80
REVIEW_THRESHOLD = 0.50


def get_conn():
    return psycopg2.connect(DB_URL)


def log(msg):
    print(f"[X6] {msg}", flush=True)


# ── Helpers de merge (vectorized) ──

def first_non_null_val(series):
    vals = series.dropna()
    if len(vals) == 0:
        return None
    v = vals.iloc[0]
    if isinstance(v, str) and v == '':
        vals = vals[vals != '']
        return vals.iloc[0] if len(vals) > 0 else None
    return v


def most_common_val(series):
    vals = series.dropna()
    vals = vals[vals != ''] if vals.dtype == object else vals
    if len(vals) == 0:
        return None
    mode = vals.mode()
    return mode.iloc[0] if len(mode) > 0 else vals.iloc[0]


def merge_group_fast(group_df, match_type, match_probability=1.0):
    """Merge multiplas copias em 1 vinho unico — versao otimizada."""
    try:
        # Precos validos
        precos = group_df['preco'].dropna()
        precos = precos[precos > 0]

        # Nome mais longo
        nomes = group_df['nome_limpo'].dropna()
        if len(nomes) > 0:
            nome_limpo = nomes.iloc[nomes.str.len().values.argmax()]
        else:
            nome_limpo = group_df.iloc[0]['nome_limpo'] or ''

        # Rating e total_ratings
        rating_max = None
        if group_df['rating'].notna().any():
            rating_max = float(group_df['rating'].max())

        tr_max = None
        if group_df['total_ratings'].notna().any():
            tr_max = int(group_df['total_ratings'].max())

        return {
            'nome_limpo': nome_limpo,
            'nome_normalizado': group_df.iloc[0]['nome_normalizado'],
            'produtor': first_non_null_val(group_df['produtor_extraido']),
            'produtor_normalizado': first_non_null_val(group_df['produtor_normalizado']),
            'safra': first_non_null_val(group_df['safra']),
            'tipo': most_common_val(group_df['tipo']),
            'pais': first_non_null_val(group_df['pais']),
            'pais_tabela': group_df.iloc[0]['pais_tabela'],
            'regiao': first_non_null_val(group_df['regiao']),
            'sub_regiao': first_non_null_val(group_df['sub_regiao']),
            'uvas': first_non_null_val(group_df['uvas']),
            'rating_melhor': rating_max,
            'total_ratings_max': tr_max,
            'preco_min_global': float(precos.min()) if len(precos) > 0 else None,
            'preco_max_global': float(precos.max()) if len(precos) > 0 else None,
            'moeda_referencia': most_common_val(group_df['moeda']),
            'url_imagem': first_non_null_val(group_df['url_imagem']),
            'hash_dedup': first_non_null_val(group_df['hash_dedup']),
            'ean_gtin': first_non_null_val(group_df['ean_gtin']),
            'match_type': match_type,
            'match_probability': match_probability,
            'total_copias': len(group_df),
            'clean_ids': list(group_df['id'].astype(int)),
        }
    except Exception as e:
        log(f"  ERRO merge_group: {e}")
        return None


def validate_group(group_df):
    """Validacoes de seguranca. Retorna (ok, motivo)."""
    tipos = group_df['tipo'].dropna().unique()
    tipo_set = set(str(t).lower().strip() for t in tipos if t)
    if 'tinto' in tipo_set and 'branco' in tipo_set:
        return False, "tipo_conflito: tinto+branco"
    if 'tinto' in tipo_set and 'rose' in tipo_set:
        return False, "tipo_conflito: tinto+rose"
    if 'branco' in tipo_set and 'rose' in tipo_set:
        return False, "tipo_conflito: branco+rose"

    precos = group_df['preco'].dropna()
    precos = precos[precos > 0]
    if len(precos) >= 2:
        if precos.max() / precos.min() > 10:
            return False, f"preco_variacao: {precos.min():.2f}-{precos.max():.2f}"

    if len(group_df) > 100:
        return False, f"grupo_gigante: {len(group_df)} copias"

    return True, None


# ── Criar tabelas ──

def create_tables():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        DROP TABLE IF EXISTS wines_unique_g6 CASCADE;
        CREATE TABLE wines_unique_g6 (
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
        DROP TABLE IF EXISTS dedup_quarantine_g6 CASCADE;
        CREATE TABLE dedup_quarantine_g6 (
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
    conn.close()
    log("Tabelas criadas: wines_unique_g6, dedup_quarantine_g6")


# ── Carregar dados ──

def load_data():
    conn = get_conn()
    placeholders = ','.join(['%s'] * len(PAISES))
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
    df = pd.read_sql(query, conn, params=PAISES)
    conn.close()
    log(f"Carregados {len(df):,} vinhos ({', '.join(PAISES)})")
    return df


# ── Nivel 1: Deterministico ──

def nivel_1_deterministico(df):
    log("Nivel 1 -- Deterministico...")
    processed_ids = set()
    group_dfs = []  # list of (group_df, match_type)
    quarantine_from_validation = []

    # 1a. hash_dedup identico
    df_hash = df[df['hash_dedup'].notna() & (df['hash_dedup'] != '')]
    if len(df_hash) > 0:
        for (pais, hash_val), grp in df_hash.groupby(['pais_tabela', 'hash_dedup']):
            if len(grp) < 2:
                continue
            ids = set(grp['id'].tolist())
            new_ids = ids - processed_ids
            if len(new_ids) < 2:
                continue
            sub = grp[grp['id'].isin(new_ids)]
            ok, motivo = validate_group(sub)
            if ok:
                group_dfs.append((sub, 'deterministic'))
                processed_ids.update(new_ids)
            else:
                quarantine_from_validation.append((sub, motivo))
                processed_ids.update(new_ids)

    log(f"  1a hash_dedup: {len(group_dfs)} grupos")

    # 1b. ean_gtin identico
    count_before = len(group_dfs)
    df_ean = df[df['ean_gtin'].notna() & (df['ean_gtin'] != '')]
    if len(df_ean) > 0:
        for (pais, ean), grp in df_ean.groupby(['pais_tabela', 'ean_gtin']):
            if len(grp) < 2:
                continue
            ids = set(grp['id'].tolist())
            new_ids = ids - processed_ids
            if len(new_ids) < 2:
                continue
            sub = grp[grp['id'].isin(new_ids)]
            ok, motivo = validate_group(sub)
            if ok:
                group_dfs.append((sub, 'deterministic'))
                processed_ids.update(new_ids)
            else:
                quarantine_from_validation.append((sub, motivo))
                processed_ids.update(new_ids)

    log(f"  1b ean_gtin: {len(group_dfs) - count_before} grupos")

    # 1c. nome_normalizado + safra identicos
    count_before = len(group_dfs)
    df_nome = df[~df['id'].isin(processed_ids)]

    # With safra
    df_with_safra = df_nome[df_nome['safra'].notna()]
    if len(df_with_safra) > 0:
        for (pais, nome, safra), grp in df_with_safra.groupby(['pais_tabela', 'nome_normalizado', 'safra']):
            if len(grp) < 2:
                continue
            ids = set(grp['id'].tolist())
            new_ids = ids - processed_ids
            if len(new_ids) < 2:
                continue
            sub = grp[grp['id'].isin(new_ids)]
            ok, motivo = validate_group(sub)
            if ok:
                group_dfs.append((sub, 'deterministic'))
                processed_ids.update(new_ids)
            else:
                quarantine_from_validation.append((sub, motivo))
                processed_ids.update(new_ids)

    log(f"  1c-safra: {len(group_dfs) - count_before} grupos")

    # Without safra
    count_before2 = len(group_dfs)
    df_no_safra = df_nome[df_nome['safra'].isna() & ~df_nome['id'].isin(processed_ids)]
    if len(df_no_safra) > 0:
        for (pais, nome), grp in df_no_safra.groupby(['pais_tabela', 'nome_normalizado']):
            if len(grp) < 2:
                continue
            ids = set(grp['id'].tolist())
            new_ids = ids - processed_ids
            if len(new_ids) < 2:
                continue
            sub = grp[grp['id'].isin(new_ids)]
            ok, motivo = validate_group(sub)
            if ok:
                group_dfs.append((sub, 'deterministic'))
                processed_ids.update(new_ids)
            else:
                quarantine_from_validation.append((sub, motivo))
                processed_ids.update(new_ids)

    log(f"  1c-nosafra: {len(group_dfs) - count_before2} grupos")

    # Merge groups
    log(f"  Merging {len(group_dfs)} grupos...")
    merged = []
    for i, (grp_df, mtype) in enumerate(group_dfs):
        m = merge_group_fast(grp_df, mtype, 1.0)
        if m:
            merged.append(m)
        if (i + 1) % 5000 == 0:
            log(f"    merged {i+1}/{len(group_dfs)}")

    log(f"  Merge concluido: {len(merged)} vinhos unicos")

    # Remaining
    remaining_ids = set(df['id'].tolist()) - processed_ids
    df_remaining = df[df['id'].isin(remaining_ids)].copy()

    log(f"  Nivel 1 total: {len(group_dfs)} grupos ({len(processed_ids):,} vinhos agrupados)")
    log(f"  Restam: {len(df_remaining):,} vinhos para nivel 2")
    log(f"  Quarentena (validacao): {len(quarantine_from_validation)} grupos")

    return merged, df_remaining, processed_ids, quarantine_from_validation


# ── Nivel 2: Splink ──

def nivel_2_splink(df_remaining):
    if len(df_remaining) < 100:
        log(f"  Nivel 2: pulando (apenas {len(df_remaining)} vinhos restantes)")
        return [], pd.DataFrame(), []

    log(f"Nivel 2 -- Splink probabilistico ({len(df_remaining):,} vinhos)...")

    try:
        import splink.comparison_library as cl
        import splink.blocking_rule_library as brl
        from splink import DuckDBAPI, Linker, SettingsCreator, block_on
        log("  Splink importado com sucesso")
    except Exception as e:
        log(f"  ERRO importando Splink: {e}")
        return [], df_remaining, []

    all_clusters_merged = []
    all_review_pairs = []
    all_singletons_df = pd.DataFrame()

    for pais in PAISES:
        df_pais = df_remaining[df_remaining['pais_tabela'] == pais].copy()
        if len(df_pais) < 100:
            log(f"  {pais.upper()}: pulando Splink ({len(df_pais)} vinhos)")
            all_singletons_df = pd.concat([all_singletons_df, df_pais])
            continue

        log(f"  {pais.upper()}: processando {len(df_pais):,} vinhos com Splink...")

        # Prepare dataframe
        df_splink = df_pais[['id', 'nome_normalizado', 'produtor_normalizado',
                              'safra', 'tipo', 'pais_tabela', 'regiao', 'uvas']].copy()
        for col in df_splink.columns:
            if df_splink[col].dtype == object:
                df_splink[col] = df_splink[col].replace('', None)

        try:
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

            log(f"  {pais.upper()}: criando Linker...")
            db_api = DuckDBAPI()
            linker = Linker(df_splink, settings, db_api)

            log(f"  {pais.upper()}: estimando probabilidades...")
            linker.training.estimate_probability_two_random_records_match(
                training_block_nome, recall=0.7,
            )

            log(f"  {pais.upper()}: estimando u-probabilities...")
            linker.training.estimate_u_using_random_sampling(max_pairs=1_000_000)

            log(f"  {pais.upper()}: EM (nome)...")
            linker.training.estimate_parameters_using_expectation_maximisation(
                training_block_nome, fix_u_probabilities=True,
            )

            log(f"  {pais.upper()}: EM (produtor)...")
            linker.training.estimate_parameters_using_expectation_maximisation(
                training_block_produtor, fix_u_probabilities=True,
            )

            log(f"  {pais.upper()}: predizendo pares...")
            results = linker.inference.predict(threshold_match_probability=REVIEW_THRESHOLD)
            df_predictions = results.as_pandas_dataframe()

            log(f"  {pais.upper()}: {len(df_predictions):,} pares encontrados")

            if len(df_predictions) == 0:
                all_singletons_df = pd.concat([all_singletons_df, df_pais])
                continue

            # Review pairs (quarantine)
            df_review = df_predictions[
                (df_predictions["match_probability"] >= REVIEW_THRESHOLD) &
                (df_predictions["match_probability"] < MATCH_THRESHOLD)
            ].copy()

            if len(df_review) > 0:
                for _, row in df_review.iterrows():
                    id_l = int(row.get('id_l', row.get('unique_id_l', 0)))
                    id_r = int(row.get('id_r', row.get('unique_id_r', 0)))
                    nome_l = str(row.get('nome_normalizado_l', ''))
                    nome_r = str(row.get('nome_normalizado_r', ''))
                    all_review_pairs.append({
                        'clean_id_a': id_l,
                        'clean_id_b': id_r,
                        'nome_a': nome_l,
                        'nome_b': nome_r,
                        'match_probability': float(row['match_probability']),
                        'motivo': 'splink_uncertain',
                    })

            # Cluster high-confidence matches
            log(f"  {pais.upper()}: clusterizando...")
            clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
                results, threshold_match_probability=MATCH_THRESHOLD,
            )
            df_clusters = clusters.as_pandas_dataframe()

            if len(df_clusters) == 0:
                all_singletons_df = pd.concat([all_singletons_df, df_pais])
                continue

            # Group by cluster_id and merge
            clustered_ids = set()
            cluster_groups = df_clusters.groupby('cluster_id')
            multi_clusters = {cid: grp for cid, grp in cluster_groups if len(grp) >= 2}

            log(f"  {pais.upper()}: {len(multi_clusters)} clusters com 2+ membros")

            for cluster_id, cluster_grp in multi_clusters.items():
                cluster_wine_ids = cluster_grp['id'].tolist()
                grp_full = df_pais[df_pais['id'].isin(cluster_wine_ids)]
                if len(grp_full) < 2:
                    continue

                ok, motivo = validate_group(grp_full)
                if ok:
                    m = merge_group_fast(grp_full, 'splink_high', 0.85)
                    if m:
                        all_clusters_merged.append(m)
                        clustered_ids.update(cluster_wine_ids)
                else:
                    ids_list = grp_full['id'].tolist()
                    for i in range(len(ids_list) - 1):
                        all_review_pairs.append({
                            'clean_id_a': int(ids_list[i]),
                            'clean_id_b': int(ids_list[i + 1]),
                            'nome_a': '',
                            'nome_b': '',
                            'match_probability': 0.80,
                            'motivo': f'validation_failed: {motivo}',
                        })

            remaining_pais = df_pais[~df_pais['id'].isin(clustered_ids)]
            all_singletons_df = pd.concat([all_singletons_df, remaining_pais])

            log(f"  {pais.upper()}: {len([m for m in all_clusters_merged])} grupos Splink total, {len(df_review)} pares quarentena")

        except Exception as e:
            log(f"  {pais.upper()}: ERRO Splink -- {e}")
            traceback.print_exc()
            all_singletons_df = pd.concat([all_singletons_df, df_pais])
            continue

    log(f"  Nivel 2 total: {len(all_clusters_merged)} grupos Splink")
    log(f"  Nivel 2 quarentena: {len(all_review_pairs)} pares")

    return all_clusters_merged, all_singletons_df, all_review_pairs


# ── Inserir resultados ──

def insert_unique(merged_records):
    if not merged_records:
        return 0

    conn = get_conn()
    cur = conn.cursor()

    cols = [
        'nome_limpo', 'nome_normalizado', 'produtor', 'produtor_normalizado',
        'safra', 'tipo', 'pais', 'pais_tabela', 'regiao', 'sub_regiao', 'uvas',
        'rating_melhor', 'total_ratings_max', 'preco_min_global', 'preco_max_global',
        'moeda_referencia', 'url_imagem', 'hash_dedup', 'ean_gtin',
        'match_type', 'match_probability', 'total_copias', 'clean_ids'
    ]
    insert_sql = f"INSERT INTO wines_unique_g6 ({','.join(cols)}) VALUES %s"

    rows = []
    for rec in merged_records:
        # Convert safra to int if not None
        safra = rec['safra']
        if safra is not None:
            try:
                safra = int(float(safra))
            except (ValueError, TypeError):
                safra = None
        rec_copy = dict(rec)
        rec_copy['safra'] = safra
        row = tuple(rec_copy[c] for c in cols)
        rows.append(row)

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        execute_values(cur, insert_sql, batch, page_size=BATCH_SIZE)
        if (i // BATCH_SIZE) % 5 == 0 and i > 0:
            log(f"  Inserted {i + len(batch):,} / {len(rows):,}")

    conn.commit()
    cur.close()
    conn.close()
    return len(rows)


def insert_singletons(df_singletons):
    """Insert remaining wines as singletons."""
    if len(df_singletons) == 0:
        return 0

    records = []
    for _, row in df_singletons.iterrows():
        preco = row['preco'] if pd.notna(row['preco']) and row['preco'] > 0 else None
        safra = int(row['safra']) if pd.notna(row.get('safra')) else None
        records.append({
            'nome_limpo': row['nome_limpo'] or '',
            'nome_normalizado': row['nome_normalizado'] or '',
            'produtor': row.get('produtor_extraido'),
            'produtor_normalizado': row.get('produtor_normalizado'),
            'safra': safra,
            'tipo': row.get('tipo'),
            'pais': row.get('pais'),
            'pais_tabela': row['pais_tabela'],
            'regiao': row.get('regiao'),
            'sub_regiao': row.get('sub_regiao'),
            'uvas': row.get('uvas'),
            'rating_melhor': float(row['rating']) if pd.notna(row.get('rating')) else None,
            'total_ratings_max': int(row['total_ratings']) if pd.notna(row.get('total_ratings')) else None,
            'preco_min_global': float(preco) if preco else None,
            'preco_max_global': float(preco) if preco else None,
            'moeda_referencia': row.get('moeda'),
            'url_imagem': row.get('url_imagem'),
            'hash_dedup': row.get('hash_dedup'),
            'ean_gtin': row.get('ean_gtin'),
            'match_type': 'singleton',
            'match_probability': None,
            'total_copias': 1,
            'clean_ids': [int(row['id'])],
        })

    return insert_unique(records)


def insert_quarantine(review_pairs):
    if not review_pairs:
        return 0

    conn = get_conn()
    cur = conn.cursor()

    insert_sql = """INSERT INTO dedup_quarantine_g6
        (clean_id_a, clean_id_b, nome_a, nome_b, match_probability, motivo)
        VALUES %s"""

    rows = [(p['clean_id_a'], p['clean_id_b'], p.get('nome_a', ''),
             p.get('nome_b', ''), p['match_probability'], p['motivo'])
            for p in review_pairs]

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        execute_values(cur, insert_sql, batch, page_size=BATCH_SIZE)

    conn.commit()
    cur.close()
    conn.close()
    return len(rows)


def insert_quarantine_from_validation(quarantine_groups):
    pairs = []
    for grp_df, motivo in quarantine_groups:
        ids = grp_df['id'].tolist()
        nomes = grp_df['nome_normalizado'].tolist()
        for i in range(len(ids) - 1):
            pairs.append({
                'clean_id_a': int(ids[i]),
                'clean_id_b': int(ids[i + 1]),
                'nome_a': nomes[i] if i < len(nomes) else '',
                'nome_b': nomes[i + 1] if i + 1 < len(nomes) else '',
                'match_probability': 1.0,
                'motivo': f'validation_failed: {motivo}',
            })
    return insert_quarantine(pairs)


# ── Exemplos ──

def show_examples(df, merged_records, label, n=10):
    log(f"\n  --- {n} exemplos de merge ({label}) ---")
    count = 0
    for rec in merged_records:
        if rec['total_copias'] >= 2 and count < n:
            clean_ids = rec['clean_ids'][:3]
            sub = df[df['id'].isin(clean_ids)]
            nomes_orig = sub['nome_limpo'].tolist()
            log(f"  [{count+1}] {rec['nome_limpo']} (safra={rec['safra']}, copias={rec['total_copias']})")
            for nome in nomes_orig[:3]:
                log(f"       <- {nome}")
            count += 1
    if count == 0:
        log(f"  (nenhum merge com 2+ copias)")


# ── Main ──

def main():
    t0 = time.time()

    log("=== DEDUP GRUPO 6 -- PT, FR, NZ, ES ===")

    # 1. Criar tabelas
    create_tables()

    # 2. Carregar dados
    df = load_data()
    total_input = len(df)

    if total_input == 0:
        log("ERRO: nenhum vinho encontrado")
        sys.exit(1)

    for pais in PAISES:
        n = len(df[df['pais_tabela'] == pais])
        log(f"  {pais.upper()}: {n:,} vinhos")

    # 3. Nivel 1
    t1 = time.time()
    merged_det, df_remaining, processed_ids, quarantine_validation = nivel_1_deterministico(df)
    log(f"  Nivel 1 em {time.time() - t1:.1f}s")

    # 4. Nivel 2
    t2 = time.time()
    merged_splink, df_singletons, review_pairs = nivel_2_splink(df_remaining)
    log(f"  Nivel 2 em {time.time() - t2:.1f}s")

    # 5. Insert
    log("Inserindo resultados...")

    n_det = insert_unique(merged_det)
    log(f"  {n_det:,} vinhos deterministicos inseridos")

    n_splink = insert_unique(merged_splink)
    log(f"  {n_splink:,} vinhos Splink inseridos")

    log(f"  Inserindo {len(df_singletons):,} singletons...")
    n_single = insert_singletons(df_singletons)
    log(f"  {n_single:,} singletons inseridos")

    n_quarantine_val = insert_quarantine_from_validation(quarantine_validation)
    n_quarantine_splink = insert_quarantine(review_pairs)
    total_quarantine = n_quarantine_val + n_quarantine_splink
    log(f"  {total_quarantine:,} pares em quarentena")

    # 6. Examples
    show_examples(df, merged_det, "Nivel 1 -- Deterministico")
    show_examples(df, merged_splink, "Nivel 2 -- Splink")

    # 7. Verificacoes
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM wines_unique_g6")
    total_unique = cur.fetchone()[0]
    cur.execute("SELECT match_type, COUNT(*) FROM wines_unique_g6 GROUP BY match_type ORDER BY count DESC")
    by_type = cur.fetchall()
    cur.execute("SELECT total_copias, COUNT(*) FROM wines_unique_g6 GROUP BY total_copias ORDER BY total_copias DESC LIMIT 10")
    by_copias = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM dedup_quarantine_g6")
    total_q = cur.fetchone()[0]
    cur.close()
    conn.close()

    total_elapsed = time.time() - t0
    taxa_dedup = ((total_input - total_unique) / total_input * 100) if total_input > 0 else 0

    print(f"""
=== GRUPO 6 CONCLUIDO ===
Paises: PT, FR, NZ, ES
Input: {total_input:,} vinhos de wines_clean
Nivel 1 (deterministico): {len(merged_det):,} grupos
Nivel 2 (Splink): {len(merged_splink):,} grupos adicionais
Nivel 3 (quarentena): {total_quarantine:,} pares incertos
Output: {total_unique:,} vinhos unicos em wines_unique_g6
Taxa de dedup: {taxa_dedup:.1f}% (de {total_input:,} para {total_unique:,})
Tempo total: {total_elapsed:.1f}s

--- Por match_type ---""", flush=True)
    for mtype, cnt in by_type:
        print(f"  {mtype}: {cnt:,}", flush=True)

    print("\n--- Top copias ---", flush=True)
    for copias, cnt in by_copias:
        print(f"  {copias} copias: {cnt:,} vinhos", flush=True)

    print(f"\n--- Quarentena ---", flush=True)
    print(f"  Total pares: {total_q:,}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERRO FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
