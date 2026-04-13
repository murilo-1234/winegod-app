"""
Demanda 6C -- Medicao de cacheabilidade por canal em TODA a cauda (779.383 wines).

READ-ONLY. Nenhuma escrita em producao.

Para cada um dos 6 canais da Demanda 5, computa a chave de cache usada pela
query SQL e mede:
  - total de wines
  - chaves distintas
  - taxa de repeticao
  - distribuicao de frequencia (1x / 2x / 3-5x / 6-10x / >10x)
  - cobertura acumulada das top-K chaves (100 / 1.000 / 10.000)

Normalizacao das chaves e IDENTICA ao que as funcoes channel_* da Demanda 5 usam:

  render_nome_produtor -> f"{prod} {nome}".strip()    (passado ao similarity() no SQL)
  render_nome          -> nome.strip()                (passado ao similarity())
  render_produtor      -> prod.strip()                (passado ao similarity())
  import_nome_produtor -> (longest_word(nome,4), longest_word(prod,3))
  import_nome          -> longest_word(nome,4)
  import_produtor      -> longest_word(prod,3)

Wines cuja chave e vazia / nao cumpre requisito minimo da D5 (len<3, longest_word is None)
sao contados a parte como "skipped" e NAO contam nas chaves distintas (porque a D5 nao
faria query pra eles).

Uso:
  python scripts/measure_candidate_key_cardinality.py

Artefatos:
  reports/tail_candidate_cacheability_channels_2026-04-10.csv   (long format por canal+metrica)
  reports/tail_candidate_cacheability_keys_dump.sqlite3          (opcional, dump das chaves -- criado quando --dump)
"""

import argparse
import csv
import gzip
import os
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_candidate_controls as bcc  # noqa: E402


REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")
ENRICHED_CSV = os.path.join(REPORT_DIR, "tail_y2_lineage_enriched_2026-04-10.csv.gz")
OUT_CSV = os.path.join(REPORT_DIR, "tail_candidate_cacheability_channels_2026-04-10.csv")


CHUNK_SIZE = 20_000


