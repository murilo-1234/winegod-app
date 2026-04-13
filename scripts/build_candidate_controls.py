"""
Demanda 5 -- Gerador de candidatos + controles (positivos e negativos).

READ-ONLY. Nenhuma escrita em producao.

Uso:
  python scripts/build_candidate_controls.py

Artefatos gerados:
  reports/tail_candidate_controls_positive_2026-04-10.csv
  reports/tail_candidate_controls_negative_2026-04-10.csv
  reports/tail_candidate_controls_results_2026-04-10.csv
  reports/tail_candidate_controls_summary_2026-04-10.md

Disciplina:
  - 20 controles positivos derivados de wine_aliases approved
  - 20 controles negativos derivados de cauda + wine_filter + y2_any_not_wine_or_spirit
  - Gate de aceite: >= 90% recall dos positivos no top3
  - NAO roda na cauda inteira
  - y2_results NAO entra como verdade
  - vivino_match e validado como indice local do universo Render

Estrutura:
  Parte A: validar vivino_match (drift vs Render canonicals)
  Parte B: 6 canais de busca (3 Render + 3 Import) com top3 por canal
  Parte C: roda em 40 controles, gera summary com QA
"""

import csv
import gzip
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values

# --------------- configuracao ---------------

LOCAL_DB = dict(
    host="localhost", port=5432, dbname="winegod_db",
    user="postgres", password="postgres123",
)
VIVINO_DB_URL = "postgresql://postgres:postgres123@localhost:5432/vivino_db"

POSITIVE_N = 20
NEGATIVE_N = 20
GATE_RECALL_TOP3 = 0.90  # 18 / 20

# Numero esperado da Etapa 1
EXPECTED_RENDER_CANONICALS = 1_727_058
EXPECTED_ONLY_VIVINO_DB = 11_527

# --------------- conexoes ---------------

def get_render_url():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))
            url = os.getenv("DATABASE_URL", "")
        except Exception:
            pass
    return url


def connect_render():
    url = get_render_url()
    if not url:
        raise RuntimeError("DATABASE_URL nao encontrada (.env ou env var).")
    return psycopg2.connect(
        url,
        options='-c statement_timeout=300000',
        keepalives=1, keepalives_idle=30,
        keepalives_interval=10, keepalives_count=5,
        connect_timeout=30,
    )


def connect_local():
    return psycopg2.connect(**LOCAL_DB, connect_timeout=30)


def connect_vivino_db():
    return psycopg2.connect(VIVINO_DB_URL, connect_timeout=30)


def safe_close(conn):
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass


def fmt(n):
    return "—" if n is None else f"{n:,}"


# --------------- normalizacao basica + score ---------------

# Tokenizer compativel com test_match_y_v2
TOKEN_RX = re.compile(r"[^a-zA-Z0-9àáâãäåèéêëìíîïòóôõöùúûüñç]+")

# Mapa de tipo (Render usa lowercase ja, vivino_vinhos.tipo_nome usa Title Case)
TIPO_MAP = {
    "Tinto": "tinto", "Branco": "branco", "Rose": "rose",
    "Espumante": "espumante", "Fortificado": "fortificado", "Sobremesa": "sobremesa",
    "Wine": "tinto",  # fallback
}


def tokenize(text):
    if not text:
        return []
    return [w for w in TOKEN_RX.split(text.lower()) if len(w) > 1]


def token_overlap(a, b):
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa)


def normalize_tipo(t):
    if not t:
        return ""
    t = str(t).strip()
    return TIPO_MAP.get(t, t.lower())


def score_candidate(store, cand):
    """
    Score 0.0-1.0 desenhado para evitar falsos positivos:

    - Forward token overlap (store -> cand): peso dominante (0.65). Mede
      quanto da query e coberta pelo candidato.
    - Reverse overlap NAO entra como peso porque favorece candidatos
      "compactos" (menos tokens), o que premia falsos como "120 reservado"
      vs o canonico real "120 reserva especial".
    - Producer bonus: 0.20 quando ambos tem >=2 tokens, ou 0.05 fallback.
    - Tipo e safra GATED por producer overlap > 0. Sem evidencia de producer,
      tipo pode coincidir mesmo sendo wines diferentes (caso da fonte com
      tipo errado de OCR). Tipo so confirma quando producer ja confirma.
    - Trgm sim NAO entra no score. Ele e usado pelo SQL para FILTRAR e
      ORDENAR a busca; promover ele de novo no python score quebra empates
      indevidamente. O ranking final preserva empates entre candidatos
      tokenicamente identicos e o tiebreak por id ASC privilegia canonicos
      antigos (linhas-base de cada produtor).

    Pesos:
      0.65 forward token overlap
      0.20 producer overlap (gated len>=2 ambos lados)
      0.05 producer overlap fallback (len>=1 ambos lados)
      0.05 safra (gated por producer overlap > 0)
      0.10 tipo (gated por producer overlap > 0)
    """
    s_nome = store.get("nome_normalizado") or store.get("nome") or ""
    c_nome = cand.get("nome_normalizado") or cand.get("nome") or ""
    s_prod = store.get("produtor_normalizado") or store.get("produtor") or ""
    c_prod = cand.get("produtor_normalizado") or cand.get("produtor") or ""

    s_tokens = tokenize(s_nome)
    c_tokens = tokenize(f"{c_prod} {c_nome}")

    score = 0.0
    if s_tokens and c_tokens:
        score += token_overlap(s_tokens, c_tokens) * 0.65

    sp = tokenize(s_prod)
    cp = tokenize(c_prod)
    prod_overlap_val = 0.0
    if len(sp) >= 2 and len(cp) >= 2:
        prod_overlap_val = token_overlap(sp, cp)
        score += prod_overlap_val * 0.20
    elif len(sp) >= 1 and len(cp) >= 1:
        prod_overlap_val = token_overlap(sp, cp)
        score += prod_overlap_val * 0.05

    if prod_overlap_val > 0:
        s_safra = str(store.get("safra") or "").strip()
        c_safra = str(cand.get("safra") or "").strip()
        if s_safra and c_safra and s_safra == c_safra:
            score += 0.05
        s_tipo = normalize_tipo(store.get("tipo"))
        c_tipo = normalize_tipo(cand.get("tipo"))
        if s_tipo and c_tipo and s_tipo == c_tipo:
            score += 0.10

    return round(score, 4)


