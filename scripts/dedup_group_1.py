"""
CHAT X1 — Deduplicacao de Vinhos (Grupo 1: US)
Deduplica vinhos da tabela wines_clean para wines_unique_g1.
3 niveis: deterministico + Splink probabilistico + quarentena.
"""

import sys
import time
import warnings

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

warnings.filterwarnings("ignore")

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
PAISES = ["us"]
GROUP = 1
BATCH_SIZE = 5000


# ── DB Setup ─────────────────────────────────────────────────────────────────

def create_tables(conn):
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS wines_unique_g1 CASCADE;")
    cur.execute("DROP TABLE IF EXISTS dedup_quarantine_g1 CASCADE;")
    cur.execute("""
        CREATE TABLE wines_unique_g1 (
            id SERIAL PRIMARY KEY,
            nome_limpo TEXT NOT NULL,
            nome_normalizado TEXT NOT NULL,
            produtor TEXT,
            produtor_normalizado TEXT,
            safra INTEGER,
            tipo TEXT,
            pais TEXT,
            pais_tabela VARCHAR(5),
            regiao TEXT,
            sub_regiao TEXT,
            uvas TEXT,
            rating_melhor REAL,
            total_ratings_max INTEGER,
            preco_min_global REAL,
            preco_max_global REAL,
            moeda_referencia VARCHAR(10),
            url_imagem TEXT,
            hash_dedup VARCHAR(64),
            ean_gtin VARCHAR(50),
            match_type VARCHAR(20) NOT NULL,
            match_probability REAL,
            total_copias INTEGER,
            clean_ids INTEGER[]
        );
    """)
    cur.execute("""
        CREATE TABLE dedup_quarantine_g1 (
            id SERIAL PRIMARY KEY,
            clean_id_a INTEGER NOT NULL,
            clean_id_b INTEGER NOT NULL,
            nome_a TEXT,
            nome_b TEXT,
            match_probability REAL,
            motivo TEXT
        );
    """)
    conn.commit()
    print("[X1] Tabelas criadas.")


def load_wines(conn):
    pais_filter = "','".join(PAISES)
    query = f"""
        SELECT id, pais_tabela, nome_limpo, nome_normalizado,
               produtor_extraido, produtor_normalizado, safra, tipo,
               pais, regiao, sub_regiao, uvas, rating, total_ratings,
               preco, moeda, url_imagem, hash_dedup, ean_gtin
        FROM wines_clean
        WHERE pais_tabela IN ('{pais_filter}')
    """
    print(f"[X1] Carregando vinhos...")
    t0 = time.time()
    df = pd.read_sql(query, conn)
    print(f"[X1] Carregados {len(df):,} vinhos em {time.time()-t0:.1f}s")
    return df


# ── Nivel 1: Deterministico (vectorized) ────────────────────────────────────

