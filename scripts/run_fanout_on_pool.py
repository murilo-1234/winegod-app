"""
Demanda 7 -- Wrapper do runner rapido D6B para rodar fan-out em uma LISTA
EXPLICITA de render_wine_ids (o working pool), em vez da selecao do piloto
D6A.

READ-ONLY. Reusa integralmente a logica CONGELADA de:
  - bcc.CHANNELS_RENDER, CHANNELS_IMPORT, score_candidate, rank_top3
  - fast_runner.worker_loop, prefetch_source_info, build_per_wine_rows

Zero drift semantico. So muda a ORIGEM da lista de ids.

Uso:
  python scripts/run_fanout_on_pool.py \\
      --pool-csv reports/tail_working_pool_1200_2026-04-10.csv \\
      --out-detail reports/tail_working_pool_fanout_detail_2026-04-10.csv.gz \\
      --out-per-wine reports/tail_working_pool_fanout_per_wine_2026-04-10.csv.gz \\
      --workers 32
"""

import argparse
import csv
import gzip
import os
import queue
import shutil
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_candidate_controls as bcc  # noqa: E402
import run_candidate_fanout_fast as fast_runner  # noqa: E402


REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")


def load_pool_ids(csv_path):
    ids = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ids.append(int(row["render_wine_id"]))
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool-csv", required=True,
                    help="CSV com coluna render_wine_id (working pool)")
    ap.add_argument("--out-detail", required=True)
    ap.add_argument("--out-per-wine", required=True)
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--batch-size", type=int, default=250)
    ap.add_argument("--partial-dir", type=str,
                    default=os.path.join(REPORT_DIR, ".fanout_pool_partial"))
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    pool_ids = load_pool_ids(args.pool_csv)
    print(f"[pool] {len(pool_ids):,} ids from {args.pool_csv}")

    # Bootstrap
    print(f"[boot] carregando indices...")
    t0 = time.time()
    rset = bcc.bootstrap_render_vivino_id_set()
    only_vivino = bcc.bootstrap_only_vivino_db_set(rset)
    boot_sec = time.time() - t0
    print(f"[boot] done {boot_sec:.1f}s")

    # Prefetch source info (1 query Render)
    print(f"[prefetch] source info...")
    t0 = time.time()
    source_info = fast_runner.prefetch_source_info(pool_ids)
    pref_sec = time.time() - t0
    print(f"[prefetch] {len(source_info):,} rows em {pref_sec:.1f}s")

    # Limpar partial dir se --fresh
    if args.fresh and os.path.exists(args.partial_dir):
        shutil.rmtree(args.partial_dir)
    os.makedirs(args.partial_dir, exist_ok=True)

    # Pool de workers (fast_runner worker_loop)
    print(f"[pool] iniciando {args.workers} workers...")
    task_q = queue.Queue()
    result_q = queue.Queue()
    threads = [
        threading.Thread(
            target=fast_runner.worker_loop,
            args=(task_q, result_q, only_vivino),
            daemon=True,
        )
        for _ in range(args.workers)
    ]
    for t in threads:
        t.start()

    # Loop de batches
    batch_size = args.batch_size
    n_batches = (len(pool_ids) + batch_size - 1) // batch_size
    print(f"[run] {n_batches} batches x {batch_size} wines")

    all_detail_rows = []
    session_t0 = time.time()
    try:
        for batch_idx in range(n_batches):
            bstart = batch_idx * batch_size
            batch_ids = pool_ids[bstart:bstart + batch_size]

            t0 = time.time()
            submitted = 0
            for wid in batch_ids:
                store = source_info.get(wid)
                if not store:
                    continue
                task_q.put((wid, store, batch_idx))
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

            if errors:
                print(f"  [batch {batch_idx}] ERROS: {errors[:3]}")
                raise RuntimeError(f"batch {batch_idx} worker errors: {errors[:3]}")

            # Dedupe defensivo
            seen = set()
            dedup = []
            for r in collected_rows:
                key = (r["render_wine_id"], r["channel"], r["candidate_rank"], r["candidate_id"])
                if key in seen:
                    continue
                seen.add(key)
                dedup.append(r)
            all_detail_rows.extend(dedup)

            # Write atomic partial
            part_path = os.path.join(args.partial_dir, f"batch_{batch_idx:05d}.csv")
            tmp = part_path + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fast_runner.DETAIL_HEADER, extrasaction="ignore")
                w.writeheader()
                for r in dedup:
                    w.writerow(r)
            os.replace(tmp, part_path)

            elapsed = time.time() - t0
            print(f"  [batch {batch_idx+1}/{n_batches}] {submitted} wines, {elapsed:.1f}s, {len(dedup)} rows")

    finally:
        for _ in threads:
            task_q.put(None)
        for t in threads:
            t.join(timeout=30)

    session_sec = time.time() - session_t0
    print(f"[session] {session_sec:.1f}s em {n_batches} batches")

    # ---------- Finalize ----------
    print(f"[write] detail -> {args.out_detail}")
    with gzip.open(args.out_detail, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fast_runner.DETAIL_HEADER, extrasaction="ignore")
        w.writeheader()
        for r in all_detail_rows:
            w.writerow(r)

    print(f"[build per_wine]")
    per_wine = fast_runner.build_per_wine_rows(all_detail_rows, pool_ids)

    print(f"[write] per_wine -> {args.out_per_wine}")
    with gzip.open(args.out_per_wine, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fast_runner.PERWINE_HEADER, extrasaction="ignore")
        w.writeheader()
        for r in per_wine:
            w.writerow(r)

    print()
    print(f"=== WORKING POOL FAN-OUT ===")
    print(f"  pool size:      {len(pool_ids):,}")
    print(f"  detail rows:    {len(all_detail_rows):,}")
    print(f"  per_wine rows:  {len(per_wine):,}")
    print(f"  bootstrap:      {boot_sec:.1f}s")
    print(f"  prefetch:       {pref_sec:.1f}s")
    print(f"  session run:    {session_sec:.1f}s")
    print(f"  wall total:     {boot_sec+pref_sec+session_sec:.1f}s")


if __name__ == "__main__":
    main()
