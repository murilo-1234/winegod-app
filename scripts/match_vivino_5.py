"""
CHAT Y5 — Match Vinhos de Loja contra Vivino (Grupo 5 de 15)
Faixa: wines_unique WHERE id >= 784613 AND id <= 980765
"""

import sys
import time
import os
import psycopg2
import pandas as pd
import numpy as np

# === CONFIG ===
LOCAL_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
RENDER_URL = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod"

ID_MIN = 784613
ID_MAX = 980765
GROUP = "Y5"
TABLE = "match_results_g5"
BATCH_SIZE = 5000


def log(msg):
    print(f"[{GROUP}] {msg}", flush=True)


def create_result_table(conn):
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id SERIAL PRIMARY KEY,
            unique_id INTEGER NOT NULL,
            vivino_id INTEGER,
            match_level VARCHAR(20) NOT NULL,
            match_probability REAL,
            vivino_nome TEXT,
            loja_nome TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mr5_uid ON {TABLE} (unique_id);
        CREATE INDEX IF NOT EXISTS idx_mr5_vid ON {TABLE} (vivino_id) WHERE vivino_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_mr5_level ON {TABLE} (match_level);
    """)
    conn.commit()
    cur.close()


def insert_batch(conn, rows):
    if not rows:
        return
    cur = conn.cursor()
    args = ",".join(
        cur.mogrify("(%s,%s,%s,%s,%s,%s)", r).decode() for r in rows
    )
    cur.execute(f"""
        INSERT INTO {TABLE} (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)
        VALUES {args}
    """)
    conn.commit()
    cur.close()


def flush_rows(conn, buffer):
    for i in range(0, len(buffer), BATCH_SIZE):
        insert_batch(conn, buffer[i : i + BATCH_SIZE])


def load_vivino():
    """Load Vivino wines from cache or Render with OFFSET/LIMIT batches."""
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vivino_cache.parquet')
    cols = ['vivino_id', 'nome_normalizado', 'produtor_normalizado', 'safra',
            'tipo', 'pais_code', 'regiao', 'hash_dedup', 'ean_gtin', 'nome']

    if os.path.exists(cache_path):
        log("Carregando Vivino do cache parquet...")
        df = pd.read_parquet(cache_path)
        log(f"Vivino cache: {len(df):,} vinhos")
        return df

    log("Carregando wines Vivino (Render) em batches OFFSET/LIMIT...")
    FETCH_SIZE = 100_000
    chunks = []
    offset = 0
    while True:
        rows = None
        for retry in range(5):
            try:
                cr = psycopg2.connect(RENDER_URL, connect_timeout=30,
                                      keepalives=1, keepalives_idle=30,
                                      keepalives_interval=10, keepalives_count=5)
                cur = cr.cursor()
                cur.execute(f"""
                    SELECT id, nome_normalizado, produtor_normalizado, safra,
                           tipo, pais, regiao, hash_dedup, ean_gtin, nome
                    FROM wines ORDER BY id
                    LIMIT {FETCH_SIZE} OFFSET {offset}
                """)
                rows = cur.fetchall()
                cur.close()
                cr.close()
                break
            except Exception as e:
                log(f"  Retry {retry+1} offset={offset}: {e}")
                time.sleep(3 * (retry + 1))
                if retry == 4:
                    raise
        if not rows:
            break
        chunks.append(pd.DataFrame(rows, columns=cols))
        offset += len(rows)
        log(f"  Vivino: {offset:,} lidos...")

    df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(columns=cols)
    df.to_parquet(cache_path, index=False)
    log(f"Vivino carregado e cacheado: {len(df):,} vinhos")
    return df


def main():
    t0 = time.time()
    log(f"Iniciando match — IDs {ID_MIN} a {ID_MAX}")

    # --- PASSO 0: Carregar dados ---
    log("Carregando wines_unique (local)...")
    conn_local = psycopg2.connect(LOCAL_URL)
    df_loja = pd.read_sql(f"""
        SELECT id, nome_normalizado, produtor_normalizado, safra,
               tipo, pais_tabela, regiao, hash_dedup, ean_gtin, nome_limpo
        FROM wines_unique
        WHERE id >= {ID_MIN} AND id <= {ID_MAX}
    """, conn_local)
    log(f"Loja: {len(df_loja):,} vinhos carregados")

    df_vivino = load_vivino()
    log(f"Vivino: {len(df_vivino):,} vinhos total")

    # Converter safra Vivino (varchar) pra Int64
    df_vivino['safra'] = pd.to_numeric(df_vivino['safra'], errors='coerce').astype('Int64')
    df_loja['safra'] = df_loja['safra'].astype('Int64')

    # Tracking
    matched_ids = set()
    results_buffer = []
    stats = {'hash': 0, 'ean': 0, 'exact_name': 0, 'exact_name_no_safra': 0, 'splink_high': 0, 'no_match': 0}

    # Criar tabela resultado
    create_result_table(conn_local)

    # --- NIVEL 1a: Match por hash_dedup ---
    log("Nivel 1a: hash_dedup...")
    loja_hash = df_loja[df_loja['hash_dedup'].notna()].copy()
    vivino_hash = df_vivino[df_vivino['hash_dedup'].notna()][['vivino_id', 'hash_dedup', 'nome']].copy()

    if len(loja_hash) > 0 and len(vivino_hash) > 0:
        matches_hash = loja_hash.merge(vivino_hash, on='hash_dedup', how='inner')
        matches_hash = matches_hash.merge(
            df_vivino[['vivino_id', 'tipo']].rename(columns={'tipo': 'tipo_vivino'}),
            on='vivino_id', how='left'
        )
        matches_hash = matches_hash[
            (matches_hash['tipo'].isna()) |
            (matches_hash['tipo_vivino'].isna()) |
            (matches_hash['tipo'] == matches_hash['tipo_vivino'])
        ]
        matches_hash = matches_hash.drop_duplicates(subset='id', keep='first')

        for _, row in matches_hash.iterrows():
            results_buffer.append((
                int(row['id']), int(row['vivino_id']), 'hash', 1.0,
                row.get('nome', None), row.get('nome_limpo', None)
            ))
        matched_ids.update(matches_hash['id'].tolist())
        stats['hash'] = len(matches_hash)

    log(f"Nivel 1a: {stats['hash']:,} matches por hash")

    # --- NIVEL 1b: Match por ean_gtin ---
    log("Nivel 1b: ean_gtin...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    loja_ean = remaining[remaining['ean_gtin'].notna()].copy()
    vivino_ean = df_vivino[df_vivino['ean_gtin'].notna()][['vivino_id', 'ean_gtin', 'nome']].copy()

    if len(loja_ean) > 0 and len(vivino_ean) > 0:
        matches_ean = loja_ean.merge(vivino_ean, on='ean_gtin', how='inner')
        matches_ean = matches_ean.merge(
            df_vivino[['vivino_id', 'tipo']].rename(columns={'tipo': 'tipo_vivino'}),
            on='vivino_id', how='left'
        )
        matches_ean = matches_ean[
            (matches_ean['tipo'].isna()) |
            (matches_ean['tipo_vivino'].isna()) |
            (matches_ean['tipo'] == matches_ean['tipo_vivino'])
        ]
        matches_ean = matches_ean.drop_duplicates(subset='id', keep='first')

        for _, row in matches_ean.iterrows():
            results_buffer.append((
                int(row['id']), int(row['vivino_id']), 'ean', 1.0,
                row.get('nome', None), row.get('nome_limpo', None)
            ))
        matched_ids.update(matches_ean['id'].tolist())
        stats['ean'] = len(matches_ean)

    log(f"Nivel 1b: {stats['ean']:,} matches por EAN")

    # --- NIVEL 1c: Match por nome_normalizado + safra ---
    log("Nivel 1c: nome_normalizado + safra...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_with_safra = remaining[remaining['safra'].notna()].copy()
    vivino_with_safra = df_vivino[df_vivino['safra'].notna()][
        ['vivino_id', 'nome_normalizado', 'safra', 'nome', 'tipo']
    ].copy()

    if len(remaining_with_safra) > 0 and len(vivino_with_safra) > 0:
        matches_exact = remaining_with_safra.merge(
            vivino_with_safra,
            on=['nome_normalizado', 'safra'],
            how='inner',
            suffixes=('', '_vivino')
        )
        matches_exact = matches_exact[
            (matches_exact['tipo'].isna()) |
            (matches_exact['tipo_vivino'].isna()) |
            (matches_exact['tipo'] == matches_exact['tipo_vivino'])
        ]
        matches_exact = matches_exact.drop_duplicates(subset='id', keep='first')

        for _, row in matches_exact.iterrows():
            results_buffer.append((
                int(row['id']), int(row['vivino_id']), 'exact_name', 1.0,
                row.get('nome', None), row.get('nome_limpo', None)
            ))
        matched_ids.update(matches_exact['id'].tolist())
        stats['exact_name'] = len(matches_exact)

    log(f"Nivel 1c: {stats['exact_name']:,} matches por nome+safra")

    # --- NIVEL 1d: Match por nome_normalizado sem safra (ambos NULL) ---
    log("Nivel 1d: nome_normalizado sem safra...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_no_safra = remaining[remaining['safra'].isna()].copy()
    vivino_no_safra = df_vivino[df_vivino['safra'].isna()][
        ['vivino_id', 'nome_normalizado', 'nome', 'tipo']
    ].copy()

    if len(remaining_no_safra) > 0 and len(vivino_no_safra) > 0:
        matches_no_safra = remaining_no_safra.merge(
            vivino_no_safra,
            on='nome_normalizado',
            how='inner',
            suffixes=('', '_vivino')
        )
        matches_no_safra = matches_no_safra[
            (matches_no_safra['tipo'].isna()) |
            (matches_no_safra['tipo_vivino'].isna()) |
            (matches_no_safra['tipo'] == matches_no_safra['tipo_vivino'])
        ]
        matches_no_safra = matches_no_safra.drop_duplicates(subset='id', keep='first')

        for _, row in matches_no_safra.iterrows():
            results_buffer.append((
                int(row['id']), int(row['vivino_id']), 'exact_name', 1.0,
                row.get('nome', None), row.get('nome_limpo', None)
            ))
        matched_ids.update(matches_no_safra['id'].tolist())
        stats['exact_name_no_safra'] = len(matches_no_safra)

    log(f"Nivel 1d: {stats['exact_name_no_safra']:,} matches por nome (sem safra)")

    # Flush nivel 1
    log("Salvando nivel 1...")
    flush_rows(conn_local, results_buffer)
    n1_total = len(results_buffer)
    results_buffer.clear()
    log(f"Nivel 1 completo: {n1_total:,} matches salvos")

    # --- NIVEL 2: Splink ---
    remaining = df_loja[~df_loja['id'].isin(matched_ids)].copy()
    log(f"Nivel 2: Splink com {len(remaining):,} vinhos restantes...")

    if len(remaining) > 0:
        import splink.comparison_library as cl
        import splink.blocking_rule_library as brl
        from splink import DuckDBAPI, Linker, SettingsCreator, block_on

        # Preparar DataFrames
        df_left = remaining.rename(columns={'id': 'unique_id', 'pais_tabela': 'pais_code'}).copy()
        df_left['source_dataset'] = 'loja'

        df_right = df_vivino.rename(columns={'vivino_id': 'unique_id'}).copy()
        df_right['source_dataset'] = 'vivino'

        cols = ['unique_id', 'nome_normalizado', 'produtor_normalizado',
                'safra', 'tipo', 'pais_code', 'regiao', 'source_dataset']

        df_left = df_left[[c for c in cols if c in df_left.columns]].copy()
        df_right = df_right[[c for c in cols if c in df_right.columns]].copy()

        # Converter safra pra string pro Splink
        df_left['safra'] = df_left['safra'].astype(str)
        df_right['safra'] = df_right['safra'].astype(str)
        df_left.loc[df_left['safra'].isin(['<NA>', 'nan', 'None', '']), 'safra'] = None
        df_right.loc[df_right['safra'].isin(['<NA>', 'nan', 'None', '']), 'safra'] = None

        # NaN em texto -> None
        for col in ['nome_normalizado', 'produtor_normalizado', 'regiao', 'tipo', 'pais_code']:
            if col in df_left.columns:
                df_left[col] = df_left[col].where(df_left[col].notna(), None)
            if col in df_right.columns:
                df_right[col] = df_right[col].where(df_right[col].notna(), None)

        settings = SettingsCreator(
            link_type="link_only",
            unique_id_column_name="unique_id",
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
                cl.ExactMatch("pais_code"),
                cl.JaroWinklerAtThresholds(
                    col_name="regiao",
                    score_threshold_or_thresholds=[0.88],
                ),
            ],
            blocking_rules_to_generate_predictions=[
                block_on("nome_normalizado"),
                block_on("produtor_normalizado", "pais_code"),
                brl.CustomRule(
                    "SUBSTR(l.nome_normalizado,1,10) = SUBSTR(r.nome_normalizado,1,10) "
                    "AND l.pais_code = r.pais_code"
                ),
            ],
            retain_matching_columns=True,
        )

        log("Splink: Inicializando linker...")
        db_api = DuckDBAPI()
        linker = Linker([df_left, df_right], settings, db_api)

        log("Splink: Treinando modelo...")
        training_block_nome = block_on("nome_normalizado")
        training_block_produtor = block_on("produtor_normalizado")

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

        log("Splink: Predizendo matches...")
        results = linker.inference.predict(threshold_match_probability=0.50)
        df_predictions = results.as_pandas_dataframe()
        log(f"Splink: {len(df_predictions):,} pares candidatos (prob >= 0.50)")

        if len(df_predictions) > 0:
            df_pred = df_predictions.copy()

            # Mapas de tipo pra validacao
            vivino_tipo_map = df_vivino.set_index(
                df_vivino['vivino_id'].astype(str)
            )['tipo'].to_dict()
            loja_tipo_map = remaining.set_index(
                remaining['id'].astype(str)
            )['tipo'].to_dict()

            def tipo_ok(row):
                lid = str(row.get('unique_id_l', ''))
                rid = str(row.get('unique_id_r', ''))
                t_loja = loja_tipo_map.get(lid)
                t_viv = vivino_tipo_map.get(rid)
                if t_loja is None or t_viv is None:
                    return True
                return t_loja == t_viv

            df_pred['tipo_ok'] = df_pred.apply(tipo_ok, axis=1)
            df_pred = df_pred[df_pred['tipo_ok']].copy()

            # So matches >= 0.80
            df_high = df_pred[df_pred['match_probability'] >= 0.80].copy()
            df_high = df_high.sort_values('match_probability', ascending=False)
            df_high = df_high.drop_duplicates(subset='unique_id_l', keep='first')

            # Mapear nomes
            vivino_nome_map = df_vivino.set_index(
                df_vivino['vivino_id'].astype(str)
            )['nome'].to_dict()
            loja_nome_map = remaining.set_index(
                remaining['id'].astype(str)
            )['nome_limpo'].to_dict()

            for _, row in df_high.iterrows():
                uid = int(row['unique_id_l'])
                vid = int(row['unique_id_r'])
                prob = float(row['match_probability'])
                v_nome = vivino_nome_map.get(str(vid))
                l_nome = loja_nome_map.get(str(uid))
                results_buffer.append((uid, vid, 'splink_high', prob, v_nome, l_nome))

            matched_ids.update(df_high['unique_id_l'].astype(int).tolist())
            stats['splink_high'] = len(df_high)

        log(f"Nivel 2: {stats['splink_high']:,} matches Splink (prob >= 0.80)")
        flush_rows(conn_local, results_buffer)
        results_buffer.clear()

    # --- NIVEL 3: Sem match ---
    remaining_final = df_loja[~df_loja['id'].isin(matched_ids)].copy()
    stats['no_match'] = len(remaining_final)
    log(f"Nivel 3: {stats['no_match']:,} vinhos sem match")

    no_match_rows = []
    for _, row in remaining_final.iterrows():
        no_match_rows.append((
            int(row['id']), None, 'no_match', None, None, row.get('nome_limpo', None)
        ))
    flush_rows(conn_local, no_match_rows)

    elapsed = time.time() - t0

    # --- ENTREGAVEL ---
    total_input = len(df_loja)
    total_vivino = len(df_vivino)
    total_match = total_input - stats['no_match']
    taxa = (total_match / total_input * 100) if total_input > 0 else 0
    exact_name_total = stats['exact_name'] + stats['exact_name_no_safra']

    print(f"\n{'='*50}", flush=True)
    print(f"=== GRUPO {GROUP} CONCLUIDO ===", flush=True)
    print(f"{'='*50}", flush=True)
    print(f"Input: {total_input:,} vinhos de wines_unique (IDs {ID_MIN} a {ID_MAX})", flush=True)
    print(f"Vivino carregado: {total_vivino:,} vinhos", flush=True)
    print(flush=True)
    print(f"Nivel 1 (hash):       {stats['hash']:,} matches", flush=True)
    print(f"Nivel 1 (ean):        {stats['ean']:,} matches", flush=True)
    print(f"Nivel 1 (nome exato): {exact_name_total:,} matches", flush=True)
    print(f"Nivel 2 (Splink):     {stats['splink_high']:,} matches", flush=True)
    print(f"Sem match:            {stats['no_match']:,} vinhos", flush=True)
    print(flush=True)
    print(f"Taxa de match: {taxa:.1f}% encontraram par no Vivino", flush=True)
    print(f"Tabela: {TABLE} populada com {total_input:,} registros", flush=True)
    print(f"Tempo total: {elapsed/60:.1f} minutos", flush=True)

    # Exemplos
    print(f"\n--- Exemplos Nivel 1 ---", flush=True)
    cur = conn_local.cursor()
    cur.execute(f"""
        SELECT match_level, loja_nome, vivino_nome, match_probability
        FROM {TABLE}
        WHERE match_level IN ('hash', 'ean', 'exact_name')
        AND vivino_nome IS NOT NULL AND loja_nome IS NOT NULL
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"[{row[0].upper()}] \"{row[1]}\" (loja) -> \"{row[2]}\" (vivino) | prob={row[3]}", flush=True)

    print(f"\n--- Exemplos Nivel 2 (Splink) ---", flush=True)
    cur.execute(f"""
        SELECT match_level, loja_nome, vivino_nome, match_probability
        FROM {TABLE}
        WHERE match_level = 'splink_high'
        AND vivino_nome IS NOT NULL AND loja_nome IS NOT NULL
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"[SPLINK] \"{row[1]}\" (loja) -> \"{row[2]}\" (vivino) | prob={row[3]:.2f}", flush=True)

    cur.close()
    conn_local.close()
    log("Finalizado!")


if __name__ == "__main__":
    main()
