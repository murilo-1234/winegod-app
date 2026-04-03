"""
CHAT Y3 — Match Vinhos de Loja contra Vivino (Grupo 3 de 15)
Faixa: wines_unique WHERE id >= 392307 AND id <= 588459
"""

import psycopg2
import pandas as pd
import numpy as np
import re
import time
import sys
import io

# Fix encoding para Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# --- Credenciais ---
LOCAL_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
RENDER_URL = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod"

# --- Faixa deste grupo ---
ID_MIN = 392307
ID_MAX = 588459
GROUP = "Y3"
TABLE_NAME = "match_results_g3"
BATCH_SIZE = 5000

# Regex para remover safra (ano 4 digitos) do final ou meio do nome
RE_SAFRA = re.compile(r'\b(19|20)\d{2}\b')


def strip_safra_from_name(nome):
    """Remove ano (safra) do nome normalizado para comparar com Vivino."""
    if not nome or not isinstance(nome, str):
        return nome
    cleaned = RE_SAFRA.sub('', nome).strip()
    # Remover espacos duplos
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned if cleaned else nome


def create_result_table(conn):
    """Cria tabela de resultado no banco local."""
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
    """)
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_mr3_uid ON {TABLE_NAME} (unique_id);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_mr3_vid ON {TABLE_NAME} (vivino_id) WHERE vivino_id IS NOT NULL;")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_mr3_level ON {TABLE_NAME} (match_level);")
    conn.commit()
    cur.close()


def insert_matches(conn, records):
    """Insere registros em batches."""
    if not records:
        return
    cur = conn.cursor()
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        args_str = ",".join(
            cur.mogrify("(%s,%s,%s,%s,%s,%s)", r).decode()
            for r in batch
        )
        cur.execute(f"""
            INSERT INTO {TABLE_NAME} (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)
            VALUES {args_str}
        """)
        conn.commit()
    cur.close()


def log(msg):
    print(f"[{GROUP}] {msg}", flush=True)


def main():
    t0 = time.time()

    # =============================================
    # PASSO 0 — Carregar dados
    # =============================================
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

    # Tentar carregar Vivino do cache local primeiro
    import os
    VIVINO_CACHE = os.path.join(os.path.dirname(__file__), 'vivino_cache.parquet')

    if os.path.exists(VIVINO_CACHE):
        log(f"Carregando Vivino do cache local ({VIVINO_CACHE})...")
        df_vivino = pd.read_parquet(VIVINO_CACHE)
        log(f"Vivino carregado do cache: {len(df_vivino):,} vinhos")
    else:
        log("Conectando ao Render (Vivino)...")
        vivino_query = """
            SELECT id as vivino_id, nome_normalizado, produtor_normalizado, safra,
                   tipo, pais as pais_code, regiao, hash_dedup, ean_gtin, nome
            FROM wines
        """
        FETCH_SIZE = 100000
        for attempt in range(5):
            try:
                conn_render = psycopg2.connect(RENDER_URL, connect_timeout=60)
                conn_render.set_session(autocommit=False)
                log(f"Carregando Vivino em batches de {FETCH_SIZE:,} (tentativa {attempt + 1})...")
                cur_r = conn_render.cursor(name='vivino_fetch')
                cur_r.itersize = FETCH_SIZE
                cur_r.execute(vivino_query)
                col_names = [desc[0] for desc in cur_r.description]
                all_rows = []
                batch_num = 0
                while True:
                    rows = cur_r.fetchmany(FETCH_SIZE)
                    if not rows:
                        break
                    all_rows.extend(rows)
                    batch_num += 1
                    log(f"  Batch {batch_num}: {len(all_rows):,} registros carregados...")
                cur_r.close()
                conn_render.close()
                df_vivino = pd.DataFrame(all_rows, columns=col_names)
                log(f"Vivino carregado: {len(df_vivino):,} vinhos")
                # Salvar cache local
                log(f"Salvando cache em {VIVINO_CACHE}...")
                df_vivino.to_parquet(VIVINO_CACHE, index=False)
                log("Cache salvo!")
                break
            except Exception as e:
                log(f"Erro ao carregar Vivino (tentativa {attempt + 1}): {e}")
                try:
                    conn_render.close()
                except:
                    pass
                if attempt == 4:
                    raise
                wait = 15 * (attempt + 1)
                log(f"  Aguardando {wait}s antes de tentar novamente...")
                import time as t
                t.sleep(wait)

    # Converter safra do Vivino pra int
    df_vivino['safra'] = pd.to_numeric(df_vivino['safra'], errors='coerce').astype('Int64')

    # IMPORTANTE: Loja embute safra no nome_normalizado, Vivino nao.
    # Criar coluna nome_sem_safra na loja para comparacao
    log("Criando nome_sem_safra (removendo ano do nome da loja)...")
    df_loja['nome_sem_safra'] = df_loja['nome_normalizado'].apply(strip_safra_from_name)

    # Criar tabela de resultado
    create_result_table(conn_local)

    # Limpar resultados anteriores (caso re-execute)
    cur = conn_local.cursor()
    cur.execute(f"DELETE FROM {TABLE_NAME};")
    conn_local.commit()
    cur.close()

    matched_ids = set()
    all_records = []  # (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)

    counters = {
        'hash': 0,
        'ean': 0,
        'exact_name': 0,
        'exact_name_no_safra': 0,
        'splink_high': 0,
        'no_match': 0,
    }

    # =============================================
    # NIVEL 1a — Match por hash_dedup
    # =============================================
    log("Nivel 1a: Match por hash_dedup...")
    loja_hash = df_loja[df_loja['hash_dedup'].notna()].copy()
    vivino_hash = df_vivino[df_vivino['hash_dedup'].notna()][['vivino_id', 'hash_dedup', 'nome']].copy()

    matches_hash = loja_hash.merge(vivino_hash, on='hash_dedup', how='inner')
    matches_hash = matches_hash.drop_duplicates(subset='id', keep='first')

    for _, row in matches_hash.iterrows():
        all_records.append((
            int(row['id']), int(row['vivino_id']), 'hash', 1.0,
            row['nome'], row['nome_limpo']
        ))
    matched_ids.update(matches_hash['id'].tolist())
    counters['hash'] = len(matches_hash)
    log(f"  hash_dedup: {counters['hash']:,} matches")

    # =============================================
    # NIVEL 1b — Match por ean_gtin
    # =============================================
    log("Nivel 1b: Match por ean_gtin...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    loja_ean = remaining[remaining['ean_gtin'].notna() & (remaining['ean_gtin'] != '')].copy()
    vivino_ean = df_vivino[df_vivino['ean_gtin'].notna() & (df_vivino['ean_gtin'] != '')][['vivino_id', 'ean_gtin', 'nome']].copy()

    matches_ean = loja_ean.merge(vivino_ean, on='ean_gtin', how='inner')
    matches_ean = matches_ean.drop_duplicates(subset='id', keep='first')

    for _, row in matches_ean.iterrows():
        all_records.append((
            int(row['id']), int(row['vivino_id']), 'ean', 1.0,
            row['nome'], row['nome_limpo']
        ))
    matched_ids.update(matches_ean['id'].tolist())
    counters['ean'] = len(matches_ean)
    log(f"  ean_gtin: {counters['ean']:,} matches")

    # =============================================
    # NIVEL 1c — Match por nome_sem_safra + safra
    # (loja nome sem ano == vivino nome_normalizado, E safras iguais)
    # =============================================
    log("Nivel 1c: Match por nome_sem_safra + safra...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]

    loja_with_safra = remaining[
        remaining['safra'].notna() & remaining['nome_sem_safra'].notna()
    ].copy()
    vivino_with_safra = df_vivino[
        df_vivino['safra'].notna() & df_vivino['nome_normalizado'].notna()
    ][['vivino_id', 'nome_normalizado', 'safra', 'nome', 'tipo']].copy()

    # Merge: loja.nome_sem_safra == vivino.nome_normalizado AND safra == safra
    vivino_with_safra = vivino_with_safra.rename(columns={
        'nome_normalizado': 'nome_sem_safra',
        'tipo': 'tipo_vivino'
    })
    matches_exact = loja_with_safra.merge(
        vivino_with_safra, on=['nome_sem_safra', 'safra'], how='inner'
    )

    # Validar tipo
    if len(matches_exact) > 0:
        mask_tipo_ok = (
            matches_exact['tipo'].isna() |
            matches_exact['tipo_vivino'].isna() |
            (matches_exact['tipo'] == '') |
            (matches_exact['tipo_vivino'] == '') |
            (matches_exact['tipo'] == matches_exact['tipo_vivino'])
        )
        matches_exact = matches_exact[mask_tipo_ok]

    matches_exact = matches_exact.drop_duplicates(subset='id', keep='first')

    for _, row in matches_exact.iterrows():
        all_records.append((
            int(row['id']), int(row['vivino_id']), 'exact_name', 1.0,
            row['nome'], row['nome_limpo']
        ))
    matched_ids.update(matches_exact['id'].tolist())
    counters['exact_name'] = len(matches_exact)
    log(f"  nome_sem_safra+safra: {counters['exact_name']:,} matches")

    # =============================================
    # NIVEL 1d — Match por nome_sem_safra (ambas safras NULL)
    # =============================================
    log("Nivel 1d: Match por nome_sem_safra (ambas safras NULL)...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_no_safra = remaining[
        remaining['safra'].isna() & remaining['nome_sem_safra'].notna()
    ]
    vivino_no_safra = df_vivino[
        df_vivino['safra'].isna() & df_vivino['nome_normalizado'].notna()
    ][['vivino_id', 'nome_normalizado', 'nome', 'tipo']].copy()
    vivino_no_safra = vivino_no_safra.rename(columns={
        'nome_normalizado': 'nome_sem_safra',
        'tipo': 'tipo_vivino'
    })

    matches_no_safra = remaining_no_safra.merge(
        vivino_no_safra, on='nome_sem_safra', how='inner'
    )

    # Validar tipo
    if len(matches_no_safra) > 0:
        mask_tipo_ok = (
            matches_no_safra['tipo'].isna() |
            matches_no_safra['tipo_vivino'].isna() |
            (matches_no_safra['tipo'] == '') |
            (matches_no_safra['tipo_vivino'] == '') |
            (matches_no_safra['tipo'] == matches_no_safra['tipo_vivino'])
        )
        matches_no_safra = matches_no_safra[mask_tipo_ok]

    matches_no_safra = matches_no_safra.drop_duplicates(subset='id', keep='first')

    for _, row in matches_no_safra.iterrows():
        all_records.append((
            int(row['id']), int(row['vivino_id']), 'exact_name', 1.0,
            row['nome'], row['nome_limpo']
        ))
    matched_ids.update(matches_no_safra['id'].tolist())
    counters['exact_name_no_safra'] = len(matches_no_safra)
    log(f"  nome sem safra: {counters['exact_name_no_safra']:,} matches")

    # =============================================
    # NIVEL 1e — Match por nome_sem_safra (loja tem safra, Vivino nao, ou vice-versa)
    # Usa apenas o nome sem safra para match, ignorando safra
    # =============================================
    log("Nivel 1e: Match por nome_sem_safra (safra ignorada)...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_with_nome = remaining[remaining['nome_sem_safra'].notna()].copy()
    vivino_all_nomes = df_vivino[df_vivino['nome_normalizado'].notna()][
        ['vivino_id', 'nome_normalizado', 'nome', 'tipo']
    ].copy()
    vivino_all_nomes = vivino_all_nomes.rename(columns={
        'nome_normalizado': 'nome_sem_safra',
        'tipo': 'tipo_vivino'
    })

    matches_nome_only = remaining_with_nome.merge(
        vivino_all_nomes, on='nome_sem_safra', how='inner'
    )

    # Validar tipo
    if len(matches_nome_only) > 0:
        mask_tipo_ok = (
            matches_nome_only['tipo'].isna() |
            matches_nome_only['tipo_vivino'].isna() |
            (matches_nome_only['tipo'] == '') |
            (matches_nome_only['tipo_vivino'] == '') |
            (matches_nome_only['tipo'] == matches_nome_only['tipo_vivino'])
        )
        matches_nome_only = matches_nome_only[mask_tipo_ok]

    matches_nome_only = matches_nome_only.drop_duplicates(subset='id', keep='first')
    nome_only_count = len(matches_nome_only)

    for _, row in matches_nome_only.iterrows():
        all_records.append((
            int(row['id']), int(row['vivino_id']), 'exact_name', 1.0,
            row['nome'], row['nome_limpo']
        ))
    matched_ids.update(matches_nome_only['id'].tolist())
    log(f"  nome_sem_safra (qualquer safra): {nome_only_count:,} matches")
    counters['exact_name'] += counters['exact_name_no_safra'] + nome_only_count

    # Salvar matches nivel 1
    log(f"Salvando {len(all_records):,} matches nivel 1...")
    insert_matches(conn_local, all_records)
    nivel1_total = len(all_records)
    log(f"Nivel 1 completo: {nivel1_total:,} matches salvos")

    # =============================================
    # NIVEL 2 — Probabilistico com Splink
    # =============================================
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    log(f"Nivel 2: {len(remaining):,} vinhos restantes para Splink...")

    splink_records = []
    if len(remaining) > 0:
        try:
            import splink.comparison_library as cl
            import splink.blocking_rule_library as brl
            from splink import DuckDBAPI, Linker, SettingsCreator, block_on

            # Preparar loja (usar nome_sem_safra como nome_normalizado para Splink)
            df_loja_remaining = remaining.copy()
            df_loja_remaining['nome_normalizado'] = df_loja_remaining['nome_sem_safra']
            df_loja_remaining = df_loja_remaining.rename(columns={'id': 'unique_id', 'pais_tabela': 'pais_code'})
            df_loja_remaining['source_dataset'] = 'loja'

            df_vivino_splink = df_vivino.copy()
            df_vivino_splink['source_dataset'] = 'vivino'
            df_vivino_splink = df_vivino_splink.rename(columns={'vivino_id': 'unique_id'})

            cols = ['unique_id', 'nome_normalizado', 'produtor_normalizado',
                    'safra', 'tipo', 'pais_code', 'regiao', 'source_dataset']

            df_left = df_loja_remaining[cols].copy()
            df_right = df_vivino_splink[cols].copy()

            # Converter safra pra string pro Splink
            df_left['safra'] = df_left['safra'].astype(str).replace('<NA>', None).replace('nan', None)
            df_right['safra'] = df_right['safra'].astype(str).replace('<NA>', None).replace('nan', None)

            # Substituir NaN/None em strings
            for col in ['nome_normalizado', 'produtor_normalizado', 'regiao', 'tipo', 'pais_code']:
                df_left[col] = df_left[col].where(df_left[col].notna(), None)
                df_right[col] = df_right[col].where(df_right[col].notna(), None)

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
                    brl.CustomRule(
                        "SUBSTR(l.nome_normalizado,1,15) = SUBSTR(r.nome_normalizado,1,15)"
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

            log("Gerando predicoes Splink...")
            results = linker.inference.predict(threshold_match_probability=0.50)
            df_predictions = results.as_pandas_dataframe()
            log(f"  Splink retornou {len(df_predictions):,} pares candidatos")

            if len(df_predictions) > 0:
                df_predictions = df_predictions.sort_values('match_probability', ascending=False)

                # Pegar apenas matches >= 0.80 (splink_high)
                df_high = df_predictions[df_predictions['match_probability'] >= 0.80].copy()

                # Um vinho de loja so pode ter 1 match
                df_high = df_high.drop_duplicates(subset='unique_id_l', keep='first')

                # Validar tipo
                if 'tipo_l' in df_high.columns and 'tipo_r' in df_high.columns:
                    mask_tipo_ok = (
                        df_high['tipo_l'].isna() |
                        df_high['tipo_r'].isna() |
                        (df_high['tipo_l'] == '') |
                        (df_high['tipo_r'] == '') |
                        (df_high['tipo_l'] == df_high['tipo_r'])
                    )
                    df_high = df_high[mask_tipo_ok]

                # Buscar nomes pra conferencia
                loja_names = df_loja_remaining.set_index('unique_id')['nome_normalizado'].to_dict()
                vivino_names = df_vivino_splink.set_index('unique_id')['nome'].to_dict()

                for _, row in df_high.iterrows():
                    uid_loja = int(row['unique_id_l'])
                    uid_vivino = int(row['unique_id_r'])
                    prob = float(row['match_probability'])
                    v_nome = vivino_names.get(uid_vivino, '')
                    l_nome = loja_names.get(uid_loja, '')
                    splink_records.append((
                        uid_loja, uid_vivino, 'splink_high', prob, v_nome, l_nome
                    ))

                matched_ids.update([r[0] for r in splink_records])
                counters['splink_high'] = len(splink_records)
                log(f"  Splink high (>=0.80): {counters['splink_high']:,} matches")

                # Salvar matches Splink
                insert_matches(conn_local, splink_records)
                log(f"  Splink matches salvos")

        except ImportError:
            log("AVISO: splink nao instalado. Pulando nivel 2.")
            log("  Instale com: pip install splink[duckdb]")
        except Exception as e:
            log(f"ERRO no Splink: {e}")
            import traceback
            traceback.print_exc()

    # =============================================
    # NIVEL 3 — Sem match
    # =============================================
    remaining_final = df_loja[~df_loja['id'].isin(matched_ids)]
    counters['no_match'] = len(remaining_final)
    log(f"Sem match: {counters['no_match']:,} vinhos")

    # Registrar no_match
    no_match_records = []
    for _, row in remaining_final.iterrows():
        no_match_records.append((
            int(row['id']), None, 'no_match', None, None, row['nome_limpo']
        ))
    insert_matches(conn_local, no_match_records)
    log(f"no_match registrados: {counters['no_match']:,}")

    # =============================================
    # ENTREGAVEL — Resumo final
    # =============================================
    total = len(df_loja)
    total_com_match = total - counters['no_match']
    taxa = (total_com_match / total * 100) if total > 0 else 0
    total_registros = total

    elapsed = time.time() - t0

    print(f"""
