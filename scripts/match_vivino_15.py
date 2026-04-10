"""
CHAT Y15 — Match Vinhos de Loja contra Vivino (Grupo 15 de 15)
Faixa: wines_unique WHERE id >= 2746143 AND id <= 2942304
"""

import psycopg2
import psycopg2.extras
import pandas as pd
import time
import sys
import os
import _env

# === CREDENCIAIS ===
LOCAL_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
RENDER_URL = os.environ["DATABASE_URL"]

# === FAIXA ===
ID_MIN = 2746143
ID_MAX = 2942304
GROUP = "Y15"
TABLE = "match_results_g15"
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
        CREATE INDEX IF NOT EXISTS idx_mr15_uid ON {TABLE} (unique_id);
        CREATE INDEX IF NOT EXISTS idx_mr15_vid ON {TABLE} (vivino_id) WHERE vivino_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_mr15_level ON {TABLE} (match_level);
    """)
    conn.commit()
    # Limpar resultados anteriores (para re-runs)
    cur.execute(f"DELETE FROM {TABLE};")
    conn.commit()
    cur.close()

def insert_matches(conn, records):
    """Insert batch of (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)"""
    if not records:
        return
    cur = conn.cursor()
    psycopg2.extras.execute_values(
        cur,
        f"""INSERT INTO {TABLE} (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)
            VALUES %s""",
        records,
        page_size=BATCH_SIZE
    )
    conn.commit()
    cur.close()

def main():
    t0 = time.time()

    # === PASSO 0: Carregar dados ===
    log("Conectando ao banco local...")
    conn_local = psycopg2.connect(LOCAL_URL)

    log(f"Carregando wines_unique (IDs {ID_MIN} a {ID_MAX})...")
    df_loja = pd.read_sql(f"""
        SELECT id, nome_normalizado, produtor_normalizado, safra,
               tipo, pais_tabela, regiao, hash_dedup, ean_gtin, nome_limpo
        FROM wines_unique
        WHERE id >= {ID_MIN} AND id <= {ID_MAX}
    """, conn_local)
    log(f"Loja carregada: {len(df_loja):,} vinhos")

    log("Carregando TODOS os vinhos Vivino (em batches com OFFSET/LIMIT)...")
    vivino_chunks = []
    cols = ['vivino_id', 'nome_normalizado', 'produtor_normalizado', 'safra',
            'tipo', 'pais_code', 'regiao', 'hash_dedup', 'ean_gtin', 'nome']
    CHUNK = 50000
    offset = 0
    MAX_RETRIES = 10
    while True:
        rows = None
        for attempt in range(MAX_RETRIES):
            try:
                conn_render = psycopg2.connect(RENDER_URL,
                    keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
                    connect_timeout=60)
                cur = conn_render.cursor()
                cur.execute(f"""
                    SELECT id as vivino_id, nome_normalizado, produtor_normalizado, safra,
                           tipo, pais as pais_code, regiao, hash_dedup, ean_gtin, nome
                    FROM wines ORDER BY id LIMIT {CHUNK} OFFSET {offset}
                """)
                rows = cur.fetchall()
                cur.close()
                conn_render.close()
                break
            except Exception as e:
                try:
                    conn_render.close()
                except:
                    pass
                wait = min(5 * (2 ** attempt), 120)
                log(f"  Tentativa {attempt+1}/{MAX_RETRIES} falhou no offset {offset} (wait {wait}s): {e}")
                time.sleep(wait)
                if attempt == MAX_RETRIES - 1:
                    raise
        if not rows:
            break
        vivino_chunks.append(pd.DataFrame(rows, columns=cols))
        offset += CHUNK
        log(f"  Vivino: {offset:,} registros lidos...")
        time.sleep(1)  # Pausa entre batches pra nao sobrecarregar Render
    df_vivino = pd.concat(vivino_chunks, ignore_index=True)
    del vivino_chunks
    log(f"Vivino carregado: {len(df_vivino):,} vinhos")

    # Converter safra do Vivino pra int
    df_vivino['safra'] = pd.to_numeric(df_vivino['safra'], errors='coerce').astype('Int64')

    # Criar tabela de resultado
    create_result_table(conn_local)

    matched_ids = set()
    all_results = []  # (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)
    examples_nivel1 = []
    examples_nivel2 = []

    # === NIVEL 1a: Match por hash_dedup ===
    log("Nivel 1a: Match por hash_dedup...")
    loja_hash = df_loja[df_loja['hash_dedup'].notna() & (df_loja['hash_dedup'] != '')].copy()
    vivino_hash = df_vivino[df_vivino['hash_dedup'].notna() & (df_vivino['hash_dedup'] != '')][['vivino_id', 'hash_dedup', 'nome']].copy()

    matches_hash = loja_hash.merge(vivino_hash, on='hash_dedup', how='inner')
    matches_hash = matches_hash.drop_duplicates(subset='id', keep='first')

    for _, row in matches_hash.iterrows():
        all_results.append((int(row['id']), int(row['vivino_id']), 'hash', 1.0, row['nome'], row.get('nome_limpo')))
        if len(examples_nivel1) < 5:
            examples_nivel1.append(('HASH', row.get('nome_limpo', row.get('nome_normalizado', '')), row['nome'], 1.0))

    matched_ids.update(matches_hash['id'].tolist())
    count_hash = len(matches_hash)
    log(f"Nivel 1a (hash): {count_hash:,} matches")

    # === NIVEL 1b: Match por ean_gtin ===
    log("Nivel 1b: Match por ean_gtin...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    loja_ean = remaining[remaining['ean_gtin'].notna() & (remaining['ean_gtin'] != '')].copy()
    vivino_ean = df_vivino[df_vivino['ean_gtin'].notna() & (df_vivino['ean_gtin'] != '')][['vivino_id', 'ean_gtin', 'nome']].copy()

    matches_ean = loja_ean.merge(vivino_ean, on='ean_gtin', how='inner')
    matches_ean = matches_ean.drop_duplicates(subset='id', keep='first')

    for _, row in matches_ean.iterrows():
        all_results.append((int(row['id']), int(row['vivino_id']), 'ean', 1.0, row['nome'], row.get('nome_limpo')))
        if len(examples_nivel1) < 10:
            examples_nivel1.append(('EAN', row.get('nome_limpo', row.get('nome_normalizado', '')), row['nome'], 1.0))

    matched_ids.update(matches_ean['id'].tolist())
    count_ean = len(matches_ean)
    log(f"Nivel 1b (ean): {count_ean:,} matches")

    # === NIVEL 1c: Match por nome_normalizado + safra exato ===
    log("Nivel 1c: Match por nome_normalizado + safra...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_with_safra = remaining[remaining['safra'].notna()].copy()
    vivino_with_safra = df_vivino[df_vivino['safra'].notna()][['vivino_id', 'nome_normalizado', 'safra', 'nome']].copy()

    matches_exact = remaining_with_safra.merge(
        vivino_with_safra, on=['nome_normalizado', 'safra'], how='inner'
    )
    matches_exact = matches_exact.drop_duplicates(subset='id', keep='first')

    for _, row in matches_exact.iterrows():
        all_results.append((int(row['id']), int(row['vivino_id']), 'exact_name', 1.0, row['nome'], row.get('nome_limpo')))
        if len(examples_nivel1) < 10:
            examples_nivel1.append(('EXACT', row.get('nome_limpo', row.get('nome_normalizado', '')), row['nome'], 1.0))

    matched_ids.update(matches_exact['id'].tolist())
    count_exact = len(matches_exact)
    log(f"Nivel 1c (nome+safra): {count_exact:,} matches")

    # === NIVEL 1d: Match por nome_normalizado sem safra (ambas NULL) ===
    log("Nivel 1d: Match por nome_normalizado (sem safra)...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_no_safra = remaining[remaining['safra'].isna()].copy()
    vivino_no_safra = df_vivino[df_vivino['safra'].isna()][['vivino_id', 'nome_normalizado', 'nome']].copy()

    matches_no_safra = remaining_no_safra.merge(
        vivino_no_safra, on='nome_normalizado', how='inner'
    )
    matches_no_safra = matches_no_safra.drop_duplicates(subset='id', keep='first')

    for _, row in matches_no_safra.iterrows():
        all_results.append((int(row['id']), int(row['vivino_id']), 'exact_name', 1.0, row['nome'], row.get('nome_limpo')))

    matched_ids.update(matches_no_safra['id'].tolist())
    count_no_safra = len(matches_no_safra)
    log(f"Nivel 1d (nome sem safra): {count_no_safra:,} matches")

    # Salvar resultados nivel 1
    log(f"Salvando {len(all_results):,} matches nivel 1...")
    for i in range(0, len(all_results), BATCH_SIZE):
        insert_matches(conn_local, all_results[i:i+BATCH_SIZE])

    total_nivel1 = count_hash + count_ean + count_exact + count_no_safra
    log(f"Total Nivel 1: {total_nivel1:,} matches")

    # === NIVEL 2: Splink ===
    remaining = df_loja[~df_loja['id'].isin(matched_ids)].copy()
    log(f"Nivel 2 (Splink): {len(remaining):,} vinhos restantes para match probabilistico...")

    splink_results = []
    if len(remaining) > 0:
        try:
            import splink.comparison_library as cl
            import splink.blocking_rule_library as brl
            from splink import DuckDBAPI, Linker, SettingsCreator, block_on

            # Preparar DataFrames
            df_left = remaining.rename(columns={'id': 'unique_id', 'pais_tabela': 'pais_code'})[
                ['unique_id', 'nome_normalizado', 'produtor_normalizado', 'safra', 'tipo', 'pais_code', 'regiao']
            ].copy()
            df_left['source_dataset'] = 'loja'
            df_left['safra'] = df_left['safra'].astype(str).replace('<NA>', None).replace('nan', None)

            df_right = df_vivino.rename(columns={'vivino_id': 'unique_id'})[
                ['unique_id', 'nome_normalizado', 'produtor_normalizado', 'safra', 'tipo', 'pais_code', 'regiao']
            ].copy()
            df_right['source_dataset'] = 'vivino'
            df_right['safra'] = df_right['safra'].astype(str).replace('<NA>', None).replace('nan', None)

            # Substituir NaN/None em strings para evitar problemas
            for col in ['nome_normalizado', 'produtor_normalizado', 'tipo', 'pais_code', 'regiao']:
                df_left[col] = df_left[col].where(df_left[col].notna(), None)
                df_right[col] = df_right[col].where(df_right[col].notna(), None)

            log(f"Splink: {len(df_left):,} loja x {len(df_right):,} vivino")

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

            # Treinar
            log("Splink: estimando probabilidade base...")
            training_block_nome = block_on("nome_normalizado")
            training_block_produtor = block_on("produtor_normalizado")

            linker.training.estimate_probability_two_random_records_match(
                training_block_nome, recall=0.7,
            )
            log("Splink: estimando u via random sampling...")
            linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)

            log("Splink: EM por nome...")
            linker.training.estimate_parameters_using_expectation_maximisation(
                training_block_nome, fix_u_probabilities=True,
            )
            log("Splink: EM por produtor...")
            linker.training.estimate_parameters_using_expectation_maximisation(
                training_block_produtor, fix_u_probabilities=True,
            )

            # Predizer
            log("Splink: predizendo matches (threshold=0.50)...")
            results = linker.inference.predict(threshold_match_probability=0.50)
            df_predictions = results.as_pandas_dataframe()
            log(f"Splink: {len(df_predictions):,} pares candidatos")

            if len(df_predictions) > 0:
                # df_left e loja (passado primeiro), df_right e vivino (passado segundo)
                # unique_id_l = loja, unique_id_r = vivino
                df_high = df_predictions[df_predictions['match_probability'] >= 0.80].copy()

                # Validacao: tipo deve bater
                if 'tipo_l' in df_high.columns and 'tipo_r' in df_high.columns:
                    # Descartar onde tipo diverge (exceto quando algum e null)
                    mask_tipo_ok = (
                        df_high['tipo_l'].isna() |
                        df_high['tipo_r'].isna() |
                        (df_high['tipo_l'] == df_high['tipo_r'])
                    )
                    df_high = df_high[mask_tipo_ok]

                # Um vinho de loja so pode ter 1 match — pegar o de maior probabilidade
                df_high = df_high.sort_values('match_probability', ascending=False)
                df_high = df_high.drop_duplicates(subset='unique_id_l', keep='first')

                log(f"Splink: {len(df_high):,} matches com prob >= 0.80")

                # Mapear de volta para nomes para conferencia visual
                vivino_names = df_vivino.set_index('vivino_id')['nome'].to_dict()
                loja_names = df_loja.set_index('id')['nome_limpo'].to_dict()

                for _, row in df_high.iterrows():
                    loja_id = int(row['unique_id_l'])
                    viv_id = int(row['unique_id_r'])
                    prob = float(row['match_probability'])
                    viv_nome = vivino_names.get(viv_id, '')
                    loja_nome = loja_names.get(loja_id, '')
                    splink_results.append((loja_id, viv_id, 'splink_high', prob, viv_nome, loja_nome))
                    if len(examples_nivel2) < 10:
                        examples_nivel2.append(('SPLINK', loja_nome, viv_nome, prob))

                matched_ids.update(df_high['unique_id_l'].tolist())

        except Exception as e:
            log(f"ERRO no Splink: {e}")
            import traceback
            traceback.print_exc()

    count_splink = len(splink_results)
    log(f"Nivel 2 (Splink): {count_splink:,} matches")

    # Salvar resultados Splink
    if splink_results:
        for i in range(0, len(splink_results), BATCH_SIZE):
            insert_matches(conn_local, splink_results[i:i+BATCH_SIZE])

    # === NIVEL 3: Sem match ===
    remaining_final = df_loja[~df_loja['id'].isin(matched_ids)]
    count_no_match = len(remaining_final)
    log(f"Sem match: {count_no_match:,} vinhos")

    # Salvar no_match
    no_match_records = []
    for _, row in remaining_final.iterrows():
        no_match_records.append((int(row['id']), None, 'no_match', None, None, row.get('nome_limpo')))

    for i in range(0, len(no_match_records), BATCH_SIZE):
        insert_matches(conn_local, no_match_records[i:i+BATCH_SIZE])

    conn_local.close()

    # === RESULTADO FINAL ===
    elapsed = time.time() - t0
    total_input = len(df_loja)
    total_vivino = len(df_vivino)
    total_com_match = total_nivel1 + count_splink
    taxa = (total_com_match / total_input * 100) if total_input > 0 else 0

    print(f"\n=== GRUPO {GROUP} CONCLUIDO ({elapsed:.0f}s) ===")
    print(f"Input: {total_input:,} vinhos de wines_unique (IDs {ID_MIN} a {ID_MAX})")
    print(f"Vivino carregado: {total_vivino:,} vinhos")
    print()
    print(f"Nivel 1 (hash):       {count_hash:,} matches")
    print(f"Nivel 1 (ean):        {count_ean:,} matches")
    print(f"Nivel 1 (nome exato): {count_exact + count_no_safra:,} matches")
    print(f"Nivel 2 (Splink):     {count_splink:,} matches")
    print(f"Sem match:            {count_no_match:,} vinhos")
    print()
    print(f"Taxa de match: {taxa:.1f}% encontraram par no Vivino")
    print(f"Tabela: {TABLE} populada com {total_input:,} registros")

    # Exemplos visuais
    if examples_nivel1:
        print(f"\n--- Exemplos Nivel 1 ---")
        for tag, loja, vivino, prob in examples_nivel1[:10]:
            print(f'[{tag}] "{loja}" (loja) -> "{vivino}" (vivino) | prob={prob}')

    if examples_nivel2:
        print(f"\n--- Exemplos Nivel 2 (Splink) ---")
        for tag, loja, vivino, prob in examples_nivel2[:10]:
            print(f'[{tag}] "{loja}" (loja) -> "{vivino}" (vivino) | prob={prob:.2f}')

if __name__ == "__main__":
    main()
