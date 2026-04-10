"""
CHAT Y1 — Match Vinhos de Loja contra Vivino (Grupo 1 de 15)
Faixa: wines_unique IDs 1 a 196153
"""

import sys
import time
import psycopg2
import psycopg2.extras
import pandas as pd
import numpy as np
import os
import _env

# ── Credenciais ──────────────────────────────────────────────
LOCAL_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
RENDER_URL = os.environ["DATABASE_URL"]

ID_MIN = 1
ID_MAX = 196153
GROUP = "Y1"
TABLE_OUT = "match_results_g1"
BATCH_SIZE = 5000


def log(msg):
    print(f"[{GROUP}] {msg}", flush=True)


def create_output_table(conn):
    """Cria tabela de resultados no banco local."""
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_OUT} (
            id SERIAL PRIMARY KEY,
            unique_id INTEGER NOT NULL,
            vivino_id INTEGER,
            match_level VARCHAR(20) NOT NULL,
            match_probability REAL,
            vivino_nome TEXT,
            loja_nome TEXT
        );
    """)
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_mr1_uid ON {TABLE_OUT} (unique_id);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_mr1_vid ON {TABLE_OUT} (vivino_id) WHERE vivino_id IS NOT NULL;")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_mr1_level ON {TABLE_OUT} (match_level);")
    conn.commit()
    cur.close()


def truncate_output(conn):
    """Limpa tabela antes de reprocessar."""
    cur = conn.cursor()
    cur.execute(f"TRUNCATE TABLE {TABLE_OUT} RESTART IDENTITY;")
    conn.commit()
    cur.close()


def insert_matches(conn, rows):
    """Insert em batch. rows: list of (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)"""
    if not rows:
        return
    cur = conn.cursor()
    psycopg2.extras.execute_values(
        cur,
        f"""INSERT INTO {TABLE_OUT} (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)
            VALUES %s""",
        rows,
        page_size=BATCH_SIZE,
    )
    conn.commit()
    cur.close()


# ── PASSO 0 — Carregar dados ────────────────────────────────
def load_data():
    log("Carregando wines_unique (local)...")
    conn_local = psycopg2.connect(LOCAL_URL)
    df_loja = pd.read_sql(f"""
        SELECT id, nome_normalizado, produtor_normalizado, safra,
               tipo, pais_tabela, regiao, hash_dedup, ean_gtin, nome_limpo
        FROM wines_unique
        WHERE id >= {ID_MIN} AND id <= {ID_MAX}
    """, conn_local)
    conn_local.close()
    log(f"Loja carregada: {len(df_loja):,} vinhos")

    log("Carregando wines Vivino (Render)...")
    conn_render = psycopg2.connect(RENDER_URL, sslmode='require',
                                   keepalives=1, keepalives_idle=30,
                                   keepalives_interval=10, keepalives_count=5)
    cur = conn_render.cursor(name='vivino_cursor')
    cur.itersize = 50000
    cur.execute("""
        SELECT id as vivino_id, nome_normalizado, produtor_normalizado, safra,
               tipo, pais as pais_code, regiao, hash_dedup, ean_gtin, nome
        FROM wines
    """)
    cols = ['vivino_id', 'nome_normalizado', 'produtor_normalizado', 'safra',
            'tipo', 'pais_code', 'regiao', 'hash_dedup', 'ean_gtin', 'nome']
    chunks = []
    while True:
        rows = cur.fetchmany(50000)
        if not rows:
            break
        chunks.append(pd.DataFrame(rows, columns=cols))
        log(f"  Vivino: {sum(len(c) for c in chunks):,} lidos...")
    cur.close()
    conn_render.close()
    df_vivino = pd.concat(chunks, ignore_index=True)
    log(f"Vivino carregado: {len(df_vivino):,} vinhos")

    # Converter safra do Vivino pra int
    df_vivino['safra'] = pd.to_numeric(df_vivino['safra'], errors='coerce').astype('Int64')

    return df_loja, df_vivino


# ── NIVEL 1 — Deterministico ────────────────────────────────
def nivel1(df_loja, df_vivino):
    results = []
    matched_ids = set()

    # 1a. Hash
    log("Nivel 1a: match por hash_dedup...")
    loja_hash = df_loja[df_loja['hash_dedup'].notna()].copy()
    vivino_hash = df_vivino[df_vivino['hash_dedup'].notna()][['vivino_id', 'hash_dedup', 'nome', 'tipo']].copy()
    matches_hash = loja_hash.merge(vivino_hash, on='hash_dedup', how='inner', suffixes=('', '_v'))

    # Validacao: tipo deve bater
    if 'tipo' in matches_hash.columns and 'tipo_v' in matches_hash.columns:
        matches_hash = matches_hash[
            (matches_hash['tipo'].isna()) | (matches_hash['tipo_v'].isna()) |
            (matches_hash['tipo'] == matches_hash['tipo_v'])
        ]

    matches_hash = matches_hash.drop_duplicates(subset='id', keep='first')
    for _, row in matches_hash.iterrows():
        results.append((int(row['id']), int(row['vivino_id']), 'hash', 1.0, row['nome'], row.get('nome_limpo')))
    matched_ids.update(matches_hash['id'].tolist())
    log(f"  hash: {len(matches_hash):,} matches")

    # 1b. EAN/GTIN
    log("Nivel 1b: match por ean_gtin...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_ean = remaining[remaining['ean_gtin'].notna()].copy()
    vivino_ean = df_vivino[df_vivino['ean_gtin'].notna()][['vivino_id', 'ean_gtin', 'nome', 'tipo']].copy()
    matches_ean = remaining_ean.merge(vivino_ean, on='ean_gtin', how='inner', suffixes=('', '_v'))

    if 'tipo' in matches_ean.columns and 'tipo_v' in matches_ean.columns:
        matches_ean = matches_ean[
            (matches_ean['tipo'].isna()) | (matches_ean['tipo_v'].isna()) |
            (matches_ean['tipo'] == matches_ean['tipo_v'])
        ]

    matches_ean = matches_ean.drop_duplicates(subset='id', keep='first')
    for _, row in matches_ean.iterrows():
        results.append((int(row['id']), int(row['vivino_id']), 'ean', 1.0, row['nome'], row.get('nome_limpo')))
    matched_ids.update(matches_ean['id'].tolist())
    log(f"  ean: {len(matches_ean):,} matches")

    # 1c. nome_normalizado + safra exato
    log("Nivel 1c: match por nome_normalizado + safra...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_safra = remaining[remaining['safra'].notna() & remaining['nome_normalizado'].notna()].copy()
    vivino_safra = df_vivino[df_vivino['safra'].notna() & df_vivino['nome_normalizado'].notna()][
        ['vivino_id', 'nome_normalizado', 'safra', 'nome', 'tipo']
    ].copy()
    matches_exact = remaining_safra.merge(
        vivino_safra, on=['nome_normalizado', 'safra'], how='inner', suffixes=('', '_v')
    )

    if 'tipo' in matches_exact.columns and 'tipo_v' in matches_exact.columns:
        matches_exact = matches_exact[
            (matches_exact['tipo'].isna()) | (matches_exact['tipo_v'].isna()) |
            (matches_exact['tipo'] == matches_exact['tipo_v'])
        ]

    matches_exact = matches_exact.drop_duplicates(subset='id', keep='first')
    for _, row in matches_exact.iterrows():
        results.append((int(row['id']), int(row['vivino_id']), 'exact_name', 1.0, row['nome'], row.get('nome_limpo')))
    matched_ids.update(matches_exact['id'].tolist())
    log(f"  nome+safra: {len(matches_exact):,} matches")

    # 1d. nome_normalizado sem safra (ambas NULL)
    log("Nivel 1d: match por nome_normalizado (sem safra)...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_no_safra = remaining[remaining['safra'].isna() & remaining['nome_normalizado'].notna()].copy()
    vivino_no_safra = df_vivino[df_vivino['safra'].isna() & df_vivino['nome_normalizado'].notna()][
        ['vivino_id', 'nome_normalizado', 'nome', 'tipo']
    ].copy()
    matches_no_safra = remaining_no_safra.merge(
        vivino_no_safra, on='nome_normalizado', how='inner', suffixes=('', '_v')
    )

    if 'tipo' in matches_no_safra.columns and 'tipo_v' in matches_no_safra.columns:
        matches_no_safra = matches_no_safra[
            (matches_no_safra['tipo'].isna()) | (matches_no_safra['tipo_v'].isna()) |
            (matches_no_safra['tipo'] == matches_no_safra['tipo_v'])
        ]

    matches_no_safra = matches_no_safra.drop_duplicates(subset='id', keep='first')
    for _, row in matches_no_safra.iterrows():
        results.append((int(row['id']), int(row['vivino_id']), 'exact_name', 1.0, row['nome'], row.get('nome_limpo')))
    matched_ids.update(matches_no_safra['id'].tolist())
    log(f"  nome sem safra: {len(matches_no_safra):,} matches")

    stats = {
        'hash': len(matches_hash),
        'ean': len(matches_ean),
        'exact_name': len(matches_exact) + len(matches_no_safra),
    }

    return results, matched_ids, stats


# ── NIVEL 2 — Splink ────────────────────────────────────────
def nivel2(df_loja, df_vivino, matched_ids):
    import splink.comparison_library as cl
    import splink.blocking_rule_library as brl
    from splink import DuckDBAPI, Linker, SettingsCreator, block_on

    df_loja_remaining = df_loja[~df_loja['id'].isin(matched_ids)].copy()
    log(f"Nivel 2: {len(df_loja_remaining):,} vinhos restantes pra Splink...")

    if len(df_loja_remaining) == 0:
        log("  Nenhum vinho restante, pulando Splink.")
        return [], set()

    # Preparar DataFrames
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

    # Substituir NaN por None em todas as colunas string
    for col in ['nome_normalizado', 'produtor_normalizado', 'safra', 'tipo', 'pais_code', 'regiao']:
        df_left[col] = df_left[col].where(df_left[col].notna(), None)
        df_right[col] = df_right[col].where(df_right[col].notna(), None)

    log("  Configurando Splink...")
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

    log("  Treinando modelo...")
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

    log("  Predizendo matches...")
    results_splink = linker.inference.predict(threshold_match_probability=0.50)
    df_predictions = results_splink.as_pandas_dataframe()
    log(f"  Splink retornou {len(df_predictions):,} pares candidatos")

    if len(df_predictions) == 0:
        return [], set()

    # unique_id_l = loja (df_left), unique_id_r = vivino (df_right)
    df_high = df_predictions[df_predictions['match_probability'] >= 0.80].copy()

    # Para cada vinho de loja, pegar o melhor match
    df_high = df_high.sort_values('match_probability', ascending=False)
    df_high = df_high.drop_duplicates(subset='unique_id_l', keep='first')

    # Validacao de tipo
    if 'tipo_l' in df_high.columns and 'tipo_r' in df_high.columns:
        df_high = df_high[
            (df_high['tipo_l'].isna()) | (df_high['tipo_r'].isna()) |
            (df_high['tipo_l'] == df_high['tipo_r'])
        ]

    # Buscar nomes pra conferencia
    loja_names = df_loja.set_index('id')['nome_limpo'].to_dict()
    vivino_names = df_vivino.set_index('vivino_id')['nome'].to_dict()

    results = []
    matched_splink_ids = set()
    for _, row in df_high.iterrows():
        loja_id = int(row['unique_id_l'])
        viv_id = int(row['unique_id_r'])
        prob = float(row['match_probability'])
        viv_nome = vivino_names.get(viv_id)
        loja_nome = loja_names.get(loja_id)
        results.append((loja_id, viv_id, 'splink_high', prob, viv_nome, loja_nome))
        matched_splink_ids.add(loja_id)

    log(f"  Splink high (>=0.80): {len(results):,} matches")
    return results, matched_splink_ids


# ── MAIN ─────────────────────────────────────────────────────
def main():
    t0 = time.time()

    # Carregar dados
    df_loja, df_vivino = load_data()

    # Criar tabela de resultados
    log("Criando tabela de resultados...")
    conn_local = psycopg2.connect(LOCAL_URL)
    create_output_table(conn_local)
    truncate_output(conn_local)

    # ── Nivel 1 ──
    log("=== NIVEL 1 — Deterministico ===")
    t1 = time.time()
    results_n1, matched_ids, stats_n1 = nivel1(df_loja, df_vivino)
    log(f"Nivel 1 completo em {time.time()-t1:.0f}s — {len(results_n1):,} matches")

    # Inserir nivel 1
    log("Inserindo matches nivel 1...")
    for i in range(0, len(results_n1), BATCH_SIZE):
        insert_matches(conn_local, results_n1[i:i+BATCH_SIZE])
    log(f"  {len(results_n1):,} registros inseridos")

    # ── Nivel 2 ──
    log("=== NIVEL 2 — Splink ===")
    t2 = time.time()
    results_n2, matched_splink_ids = nivel2(df_loja, df_vivino, matched_ids)
    log(f"Nivel 2 completo em {time.time()-t2:.0f}s — {len(results_n2):,} matches")

    # Inserir nivel 2
    if results_n2:
        log("Inserindo matches nivel 2...")
        for i in range(0, len(results_n2), BATCH_SIZE):
            insert_matches(conn_local, results_n2[i:i+BATCH_SIZE])
        log(f"  {len(results_n2):,} registros inseridos")

    matched_ids.update(matched_splink_ids)

    # ── Nivel 3 — Sem match ──
    log("=== NIVEL 3 — Sem match ===")
    no_match_ids = set(df_loja['id'].tolist()) - matched_ids
    no_match_rows = []
    loja_names = df_loja.set_index('id')['nome_limpo'].to_dict()
    for uid in no_match_ids:
        no_match_rows.append((int(uid), None, 'no_match', None, None, loja_names.get(uid)))

    log(f"Inserindo {len(no_match_rows):,} registros sem match...")
    for i in range(0, len(no_match_rows), BATCH_SIZE):
        insert_matches(conn_local, no_match_rows[i:i+BATCH_SIZE])

    conn_local.close()

    # ── Resumo ──
    total = len(df_loja)
    total_match = len(results_n1) + len(results_n2)
    taxa = (total_match / total * 100) if total > 0 else 0

    print(f"""
