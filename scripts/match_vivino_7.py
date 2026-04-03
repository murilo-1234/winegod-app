"""
CHAT Y7 — Match Vinhos de Loja contra Vivino (Grupo 7 de 15)
Faixa: wines_unique WHERE id >= 1176919 AND id <= 1373071
"""

import psycopg2
import pandas as pd
import numpy as np
import time
import sys

# --- Credenciais ---
LOCAL_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
RENDER_URL = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod"

# --- Faixa deste grupo ---
ID_MIN = 1176919
ID_MAX = 1373071
GROUP = "Y7"
TABLE = "match_results_g7"
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
    """)
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_mr7_uid ON {TABLE} (unique_id);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_mr7_vid ON {TABLE} (vivino_id) WHERE vivino_id IS NOT NULL;")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_mr7_level ON {TABLE} (match_level);")
    conn.commit()
    cur.close()

def insert_matches(conn, rows):
    if not rows:
        return
    cur = conn.cursor()
    args = ",".join(
        cur.mogrify("(%s,%s,%s,%s,%s,%s)", r).decode()
        for r in rows
    )
    cur.execute(f"""
        INSERT INTO {TABLE} (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)
        VALUES {args}
    """)
    conn.commit()
    cur.close()

def main():
    t0 = time.time()

    # --- PASSO 0: Carregar dados ---
    log("Conectando ao banco local...")
    conn_local = psycopg2.connect(LOCAL_URL)

    log("Criando tabela de resultado...")
    create_result_table(conn_local)

    # Limpar resultados anteriores (se re-executar)
    cur = conn_local.cursor()
    cur.execute(f"DELETE FROM {TABLE};")
    conn_local.commit()
    cur.close()

    log(f"Carregando wines_unique (IDs {ID_MIN} a {ID_MAX})...")
    df_loja = pd.read_sql(f"""
        SELECT id, nome_normalizado, produtor_normalizado, safra,
               tipo, pais_tabela, regiao, hash_dedup, ean_gtin, nome_limpo
        FROM wines_unique
        WHERE id >= {ID_MIN} AND id <= {ID_MAX}
    """, conn_local)
    log(f"Loja carregado: {len(df_loja):,} vinhos")

    # Tentar carregar cache local primeiro (parquet)
    import os
    cache_file = os.path.join(os.path.dirname(__file__), 'vivino_cache.parquet')
    if os.path.exists(cache_file):
        log(f"Carregando Vivino do cache local: {cache_file}")
        df_vivino = pd.read_parquet(cache_file)
        log(f"Vivino carregado do cache: {len(df_vivino):,} vinhos")
    else:
        log("Carregando wines Vivino (Render) em chunks com reconexao...")
        chunks = []
        chunk_size = 30000
        offset = 0
        cols = ['vivino_id', 'nome_normalizado', 'produtor_normalizado', 'safra',
                'tipo', 'pais_code', 'regiao', 'hash_dedup', 'ean_gtin', 'nome']
        while True:
            for attempt in range(10):
                try:
                    conn_render = psycopg2.connect(RENDER_URL, sslmode='require',
                                                   connect_timeout=60, keepalives=1,
                                                   keepalives_idle=10, keepalives_interval=5,
                                                   keepalives_count=10)
                    cur_r = conn_render.cursor()
                    cur_r.execute(f"""
                        SELECT id as vivino_id, nome_normalizado, produtor_normalizado, safra,
                               tipo, pais as pais_code, regiao, hash_dedup, ean_gtin, nome
                        FROM wines
                        ORDER BY id
                        LIMIT {chunk_size} OFFSET {offset}
                    """)
                    rows = cur_r.fetchall()
                    cur_r.close()
                    conn_render.close()
                    break
                except Exception as e:
                    log(f"  Tentativa {attempt+1}/10 falhou (offset={offset}): {e}")
                    try:
                        conn_render.close()
                    except:
                        pass
                    if attempt == 9:
                        raise
                    time.sleep(5 * (attempt + 1))
            if not rows:
                break
            chunks.append(pd.DataFrame(rows, columns=cols))
            offset += chunk_size
            log(f"  Vivino: {offset:,} registros carregados...")
        df_vivino = pd.concat(chunks, ignore_index=True)
        log(f"Vivino carregado: {len(df_vivino):,} vinhos")
        # Salvar cache pra outros grupos
        df_vivino.to_parquet(cache_file, index=False)
        log(f"Cache salvo em: {cache_file}")

    # Converter safra do Vivino pra int
    df_vivino['safra'] = pd.to_numeric(df_vivino['safra'], errors='coerce').astype('Int64')

    log(f"Loja: {len(df_loja):,} | Vivino: {len(df_vivino):,}")

    total_loja = len(df_loja)
    matched_ids = set()
    all_results = []  # (unique_id, vivino_id, match_level, prob, vivino_nome, loja_nome)

    # --- NIVEL 1a: Match por hash_dedup ---
    log("Nivel 1a: Match por hash_dedup...")
    loja_hash = df_loja[df_loja['hash_dedup'].notna()].copy()
    viv_hash = df_vivino[df_vivino['hash_dedup'].notna()][['vivino_id', 'hash_dedup', 'nome']].copy()
    matches_hash = loja_hash.merge(viv_hash, on='hash_dedup', how='inner')
    matches_hash = matches_hash.drop_duplicates(subset='id', keep='first')

    # Validacao de tipo
    if 'tipo' in matches_hash.columns:
        # merge tipo do vivino
        viv_tipo = df_vivino[['vivino_id', 'tipo']].rename(columns={'tipo': 'tipo_vivino'})
        matches_hash = matches_hash.merge(viv_tipo, on='vivino_id', how='left')
        mask_tipo_ok = (
            matches_hash['tipo'].isna() |
            matches_hash['tipo_vivino'].isna() |
            (matches_hash['tipo'] == matches_hash['tipo_vivino'])
        )
        matches_hash = matches_hash[mask_tipo_ok]

    for _, r in matches_hash.iterrows():
        all_results.append((int(r['id']), int(r['vivino_id']), 'hash', 1.0, r.get('nome', ''), r.get('nome_limpo', '')))
    matched_ids.update(matches_hash['id'].tolist())
    n_hash = len(matches_hash)
    log(f"Nivel 1a (hash): {n_hash:,} matches")

    # --- NIVEL 1b: Match por ean_gtin ---
    log("Nivel 1b: Match por ean_gtin...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    loja_ean = remaining[remaining['ean_gtin'].notna() & (remaining['ean_gtin'] != '')].copy()
    viv_ean = df_vivino[df_vivino['ean_gtin'].notna() & (df_vivino['ean_gtin'] != '')][['vivino_id', 'ean_gtin', 'nome']].copy()
    matches_ean = loja_ean.merge(viv_ean, on='ean_gtin', how='inner')
    matches_ean = matches_ean.drop_duplicates(subset='id', keep='first')

    # Validacao de tipo
    if len(matches_ean) > 0:
        matches_ean = matches_ean.merge(viv_tipo, on='vivino_id', how='left')
        mask_tipo_ok = (
            matches_ean['tipo'].isna() |
            matches_ean['tipo_vivino'].isna() |
            (matches_ean['tipo'] == matches_ean['tipo_vivino'])
        )
        matches_ean = matches_ean[mask_tipo_ok]

    for _, r in matches_ean.iterrows():
        all_results.append((int(r['id']), int(r['vivino_id']), 'ean', 1.0, r.get('nome', ''), r.get('nome_limpo', '')))
    matched_ids.update(matches_ean['id'].tolist())
    n_ean = len(matches_ean)
    log(f"Nivel 1b (ean): {n_ean:,} matches")

    # --- NIVEL 1c: Match por nome_normalizado + safra exato ---
    log("Nivel 1c: Match por nome_normalizado + safra...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_with_safra = remaining[remaining['nome_normalizado'].notna() & remaining['safra'].notna()].copy()
    viv_with_safra = df_vivino[df_vivino['nome_normalizado'].notna() & df_vivino['safra'].notna()][['vivino_id', 'nome_normalizado', 'safra', 'nome', 'tipo']].copy()
    viv_with_safra = viv_with_safra.rename(columns={'tipo': 'tipo_vivino'})

    matches_exact = remaining_with_safra.merge(
        viv_with_safra,
        on=['nome_normalizado', 'safra'], how='inner'
    )

    # Validacao de tipo
    if len(matches_exact) > 0:
        mask_tipo_ok = (
            matches_exact['tipo'].isna() |
            matches_exact['tipo_vivino'].isna() |
            (matches_exact['tipo'] == matches_exact['tipo_vivino'])
        )
        matches_exact = matches_exact[mask_tipo_ok]

    matches_exact = matches_exact.drop_duplicates(subset='id', keep='first')
    for _, r in matches_exact.iterrows():
        all_results.append((int(r['id']), int(r['vivino_id']), 'exact_name', 1.0, r.get('nome', ''), r.get('nome_limpo', '')))
    matched_ids.update(matches_exact['id'].tolist())
    n_exact = len(matches_exact)
    log(f"Nivel 1c (nome exato + safra): {n_exact:,} matches")

    # --- NIVEL 1d: Match por nome_normalizado sem safra (ambas NULL) ---
    log("Nivel 1d: Match por nome_normalizado sem safra...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_no_safra = remaining[remaining['safra'].isna() & remaining['nome_normalizado'].notna()].copy()
    vivino_no_safra = df_vivino[df_vivino['safra'].isna() & df_vivino['nome_normalizado'].notna()][['vivino_id', 'nome_normalizado', 'nome', 'tipo']].copy()
    vivino_no_safra = vivino_no_safra.rename(columns={'tipo': 'tipo_vivino'})

    matches_no_safra = remaining_no_safra.merge(
        vivino_no_safra,
        on='nome_normalizado', how='inner'
    )

    if len(matches_no_safra) > 0:
        mask_tipo_ok = (
            matches_no_safra['tipo'].isna() |
            matches_no_safra['tipo_vivino'].isna() |
            (matches_no_safra['tipo'] == matches_no_safra['tipo_vivino'])
        )
        matches_no_safra = matches_no_safra[mask_tipo_ok]

    matches_no_safra = matches_no_safra.drop_duplicates(subset='id', keep='first')
    for _, r in matches_no_safra.iterrows():
        all_results.append((int(r['id']), int(r['vivino_id']), 'exact_name', 1.0, r.get('nome', ''), r.get('nome_limpo', '')))
    matched_ids.update(matches_no_safra['id'].tolist())
    n_no_safra = len(matches_no_safra)
    log(f"Nivel 1d (nome sem safra): {n_no_safra:,} matches")

    n_nivel1_total = n_hash + n_ean + n_exact + n_no_safra
    log(f"Nivel 1 total: {n_nivel1_total:,} matches")

    # --- Salvar resultados Nivel 1 em batches ---
    log("Salvando resultados Nivel 1...")
    for i in range(0, len(all_results), BATCH_SIZE):
        batch = all_results[i:i+BATCH_SIZE]
        insert_matches(conn_local, batch)
    log(f"Nivel 1 salvo: {len(all_results):,} registros")

    # --- NIVEL 2: Splink ---
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    n_remaining = len(remaining)
    log(f"Nivel 2: {n_remaining:,} vinhos restantes para Splink...")

    n_splink = 0
    splink_results = []

    if n_remaining > 0:
        import splink.comparison_library as cl
        import splink.blocking_rule_library as brl
        from splink import DuckDBAPI, Linker, SettingsCreator, block_on

        df_loja_remaining = remaining.copy()
        df_loja_remaining = df_loja_remaining.rename(columns={'id': 'unique_id', 'pais_tabela': 'pais_code'})
        df_loja_remaining['source_dataset'] = 'loja'

        df_vivino_splink = df_vivino.copy()
        df_vivino_splink['source_dataset'] = 'vivino'
        df_vivino_splink = df_vivino_splink.rename(columns={'vivino_id': 'unique_id', 'pais_code': 'pais_code'})

        cols = ['unique_id', 'nome_normalizado', 'produtor_normalizado',
                'safra', 'tipo', 'pais_code', 'regiao', 'source_dataset']

        df_left = df_loja_remaining[cols].copy()
        df_right = df_vivino_splink[cols].copy()

        # Converter safra pra string pro Splink
        df_left['safra'] = df_left['safra'].astype(str).replace('<NA>', None).replace('nan', None)
        df_right['safra'] = df_right['safra'].astype(str).replace('<NA>', None).replace('nan', None)

        # Replace string 'None' and 'nan' with actual None
        df_left.loc[df_left['safra'].isin(['<NA>', 'nan', 'None', 'NaT']), 'safra'] = None
        df_right.loc[df_right['safra'].isin(['<NA>', 'nan', 'None', 'NaT']), 'safra'] = None

        log("Configurando Splink...")
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

        db_api = DuckDBAPI()
        linker = Linker([df_left, df_right], settings, db_api)

        log("Treinando modelo Splink...")
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

        log("Predizendo matches...")
        results = linker.inference.predict(threshold_match_probability=0.50)
        df_predictions = results.as_pandas_dataframe()
        log(f"Splink retornou {len(df_predictions):,} pares candidatos")

        if len(df_predictions) > 0:
            # df_left e loja (posicao 0), df_right e vivino (posicao 1)
            # unique_id_l = loja, unique_id_r = vivino
            df_high = df_predictions[df_predictions['match_probability'] >= 0.80].copy()

            # Pegar o melhor match pra cada vinho de loja
            df_high = df_high.sort_values('match_probability', ascending=False)
            df_high = df_high.drop_duplicates(subset='unique_id_l', keep='first')

            # Validacao de tipo
            if 'tipo_l' in df_high.columns and 'tipo_r' in df_high.columns:
                mask_tipo_ok = (
                    df_high['tipo_l'].isna() |
                    df_high['tipo_r'].isna() |
                    (df_high['tipo_l'] == df_high['tipo_r'])
                )
                df_high = df_high[mask_tipo_ok]

            # Buscar nomes pra conferencia
            loja_nomes = df_loja.set_index('id')['nome_limpo'].to_dict()
            viv_nomes = df_vivino.set_index('vivino_id')['nome'].to_dict()

            for _, r in df_high.iterrows():
                uid = int(r['unique_id_l'])
                vid = int(r['unique_id_r'])
                prob = float(r['match_probability'])
                v_nome = viv_nomes.get(vid, '')
                l_nome = loja_nomes.get(uid, '')
                splink_results.append((uid, vid, 'splink_high', prob, v_nome, l_nome))
                matched_ids.add(uid)

            n_splink = len(splink_results)
            log(f"Nivel 2 (Splink >= 0.80): {n_splink:,} matches")

            # Salvar resultados Splink
            for i in range(0, len(splink_results), BATCH_SIZE):
                batch = splink_results[i:i+BATCH_SIZE]
                insert_matches(conn_local, batch)
    else:
        log("Nivel 2: nenhum vinho restante para Splink")

    # --- NIVEL 3: Sem match ---
    remaining_final = df_loja[~df_loja['id'].isin(matched_ids)]
    n_no_match = len(remaining_final)
    log(f"Nivel 3: {n_no_match:,} vinhos sem match")

    # Salvar no_match em batches
    no_match_results = []
    for _, r in remaining_final.iterrows():
        no_match_results.append((int(r['id']), None, 'no_match', None, None, r.get('nome_limpo', '')))

    for i in range(0, len(no_match_results), BATCH_SIZE):
        batch = no_match_results[i:i+BATCH_SIZE]
        insert_matches(conn_local, batch)

    log(f"Nivel 3 salvo: {n_no_match:,} registros no_match")

    # --- RESUMO FINAL ---
    elapsed = time.time() - t0
    total_matches = n_nivel1_total + n_splink
    taxa = (total_matches / total_loja * 100) if total_loja > 0 else 0
    total_registros = n_nivel1_total + n_splink + n_no_match

    print(f"\n{'='*50}")
    print(f"=== GRUPO {GROUP} CONCLUIDO ===")
    print(f"{'='*50}")
    print(f"Input: {total_loja:,} vinhos de wines_unique (IDs {ID_MIN} a {ID_MAX})")
    print(f"Vivino carregado: {len(df_vivino):,} vinhos")
    print()
    print(f"Nivel 1 (hash):       {n_hash:,} matches")
    print(f"Nivel 1 (ean):        {n_ean:,} matches")
    print(f"Nivel 1 (nome exato): {n_exact + n_no_safra:,} matches")
    print(f"Nivel 2 (Splink):     {n_splink:,} matches")
    print(f"Sem match:            {n_no_match:,} vinhos")
    print()
    print(f"Taxa de match: {taxa:.1f}% encontraram par no Vivino")
    print(f"Tabela: {TABLE} populada com {total_registros:,} registros")
    print(f"Tempo total: {elapsed/60:.1f} minutos")

    # --- Exemplos visuais ---
    print(f"\n--- Exemplos Nivel 1 (primeiros 10) ---")
    for row in all_results[:10]:
        uid, vid, level, prob, vn, ln = row
        print(f"[{level.upper()}] \"{ln}\" (loja) -> \"{vn}\" (vivino) | prob={prob}")

    if splink_results:
        print(f"\n--- Exemplos Nivel 2 Splink (primeiros 10) ---")
        for row in splink_results[:10]:
            uid, vid, level, prob, vn, ln = row
            print(f"[SPLINK] \"{ln}\" (loja) -> \"{vn}\" (vivino) | prob={prob:.2f}")

    conn_local.close()
    print(f"\n[{GROUP}] Done!")

if __name__ == "__main__":
    main()
