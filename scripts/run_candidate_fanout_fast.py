"""
Demanda 6B -- Runner de fan-out ACELERADO.

READ-ONLY. Nenhuma escrita em producao.

LOGICA CONGELADA: importa as funcoes diretamente de `build_candidate_controls.py`
(Demanda 5). Mesmos 6 canais, mesma score function, mesmo tiebreak
`candidate_id ASC`, mesma restricao Import via TEMP TABLE `_only_vivino`.
Zero drift semantico.

Estrategia de aceleracao:
  1) Pool de workers threads com CONEXOES PERSISTENTES.
     Cada worker cria local_conn + viv_conn UMA UNICA VEZ, constroi o
     TEMP TABLE `_only_vivino` UMA UNICA VEZ, e reusa a mesma tupla
     de cursores para todos os wines que processar. Isso elimina o
     overhead de connect + temp-table-build por wine do runner original
     (o runner antigo nao usava pool explicito mas cada canal ainda
     batia no mesmo cursor sequencial).

  2) Memoizacao compartilhada dos 2 canais `*_produtor`. Em um sample
     de 50 wines reais da cauda, 48% dos valores de produtor_normalizado
     se repetem. Cacheamos por chave de produto e reusamos o resultado
     SQL. Como `score_candidate` nao usa trgm_sim, e o ranking final
     ordena por (score DESC, candidate_id ASC), o resultado e identico.

  3) Prefetch de `fetch_source_info` para TODOS os wines do slice em
     UMA query Render, nao uma por batch. Poupa round-trips ao Render.

  4) Mesmo layout de checkpoint/parciais atomicos do runner D6A: o
     finalize concatena parciais -> detail.csv.gz + per_wine.csv.gz.

Compatibilidade com artefatos oficiais de D6A:
  - A ordem de itens, o formato do detail/per_wine, a ordenacao dos
    candidatos dentro de cada canal (dedupe por id; re-rank por
    (-score, id)), e o tiebreak alfabetico em channel, sao preservados.
  - O slice de 250 primeiros ids gera output funcionalmente identico
    ao artefato oficial D6A para o mesmo slice. (Ver equivalence test.)

Uso:
  python scripts/run_candidate_fanout_fast.py --slice 250               # equivalence
  python scripts/run_candidate_fanout_fast.py --slice 250 --benchmark   # timing
  python scripts/run_candidate_fanout_fast.py --slice 10000             # piloto fast
  python scripts/run_candidate_fanout_fast.py --slice 10000 --fresh
  python scripts/run_candidate_fanout_fast.py --slice 250 --workers 16

Artefatos (separados por slice, para nao clobberar D6A):
  reports/tail_candidate_fanout_fast_<slice>_detail_2026-04-10.csv.gz
  reports/tail_candidate_fanout_fast_<slice>_per_wine_2026-04-10.csv.gz
  reports/tail_candidate_fanout_fast_<slice>_checkpoint_2026-04-10.json
  reports/.fanout_fast_<slice>_partial/batch_NNNNN.csv
"""

import argparse
import csv
import gzip
import hashlib
import json
import os
import queue
import shutil
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_candidate_controls as bcc  # noqa: E402
import run_candidate_fanout_pilot as d6a_runner  # noqa: E402  (reuse select_pilot etc)


BATCH_SIZE = 250
DEFAULT_WORKERS = 32

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")

DETAIL_HEADER = d6a_runner.DETAIL_HEADER
PERWINE_HEADER = d6a_runner.PERWINE_HEADER


def artifact_paths(slice_size):
    prefix = f"tail_candidate_fanout_fast_{slice_size}"
    return dict(
        detail=os.path.join(REPORT_DIR, f"{prefix}_detail_2026-04-10.csv.gz"),
        per_wine=os.path.join(REPORT_DIR, f"{prefix}_per_wine_2026-04-10.csv.gz"),
        checkpoint=os.path.join(REPORT_DIR, f"{prefix}_checkpoint_2026-04-10.json"),
        partial_dir=os.path.join(REPORT_DIR, f".fanout_fast_{slice_size}_partial"),
    )


