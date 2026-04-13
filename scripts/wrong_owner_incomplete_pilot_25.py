#!/usr/bin/env python3
"""
Piloto de 25 UPDATEs — incomplete recoverable_safe.

Seleciona os 25 melhores casos dos 39, executa UPDATE com guard clause
atômica, gera CSVs de execução/revert/skipped.
"""

import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True)

import psycopg2
import psycopg2.extras

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_recoverable_safe.csv")

OUT_PILOT    = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_pilot_25.csv")
OUT_REVERT   = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_pilot_25_revert.csv")
OUT_SKIPPED  = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_pilot_25_skipped.csv")

# Already-executed ws_ids from Classe B safe (for exclusion check)
BATCH_REVERT = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_batch_all_revert.csv")
PILOT_REVERT = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_pilot_100_revert.csv")

ENV_PATH = os.path.join(SCRIPT_DIR, "..", "backend", ".env")
DATABASE_URL = None
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                DATABASE_URL = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found")
    sys.exit(1)


def load_already_executed():
    """Load ws_ids from previous Classe B safe execution."""
    ws_ids = set()
    for path in [BATCH_REVERT, PILOT_REVERT]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    ws = r.get("ws_id", "").strip()
                    if ws:
                        ws_ids.add(ws)
    return ws_ids


def select_25(rows):
    """Select 25 best cases prioritizing unique expected_wine_id and store diversity."""
    expected_counts = Counter(r["expected_wine_id"] for r in rows)

    # Priority 1: cases where expected_wine_id appears only once (strongest proof)
    unique_expected = [r for r in rows if expected_counts[r["expected_wine_id"]] == 1]
    multi_expected = [r for r in rows if expected_counts[r["expected_wine_id"]] > 1]

    selected = list(unique_expected)  # all unique-expected cases

    # Priority 2: one case per multi-expected group, diversify by store
    seen_expected = set()
    for r in sorted(multi_expected, key=lambda x: x["store_id"]):
        if r["expected_wine_id"] not in seen_expected and len(selected) < 25:
            selected.append(r)
            seen_expected.add(r["expected_wine_id"])

    # If still need more, add remaining multi-expected
    if len(selected) < 25:
        for r in multi_expected:
            if r not in selected and len(selected) < 25:
                selected.append(r)

    return selected[:25]