def nivel_1_deterministico(df):
    """
    Assign group_id to each row via deterministic matching.
    Returns: (df with dedup_group col, quarantine_list, stats)
    """
    print("\n[X1] === NIVEL 1: Deterministico ===")
    t0 = time.time()

    # Initialize: no group assigned
    df["dedup_group"] = -1
    next_group = 0
    quarantine = []

    # 1a. hash_dedup — group by duplicate hashes
    hash_mask = df["hash_dedup"].notna() & (df["hash_dedup"] != "")
    if hash_mask.any():
        counts = df.loc[hash_mask, "hash_dedup"].value_counts()
        dup_hashes = counts[counts > 1].index
        if len(dup_hashes) > 0:
            dup_mask = hash_mask & df["hash_dedup"].isin(dup_hashes)
            # Assign group ids
            hash_groups = df.loc[dup_mask].groupby("hash_dedup")
            for _, gidx in hash_groups.groups.items():
                df.loc[gidx, "dedup_group"] = next_group
                next_group += 1
            n_hash = len(dup_hashes)
            n_hash_wines = int(dup_mask.sum())
            print(f"[X1] 1a. hash_dedup: {n_hash:,} grupos, {n_hash_wines:,} vinhos")
        else:
            print("[X1] 1a. hash_dedup: 0 grupos")
    else:
        print("[X1] 1a. hash_dedup: 0 grupos")

    # 1b. ean_gtin — for wines not yet grouped
    ungrouped = df["dedup_group"] == -1
    ean_mask = ungrouped & df["ean_gtin"].notna() & (df["ean_gtin"] != "")
    if ean_mask.any():
        counts = df.loc[ean_mask, "ean_gtin"].value_counts()
        dup_eans = counts[counts > 1].index
        if len(dup_eans) > 0:
            dup_mask = ean_mask & df["ean_gtin"].isin(dup_eans)
            ean_groups = df.loc[dup_mask].groupby("ean_gtin")
            for _, gidx in ean_groups.groups.items():
                df.loc[gidx, "dedup_group"] = next_group
                next_group += 1
            print(f"[X1] 1b. ean_gtin: {len(dup_eans):,} grupos, {int(dup_mask.sum()):,} vinhos")
        else:
            print("[X1] 1b. ean_gtin: 0 grupos")
    else:
        print("[X1] 1b. ean_gtin: 0 grupos")

    # 1c. nome_normalizado + safra — for wines not yet grouped
    ungrouped = df["dedup_group"] == -1
    df_rem = df[ungrouped].copy()
    df_rem["safra_key"] = df_rem["safra"].fillna(-1).astype(int)
    group_key = df_rem.groupby(["pais_tabela", "nome_normalizado", "safra_key"]).ngroup()
    # Only keep groups with 2+ members
    key_counts = group_key.value_counts()
    dup_keys = key_counts[key_counts > 1].index
    dup_mask_local = group_key.isin(dup_keys)

    if dup_mask_local.any():
        # Assign unique group ids offset by next_group
        offsets = group_key[dup_mask_local].map(
            dict(zip(sorted(dup_keys), range(next_group, next_group + len(dup_keys))))
        )
        df.loc[offsets.index, "dedup_group"] = offsets.values
        n_name = len(dup_keys)
        n_name_wines = int(dup_mask_local.sum())
        next_group += n_name
        print(f"[X1] 1c. nome+safra: {n_name:,} grupos, {n_name_wines:,} vinhos")
    else:
        print("[X1] 1c. nome+safra: 0 grupos")

    # Validate groups: check tipo consistency, price variance, group size
    grouped = df[df["dedup_group"] >= 0]
    n_det_groups = grouped["dedup_group"].nunique()
    n_det_wines = len(grouped)
    print(f"[X1] Validando {n_det_groups:,} grupos...")

    bad_groups = set()
    # Check tipo conflicts
    tipo_nunique = grouped.groupby("dedup_group")["tipo"].apply(
        lambda s: s.dropna().nunique()
    )
    bad_tipo = tipo_nunique[tipo_nunique > 1].index.tolist()

    # Check price variance > 10x
    preco_clean = grouped["preco"].where(grouped["preco"] > 0)
    preco_stats = grouped.assign(preco_clean=preco_clean).groupby("dedup_group")["preco_clean"].agg(["min", "max", "count"])
    bad_price = preco_stats[(preco_stats["count"] >= 2) & (preco_stats["max"] / preco_stats["min"] > 10)].index.tolist()

    # Check group size > 100
    group_sizes = grouped.groupby("dedup_group").size()
    bad_size = group_sizes[group_sizes > 100].index.tolist()

    bad_groups = set(bad_tipo) | set(bad_price) | set(bad_size)

    if bad_groups:
        print(f"[X1] {len(bad_groups):,} grupos falharam validacao -> quarentena")
        # Generate quarantine pairs for bad groups
        for gid in bad_groups:
            gdf = df[df["dedup_group"] == gid]
            ids_list = gdf["id"].tolist()
            nomes = gdf["nome_limpo"].tolist()
            motivo = []
            if gid in bad_tipo:
                motivo.append("tipos_diferentes")
            if gid in bad_price:
                motivo.append("preco_10x")
            if gid in bad_size:
                motivo.append(f"grupo_{len(gdf)}")
            motivo_str = "validation: " + ",".join(motivo)
            for i in range(min(len(ids_list) - 1, 5)):
                quarantine.append((ids_list[0], ids_list[i+1], nomes[0], nomes[i+1], 1.0, motivo_str))
        # Ungroup bad groups
        df.loc[df["dedup_group"].isin(bad_groups), "dedup_group"] = -1

    n_valid_groups = df[df["dedup_group"] >= 0]["dedup_group"].nunique()
    n_valid_wines = int((df["dedup_group"] >= 0).sum())
    elapsed = time.time() - t0
    print(f"[X1] Nivel 1: {n_valid_groups:,} grupos validos, {n_valid_wines:,} vinhos agrupados em {elapsed:.1f}s")

    return df, quarantine, n_valid_groups


