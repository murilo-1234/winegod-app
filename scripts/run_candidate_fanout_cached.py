"""
Demanda 6C -- Runner de fan-out usando CACHE PERSISTENTE por chave.

READ-ONLY. Le o SQLite produzido por scripts/build_candidate_cache.py
e produz detail + per_wine CSVs usando candidatos cacheados.

Logica D5 preservada:
  - mesmas chaves que build_candidate_cache.py computa
  - mesmo score_candidate() per-wine (aplicado DEPOIS do cache hit)
  - mesmo rank_top3() com tiebreak candidate_id ASC
  - mesmos 6 canais na mesma ordem
  - zero conexao a Postgres na fase consume (cache e a fonte unica)

Uso:
  python scripts/run_candidate_fanout_cached.py \\
      --slice 250 \\
      --cache reports/candidate_cache_slice250.sqlite3 \\
      --out-detail reports/tail_candidate_fanout_cached_250_detail_2026-04-10.csv.gz \\
      --out-per-wine reports/tail_candidate_fanout_cached_250_per_wine_2026-04-10.csv.gz

Miss policy:
  --on-miss=fail       -> erro se alguma chave estiver ausente do cache (default)
  --on-miss=live       -> fallback para queries ao vivo (para validar)
  --on-miss=empty      -> tratar como empty candidates
"""

import argparse
import csv
import gzip
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_candidate_controls as bcc  # noqa: E402
import run_candidate_fanout_pilot as d6a_runner  # noqa: E402
import run_candidate_fanout_fast as fast_runner  # noqa: E402
import build_candidate_cache as cache_builder  # noqa: E402


REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")


# ---------- SQLite cache reader ----------

