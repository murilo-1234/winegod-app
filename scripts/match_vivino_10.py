"""
CHAT Y10 — Match Vinhos de Loja contra Vivino (Grupo 10 de 15)
Faixa: wines_unique WHERE id >= 1765378 AND id <= 1961530
"""

import psycopg2
import pandas as pd
import numpy as np
import time
import sys
import os

# ── Credenciais ──────────────────────────────────────────────
LOCAL_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
RENDER_URL = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod"

ID_MIN = 1765378
ID_MAX = 1961530
BATCH_SIZE = 5000
GROUP = "Y10"

def log(msg):
    print(f"[{GROUP}] {msg}", flush=True)

def create_result_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS match_results_g10 (
            id SERIAL PRIMARY KEY,
            unique_id INTEGER NOT NULL,
            vivino_id INTEGER,
            match_level VARCHAR(20) NOT NULL,
            match_probability REAL,
            vivino_nome TEXT,
            loja_nome TEXT
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mr10_uid ON match_results_g10 (unique_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mr10_vid ON match_results_g10 (vivino_id) WHERE vivino_id IS NOT NULL;")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mr10_level ON match_results_g10 (match_level);")
    conn.commit()
    cur.close()

def insert_matches(conn, records):
    """Insert list of (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome)."""
    if not records:
        return
    cur = conn.cursor()
    args = ",".join(
        cur.mogrify("(%s,%s,%s,%s,%s,%s)", r).decode() for r in records
    )
    cur.execute(
        "INSERT INTO match_results_g10 (unique_id, vivino_id, match_level, match_probability, vivino_nome, loja_nome) VALUES " + args
    )
    conn.commit()
    cur.close()

def insert_batched(conn, records, label=""):
    total = len(records)
    for i in range(0, total, BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]
        insert_matches(conn, batch)
        if label:
            log(f"  {label}: inseridos {min(i+BATCH_SIZE, total):,}/{total:,}")

# ── PASSO 0: Carregar dados ─────────────────────────────────
def load_data():
    log("Carregando wines_unique (local)...")
    t0 = time.time()
    conn_local = psycopg2.connect(LOCAL_URL)
    df_loja = pd.read_sql(f"""
        SELECT id, nome_normalizado, produtor_normalizado, safra,
               tipo, pais_tabela, regiao, hash_dedup, ean_gtin, nome_limpo
        FROM wines_unique
        WHERE id >= {ID_MIN} AND id <= {ID_MAX}
    """, conn_local)
    conn_local.close()
    log(f"  Loja carregada: {len(df_loja):,} vinhos ({time.time()-t0:.1f}s)")

    # Tentar cache local primeiro
    cache_path = os.path.join(os.path.dirname(__file__), "vivino_cache.parquet")
    if os.path.exists(cache_path):
        log(f"Carregando Vivino do cache local ({cache_path})...")
        t0 = time.time()
        df_vivino = pd.read_parquet(cache_path)
        log(f"  Vivino carregado do cache: {len(df_vivino):,} vinhos ({time.time()-t0:.1f}s)")
    else:
        log("Carregando wines Vivino (Render) com retry...")
        t0 = time.time()
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                log(f"  Tentativa {attempt}/{max_retries}...")
                conn_render = psycopg2.connect(RENDER_URL, connect_timeout=30,
                                                keepalives=1, keepalives_idle=30,
                                                keepalives_interval=10, keepalives_count=5)
                cur_render = conn_render.cursor(name='vivino_fetch')
                cur_render.itersize = 50000
                cur_render.execute("""
                    SELECT id as vivino_id, nome_normalizado, produtor_normalizado, safra,
                           tipo, pais as pais_code, regiao, hash_dedup, ean_gtin, nome
                    FROM wines
                """)
                cols_vivino = ['vivino_id', 'nome_normalizado', 'produtor_normalizado', 'safra',
                               'tipo', 'pais_code', 'regiao', 'hash_dedup', 'ean_gtin', 'nome']
                chunks = []
                total_fetched = 0
                while True:
                    rows = cur_render.fetchmany(50000)
                    if not rows:
                        break
                    chunks.append(pd.DataFrame(rows, columns=cols_vivino))
                    total_fetched += len(rows)
                    if total_fetched % 200000 == 0:
                        log(f"  Vivino: {total_fetched:,} carregados...")
                cur_render.close()
                conn_render.close()
                df_vivino = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(columns=cols_vivino)
                # Salvar cache
                df_vivino.to_parquet(cache_path, index=False)
                log(f"  Vivino carregado e cacheado: {len(df_vivino):,} vinhos ({time.time()-t0:.1f}s)")
                break
            except Exception as e:
                log(f"  Erro na tentativa {attempt}: {e}")
                if attempt == max_retries:
                    raise RuntimeError(f"Nao foi possivel conectar ao Render apos {max_retries} tentativas. "
                                       f"Tente novamente mais tarde ou copie vivino_cache.parquet de outro grupo.")

    # Converter safra Vivino (varchar) pra Int64
    df_vivino['safra'] = pd.to_numeric(df_vivino['safra'], errors='coerce').astype('Int64')

    return df_loja, df_vivino


# ── NIVEL 1: Deterministico ─────────────────────────────────
def nivel1(df_loja, df_vivino):
    matched_ids = set()
    results_hash = []
    results_ean = []
    results_exact = []
    results_nosafra = []
    examples_n1 = []

    # 1a. Hash
    log("Nivel 1a: match por hash_dedup...")
    loja_h = df_loja[df_loja['hash_dedup'].notna() & (df_loja['hash_dedup'] != '')].copy()
    viv_h = df_vivino[df_vivino['hash_dedup'].notna() & (df_vivino['hash_dedup'] != '')][['vivino_id', 'hash_dedup', 'nome', 'tipo']].copy()
    matches_hash = loja_h.merge(viv_h, on='hash_dedup', how='inner', suffixes=('', '_viv'))
    # Validar tipo
    matches_hash = matches_hash[
        matches_hash['tipo'].isna() | matches_hash['tipo_viv'].isna() |
        (matches_hash['tipo'] == matches_hash['tipo_viv'])
    ]
    matches_hash = matches_hash.drop_duplicates(subset='id', keep='first')
    for _, r in matches_hash.iterrows():
        results_hash.append((int(r['id']), int(r['vivino_id']), 'hash', 1.0, r['nome'], r['nome_limpo']))
    matched_ids.update(matches_hash['id'].tolist())
    log(f"  Hash: {len(results_hash):,} matches")

    # 1b. EAN
    log("Nivel 1b: match por ean_gtin...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    loja_e = remaining[remaining['ean_gtin'].notna() & (remaining['ean_gtin'] != '')].copy()
    viv_e = df_vivino[df_vivino['ean_gtin'].notna() & (df_vivino['ean_gtin'] != '')][['vivino_id', 'ean_gtin', 'nome', 'tipo']].copy()
    matches_ean = loja_e.merge(viv_e, on='ean_gtin', how='inner', suffixes=('', '_viv'))
    matches_ean = matches_ean[
        matches_ean['tipo'].isna() | matches_ean['tipo_viv'].isna() |
        (matches_ean['tipo'] == matches_ean['tipo_viv'])
    ]
    matches_ean = matches_ean.drop_duplicates(subset='id', keep='first')
    for _, r in matches_ean.iterrows():
        results_ean.append((int(r['id']), int(r['vivino_id']), 'ean', 1.0, r['nome'], r['nome_limpo']))
    matched_ids.update(matches_ean['id'].tolist())
    log(f"  EAN: {len(results_ean):,} matches")

    # 1c. Nome + safra exato
    log("Nivel 1c: match por nome_normalizado + safra...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_with_safra = remaining[remaining['nome_normalizado'].notna() & remaining['safra'].notna()].copy()
    viv_name = df_vivino[df_vivino['nome_normalizado'].notna() & df_vivino['safra'].notna()][['vivino_id', 'nome_normalizado', 'safra', 'nome', 'tipo']].copy()
    matches_exact = remaining_with_safra.merge(viv_name, on=['nome_normalizado', 'safra'], how='inner', suffixes=('', '_viv'))
    matches_exact = matches_exact[
        matches_exact['tipo'].isna() | matches_exact['tipo_viv'].isna() |
        (matches_exact['tipo'] == matches_exact['tipo_viv'])
    ]
    matches_exact = matches_exact.drop_duplicates(subset='id', keep='first')
    for _, r in matches_exact.iterrows():
        results_exact.append((int(r['id']), int(r['vivino_id']), 'exact_name', 1.0, r['nome'], r['nome_limpo']))
    matched_ids.update(matches_exact['id'].tolist())
    log(f"  Nome exato + safra: {len(results_exact):,} matches")

    # 1d. Nome sem safra (ambos NULL)
    log("Nivel 1d: match por nome_normalizado sem safra (ambas NULL)...")
    remaining = df_loja[~df_loja['id'].isin(matched_ids)]
    remaining_no_safra = remaining[remaining['nome_normalizado'].notna() & remaining['safra'].isna()].copy()
    viv_no_safra = df_vivino[df_vivino['nome_normalizado'].notna() & df_vivino['safra'].isna()][['vivino_id', 'nome_normalizado', 'nome', 'tipo']].copy()
    matches_ns = remaining_no_safra.merge(viv_no_safra, on='nome_normalizado', how='inner', suffixes=('', '_viv'))
    matches_ns = matches_ns[
        matches_ns['tipo'].isna() | matches_ns['tipo_viv'].isna() |
        (matches_ns['tipo'] == matches_ns['tipo_viv'])
    ]
    matches_ns = matches_ns.drop_duplicates(subset='id', keep='first')
    for _, r in matches_ns.iterrows():
        results_nosafra.append((int(r['id']), int(r['vivino_id']), 'exact_name', 1.0, r['nome'], r['nome_limpo']))
    matched_ids.update(matches_ns['id'].tolist())
    log(f"  Nome sem safra: {len(results_nosafra):,} matches")

    # Exemplos nivel 1
    for label, df_ex in [('HASH', matches_hash), ('EAN', matches_ean), ('EXACT', matches_exact), ('NO_SAFRA', matches_ns)]:
        for _, r in df_ex.head(3).iterrows():
            examples_n1.append(f'[{label}] "{r["nome_limpo"]}" (loja) -> "{r["nome"]}" (vivino) | prob=1.0')

    all_n1 = results_hash + results_ean + results_exact + results_nosafra
    return all_n1, matched_ids, examples_n1, len(results_hash), len(results_ean), len(results_exact) + len(results_nosafra)


# ── NIVEL 2: Splink ─────────────────────────────────────────
def nivel2(df_loja, df_vivino, matched_ids):
    import splink.comparison_library as cl
    import splink.blocking_rule_library as brl
    from splink import DuckDBAPI, Linker, SettingsCreator, block_on

    df_loja_remaining = df_loja[~df_loja['id'].isin(matched_ids)].copy()
    log(f"Nivel 2: {len(df_loja_remaining):,} vinhos restantes para Splink...")

    if len(df_loja_remaining) == 0:
        log("  Nenhum vinho restante para Splink.")
        return [], set(), []

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

    # Substituir strings 'None'/'nan'/'<NA>' por None real
    for df in [df_left, df_right]:
        df['safra'] = df['safra'].where(~df['safra'].isin(['None', 'nan', '<NA>', 'NaT']), None)
        df['nome_normalizado'] = df['nome_normalizado'].where(df['nome_normalizado'].notna(), None)
        df['produtor_normalizado'] = df['produtor_normalizado'].where(df['produtor_normalizado'].notna(), None)
        df['regiao'] = df['regiao'].where(df['regiao'].notna(), None)

    log(f"  Splink: left={len(df_left):,}, right={len(df_right):,}")

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
    log("  Treinando modelo Splink...")
    t0 = time.time()
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
    log(f"  Treino concluido ({time.time()-t0:.1f}s)")

    # Predizer
    log("  Predizendo matches...")
    t0 = time.time()
    results = linker.inference.predict(threshold_match_probability=0.50)
    df_predictions = results.as_pandas_dataframe()
    log(f"  Predicoes: {len(df_predictions):,} pares ({time.time()-t0:.1f}s)")

    if len(df_predictions) == 0:
        log("  Nenhum par encontrado pelo Splink.")
        return [], set(), []

    # Identificar loja vs vivino pelos source_dataset
    # df_left (loja) e passado primeiro, df_right (vivino) segundo
    # unique_id_l = loja, unique_id_r = vivino
    df_high = df_predictions[df_predictions['match_probability'] >= 0.80].copy()

    # Validar tipo: descartar matches onde tipo diverge
    if 'tipo_l' in df_high.columns and 'tipo_r' in df_high.columns:
        df_high = df_high[
            df_high['tipo_l'].isna() | df_high['tipo_r'].isna() |
            (df_high['tipo_l'] == df_high['tipo_r'])
        ]

    # Pegar melhor match por vinho de loja
    df_high = df_high.sort_values('match_probability', ascending=False)
    df_high = df_high.drop_duplicates(subset='unique_id_l', keep='first')

    # Buscar nomes para conferencia
    nome_map_loja = df_loja_remaining.set_index('unique_id')['nome_normalizado'].to_dict() if 'nome_normalizado' in df_loja_remaining.columns else {}
    nome_limpo_map = df_loja[['id', 'nome_limpo']].set_index('id')['nome_limpo'].to_dict()
    nome_map_vivino = df_vivino.set_index('vivino_id')['nome'].to_dict() if 'nome' in df_vivino.columns else {}

    results_splink = []
    examples_n2 = []
    splink_matched_ids = set()

    for _, r in df_high.iterrows():
        loja_id = int(r['unique_id_l'])
        viv_id = int(r['unique_id_r'])
        prob = float(r['match_probability'])
        viv_nome = nome_map_vivino.get(viv_id, '')
        loja_nome = nome_limpo_map.get(loja_id, nome_map_loja.get(loja_id, ''))

        results_splink.append((loja_id, viv_id, 'splink_high', prob, viv_nome, loja_nome))
        splink_matched_ids.add(loja_id)

        if len(examples_n2) < 10:
            examples_n2.append(f'[SPLINK] "{loja_nome}" (loja) -> "{viv_nome}" (vivino) | prob={prob:.2f}')

    log(f"  Splink high (>=0.80): {len(results_splink):,} matches")
    return results_splink, splink_matched_ids, examples_n2


# ── MAIN ─────────────────────────────────────────────────────
def main():
    t_start = time.time()

    # Carregar dados
    df_loja, df_vivino = load_data()
    total_loja = len(df_loja)
    total_vivino = len(df_vivino)

    # Criar tabela resultado
    conn_local = psycopg2.connect(LOCAL_URL)
    create_result_table(conn_local)

    # Limpar resultados anteriores desta faixa (re-run safe)
    cur = conn_local.cursor()
    cur.execute(f"DELETE FROM match_results_g10 WHERE unique_id >= {ID_MIN} AND unique_id <= {ID_MAX}")
    conn_local.commit()
    cur.close()
    log("Tabela match_results_g10 pronta (limpa para re-run)")

    # ── Nivel 1 ──
    log("=" * 50)
    log("NIVEL 1 — Deterministico")
    t0 = time.time()
    results_n1, matched_ids, examples_n1, cnt_hash, cnt_ean, cnt_exact = nivel1(df_loja, df_vivino)
    log(f"Nivel 1 total: {len(results_n1):,} matches ({time.time()-t0:.1f}s)")

    # Inserir nivel 1
    insert_batched(conn_local, results_n1, "Nivel 1")

    # ── Nivel 2 ──
    log("=" * 50)
    log("NIVEL 2 — Splink probabilistico")
    t0 = time.time()
    results_n2, splink_ids, examples_n2 = nivel2(df_loja, df_vivino, matched_ids)
    log(f"Nivel 2 total: {len(results_n2):,} matches ({time.time()-t0:.1f}s)")

    # Inserir nivel 2
    insert_batched(conn_local, results_n2, "Nivel 2")

    matched_ids.update(splink_ids)

    # ── Nivel 3 — Sem match ──
    log("=" * 50)
    log("NIVEL 3 — Sem match")
    no_match_ids = set(df_loja['id'].tolist()) - matched_ids
    results_nomatch = []
    for uid in no_match_ids:
        nome_limpo = df_loja.loc[df_loja['id'] == uid, 'nome_limpo'].values
        loja_nome = nome_limpo[0] if len(nome_limpo) > 0 else ''
        results_nomatch.append((int(uid), None, 'no_match', None, None, loja_nome))
    log(f"Sem match: {len(results_nomatch):,} vinhos")

    insert_batched(conn_local, results_nomatch, "No match")

    conn_local.close()

    # ── Relatorio final ──
    elapsed = time.time() - t_start
    total_matches = len(results_n1) + len(results_n2)

    print("\n" + "=" * 55)
    print(f"=== GRUPO {GROUP} CONCLUIDO ===")
    print(f"Input: {total_loja:,} vinhos de wines_unique (IDs {ID_MIN} a {ID_MAX})")
    print(f"Vivino carregado: {total_vivino:,} vinhos")
    print()
    print(f"Nivel 1 (hash):       {cnt_hash:,} matches")
    print(f"Nivel 1 (ean):        {cnt_ean:,} matches")
    print(f"Nivel 1 (nome exato): {cnt_exact:,} matches")
    print(f"Nivel 2 (Splink):     {len(results_n2):,} matches")
    print(f"Sem match:            {len(results_nomatch):,} vinhos")
    print()
    taxa = (total_matches / total_loja * 100) if total_loja > 0 else 0
    print(f"Taxa de match: {taxa:.1f}% encontraram par no Vivino")
    print(f"Tabela: match_results_g10 populada com {total_loja:,} registros")
    print(f"Tempo total: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    # Exemplos
    print("\n--- Exemplos Nivel 1 (deterministico) ---")
    for ex in examples_n1[:10]:
        print(f"  {ex}")

    print("\n--- Exemplos Nivel 2 (Splink) ---")
    for ex in examples_n2[:10]:
        print(f"  {ex}")

    print("=" * 55)


if __name__ == "__main__":
    main()
