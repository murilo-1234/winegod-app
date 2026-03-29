#!/usr/bin/env python3
"""
DEDUP GROUP 9 — ZA, GR, RO, CL, SE, MD, IN
Deduplicacao de vinhos em 3 niveis: deterministico + Splink + quarentena
"""

import os
import sys
import time
import warnings
from collections import Counter

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

warnings.filterwarnings("ignore")

# Fix Windows encoding
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower().startswith('cp'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Config ──
DB_URL = os.getenv("WINEGOD_LOCAL_URL", "postgresql://postgres:postgres123@localhost:5432/winegod_db")
PAISES = ('za', 'gr', 'ro', 'cl', 'se', 'md', 'in')
GROUP = 9
TABLE_UNIQUE = f"wines_unique_g{GROUP}"
TABLE_QUARANTINE = f"dedup_quarantine_g{GROUP}"
BATCH_SIZE = 5000
MATCH_THRESHOLD = 0.80
REVIEW_THRESHOLD = 0.50

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
    c = Counter(vals)
    return c.most_common(1)[0][0]

def to_python(val):
    """Convert numpy types to native Python types for DB insertion."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if hasattr(val, 'item'):
        return val.item()
    return val

def merge_group(group_df, match_type, match_probability=1.0):
    """Merge N copias em 1 vinho unico."""
    # Filtrar precos validos (> 0)
    precos_validos = group_df['preco'].dropna()
    precos_validos = precos_validos[precos_validos > 0]

    nome_limpo_series = group_df['nome_limpo'].dropna()
    if len(nome_limpo_series) > 0:
        nome_limpo = nome_limpo_series.loc[nome_limpo_series.str.len().idxmax()]
    else:
        nome_limpo = group_df.iloc[0]['nome_limpo']

    return {
        'nome_limpo': str(nome_limpo) if nome_limpo is not None else None,
        'nome_normalizado': str(group_df.iloc[0]['nome_normalizado']),
        'produtor': to_python(first_non_null(group_df, 'produtor_extraido')),
        'produtor_normalizado': to_python(first_non_null(group_df, 'produtor_normalizado')),
        'safra': int(first_non_null(group_df, 'safra')) if first_non_null(group_df, 'safra') is not None else None,
        'tipo': to_python(most_common(group_df, 'tipo')),
        'pais': to_python(first_non_null(group_df, 'pais')),
        'pais_tabela': str(group_df.iloc[0]['pais_tabela']),
        'regiao': to_python(first_non_null(group_df, 'regiao')),
        'sub_regiao': to_python(first_non_null(group_df, 'sub_regiao')),
        'uvas': to_python(first_non_null(group_df, 'uvas')),
        'rating_melhor': float(group_df['rating'].max()) if group_df['rating'].notna().any() else None,
        'total_ratings_max': int(group_df['total_ratings'].max()) if group_df['total_ratings'].notna().any() else None,
        'preco_min_global': float(precos_validos.min()) if len(precos_validos) > 0 else None,
        'preco_max_global': float(precos_validos.max()) if len(precos_validos) > 0 else None,
        'moeda_referencia': to_python(most_common(group_df, 'moeda')),
        'url_imagem': to_python(first_non_null(group_df, 'url_imagem')),
        'hash_dedup': to_python(first_non_null(group_df, 'hash_dedup')),
        'ean_gtin': to_python(first_non_null(group_df, 'ean_gtin')),
        'match_type': match_type,
        'match_probability': float(match_probability) if match_probability is not None else None,
        'total_copias': len(group_df),
        'clean_ids': [int(x) for x in group_df['id'].tolist()],
    }

def validate_group(group_df):
    """Validacoes de seguranca. Retorna (ok, motivo)."""
    # Tipo deve bater
    tipos = group_df['tipo'].dropna().unique()
    if len(tipos) > 1:
        return False, f"tipos_diferentes: {','.join(tipos)}"

    # Preco nao pode variar >10x
    precos = group_df['preco'].dropna()
    precos = precos[precos > 0]
    if len(precos) >= 2:
        if precos.max() / precos.min() > 10:
            return False, f"preco_variacao_10x: {precos.min():.2f}-{precos.max():.2f}"

    # Grupos gigantes
    if len(group_df) > 100:
        return False, f"grupo_gigante: {len(group_df)} copias"

    return True, None


# ── Main ──

def main():
    t0 = time.time()
    print(f"=== DEDUP GRUPO {GROUP} — Paises: {', '.join(p.upper() for p in PAISES)} ===\n")

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    # ── Criar tabelas de destino ──
    print("[X9] Criando tabelas de destino...")
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

    # ── Carregar dados ──
    paises_str = ",".join(f"'{p}'" for p in PAISES)
    print(f"[X9] Carregando vinhos de wines_clean WHERE pais_tabela IN ({paises_str})...")

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
    print(f"[X9] Carregados: {total_input:,} vinhos\n")

    if total_input == 0:
        print("[X9] Nenhum vinho encontrado. Saindo.")
        conn.close()
        return

    # Estatisticas por pais
    for pais in PAISES:
        count = len(df[df['pais_tabela'] == pais])
        print(f"  {pais.upper()}: {count:,} vinhos")
    print()

    # ── NIVEL 1 — Deterministico ──
    print("=" * 60)
    print("NIVEL 1 — Deterministico (100% certeza)")
    print("=" * 60)

    processed_ids = set()
    det_groups = []  # list of DataFrames (each is a group)
    quarantine_rows = []

    # 1a. hash_dedup identico
    print("[X9] 1a. Agrupando por hash_dedup...")
    df_hash = df[df['hash_dedup'].notna() & (df['hash_dedup'] != '')].copy()
    hash_groups = df_hash.groupby(['pais_tabela', 'hash_dedup'])
    n_hash_groups = 0
    n_hash_merged = 0

    for (pais, hash_val), group in hash_groups:
        if len(group) < 2:
            continue
        ok, motivo = validate_group(group)
        if ok:
            det_groups.append(group)
            processed_ids.update(group['id'].tolist())
            n_hash_groups += 1
            n_hash_merged += len(group)
        else:
            # Para quarentena — registrar pares
            ids = group['id'].tolist()
            nomes = group['nome_limpo'].tolist()
            for i in range(min(len(ids) - 1, 5)):  # limitar pares
                quarantine_rows.append({
                    'clean_id_a': int(ids[0]),
                    'clean_id_b': int(ids[i + 1]),
                    'nome_a': nomes[0],
                    'nome_b': nomes[i + 1],
                    'match_probability': 1.0,
                    'motivo': f"hash_dedup_{motivo}"
                })

    print(f"  → {n_hash_groups:,} grupos por hash ({n_hash_merged:,} vinhos)")

    # 1b. ean_gtin identico (excluir ja processados)
    print("[X9] 1b. Agrupando por ean_gtin...")
    df_ean = df[
        (df['ean_gtin'].notna()) &
        (df['ean_gtin'] != '') &
        (~df['id'].isin(processed_ids))
    ].copy()
    ean_groups = df_ean.groupby(['pais_tabela', 'ean_gtin'])
    n_ean_groups = 0
    n_ean_merged = 0

    for (pais, ean_val), group in ean_groups:
        if len(group) < 2:
            continue
        ok, motivo = validate_group(group)
        if ok:
            det_groups.append(group)
            processed_ids.update(group['id'].tolist())
            n_ean_groups += 1
            n_ean_merged += len(group)
        else:
            ids = group['id'].tolist()
            nomes = group['nome_limpo'].tolist()
            for i in range(min(len(ids) - 1, 5)):
                quarantine_rows.append({
                    'clean_id_a': int(ids[0]),
                    'clean_id_b': int(ids[i + 1]),
                    'nome_a': nomes[0],
                    'nome_b': nomes[i + 1],
                    'match_probability': 1.0,
                    'motivo': f"ean_gtin_{motivo}"
                })

    print(f"  → {n_ean_groups:,} grupos por EAN ({n_ean_merged:,} vinhos)")

    # 1c. nome_normalizado + safra identicos (excluir ja processados)
    print("[X9] 1c. Agrupando por nome_normalizado + safra...")
    df_nome = df[~df['id'].isin(processed_ids)].copy()

    # Tratar safra NULL como string pra groupby
    df_nome['safra_key'] = df_nome['safra'].fillna(-1).astype(int)
    nome_groups = df_nome.groupby(['pais_tabela', 'nome_normalizado', 'safra_key'])
    n_nome_groups = 0
    n_nome_merged = 0

    for (pais, nome, safra_key), group in nome_groups:
        if len(group) < 2:
            continue
        ok, motivo = validate_group(group)
        if ok:
            det_groups.append(group)
            processed_ids.update(group['id'].tolist())
            n_nome_groups += 1
            n_nome_merged += len(group)
        else:
            ids = group['id'].tolist()
            nomes = group['nome_limpo'].tolist()
            for i in range(min(len(ids) - 1, 5)):
                quarantine_rows.append({
                    'clean_id_a': int(ids[0]),
                    'clean_id_b': int(ids[i + 1]),
                    'nome_a': nomes[0],
                    'nome_b': nomes[i + 1],
                    'match_probability': 1.0,
                    'motivo': f"nome_safra_{motivo}"
                })

    print(f"  → {n_nome_groups:,} grupos por nome+safra ({n_nome_merged:,} vinhos)")

    total_det_groups = n_hash_groups + n_ean_groups + n_nome_groups
    total_det_merged = n_hash_merged + n_ean_merged + n_nome_merged
    print(f"\n  NIVEL 1 TOTAL: {total_det_groups:,} grupos ({total_det_merged:,} vinhos agrupados)")

    # ── Preparar registros nivel 1 para insert ──
    print("\n[X9] Preparando registros deterministicos para insert...")
    unique_rows = []

    for group in det_groups:
        merged = merge_group(group, match_type='deterministic', match_probability=1.0)
        unique_rows.append(merged)

    # ── NIVEL 2 — Splink ──
    print("\n" + "=" * 60)
    print("NIVEL 2 — Probabilistico com Splink")
    print("=" * 60)

    df_remaining = df[~df['id'].isin(processed_ids)].copy()
    print(f"[X9] Vinhos restantes para nivel 2: {len(df_remaining):,}")

    splink_groups = 0
    splink_merged = 0
    splink_quarantine = 0

    if len(df_remaining) >= 100:
        try:
            import splink.comparison_library as cl
            import splink.blocking_rule_library as brl
            from splink import DuckDBAPI, Linker, SettingsCreator, block_on

            # Processar por pais para evitar problemas de memoria
            for pais in PAISES:
                df_pais = df_remaining[df_remaining['pais_tabela'] == pais].copy()
                if len(df_pais) < 10:
                    print(f"  {pais.upper()}: {len(df_pais)} vinhos — pulando (muito poucos)")
                    continue

                print(f"\n[X9] Splink para {pais.upper()}: {len(df_pais):,} vinhos...")

                # Preparar DataFrame — Splink precisa de colunas limpas
                df_splink = df_pais[['id', 'nome_normalizado', 'produtor_normalizado',
                                      'safra', 'tipo', 'pais_tabela', 'regiao', 'uvas']].copy()

                # Substituir NaN por None para Splink
                df_splink = df_splink.where(df_splink.notna(), None)

                # Blocking rules para treino
                training_block_nome = block_on("nome_normalizado")
                training_block_produtor = block_on("produtor_normalizado")

                # Blocking rules para predicao
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
                        # Quarentena: pares incertos
                        df_review = df_predictions[
                            (df_predictions["match_probability"] >= REVIEW_THRESHOLD) &
                            (df_predictions["match_probability"] < MATCH_THRESHOLD)
                        ].copy()

                        if len(df_review) > 0:
                            # Buscar nomes
                            id_to_nome = df_pais.set_index('id')['nome_limpo'].to_dict()
                            for _, row in df_review.iterrows():
                                id_l = int(row.get('id_l', row.get('unique_id_l', 0)))
                                id_r = int(row.get('id_r', row.get('unique_id_r', 0)))
                                quarantine_rows.append({
                                    'clean_id_a': id_l,
                                    'clean_id_b': id_r,
                                    'nome_a': id_to_nome.get(id_l, ''),
                                    'nome_b': id_to_nome.get(id_r, ''),
                                    'match_probability': float(row['match_probability']),
                                    'motivo': 'splink_uncertain',
                                })
                            splink_quarantine += len(df_review)
                            print(f"  → {pais.upper()}: {len(df_review):,} pares em quarentena")

                        # Clusterizar matches fortes
                        clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
                            results, threshold_match_probability=MATCH_THRESHOLD,
                        )
                        df_clusters = clusters.as_pandas_dataframe()

                        if len(df_clusters) > 0:
                            # Identificar col do cluster_id
                            cluster_col = 'cluster_id' if 'cluster_id' in df_clusters.columns else df_clusters.columns[-1]
                            id_col = 'id' if 'id' in df_clusters.columns else df_clusters.columns[0]

                            cluster_groups = df_clusters.groupby(cluster_col)
                            n_multi = 0
                            for cluster_id, cluster in cluster_groups:
                                ids_in_cluster = cluster[id_col].tolist()
                                if len(ids_in_cluster) < 2:
                                    continue
                                group_data = df_pais[df_pais['id'].isin(ids_in_cluster)]
                                if len(group_data) < 2:
                                    continue

                                ok, motivo = validate_group(group_data)
                                if ok:
                                    merged = merge_group(group_data, match_type='splink_high',
                                                        match_probability=float(MATCH_THRESHOLD))
                                    unique_rows.append(merged)
                                    processed_ids.update(ids_in_cluster)
                                    n_multi += 1
                                    splink_merged += len(ids_in_cluster)
                                else:
                                    ids = group_data['id'].tolist()
                                    nomes = group_data['nome_limpo'].tolist()
                                    for i in range(min(len(ids) - 1, 5)):
                                        quarantine_rows.append({
                                            'clean_id_a': int(ids[0]),
                                            'clean_id_b': int(ids[i + 1]),
                                            'nome_a': nomes[0],
                                            'nome_b': nomes[i + 1],
                                            'match_probability': float(MATCH_THRESHOLD),
                                            'motivo': f"splink_{motivo}",
                                        })

                            splink_groups += n_multi
                            print(f"  → {pais.upper()}: {n_multi:,} clusters Splink ({splink_merged:,} vinhos)")

                except Exception as e:
                    print(f"  [WARN] Splink falhou para {pais.upper()}: {e}")
                    import traceback
                    traceback.print_exc()

        except ImportError:
            print("[WARN] Splink nao instalado. Pulando nivel 2.")
            print("  Para instalar: pip install splink[duckdb]")
    else:
        print(f"  Poucos vinhos restantes ({len(df_remaining):,}). Pulando nivel 2.")

    print(f"\n  NIVEL 2 TOTAL: {splink_groups:,} grupos ({splink_merged:,} vinhos agrupados)")

    # ── Singletons — vinhos sem match ──
    print("\n[X9] Adicionando singletons (sem match)...")
    df_singletons = df[~df['id'].isin(processed_ids)]
    n_singletons = len(df_singletons)

    for _, row in df_singletons.iterrows():
        unique_rows.append({
            'nome_limpo': str(row['nome_limpo']) if pd.notna(row.get('nome_limpo')) else '',
            'nome_normalizado': str(row['nome_normalizado']) if pd.notna(row.get('nome_normalizado')) else '',
            'produtor': to_python(row.get('produtor_extraido')),
            'produtor_normalizado': to_python(row.get('produtor_normalizado')),
            'safra': int(row['safra']) if pd.notna(row.get('safra')) else None,
            'tipo': to_python(row.get('tipo')),
            'pais': to_python(row.get('pais')),
            'pais_tabela': str(row['pais_tabela']),
            'regiao': to_python(row.get('regiao')),
            'sub_regiao': to_python(row.get('sub_regiao')),
            'uvas': to_python(row.get('uvas')),
            'rating_melhor': float(row['rating']) if pd.notna(row.get('rating')) else None,
            'total_ratings_max': int(row['total_ratings']) if pd.notna(row.get('total_ratings')) else None,
            'preco_min_global': float(row['preco']) if pd.notna(row.get('preco')) and row.get('preco', 0) > 0 else None,
            'preco_max_global': float(row['preco']) if pd.notna(row.get('preco')) and row.get('preco', 0) > 0 else None,
            'moeda_referencia': to_python(row.get('moeda')),
            'url_imagem': to_python(row.get('url_imagem')),
            'hash_dedup': to_python(row.get('hash_dedup')),
            'ean_gtin': to_python(row.get('ean_gtin')),
            'match_type': 'singleton',
            'match_probability': None,
            'total_copias': 1,
            'clean_ids': [int(row['id'])],
        })

    print(f"  → {n_singletons:,} singletons")

    # ── INSERT wines_unique ──
    print(f"\n[X9] Inserindo {len(unique_rows):,} registros em {TABLE_UNIQUE}...")
    cols = [
        'nome_limpo', 'nome_normalizado', 'produtor', 'produtor_normalizado',
        'safra', 'tipo', 'pais', 'pais_tabela', 'regiao', 'sub_regiao', 'uvas',
        'rating_melhor', 'total_ratings_max', 'preco_min_global', 'preco_max_global',
        'moeda_referencia', 'url_imagem', 'hash_dedup', 'ean_gtin',
        'match_type', 'match_probability', 'total_copias', 'clean_ids'
    ]

    insert_sql = f"""
        INSERT INTO {TABLE_UNIQUE} ({', '.join(cols)})
        VALUES %s
    """

    def row_to_tuple(r):
        return tuple(
            r.get(c) if c != 'clean_ids' else r.get(c, [])
            for c in cols
        )

    for i in range(0, len(unique_rows), BATCH_SIZE):
        batch = unique_rows[i:i + BATCH_SIZE]
        values = [row_to_tuple(r) for r in batch]
        execute_values(cur, insert_sql, values, page_size=BATCH_SIZE)
        conn.commit()
        if (i // BATCH_SIZE) % 10 == 0 or i + BATCH_SIZE >= len(unique_rows):
            print(f"  ... {min(i + BATCH_SIZE, len(unique_rows)):,}/{len(unique_rows):,}")

    # ── INSERT quarantine ──
    if quarantine_rows:
        print(f"\n[X9] Inserindo {len(quarantine_rows):,} registros em {TABLE_QUARANTINE}...")
        q_cols = ['clean_id_a', 'clean_id_b', 'nome_a', 'nome_b', 'match_probability', 'motivo']
        q_sql = f"""
            INSERT INTO {TABLE_QUARANTINE} ({', '.join(q_cols)})
            VALUES %s
        """
        q_values = [tuple(r[c] for c in q_cols) for r in quarantine_rows]
        for i in range(0, len(q_values), BATCH_SIZE):
            batch = q_values[i:i + BATCH_SIZE]
            execute_values(cur, q_sql, batch, page_size=BATCH_SIZE)
            conn.commit()
    else:
        print(f"\n[X9] Nenhum registro de quarentena.")

    # ── Verificacoes ──
    print("\n[X9] Verificando...")
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

    # ── Exemplos ──
    print("\n" + "=" * 60)
    print("EXEMPLOS — Merges Nivel 1 (deterministico)")
    print("=" * 60)
    cur.execute(f"""
        SELECT nome_limpo, produtor, safra, tipo, pais_tabela, total_copias, clean_ids
        FROM {TABLE_UNIQUE}
        WHERE match_type = 'deterministic' AND total_copias > 1
        ORDER BY total_copias DESC
        LIMIT 10;
    """)
    for row in cur.fetchall():
        nome, produtor, safra, tipo, pais, copias, ids = row
        print(f"  [{pais.upper()}] {nome} | {produtor or '?'} | {safra or '?'} | {tipo or '?'} | {copias} copias | IDs: {ids[:5]}{'...' if len(ids) > 5 else ''}")

    print("\n" + "=" * 60)
    print("EXEMPLOS — Merges Nivel 2 (Splink)")
    print("=" * 60)
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
            print(f"  [{pais.upper()}] {nome} | {produtor or '?'} | {safra or '?'} | prob={prob:.2f} | {copias} copias")
    else:
        print("  (nenhum merge Splink neste grupo)")

    # ── Relatorio final ──
    elapsed = time.time() - t0

    print("\n" + "=" * 60)
    print(f"=== GRUPO {GROUP} CONCLUIDO ===")
    print("=" * 60)
    print(f"Paises: {', '.join(p.upper() for p in PAISES)}")
    print(f"Input: {total_input:,} vinhos de wines_clean")
    print(f"Nivel 1 (deterministico): {total_det_groups:,} grupos")
    print(f"Nivel 2 (Splink): {splink_groups:,} grupos adicionais")
    print(f"Nivel 3 (quarentena): {total_quarantine:,} pares incertos")
    print(f"Output: {total_unique:,} vinhos unicos em {TABLE_UNIQUE}")
    if total_input > 0:
        taxa = (1 - total_unique / total_input) * 100
        print(f"Taxa de dedup: {taxa:.1f}% (de {total_input:,} para {total_unique:,})")
    print(f"\nDistribuicao por match_type:")
    for mt, cnt in match_types:
        print(f"  {mt}: {cnt:,}")
    print(f"\nDistribuicao por total_copias (top 10):")
    for copias, cnt in copias_dist:
        print(f"  {copias} copias: {cnt:,} vinhos")
    print(f"\nTempo total: {elapsed:.1f}s")

    conn.close()
    print("\n[X9] Done!")


if __name__ == "__main__":
    main()
