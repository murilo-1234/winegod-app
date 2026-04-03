"""
CHAT Y12 — Match Vinhos de Loja contra Vivino (Grupo 12 de 15)
Faixa: wines_unique WHERE id >= 2157684 AND id <= 2353836
"""

import psycopg2
import pandas as pd
import numpy as np
import time
import sys

# === CREDENCIAIS ===
LOCAL_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
RENDER_URL = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod"

# === FAIXA ===
ID_MIN = 2157684
ID_MAX = 2353836
GROUP = "Y12"
TABLE = "match_results_g12"
BATCH_SIZE = 5000


def create_result_table(conn):
    """Cria tabela de resultados no banco local."""
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
        CREATE INDEX IF NOT EXISTS idx_mr12_uid ON {TABLE} (unique_id);
        CREATE INDEX IF NOT EXISTS idx_mr12_vid ON {TABLE} (vivino_id) WHERE vivino_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_mr12_level ON {TABLE} (match_level);
    """)
    conn.commit()
    cur.close()


def insert_matches(conn, rows):
    """Insere matches em batches."""
    if not rows:
        return
    cur = conn.cursor()
    args_str = ",".join(
        cur.mogrify("(%s,%s,%s,%s,%s,%s)", r).decode()
        for r in rows
    )
    cur.execute(f"""
        INSERT INTO {TABLE} (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)
        VALUES {args_str}
    """)
    conn.commit()
    cur.close()


def insert_batched(conn, rows, label=""):
    """Insere em batches de BATCH_SIZE."""
    total = len(rows)
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        insert_matches(conn, batch)
        if label:
            done = min(i + BATCH_SIZE, total)
            print(f"  [{GROUP}] {label}: {done:,}/{total:,} inseridos", flush=True)


def main():
    t0 = time.time()

    # === PASSO 0 — Carregar dados ===
    print(f"[{GROUP}] Conectando ao banco local...", flush=True)
    conn_local = psycopg2.connect(LOCAL_URL)

    print(f"[{GROUP}] Carregando wines_unique (IDs {ID_MIN} a {ID_MAX})...", flush=True)
    df_loja = pd.read_sql(f"""
        SELECT id, nome_normalizado, produtor_normalizado, safra,
               tipo, pais_tabela, regiao, hash_dedup, ean_gtin, nome_limpo
        FROM wines_unique
        WHERE id >= {ID_MIN} AND id <= {ID_MAX}
    """, conn_local)
    print(f"[{GROUP}] Loja: {len(df_loja):,} vinhos carregados", flush=True)

    print(f"[{GROUP}] Carregando TODOS os vinhos Vivino (em chunks SQL)...", flush=True)
    chunks = []
    chunk_size = 50000
    offset = 0
    col_names = ['vivino_id', 'nome_normalizado', 'produtor_normalizado', 'safra',
                 'tipo', 'pais_code', 'regiao', 'hash_dedup', 'ean_gtin', 'nome']
    while True:
        rows = None
        for attempt in range(5):
            try:
                cr = psycopg2.connect(RENDER_URL, sslmode='require',
                                      connect_timeout=60,
                                      options='-c statement_timeout=120000')
                with cr.cursor() as cur_v:
                    cur_v.execute(f"""
                        SELECT id as vivino_id, nome_normalizado, produtor_normalizado, safra,
                               tipo, pais as pais_code, regiao, hash_dedup, ean_gtin, nome
                        FROM wines
                        ORDER BY id
                        LIMIT {chunk_size} OFFSET {offset}
                    """)
                    rows = cur_v.fetchall()
                cr.close()
                break
            except Exception as e:
                try:
                    cr.close()
                except:
                    pass
                wait = 10 * (attempt + 1)
                print(f"  [{GROUP}] Tentativa {attempt+1}/5 falhou: {e}. Aguardando {wait}s...", flush=True)
                time.sleep(wait)
        if rows is None:
            raise Exception(f"Falha ao carregar chunk no offset {offset} apos 5 tentativas")
        if not rows:
            break
        chunks.append(pd.DataFrame(rows, columns=col_names))
        offset += len(rows)
        print(f"  [{GROUP}] Vivino: {offset:,} carregados...", flush=True)
        time.sleep(2)
    df_vivino = pd.concat(chunks, ignore_index=True)
    del chunks
    print(f"[{GROUP}] Vivino: {len(df_vivino):,} vinhos carregados", flush=True)

    # Converter safra do Vivino pra int
    df_vivino['safra'] = pd.to_numeric(df_vivino['safra'], errors='coerce').astype('Int64')

    # Criar tabela de resultados
    create_result_table(conn_local)

    # Limpar resultados anteriores (caso re-rode)
    cur = conn_local.cursor()
    cur.execute(f"DELETE FROM {TABLE}")
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

    # === NIVEL 1a — Match por hash_dedup ===
    print(f"\n[{GROUP}] Nivel 1a — Match por hash_dedup...", flush=True)
    loja_hash = df_loja[df_loja['hash_dedup'].notna()].copy()
    vivino_hash = df_vivino[df_vivino['hash_dedup'].notna()][['vivino_id', 'hash_dedup', 'nome']].copy()
    matches_hash = loja_hash.merge(vivino_hash, on='hash_dedup', how='inner')
    matches_hash = matches_hash.drop_duplicates(subset='id', keep='first')

    for _, row in matches_hash.iterrows():
        all_results.append((
            int(row['id']), int(row['vivino_id']), 'hash', 1.0,
            row['nome'], row.get('nome_limpo', row.get('nome_normalizado', ''))
        ))
    matched_ids.update(matches_hash['id'].tolist())
    count_hash = len(matches_hash)
    print(f"[{GROUP}] Nivel 1a (hash): {count_hash:,} matches", flush=True)

    # === NIVEL 1b — Match por ean_gtin ===
    print(f"[{GROUP}] Nivel 1b — Match por ean_gtin...", flush=True)
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_ean = remaining[remaining['ean_gtin'].notna()].copy()
    vivino_ean = df_vivino[df_vivino['ean_gtin'].notna()][['vivino_id', 'ean_gtin', 'nome']].copy()
    matches_ean = remaining_ean.merge(vivino_ean, on='ean_gtin', how='inner')
    matches_ean = matches_ean.drop_duplicates(subset='id', keep='first')

    for _, row in matches_ean.iterrows():
        all_results.append((
            int(row['id']), int(row['vivino_id']), 'ean', 1.0,
            row['nome'], row.get('nome_limpo', row.get('nome_normalizado', ''))
        ))
    matched_ids.update(matches_ean['id'].tolist())
    count_ean = len(matches_ean)
    print(f"[{GROUP}] Nivel 1b (ean): {count_ean:,} matches", flush=True)

    # === NIVEL 1c — Match por nome_normalizado + safra ===
    print(f"[{GROUP}] Nivel 1c — Match por nome_normalizado + safra...", flush=True)
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    vivino_nome_safra = df_vivino[['vivino_id', 'nome_normalizado', 'safra', 'nome']].copy()
    matches_exact = remaining.merge(vivino_nome_safra, on=['nome_normalizado', 'safra'], how='inner')
    matches_exact = matches_exact.drop_duplicates(subset='id', keep='first')

    # Validacao: tipo deve bater
    if 'tipo_x' in matches_exact.columns and 'tipo_y' in matches_exact.columns:
        matches_exact = matches_exact[
            (matches_exact['tipo_x'].isna()) |
            (matches_exact['tipo_y'].isna()) |
            (matches_exact['tipo_x'] == matches_exact['tipo_y'])
        ]

    for _, row in matches_exact.iterrows():
        all_results.append((
            int(row['id']), int(row['vivino_id']), 'exact_name', 1.0,
            row['nome'], row.get('nome_limpo', row.get('nome_normalizado_x', ''))
        ))
    matched_ids.update(matches_exact['id'].tolist())
    count_exact_name = len(matches_exact)
    print(f"[{GROUP}] Nivel 1c (nome+safra): {count_exact_name:,} matches", flush=True)

    # === NIVEL 1d — Match por nome_normalizado sem safra (ambas NULL) ===
    print(f"[{GROUP}] Nivel 1d — Match por nome_normalizado (sem safra)...", flush=True)
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_no_safra = remaining[remaining['safra'].isna()]
    vivino_no_safra = df_vivino[df_vivino['safra'].isna()][['vivino_id', 'nome_normalizado', 'nome']].copy()
    matches_no_safra = remaining_no_safra.merge(vivino_no_safra, on='nome_normalizado', how='inner')
    matches_no_safra = matches_no_safra.drop_duplicates(subset='id', keep='first')

    for _, row in matches_no_safra.iterrows():
        all_results.append((
            int(row['id']), int(row['vivino_id']), 'exact_name', 1.0,
            row['nome'], row.get('nome_limpo', row.get('nome_normalizado_x', ''))
        ))
    matched_ids.update(matches_no_safra['id'].tolist())
    count_exact_no_safra = len(matches_no_safra)
    count_exact_name += count_exact_no_safra
    print(f"[{GROUP}] Nivel 1d (nome sem safra): {count_exact_no_safra:,} matches", flush=True)

    # Inserir todos os resultados nivel 1
    total_n1 = count_hash + count_ean + count_exact_name
    print(f"\n[{GROUP}] Total Nivel 1: {total_n1:,} matches. Inserindo...", flush=True)
    insert_batched(conn_local, all_results, "Nivel 1")

    # === NIVEL 2 — Splink ===
    print(f"\n[{GROUP}] Nivel 2 — Preparando Splink...", flush=True)
    df_loja_remaining = df_loja[~df_loja['id'].isin(matched_ids)].copy()
    remaining_count = len(df_loja_remaining)
    print(f"[{GROUP}] Vinhos restantes para Splink: {remaining_count:,}", flush=True)

    splink_results = []

    if remaining_count > 0:
        try:
            import splink.comparison_library as cl
            import splink.blocking_rule_library as brl
            from splink import DuckDBAPI, Linker, SettingsCreator, block_on

            # Preparar DataFrames
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

            # Substituir NaN por None em colunas de texto
            for col in ['nome_normalizado', 'produtor_normalizado', 'tipo', 'pais_code', 'regiao']:
                df_left[col] = df_left[col].where(df_left[col].notna(), None)
                df_right[col] = df_right[col].where(df_right[col].notna(), None)

            print(f"[{GROUP}] Configurando Splink (link_only)...", flush=True)

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
            print(f"[{GROUP}] Treinando modelo Splink...", flush=True)
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

            # Predizer
            print(f"[{GROUP}] Rodando predicao Splink (threshold=0.50)...", flush=True)
            results = linker.inference.predict(threshold_match_probability=0.50)
            df_predictions = results.as_pandas_dataframe()
            print(f"[{GROUP}] Splink retornou {len(df_predictions):,} pares candidatos", flush=True)

            if len(df_predictions) > 0:
                # Filtrar apenas matches >= 0.80
                df_high = df_predictions[df_predictions['match_probability'] >= 0.80].copy()
                print(f"[{GROUP}] Splink pares com prob >= 0.80: {len(df_high):,}", flush=True)

                if len(df_high) > 0:
                    # unique_id_l = loja (df_left), unique_id_r = vivino (df_right)
                    # Pegar o melhor match por vinho de loja
                    df_high = df_high.sort_values('match_probability', ascending=False)
                    df_high = df_high.drop_duplicates(subset='unique_id_l', keep='first')

                    # Validacao de tipo
                    if 'tipo_l' in df_high.columns and 'tipo_r' in df_high.columns:
                        df_high = df_high[
                            (df_high['tipo_l'].isna()) |
                            (df_high['tipo_r'].isna()) |
                            (df_high['tipo_l'] == df_high['tipo_r'])
                        ]

                    # Buscar nomes pra conferencia
                    vivino_names = df_vivino.set_index('vivino_id')['nome'].to_dict()
                    loja_names = df_loja.set_index('id')

                    for _, row in df_high.iterrows():
                        loja_id = int(row['unique_id_l'])
                        viv_id = int(row['unique_id_r'])
                        prob = float(row['match_probability'])
                        viv_nome = vivino_names.get(viv_id, '')
                        try:
                            l_nome = loja_names.loc[loja_id, 'nome_limpo'] or loja_names.loc[loja_id, 'nome_normalizado']
                        except Exception:
                            l_nome = ''
                        splink_results.append((loja_id, viv_id, 'splink_high', prob, viv_nome, l_nome))

                    count_splink = len(splink_results)
                    print(f"[{GROUP}] Nivel 2 (Splink high): {count_splink:,} matches", flush=True)

                    # Inserir matches Splink
                    insert_batched(conn_local, splink_results, "Nivel 2 Splink")
                    matched_ids.update([r[0] for r in splink_results])

        except ImportError as e:
            print(f"[{GROUP}] AVISO: Splink nao disponivel ({e}). Pulando nivel 2.", flush=True)
        except Exception as e:
            print(f"[{GROUP}] ERRO no Splink: {e}", flush=True)
            import traceback
            traceback.print_exc()

    # === NIVEL 3 — Sem match ===
    print(f"\n[{GROUP}] Nivel 3 — Registrando vinhos sem match...", flush=True)
    no_match_ids = set(df_loja['id'].tolist()) - matched_ids
    count_no_match = len(no_match_ids)

    no_match_rows = []
    for uid in no_match_ids:
        try:
            row = df_loja[df_loja['id'] == uid].iloc[0]
            l_nome = row.get('nome_limpo', '') or row.get('nome_normalizado', '')
        except Exception:
            l_nome = ''
        no_match_rows.append((int(uid), None, 'no_match', None, None, l_nome))

    insert_batched(conn_local, no_match_rows, "no_match")
    print(f"[{GROUP}] Sem match: {count_no_match:,} vinhos", flush=True)

    # === RESUMO FINAL ===
    total_input = len(df_loja)
    total_com_match = count_hash + count_ean + count_exact_name + count_splink
    taxa = (total_com_match / total_input * 100) if total_input > 0 else 0
    total_registros = total_com_match + count_no_match

    elapsed = time.time() - t0

    print(f"\n{'='*50}")
    print(f"=== GRUPO {GROUP} CONCLUIDO ===")
    print(f"Input: {total_input:,} vinhos de wines_unique (IDs {ID_MIN} a {ID_MAX})")
    print(f"Vivino carregado: {len(df_vivino):,} vinhos")
    print(f"")
    print(f"Nivel 1 (hash):       {count_hash:,} matches")
    print(f"Nivel 1 (ean):        {count_ean:,} matches")
    print(f"Nivel 1 (nome exato): {count_exact_name:,} matches")
    print(f"Nivel 2 (Splink):     {count_splink:,} matches")
    print(f"Sem match:            {count_no_match:,} vinhos")
    print(f"")
    print(f"Taxa de match: {taxa:.1f}% encontraram par no Vivino")
    print(f"Tabela: {TABLE} populada com {total_registros:,} registros")
    print(f"Tempo total: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"{'='*50}")

    # === EXEMPLOS ===
    print(f"\n--- Exemplos Nivel 1 (hash/ean/exact) ---")
    n1_examples = [r for r in all_results if r[2] in ('hash', 'ean', 'exact_name')][:10]
    for r in n1_examples:
        level = r[2].upper()
        print(f"  [{level}] \"{r[5]}\" (loja) -> \"{r[4]}\" (vivino) | prob={r[3]}")

    print(f"\n--- Exemplos Nivel 2 (Splink) ---")
    splink_examples = splink_results[:10]
    if splink_examples:
        for r in splink_examples:
            print(f"  [SPLINK] \"{r[5]}\" (loja) -> \"{r[4]}\" (vivino) | prob={r[3]:.2f}")
    else:
        print("  (nenhum match Splink)")

    # Verificacao SQL
    print(f"\n--- Verificacao ---")
    cur = conn_local.cursor()
    cur.execute(f"""
        SELECT match_level, COUNT(*), ROUND(AVG(match_probability)::numeric, 2) as prob_media
        FROM {TABLE} GROUP BY match_level ORDER BY COUNT(*) DESC;
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} registros (prob media: {row[2]})")
    cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
    print(f"  Total: {cur.fetchone()[0]:,}")
    cur.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE vivino_id IS NOT NULL")
    print(f"  Com match: {cur.fetchone()[0]:,}")
    cur.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE vivino_id IS NULL")
    print(f"  Sem match: {cur.fetchone()[0]:,}")
    cur.close()

    conn_local.close()
    print(f"\n[{GROUP}] Finalizado com sucesso!", flush=True)


if __name__ == "__main__":
    main()