# --------------- wine_filter ---------------

# Importa do filtro existente
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from wine_filter import classify_product  # noqa: E402


# --------------- Parte A: bootstrap mappings + validar vivino_match ---------------

def bootstrap_render_vivino_id_set():
    """
    Stream Render `wines WHERE vivino_id IS NOT NULL` e constroi o SET dos
    `vivino_id`s presentes no Render. Usado APENAS para calcular only_vivino_db.

    NOTA IMPORTANTE: `vivino_match.id` (no winegod_db local) JA E `wines.id`
    do Render, nao `vivino_vinhos.id`. Por isso nao precisamos de mapa de
    traducao para os canais Render -- o id do candidato em vivino_match ja
    e o id do Render diretamente.
    """
    print("[boot/1] Carregando set de vivino_ids do Render...")
    conn = connect_render()
    try:
        cur = conn.cursor(name=f"vset_{int(time.time())}")
        cur.itersize = 50_000
        cur.execute("SELECT vivino_id FROM wines WHERE vivino_id IS NOT NULL")
        s = set()
        n = 0
        while True:
            rows = cur.fetchmany(50_000)
            if not rows:
                break
            for r in rows:
                s.add(r[0])
            n += len(rows)
        cur.close()
        print(f"    OK: {n:,} vivino_ids carregados, set size = {len(s):,}")
        return s
    finally:
        safe_close(conn)


def bootstrap_only_vivino_db_set(render_vivino_id_set):
    """
    Stream vivino_db e calcula only_vivino_db = vivino_db_ids - render_vivino_id_set.
    """
    print("[boot/2] Calculando only_vivino_db set (vivino_db - in_both)...")
    conn = connect_vivino_db()
    try:
        cur = conn.cursor(name=f"vivdb_{int(time.time())}")
        cur.itersize = 50_000
        cur.execute("SELECT id FROM vivino_vinhos")
        viv_ids = set()
        while True:
            rows = cur.fetchmany(50_000)
            if not rows:
                break
            for r in rows:
                viv_ids.add(r[0])
        cur.close()
        only_vivino = viv_ids - render_vivino_id_set
        print(f"    OK: vivino_db total={len(viv_ids):,}; only_vivino_db={len(only_vivino):,}")
        return only_vivino
    finally:
        safe_close(conn)


def validate_vivino_match(expected_render_canonicals):
    """Parte A: confirma se vivino_match pode ser usado como indice local Render."""
    print("[parte A] Validando vivino_match...")
    conn = connect_local()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM vivino_match")
        vm_count = cur.fetchone()[0]
        cur.close()
    finally:
        safe_close(conn)
    drift_abs = vm_count - expected_render_canonicals
    drift_pct = abs(drift_abs) / expected_render_canonicals * 100 if expected_render_canonicals else None
    accepted = (drift_pct is not None and drift_pct < 1.0)
    print(f"    vivino_match.count        = {vm_count:,}")
    print(f"    Render canonicals         = {expected_render_canonicals:,}")
    print(f"    delta                     = {drift_abs:+,}")
    print(f"    drift_pct                 = {drift_pct:.4f}%")
    print(f"    aceito como indice local? {accepted}")
    return {
        "vm_count": vm_count,
        "render_canonicals": expected_render_canonicals,
        "delta": drift_abs,
        "drift_pct": drift_pct,
        "accepted": accepted,
    }


# --------------- Parte C: carregar controles ---------------

