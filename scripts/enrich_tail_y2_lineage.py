"""
Demanda 4 -- Enriquecimento da cauda com baseline y2_results e linhagem local.

READ-ONLY. Nenhuma escrita em producao. Bancos LOCAL e Render apenas leitura.

Uso:
  python scripts/enrich_tail_y2_lineage.py

Artefatos gerados:
  reports/tail_y2_lineage_enriched_2026-04-10.csv.gz
  reports/tail_y2_lineage_summary_2026-04-10.md

Estrategia (sem loop por item, sem N+1):
  1. Stream cauda do Render: (id, hash_dedup) para wines com vivino_id IS NULL.
  2. Resolve hash_dedup -> wines_clean via TEMP TABLE local com JOIN.
     Resultado: hash -> [(clean_id, pais_tabela, id_original), ...]
  3. Agrega y2_results filtrado por clean_id via TEMP TABLE local com JOIN.
     Resultado: clean_id -> stats agregados.
  4. Para cada (pais_tabela, id_original) na cauda, agrega vinhos_XX_fontes:
     enumera as 50 tabelas via information_schema, carrega em batches de
     ANY(%s) por id_original. Resultado: (pais, id_orig) -> stats.
  5. Itera cauda em memoria, monta 1 linha por render_wine_id no CSV.
  6. Gera summary com QA, buckets de cardinalidade e proveniencia.

Disciplina:
  - y2_results entra como BASELINE HISTORICO, NAO como verdade.
  - y2_results.vivino_id = wines.id do Render (NAO o vivino_id real).
  - Sem candidato Render. Sem candidato vivino_db. Sem business_class.
  - Sem decisao de match.
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
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 2
ANY_BATCH = 5_000

# Numeros oficiais da Etapa 1 (para QA cruzado)
ETAPA1 = {
    "wines_sem_vivino_id": 779_383,
}

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


def safe_close(conn):
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass


def fmt(n):
    if n is None:
        return "ERRO"
    return f"{n:,}"


# --------------- ETAPA 1: stream cauda do Render ---------------

def stream_render_cauda():
    """
    Stream (wine_id, hash_dedup) para todos os wines com vivino_id IS NULL.
    Retorna lista preservando ordem por wine_id e set de hashes nao-nulos.
    """
    print("[1/5] Streaming cauda do Render (id, hash_dedup)...")
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        conn = None
        try:
            conn = connect_render()
            cur_name = f'cauda_{attempt}_{int(time.time())}'
            cur = conn.cursor(name=cur_name)
            cur.itersize = 25_000
            cur.execute("""
                SELECT id, hash_dedup
                FROM wines
                WHERE vivino_id IS NULL
                ORDER BY id
            """)
            cauda = []
            cauda_hashes = set()
            n = 0
            while True:
                rows = cur.fetchmany(25_000)
                if not rows:
                    break
                for wid, hd in rows:
                    cauda.append((wid, hd))
                    if hd:
                        cauda_hashes.add(hd)
                n += len(rows)
                if n % 100_000 == 0:
                    print(f"      ... {n:,} wines lidos")
            cur.close()
            conn.close()
            print(f"    OK: {len(cauda):,} wines, {len(cauda_hashes):,} hashes nao-nulos distintos")
            return cauda, cauda_hashes
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_error = e
            print(f"    tentativa {attempt}/{MAX_RETRIES} falhou: {type(e).__name__}: {e}")
            safe_close(conn)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SEC * attempt)
        except Exception as e:
            safe_close(conn)
            raise
    raise RuntimeError(f"stream_render_cauda falhou: {last_error}")


# --------------- ETAPA 2: hash_dedup -> wines_clean ---------------

def resolve_hashes_to_cleans(cauda_hashes):
    """
    Cria TEMP TABLE local com os hashes da cauda, faz JOIN com wines_clean,
    retorna hash -> [(clean_id, pais_tabela, id_original), ...].
    """
    print(f"[2/5] Resolvendo {len(cauda_hashes):,} hashes em wines_clean (TEMP TABLE)...")
    conn = connect_local()
    try:
        cur = conn.cursor()
        cur.execute("CREATE TEMP TABLE _cauda_hashes (h text PRIMARY KEY) ON COMMIT DROP")
        # bulk insert em chunks
        hash_list = list(cauda_hashes)
        for i in range(0, len(hash_list), 50_000):
            chunk = hash_list[i:i + 50_000]
            execute_values(
                cur,
                "INSERT INTO _cauda_hashes (h) VALUES %s ON CONFLICT DO NOTHING",
                [(h,) for h in chunk],
                page_size=10_000,
            )
        # NAO commit (TEMP TABLE com ON COMMIT DROP some). Mantem na sessao.

        # JOIN
        cur.execute("""
            SELECT wc.id, wc.hash_dedup, wc.pais_tabela, wc.id_original
            FROM wines_clean wc
            JOIN _cauda_hashes t ON t.h = wc.hash_dedup
        """)
        hash_to_cleans = defaultdict(list)
        all_clean_ids = set()
        all_orig_keys = set()  # set of (pais_tabela, id_original)
        rows_n = 0
        for clean_id, hd, pais, id_orig in cur:
            hash_to_cleans[hd].append((clean_id, pais, id_orig))
            all_clean_ids.add(clean_id)
            if pais and id_orig is not None:
                all_orig_keys.add((pais, id_orig))
            rows_n += 1
        cur.close()
        print(f"    OK: {rows_n:,} linhas wines_clean (cobre {len(hash_to_cleans):,} hashes; {len(all_clean_ids):,} clean_ids unicos; {len(all_orig_keys):,} orig keys unicas)")
        return dict(hash_to_cleans), all_clean_ids, all_orig_keys
    finally:
        safe_close(conn)


# --------------- ETAPA 3: y2_results agregado ---------------

def aggregate_y2_results(all_clean_ids):
    """
    TEMP TABLE com clean_ids relevantes, JOIN com y2_results.
    Retorna dict: clean_id -> dict de stats (status, match_score, ...).
    """
    print(f"[3/5] Agregando y2_results para {len(all_clean_ids):,} clean_ids (TEMP TABLE)...")
    conn = connect_local()
    try:
        cur = conn.cursor()
        cur.execute("CREATE TEMP TABLE _cauda_cleans (cid integer PRIMARY KEY) ON COMMIT DROP")
        clean_list = list(all_clean_ids)
        for i in range(0, len(clean_list), 50_000):
            chunk = clean_list[i:i + 50_000]
            execute_values(
                cur,
                "INSERT INTO _cauda_cleans (cid) VALUES %s ON CONFLICT DO NOTHING",
                [(c,) for c in chunk],
                page_size=10_000,
            )

        cur.execute("""
            SELECT y.clean_id, y.status, y.vivino_id, y.match_score,
                   y.prod_banco, y.vinho_banco, y.safra,
                   y.vivino_produtor, y.vivino_nome, y.fonte_llm
            FROM y2_results y
            JOIN _cauda_cleans t ON t.cid = y.clean_id
        """)
        clean_to_y2 = {}
        rows_n = 0
        for row in cur:
            (clean_id, status, vivino_id, match_score,
             prod_banco, vinho_banco, safra,
             vivino_produtor, vivino_nome, fonte_llm) = row
            # y2_results.clean_id e UNICO (verificado), entao 1 row max por clean_id
            clean_to_y2[clean_id] = {
                "status": status,
                "vivino_id": vivino_id,
                "match_score": match_score,
                "prod_banco": prod_banco,
                "vinho_banco": vinho_banco,
                "safra": safra,
                "vivino_produtor": vivino_produtor,
                "vivino_nome": vivino_nome,
                "fonte_llm": fonte_llm,
            }
            rows_n += 1
        cur.close()
        print(f"    OK: {rows_n:,} y2_results carregados (cobertura: {rows_n}/{len(all_clean_ids)} = {rows_n/len(all_clean_ids)*100:.2f}% dos clean_ids)")
        return clean_to_y2
    finally:
        safe_close(conn)


# --------------- ETAPA 4: vinhos_XX_fontes agregado ---------------

PAIS_RX = re.compile(r"^vinhos_([a-z]{2})_fontes$")


def discover_fontes_tables():
    """Lista as tabelas vinhos_XX_fontes via information_schema."""
    conn = connect_local()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_name LIKE 'vinhos_%_fontes'
            ORDER BY table_name
        """)
        tables = [r[0] for r in cur.fetchall()]
        cur.close()
        return tables
    finally:
        safe_close(conn)