=== GRUPO {GROUP} CONCLUIDO ===
Input: {total:,} vinhos de wines_unique (IDs {ID_MIN} a {ID_MAX})
Vivino carregado: {len(df_vivino):,} vinhos

Nivel 1 (hash):       {stats_n1['hash']:,} matches
Nivel 1 (ean):        {stats_n1['ean']:,} matches
Nivel 1 (nome exato): {stats_n1['exact_name']:,} matches
Nivel 2 (Splink):     {len(results_n2):,} matches
Sem match:            {len(no_match_rows):,} vinhos

Taxa de match: {taxa:.1f}% encontraram par no Vivino
Tabela: {TABLE_OUT} populada com {total:,} registros
Tempo total: {time.time()-t0:.0f}s
""")

    # ── Exemplos ──
    print("--- Exemplos Nivel 1 ---")
    for r in results_n1[:10]:
        uid, vid, lvl, prob, vname, lname = r
        print(f"  [{lvl.upper()}] \"{lname}\" (loja) → \"{vname}\" (vivino) | prob={prob}")

    if results_n2:
        print("\n--- Exemplos Nivel 2 (Splink) ---")
        for r in results_n2[:10]:
            uid, vid, lvl, prob, vname, lname = r
            print(f"  [SPLINK] \"{lname}\" (loja) → \"{vname}\" (vivino) | prob={prob:.2f}")


if __name__ == "__main__":
    main()