# ── Nivel 2: Splink Probabilistico ──────────────────────────────────────────

def nivel_2_splink(df, match_threshold=0.80, review_threshold=0.50):
    print("\n[X1] === NIVEL 2: Splink Probabilistico ===")

    ungrouped = df["dedup_group"] == -1
    df_remaining = df[ungrouped].copy()
    print(f"[X1] Vinhos restantes: {len(df_remaining):,}")

    if len(df_remaining) < 100:
        print("[X1] Poucos vinhos (<100), pulando Splink.")
        return {}, []

    cols = ["id", "nome_normalizado", "produtor_normalizado", "safra", "tipo", "regiao", "uvas"]
    df_splink = df_remaining[cols].copy()
    for col in ["nome_normalizado", "produtor_normalizado", "tipo", "regiao", "uvas"]:
        df_splink[col] = df_splink[col].where(df_splink[col].notna() & (df_splink[col] != ""), None)
    df_splink["safra"] = df_splink["safra"].where(df_splink["safra"].notna(), None)
    df_splink = df_splink.reset_index(drop=True)

    t0 = time.time()
    try:
        import splink.comparison_library as cl
        import splink.blocking_rule_library as brl
        from splink import DuckDBAPI, Linker, SettingsCreator, block_on

        training_block_nome = block_on("nome_normalizado")
        training_block_produtor = block_on("produtor_normalizado")

        prediction_blocking_rules = [
            block_on("produtor_normalizado", "safra"),
            brl.CustomRule("SUBSTR(l.nome_normalizado,1,20) = SUBSTR(r.nome_normalizado,1,20)"),
        ]

        settings = SettingsCreator(
            link_type="dedupe_only",
            unique_id_column_name="id",
            comparisons=[
                cl.JaroWinklerAtThresholds("nome_normalizado", [0.92, 0.80]),
                cl.JaroWinklerAtThresholds("produtor_normalizado", [0.92, 0.80]),
                cl.ExactMatch("safra"),
                cl.ExactMatch("tipo"),
                cl.JaroWinklerAtThresholds("regiao", [0.88]),
                cl.JaroWinklerAtThresholds("uvas", [0.88]),
            ],
            blocking_rules_to_generate_predictions=prediction_blocking_rules,
            retain_matching_columns=True,
        )

        print("[X1] Splink: inicializando...")
        db_api = DuckDBAPI()
        linker = Linker(df_splink, settings, db_api)

        print("[X1] Splink: estimando prior...")
        linker.training.estimate_probability_two_random_records_match(training_block_nome, recall=0.7)
        print("[X1] Splink: estimando u...")
        linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)
        print("[X1] Splink: EM (nome)...")
        linker.training.estimate_parameters_using_expectation_maximisation(training_block_nome, fix_u_probabilities=True)
        print("[X1] Splink: EM (produtor)...")
        linker.training.estimate_parameters_using_expectation_maximisation(training_block_produtor, fix_u_probabilities=True)

        print("[X1] Splink: predizendo...")
        results = linker.inference.predict(threshold_match_probability=review_threshold)
        df_pred = results.as_pandas_dataframe()
        print(f"[X1] Splink: {len(df_pred):,} pares encontrados")

        if len(df_pred) == 0:
            return {}, []

        # Quarantine pairs (vectorized)
        df_review = df_pred[
            (df_pred["match_probability"] >= review_threshold) &
            (df_pred["match_probability"] < match_threshold)
        ]
        quarantine_pairs = []
        if len(df_review) > 0:
            print(f"[X1] Preparando {len(df_review):,} pares quarentena...")
            id_to_nome = pd.Series(df_remaining["nome_limpo"].values, index=df_remaining["id"])
            q = df_review[["id_l", "id_r", "match_probability"]].copy()
            q["id_l"] = q["id_l"].astype(int)
            q["id_r"] = q["id_r"].astype(int)
            q["nome_a"] = q["id_l"].map(id_to_nome).fillna("")
            q["nome_b"] = q["id_r"].map(id_to_nome).fillna("")
            quarantine_pairs = list(zip(q["id_l"], q["id_r"], q["nome_a"], q["nome_b"],
                                        q["match_probability"],
                                        ["splink_uncertain"] * len(q)))

        # Cluster
        print("[X1] Splink: clusterizando...")
        clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
            results, threshold_match_probability=match_threshold
        )
        df_clusters = clusters.as_pandas_dataframe()

        splink_groups = {}
        if len(df_clusters) > 0:
            for cid, cdf in df_clusters.groupby("cluster_id"):
                ids = cdf["id"].tolist()
                if len(ids) > 1:
                    splink_groups[cid] = ids

        elapsed = time.time() - t0
        print(f"[X1] Splink: {len(splink_groups):,} clusters, {len(quarantine_pairs):,} quarentena em {elapsed:.1f}s")
        return splink_groups, quarantine_pairs

    except Exception as e:
        print(f"[X1] ERRO Splink: {e}")
        import traceback; traceback.print_exc()
        return {}, []


