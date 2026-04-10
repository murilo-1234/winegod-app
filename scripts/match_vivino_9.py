"""
CHAT Y9 — Match Vinhos de Loja contra Vivino (Grupo 9 de 15)
Faixa: wines_unique WHERE id >= 1569225 AND id <= 1765377
"""

import psycopg
import pandas as pd
import numpy as np
import time
import sys
import os
import _env

# === CREDENCIAIS ===
LOCAL_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
RENDER_URL = os.environ["DATABASE_URL"]

# === FAIXA ===
ID_MIN = 1569225
ID_MAX = 1765377
GROUP = "Y9"
TABLE = "match_results_g9"
BATCH_SIZE = 5000

def log(msg):
    print(f"[{GROUP}] {msg}", flush=True)

def create_result_table(conn):
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id SERIAL PRIMARY KEY,
            unique_id INTEGER NOT NULL,
            vivino_id INTEGER,
            match_level VARCHAR(20) NOT NULL,
            match_probability REAL,
            vivino_nome TEXT,
            loja_nome TEXT
        )
    """)
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_mr9_uid ON {TABLE} (unique_id)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_mr9_vid ON {TABLE} (vivino_id) WHERE vivino_id IS NOT NULL")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_mr9_level ON {TABLE} (match_level)")
    conn.commit()

def insert_batch(conn, rows):
    if not rows:
        return
    placeholders = ",".join(
        conn.execute("SELECT ''").connection.cursor().mogrify(
            "(%s,%s,%s,%s,%s,%s)", r
        ).decode() if False else "(%s,%s,%s,%s,%s,%s)"
        for r in rows
    )
    # Use executemany for psycopg v3
    with conn.cursor() as cur:
        cur.executemany(
            f"INSERT INTO {TABLE} (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome) VALUES (%s,%s,%s,%s,%s,%s)",
            rows
        )
    conn.commit()

def main():
    t0 = time.time()

    # === PASSO 0: Carregar dados ===
    log("Conectando ao banco local...")
    conn_local = psycopg.connect(LOCAL_URL, autocommit=False)

    log(f"Carregando wines_unique (IDs {ID_MIN} a {ID_MAX})...")
    with conn_local.cursor() as cur:
        cur.execute(f"""
            SELECT id, nome_normalizado, produtor_normalizado, safra,
                   tipo, pais_tabela, regiao, hash_dedup, ean_gtin, nome_limpo
            FROM wines_unique
            WHERE id >= {ID_MIN} AND id <= {ID_MAX}
        """)
        cols_loja = [d.name for d in cur.description]
        rows_loja = cur.fetchall()
    df_loja = pd.DataFrame(rows_loja, columns=cols_loja)
    log(f"Loja carregada: {len(df_loja):,} vinhos")

    # Carregar Vivino em chunks via LIMIT/OFFSET (psycopg v3)
    log("Conectando ao Render e carregando Vivino (1.72M) em chunks...")
    CHUNK = 50_000
    chunks = []
    offset = 0
    cols_vivino = ['vivino_id', 'nome_normalizado', 'produtor_normalizado', 'safra',
                   'tipo', 'pais_code', 'regiao', 'hash_dedup', 'ean_gtin', 'nome']
    while True:
        for attempt in range(5):
            try:
                with psycopg.connect(RENDER_URL, connect_timeout=60) as conn_r:
                    with conn_r.cursor() as cur_r:
                        cur_r.execute(f"""
                            SELECT id, nome_normalizado, produtor_normalizado, safra,
                                   tipo, pais, regiao, hash_dedup, ean_gtin, nome
                            FROM wines ORDER BY id LIMIT {CHUNK} OFFSET {offset}
                        """)
                        rows = cur_r.fetchall()
                break
            except Exception as e:
                log(f"  Tentativa {attempt+1} falhou offset={offset}: {e}")
                time.sleep(10 * (attempt + 1))
                if attempt == 4:
                    raise
        if not rows:
            break
        chunks.append(pd.DataFrame(rows, columns=cols_vivino))
        offset += CHUNK
        log(f"  ... {sum(len(c) for c in chunks):,} rows lidas")
    df_vivino = pd.concat(chunks, ignore_index=True)
    del chunks
    log(f"Vivino carregado: {len(df_vivino):,} vinhos")

    # Converter safra do Vivino pra int
    df_vivino['safra'] = pd.to_numeric(df_vivino['safra'], errors='coerce').astype('Int64')

    # Criar tabela de resultado
    create_result_table(conn_local)

    # Limpar resultados anteriores (re-run safe)
    conn_local.execute(f"DELETE FROM {TABLE}")
    conn_local.commit()

    # Tracking
    all_results = []
    matched_ids = set()
    counts = {'hash': 0, 'ean': 0, 'exact_name': 0, 'exact_name_no_safra': 0, 'splink_high': 0, 'no_match': 0}

    # === NIVEL 1a: Match por hash_dedup ===
    log("Nivel 1a: Match por hash_dedup...")
    loja_hash = df_loja[df_loja['hash_dedup'].notna()].copy()
    viv_hash = df_vivino[df_vivino['hash_dedup'].notna()][['vivino_id', 'hash_dedup', 'nome']].copy()
    matches_hash = loja_hash.merge(viv_hash, on='hash_dedup', how='inner')
    matches_hash = matches_hash.drop_duplicates(subset='id', keep='first')

    for _, r in matches_hash.iterrows():
        all_results.append((int(r['id']), int(r['vivino_id']), 'hash', 1.0, r['nome'], r['nome_limpo']))
        matched_ids.add(r['id'])
    counts['hash'] = len(matches_hash)
    log(f"  hash_dedup: {counts['hash']:,} matches")

    # === NIVEL 1b: Match por ean_gtin ===
    log("Nivel 1b: Match por ean_gtin...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    rem_ean = remaining[remaining['ean_gtin'].notna()].copy()
    viv_ean = df_vivino[df_vivino['ean_gtin'].notna()][['vivino_id', 'ean_gtin', 'nome']].copy()
    matches_ean = rem_ean.merge(viv_ean, on='ean_gtin', how='inner')
    matches_ean = matches_ean.drop_duplicates(subset='id', keep='first')

    for _, r in matches_ean.iterrows():
        all_results.append((int(r['id']), int(r['vivino_id']), 'ean', 1.0, r['nome'], r['nome_limpo']))
        matched_ids.add(r['id'])
    counts['ean'] = len(matches_ean)
    log(f"  ean_gtin: {counts['ean']:,} matches")

    # === NIVEL 1c: Match por nome_normalizado + safra ===
    log("Nivel 1c: Match por nome_normalizado + safra...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    rem_nome = remaining[remaining['nome_normalizado'].notna()].copy()
    viv_nome = df_vivino[df_vivino['nome_normalizado'].notna()][['vivino_id', 'nome_normalizado', 'safra', 'nome']].copy()

    rem_with_safra = rem_nome[rem_nome['safra'].notna()].copy()
    viv_with_safra = viv_nome[viv_nome['safra'].notna()].copy()
    matches_exact = rem_with_safra.merge(viv_with_safra, on=['nome_normalizado', 'safra'], how='inner')
    matches_exact = matches_exact.drop_duplicates(subset='id', keep='first')

    for _, r in matches_exact.iterrows():
        all_results.append((int(r['id']), int(r['vivino_id']), 'exact_name', 1.0, r['nome'], r['nome_limpo']))
        matched_ids.add(r['id'])
    counts['exact_name'] = len(matches_exact)
    log(f"  nome+safra: {counts['exact_name']:,} matches")

    # === NIVEL 1d: Match por nome_normalizado sem safra (ambas NULL) ===
    log("Nivel 1d: Match por nome_normalizado (sem safra)...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    rem_no_safra = remaining[(remaining['nome_normalizado'].notna()) & (remaining['safra'].isna())].copy()
    viv_no_safra = viv_nome[viv_nome['safra'].isna()].copy()
    matches_no_safra = rem_no_safra.merge(
        viv_no_safra[['vivino_id', 'nome_normalizado', 'nome']],
        on='nome_normalizado', how='inner'
    )
    matches_no_safra = matches_no_safra.drop_duplicates(subset='id', keep='first')

    for _, r in matches_no_safra.iterrows():
        all_results.append((int(r['id']), int(r['vivino_id']), 'exact_name', 1.0, r['nome'], r['nome_limpo']))
        matched_ids.add(r['id'])
    counts['exact_name_no_safra'] = len(matches_no_safra)
    log(f"  nome sem safra: {counts['exact_name_no_safra']:,} matches")

    total_n1 = counts['hash'] + counts['ean'] + counts['exact_name'] + counts['exact_name_no_safra']
    log(f"Nivel 1 total: {total_n1:,} matches | Restam: {len(df_loja) - len(matched_ids):,}")

    # Salvar Nivel 1
    log("Salvando Nivel 1 no banco...")
    for i in range(0, len(all_results), BATCH_SIZE):
        batch = all_results[i:i+BATCH_SIZE]
        insert_batch(conn_local, batch)
    log(f"Nivel 1 salvo: {len(all_results):,} registros")

    # === NIVEL 2: Splink ===
    remaining_count = len(df_loja) - len(matched_ids)
    if remaining_count > 0:
        log(f"Nivel 2: Splink para {remaining_count:,} vinhos restantes...")

        import splink.comparison_library as cl
        import splink.blocking_rule_library as brl
        from splink import DuckDBAPI, Linker, SettingsCreator, block_on

        df_loja_remaining = df_loja[~df_loja['id'].isin(matched_ids)].copy()
        df_loja_remaining = df_loja_remaining.rename(columns={'id': 'unique_id', 'pais_tabela': 'pais_code'})
        df_loja_remaining['source_dataset'] = 'loja'

        df_vivino_splink = df_vivino.copy()
        df_vivino_splink = df_vivino_splink.rename(columns={'vivino_id': 'unique_id'})
        df_vivino_splink['source_dataset'] = 'vivino'

        cols = ['unique_id', 'nome_normalizado', 'produtor_normalizado',
                'safra', 'tipo', 'pais_code', 'regiao', 'source_dataset']

        df_left = df_loja_remaining[cols].copy()
        df_right = df_vivino_splink[cols].copy()

        # Converter safra pra string pro Splink
        df_left['safra'] = df_left['safra'].astype(str)
        df_right['safra'] = df_right['safra'].astype(str)
        df_left.loc[df_left['safra'].isin(['<NA>', 'nan', 'None', '']), 'safra'] = None
        df_right.loc[df_right['safra'].isin(['<NA>', 'nan', 'None', '']), 'safra'] = None

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
            df_high = df_predictions[df_predictions['match_probability'] >= 0.80].copy()

            # Validacao: tipo deve bater
            if 'tipo_l' in df_high.columns and 'tipo_r' in df_high.columns:
                mask_tipo_ok = (
                    df_high['tipo_l'].isna() |
                    df_high['tipo_r'].isna() |
                    (df_high['tipo_l'] == df_high['tipo_r'])
                )
                df_high = df_high[mask_tipo_ok]

            # Pegar melhor match por vinho de loja
            df_high = df_high.sort_values('match_probability', ascending=False)
            df_high = df_high.drop_duplicates(subset='unique_id_l', keep='first')

            # Excluir vinhos ja matchados no Nivel 1
            df_high = df_high[~df_high['unique_id_l'].isin(matched_ids)]

            log(f"Splink high (>=0.80): {len(df_high):,} matches")

            # Buscar nomes para conferencia
            loja_names = df_loja.set_index('id')['nome_limpo'].to_dict()
            vivino_names = df_vivino.set_index('vivino_id')['nome'].to_dict()

            splink_results = []
            for _, r in df_high.iterrows():
                uid_l = int(r['unique_id_l'])
                uid_r = int(r['unique_id_r'])
                prob = float(r['match_probability'])
                v_nome = vivino_names.get(uid_r, '')
                l_nome = loja_names.get(uid_l, '')
                splink_results.append((uid_l, uid_r, 'splink_high', prob, v_nome, l_nome))
                matched_ids.add(uid_l)

            counts['splink_high'] = len(splink_results)

            # Salvar Splink
            log("Salvando Splink no banco...")
            for i in range(0, len(splink_results), BATCH_SIZE):
                batch = splink_results[i:i+BATCH_SIZE]
                insert_batch(conn_local, batch)
        else:
            log("Splink nao encontrou pares candidatos")
    else:
        log("Todos matcharam no Nivel 1 — Splink nao necessario")

    # === NIVEL 3: Sem match ===
    log("Nivel 3: Registrando vinhos sem match...")
    no_match_ids = set(df_loja['id']) - matched_ids
    counts['no_match'] = len(no_match_ids)

    loja_names_dict = df_loja.set_index('id')['nome_limpo'].to_dict()
    no_match_results = []
    for uid in no_match_ids:
        l_nome = loja_names_dict.get(uid, '')
        no_match_results.append((int(uid), None, 'no_match', None, None, l_nome))

    for i in range(0, len(no_match_results), BATCH_SIZE):
        batch = no_match_results[i:i+BATCH_SIZE]
        insert_batch(conn_local, batch)

    log(f"Sem match: {counts['no_match']:,} vinhos")

    conn_local.close()

    # === RESUMO ===
    elapsed = time.time() - t0
    total_input = len(df_loja)
    total_com_match = total_input - counts['no_match']
    taxa = (total_com_match / total_input * 100) if total_input > 0 else 0

    print(f"""