def aggregate_local_fontes(all_orig_keys):
    """
    Para cada (pais, id_orig), agrega:
      total_rows, urls_count (url_original NOT NULL), price_rows (preco NOT NULL).
    Enumera as 50 tabelas via information_schema. Filtra por vinho_id em batches.
    Retorna dict: (pais, id_orig) -> {rows, urls, prices, table}.
    """
    print(f"[4/5] Agregando vinhos_XX_fontes para {len(all_orig_keys):,} orig keys...")
    pais_to_origs = defaultdict(set)
    for pais, id_orig in all_orig_keys:
        pais_to_origs[pais].add(id_orig)

    fontes_tables = discover_fontes_tables()
    fontes_tables_paises = {}
    for tbl in fontes_tables:
        m = PAIS_RX.match(tbl)
        if m:
            fontes_tables_paises[m.group(1)] = tbl

    orig_to_fontes = {}
    paises_used = set()
    paises_no_table = set()
    total_rows_loaded = 0

    conn = connect_local()
    try:
        cur = conn.cursor()
        for pais, ids in sorted(pais_to_origs.items()):
            if pais not in fontes_tables_paises:
                paises_no_table.add(pais)
                continue
            tbl = fontes_tables_paises[pais]
            paises_used.add(pais)
            ids_list = list(ids)
            print(f"      pais={pais} tbl={tbl} ids={len(ids_list):,}")
            for i in range(0, len(ids_list), ANY_BATCH):
                chunk = ids_list[i:i + ANY_BATCH]
                # NOTA: nome da tabela e validado por regex (pais e [a-z]{2}); seguro
                cur.execute(
                    f"SELECT vinho_id, url_original, preco FROM {tbl} WHERE vinho_id = ANY(%s)",
                    (chunk,),
                )
                for vinho_id, url, preco in cur:
                    key = (pais, vinho_id)
                    rec = orig_to_fontes.get(key)
                    if rec is None:
                        rec = {"rows": 0, "urls": 0, "prices": 0, "table": tbl}
                        orig_to_fontes[key] = rec
                    rec["rows"] += 1
                    if url:
                        rec["urls"] += 1
                    if preco is not None:
                        rec["prices"] += 1
                    total_rows_loaded += 1
        cur.close()
    finally:
        safe_close(conn)

    print(f"    OK: {total_rows_loaded:,} linhas de fontes carregadas; {len(orig_to_fontes):,} (pais, id_orig) com fontes")
    if paises_no_table:
        print(f"    paises sem tabela vinhos_XX_fontes: {sorted(paises_no_table)}")
    return orig_to_fontes, sorted(paises_used), sorted(paises_no_table)