# ── Vectorized merge + save ──────────────────────────────────────────────────

def merge_and_save(conn, df, splink_groups, quarantine_pairs, n_det_groups):
    """Merge groups and save to DB using vectorized operations."""
    print("\n[X1] === Merge + Save ===")
    t0 = time.time()
    cur = conn.cursor()

    # Assign splink groups to df using vectorized id-to-group mapping
    max_det_group = int(df["dedup_group"].max()) if (df["dedup_group"] >= 0).any() else -1
    next_gid = max_det_group + 1

    # Build id->group_id map from splink clusters
    id_to_splink_gid = {}
    for cid, ids in splink_groups.items():
        for wine_id in ids:
            id_to_splink_gid[wine_id] = next_gid
        next_gid += 1

    # Apply mapping to ungrouped wines only
    ungrouped_mask = df["dedup_group"] == -1
    splink_gids = df.loc[ungrouped_mask, "id"].map(id_to_splink_gid)
    has_splink = splink_gids.notna()
    df.loc[splink_gids[has_splink].index, "dedup_group"] = splink_gids[has_splink].astype(int)

    # Validate splink groups (vectorized)
    splink_mask = df["dedup_group"] > max_det_group
    splink_df = df[splink_mask]
    bad_splink = set()

    if len(splink_df) > 0:
        # Check tipo conflicts
        tipo_n = splink_df.groupby("dedup_group")["tipo"].apply(lambda s: len(s.dropna().unique()))
        bad_splink |= set(tipo_n[tipo_n > 1].index)
        # Check price 10x
        preco_pos = splink_df["preco"].where(splink_df["preco"] > 0)
        ps = splink_df.assign(pp=preco_pos).groupby("dedup_group")["pp"].agg(["min", "max", "count"])
        bad_splink |= set(ps[(ps["count"] >= 2) & (ps["max"] / ps["min"] > 10)].index)
        # Check size > 100
        sizes = splink_df.groupby("dedup_group").size()
        bad_splink |= set(sizes[sizes > 100].index)

        if bad_splink:
            df.loc[df["dedup_group"].isin(bad_splink), "dedup_group"] = -1

    splink_valid = df[df["dedup_group"] > max_det_group]["dedup_group"].nunique()
    print(f"[X1] Splink validos: {splink_valid:,} clusters ({len(bad_splink)} falharam validacao)")

    # Now all wines with dedup_group >= 0 are in groups; -1 are singletons
    grouped_mask = df["dedup_group"] >= 0
    singleton_mask = ~grouped_mask
    n_singletons = int(singleton_mask.sum())
    n_grouped = int(grouped_mask.sum())
    n_groups = df.loc[grouped_mask, "dedup_group"].nunique()
    print(f"[X1] {n_groups:,} grupos ({n_grouped:,} vinhos) + {n_singletons:,} singletons")

    # ── Merge grouped wines (vectorized agg) ────────────────────────────
    print("[X1] Merging grupos...")
    t1 = time.time()

    grp = df[grouped_mask].copy()
    # Preco positivo para agg
    grp["preco_pos"] = grp["preco"].where(grp["preco"] > 0)
    # Nome length for picking longest
    grp["nome_len"] = grp["nome_limpo"].str.len()

    agg = grp.groupby("dedup_group").agg(
        nome_normalizado=("nome_normalizado", "first"),
        pais=("pais", "first"),
        pais_tabela=("pais_tabela", "first"),
        rating_melhor=("rating", "max"),
        total_ratings_max=("total_ratings", "max"),
        preco_min_global=("preco_pos", "min"),
        preco_max_global=("preco_pos", "max"),
        total_copias=("id", "count"),
        clean_ids=("id", lambda x: sorted(x.tolist())),
    ).reset_index()

    # Nome limpo: pick the longest per group
    idx_longest = grp.loc[grp.groupby("dedup_group")["nome_len"].idxmax()]
    nome_limpo_map = idx_longest.set_index("dedup_group")["nome_limpo"]
    agg["nome_limpo"] = agg["dedup_group"].map(nome_limpo_map)

    # First non-null per group for various fields
    for col, src in [("produtor", "produtor_extraido"), ("produtor_normalizado", "produtor_normalizado"),
                     ("safra", "safra"), ("regiao", "regiao"), ("sub_regiao", "sub_regiao"),
                     ("uvas", "uvas"), ("url_imagem", "url_imagem"),
                     ("hash_dedup", "hash_dedup"), ("ean_gtin", "ean_gtin")]:
        first_vals = grp.dropna(subset=[src]).groupby("dedup_group")[src].first()
        agg[col] = agg["dedup_group"].map(first_vals)

    # Most common tipo and moeda
    for col, src in [("tipo", "tipo"), ("moeda_referencia", "moeda")]:
        mode_vals = grp.dropna(subset=[src]).groupby("dedup_group")[src].agg(
            lambda s: s.value_counts().index[0] if len(s) > 0 else None
        )
        agg[col] = agg["dedup_group"].map(mode_vals)

    # Match type: deterministic for groups <= max_det_group, splink_high for rest
    agg["match_type"] = np.where(agg["dedup_group"] <= max_det_group, "deterministic", "splink_high")
    agg["match_probability"] = np.where(agg["dedup_group"] <= max_det_group, 1.0, 0.85)

    # Convert safra to int where possible
    agg["safra"] = agg["safra"].where(agg["safra"].notna(), None)
    agg["total_ratings_max"] = agg["total_ratings_max"].where(agg["total_ratings_max"].notna(), None)

    print(f"[X1] Merge de {len(agg):,} grupos em {time.time()-t1:.1f}s")

    # ── Build singletons ─────────────────────────────────────────────────
    print(f"[X1] Preparando {n_singletons:,} singletons...")
    t2 = time.time()

    sing = df[singleton_mask].copy()
    sing["preco_pos"] = sing["preco"].where(sing["preco"] > 0)
    sing_out = pd.DataFrame({
        "nome_limpo": sing["nome_limpo"],
        "nome_normalizado": sing["nome_normalizado"],
        "produtor": sing["produtor_extraido"],
        "produtor_normalizado": sing["produtor_normalizado"],
        "safra": sing["safra"],
        "tipo": sing["tipo"],
        "pais": sing["pais"],
        "pais_tabela": sing["pais_tabela"],
        "regiao": sing["regiao"],
        "sub_regiao": sing["sub_regiao"],
        "uvas": sing["uvas"],
        "rating_melhor": sing["rating"],
        "total_ratings_max": sing["total_ratings"],
        "preco_min_global": sing["preco_pos"],
        "preco_max_global": sing["preco_pos"],
        "moeda_referencia": sing["moeda"],
        "url_imagem": sing["url_imagem"],
        "hash_dedup": sing["hash_dedup"],
        "ean_gtin": sing["ean_gtin"],
        "match_type": "singleton",
        "match_probability": None,
        "total_copias": 1,
        "clean_ids": sing["id"].apply(lambda x: [int(x)]),
    })

    print(f"[X1] Singletons preparados em {time.time()-t2:.1f}s")

    # ── Combine and insert ────────────────────────────────────────────────
    # Select same columns from agg
    cols_out = ["nome_limpo", "nome_normalizado", "produtor", "produtor_normalizado",
                "safra", "tipo", "pais", "pais_tabela", "regiao", "sub_regiao", "uvas",
                "rating_melhor", "total_ratings_max", "preco_min_global", "preco_max_global",
                "moeda_referencia", "url_imagem", "hash_dedup", "ean_gtin",
                "match_type", "match_probability", "total_copias", "clean_ids"]

    combined = pd.concat([agg[cols_out], sing_out[cols_out]], ignore_index=True)
    total_unique = len(combined)
    print(f"[X1] Total: {total_unique:,} vinhos unicos")


    insert_sql = """
        INSERT INTO wines_unique_g1 (
            nome_limpo, nome_normalizado, produtor, produtor_normalizado,
            safra, tipo, pais, pais_tabela, regiao, sub_regiao, uvas,
            rating_melhor, total_ratings_max, preco_min_global, preco_max_global,
            moeda_referencia, url_imagem, hash_dedup, ean_gtin,
            match_type, match_probability, total_copias, clean_ids
        ) VALUES %s
    """

    print("[X1] Convertendo e inserindo...")
    t3 = time.time()

    def _sanitize(d):
        """Convert all dict values to proper Python types for psycopg2."""
        def _int(v):
            try:
                f = float(v)
                return int(f) if not (np.isnan(f) or np.isinf(f)) else None
            except Exception:
                return None

        def _flt(v):
            try:
                f = float(v)
                return f if not (np.isnan(f) or np.isinf(f)) else None
            except Exception:
                return None

        def _str(v):
            try:
                if isinstance(v, float) and np.isnan(v):
                    return None
            except Exception:
                pass
            return str(v) if v is not None and v != "" else None

        return (
            _str(d["nome_limpo"]), _str(d["nome_normalizado"]),
            _str(d["produtor"]), _str(d["produtor_normalizado"]),
            _int(d["safra"]), _str(d["tipo"]),
            _str(d["pais"]), _str(d["pais_tabela"]),
            _str(d["regiao"]), _str(d["sub_regiao"]), _str(d["uvas"]),
            _flt(d["rating_melhor"]), _int(d["total_ratings_max"]),
            _flt(d["preco_min_global"]), _flt(d["preco_max_global"]),
            _str(d["moeda_referencia"]), _str(d["url_imagem"]),
            _str(d["hash_dedup"]), _str(d["ean_gtin"]),
            _str(d["match_type"]), _flt(d["match_probability"]),
            _int(d["total_copias"]),
            [int(i) for i in d["clean_ids"]] if d["clean_ids"] is not None else [],
        )

    rows = [_sanitize(d) for d in combined.to_dict("records")]
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        try:
            execute_values(cur, insert_sql, batch)
            conn.commit()
        except Exception as e:
            conn.rollback()
            # Find the problematic row
            for j, row in enumerate(batch):
                try:
                    execute_values(cur, insert_sql, [row])
                    conn.commit()
                except Exception as e2:
                    print(f"[X1] ERRO na linha {i+j}: {e2}")
                    print(f"[X1] Dados: safra={row[4]}, total_ratings_max={row[12]}, total_copias={row[21]}")
                    print(f"[X1] Tipos: safra={type(row[4])}, total_ratings_max={type(row[12])}, total_copias={type(row[21])}")
                    print(f"[X1] clean_ids types: {[type(x) for x in row[22][:3]] if row[22] else 'empty'}")
                    conn.rollback()
                    raise
            raise
        done = min(i + BATCH_SIZE, len(rows))
        if done % 100000 == 0 or done == len(rows):
            print(f"[X1] Inseridos {done:,}/{len(rows):,}")

    print(f"[X1] wines_unique_g1: {total_unique:,} registros em {time.time()-t3:.1f}s")

    # Save quarantine
    if quarantine_pairs:
        print(f"[X1] Salvando {len(quarantine_pairs):,} pares quarentena...")
        q_sql = "INSERT INTO dedup_quarantine_g1 (clean_id_a, clean_id_b, nome_a, nome_b, match_probability, motivo) VALUES %s"
        for i in range(0, len(quarantine_pairs), BATCH_SIZE):
            batch = quarantine_pairs[i:i+BATCH_SIZE]
            execute_values(cur, q_sql, batch)
            conn.commit()
        print(f"[X1] dedup_quarantine_g1: {len(quarantine_pairs):,} pares salvos")

    elapsed = time.time() - t0
    print(f"[X1] Save total: {elapsed:.1f}s")
    return total_unique, splink_valid, n_singletons