# ---------- checkpoint ----------

def init_checkpoint(pilot_hash, slice_ids, workers):
    return {
        "schema_version": 2,
        "demanda": "6B",
        "runner": "run_candidate_fanout_fast.py",
        "pilot_hash": pilot_hash,
        "slice_size": len(slice_ids),
        "batch_size": BATCH_SIZE,
        "workers": workers,
        "total_batches": (len(slice_ids) + BATCH_SIZE - 1) // BATCH_SIZE,
        "completed_batches": [],
        "processed_items": 0,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_update": None,
        "resume_count": 0,
        "batch_timings_sec": [],
        "bootstrap_sec": None,
        "prefetch_source_sec": None,
        "errors": [],
        "memo_hits": {},
        "done": False,
    }


def save_checkpoint(cp, path):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cp, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_checkpoint(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_slice_hash(slice_ids, workers):
    h = hashlib.sha256()
    for pid in slice_ids:
        h.update(str(pid).encode())
        h.update(b",")
    h.update(f"|workers={workers}".encode())
    return h.hexdigest()


# ---------- partial files (same layout as D6A) ----------

def partial_path(partial_dir, batch_id):
    return os.path.join(partial_dir, f"batch_{batch_id:05d}.csv")


def write_batch_file(partial_dir, batch_id, rows):
    path = partial_path(partial_dir, batch_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DETAIL_HEADER, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    os.replace(tmp, path)


def read_all_partial_files(partial_dir, total_batches):
    rows = []
    for batch_id in range(total_batches):
        path = partial_path(partial_dir, batch_id)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    return rows


# ---------- prefetch source info (all in one Render round-trip) ----------

def prefetch_source_info(all_ids):
    conn = bcc.connect_render()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, nome_normalizado, produtor_normalizado, safra, tipo
            FROM wines
            WHERE id = ANY(%s)
            """,
            (list(all_ids),),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        bcc.safe_close(conn)
    return {
        r[0]: {
            "nome_normalizado": r[1],
            "produtor_normalizado": r[2],
            "safra": r[3],
            "tipo": r[4],
        }
        for r in rows
    }


# ---------- worker ----------

# Shared memo for produtor-only channels. dict reads/writes are thread-safe
# under CPython's GIL; we also guard each channel with its own dict so there
# is no cross-channel confusion.
_MEMO_RENDER_PROD = {}       # key = produtor_normalizado -> list[cand dicts]
_MEMO_IMPORT_PROD = {}       # key = longest_word(prod,3) -> list[cand dicts]
_MEMO_IMPORT_NOME = {}       # key = longest_word(nome,4) -> list[cand dicts]
_MEMO_HITS = defaultdict(int)
_MEMO_MISSES = defaultdict(int)
_MEMO_LOCK = threading.Lock()  # only used to increment counters


def _memo_get_or_run(memo, key, compute_fn):
    """
    Thread-safe-enough memoization. We allow two threads to compute the same
    key concurrently on a cold cache (duplicate work once in a race), then
    last writer wins. Result is deterministic because compute_fn is
    semantically idempotent (same SQL, same result set, same Python dedupe).
    """
    cached = memo.get(key)
    if cached is not None:
        with _MEMO_LOCK:
            _MEMO_HITS[id(memo)] += 1
        return cached
    result = compute_fn()
    memo[key] = result
    with _MEMO_LOCK:
        _MEMO_MISSES[id(memo)] += 1
    return result


def _memoized_render_produtor(local_cur, store):
    prod = (store.get("produtor_normalizado") or "").strip()
    if len(prod) < 3:
        return []
    return _memo_get_or_run(
        _MEMO_RENDER_PROD,
        prod,
        lambda: bcc.channel_render_produtor(local_cur, store),
    )


def _memoized_import_produtor(viv_cur, store):
    prod = (store.get("produtor_normalizado") or store.get("produtor") or "")
    anchor = bcc.longest_word(prod, min_len=3)
    if not anchor:
        return []
    return _memo_get_or_run(
        _MEMO_IMPORT_PROD,
        anchor,
        lambda: bcc.channel_import_produtor(viv_cur, store),
    )


def _memoized_import_nome(viv_cur, store):
    nome = (store.get("nome_normalizado") or store.get("nome") or "")
    anchor = bcc.longest_word(nome, min_len=4)
    if not anchor:
        return []
    return _memo_get_or_run(
        _MEMO_IMPORT_NOME,
        anchor,
        lambda: bcc.channel_import_nome(viv_cur, store),
    )


# Memoized channel dispatch preserves the 6-channel contract but intercepts
# the high-duplicate ones.
def _run_channels_memoized(wid, store, batch_id, local_cur, viv_cur):
    rows = []

    # CHANNELS_RENDER order: nome_produtor, nome, produtor
    cands = bcc.channel_render_nome_produtor(local_cur, store)
    _append_channel_top3(rows, wid, batch_id, "render_nome_produtor", "render", bcc.rank_top3(cands, store))

    cands = bcc.channel_render_nome(local_cur, store)
    _append_channel_top3(rows, wid, batch_id, "render_nome", "render", bcc.rank_top3(cands, store))

    cands = _memoized_render_produtor(local_cur, store)
    _append_channel_top3(rows, wid, batch_id, "render_produtor", "render", bcc.rank_top3(cands, store))

    # CHANNELS_IMPORT order: nome_produtor, nome, produtor
    cands = bcc.channel_import_nome_produtor(viv_cur, store)
    _append_channel_top3(rows, wid, batch_id, "import_nome_produtor", "import", bcc.rank_top3(cands, store))

    cands = _memoized_import_nome(viv_cur, store)
    _append_channel_top3(rows, wid, batch_id, "import_nome", "import", bcc.rank_top3(cands, store))

    cands = _memoized_import_produtor(viv_cur, store)
    _append_channel_top3(rows, wid, batch_id, "import_produtor", "import", bcc.rank_top3(cands, store))

    return rows


def _append_channel_top3(detail_rows, wid, batch_id, ch_name, ch_universe, top3):
    if not top3:
        return
    top1_score = top3[0][1]
    top2_score = top3[1][1] if len(top3) >= 2 else 0.0
    gap = round(top1_score - top2_score, 4)
    for rank, (cand, score) in enumerate(top3, 1):
        detail_rows.append({
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


def worker_loop(task_q, result_q, only_vivino_ids):
    """
    Each worker holds persistent local_conn + viv_conn and a built temp
    table. Processes wines until sentinel None.
    """
    local_conn = None
    viv_conn = None
    try:
        local_conn = bcc.connect_local()
        viv_conn = bcc.connect_vivino_db()
        local_cur = local_conn.cursor()
        local_cur.execute("SET pg_trgm.similarity_threshold = 0.10")
        viv_cur = bcc.setup_only_vivino_temp(viv_conn, only_vivino_ids)
        viv_cur.execute("SET pg_trgm.similarity_threshold = 0.10")

        while True:
            task = task_q.get()
            if task is None:
                break
            wid, store, batch_id = task
            try:
                rows = _run_channels_memoized(wid, store, batch_id, local_cur, viv_cur)
                result_q.put(("ok", batch_id, wid, rows))
            except Exception as e:
                result_q.put(("err", batch_id, wid, f"{type(e).__name__}: {e}"))
    finally:
        if local_conn is not None:
            try: local_conn.close()
            except Exception: pass
        if viv_conn is not None:
            try: viv_conn.close()
            except Exception: pass


# ---------- batch-level orchestration ----------

def process_batch_parallel(batch_id, batch_ids, source_info, only_vivino,
                           workers, task_q, result_q):
    """
    Submits wines of one batch to the pool and collects rows. The pool
    is shared across batches (persistent).
    """
    submitted = 0
    for wid in batch_ids:
        store = source_info.get(wid)
        if not store:
            continue
        task_q.put((wid, store, batch_id))
        submitted += 1

    collected_rows = []
    errors = []
    completed = 0
    while completed < submitted:
        status, bid, wid, payload = result_q.get()
        completed += 1
        if status == "ok":
            collected_rows.extend(payload)
        else:
            errors.append((bid, wid, payload))
    return collected_rows, errors


# ---------- per_wine (reuse D6A logic verbatim) ----------

build_per_wine_rows = d6a_runner.build_per_wine_rows
write_detail_csv_gz = d6a_runner.write_detail_csv_gz
write_per_wine_csv_gz = d6a_runner.write_per_wine_csv_gz


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slice", type=int, default=10000,
                        help="Quantos render_wine_ids do piloto processar")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="Tamanho do pool de workers threads")
    parser.add_argument("--fresh", action="store_true",
                        help="Descarta checkpoint + parciais")
    parser.add_argument("--benchmark", action="store_true",
                        help="Imprime timings detalhados")
    args = parser.parse_args()

    paths = artifact_paths(args.slice)

    # 1) Selecao (mesma logica D6A)
    pilot_ids_full, control_ids = d6a_runner.select_pilot()
    slice_ids = pilot_ids_full[:args.slice]
    slice_hash = compute_slice_hash(slice_ids, args.workers)
    print(f"[slice] size={len(slice_ids):,}, first={slice_ids[0]}, last={slice_ids[-1]}, hash={slice_hash[:16]}...")

    # 2) Checkpoint load/init
    cp = load_checkpoint(paths["checkpoint"])
    if args.fresh or cp is None or cp.get("pilot_hash") != slice_hash:
        if args.fresh:
            print("[--fresh] descartando checkpoint e parciais")
        elif cp is None:
            print("[checkpoint] nenhum checkpoint -- fresh start")
        else:
            print("[checkpoint] pilot_hash/workers divergente -- fresh start")
        if os.path.exists(paths["partial_dir"]):
            shutil.rmtree(paths["partial_dir"])
        os.makedirs(paths["partial_dir"], exist_ok=True)
        cp = init_checkpoint(slice_hash, slice_ids, args.workers)
    else:
        cp["resume_count"] = cp.get("resume_count", 0) + 1
        cp["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[checkpoint] RESUME de {len(cp['completed_batches'])} batches completos (resume #{cp['resume_count']})")
        os.makedirs(paths["partial_dir"], exist_ok=True)
    save_checkpoint(cp, paths["checkpoint"])

    # 3) Bootstrap indices (only_vivino set) -- paga 1x por sessao
    print("[boot] carregando indices Render + vivino_db...")
    t_boot0 = time.time()
    render_vivino_id_set = bcc.bootstrap_render_vivino_id_set()
    only_vivino = bcc.bootstrap_only_vivino_db_set(render_vivino_id_set)
    cp["bootstrap_sec"] = round(time.time() - t_boot0, 3)
    print(f"[boot] total: {cp['bootstrap_sec']:.1f}s")

    # 4) Prefetch TODOS os source infos do slice em 1 query Render
    print(f"[prefetch] fetching source info de {len(slice_ids):,} wines...")
    t_pref0 = time.time()
    source_info = prefetch_source_info(slice_ids)
    cp["prefetch_source_sec"] = round(time.time() - t_pref0, 3)
    print(f"[prefetch] got {len(source_info):,} rows em {cp['prefetch_source_sec']:.1f}s")
    save_checkpoint(cp, paths["checkpoint"])

    # 5) Iniciar pool de workers (persistente por sessao)
    print(f"[pool] iniciando {args.workers} workers...")
    task_q = queue.Queue()
    result_q = queue.Queue()
    threads = [
        threading.Thread(
            target=worker_loop,
            args=(task_q, result_q, only_vivino),
            daemon=True,
        )
        for _ in range(args.workers)
    ]
    for t in threads:
        t.start()

    # 6) Loop de batches (respeitando checkpoint)
    completed_set = set(cp["completed_batches"])
    total_batches = cp["total_batches"]
    session_start = time.time()
    batches_run = 0
    try:
        for batch_id in range(total_batches):
            if batch_id in completed_set:
                continue
            batch_start = batch_id * BATCH_SIZE
            batch_ids = slice_ids[batch_start:batch_start + BATCH_SIZE]

            t0 = time.time()
            try:
                rows, batch_errs = process_batch_parallel(
                    batch_id, batch_ids, source_info, only_vivino,
                    args.workers, task_q, result_q,
                )
                if batch_errs:
                    for berr in batch_errs:
                        cp["errors"].append(f"batch {berr[0]} wid={berr[1]}: {berr[2]}")
                    save_checkpoint(cp, paths["checkpoint"])
                    raise RuntimeError(f"batch {batch_id} worker errors: {batch_errs[:3]}")

                # Dedupe defensivo por (wid, channel, rank, candidate_id)
                seen = set()
                dedup = []
                for r in rows:
                    key = (r["render_wine_id"], r["channel"], r["candidate_rank"], r["candidate_id"])
                    if key in seen:
                        continue
                    seen.add(key)
                    dedup.append(r)
                write_batch_file(paths["partial_dir"], batch_id, dedup)
            except Exception as e:
                err = f"batch {batch_id}: {type(e).__name__}: {e}"
                cp["errors"].append(err)
                save_checkpoint(cp, paths["checkpoint"])
                print(f"    [batch {batch_id}] ERRO: {err}")
                raise

            elapsed = round(time.time() - t0, 3)
            cp["completed_batches"].append(batch_id)
            cp["processed_items"] = len(cp["completed_batches"]) * BATCH_SIZE
            cp["batch_timings_sec"].append(elapsed)
            cp["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cp["memo_hits"] = {
                "render_produtor_hits": _MEMO_HITS[id(_MEMO_RENDER_PROD)],
                "render_produtor_misses": _MEMO_MISSES[id(_MEMO_RENDER_PROD)],
                "import_produtor_hits": _MEMO_HITS[id(_MEMO_IMPORT_PROD)],
                "import_produtor_misses": _MEMO_MISSES[id(_MEMO_IMPORT_PROD)],
                "import_nome_hits": _MEMO_HITS[id(_MEMO_IMPORT_NOME)],
                "import_nome_misses": _MEMO_MISSES[id(_MEMO_IMPORT_NOME)],
            }
            save_checkpoint(cp, paths["checkpoint"])
            batches_run += 1
            print(f"  [batch {batch_id + 1}/{total_batches}] {len(batch_ids)} itens, {elapsed:.1f}s, {len(dedup)} rows")
    finally:
        # Sentinel para encerrar workers
        for _ in threads:
            task_q.put(None)
        for t in threads:
            t.join(timeout=30)

    session_elapsed = time.time() - session_start
    print(f"[session] {batches_run} batches em {session_elapsed:.1f}s")

    # 7) Finalize
    print("[finalize] lendo parciais...")
    detail_rows_raw = read_all_partial_files(paths["partial_dir"], total_batches)
    print(f"    detail rows (raw): {len(detail_rows_raw):,}")

    seen = set()
    detail_rows = []
    for r in detail_rows_raw:
        key = (r["render_wine_id"], r["channel"], r["candidate_rank"], r["candidate_id"])
        if key in seen:
            continue
        seen.add(key)
        detail_rows.append(r)
    print(f"    detail rows (deduped): {len(detail_rows):,}")

    print("[finalize] escrevendo detail CSV.gz...")
    write_detail_csv_gz(paths["detail"], detail_rows)

    print("[finalize] construindo per_wine rows...")
    per_wine_rows = build_per_wine_rows(detail_rows, slice_ids)
    print("[finalize] escrevendo per_wine CSV.gz...")
    write_per_wine_csv_gz(paths["per_wine"], per_wine_rows)

    cp["done"] = True
    cp["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_checkpoint(cp, paths["checkpoint"])

    print()
    print(f"Detail:     {paths['detail']}")
    print(f"Per-wine:   {paths['per_wine']}")
    print(f"Checkpoint: {paths['checkpoint']}")
    print()
    # Summary de throughput
    timings = cp["batch_timings_sec"]
    if timings:
        mean = sum(timings) / len(timings)
        print(f"=== FAST RUNNER: {len(slice_ids)} itens em {sum(timings):.1f}s ({mean:.1f}s/batch) ===")


if __name__ == "__main__":
    main()
