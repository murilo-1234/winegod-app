#!/usr/bin/env python3
"""
Triage READ-ONLY dos 606 incomplete da Classe B wrong_owner.

Para cada caso, tenta recuperar o ws_id no estado atual do banco.
Classifica cada linha em:
  - recoverable_safe
  - ambiguous
  - stale_or_already_fixed
  - unresolved_incomplete

ZERO writes no banco. Apenas SELECT.
"""

import csv
import json
import os
import sys
from datetime import datetime

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

import psycopg2
import psycopg2.extras

# ---------- config ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete.csv")

OUT_AUDIT     = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_input_audit.csv")
OUT_SAFE      = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_recoverable_safe.csv")
OUT_AMBIGUOUS = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_ambiguous.csv")
OUT_STALE     = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_stale.csv")
OUT_UNRESOLVED= os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_unresolved.csv")
OUT_STATS     = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_stats.json")

# Load DATABASE_URL from backend/.env
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
    print("ERROR: DATABASE_URL not found in backend/.env")
    sys.exit(1)


def get_connection():
    return psycopg2.connect(
        DATABASE_URL,
        options="-c statement_timeout=60000 -c default_transaction_read_only=on",
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )


def load_incomplete():
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def triage_one(cur, row):
    """
    Triage a single incomplete case. Returns (classification, ws_id_or_none, reason).
    """
    actual = int(row["actual_wine_id"])
    expected = int(row["expected_wine_id"])
    store_id = int(row["store_id"])
    url = row["url"].strip()

    # ------------------------------------------------------------------
    # Step 1: Find candidate ws rows on the ACTUAL owner with same (url, store_id)
    # ------------------------------------------------------------------
    cur.execute("""
        SELECT id, wine_id, url, store_id
        FROM wine_sources
        WHERE url = %s AND store_id = %s AND wine_id = %s
    """, (url, store_id, actual))
    candidates_actual = cur.fetchall()

    # ------------------------------------------------------------------
    # Step 2: Check if the row already moved to expected (stale/fixed)
    # ------------------------------------------------------------------
    cur.execute("""
        SELECT id, wine_id, url, store_id
        FROM wine_sources
        WHERE url = %s AND store_id = %s AND wine_id = %s
    """, (url, store_id, expected))
    candidates_expected = cur.fetchall()

    # ------------------------------------------------------------------
    # Step 3: Check if the row exists on ANY owner (might be a third owner)
    # ------------------------------------------------------------------
    if not candidates_actual and not candidates_expected:
        cur.execute("""
            SELECT id, wine_id, url, store_id
            FROM wine_sources
            WHERE url = %s AND store_id = %s
        """, (url, store_id))
        candidates_any = cur.fetchall()
    else:
        candidates_any = []

    # ------------------------------------------------------------------
    # Step 4: Check expected wine still exists
    # ------------------------------------------------------------------
    cur.execute("SELECT 1 FROM wines WHERE id = %s", (expected,))
    expected_exists = cur.fetchone() is not None

    # ------------------------------------------------------------------
    # Classification logic
    # ------------------------------------------------------------------

    # Case A: Row already on expected owner => stale_or_already_fixed
    if candidates_expected:
        ws_id = candidates_expected[0]["id"]
        return ("stale_or_already_fixed", ws_id,
                f"row already on expected_wine_id={expected}; ws_id={ws_id}")

    # Case B: Row gone from actual AND not on expected AND not anywhere
    if not candidates_actual and not candidates_expected and not candidates_any:
        return ("stale_or_already_fixed", None,
                f"row with (url, store_id={store_id}) no longer exists in wine_sources; likely deleted in Classe A cleanup")

    # Case C: Row exists on actual, exactly 1 candidate
    if len(candidates_actual) == 1:
        ws_id = candidates_actual[0]["id"]

        # Check expected wine still exists
        if not expected_exists:
            return ("unresolved_incomplete", ws_id,
                    f"ws_id={ws_id} found on actual={actual}, but expected={expected} no longer exists in wines table")

        # Check no duplicate would be created on expected
        # (already checked above: candidates_expected is empty at this point)

        return ("recoverable_safe", ws_id,
                f"exactly 1 candidate ws_id={ws_id} on actual={actual}; "
                f"expected={expected} exists and has no (url, store_id) conflict")

    # Case D: Multiple candidates on actual
    if len(candidates_actual) > 1:
        ws_ids = [c["id"] for c in candidates_actual]
        return ("ambiguous", None,
                f"multiple ws_ids {ws_ids} on actual={actual} with same (url, store_id={store_id}); "
                f"cannot determine which one to move")

    # Case E: Not on actual but found on a THIRD owner
    if candidates_any:
        third_owners = [(c["id"], c["wine_id"]) for c in candidates_any]
        return ("stale_or_already_fixed", None,
                f"row no longer on actual={actual} nor expected={expected}; "
                f"found on third owner(s): {third_owners}; state changed")

    # Fallback: should not reach here
    return ("unresolved_incomplete", None,
            f"unexpected state: no candidates found for (url={url}, store_id={store_id})")