=== GRUPO {GROUP} CONCLUIDO ===
Input: {total:,} vinhos de wines_unique (IDs {ID_MIN} a {ID_MAX})
Vivino carregado: {len(df_vivino):,} vinhos

Nivel 1 (hash):       {counters['hash']:,} matches
Nivel 1 (ean):        {counters['ean']:,} matches
Nivel 1 (nome exato): {counters['exact_name']:,} matches
Nivel 2 (Splink):     {counters['splink_high']:,} matches
Sem match:            {counters['no_match']:,} vinhos

Taxa de match: {taxa:.1f}% encontraram par no Vivino
Tabela: {TABLE_NAME} populada com {total_registros:,} registros
Tempo: {elapsed/60:.1f} minutos
""")

    # --- Exemplos pra conferencia visual ---
    cur = conn_local.cursor()

    print("--- 10 exemplos Nivel 1 (deterministico) ---")
    cur.execute(f"""
        SELECT match_level, loja_nome, vivino_nome, match_probability
        FROM {TABLE_NAME}
        WHERE match_level IN ('hash', 'ean', 'exact_name')
        AND vivino_nome IS NOT NULL
        LIMIT 10
    """)
    for row in cur.fetchall():
        level = row[0].upper() if row[0] else '?'
        loja = row[1] or '?'
        vivino = row[2] or '?'
        prob = row[3]
        print(f'  [{level}] "{loja}" (loja) -> "{vivino}" (vivino) | prob={prob}')

    print("\n--- 10 exemplos Nivel 2 (Splink) ---")
    cur.execute(f"""
        SELECT match_level, loja_nome, vivino_nome, match_probability
        FROM {TABLE_NAME}
        WHERE match_level = 'splink_high'
        AND vivino_nome IS NOT NULL
        ORDER BY match_probability DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            loja = row[1] or '?'
            vivino = row[2] or '?'
            prob = row[3]
            print(f'  [SPLINK] "{loja}" (loja) -> "{vivino}" (vivino) | prob={prob:.2f}')
    else:
        print("  (nenhum match Splink)")

    cur.close()
    conn_local.close()
    log("Finalizado!")


if __name__ == "__main__":
    main()
