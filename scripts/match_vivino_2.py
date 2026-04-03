"""
CHAT Y2 — Match Vinhos de Loja contra Vivino (Grupo 2 de 15)
Faixa: wines_unique WHERE id >= 196154 AND id <= 392306
"""

import psycopg2
import psycopg2.extras
import pandas as pd
import numpy as np
import time
import sys

# ── Credenciais ──────────────────────────────────────────────
LOCAL_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
RENDER_URL = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod"

# ── Faixa deste grupo ───────────────────────────────────────
ID_MIN = 196154
ID_MAX = 392306
GROUP = "Y2"
TABLE_NAME = "match_results_g2"
BATCH_SIZE = 5000

def log(msg):
    print(f"[{GROUP}] {msg}", flush=True)

def create_results_table(conn):
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id SERIAL PRIMARY KEY,
            unique_id INTEGER NOT NULL,
            vivino_id INTEGER,
            match_level VARCHAR(20) NOT NULL,
            match_probability REAL,
            vivino_nome TEXT,
            loja_nome TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mr2_uid ON {TABLE_NAME} (unique_id);
        CREATE INDEX IF NOT EXISTS idx_mr2_vid ON {TABLE_NAME} (vivino_id) WHERE vivino_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_mr2_level ON {TABLE_NAME} (match_level);
    """)
    conn.commit()
    cur.close()

def insert_batch(conn, rows):
    if not rows:
        return
    cur = conn.cursor()
    psycopg2.extras.execute_values(
        cur,
        f"""INSERT INTO {TABLE_NAME}
            (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)
            VALUES %s""",
        rows,
        page_size=BATCH_SIZE
    )
    conn.commit()
    cur.close()

def validate_tipo(df_matches, df_loja, df_vivino):
    """Remove matches onde o tipo diverge (tinto vs branco, etc)."""
    if df_matches.empty:
        return df_matches

    if 'tipo_loja' in df_matches.columns and 'tipo_vivino' in df_matches.columns:
        mask = (
            df_matches['tipo_loja'].isna() |
            df_matches['tipo_vivino'].isna() |
            (df_matches['tipo_loja'] == df_matches['tipo_vivino'])
        )
        removed = len(df_matches) - mask.sum()
        if removed > 0:
            log(f"  Tipo validation removeu {removed:,} matches")
        return df_matches[mask].copy()
    return df_matches

def main():
    t0 = time.time()

    # ── PASSO 0: Carregar dados ──────────────────────────────
    log("Conectando ao banco LOCAL...")
    conn_local = psycopg2.connect(LOCAL_URL)

    log(f"Carregando wines_unique (IDs {ID_MIN:,} a {ID_MAX:,})...")
    df_loja = pd.read_sql(f"""
        SELECT id, nome_normalizado, produtor_normalizado, safra,
               tipo, pais_tabela, regiao, hash_dedup, ean_gtin, nome_limpo
        FROM wines_unique
        WHERE id >= {ID_MIN} AND id <= {ID_MAX}
    """, conn_local)
    log(f"Loja carregada: {len(df_loja):,} vinhos")

    log("Conectando ao banco RENDER...")
    conn_render = psycopg2.connect(RENDER_URL)

    log("Carregando TODOS os vinhos Vivino...")
    df_vivino = pd.read_sql("""
        SELECT id as vivino_id, nome_normalizado, produtor_normalizado, safra,
               tipo, pais as pais_code, regiao, hash_dedup, ean_gtin, nome
        FROM wines
    """, conn_render)
    conn_render.close()
    log(f"Vivino carregado: {len(df_vivino):,} vinhos")

    # Converter safra do Vivino pra int
    df_vivino['safra'] = pd.to_numeric(df_vivino['safra'], errors='coerce').astype('Int64')

    # Criar tabela de resultados
    log("Criando tabela de resultados...")
    create_results_table(conn_local)

    # Limpar resultados anteriores (re-run safety)
    cur = conn_local.cursor()
    cur.execute(f"DELETE FROM {TABLE_NAME}")
    conn_local.commit()
    cur.close()

    matched_ids = set()
    all_results = []  # (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)

    # Contadores
    count_hash = 0
    count_ean = 0
    count_exact_name = 0
    count_exact_no_safra = 0
    count_splink = 0
    count_no_match = 0

    # ── NIVEL 1a: Match por hash_dedup ───────────────────────
    log("Nivel 1a: Match por hash_dedup...")
    loja_hash = df_loja[df_loja['hash_dedup'].notna()].copy()
    vivino_hash = df_vivino[df_vivino['hash_dedup'].notna()][['vivino_id', 'hash_dedup', 'nome', 'tipo']].copy()

    matches_hash = loja_hash.merge(vivino_hash, on='hash_dedup', how='inner', suffixes=('', '_viv'))

    # Validar tipo
    matches_hash = matches_hash.rename(columns={'tipo': 'tipo_loja', 'tipo_viv': 'tipo_vivino'})
    matches_hash = validate_tipo(matches_hash, df_loja, df_vivino)
    matches_hash = matches_hash.drop_duplicates(subset='id', keep='first')

    for _, row in matches_hash.iterrows():
        all_results.append((
            int(row['id']), int(row['vivino_id']), 'hash', 1.0,
            row.get('nome', None), row.get('nome_limpo', None)
        ))
    matched_ids.update(matches_hash['id'].tolist())
    count_hash = len(matches_hash)
    log(f"  hash_dedup: {count_hash:,} matches")

    # ── NIVEL 1b: Match por ean_gtin ─────────────────────────
    log("Nivel 1b: Match por ean_gtin...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_ean = remaining[remaining['ean_gtin'].notna()].copy()
    vivino_ean = df_vivino[df_vivino['ean_gtin'].notna()][['vivino_id', 'ean_gtin', 'nome', 'tipo']].copy()

    matches_ean = remaining_ean.merge(vivino_ean, on='ean_gtin', how='inner', suffixes=('', '_viv'))
    matches_ean = matches_ean.rename(columns={'tipo': 'tipo_loja', 'tipo_viv': 'tipo_vivino'})
    matches_ean = validate_tipo(matches_ean, df_loja, df_vivino)
    matches_ean = matches_ean.drop_duplicates(subset='id', keep='first')

    for _, row in matches_ean.iterrows():
        all_results.append((
            int(row['id']), int(row['vivino_id']), 'ean', 1.0,
            row.get('nome', None), row.get('nome_limpo', None)
        ))
    matched_ids.update(matches_ean['id'].tolist())
    count_ean = len(matches_ean)
    log(f"  ean_gtin: {count_ean:,} matches")

    # ── NIVEL 1c: Match por nome_normalizado + safra ─────────
    log("Nivel 1c: Match por nome_normalizado + safra exato...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_safra = remaining[remaining['safra'].notna() & remaining['nome_normalizado'].notna()].copy()
    vivino_safra = df_vivino[df_vivino['safra'].notna() & df_vivino['nome_normalizado'].notna()][
        ['vivino_id', 'nome_normalizado', 'safra', 'nome', 'tipo']
    ].copy()

    matches_exact = remaining_safra.merge(
        vivino_safra, on=['nome_normalizado', 'safra'], how='inner', suffixes=('', '_viv')
    )
    matches_exact = matches_exact.rename(columns={'tipo': 'tipo_loja', 'tipo_viv': 'tipo_vivino'})
    matches_exact = validate_tipo(matches_exact, df_loja, df_vivino)
    matches_exact = matches_exact.drop_duplicates(subset='id', keep='first')

    for _, row in matches_exact.iterrows():
        all_results.append((
            int(row['id']), int(row['vivino_id']), 'exact_name', 1.0,
            row.get('nome', None), row.get('nome_limpo', None)
        ))
    matched_ids.update(matches_exact['id'].tolist())
    count_exact_name = len(matches_exact)
    log(f"  nome+safra exato: {count_exact_name:,} matches")

    # ── NIVEL 1d: Match por nome_normalizado sem safra ───────
    log("Nivel 1d: Match por nome_normalizado (ambas safras NULL)...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_no_safra = remaining[remaining['safra'].isna() & remaining['nome_normalizado'].notna()].copy()
    vivino_no_safra = df_vivino[df_vivino['safra'].isna() & df_vivino['nome_normalizado'].notna()][
        ['vivino_id', 'nome_normalizado', 'nome', 'tipo']
    ].copy()

    matches_no_safra = remaining_no_safra.merge(
        vivino_no_safra, on='nome_normalizado', how='inner', suffixes=('', '_viv')
    )
    matches_no_safra = matches_no_safra.rename(columns={'tipo': 'tipo_loja', 'tipo_viv': 'tipo_vivino'})
    matches_no_safra = validate_tipo(matches_no_safra, df_loja, df_vivino)
    matches_no_safra = matches_no_safra.drop_duplicates(subset='id', keep='first')

    for _, row in matches_no_safra.iterrows():
        all_results.append((
            int(row['id']), int(row['vivino_id']), 'exact_name', 1.0,
            row.get('nome', None), row.get('nome_limpo', None)
        ))
    matched_ids.update(matches_no_safra['id'].tolist())
    count_exact_no_safra = len(matches_no_safra)
    count_exact_name += count_exact_no_safra
    log(f"  nome sem safra: {count_exact_no_safra:,} matches")

    # Salvar nivel 1
    log(f"Salvando {len(all_results):,} resultados do Nivel 1...")
    for i in range(0, len(all_results), BATCH_SIZE):
        insert_batch(conn_local, all_results[i:i+BATCH_SIZE])
    nivel1_total = len(all_results)
    log(f"Nivel 1 total: {nivel1_total:,} matches salvos")

    # ── NIVEL 2: Splink probabilistico ───────────────────────
    log("Nivel 2: Preparando Splink...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)].copy()
    log(f"  Restantes pra Splink: {len(remaining):,} vinhos")

    splink_results = []

    if len(remaining) > 0:
        try:
            import splink.comparison_library as cl
            import splink.blocking_rule_library as brl
            from splink import DuckDBAPI, Linker, SettingsCreator, block_on

            # Preparar DataFrames pro Splink
            df_left = remaining.rename(columns={'id': 'unique_id', 'pais_tabela': 'pais_code'}).copy()
            df_left['source_dataset'] = 'loja'

            df_right = df_vivino.rename(columns={'vivino_id': 'unique_id'}).copy()
            df_right['source_dataset'] = 'vivino'

            cols = ['unique_id', 'nome_normalizado', 'produtor_normalizado',
                    'safra', 'tipo', 'pais_code', 'regiao', 'source_dataset']

            df_left = df_left[cols].copy()
            df_right = df_right[cols].copy()

            # Converter safra pra string pro Splink
            df_left['safra'] = df_left['safra'].astype(str).replace('<NA>', None).replace('nan', None)
            df_right['safra'] = df_right['safra'].astype(str).replace('<NA>', None).replace('nan', None)

            # Substituir strings 'None'/'nan'/'<NA>' por None real
            for df in [df_left, df_right]:
                df['safra'] = df['safra'].where(~df['safra'].isin(['None', 'nan', '<NA>', 'NaN']), None)
                df['nome_normalizado'] = df['nome_normalizado'].where(df['nome_normalizado'].notna(), None)
                df['produtor_normalizado'] = df['produtor_normalizado'].where(df['produtor_normalizado'].notna(), None)
                df['regiao'] = df['regiao'].where(df['regiao'].notna(), None)

            log(f"  Splink: left={len(df_left):,} (loja) | right={len(df_right):,} (vivino)")

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

            log("  Treinando modelo Splink...")
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

            log("  Executando predicoes Splink...")
            results = linker.inference.predict(threshold_match_probability=0.50)
            df_predictions = results.as_pandas_dataframe()
            log(f"  Splink retornou {len(df_predictions):,} pares candidatos")

            if len(df_predictions) > 0:
                # unique_id_l = loja (df_left), unique_id_r = vivino (df_right)
                df_high = df_predictions[df_predictions['match_probability'] >= 0.80].copy()

                # Pegar melhor match por vinho de loja
                df_high = df_high.sort_values('match_probability', ascending=False)
                df_high = df_high.drop_duplicates(subset='unique_id_l', keep='first')

                # Validar tipo
                if 'tipo_l' in df_high.columns and 'tipo_r' in df_high.columns:
                    mask = (
                        df_high['tipo_l'].isna() |
                        df_high['tipo_r'].isna() |
                        (df_high['tipo_l'] == df_high['tipo_r'])
                    )
                    removed = len(df_high) - mask.sum()
                    if removed > 0:
                        log(f"  Splink tipo validation removeu {removed:,} matches")
                    df_high = df_high[mask].copy()

                # Buscar nomes pra conferencia
                loja_names = df_loja.set_index('id')['nome_limpo'].to_dict()
                vivino_names = df_vivino.set_index('vivino_id')['nome'].to_dict()

                for _, row in df_high.iterrows():
                    loja_id = int(row['unique_id_l'])
                    viv_id = int(row['unique_id_r'])
                    prob = float(row['match_probability'])
                    splink_results.append((
                        loja_id, viv_id, 'splink_high', prob,
                        vivino_names.get(viv_id), loja_names.get(loja_id)
                    ))
                    matched_ids.add(loja_id)

                count_splink = len(splink_results)
                log(f"  Splink high (>=0.80): {count_splink:,} matches")

        except ImportError:
            log("  AVISO: splink nao instalado. Instalando...")
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "splink[duckdb]"])
            log("  splink instalado. Re-execute o script.")
            conn_local.close()
            return
        except Exception as e:
            log(f"  ERRO no Splink: {e}")
            import traceback
            traceback.print_exc()

    # Salvar Splink results
    if splink_results:
        log(f"Salvando {len(splink_results):,} resultados do Splink...")
        for i in range(0, len(splink_results), BATCH_SIZE):
            insert_batch(conn_local, splink_results[i:i+BATCH_SIZE])

    # ── NIVEL 3: Sem match ───────────────────────────────────
    log("Nivel 3: Registrando vinhos sem match...")
    remaining_final = df_loja[~df_loja['id'].isin(matched_ids)]
    no_match_results = []
    for _, row in remaining_final.iterrows():
        no_match_results.append((
            int(row['id']), None, 'no_match', None,
            None, row.get('nome_limpo', None)
        ))
    count_no_match = len(no_match_results)

    if no_match_results:
        log(f"Salvando {count_no_match:,} vinhos sem match...")
        for i in range(0, len(no_match_results), BATCH_SIZE):
            insert_batch(conn_local, no_match_results[i:i+BATCH_SIZE])

    # ── RELATORIO FINAL ──────────────────────────────────────
    elapsed = time.time() - t0
    total_input = len(df_loja)
    total_vivino = len(df_vivino)
    total_com_match = count_hash + count_ean + count_exact_name + count_splink
    taxa = (total_com_match / total_input * 100) if total_input > 0 else 0
    total_registros = total_com_match + count_no_match

    print(f"""