# --------------- ETAPA 5: monta CSV enriquecido ---------------

CSV_HEADER = [
    "render_wine_id",
    "hash_dedup",
    "clean_ids_count",
    "clean_ids_sample",
    "y2_present",
    "y2_rows_count",
    "y2_status_set",
    "y2_any_matched",
    "y2_any_new",
    "y2_any_not_wine_or_spirit",
    "y2_match_score_max",
    "y2_match_score_min",
    "y2_matched_rows_count",
    "y2_new_rows_count",
    "local_lineage_resolved",
    "local_fontes_rows_count",
    "local_fontes_tables_count",
    "local_urls_count",
    "local_price_rows_count",
]

NOT_WINE_OR_SPIRIT = {"not_wine", "spirit"}


def build_enriched_row(wid, hd, hash_to_cleans, clean_to_y2, orig_to_fontes):
    """Monta a linha enriquecida para um render_wine_id."""
    cleans = hash_to_cleans.get(hd, []) if hd else []
    clean_ids = [c[0] for c in cleans]
    clean_ids_count = len(clean_ids)
    clean_ids_sample = ",".join(str(c) for c in sorted(clean_ids)[:5])

    # y2 stats
    y2_rows = []
    for cid in clean_ids:
        rec = clean_to_y2.get(cid)
        if rec is not None:
            y2_rows.append(rec)
    y2_rows_count = len(y2_rows)
    y2_present = 1 if y2_rows_count > 0 else 0

    statuses = sorted({r["status"] for r in y2_rows if r["status"]})
    y2_status_set = "|".join(statuses)
    y2_any_matched = 1 if any(r["status"] == "matched" for r in y2_rows) else 0
    y2_any_new = 1 if any(r["status"] == "new" for r in y2_rows) else 0
    y2_any_not_wine_or_spirit = 1 if any(r["status"] in NOT_WINE_OR_SPIRIT for r in y2_rows) else 0
    y2_matched_rows_count = sum(1 for r in y2_rows if r["status"] == "matched")
    y2_new_rows_count = sum(1 for r in y2_rows if r["status"] == "new")

    scores = [r["match_score"] for r in y2_rows if r["match_score"] is not None]
    y2_match_score_max = max(scores) if scores else ""
    y2_match_score_min = min(scores) if scores else ""

    # linhagem local: agregada de todas as (pais, id_orig) deste wine
    fontes_rows = 0
    fontes_urls = 0
    fontes_prices = 0
    fontes_tables = set()
    for (cid, pais, id_orig) in cleans:
        if not (pais and id_orig is not None):
            continue
        rec = orig_to_fontes.get((pais, id_orig))
        if rec is None:
            continue
        fontes_rows += rec["rows"]
        fontes_urls += rec["urls"]
        fontes_prices += rec["prices"]
        fontes_tables.add(rec["table"])

    local_lineage_resolved = 1 if (clean_ids_count > 0 and fontes_rows > 0) else 0

    return [
        wid,
        hd if hd else "",
        clean_ids_count,
        clean_ids_sample,
        y2_present,
        y2_rows_count,
        y2_status_set,
        y2_any_matched,
        y2_any_new,
        y2_any_not_wine_or_spirit,
        y2_match_score_max,
        y2_match_score_min,
        y2_matched_rows_count,
        y2_new_rows_count,
        local_lineage_resolved,
        fontes_rows,
        len(fontes_tables),
        fontes_urls,
        fontes_prices,
    ]