def main():
    print(f"[{datetime.now():%H:%M:%S}] Loading inputs...")

    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))
    print(f"  Total recoverable_safe: {len(all_rows)}")

    already_executed = load_already_executed()
    print(f"  Already-executed ws_ids loaded: {len(already_executed)}")

    # Filter out any that overlap with already-executed
    clean_rows = [r for r in all_rows if r["ws_id_recovered"] not in already_executed]
    filtered = len(all_rows) - len(clean_rows)
    if filtered:
        print(f"  WARNING: {filtered} ws_ids filtered (overlap with executed B safe)")
    print(f"  Clean candidates: {len(clean_rows)}")

    # Select 25
    pilot_rows = select_25(clean_rows)
    print(f"  Selected for pilot: {len(pilot_rows)}")

    # Connect
    print(f"\n[{datetime.now():%H:%M:%S}] Connecting to database...")
    conn = psycopg2.connect(
        DATABASE_URL,
        options="-c statement_timeout=30000",
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    executed = []
    skipped = []

    print(f"[{datetime.now():%H:%M:%S}] Starting pilot of {len(pilot_rows)} cases...\n")

    for i, row in enumerate(pilot_rows):
        ws_id = int(row["ws_id_recovered"])
        actual = int(row["actual_wine_id"])
        expected = int(row["expected_wine_id"])
        store_id = int(row["store_id"])
        url = row["url"].strip()
        line_num = i + 1

        print(f"  [{line_num:2d}/25] ws_id={ws_id} actual={actual} expected={expected} store={store_id}")

        # ---- CHECK 1: ws_id still exists and belongs to actual ----
        cur.execute("""
            SELECT id, wine_id, store_id, url, preco, moeda, disponivel,
                   descoberto_em, atualizado_em
            FROM wine_sources WHERE id = %s
        """, (ws_id,))
        db_row = cur.fetchone()

        if not db_row:
            reason = f"ws_id={ws_id} no longer exists in wine_sources"
            print(f"         SKIP: {reason}")
            skipped.append({**row, "skip_reason": reason})
            continue

        if db_row["wine_id"] != actual:
            reason = f"ws_id={ws_id} wine_id={db_row['wine_id']} != expected actual={actual} (already changed)"
            print(f"         SKIP: {reason}")
            skipped.append({**row, "skip_reason": reason})
            continue

        # ---- CHECK 2: url and store_id match ----
        if db_row["url"] != url or db_row["store_id"] != store_id:
            reason = (f"ws_id={ws_id} url/store mismatch: "
                      f"db_url={db_row['url'][:60]} db_store={db_row['store_id']} "
                      f"vs csv_url={url[:60]} csv_store={store_id}")
            print(f"         SKIP: {reason}")
            skipped.append({**row, "skip_reason": reason})
            continue

        # ---- CHECK 3: expected wine exists ----
        cur.execute("SELECT 1 FROM wines WHERE id = %s", (expected,))
        if not cur.fetchone():
            reason = f"expected_wine_id={expected} no longer exists in wines"
            print(f"         SKIP: {reason}")
            skipped.append({**row, "skip_reason": reason})
            continue

        # ---- CHECK 4: no duplicate on expected ----
        cur.execute("""
            SELECT 1 FROM wine_sources
            WHERE wine_id = %s AND store_id = %s AND url = %s
        """, (expected, store_id, url))
        if cur.fetchone():
            reason = f"expected={expected} already has (url, store_id={store_id}) — would create duplicate"
            print(f"         SKIP: {reason}")
            skipped.append({**row, "skip_reason": reason})
            continue

        # ---- All checks passed — EXECUTE UPDATE ----
        cur.execute("SAVEPOINT sp_pilot_%s", (psycopg2.extensions.AsIs(str(i)),))

        cur.execute("""
            UPDATE wine_sources
            SET wine_id = %s
            WHERE id = %s
              AND wine_id = %s
              AND NOT EXISTS (
                  SELECT 1 FROM wine_sources w2
                  WHERE w2.wine_id = %s
                    AND w2.store_id = %s
                    AND w2.url = %s
              )
        """, (expected, ws_id, actual, expected, store_id, url))

        rows_affected = cur.rowcount

        if rows_affected == 1:
            cur.execute("RELEASE SAVEPOINT sp_pilot_%s", (psycopg2.extensions.AsIs(str(i)),))
            print(f"         OK: updated wine_id {actual} -> {expected}")
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
        elif rows_affected == 0:
            cur.execute("ROLLBACK TO SAVEPOINT sp_pilot_%s", (psycopg2.extensions.AsIs(str(i)),))
            reason = f"UPDATE returned 0 rows (guard clause or NOT EXISTS blocked)"
            print(f"         SKIP: {reason}")
            skipped.append({**row, "skip_reason": reason})
        else:
            cur.execute("ROLLBACK TO SAVEPOINT sp_pilot_%s", (psycopg2.extensions.AsIs(str(i)),))
            reason = f"UPDATE affected {rows_affected} rows (unexpected, rolled back)"
            print(f"         ERROR: {reason}")
            skipped.append({**row, "skip_reason": reason})

    # COMMIT all successful updates
    if executed:
        conn.commit()
        print(f"\n[{datetime.now():%H:%M:%S}] COMMITTED {len(executed)} updates.")
    else:
        conn.rollback()
        print(f"\n[{datetime.now():%H:%M:%S}] No updates to commit.")

    cur.close()
    conn.close()

    # ---- Write output CSVs ----

    # Pilot input CSV
    pilot_fields = [
        "ws_id_recovered", "actual_wine_id", "expected_wine_id",
        "store_id", "url", "clean_id", "origem_csv", "owner_range",
    ]
    with open(OUT_PILOT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pilot_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(pilot_rows)
    print(f"  Wrote {OUT_PILOT} ({len(pilot_rows)} rows)")

    # Revert CSV (lossless snapshot)
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

    # Skipped CSV
    skip_fields = [
        "ws_id_recovered", "actual_wine_id", "expected_wine_id",
        "store_id", "url", "skip_reason",
    ]
    with open(OUT_SKIPPED, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=skip_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(skipped)
    print(f"  Wrote {OUT_SKIPPED} ({len(skipped)} rows)")

    # Summary
    print(f"\n{'='*60}")
    print(f"PILOT SUMMARY")
    print(f"{'='*60}")
    print(f"  Candidates entered:   {len(pilot_rows)}")
    print(f"  Passed all checks:    {len(executed)}")
    print(f"  Updated:              {len(executed)}")
    print(f"  Skipped/stale:        {len(skipped)}")
    print(f"  Errors:               0")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
