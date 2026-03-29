#!/usr/bin/env python3
"""
DEDUP GROUP 8 — PE, BE, CH, PL, UY
Deduplicacao de vinhos em 3 niveis: deterministico + Splink + quarentena
Processa 1 pais por vez para economizar memoria.
"""

import gc
import os
import sys
import time
import warnings
from collections import Counter

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

warnings.filterwarnings("ignore")

# ── Config ──
DB_URL = os.getenv("WINEGOD_LOCAL_URL", "postgresql://postgres:postgres123@localhost:5432/winegod_db")
PAISES = ('pe', 'be', 'ch', 'pl', 'uy')
GROUP = 8
TABLE_UNIQUE = f"wines_unique_g{GROUP}"
TABLE_QUARANTINE = f"dedup_quarantine_g{GROUP}"
BATCH_SIZE = 5000
MATCH_THRESHOLD = 0.80
REVIEW_THRESHOLD = 0.50

# ── Helpers ──

def to_python(val):
    """Convert numpy types to Python native types for psycopg2."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        v = float(val)
        return None if pd.isna(v) else v
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, np.ndarray):
        return val.tolist()
    return val

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

def merge_group(group_df, match_type, match_probability=1.0):
    """Merge N copias em 1 vinho unico."""
    precos_validos = group_df['preco'].dropna()
    precos_validos = precos_validos[precos_validos > 0]

    nome_limpo_series = group_df['nome_limpo'].dropna()
    if len(nome_limpo_series) > 0:
        nome_limpo = nome_limpo_series.loc[nome_limpo_series.str.len().idxmax()]
    else:
        nome_limpo = group_df.iloc[0]['nome_limpo']

    return {
        'nome_limpo': to_python(nome_limpo),
        'nome_normalizado': to_python(group_df.iloc[0]['nome_normalizado']),
        'produtor': to_python(first_non_null(group_df, 'produtor_extraido')),
        'produtor_normalizado': to_python(first_non_null(group_df, 'produtor_normalizado')),
        'safra': to_python(first_non_null(group_df, 'safra')),
        'tipo': to_python(most_common(group_df, 'tipo')),
        'pais': to_python(first_non_null(group_df, 'pais')),
        'pais_tabela': to_python(group_df.iloc[0]['pais_tabela']),
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
        'match_probability': match_probability,
        'total_copias': len(group_df),
        'clean_ids': [int(x) for x in group_df['id']],
    }

def validate_group(group_df):
    """Validacoes de seguranca. Retorna (ok, motivo)."""
    tipos = group_df['tipo'].dropna().unique()
    if len(tipos) > 1:
        return False, f"tipos_diferentes: {','.join(tipos)}"

    precos = group_df['preco'].dropna()
    precos = precos[precos > 0]
    if len(precos) >= 2:
        if precos.max() / precos.min() > 10:
            return False, f"preco_variacao_10x: {precos.min():.2f}-{precos.max():.2f}"

    if len(group_df) > 100:
        return False, f"grupo_gigante: {len(group_df)} copias"

    return True, None

def make_singleton(row):
    """Cria registro singleton de uma row."""
    return {
        'nome_limpo': to_python(row['nome_limpo']),
        'nome_normalizado': to_python(row['nome_normalizado']),
        'produtor': to_python(row.get('produtor_extraido')),
        'produtor_normalizado': to_python(row.get('produtor_normalizado')),
        'safra': int(row['safra']) if pd.notna(row.get('safra')) else None,
        'tipo': to_python(row.get('tipo')),
        'pais': to_python(row.get('pais')),
        'pais_tabela': to_python(row['pais_tabela']),
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
    }

def insert_batch(cur, conn, table, rows):
    """Insert rows em batches."""
    if not rows:
        return
    cols = [
        'nome_limpo', 'nome_normalizado', 'produtor', 'produtor_normalizado',
        'safra', 'tipo', 'pais', 'pais_tabela', 'regiao', 'sub_regiao', 'uvas',
        'rating_melhor', 'total_ratings_max', 'preco_min_global', 'preco_max_global',
        'moeda_referencia', 'url_imagem', 'hash_dedup', 'ean_gtin',
        'match_type', 'match_probability', 'total_copias', 'clean_ids'
    ]
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s"

    def row_to_tuple(r):
        return tuple(
            to_python(r.get(c)) if c != 'clean_ids' else [int(x) for x in r.get(c, [])]
            for c in cols
        )

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        values = [row_to_tuple(r) for r in batch]
        execute_values(cur, sql, values, page_size=BATCH_SIZE)
        conn.commit()

def insert_quarantine(cur, conn, table, rows):
    """Insert quarantine rows em batches."""
    if not rows:
        return
    q_cols = ['clean_id_a', 'clean_id_b', 'nome_a', 'nome_b', 'match_probability', 'motivo']
    sql = f"INSERT INTO {table} ({', '.join(q_cols)}) VALUES %s"
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        values = [tuple(r[c] for c in q_cols) for r in batch]
        execute_values(cur, sql, values, page_size=BATCH_SIZE)
        conn.commit()


def process_country(pais, conn, cur):
    """Processa 1 pais: nivel 1 + nivel 2 + singletons. Retorna stats."""
    t_pais = time.time()
    print(f"\n{'='*60}")
    print(f"[X8] Processando {pais.upper()}...")
    print(f"{'='*60}")

    # Carregar dados do pais
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
        WHERE pais_tabela = '{pais}'
    """
    df = pd.read_sql(query, conn)
    total_pais = len(df)
    print(f"  Carregados: {total_pais:,} vinhos")

    if total_pais == 0:
        return {'input': 0, 'det_groups': 0, 'splink_groups': 0, 'quarantine': 0, 'unique': 0}

    processed_ids = set()
    unique_rows = []
    quarantine_rows = []
    n_det_groups = 0

    # ── NIVEL 1a: hash_dedup ──
    df_hash = df[df['hash_dedup'].notna() & (df['hash_dedup'] != '')]
    if len(df_hash) > 0:
        for hash_val, group in df_hash.groupby('hash_dedup'):
            if len(group) < 2:
                continue
            ok, motivo = validate_group(group)
            if ok:
                unique_rows.append(merge_group(group, 'deterministic', 1.0))
                processed_ids.update(group['id'].tolist())
                n_det_groups += 1
            else:
                ids = group['id'].tolist()
                nomes = group['nome_limpo'].tolist()
                for i in range(min(len(ids) - 1, 5)):
                    quarantine_rows.append({
                        'clean_id_a': int(ids[0]), 'clean_id_b': int(ids[i+1]),
                        'nome_a': nomes[0], 'nome_b': nomes[i+1],
                        'match_probability': 1.0, 'motivo': f"hash_{motivo}"
                    })

    # ── NIVEL 1b: ean_gtin ──
    df_ean = df[(df['ean_gtin'].notna()) & (df['ean_gtin'] != '') & (~df['id'].isin(processed_ids))]
    if len(df_ean) > 0:
        for ean_val, group in df_ean.groupby('ean_gtin'):
            if len(group) < 2:
                continue
            ok, motivo = validate_group(group)
            if ok:
                unique_rows.append(merge_group(group, 'deterministic', 1.0))
                processed_ids.update(group['id'].tolist())
                n_det_groups += 1
            else:
                ids = group['id'].tolist()
                nomes = group['nome_limpo'].tolist()
                for i in range(min(len(ids) - 1, 5)):
                    quarantine_rows.append({
                        'clean_id_a': int(ids[0]), 'clean_id_b': int(ids[i+1]),
                        'nome_a': nomes[0], 'nome_b': nomes[i+1],
                        'match_probability': 1.0, 'motivo': f"ean_{motivo}"
                    })

    # ── NIVEL 1c: nome_normalizado + safra ──
    df_nome = df[~df['id'].isin(processed_ids)].copy()
    df_nome['safra_key'] = df_nome['safra'].fillna(-1).astype(int)
    for (nome, safra_key), group in df_nome.groupby(['nome_normalizado', 'safra_key']):
        if len(group) < 2:
            continue
        ok, motivo = validate_group(group)
        if ok:
            unique_rows.append(merge_group(group, 'deterministic', 1.0))
            processed_ids.update(group['id'].tolist())
            n_det_groups += 1
        else:
            ids = group['id'].tolist()
            nomes = group['nome_limpo'].tolist()
            for i in range(min(len(ids) - 1, 5)):
                quarantine_rows.append({
                    'clean_id_a': int(ids[0]), 'clean_id_b': int(ids[i+1]),
                    'nome_a': nomes[0], 'nome_b': nomes[i+1],
                    'match_probability': 1.0, 'motivo': f"nome_{motivo}"
                })

    del df_nome
    n_det_merged = sum(r['total_copias'] for r in unique_rows if r['match_type'] == 'deterministic')
    print(f"  Nivel 1: {n_det_groups:,} grupos ({n_det_merged:,} vinhos)")

    # ── NIVEL 2: Splink ──
    df_remaining = df[~df['id'].isin(processed_ids)].copy()
    n_splink_groups = 0
    n_splink_merged = 0

    if len(df_remaining) >= 100:
        try:
            import splink.comparison_library as cl
            import splink.blocking_rule_library as brl
            from splink import DuckDBAPI, Linker, SettingsCreator, block_on

            print(f"  Splink: {len(df_remaining):,} vinhos restantes...")

            df_splink = df_remaining[['id', 'nome_normalizado', 'produtor_normalizado',
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

            db_api = DuckDBAPI()
            linker = Linker(df_splink, settings, db_api)

            linker.training.estimate_probability_two_random_records_match(training_block_nome, recall=0.7)
            linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)
            linker.training.estimate_parameters_using_expectation_maximisation(training_block_nome, fix_u_probabilities=True)
            linker.training.estimate_parameters_using_expectation_maximisation(training_block_produtor, fix_u_probabilities=True)

            results = linker.inference.predict(threshold_match_probability=REVIEW_THRESHOLD)
            df_predictions = results.as_pandas_dataframe()

            if len(df_predictions) > 0:
                # Quarentena
                df_review = df_predictions[
                    (df_predictions["match_probability"] >= REVIEW_THRESHOLD) &
                    (df_predictions["match_probability"] < MATCH_THRESHOLD)
                ]
                if len(df_review) > 0:
                    id_to_nome = df_remaining.set_index('id')['nome_limpo'].to_dict()
                    for _, row in df_review.iterrows():
                        id_l = int(row.get('id_l', row.get('unique_id_l', 0)))
                        id_r = int(row.get('id_r', row.get('unique_id_r', 0)))
                        quarantine_rows.append({
                            'clean_id_a': id_l, 'clean_id_b': id_r,
                            'nome_a': id_to_nome.get(id_l, ''),
                            'nome_b': id_to_nome.get(id_r, ''),
                            'match_probability': float(row['match_probability']),
                            'motivo': 'splink_uncertain',
                        })
                    print(f"  Splink quarentena: {len(df_review):,} pares")

                # Clusters
                clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
                    results, threshold_match_probability=MATCH_THRESHOLD)
                df_clusters = clusters.as_pandas_dataframe()

                if len(df_clusters) > 0:
                    cluster_col = 'cluster_id' if 'cluster_id' in df_clusters.columns else df_clusters.columns[-1]
                    id_col = 'id' if 'id' in df_clusters.columns else df_clusters.columns[0]

                    for cluster_id, cluster in df_clusters.groupby(cluster_col):
                        ids_in_cluster = cluster[id_col].tolist()
                        if len(ids_in_cluster) < 2:
                            continue
                        group_data = df_remaining[df_remaining['id'].isin(ids_in_cluster)]
                        if len(group_data) < 2:
                            continue

                        ok, motivo = validate_group(group_data)
                        if ok:
                            unique_rows.append(merge_group(group_data, 'splink_high', float(MATCH_THRESHOLD)))
                            processed_ids.update(ids_in_cluster)
                            n_splink_groups += 1
                            n_splink_merged += len(ids_in_cluster)
                        else:
                            ids = group_data['id'].tolist()
                            nomes = group_data['nome_limpo'].tolist()
                            for i in range(min(len(ids) - 1, 5)):
                                quarantine_rows.append({
                                    'clean_id_a': int(ids[0]), 'clean_id_b': int(ids[i+1]),
                                    'nome_a': nomes[0], 'nome_b': nomes[i+1],
                                    'match_probability': float(MATCH_THRESHOLD),
                                    'motivo': f"splink_{motivo}",
                                })

            # Cleanup Splink
            del df_splink, linker, db_api, results, df_predictions
            gc.collect()

            print(f"  Splink: {n_splink_groups:,} clusters ({n_splink_merged:,} vinhos)")

        except Exception as e:
            print(f"  [WARN] Splink falhou para {pais.upper()}: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"  Splink: pulando ({len(df_remaining):,} restantes < 100)")

    # ── Singletons ──
    df_singletons = df[~df['id'].isin(processed_ids)]
    n_singletons = len(df_singletons)
    for _, row in df_singletons.iterrows():
        unique_rows.append(make_singleton(row))
    print(f"  Singletons: {n_singletons:,}")

    # ── INSERT ──
    print(f"  Inserindo {len(unique_rows):,} em {TABLE_UNIQUE}...")
    insert_batch(cur, conn, TABLE_UNIQUE, unique_rows)

    if quarantine_rows:
        print(f"  Inserindo {len(quarantine_rows):,} em {TABLE_QUARANTINE}...")
        insert_quarantine(cur, conn, TABLE_QUARANTINE, quarantine_rows)

    elapsed_pais = time.time() - t_pais
    print(f"  {pais.upper()} concluido: {total_pais:,} -> {len(unique_rows):,} unicos em {elapsed_pais:.1f}s")

    # Cleanup
    del df, df_remaining, df_singletons, unique_rows, quarantine_rows
    gc.collect()

    return {
        'input': total_pais,
        'det_groups': n_det_groups,
        'splink_groups': n_splink_groups,
        'quarantine': len(quarantine_rows) if 'quarantine_rows' in dir() else 0,
        'unique': total_pais,  # will be recounted from DB
    }


# ── Main ──

def main():
    t0 = time.time()
    print(f"=== DEDUP GRUPO {GROUP} -- Paises: {', '.join(p.upper() for p in PAISES)} ===\n")

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    # ── Criar tabelas de destino ──
    print("[X8] Criando tabelas de destino...")
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

    # ── Contar total ──
    paises_str = ",".join(f"'{p}'" for p in PAISES)
    cur.execute(f"SELECT pais_tabela, COUNT(*) FROM wines_clean WHERE pais_tabela IN ({paises_str}) GROUP BY pais_tabela ORDER BY COUNT(*) DESC")
    pais_counts = cur.fetchall()
    total_input = sum(c for _, c in pais_counts)
    print(f"[X8] Total: {total_input:,} vinhos")
    for p, c in pais_counts:
        print(f"  {p.upper()}: {c:,}")

    # ── Processar cada pais individualmente ──
    total_det = 0
    total_splink = 0

    for pais in PAISES:
        stats = process_country(pais, conn, cur)
        total_det += stats['det_groups']
        total_splink += stats['splink_groups']

    # ── Verificacoes finais ──
    print(f"\n{'='*60}")
    print("[X8] Verificacoes finais...")
    print(f"{'='*60}")

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
    print(f"\n{'='*60}")
    print("EXEMPLOS -- Merges Nivel 1 (deterministico)")
    print(f"{'='*60}")
    cur.execute(f"""
        SELECT nome_limpo, produtor, safra, tipo, pais_tabela, total_copias, clean_ids
        FROM {TABLE_UNIQUE}
        WHERE match_type = 'deterministic' AND total_copias > 1
        ORDER BY total_copias DESC
        LIMIT 10;
    """)
    for row in cur.fetchall():
        nome, produtor, safra, tipo, pais_t, copias, ids = row
        print(f"  [{pais_t.upper()}] {nome} | {produtor or '?'} | {safra or '?'} | {tipo or '?'} | {copias} copias | IDs: {ids[:5]}{'...' if len(ids) > 5 else ''}")

    print(f"\n{'='*60}")
    print("EXEMPLOS -- Merges Nivel 2 (Splink)")
    print(f"{'='*60}")
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
            nome, produtor, safra, tipo, pais_t, copias, prob, ids = row
            print(f"  [{pais_t.upper()}] {nome} | {produtor or '?'} | {safra or '?'} | prob={prob:.2f} | {copias} copias")
    else:
        print("  (nenhum merge Splink neste grupo)")

    # ── Relatorio final ──
    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"=== GRUPO {GROUP} CONCLUIDO ===")
    print(f"{'='*60}")
    print(f"Paises: {', '.join(p.upper() for p in PAISES)}")
    print(f"Input: {total_input:,} vinhos de wines_clean")
    print(f"Nivel 1 (deterministico): {total_det:,} grupos")
    print(f"Nivel 2 (Splink): {total_splink:,} grupos adicionais")
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
    print("\n[X8] Done!")


if __name__ == "__main__":
    main()