def write_enriched_csv(cauda, hash_to_cleans, clean_to_y2, orig_to_fontes, csv_path):
    print("[5/5] Escrevendo CSV enriquecido...")
    stats = {
        "rows_written": 0,
        "ids_seen": set(),
        "no_hash_dedup": 0,
        "clean_buckets": {"0": 0, "1": 0, ">1": 0},
        "y2_buckets":    {"0": 0, "1": 0, ">1": 0},
        "y2_present_count": 0,
        "y2_status_set_dist": defaultdict(int),
        "y2_any_matched_count": 0,
        "y2_any_new_count": 0,
        "y2_any_not_wine_or_spirit_count": 0,
        "wines_with_clean": 0,
        "wines_without_clean": 0,
        "lineage_resolved_count": 0,
        "lineage_fontes_zero_count": 0,
    }

    with gzip.open(csv_path, 'wt', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for wid, hd in cauda:
            row = build_enriched_row(wid, hd, hash_to_cleans, clean_to_y2, orig_to_fontes)
            writer.writerow(row)

            stats["rows_written"] += 1
            stats["ids_seen"].add(wid)
            if not hd:
                stats["no_hash_dedup"] += 1

            clean_count = row[2]
            bucket = "0" if clean_count == 0 else ("1" if clean_count == 1 else ">1")
            stats["clean_buckets"][bucket] += 1
            if clean_count > 0:
                stats["wines_with_clean"] += 1
            else:
                stats["wines_without_clean"] += 1

            y2_count = row[5]
            bucket_y2 = "0" if y2_count == 0 else ("1" if y2_count == 1 else ">1")
            stats["y2_buckets"][bucket_y2] += 1

            if row[4] == 1:  # y2_present
                stats["y2_present_count"] += 1
                stats["y2_status_set_dist"][row[6]] += 1
            if row[7] == 1:
                stats["y2_any_matched_count"] += 1
            if row[8] == 1:
                stats["y2_any_new_count"] += 1
            if row[9] == 1:
                stats["y2_any_not_wine_or_spirit_count"] += 1

            if row[14] == 1:  # local_lineage_resolved
                stats["lineage_resolved_count"] += 1
            if row[15] == 0:  # local_fontes_rows_count
                stats["lineage_fontes_zero_count"] += 1

            if stats["rows_written"] % 100_000 == 0:
                print(f"      ... {stats['rows_written']:,} linhas escritas")
    print(f"    OK: {stats['rows_written']:,} linhas")
    return stats


# --------------- summary ---------------

def render_summary(stats, paises_used, paises_no_table, csv_path, summary_path, ts):
    rows_written = stats["rows_written"]
    ids_seen_count = len(stats["ids_seen"])

    check_total = (rows_written == ETAPA1["wines_sem_vivino_id"])
    check_unique = (ids_seen_count == rows_written)
    all_ok = check_total and check_unique

    lines = []
    lines.append("# Tail Y2 + Lineage Enriched -- Summary (Demanda 4)")
    lines.append("")
    lines.append(f"Data execucao: {ts}")
    lines.append("Executor: `scripts/enrich_tail_y2_lineage.py`")
    lines.append(f"Artefato CSV: `{os.path.basename(csv_path)}` (gzip)")
    lines.append("")

    lines.append("## Disciplina Metodologica")
    lines.append("")
    lines.append("- `y2_results` entra como **BASELINE HISTORICO**, NAO como verdade.")
    lines.append("- `y2_results.vivino_id` = `wines.id` do Render, **NAO** o `vivino_id` real do Vivino.")
    lines.append("- Esta etapa NAO gera candidatos, NAO classifica negocio, NAO faz match.")
    lines.append("")

    lines.append("## Proveniencia")
    lines.append("")
    lines.append("- Banco Render: read-only, fonte de `wines (id, hash_dedup) WHERE vivino_id IS NULL`.")
    lines.append("- Banco LOCAL `winegod_db`: read-only, fonte de `wines_clean`, `y2_results`, `vinhos_XX_fontes`.")
    lines.append("- Joins via TEMP TABLE local (sem N+1, sem ANY com 779k itens via parametros).")
    lines.append("- 50 tabelas `vinhos_XX_fontes` enumeradas via `information_schema.tables` (regex `^vinhos_([a-z]{2})_fontes$`).")
    lines.append("- Filtragem de fontes por `vinho_id = ANY(%s)` em batches de 5.000 ids.")
    lines.append("")

    lines.append("## Conteudo do Extract")
    lines.append("")
    lines.append(f"- Total de linhas: **{fmt(rows_written)}**")
    lines.append(f"- render_wine_id distintos: **{fmt(ids_seen_count)}**")
    lines.append(f"- wines com hash_dedup nulo/vazio: **{fmt(stats['no_hash_dedup'])}**")
    lines.append("")

    lines.append("## Colunas do CSV")
    lines.append("")
    lines.append("| coluna | origem | definicao |")
    lines.append("|---|---|---|")
    lines.append("| `render_wine_id` | `wines.id` | chave primaria do vinho na cauda |")
    lines.append("| `hash_dedup` | `wines.hash_dedup` | hash MD5 do vinho no Render |")
    lines.append("| `clean_ids_count` | derivado | numero de `wines_clean.id` que casam pelo `hash_dedup` |")
    lines.append("| `clean_ids_sample` | derivado | ate 5 menores `clean_id` separados por virgula |")
    lines.append("| `y2_present` | derivado | 1 se algum `clean_id` resolveu em `y2_results`, senao 0 |")
    lines.append("| `y2_rows_count` | derivado | numero de linhas `y2_results` (1 por clean_id, ja que `clean_id` e unico em y2) |")
    lines.append("| `y2_status_set` | derivado | set de statuses unicos, ordenado, separado por `\\|` |")
    lines.append("| `y2_any_matched` | derivado | 1 se algum row tem `status='matched'` |")
    lines.append("| `y2_any_new` | derivado | 1 se algum row tem `status='new'` |")
    lines.append("| `y2_any_not_wine_or_spirit` | derivado | 1 se algum row tem `status IN ('not_wine','spirit')` |")
    lines.append("| `y2_match_score_max` | derivado | max(`match_score`) entre os rows; vazio se nenhum |")
    lines.append("| `y2_match_score_min` | derivado | min(`match_score`) entre os rows; vazio se nenhum |")
    lines.append("| `y2_matched_rows_count` | derivado | numero de rows com `status='matched'` |")
    lines.append("| `y2_new_rows_count` | derivado | numero de rows com `status='new'` |")
    lines.append("| `local_lineage_resolved` | derivado | 1 se `clean_ids_count>0` E `local_fontes_rows_count>0` |")
    lines.append("| `local_fontes_rows_count` | derivado | total de linhas em `vinhos_XX_fontes` para todas as `(pais, id_orig)` deste wine |")
    lines.append("| `local_fontes_tables_count` | derivado | numero de tabelas `vinhos_XX_fontes` distintas envolvidas |")
    lines.append("| `local_urls_count` | derivado | total de `url_original` nao-nulas em `vinhos_XX_fontes` |")
    lines.append("| `local_price_rows_count` | derivado | total de linhas com `preco` nao-nulo em `vinhos_XX_fontes` |")
    lines.append("")

    lines.append("## QA -- Cruzamento com Etapa 1")
    lines.append("")
    lines.append("| check | esperado | obtido | resultado |")
    lines.append("|---|---|---|---|")
    lines.append(f"| total de linhas do extract | {fmt(ETAPA1['wines_sem_vivino_id'])} | {fmt(rows_written)} | {'OK' if check_total else 'FALHOU'} |")
    lines.append(f"| render_wine_id unicos = total | {fmt(rows_written)} | {fmt(ids_seen_count)} | {'OK' if check_unique else 'FALHOU'} |")
    lines.append("")

    lines.append("## Cobertura -- hash_dedup -> wines_clean")
    lines.append("")
    lines.append(f"- wines com pelo menos 1 `clean_id` resolvido: **{fmt(stats['wines_with_clean'])}**")
    lines.append(f"- wines sem nenhum `clean_id` (perda de join): **{fmt(stats['wines_without_clean'])}**")
    if rows_written > 0:
        lines.append(f"- cobertura de wines_clean: **{stats['wines_with_clean'] / rows_written * 100:.2f}%**")
    lines.append("")

    lines.append("### Bucket de cardinalidade `clean_ids_count`")
    lines.append("")
    lines.append("| bucket | wines |")
    lines.append("|---|---|")
    lines.append(f"| 0 clean_ids | {fmt(stats['clean_buckets']['0'])} |")
    lines.append(f"| 1 clean_id | {fmt(stats['clean_buckets']['1'])} |")
    lines.append(f"| >1 clean_ids | {fmt(stats['clean_buckets']['>1'])} |")
    lines.append("")

    lines.append("## Cobertura -- y2_results (BASELINE, nao verdade)")
    lines.append("")
    lines.append(f"- wines com `y2_present=1`: **{fmt(stats['y2_present_count'])}**")
    if rows_written > 0:
        lines.append(f"- cobertura y2: **{stats['y2_present_count'] / rows_written * 100:.2f}%**")
    lines.append(f"- wines com `y2_any_matched=1`: **{fmt(stats['y2_any_matched_count'])}**")
    lines.append(f"- wines com `y2_any_new=1`: **{fmt(stats['y2_any_new_count'])}**")
    lines.append(f"- wines com `y2_any_not_wine_or_spirit=1`: **{fmt(stats['y2_any_not_wine_or_spirit_count'])}**")
    lines.append("")

    lines.append("### Bucket de cardinalidade `y2_rows_count`")
    lines.append("")
    lines.append("| bucket | wines |")
    lines.append("|---|---|")
    lines.append(f"| 0 y2_rows | {fmt(stats['y2_buckets']['0'])} |")
    lines.append(f"| 1 y2_row | {fmt(stats['y2_buckets']['1'])} |")
    lines.append(f"| >1 y2_rows | {fmt(stats['y2_buckets']['>1'])} |")
    lines.append("")

    lines.append("### Distribuicao de `y2_status_set` (top 20)")
    lines.append("")
    lines.append("| y2_status_set | wines |")
    lines.append("|---|---|")
    dist = sorted(stats["y2_status_set_dist"].items(), key=lambda x: -x[1])[:20]
    for status_set, n in dist:
        lines.append(f"| `{status_set}` | {fmt(n)} |")
    lines.append("")

    lines.append("## Cobertura -- linhagem local (vinhos_XX_fontes)")
    lines.append("")
    lines.append(f"- wines com `local_lineage_resolved=1`: **{fmt(stats['lineage_resolved_count'])}**")
    if rows_written > 0:
        lines.append(f"- cobertura linhagem: **{stats['lineage_resolved_count'] / rows_written * 100:.2f}%**")
    lines.append(f"- wines com `local_fontes_rows_count=0`: **{fmt(stats['lineage_fontes_zero_count'])}**")
    lines.append("")
    lines.append(f"- paises com tabela `vinhos_XX_fontes` usada: **{len(paises_used)}** -- {paises_used}")
    if paises_no_table:
        lines.append(f"- paises sem tabela `vinhos_XX_fontes`: **{len(paises_no_table)}** -- {paises_no_table}")
    lines.append("")

    lines.append("## Veredito")
    lines.append("")
    if all_ok:
        lines.append("**EXTRACT VALIDO.** A base enriquecida da cauda esta pronta para a proxima demanda.")
    else:
        lines.append("**EXTRACT COM FALHAS DE QA.** Investigar antes de prosseguir.")
    lines.append("")

    lines.append("## Reexecucao")
    lines.append("")
    lines.append("```bash")
    lines.append("cd C:\\winegod-app")
    lines.append("python scripts/enrich_tail_y2_lineage.py")
    lines.append("```")
    lines.append("")
    lines.append("Idempotente. Cada rodada sobrescreve os artefatos. Sem efeito colateral em producao.")
    lines.append("")

    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")

    return all_ok


# --------------- main ---------------

def main():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Demanda 4 -- Enrich cauda com y2_results + linhagem -- {ts}")
    print("=" * 60)

    report_dir = os.path.join(os.path.dirname(__file__), '..', 'reports')
    os.makedirs(report_dir, exist_ok=True)
    csv_path = os.path.join(report_dir, 'tail_y2_lineage_enriched_2026-04-10.csv.gz')
    summary_path = os.path.join(report_dir, 'tail_y2_lineage_summary_2026-04-10.md')

    cauda, cauda_hashes = stream_render_cauda()
    hash_to_cleans, all_clean_ids, all_orig_keys = resolve_hashes_to_cleans(cauda_hashes)
    clean_to_y2 = aggregate_y2_results(all_clean_ids)
    orig_to_fontes, paises_used, paises_no_table = aggregate_local_fontes(all_orig_keys)
    stats = write_enriched_csv(cauda, hash_to_cleans, clean_to_y2, orig_to_fontes, csv_path)

    print("Gerando summary...")
    all_ok = render_summary(stats, paises_used, paises_no_table, csv_path, summary_path, ts)
    print(f"  OK: {summary_path}")

    print()
    print(f"CSV:     {csv_path}")
    print(f"Summary: {summary_path}")
    print()
    if all_ok:
        print("=== DEMANDA 4 COMPLETA -- QA OK ===")
    else:
        print("=== DEMANDA 4 COMPLETA -- QA COM FALHAS ===")
        sys.exit(2)


if __name__ == "__main__":
    main()
