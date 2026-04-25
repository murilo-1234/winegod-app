#!/usr/bin/env python3
"""
cron_score_recalc.py — Cron wrapper para recalculo incremental de scores.

Usa advisory lock para impedir execucoes sobrepostas.
Processa a fila score_recalc_queue e faz sweep periodico.

Render Cron Jobs:

  Fila (a cada 15 min):
    Command: python scripts/cron_score_recalc.py
    Schedule: */15 * * * *

  Sweep diario (4am UTC):
    Command: python scripts/cron_score_recalc.py --sweep
    Schedule: 0 4 * * *
"""

import argparse
import os
import sys
import time

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from calc_score_incremental import build_scoring_context, process_queue, sweep_all_with_price

import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL environment variable is required.")

# Keepalives anti SSL-closed em queries longas (sweep diario).
KEEPALIVE_KWARGS = {
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5,
}

# Advisory lock IDs (arbitrary unique integers, stable across runs)
LOCK_QUEUE = 73001
LOCK_SWEEP = 73002


def acquire_advisory_lock(conn, lock_id):
    """Try to acquire a session-level advisory lock. Returns True if acquired."""
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
    acquired = cur.fetchone()[0]
    cur.close()
    return acquired


def release_advisory_lock(conn, lock_id):
    """Release a session-level advisory lock."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        cur.close()
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Cron wrapper for score recalc")
    parser.add_argument("--sweep", action="store_true",
                        help="Full sweep instead of queue processing")
    parser.add_argument("--batch", type=int, default=200,
                        help="Queue batch size (default 200)")
    parser.add_argument("--max-time", type=int, default=300,
                        help="Max processing time in seconds (default 300)")
    args = parser.parse_args()

    t0 = time.time()
    conn = psycopg2.connect(DATABASE_URL, **KEEPALIVE_KWARGS)

    lock_id = LOCK_SWEEP if args.sweep else LOCK_QUEUE
    mode = "sweep" if args.sweep else "queue"

    if not acquire_advisory_lock(conn, lock_id):
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"Another {mode} instance is running. Exiting.",
            flush=True,
        )
        conn.close()
        sys.exit(0)

    try:
        if args.sweep:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting sweep...", flush=True)
            n = sweep_all_with_price(conn)
            elapsed = time.time() - t0
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Sweep done: {n} wines in {elapsed:.0f}s",
                flush=True,
            )
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Processing queue...", flush=True)
            ctx = build_scoring_context(conn)
            total = 0
            rounds = 0
            while time.time() - t0 < args.max_time:
                n = process_queue(conn, args.batch, scoring_ctx=ctx)
                total += n
                rounds += 1
                if n == 0:
                    break
            elapsed = time.time() - t0
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Queue done: {total} wines in {rounds} rounds, {elapsed:.0f}s",
                flush=True,
            )

            # Cleanup old processed items (keep last 7 days)
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM score_recalc_queue "
                "WHERE processed_at < NOW() - INTERVAL '7 days'"
            )
            cleaned = cur.rowcount
            conn.commit()
            if cleaned > 0:
                print(f"  Cleaned {cleaned} old queue entries", flush=True)

            # Report stuck items (exceeded max attempts)
            cur.execute(
                "SELECT COUNT(*) FROM score_recalc_queue "
                "WHERE processed_at IS NULL AND attempts >= 5"
            )
            stuck = cur.fetchone()[0]
            if stuck > 0:
                print(f"  WARNING: {stuck} items exceeded max attempts (dead-lettered)", flush=True)
            cur.close()

    finally:
        release_advisory_lock(conn, lock_id)
        conn.close()


if __name__ == "__main__":
    main()
