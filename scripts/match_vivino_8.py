"""
CHAT Y8 — Match Vinhos de Loja contra Vivino (Grupo 8 de 15)
Faixa: wines_unique WHERE id >= 1373072 AND id <= 1569224
"""

import sys
import time
import psycopg2
import psycopg2.extras
import pandas as pd
import numpy as np

# ── Credenciais ──────────────────────────────────────────────
LOCAL_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
RENDER_URL = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod"

ID_MIN = 1373072
ID_MAX = 1569224
BATCH_SIZE = 5000

# ── PASSO 0: Criar tabela de resultado ──────────────────────
def criar_tabela(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS match_results_g8 (
                id SERIAL PRIMARY KEY,
                unique_id INTEGER NOT NULL,
                vivino_id INTEGER,
                match_level VARCHAR(20) NOT NULL,
                match_probability REAL,
                vivino_nome TEXT,
                loja_nome TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_mr8_uid ON match_results_g8 (unique_id);
            CREATE INDEX IF NOT EXISTS idx_mr8_vid ON match_results_g8 (vivino_id) WHERE vivino_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_mr8_level ON match_results_g8 (match_level);
        """)
        # Limpar resultados anteriores (re-run seguro)
        cur.execute("DELETE FROM match_results_g8;")
        conn.commit()
    print("[Y8] Tabela match_results_g8 pronta.")


# ── PASSO 0: Carregar dados ─────────────────────────────────
def carregar_dados():
    t0 = time.time()

    print("[Y8] Conectando ao banco local...")
    conn_local = psycopg2.connect(LOCAL_URL)

    print(f"[Y8] Carregando wines_unique (IDs {ID_MIN} a {ID_MAX})...")
    df_loja = pd.read_sql(f"""
        SELECT id, nome_normalizado, produtor_normalizado, safra,
               tipo, pais_tabela, regiao, hash_dedup, ean_gtin, nome_limpo
        FROM wines_unique
        WHERE id >= {ID_MIN} AND id <= {ID_MAX}
    """, conn_local)

    print(f"[Y8] Loja carregada: {len(df_loja):,} vinhos ({time.time()-t0:.1f}s)")

    t1 = time.time()
    print("[Y8] Carregando TODOS os vinhos Vivino em chunks (OFFSET/LIMIT)...")
    CHUNK = 50_000
    cols = ['vivino_id', 'nome_normalizado', 'produtor_normalizado', 'safra',
            'tipo', 'pais_code', 'regiao', 'hash_dedup', 'ean_gtin', 'nome']
    chunks = []
    offset = 0
    while True:
        rows = None
        for attempt in range(5):
            try:
                c = psycopg2.connect(
                    RENDER_URL,
                    sslmode='require',
                    connect_timeout=60,
                    options='-c statement_timeout=120000',
                )
                with c.cursor() as cur:
                    cur.execute(f"""
                        SELECT id as vivino_id, nome_normalizado, produtor_normalizado, safra,
                               tipo, pais as pais_code, regiao, hash_dedup, ean_gtin, nome
                        FROM wines ORDER BY id LIMIT {CHUNK} OFFSET {offset}
                    """)
                    rows = cur.fetchall()
                c.close()
                break
            except Exception as e:
                try:
                    c.close()
                except:
                    pass
                wait = 10 * (attempt + 1)
                print(f"[Y8]   Tentativa {attempt+1} falhou: {e}. Aguardando {wait}s...")
                time.sleep(wait)
        if rows is None:
            raise Exception(f"Falha ao carregar chunk no offset {offset} apos 5 tentativas")
        if not rows:
            break
        chunks.append(pd.DataFrame(rows, columns=cols))
        offset += CHUNK
        print(f"[Y8]   ...chunk {len(chunks)}: {sum(len(c) for c in chunks):,} vinhos")
        time.sleep(2)  # pequena pausa entre chunks
    df_vivino = pd.concat(chunks, ignore_index=True)

    print(f"[Y8] Vivino carregado: {len(df_vivino):,} vinhos ({time.time()-t1:.1f}s)")

    # Converter safra do Vivino pra int (era varchar)
    df_vivino['safra'] = pd.to_numeric(df_vivino['safra'], errors='coerce').astype('Int64')

    # Normalizar safra da loja tambem pra Int64 (nullable)
    df_loja['safra'] = df_loja['safra'].astype('Int64')

    print(f"[Y8] Dados carregados. Loja: {len(df_loja):,} | Vivino: {len(df_vivino):,}")
    return conn_local, df_loja, df_vivino


# ── NIVEL 1: Deterministico ─────────────────────────────────
def nivel1_deterministico(df_loja, df_vivino):
    print("\n[Y8] === NIVEL 1 — Deterministico ===")
    matched_ids = set()
    resultados = []

    # 1a. Match por hash_dedup
    t0 = time.time()
    loja_hash = df_loja[df_loja['hash_dedup'].notna() & (df_loja['hash_dedup'] != '')]
    viv_hash = df_vivino[df_vivino['hash_dedup'].notna() & (df_vivino['hash_dedup'] != '')][['vivino_id', 'hash_dedup', 'nome']]

    matches_hash = loja_hash.merge(viv_hash, on='hash_dedup', how='inner')
    matches_hash = matches_hash.drop_duplicates(subset='id', keep='first')

    for _, r in matches_hash.iterrows():
        resultados.append((int(r['id']), int(r['vivino_id']), 'hash', 1.0, r['nome'], r.get('nome_limpo', r.get('nome_normalizado', ''))))
    matched_ids.update(matches_hash['id'].tolist())
    print(f"[Y8] Hash: {len(matches_hash):,} matches ({time.time()-t0:.1f}s)")

    # 1b. Match por ean_gtin
    t0 = time.time()
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    loja_ean = remaining[remaining['ean_gtin'].notna() & (remaining['ean_gtin'] != '')]
    viv_ean = df_vivino[df_vivino['ean_gtin'].notna() & (df_vivino['ean_gtin'] != '')][['vivino_id', 'ean_gtin', 'nome']]

    matches_ean = loja_ean.merge(viv_ean, on='ean_gtin', how='inner')
    matches_ean = matches_ean.drop_duplicates(subset='id', keep='first')

    for _, r in matches_ean.iterrows():
        resultados.append((int(r['id']), int(r['vivino_id']), 'ean', 1.0, r['nome'], r.get('nome_limpo', r.get('nome_normalizado', ''))))
    matched_ids.update(matches_ean['id'].tolist())
    print(f"[Y8] EAN: {len(matches_ean):,} matches ({time.time()-t0:.1f}s)")

    # 1c. Match por nome_normalizado + safra exato
    t0 = time.time()
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_com_safra = remaining[remaining['safra'].notna()]
    viv_com_safra = df_vivino[df_vivino['safra'].notna()][['vivino_id', 'nome_normalizado', 'safra', 'nome']]

    matches_exact = remaining_com_safra.merge(viv_com_safra, on=['nome_normalizado', 'safra'], how='inner')
    matches_exact = matches_exact.drop_duplicates(subset='id', keep='first')

    # Validacao: tipo deve bater
    if 'tipo_x' in matches_exact.columns and 'tipo_y' in matches_exact.columns:
        matches_exact = matches_exact[
            (matches_exact['tipo_x'].isna()) | (matches_exact['tipo_y'].isna()) |
            (matches_exact['tipo_x'] == matches_exact['tipo_y'])
        ]

    for _, r in matches_exact.iterrows():
        resultados.append((int(r['id']), int(r['vivino_id']), 'exact_name', 1.0, r['nome'], r.get('nome_limpo', r.get('nome_normalizado_x', ''))))
    matched_ids.update(matches_exact['id'].tolist())
    print(f"[Y8] Nome exato + safra: {len(matches_exact):,} matches ({time.time()-t0:.1f}s)")

    # 1d. Match por nome_normalizado sem safra (ambos NULL)
    t0 = time.time()
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_no_safra = remaining[remaining['safra'].isna()]
    viv_no_safra = df_vivino[df_vivino['safra'].isna()][['vivino_id', 'nome_normalizado', 'nome']]

    matches_no_safra = remaining_no_safra.merge(viv_no_safra, on='nome_normalizado', how='inner')
    matches_no_safra = matches_no_safra.drop_duplicates(subset='id', keep='first')

    for _, r in matches_no_safra.iterrows():
        resultados.append((int(r['id']), int(r['vivino_id']), 'exact_name', 1.0, r['nome'], r.get('nome_limpo', r.get('nome_normalizado_x', ''))))
    matched_ids.update(matches_no_safra['id'].tolist())
    print(f"[Y8] Nome exato sem safra: {len(matches_no_safra):,} matches ({time.time()-t0:.1f}s)")

    n1_hash = len(matches_hash)
    n1_ean = len(matches_ean)
    n1_exact = len(matches_exact) + len(matches_no_safra)

    print(f"[Y8] NIVEL 1 total: {len(matched_ids):,} matches")
    return matched_ids, resultados, n1_hash, n1_ean, n1_exact


# ── NIVEL 2: Splink probabilistico ──────────────────────────
def nivel2_splink(df_loja, df_vivino, matched_ids):
    print("\n[Y8] === NIVEL 2 — Splink ===")

    remaining = df_loja[~df_loja['id'].isin(matched_ids)].copy()
    print(f"[Y8] Vinhos restantes para Splink: {len(remaining):,}")

    if len(remaining) == 0:
        print("[Y8] Nenhum vinho restante — pulando Splink.")
        return set(), []

    import splink.comparison_library as cl
    import splink.blocking_rule_library as brl
    from splink import DuckDBAPI, Linker, SettingsCreator, block_on

    # Preparar DataFrames
    df_left = remaining.rename(columns={'id': 'unique_id', 'pais_tabela': 'pais_code'})[
        ['unique_id', 'nome_normalizado', 'produtor_normalizado', 'safra', 'tipo', 'pais_code', 'regiao']
    ].copy()
    df_left['source_dataset'] = 'loja'

    df_right = df_vivino.rename(columns={'vivino_id': 'unique_id'})[
        ['unique_id', 'nome_normalizado', 'produtor_normalizado', 'safra', 'tipo', 'pais_code', 'regiao']
    ].copy()
    df_right['source_dataset'] = 'vivino'

    # Converter safra pra string pro Splink
    df_left['safra'] = df_left['safra'].astype(str).replace('<NA>', None).replace('nan', None)
    df_right['safra'] = df_right['safra'].astype(str).replace('<NA>', None).replace('nan', None)

    # Substituir NaN por None pra todas colunas string
    for col in ['nome_normalizado', 'produtor_normalizado', 'tipo', 'pais_code', 'regiao', 'safra']:
        df_left[col] = df_left[col].where(df_left[col].notna(), None)
        df_left.loc[df_left[col] == '', col] = None
        df_left.loc[df_left[col] == 'nan', col] = None
        df_left.loc[df_left[col] == '<NA>', col] = None
        df_right[col] = df_right[col].where(df_right[col].notna(), None)
        df_right.loc[df_right[col] == '', col] = None
        df_right.loc[df_right[col] == 'nan', col] = None
        df_right.loc[df_right[col] == '<NA>', col] = None

    print(f"[Y8] Splink: left={len(df_left):,}, right={len(df_right):,}")

    # Configurar Splink
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

    t0 = time.time()
    db_api = DuckDBAPI()
    linker = Linker([df_left, df_right], settings, db_api)

    # Treinar
    print("[Y8] Splink: estimando probabilidade base...")
    training_block_nome = block_on("nome_normalizado")
    training_block_produtor = block_on("produtor_normalizado")

    linker.training.estimate_probability_two_random_records_match(
        training_block_nome, recall=0.7,
    )

    print("[Y8] Splink: estimando u via random sampling...")
    linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)

    print("[Y8] Splink: EM por nome...")
    linker.training.estimate_parameters_using_expectation_maximisation(
        training_block_nome, fix_u_probabilities=True,
    )

    print("[Y8] Splink: EM por produtor...")
    linker.training.estimate_parameters_using_expectation_maximisation(
        training_block_produtor, fix_u_probabilities=True,
    )

    # Predizer
    print("[Y8] Splink: predizendo matches (threshold=0.50)...")
    results = linker.inference.predict(threshold_match_probability=0.50)
    df_predictions = results.as_pandas_dataframe()
    print(f"[Y8] Splink: {len(df_predictions):,} pares candidatos ({time.time()-t0:.1f}s)")

    if len(df_predictions) == 0:
        print("[Y8] Splink: nenhum match encontrado.")
        return set(), []

    # Identificar loja (left) e vivino (right)
    # df_left foi passado primeiro, entao unique_id_l = loja, unique_id_r = vivino
    df_pred = df_predictions.copy()

    # Filtrar >= 0.80 (splink_high)
    df_high = df_pred[df_pred['match_probability'] >= 0.80].copy()
    print(f"[Y8] Splink alto (>=0.80): {len(df_high):,} pares")

    # Validacao de tipo: descartar se tipos nao batem
    if 'tipo_l' in df_high.columns and 'tipo_r' in df_high.columns:
        before = len(df_high)
        df_high = df_high[
            (df_high['tipo_l'].isna()) | (df_high['tipo_r'].isna()) |
            (df_high['tipo_l'] == '') | (df_high['tipo_r'] == '') |
            (df_high['tipo_l'] == df_high['tipo_r'])
        ]
        print(f"[Y8] Filtro tipo: {before} → {len(df_high)} (removidos {before - len(df_high)})")

    # Pegar melhor match por vinho de loja
    df_high = df_high.sort_values('match_probability', ascending=False)
    df_high = df_high.drop_duplicates(subset='unique_id_l', keep='first')

    # Buscar nomes pra conferencia
    loja_nomes = df_loja.set_index('id')['nome_limpo'].to_dict()
    vivino_nomes = df_vivino.set_index('vivino_id')['nome'].to_dict()

    resultados = []
    splink_matched_ids = set()

    for _, r in df_high.iterrows():
        uid_loja = int(r['unique_id_l'])
        uid_vivino = int(r['unique_id_r'])
        prob = float(r['match_probability'])
        viv_nome = vivino_nomes.get(uid_vivino, '')
        loja_nome = loja_nomes.get(uid_loja, '')
        resultados.append((uid_loja, uid_vivino, 'splink_high', prob, viv_nome, loja_nome))
        splink_matched_ids.add(uid_loja)

    print(f"[Y8] Splink final: {len(splink_matched_ids):,} matches unicos")
    return splink_matched_ids, resultados


# ── Salvar resultados ────────────────────────────────────────
def salvar_resultados(conn, resultados):
    print(f"\n[Y8] Salvando {len(resultados):,} resultados...")
    t0 = time.time()

    with conn.cursor() as cur:
        for i in range(0, len(resultados), BATCH_SIZE):
            batch = resultados[i:i+BATCH_SIZE]
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO match_results_g8
                   (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)
                   VALUES %s""",
                batch,
                template="(%s, %s, %s, %s, %s, %s)",
                page_size=BATCH_SIZE,
            )
            conn.commit()
            if (i + BATCH_SIZE) % 25000 == 0 or i + BATCH_SIZE >= len(resultados):
                print(f"[Y8] Inseridos: {min(i+BATCH_SIZE, len(resultados)):,}/{len(resultados):,}")

    print(f"[Y8] Salvamento concluido ({time.time()-t0:.1f}s)")


# ── Main ─────────────────────────────────────────────────────
def main():
    total_start = time.time()

    # Carregar dados
    conn_local, df_loja, df_vivino = carregar_dados()

    # Criar tabela
    criar_tabela(conn_local)

    total_loja = len(df_loja)
    total_vivino = len(df_vivino)

    # NIVEL 1
    matched_ids_n1, resultados_n1, n1_hash, n1_ean, n1_exact = nivel1_deterministico(df_loja, df_vivino)

    # NIVEL 2
    splink_ids, resultados_n2 = nivel2_splink(df_loja, df_vivino, matched_ids_n1)
    all_matched = matched_ids_n1 | splink_ids

    # NIVEL 3 — sem match
    remaining_ids = set(df_loja['id'].tolist()) - all_matched
    resultados_n3 = []
    loja_nomes = df_loja.set_index('id')['nome_limpo'].to_dict()
    for uid in remaining_ids:
        loja_nome = loja_nomes.get(uid, '')
        resultados_n3.append((int(uid), None, 'no_match', None, None, loja_nome))

    # Salvar tudo
    all_results = resultados_n1 + resultados_n2 + resultados_n3
    salvar_resultados(conn_local, all_results)

    n_splink = len(resultados_n2)
    n_no_match = len(resultados_n3)
    n_com_match = len(resultados_n1) + n_splink
    taxa = (n_com_match / total_loja * 100) if total_loja > 0 else 0

    # Exemplos pra conferencia visual
    print("\n[Y8] === Exemplos NIVEL 1 (10 primeiros) ===")
    for r in resultados_n1[:10]:
        uid, vid, level, prob, viv_nome, loja_nome = r
        print(f"  [{level.upper()}] \"{loja_nome}\" (loja) → \"{viv_nome}\" (vivino) | prob={prob}")

    print("\n[Y8] === Exemplos NIVEL 2 - Splink (10 primeiros) ===")
    for r in resultados_n2[:10]:
        uid, vid, level, prob, viv_nome, loja_nome = r
        print(f"  [SPLINK] \"{loja_nome}\" (loja) → \"{viv_nome}\" (vivino) | prob={prob:.2f}")

    elapsed = time.time() - total_start

    print(f"""
=== GRUPO Y8 CONCLUIDO ===
Input: {total_loja:,} vinhos de wines_unique (IDs {ID_MIN} a {ID_MAX})
Vivino carregado: {total_vivino:,} vinhos

Nivel 1 (hash):       {n1_hash:,} matches
Nivel 1 (ean):        {n1_ean:,} matches
Nivel 1 (nome exato): {n1_exact:,} matches
Nivel 2 (Splink):     {n_splink:,} matches
Sem match:            {n_no_match:,} vinhos

Taxa de match: {taxa:.1f}% encontraram par no Vivino
Tabela: match_results_g8 populada com {len(all_results):,} registros
Tempo total: {elapsed:.0f}s ({elapsed/60:.1f}min)
""")

    conn_local.close()


if __name__ == "__main__":
    main()