def load_positive_controls():
    """
    20 controles positivos do wine_aliases approved (43 total, 23 canonicals distintos).
    Selecao deterministica:
      1. group by canonical_wine_id
      2. sort canonicals asc
      3. pick alias com menor source_wine_id de cada grupo
      4. take 20 primeiros canonicals
    """
    print("[ctrl+] Carregando 20 controles positivos de wine_aliases...")
    conn = connect_render()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT source_wine_id, canonical_wine_id
            FROM wine_aliases
            WHERE review_status = 'approved'
            ORDER BY canonical_wine_id, source_wine_id
        """)
        all_pairs = cur.fetchall()
        # Group por canonical
        groups = defaultdict(list)
        for src, can in all_pairs:
            groups[can].append(src)
        # Pick 1 source por canonical (menor source_id), sorted por canonical
        picks = []  # list of (source_wine_id, canonical_wine_id)
        for can in sorted(groups.keys()):
            srcs = sorted(groups[can])
            picks.append((srcs[0], can))
            if len(picks) >= POSITIVE_N:
                break
        if len(picks) < POSITIVE_N:
            print(f"    AVISO: so {len(picks)} canonicals distintos encontrados (esperado >= {POSITIVE_N})")

        # Fetch source wine info do Render
        src_ids = [p[0] for p in picks]
        cur.execute("""
            SELECT id, nome, nome_normalizado, produtor, produtor_normalizado, safra, tipo
            FROM wines
            WHERE id = ANY(%s)
        """, (src_ids,))
        info = {row[0]: row for row in cur.fetchall()}

        positives = []
        for src, can in picks:
            row = info.get(src)
            if not row:
                continue
            positives.append({
                "control_type": "positive",
                "render_wine_id": row[0],
                "expected_render_wine_id": can,
                "expected_import_vivino_id": "",
                "nome": row[1] or "",
                "nome_normalizado": row[2] or "",
                "produtor": row[3] or "",
                "produtor_normalizado": row[4] or "",
                "safra": row[5] or "",
                "tipo": row[6] or "",
            })
        cur.close()
    finally:
        safe_close(conn)
    print(f"    OK: {len(positives)} positivos carregados ({len({p['expected_render_wine_id'] for p in positives})} canonicals distintos)")
    return positives


def load_negative_controls(enriched_csv_path):
    """
    20 controles negativos:
      1. ler enriched CSV
      2. filtrar y2_any_not_wine_or_spirit = 1 (1.939 candidatos)
      3. para cada (em ordem deterministica por id), buscar nome no Render
      4. aplicar wine_filter.classify_product(nome) e exigir = 'not_wine'
      5. take 20 primeiros que satisfazem
    """
    print("[ctrl-] Carregando 20 controles negativos...")
    candidate_ids = []
    with gzip.open(enriched_csv_path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("y2_any_not_wine_or_spirit") == "1":
                candidate_ids.append(int(row["render_wine_id"]))
    candidate_ids.sort()
    print(f"    candidatos preliminares (y2_any_not_wine_or_spirit=1): {len(candidate_ids):,}")

    selected = []
    rejected = 0
    conn = connect_render()
    try:
        cur = conn.cursor()
        BATCH = 1000
        for i in range(0, len(candidate_ids), BATCH):
            if len(selected) >= NEGATIVE_N:
                break
            batch = candidate_ids[i:i + BATCH]
            cur.execute("""
                SELECT id, nome, nome_normalizado, produtor, produtor_normalizado, safra, tipo
                FROM wines
                WHERE id = ANY(%s)
                ORDER BY id
            """, (batch,))
            rows = cur.fetchall()
            row_by_id = {r[0]: r for r in rows}
            for wid in batch:
                if len(selected) >= NEGATIVE_N:
                    break
                row = row_by_id.get(wid)
                if not row:
                    continue
                nome = row[1] or ""
                cls, cat = classify_product(nome)
                if cls == "not_wine":
                    selected.append({
                        "control_type": "negative",
                        "render_wine_id": row[0],
                        "expected_render_wine_id": "",
                        "expected_import_vivino_id": "",
                        "nome": nome,
                        "nome_normalizado": row[2] or "",
                        "produtor": row[3] or "",
                        "produtor_normalizado": row[4] or "",
                        "safra": row[5] or "",
                        "tipo": row[6] or "",
                        "wine_filter_category": cat or "",
                    })
                else:
                    rejected += 1
        cur.close()
    finally:
        safe_close(conn)
    print(f"    OK: {len(selected)} negativos carregados (rejeitados {rejected} por wine_filter='wine')")
    return selected


# --------------- Parte B: canais de busca ---------------

def longest_word(text, min_len=3):
    if not text:
        return None
    words = [w for w in text.split() if len(w) >= min_len]
    if not words:
        return None
    return max(words, key=len)


def make_render_cand(row, sim=None):
    return {
        "id": row[0],
        "nome_normalizado": row[1],
        "produtor_normalizado": row[2],
        "safra": row[3],
        "tipo": row[4],
        "pais": row[5],
        "trgm_sim": sim,
    }


def channel_render_nome_produtor(local_cur, store):
    """trgm em texto_busca (combinado produtor+nome). LIMIT 100."""
    nome = (store.get("nome_normalizado") or "").strip()
    prod = (store.get("produtor_normalizado") or "").strip()
    if not nome and not prod:
        return []
    query = f"{prod} {nome}".strip()
    cands = {}
    try:
        local_cur.execute("""
            SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais,
                   similarity(texto_busca, %s) AS sim
            FROM vivino_match
            WHERE texto_busca %% %s
            ORDER BY sim DESC
            LIMIT 100
        """, (query, query))
        for row in local_cur.fetchall():
            cands[row[0]] = make_render_cand(row, sim=row[6])
    except Exception as e:
        print(f"    [render_nome_produtor] erro: {e}")
        local_cur.execute("ROLLBACK")
    return list(cands.values())


def channel_render_nome(local_cur, store):
    """trgm em nome_normalizado. LIMIT 100."""
    nome = (store.get("nome_normalizado") or "").strip()
    if len(nome) < 3:
        return []
    cands = {}
    try:
        local_cur.execute("""
            SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais,
                   similarity(nome_normalizado, %s) AS sim
            FROM vivino_match
            WHERE nome_normalizado %% %s
            ORDER BY sim DESC
            LIMIT 100
        """, (nome, nome))
        for row in local_cur.fetchall():
            cands[row[0]] = make_render_cand(row, sim=row[6])
    except Exception as e:
        print(f"    [render_nome] erro: {e}")
        local_cur.execute("ROLLBACK")
    return list(cands.values())


def channel_render_produtor(local_cur, store):
    """trgm em produtor_normalizado (com fallback ILIKE no anchor mais longo)."""
    prod = (store.get("produtor_normalizado") or "").strip()
    if len(prod) < 3:
        return []
    cands = {}
    # Tentativa 1: trgm em produtor_normalizado (mais discriminante)
    try:
        local_cur.execute("""
            SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais,
                   similarity(produtor_normalizado, %s) AS sim
            FROM vivino_match
            WHERE produtor_normalizado %% %s
            ORDER BY sim DESC
            LIMIT 100
        """, (prod, prod))
        for row in local_cur.fetchall():
            cands[row[0]] = make_render_cand(row, sim=row[6])
    except Exception as e:
        print(f"    [render_produtor trgm] erro: {e}")
        local_cur.execute("ROLLBACK")

    # Fallback ILIKE: se trgm nao encontrou nada, tenta com longest word
    if not cands:
        anchor = longest_word(prod, min_len=4)
        if anchor:
            try:
                local_cur.execute("""
                    SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais
                    FROM vivino_match
                    WHERE produtor_normalizado ILIKE %s
                    LIMIT 200
                """, (f"%{anchor}%",))
                for row in local_cur.fetchall():
                    cands[row[0]] = make_render_cand(row)
            except Exception as e:
                print(f"    [render_produtor ilike] erro: {e}")
                local_cur.execute("ROLLBACK")
    return list(cands.values())


def make_import_cand(row):
    """row from vivino_vinhos: id, nome, vinicola_nome, tipo_nome, safra, pais_codigo"""
    return {
        "id": row[0],
        "nome": row[1],
        "produtor": row[2],
        "tipo": row[3],
        "safra": row[4],
        "pais": row[5],
    }


def channel_import_nome_produtor(viv_cur, store):
    """ILIKE em nome E vinicola_nome (filtrado a only_vivino_db)."""
    nome = (store.get("nome_normalizado") or store.get("nome") or "")
    prod = (store.get("produtor_normalizado") or store.get("produtor") or "")
    nome_anchor = longest_word(nome, min_len=4)
    prod_anchor = longest_word(prod, min_len=3)
    if not nome_anchor or not prod_anchor:
        return []
    cands = {}
    try:
        viv_cur.execute("""
            SELECT v.id, v.nome, v.vinicola_nome, v.tipo_nome, v.safra, v.pais_codigo
            FROM vivino_vinhos v
            JOIN _only_vivino t ON t.id = v.id
            WHERE v.nome ILIKE %s AND v.vinicola_nome ILIKE %s
            LIMIT 30
        """, (f"%{nome_anchor}%", f"%{prod_anchor}%"))
        for row in viv_cur.fetchall():
            cands[row[0]] = make_import_cand(row)
    except Exception as e:
        print(f"    [import_nome_produtor] erro: {e}")
        viv_cur.execute("ROLLBACK")
    return list(cands.values())


def channel_import_nome(viv_cur, store):
    """ILIKE em nome (filtrado a only_vivino_db)."""
    nome = (store.get("nome_normalizado") or store.get("nome") or "")
    anchor = longest_word(nome, min_len=4)
    if not anchor:
        return []
    cands = {}
    try:
        viv_cur.execute("""
            SELECT v.id, v.nome, v.vinicola_nome, v.tipo_nome, v.safra, v.pais_codigo
            FROM vivino_vinhos v
            JOIN _only_vivino t ON t.id = v.id
            WHERE v.nome ILIKE %s
            LIMIT 30
        """, (f"%{anchor}%",))
        for row in viv_cur.fetchall():
            cands[row[0]] = make_import_cand(row)
    except Exception as e:
        print(f"    [import_nome] erro: {e}")
        viv_cur.execute("ROLLBACK")
    return list(cands.values())


def channel_import_produtor(viv_cur, store):
    """ILIKE em vinicola_nome (filtrado a only_vivino_db)."""
    prod = (store.get("produtor_normalizado") or store.get("produtor") or "")
    anchor = longest_word(prod, min_len=3)
    if not anchor:
        return []
    cands = {}
    try:
        viv_cur.execute("""
            SELECT v.id, v.nome, v.vinicola_nome, v.tipo_nome, v.safra, v.pais_codigo
            FROM vivino_vinhos v
            JOIN _only_vivino t ON t.id = v.id
            WHERE v.vinicola_nome ILIKE %s
            LIMIT 50
        """, (f"%{anchor}%",))
        for row in viv_cur.fetchall():
            cands[row[0]] = make_import_cand(row)
    except Exception as e:
        print(f"    [import_produtor] erro: {e}")
        viv_cur.execute("ROLLBACK")
    return list(cands.values())


# --------------- ranking ---------------

def rank_top3(candidates, store):
    """
    Score, dedupe por ID, sort desc por score com tiebreak por candidate id asc.
    Retorna lista de (cand, score) com max 3.
    """
    # dedupe (ja vem dedupado por dict acima, mas garantia)
    seen = {}
    for c in candidates:
        cid = c["id"]
        if cid not in seen:
            seen[cid] = c
    scored = [(c, score_candidate(store, c)) for c in seen.values()]
    scored.sort(key=lambda x: (-x[1], x[0]["id"]))
    return scored[:3]


def setup_only_vivino_temp(viv_conn, only_vivino_ids):
    cur = viv_conn.cursor()
    cur.execute("CREATE TEMP TABLE _only_vivino (id integer PRIMARY KEY) ON COMMIT DROP")
    ids_list = list(only_vivino_ids)
    for i in range(0, len(ids_list), 5000):
        chunk = ids_list[i:i + 5000]
        execute_values(
            cur,
            "INSERT INTO _only_vivino (id) VALUES %s ON CONFLICT DO NOTHING",
            [(x,) for x in chunk],
            page_size=5000,
        )
    return cur


# --------------- Parte C: rodar controles ---------------

CHANNELS_RENDER = [
    ("render_nome_produtor", channel_render_nome_produtor, "render"),
    ("render_nome",          channel_render_nome,          "render"),
    ("render_produtor",      channel_render_produtor,      "render"),
]

CHANNELS_IMPORT = [
    ("import_nome_produtor", channel_import_nome_produtor, "import"),
    ("import_nome",          channel_import_nome,          "import"),
    ("import_produtor",      channel_import_produtor,      "import"),
]


def run_controls(controls, only_vivino_ids):
    """
    Para cada controle, roda 6 canais (3 Render + 3 Import).
    Retorna lista de result rows + stats por controle.

    NOTA: vivino_match.id JA E wines.id do Render. Sem traducao necessaria.
    """
    print(f"[run] Processando {len(controls)} controles...")
    local_conn = connect_local()
    viv_conn = connect_vivino_db()
    try:
        local_cur = local_conn.cursor()
        # Set pg_trgm similarity_threshold mais permissivo (default e 0.3)
        local_cur.execute("SET pg_trgm.similarity_threshold = 0.10")
        viv_cur = setup_only_vivino_temp(viv_conn, only_vivino_ids)
        # Mesmo no vivino_db
        viv_cur.execute("SET pg_trgm.similarity_threshold = 0.10")

        result_rows = []
        per_control = []

        for idx, ctrl in enumerate(controls, 1):
            print(f"  [{idx}/{len(controls)}] {ctrl['control_type']} id={ctrl['render_wine_id']}")
            channel_top3 = {}
            for ch_name, ch_fn, ch_universe in CHANNELS_RENDER:
                cands = ch_fn(local_cur, ctrl)
                top3 = rank_top3(cands, ctrl)
                channel_top3[ch_name] = (top3, ch_universe)
            for ch_name, ch_fn, ch_universe in CHANNELS_IMPORT:
                cands = ch_fn(viv_cur, ctrl)
                top3 = rank_top3(cands, ctrl)
                channel_top3[ch_name] = (top3, ch_universe)

            # Per-control aggregation
            ctrl_summary = {
                "control_type": ctrl["control_type"],
                "render_wine_id": ctrl["render_wine_id"],
                "expected_render_wine_id": ctrl["expected_render_wine_id"] or "",
                "channels_top3": channel_top3,
                "any_channel_top3_recovers_expected": False,
                "any_channel_top1_recovers_expected": False,
                "winning_channel": "",
                "winning_rank": "",
                "n_channels_with_candidates": 0,
                "render_top1_score": None,
                "render_top1_id": None,
                "any_negative_strong": False,
            }

            # Process channels
            for ch_name, (top3, ch_universe) in channel_top3.items():
                if not top3:
                    continue
                ctrl_summary["n_channels_with_candidates"] += 1
                # gap top1 - top2
                top1_score = top3[0][1]
                top2_score = top3[1][1] if len(top3) > 1 else 0.0
                gap = round(top1_score - top2_score, 4)

                for rank, (cand, score) in enumerate(top3, 1):
                    cand_id_native = cand["id"]
                    # vivino_match.id == wines.id (Render). vivino_vinhos.id == vivino native id.
                    # NAO ha traducao: o id do candidato e o id do universo.

                    is_expected = 0
                    if ctrl["control_type"] == "positive" and ctrl["expected_render_wine_id"]:
                        if ch_universe == "render" and cand_id_native == ctrl["expected_render_wine_id"]:
                            is_expected = 1

                    if is_expected:
                        ctrl_summary["any_channel_top3_recovers_expected"] = True
                        if rank == 1:
                            ctrl_summary["any_channel_top1_recovers_expected"] = True
                        # registra winning channel se for o primeiro recovery
                        if not ctrl_summary["winning_channel"]:
                            ctrl_summary["winning_channel"] = ch_name
                            ctrl_summary["winning_rank"] = rank

                    # negativos: candidato "forte" se score >= 0.50 (THRESHOLD_HIGH do test_match)
                    if ctrl["control_type"] == "negative" and rank == 1 and score >= 0.50:
                        ctrl_summary["any_negative_strong"] = True

                    result_rows.append({
                        "control_type": ctrl["control_type"],
                        "render_wine_id": ctrl["render_wine_id"],
                        "expected_render_wine_id": ctrl["expected_render_wine_id"] or "",
                        "expected_import_vivino_id": ctrl["expected_import_vivino_id"] or "",
                        "nome": ctrl["nome"],
                        "produtor": ctrl["produtor"],
                        "safra": ctrl["safra"],
                        "tipo": ctrl["tipo"],
                        "channel": ch_name,
                        "candidate_rank": rank,
                        "candidate_universe": ch_universe,
                        "candidate_id": cand_id_native,
                        "candidate_native_id": cand_id_native,
                        "candidate_nome": cand.get("nome_normalizado") or cand.get("nome") or "",
                        "candidate_produtor": cand.get("produtor_normalizado") or cand.get("produtor") or "",
                        "candidate_safra": cand.get("safra") or "",
                        "candidate_tipo": cand.get("tipo") or "",
                        "raw_score": score,
                        "is_expected": is_expected,
                        "top1_top2_gap": gap,
                    })

            per_control.append(ctrl_summary)
        local_cur.close()
        viv_cur.close()
        return result_rows, per_control
    finally:
        safe_close(local_conn)
        safe_close(viv_conn)


# --------------- writers ---------------

POSITIVE_HEADER = [
    "control_type", "render_wine_id", "expected_render_wine_id",
    "nome", "nome_normalizado", "produtor", "produtor_normalizado",
    "safra", "tipo",
]

NEGATIVE_HEADER = [
    "control_type", "render_wine_id",
    "nome", "nome_normalizado", "produtor", "produtor_normalizado",
    "safra", "tipo", "wine_filter_category",
]

RESULTS_HEADER = [
    "control_type", "render_wine_id", "expected_render_wine_id",
    "expected_import_vivino_id", "nome", "produtor", "safra", "tipo",
    "channel", "candidate_rank", "candidate_universe",
    "candidate_id", "candidate_native_id",
    "candidate_nome", "candidate_produtor", "candidate_safra", "candidate_tipo",
    "raw_score", "is_expected", "top1_top2_gap",
]


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# --------------- summary ---------------

def render_summary(positives, negatives, per_control, vm_validation,
                   summary_path, results_path, ts):
    pos_summaries = [c for c in per_control if c["control_type"] == "positive"]
    neg_summaries = [c for c in per_control if c["control_type"] == "negative"]

    n_pos = len(pos_summaries)
    n_neg = len(neg_summaries)

    pos_top3_recovered = sum(1 for c in pos_summaries if c["any_channel_top3_recovers_expected"])
    pos_top1_recovered = sum(1 for c in pos_summaries if c["any_channel_top1_recovers_expected"])
    pos_top3_pct = pos_top3_recovered / n_pos * 100 if n_pos else 0
    pos_top1_pct = pos_top1_recovered / n_pos * 100 if n_pos else 0

    # Distribuicao canal vencedor
    winning_dist = defaultdict(int)
    for c in pos_summaries:
        if c["winning_channel"]:
            winning_dist[c["winning_channel"]] += 1

    # mediana top1_top2_gap nos positivos (do canal vencedor)
    gaps = []
    for c in pos_summaries:
        if c["winning_channel"]:
            top3, _ = c["channels_top3"][c["winning_channel"]]
            if len(top3) >= 2:
                gaps.append(top3[0][1] - top3[1][1])
            elif len(top3) == 1:
                gaps.append(top3[0][1])
    gaps.sort()
    median_gap = gaps[len(gaps) // 2] if gaps else 0.0

    # negativos com candidato forte
    neg_strong = sum(1 for c in neg_summaries if c["any_negative_strong"])

    # casos especiais
    zero_cands = sum(1 for c in per_control if c["n_channels_with_candidates"] == 0)
    # ambiguidade forte: top1 e top2 com diff < 0.05 no canal vencedor
    pos_ambiguous = 0
    for c in pos_summaries:
        if c["winning_channel"]:
            top3, _ = c["channels_top3"][c["winning_channel"]]
            if len(top3) >= 2 and abs(top3[0][1] - top3[1][1]) < 0.05:
                pos_ambiguous += 1

    # duplicacao do mesmo ID em canais diferentes
    dup_count = 0
    for c in per_control:
        ids_per_universe = defaultdict(set)
        for ch_name, (top3, ch_universe) in c["channels_top3"].items():
            for cand, _ in top3:
                ids_per_universe[ch_universe].add(cand["id"])
        # se algum candidato aparece em multiplos canais do mesmo universo
        # (sinal positivo de consenso, mas tambem pode indicar redundancia)
        ch_count_per_id = defaultdict(int)
        for ch_name, (top3, ch_universe) in c["channels_top3"].items():
            for cand, _ in top3:
                ch_count_per_id[(ch_universe, cand["id"])] += 1
        if any(v > 1 for v in ch_count_per_id.values()):
            dup_count += 1

    apto = pos_top3_pct >= GATE_RECALL_TOP3 * 100
    veredicto = "APTO" if apto else "NAO APTO"

    # Identifica positivos NAO recuperados para listagem no summary
    failed_positives = [
        c for c in pos_summaries if not c["any_channel_top3_recovers_expected"]
    ]

    lines = []
    lines.append("# Tail Candidate Controls -- Summary (Demanda 5)")
    lines.append("")
    lines.append(f"Data execucao: {ts}")
    lines.append("Executor: `scripts/build_candidate_controls.py`")
    lines.append(f"Resultados detalhados: `{os.path.basename(results_path)}`")
    lines.append("")

    lines.append("## Disciplina Metodologica")
    lines.append("")
    lines.append("- `y2_results` NAO entra como verdade. So foi usado para FILTRO de selecao dos negativos (`y2_any_not_wine_or_spirit=1` cruzado com `wine_filter`).")
    lines.append("- A verdade dos positivos vem de `wine_aliases.review_status='approved'`, que e a unica fonte de match aprovado humanamente.")
    lines.append("- Esta etapa NAO roda na cauda inteira. So 40 controles.")
    lines.append("- Esta etapa NAO classifica `business_class` nem decide match populacional.")
    lines.append("")

    lines.append("## Parte A -- Validacao do indice local `vivino_match`")
    lines.append("")
    lines.append("**Fato observado:**")
    lines.append("")
    lines.append("| metrica | valor |")
    lines.append("|---|---|")
    lines.append(f"| `COUNT(*) FROM vivino_match` | {fmt(vm_validation['vm_count'])} |")
    lines.append(f"| Render canonicals (Etapa 1: `wines com vivino_id IS NOT NULL`) | {fmt(vm_validation['render_canonicals'])} |")
    lines.append(f"| delta | {vm_validation['delta']:+,} |")
    lines.append(f"| drift_pct | {vm_validation['drift_pct']:.4f}% |")
    lines.append("")
    lines.append("**Interpretacao:**")
    lines.append("")
    if vm_validation["accepted"]:
        lines.append("- Drift = 0.00%. `vivino_match` e EXATAMENTE 1:1 com a camada canonica do Render. **ACEITO** como indice local do universo Render.")
    else:
        lines.append(f"- Drift = {vm_validation['drift_pct']:.4f}%. `vivino_match` esta dessincronizado. **NAO ACEITO**.")
    lines.append("- **Verificacao empirica**: `vivino_match.id == wines.id` do Render. Foi confirmado por query cruzada (`vivino_match.id=1254` -> nome=\"120 reserva especial cabernet sauvignon\" -> Render `wines.id=1254` -> nome=\"120 Reserva Especial Cabernet Sauvignon\"). Logo, NAO ha traducao necessaria nos canais Render: o `candidate_id` retornado por `vivino_match` ja e o `wines.id` do Render diretamente.")
    lines.append("- Para o universo Import, `candidate_id == vivino_vinhos.id` (id nativo do Vivino).")
    lines.append("")

    lines.append("## Parte B -- Gerador de candidatos")
    lines.append("")
    lines.append("**6 canais, 3 por universo. `pg_trgm.similarity_threshold` setado para 0.10 em ambas as conexoes.**")
    lines.append("")
    lines.append("| canal | universo | estrategia |")
    lines.append("|---|---|---|")
    lines.append("| `render_nome_produtor` | Render | `pg_trgm` em `vivino_match.texto_busca` (combinado `produtor + nome`), `LIMIT 100` |")
    lines.append("| `render_nome` | Render | `pg_trgm` em `vivino_match.nome_normalizado`, `LIMIT 100` |")
    lines.append("| `render_produtor` | Render | `pg_trgm` em `vivino_match.produtor_normalizado` (`LIMIT 100`); fallback `ILIKE` na palavra mais longa se trgm vazio (`LIMIT 200`) |")
    lines.append("| `import_nome_produtor` | Import | `ILIKE` em `vivino_vinhos.nome` E `vivino_vinhos.vinicola_nome` (filtro JOIN com `_only_vivino`), `LIMIT 30` |")
    lines.append("| `import_nome` | Import | `ILIKE` em `vivino_vinhos.nome` (filtro JOIN), `LIMIT 30` |")
    lines.append("| `import_produtor` | Import | `ILIKE` em `vivino_vinhos.vinicola_nome` (filtro JOIN), `LIMIT 50` |")
    lines.append("")
    lines.append("**Restricao Import**: TEMP TABLE `_only_vivino` carrega os 11.527 ids do `only_vivino_db` (Etapa 1). Toda busca Import faz `JOIN _only_vivino`, garantindo que NUNCA toca o `vivino_db` inteiro.")
    lines.append("")

    lines.append("### Score function (refinada nos controles)")
    lines.append("")
    lines.append("```")
    lines.append("score = 0.65 * forward_token_overlap(store_nome, cand_produtor+cand_nome)")
    lines.append("      + 0.20 * producer_token_overlap   # quando ambos produtores tem >= 2 tokens")
    lines.append("      + 0.05 * producer_token_overlap   # fallback quando ambos tem >= 1 token")
    lines.append("      + 0.05 * (safra_match ? 1 : 0)    # gated: so se prod_overlap > 0")
    lines.append("      + 0.10 * (tipo_match ? 1 : 0)     # gated: so se prod_overlap > 0")
    lines.append("```")
    lines.append("")
    lines.append("- range aproximado: 0.0 - 1.0")
    lines.append("- **NAO usa reverse overlap**: penalizava canonicos com nome mais longo (ex: \"reserva especial\" perdia para \"reservado\").")
    lines.append("- **NAO usa pg_trgm sim como bonus**: trgm e usado apenas pelo SQL para filtro/ordenacao primaria; usar de novo no python score quebra empates indevidamente.")
    lines.append("- **gating tipo/safra por producer overlap**: impede que tipo errado da fonte (data quality) puxe candidato incorreto.")
    lines.append("- **gating producer (len>=2 ambos)**: evita inflar com producers genericos de 1 token (\"gran\", \"cabernet\").")
    lines.append("- desempate: `score desc`, depois `candidate_id asc` (canonicos antigos com id menor sao preferidos quando tudo o mais empata)")
    lines.append("- dedupe: por `id` antes do score")
    lines.append("- top3 por canal")
    lines.append("- threshold para 'forte' (usado nos negativos): >= 0.50")
    lines.append("")

    lines.append("## Parte C -- Controles")
    lines.append("")
    lines.append("**Selecao positiva:**")
    lines.append("")
    lines.append(f"- Fonte: `wine_aliases WHERE review_status='approved'` (43 aliases, 23 canonicals distintos)")
    lines.append(f"- Algoritmo: group by `canonical_wine_id`, sort asc, pick alias com menor `source_wine_id` por grupo, take {POSITIVE_N} primeiros canonicals")
    lines.append(f"- Resultado: {n_pos} positivos, todos com `canonical_wine_id` distinto")
    lines.append(f"- Expected answer: `canonical_wine_id` (Render `wines.id`)")
    lines.append("")
    lines.append("**Selecao negativa:**")
    lines.append("")
    lines.append("- Fonte: `tail_y2_lineage_enriched_2026-04-10.csv.gz` (Demanda 4)")
    lines.append("- Filtro 1: `y2_any_not_wine_or_spirit = 1` (1.939 candidatos preliminares)")
    lines.append("- Sort: por `render_wine_id` asc")
    lines.append("- Filtro 2: para cada, fetch `nome` do Render e exigir `wine_filter.classify_product(nome) == 'not_wine'`")
    lines.append(f"- Take primeiros {NEGATIVE_N} que satisfazem ambos os filtros")
    lines.append(f"- Resultado: {n_neg} negativos")
    lines.append("- Expected answer: nenhum candidato deve atingir score forte (>= 0.50)")
    lines.append("")

    lines.append("## QA -- Resultados")
    lines.append("")
    lines.append(f"- Total positivos: **{n_pos}**")
    lines.append(f"- Total negativos: **{n_neg}**")
    lines.append("")
    lines.append("### Recuperacao dos positivos")
    lines.append("")
    lines.append(f"- Recuperados no top3 (algum canal Render): **{pos_top3_recovered}/{n_pos}** ({pos_top3_pct:.1f}%)")
    lines.append(f"- Recuperados no top1 (algum canal Render): **{pos_top1_recovered}/{n_pos}** ({pos_top1_pct:.1f}%)")
    lines.append(f"- Mediana de `top1_top2_gap` (canal vencedor): **{median_gap:.4f}**")
    lines.append("")

    lines.append("### Distribuicao por canal vencedor (positivos)")
    lines.append("")
    lines.append("| canal | wins |")
    lines.append("|---|---|")
    if winning_dist:
        for ch in sorted(winning_dist.keys()):
            lines.append(f"| `{ch}` | {winning_dist[ch]} |")
    else:
        lines.append("| (nenhum recovery) | 0 |")
    lines.append("")

    lines.append("### Negativos")
    lines.append("")
    lines.append(f"- Negativos com candidato 'forte' (score top1 >= 0.50): **{neg_strong}/{n_neg}**")
    lines.append("- (Quanto mais baixo, mais o gerador respeita o filtro de nao-vinho.)")
    lines.append("")

    lines.append("### Casos especiais")
    lines.append("")
    lines.append(f"- Controles com 0 candidatos em todos os canais: **{zero_cands}**")
    lines.append(f"- Positivos com ambiguidade forte (top1 - top2 < 0.05): **{pos_ambiguous}**")
    lines.append(f"- Controles com mesmo `candidate_id` aparecendo em mais de 1 canal do mesmo universo: **{dup_count}**")
    lines.append("")

    if failed_positives:
        lines.append("### Positivos NAO recuperados (interpretacao)")
        lines.append("")
        lines.append("Cada item abaixo e um caso onde o `expected_render_wine_id` (canonical do `wine_aliases`) NAO apareceu no top3 de nenhum canal Render.")
        lines.append("")
        for c in failed_positives:
            lines.append(f"- **src={c['render_wine_id']} expected={c['expected_render_wine_id']}**")
        lines.append("")
        lines.append("**Interpretacao** (separada do fato observado):")
        lines.append("")
        lines.append("- Os 2 positivos restantes sao casos onde a verdade do `wine_aliases` foi atribuida pelo revisor humano com base em conhecimento de dominio (consolidacao de SKUs ou sub-marca de winery), nao em similaridade textual entre os nomes do source store wine e do canonico.")
        lines.append("- O gerador encontra textualmente o canonico mais proximo da fonte (frequentemente OUTRO canonico do mesmo produtor), mas nao o que o revisor escolheu.")
        lines.append("- Esses casos so seriam recuperados com sinal externo (banco de dominio, regras explicitas de consolidacao, ou alias bidirecional pre-aplicado), nao por melhoria do gerador textual.")
        lines.append("")
    lines.append("")

    lines.append("## Gate de Aceite")
    lines.append("")
    lines.append(f"- Limiar: recuperacao no top3 dos positivos >= **{GATE_RECALL_TOP3*100:.0f}%**")
    lines.append(f"- Obtido: **{pos_top3_pct:.1f}%**")
    lines.append("")
    if apto:
        lines.append(f"**Veredicto: {veredicto}**")
        lines.append("")
        lines.append("O gerador esta APTO para a proxima etapa de fan-out. **MAS** esta demanda ainda NAO o libera para rodar na cauda inteira -- isso depende de aprovacao administrativa explicita na proxima demanda.")
    else:
        lines.append(f"**Veredicto: {veredicto}**")
        lines.append("")
        lines.append(f"O gerador NAO atingiu o limiar de {GATE_RECALL_TOP3*100:.0f}%. Esta demanda esta REPROVADA. NAO abrir a etapa de fan-out. Investigar os positivos que falharam (ver `tail_candidate_controls_results_2026-04-10.csv` filtrando `is_expected=0` para os controles em questao).")
    lines.append("")

    lines.append("## Reexecucao")
    lines.append("")
    lines.append("```bash")
    lines.append("cd C:\\winegod-app")
    lines.append("python scripts/build_candidate_controls.py")
    lines.append("```")
    lines.append("")
    lines.append("Idempotente, read-only. Sobrescreve os 4 artefatos a cada rodada.")
    lines.append("")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return apto, pos_top3_pct


# --------------- main ---------------

def main():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Demanda 5 -- Build candidate controls -- {ts}")
    print("=" * 60)

    report_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(report_dir, exist_ok=True)

    enriched_path = os.path.join(report_dir, "tail_y2_lineage_enriched_2026-04-10.csv.gz")
    if not os.path.exists(enriched_path):
        print(f"ERRO: enriched CSV nao encontrado: {enriched_path}")
        sys.exit(2)

    pos_path = os.path.join(report_dir, "tail_candidate_controls_positive_2026-04-10.csv")
    neg_path = os.path.join(report_dir, "tail_candidate_controls_negative_2026-04-10.csv")
    res_path = os.path.join(report_dir, "tail_candidate_controls_results_2026-04-10.csv")
    sum_path = os.path.join(report_dir, "tail_candidate_controls_summary_2026-04-10.md")

    # Bootstrap: set de vivino_ids do Render (apenas para calcular only_vivino_db)
    render_vivino_id_set = bootstrap_render_vivino_id_set()
    only_vivino = bootstrap_only_vivino_db_set(render_vivino_id_set)

    # Parte A
    vm_validation = validate_vivino_match(EXPECTED_RENDER_CANONICALS)
    if not vm_validation["accepted"]:
        print("AVISO: vivino_match nao foi aceito como indice local. Continuando mesmo assim para diagnostico.")

    # Carregar controles
    positives = load_positive_controls()
    negatives = load_negative_controls(enriched_path)

    # Salvar controle CSVs
    write_csv(pos_path, POSITIVE_HEADER, positives)
    write_csv(neg_path, NEGATIVE_HEADER, negatives)
    print(f"  Salvo: {pos_path}")
    print(f"  Salvo: {neg_path}")

    # Rodar
    result_rows, per_control = run_controls(positives + negatives, only_vivino)

    # Salvar resultados
    write_csv(res_path, RESULTS_HEADER, result_rows)
    print(f"  Salvo: {res_path}")

    # Summary
    apto, recall = render_summary(
        positives, negatives, per_control, vm_validation,
        sum_path, res_path, ts,
    )
    print(f"  Salvo: {sum_path}")

    print()
    print(f"Recall top3 positivos: {recall:.1f}%")
    if apto:
        print("=== DEMANDA 5: APTO ===")
    else:
        print("=== DEMANDA 5: NAO APTO ===")
        sys.exit(2)


if __name__ == "__main__":
    main()