def load_tail_ids():
    ids = []
    with gzip.open(ENRICHED_CSV, "rt", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ids.append(int(row["render_wine_id"]))
    return ids


def fetch_normalized_chunks(ids):
    """Stream normalized fields from Render em chunks. Yields dicts por wine."""
    conn = bcc.connect_render()
    try:
        cur = conn.cursor()
        total = len(ids)
        t0 = time.time()
        for start in range(0, total, CHUNK_SIZE):
            chunk = ids[start:start + CHUNK_SIZE]
            cur.execute(
                "SELECT id, nome_normalizado, produtor_normalizado FROM wines WHERE id = ANY(%s)",
                (chunk,),
            )
            for row in cur.fetchall():
                yield {
                    "id": row[0],
                    "nome_normalizado": row[1] or "",
                    "produtor_normalizado": row[2] or "",
                }
            elapsed = time.time() - t0
            done = min(start + len(chunk), total)
            print(f"  [{done:,}/{total:,}] {done/total*100:5.1f}%  elapsed {elapsed:.1f}s", flush=True)
        cur.close()
    finally:
        bcc.safe_close(conn)


def compute_keys(store):
    """Retorna dict {channel_name -> key ou None}. None significa que a D5 nao
    dispararia query para este wine neste canal (threshold de len nao atendido)."""
    nome = (store.get("nome_normalizado") or "").strip()
    prod = (store.get("produtor_normalizado") or "").strip()

    out = {}

    # render_nome_produtor: usa f"{prod} {nome}".strip(), dispara se (nome or prod)
    if nome or prod:
        out["render_nome_produtor"] = f"{prod} {nome}".strip()
    else:
        out["render_nome_produtor"] = None

    # render_nome: dispara se len(nome)>=3
    out["render_nome"] = nome if len(nome) >= 3 else None

    # render_produtor: dispara se len(prod)>=3
    out["render_produtor"] = prod if len(prod) >= 3 else None

    # import_nome_produtor: exige nome_anchor (len>=4) E prod_anchor (len>=3)
    nome_anchor = bcc.longest_word(nome, min_len=4)
    prod_anchor = bcc.longest_word(prod, min_len=3)
    if nome_anchor and prod_anchor:
        out["import_nome_produtor"] = (nome_anchor, prod_anchor)
    else:
        out["import_nome_produtor"] = None

    # import_nome: longest_word(nome, 4)
    out["import_nome"] = nome_anchor if nome_anchor else None

    # import_produtor: longest_word(prod, 3)
    out["import_produtor"] = prod_anchor if prod_anchor else None

    return out


def freq_bucket(count):
    if count == 1:
        return "1x"
    if count == 2:
        return "2x"
    if 3 <= count <= 5:
        return "3-5x"
    if 6 <= count <= 10:
        return "6-10x"
    return ">10x"


def analyze_channel(ch_name, key_counter, total_wines, skipped):
    """Retorna dict com metricas para um canal."""
    distinct = len(key_counter)
    total_queries_if_live = total_wines - skipped  # D5 dispararia query pra cada wine nao skipped
    # com cache: total_queries_with_cache = distinct (build once)
    if total_queries_if_live <= 0:
        return None
    dedup_rate = 1.0 - distinct / total_queries_if_live
    theoretical_reduction = total_queries_if_live - distinct

    freq_dist = Counter()
    for _, c in key_counter.items():
        freq_dist[freq_bucket(c)] += 1

    # top-K cumulative coverage
    sorted_counts = sorted(key_counter.values(), reverse=True)
    cum = 0
    cov = {}
    target_ks = [100, 1000, 10000]
    for i, c in enumerate(sorted_counts):
        cum += c
        if (i + 1) in target_ks:
            cov[i + 1] = cum / total_queries_if_live
    for k in target_ks:
        if k not in cov:
            if sorted_counts:
                cum_all = sum(sorted_counts[:k])
                cov[k] = cum_all / total_queries_if_live
            else:
                cov[k] = 0.0

    max_count = sorted_counts[0] if sorted_counts else 0
    return {
        "channel": ch_name,
        "total_wines": total_wines,
        "skipped_no_key": skipped,
        "queries_if_live": total_queries_if_live,
        "distinct_keys": distinct,
        "dedup_rate": dedup_rate,
        "theoretical_reduction_queries": theoretical_reduction,
        "max_key_count": max_count,
        "freq_1x": freq_dist.get("1x", 0),
        "freq_2x": freq_dist.get("2x", 0),
        "freq_3_5x": freq_dist.get("3-5x", 0),
        "freq_6_10x": freq_dist.get("6-10x", 0),
        "freq_gt_10x": freq_dist.get(">10x", 0),
        "cov_top_100": cov.get(100, 0),
        "cov_top_1000": cov.get(1000, 0),
        "cov_top_10000": cov.get(10000, 0),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Limite de wines processados (default: tudo, 779.383)")
    args = parser.parse_args()

    print(f"[A] Carregando tail ids...")
    all_ids = load_tail_ids()
    if args.limit:
        all_ids = all_ids[:args.limit]
    print(f"    total: {len(all_ids):,}")

    print(f"[B] Streaming normalized fields do Render em chunks de {CHUNK_SIZE:,}...")
    counters = {
        "render_nome_produtor": Counter(),
        "render_nome": Counter(),
        "render_produtor": Counter(),
        "import_nome_produtor": Counter(),
        "import_nome": Counter(),
        "import_produtor": Counter(),
    }
    skipped = defaultdict(int)
    total_wines = 0
    t0 = time.time()
    for store in fetch_normalized_chunks(all_ids):
        total_wines += 1
        keys = compute_keys(store)
        for ch, k in keys.items():
            if k is None:
                skipped[ch] += 1
            else:
                counters[ch][k] += 1
    elapsed = time.time() - t0
    print(f"[B] done: {total_wines:,} wines em {elapsed:.1f}s")

    print(f"[C] Analyze cardinality por canal...")
    results = []
    for ch in ("render_nome_produtor", "render_nome", "render_produtor",
               "import_nome_produtor", "import_nome", "import_produtor"):
        r = analyze_channel(ch, counters[ch], total_wines, skipped[ch])
        if r:
            results.append(r)
            print(f"  [{ch:24s}] distinct={r['distinct_keys']:>8,} / queries={r['queries_if_live']:>7,}  dedup={r['dedup_rate']*100:5.2f}%  max_freq={r['max_key_count']}  top1000 cov={r['cov_top_1000']*100:5.1f}%")

    print(f"[D] Escrevendo CSV de saida...")
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        fields = [
            "channel", "total_wines", "skipped_no_key", "queries_if_live",
            "distinct_keys", "dedup_rate", "theoretical_reduction_queries",
            "max_key_count",
            "freq_1x", "freq_2x", "freq_3_5x", "freq_6_10x", "freq_gt_10x",
            "cov_top_100", "cov_top_1000", "cov_top_10000",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow(r)
    print(f"    escrito em {OUT_CSV}")


if __name__ == "__main__":
    main()