=== GRUPO {GROUP} CONCLUIDO ===
Input: {total_input:,} vinhos de wines_unique (IDs {ID_MIN:,} a {ID_MAX:,})
Vivino carregado: {total_vivino:,} vinhos

Nivel 1 (hash):       {count_hash:,} matches
Nivel 1 (ean):        {count_ean:,} matches
Nivel 1 (nome exato): {count_exact_name:,} matches
Nivel 2 (Splink):     {count_splink:,} matches
Sem match:            {count_no_match:,} vinhos

Taxa de match: {taxa:.1f}% encontraram par no Vivino
Tabela: {TABLE_NAME} populada com {total_registros:,} registros
Tempo: {elapsed/60:.1f} minutos
""")

    # ── Exemplos pra conferencia ─────────────────────────────
    print("--- 10 exemplos Nivel 1 (deterministico) ---")
    cur = conn_local.cursor()
    cur.execute(f"""
        SELECT match_level, loja_nome, vivino_nome, match_probability
        FROM {TABLE_NAME}
        WHERE match_level IN ('hash', 'ean', 'exact_name')
        AND vivino_nome IS NOT NULL AND loja_nome IS NOT NULL
        LIMIT 10
    """)
    for row in cur.fetchall():
        level, loja, vivino, prob = row
        print(f'  [{level.upper()}] "{loja}" (loja) -> "{vivino}" (vivino) | prob={prob}')

    print("\n--- 10 exemplos Nivel 2 (Splink) ---")
    cur.execute(f"""
        SELECT match_level, loja_nome, vivino_nome, match_probability
        FROM {TABLE_NAME}
        WHERE match_level = 'splink_high'
        AND vivino_nome IS NOT NULL AND loja_nome IS NOT NULL
        ORDER BY match_probability DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        level, loja, vivino, prob = row
        print(f'  [{level.upper()}] "{loja}" (loja) -> "{vivino}" (vivino) | prob={prob:.2f}')

    cur.close()

    # Verificacao final
    print("\n--- Verificacao SQL ---")
    cur = conn_local.cursor()
    cur.execute(f"""
        SELECT match_level, COUNT(*), ROUND(AVG(match_probability)::numeric, 2) as prob_media
        FROM {TABLE_NAME} GROUP BY match_level ORDER BY COUNT(*) DESC
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} registros (prob media: {row[2]})")

    cur.close()
    conn_local.close()
    log("Done!")

if __name__ == "__main__":
    main()