class CacheReader:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None, timeout=30)
        self.db.execute("PRAGMA query_only = ON")
        self._stmts = {}
        self._stats = {ch: {"hit": 0, "miss": 0, "null_key": 0} for ch in (
            "render_nome_produtor", "render_nome", "render_produtor",
            "import_nome_produtor", "import_nome", "import_produtor",
        )}

    def lookup(self, channel, key):
        if key is None:
            self._stats[channel]["null_key"] += 1
            return None  # nao disparo query (len<3 ou sem anchor)
        row = self.db.execute(
            f"SELECT payload_json FROM cache_{channel} WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            self._stats[channel]["miss"] += 1
            return None
        self._stats[channel]["hit"] += 1
        return json.loads(row[0])

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass

    def stats(self):
        return self._stats


# ---------- consumer ----------

def _append_channel_top3(rows, wid, batch_id, ch_name, ch_universe, top3):
    if not top3:
        return
    top1_score = top3[0][1]
    top2_score = top3[1][1] if len(top3) >= 2 else 0.0
    gap = round(top1_score - top2_score, 4)
    for rank, (cand, score) in enumerate(top3, 1):
        rows.append({
            "render_wine_id": wid,
            "channel": ch_name,
            "candidate_rank": rank,
            "candidate_universe": ch_universe,
            "candidate_id": cand["id"],
            "candidate_nome": cand.get("nome_normalizado") or cand.get("nome") or "",
            "candidate_produtor": cand.get("produtor_normalizado") or cand.get("produtor") or "",
            "candidate_safra": cand.get("safra") if cand.get("safra") is not None else "",
            "candidate_tipo": cand.get("tipo") if cand.get("tipo") is not None else "",
            "raw_score": score,
            "top1_top2_gap": gap,
            "batch_id": batch_id,
        })


def consume_slice(cache, source_info, slice_ids, on_miss, live_ctx=None):
    """Produz detail rows consumindo exclusivamente o cache. Opcionalmente
    cai em live queries quando on_miss='live'."""
    detail_rows = []
    miss_live = 0
    miss_empty = 0
    for batch_start in range(0, len(slice_ids), fast_runner.BATCH_SIZE):
        batch_ids = slice_ids[batch_start:batch_start + fast_runner.BATCH_SIZE]
        batch_id = batch_start // fast_runner.BATCH_SIZE
        for wid in batch_ids:
            store = source_info.get(wid)
            if not store:
                continue
            # CHANNELS_RENDER order: nome_produtor, nome, produtor
            for ch_name, ch_universe in [
                ("render_nome_produtor", "render"),
                ("render_nome", "render"),
                ("render_produtor", "render"),
                ("import_nome_produtor", "import"),
                ("import_nome", "import"),
                ("import_produtor", "import"),
            ]:
                key = cache_builder.key_for(ch_name, store)
                payload = cache.lookup(ch_name, key)
                if payload is None:
                    # duas situacoes: null_key (=skip, 0 cands) ou miss real
                    if key is None:
                        cands_dicts = []
                    else:
                        if on_miss == "fail":
                            raise RuntimeError(
                                f"cache MISS wid={wid} channel={ch_name} key={key!r}"
                            )
                        elif on_miss == "empty":
                            miss_empty += 1
                            cands_dicts = []
                        elif on_miss == "live":
                            miss_live += 1
                            cands_dicts = _live_fallback(ch_name, store, live_ctx)
                else:
                    cands_dicts = payload

                # cast cand dicts para o formato aceito por score_candidate
                top3 = bcc.rank_top3(cands_dicts, store)
                _append_channel_top3(detail_rows, wid, batch_id, ch_name, ch_universe, top3)
    return detail_rows, miss_live, miss_empty


def _live_fallback(ch_name, store, ctx):
    """Executa a query live como fallback. ctx = dict com cursors."""
    if ch_name == "render_nome_produtor":
        return bcc.channel_render_nome_produtor(ctx["local_cur"], store)
    if ch_name == "render_nome":
        return bcc.channel_render_nome(ctx["local_cur"], store)
    if ch_name == "render_produtor":
        return bcc.channel_render_produtor(ctx["local_cur"], store)
    if ch_name == "import_nome_produtor":
        return bcc.channel_import_nome_produtor(ctx["viv_cur"], store)
    if ch_name == "import_nome":
        return bcc.channel_import_nome(ctx["viv_cur"], store)
    if ch_name == "import_produtor":
        return bcc.channel_import_produtor(ctx["viv_cur"], store)
    raise ValueError(ch_name)


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slice", type=int, default=250)
    parser.add_argument("--cache", type=str, default=os.path.join(REPORT_DIR, "candidate_cache_slice250.sqlite3"))
    parser.add_argument("--out-detail", type=str,
                        default=os.path.join(REPORT_DIR, "tail_candidate_fanout_cached_250_detail_2026-04-10.csv.gz"))
    parser.add_argument("--out-per-wine", type=str,
                        default=os.path.join(REPORT_DIR, "tail_candidate_fanout_cached_250_per_wine_2026-04-10.csv.gz"))
    parser.add_argument("--on-miss", choices=("fail", "live", "empty"), default="fail")
    args = parser.parse_args()

    # 1) Seleciona slice (mesma ordem deterministica)
    pilot_ids, _ = d6a_runner.select_pilot()
    slice_ids = pilot_ids[:args.slice]
    print(f"[slice] {len(slice_ids):,} wines: {slice_ids[0]}..{slice_ids[-1]}")

    # 2) Source info (1 query Render)
    print(f"[prefetch] source info...")
    t0 = time.time()
    source_info = fast_runner.prefetch_source_info(slice_ids)
    prefetch_sec = time.time() - t0
    print(f"[prefetch] {len(source_info):,} rows em {prefetch_sec:.1f}s")

    # 3) Abrir cache
    print(f"[cache] abrindo {args.cache}")
    cache = CacheReader(args.cache)

    # 4) Opcional: live fallback context
    live_ctx = None
    if args.on_miss == "live":
        print(f"[live-fallback] bootstrap e abrir live cursors...")
        rset = bcc.bootstrap_render_vivino_id_set()
        only_vivino = bcc.bootstrap_only_vivino_db_set(rset)
        local_conn = bcc.connect_local()
        viv_conn = bcc.connect_vivino_db()
        local_cur = local_conn.cursor()
        local_cur.execute("SET pg_trgm.similarity_threshold = 0.10")
        viv_cur = bcc.setup_only_vivino_temp(viv_conn, only_vivino)
        viv_cur.execute("SET pg_trgm.similarity_threshold = 0.10")
        live_ctx = {
            "local_cur": local_cur, "viv_cur": viv_cur,
            "local_conn": local_conn, "viv_conn": viv_conn,
        }

    # 5) Consumo
    print(f"[consume] processando {len(slice_ids):,} wines via cache...")
    t_consume0 = time.time()
    detail_rows, miss_live, miss_empty = consume_slice(
        cache, source_info, slice_ids, args.on_miss, live_ctx
    )
    consume_sec = time.time() - t_consume0
    print(f"[consume] {len(detail_rows):,} detail rows em {consume_sec:.3f}s  ({consume_sec/len(slice_ids)*1000:.2f}ms/wine)")

    # Stats cache
    stats = cache.stats()
    print(f"[cache stats]")
    total_hit = 0; total_miss = 0; total_null = 0
    for ch, s in stats.items():
        print(f"  {ch:24s}  hit={s['hit']:>5}  miss={s['miss']:>3}  null_key={s['null_key']:>3}")
        total_hit += s["hit"]; total_miss += s["miss"]; total_null += s["null_key"]
    print(f"  TOTAL                    hit={total_hit:>5}  miss={total_miss:>3}  null_key={total_null:>3}")
    if miss_live:
        print(f"  miss caiu em live: {miss_live}")

    # Dedupe defensivo por (wid, channel, rank, candidate_id)
    seen = set()
    dedup = []
    for r in detail_rows:
        key = (r["render_wine_id"], r["channel"], r["candidate_rank"], r["candidate_id"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)

    # 6) Escrita
    print(f"[write] detail -> {args.out_detail}")
    with gzip.open(args.out_detail, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fast_runner.DETAIL_HEADER, extrasaction="ignore")
        w.writeheader()
        for r in dedup:
            w.writerow(r)

    per_wine_rows = fast_runner.build_per_wine_rows(dedup, slice_ids)
    print(f"[write] per_wine -> {args.out_per_wine}")
    with gzip.open(args.out_per_wine, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fast_runner.PERWINE_HEADER, extrasaction="ignore")
        w.writeheader()
        for r in per_wine_rows:
            w.writerow(r)

    if live_ctx:
        try:
            live_ctx["local_conn"].close()
            live_ctx["viv_conn"].close()
        except Exception:
            pass
    cache.close()

    print()
    print(f"=== CACHED CONSUME: {len(slice_ids)} itens em {consume_sec:.3f}s (+{prefetch_sec:.1f}s prefetch) ===")


if __name__ == "__main__":
    main()