def main():
    print(f"[{datetime.now():%H:%M:%S}] Loading {INPUT_CSV} ...")
    rows = load_incomplete()
    print(f"  Loaded {len(rows)} incomplete cases")

    print(f"[{datetime.now():%H:%M:%S}] Connecting to database (READ-ONLY) ...")
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Verify read-only
    try:
        cur.execute("CREATE TEMP TABLE _readonly_test (x int)")
        print("WARNING: read-only mode not enforced! Aborting.")
        conn.rollback()
        sys.exit(1)
    except psycopg2.errors.ReadOnlySqlTransaction:
        conn.rollback()
        print("  Read-only mode confirmed.")

    results = []
    counters = {
        "recoverable_safe": 0,
        "ambiguous": 0,
        "stale_or_already_fixed": 0,
        "unresolved_incomplete": 0,
        "error": 0,
    }

    print(f"[{datetime.now():%H:%M:%S}] Starting triage of {len(rows)} cases ...")
    for i, row in enumerate(rows):
        try:
            classification, ws_id, reason = triage_one(cur, row)
            counters[classification] += 1
            results.append({
                **row,
                "ws_id_recovered": ws_id if ws_id else "",
                "triage_class": classification,
                "triage_reason": reason,
            })
        except Exception as e:
            conn.rollback()
            counters["error"] += 1
            results.append({
                **row,
                "ws_id_recovered": "",
                "triage_class": "error",
                "triage_reason": str(e),
            })

        if (i + 1) % 100 == 0:
            print(f"  ... {i+1}/{len(rows)} processed | "
                  f"safe={counters['recoverable_safe']} "
                  f"ambig={counters['ambiguous']} "
                  f"stale={counters['stale_or_already_fixed']} "
                  f"unresolved={counters['unresolved_incomplete']} "
                  f"err={counters['error']}")

    cur.close()
    conn.close()

    print(f"\n[{datetime.now():%H:%M:%S}] Triage complete.")
    print(f"  recoverable_safe:       {counters['recoverable_safe']}")
    print(f"  ambiguous:              {counters['ambiguous']}")
    print(f"  stale_or_already_fixed: {counters['stale_or_already_fixed']}")
    print(f"  unresolved_incomplete:  {counters['unresolved_incomplete']}")
    print(f"  errors:                 {counters['error']}")

    # ------------------------------------------------------------------
    # Write output CSVs
    # ------------------------------------------------------------------
    audit_fields = [
        "actual_wine_id", "expected_wine_id", "store_id", "url",
        "clean_id", "origem_csv", "owner_range",
        "ws_id_recovered", "triage_class", "triage_reason",
    ]

    safe_fields = [
        "ws_id_recovered", "actual_wine_id", "expected_wine_id",
        "store_id", "url", "clean_id", "origem_csv", "owner_range",
        "triage_reason",
    ]

    ambig_fields = [
        "actual_wine_id", "expected_wine_id", "store_id", "url",
        "clean_id", "ws_id_recovered", "triage_reason",
    ]

    stale_fields = [
        "actual_wine_id", "expected_wine_id", "store_id", "url",
        "clean_id", "ws_id_recovered", "triage_reason",
    ]

    unresolved_fields = [
        "actual_wine_id", "expected_wine_id", "store_id", "url",
        "clean_id", "ws_id_recovered", "triage_reason",
    ]

    def write_csv(path, fieldnames, filter_class):
        filtered = [r for r in results if r["triage_class"] == filter_class]
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(filtered)
        print(f"  Wrote {path} ({len(filtered)} rows)")

    # Full audit
    with open(OUT_AUDIT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=audit_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    print(f"  Wrote {OUT_AUDIT} ({len(results)} rows)")

    write_csv(OUT_SAFE, safe_fields, "recoverable_safe")
    write_csv(OUT_AMBIGUOUS, ambig_fields, "ambiguous")
    write_csv(OUT_STALE, stale_fields, "stale_or_already_fixed")
    write_csv(OUT_UNRESOLVED, unresolved_fields, "unresolved_incomplete")

    # Stats JSON
    stats = {
        "timestamp": datetime.now().isoformat(),
        "input_file": INPUT_CSV,
        "total_input": len(rows),
        "results": counters,
        "output_files": {
            "audit": OUT_AUDIT,
            "recoverable_safe": OUT_SAFE,
            "ambiguous": OUT_AMBIGUOUS,
            "stale_or_already_fixed": OUT_STALE,
            "unresolved_incomplete": OUT_UNRESOLVED,
        },
    }
    with open(OUT_STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"  Wrote {OUT_STATS}")

    print(f"\n[{datetime.now():%H:%M:%S}] Done.")


if __name__ == "__main__":
    main()
