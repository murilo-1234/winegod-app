#!/usr/bin/env python3
"""
Execução dos 14 recoverable_safe restantes (pós-piloto de 25).
Mesma lógica e guardrails do piloto.
"""

import csv
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True)

import psycopg2
import psycopg2.extras

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_recoverable_safe.csv")
PILOT_CSV = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_pilot_25.csv")

OUT_INPUT   = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_restante_14.csv")
OUT_REVERT  = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_restante_14_revert.csv")
OUT_SKIPPED = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_restante_14_skipped.csv")

ENV_PATH = os.path.join(SCRIPT_DIR, "..", "backend", ".env")
DATABASE_URL = None
with open(ENV_PATH, "r") as f:
    for line in f:
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            DATABASE_URL = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found")
    sys.exit(1)


def main():
    print(f"[{datetime.now():%H:%M:%S}] Loading inputs...")

    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        all_39 = list(csv.DictReader(f))

    with open(PILOT_CSV, "r", encoding="utf-8") as f:
        done_ws = set(r["ws_id_recovered"] for r in csv.DictReader(f))

    remaining = [r for r in all_39 if r["ws_id_recovered"] not in done_ws]
    print(f"  All safe: {len(all_39)}, pilot done: {len(done_ws)}, remaining: {len(remaining)}")

    if len(remaining) != 14:
        print(f"  WARNING: expected 14, got {len(remaining)}")

    # Write input CSV
    input_fields = [
        "ws_id_recovered", "actual_wine_id", "expected_wine_id",
        "store_id", "url", "clean_id", "origem_csv", "owner_range",
    ]
    with open(OUT_INPUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=input_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(remaining)

    # Connect
    print(f"[{datetime.now():%H:%M:%S}] Connecting to database...")
    conn = psycopg2.connect(
        DATABASE_URL,
        options="-c statement_timeout=30000",
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    executed = []
    skipped = []

    print(f"[{datetime.now():%H:%M:%S}] Starting execution of {len(remaining)} cases...\n")

    for i, row in enumerate(remaining):
        ws_id = int(row["ws_id_recovered"])
        actual = int(row["actual_wine_id"])
        expected = int(row["expected_wine_id"])
        store_id = int(row["store_id"])
        url = row["url"].strip()
        n = i + 1

        print(f"  [{n:2d}/14] ws_id={ws_id} actual={actual} expected={expected} store={store_id}")

        # CHECK 1: ws_id exists and belongs to actual
        cur.execute("""
            SELECT id, wine_id, store_id, url, preco, moeda, disponivel,
                   descoberto_em, atualizado_em
            FROM wine_sources WHERE id = %s
        """, (ws_id,))
        db_row = cur.fetchone()

        if not db_row:
            reason = f"ws_id={ws_id} no longer exists"
            print(f"         SKIP: {reason}")
            skipped.append({**row, "skip_reason": reason})
            continue

        if db_row["wine_id"] != actual:
            reason = f"ws_id={ws_id} wine_id={db_row['wine_id']} != actual={actual}"
            print(f"         SKIP: {reason}")
            skipped.append({**row, "skip_reason": reason})
            continue

        # CHECK 2: url and store_id match
        if db_row["url"] != url or db_row["store_id"] != store_id:
            reason = f"url/store mismatch db=({db_row['url'][:50]}, {db_row['store_id']}) vs csv=({url[:50]}, {store_id})"
            print(f"         SKIP: {reason}")
            skipped.append({**row, "skip_reason": reason})
            continue

        # CHECK 3: expected wine exists
        cur.execute("SELECT 1 FROM wines WHERE id = %s", (expected,))
        if not cur.fetchone():
            reason = f"expected={expected} no longer exists in wines"
            print(f"         SKIP: {reason}")
            skipped.append({**row, "skip_reason": reason})
            continue

        # CHECK 4: no duplicate on expected
        cur.execute("""
            SELECT 1 FROM wine_sources
            WHERE wine_id = %s AND store_id = %s AND url = %s
        """, (expected, store_id, url))
        if cur.fetchone():
            reason = f"expected={expected} already has (url, store_id={store_id})"
            print(f"         SKIP: {reason}")
            skipped.append({**row, "skip_reason": reason})
            continue

        # EXECUTE UPDATE
        cur.execute("SAVEPOINT sp_%s", (psycopg2.extensions.AsIs(str(i)),))

        cur.execute("""
            UPDATE wine_sources
            SET wine_id = %s
            WHERE id = %s
              AND wine_id = %s
              AND NOT EXISTS (
                  SELECT 1 FROM wine_sources w2
                  WHERE w2.wine_id = %s AND w2.store_id = %s AND w2.url = %s
              )
        """, (expected, ws_id, actual, expected, store_id, url))

        affected = cur.rowcount

        if affected == 1:
            cur.execute("RELEASE SAVEPOINT sp_%s", (psycopg2.extensions.AsIs(str(i)),))
            print(f"         OK: {actual} -> {expected}")
            executed.append({
                "ws_id": ws_id,
                "old_wine_id": actual,
                "new_wine_id": expected,
                "store_id": db_row["store_id"],
                "url": db_row["url"],
                "preco": db_row["preco"],
                "moeda": db_row["moeda"],
                "disponivel": db_row["disponivel"],
                "descoberto_em": db_row["descoberto_em"],
                "atualizado_em": db_row["atualizado_em"],
            })
        else:
            cur.execute("ROLLBACK TO SAVEPOINT sp_%s", (psycopg2.extensions.AsIs(str(i)),))
            reason = f"UPDATE returned {affected} rows"
            print(f"         SKIP: {reason}")
            skipped.append({**row, "skip_reason": reason})

    if executed:
        conn.commit()
        print(f"\n[{datetime.now():%H:%M:%S}] COMMITTED {len(executed)} updates.")
    else:
        conn.rollback()
        print(f"\n[{datetime.now():%H:%M:%S}] No updates to commit.")

    cur.close()
    conn.close()

    # Write revert CSV
    revert_fields = [
        "ws_id", "old_wine_id", "new_wine_id",
        "store_id", "url", "preco", "moeda", "disponivel",
        "descoberto_em", "atualizado_em",
    ]
    with open(OUT_REVERT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=revert_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(executed)
    print(f"  Wrote {OUT_REVERT} ({len(executed)} rows)")

    # Write skipped CSV
    skip_fields = ["ws_id_recovered", "actual_wine_id", "expected_wine_id", "store_id", "url", "skip_reason"]
    with open(OUT_SKIPPED, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=skip_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(skipped)
    print(f"  Wrote {OUT_SKIPPED} ({len(skipped)} rows)")

    print(f"  Wrote {OUT_INPUT} ({len(remaining)} rows)")

    print(f"\n{'='*60}")
    print(f"SUMMARY — RESTANTE 14")
    print(f"{'='*60}")
    print(f"  Candidates:    {len(remaining)}")
    print(f"  All checks OK: {len(executed)}")
    print(f"  Updated:       {len(executed)}")
    print(f"  Skipped:       {len(skipped)}")
    print(f"  Errors:        0")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