# ── Exemplos ─────────────────────────────────────────────────────────────────

def show_examples(conn):
    cur = conn.cursor()
    print("\n" + "=" * 70)
    print("EXEMPLOS DE MERGE — NIVEL 1 (Deterministico)")
    print("=" * 70)
    cur.execute("""
        SELECT nome_limpo, produtor, safra, rating_melhor, preco_min_global, preco_max_global,
               moeda_referencia, total_copias, clean_ids
        FROM wines_unique_g1
        WHERE match_type = 'deterministic' AND total_copias > 1
        ORDER BY total_copias DESC LIMIT 10
    """)
    for row in cur.fetchall():
        nome, prod, safra, rating, pmin, pmax, moeda, copias, ids = row
        print(f"\n  ({copias} copias) {nome}")
        print(f"  Safra: {safra} | Produtor: {prod} | Rating: {rating} | Preco: {pmin}-{pmax} {moeda}")
        print(f"  IDs: {ids[:5]}{'...' if len(ids) > 5 else ''}")

    cur.execute("SELECT COUNT(*) FROM wines_unique_g1 WHERE match_type = 'splink_high' AND total_copias > 1")
    splink_count = cur.fetchone()[0]
    if splink_count > 0:
        print("\n" + "=" * 70)
        print("EXEMPLOS DE MERGE — NIVEL 2 (Splink)")
        print("=" * 70)
        cur.execute("""
            SELECT nome_limpo, produtor, safra, rating_melhor, total_copias, clean_ids
            FROM wines_unique_g1
            WHERE match_type = 'splink_high' AND total_copias > 1
            ORDER BY total_copias DESC LIMIT 10
        """)
        for row in cur.fetchall():
            nome, prod, safra, rating, copias, ids = row
            print(f"\n  ({copias} copias) {nome}")
            print(f"  Safra: {safra} | Produtor: {prod} | Rating: {rating}")
            print(f"  IDs: {ids[:5]}{'...' if len(ids) > 5 else ''}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print(f"  DEDUP GRUPO {GROUP} — Paises: {', '.join(p.upper() for p in PAISES)}")
    print("=" * 70)

    t_start = time.time()
    conn = psycopg2.connect(DB_URL)

    create_tables(conn)
    df = load_wines(conn)

    if len(df) == 0:
        print("[X1] ERRO: Nenhum vinho encontrado.")
        conn.close()
        sys.exit(1)

    total_input = len(df)

    # Nivel 1
    df, quarantine_det, n_det_groups = nivel_1_deterministico(df)

    # Nivel 2
    splink_groups, quarantine_splink = nivel_2_splink(df)

    # Combine quarantine
    all_quarantine = quarantine_det + quarantine_splink

    # Merge + save
    total_unique, splink_valid, n_singletons = merge_and_save(
        conn, df, splink_groups, all_quarantine, n_det_groups
    )

    # Examples
    show_examples(conn)

    # Verification
    print("\n[X1] === Verificacao ===")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM wines_unique_g1")
    print(f"  wines_unique_g1: {cur.fetchone()[0]:,}")
    cur.execute("SELECT match_type, COUNT(*) FROM wines_unique_g1 GROUP BY match_type")
    print(f"  Por tipo: {dict(cur.fetchall())}")
    cur.execute("SELECT total_copias, COUNT(*) FROM wines_unique_g1 GROUP BY total_copias ORDER BY total_copias DESC LIMIT 10")
    print(f"  Top copias: {cur.fetchall()}")
    cur.execute("SELECT COUNT(*) FROM dedup_quarantine_g1")
    total_quarantine = cur.fetchone()[0]
    print(f"  dedup_quarantine_g1: {total_quarantine:,}")

    conn.close()

    # Final report
    elapsed = time.time() - t_start
    taxa = (1 - total_unique / total_input) * 100 if total_input > 0 else 0

    print("\n" + "=" * 70)
    print(f"=== GRUPO {GROUP} CONCLUIDO ===")
    print(f"Paises: {', '.join(p.upper() for p in PAISES)}")
    print(f"Input: {total_input:,} vinhos de wines_clean")
    print(f"Nivel 1 (deterministico): {n_det_groups:,} grupos")
    print(f"Nivel 2 (Splink): {splink_valid:,} grupos adicionais")
    print(f"Nivel 3 (quarentena): {total_quarantine:,} pares incertos")
    print(f"Output: {total_unique:,} vinhos unicos em wines_unique_g1")
    print(f"Taxa de dedup: {taxa:.1f}% (de {total_input:,} para {total_unique:,})")
    print(f"Tempo total: {elapsed:.1f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