=== GRUPO {GROUP} CONCLUIDO === ({elapsed/60:.1f} min)
Input: {total_input:,} vinhos de wines_unique (IDs {ID_MIN} a {ID_MAX})
Vivino carregado: {len(df_vivino):,} vinhos

Nivel 1 (hash):       {counts['hash']:,} matches
Nivel 1 (ean):        {counts['ean']:,} matches
Nivel 1 (nome exato): {counts['exact_name'] + counts['exact_name_no_safra']:,} matches
Nivel 2 (Splink):     {counts['splink_high']:,} matches
Sem match:            {counts['no_match']:,} vinhos

Taxa de match: {taxa:.1f}% encontraram par no Vivino
Tabela: {TABLE} populada com {total_input:,} registros
""")

    # === EXEMPLOS ===
    print("--- 10 exemplos Nivel 1 ---")
    shown = 0
    for r in all_results[:50]:
        if shown >= 10:
            break
        uid, vid, level, prob, v_nome, l_nome = r
        print(f"  [{level.upper()}] \"{l_nome}\" (loja) -> \"{v_nome}\" (vivino) | prob={prob}")
        shown += 1

    if counts['splink_high'] > 0:
        print("\n--- 10 exemplos Nivel 2 (Splink) ---")
        shown = 0
        try:
            for r in splink_results[:10]:
                uid, vid, level, prob, v_nome, l_nome = r
                print(f"  [SPLINK] \"{l_nome}\" (loja) -> \"{v_nome}\" (vivino) | prob={prob:.2f}")
                shown += 1
        except:
            pass

if __name__ == "__main__":
    main()
