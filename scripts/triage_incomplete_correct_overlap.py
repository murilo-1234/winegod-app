#!/usr/bin/env python3
"""
Post-correction: remove 36 overlap cases from recoverable_safe
and reclassify them as stale_or_already_fixed.

Then regenerate all output CSVs and stats.
"""

import csv
import json
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

AUDIT_CSV = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_input_audit.csv")
OUT_SAFE = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_recoverable_safe.csv")
OUT_AMBIGUOUS = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_ambiguous.csv")
OUT_STALE = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_stale.csv")
OUT_UNRESOLVED = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_unresolved.csv")
OUT_STATS = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete_stats.json")
SAFE_CSV = os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_safe.csv")

# The 36 ws_ids that overlap with already-executed Classe B safe
OVERLAP_WS_IDS = {
    "3496354", "3509932", "5932110", "3528150", "3891879", "3520070",
    "5893327", "3892199", "3519289", "3509937", "3505188", "3509933",
    "3779951", "3507391", "3504054", "3511744", "3509934", "3511075",
    "3504058", "3504856", "3509938", "3508058", "3570989", "3567259",
    "3891772", "5386938", "3507388", "3815361", "3711117", "3832578",
    "3509517", "3752293", "3890624", "3511076", "3749412", "3571608",
}


def main():
    # Load audit CSV
    with open(AUDIT_CSV, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"Loaded {len(rows)} audit rows")

    # Reclassify overlap cases
    reclassified = 0
    for r in rows:
        ws_id = r.get("ws_id_recovered", "").strip()
        if ws_id in OVERLAP_WS_IDS and r["triage_class"] == "recoverable_safe":
            r["triage_class"] = "stale_or_already_fixed"
            r["triage_reason"] = (
                f"RECLASSIFIED: ws_id={ws_id} already correctly moved by Classe B safe execution; "
                f"pilot_candidates had actual/expected inverted"
            )
            reclassified += 1

    print(f"Reclassified {reclassified} overlap cases from recoverable_safe -> stale_or_already_fixed")

    # Count
    counters = {}
    for r in rows:
        c = r["triage_class"]
        counters[c] = counters.get(c, 0) + 1

    print(f"Final counts:")
    for k, v in sorted(counters.items()):
        print(f"  {k}: {v}")

    # Rewrite audit
    audit_fields = list(rows[0].keys())
    with open(AUDIT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=audit_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"Rewrote {AUDIT_CSV}")

    # Rewrite safe
    safe_fields = [
        "ws_id_recovered", "actual_wine_id", "expected_wine_id",
        "store_id", "url", "clean_id", "origem_csv", "owner_range",
        "triage_reason",
    ]
    safe_rows = [r for r in rows if r["triage_class"] == "recoverable_safe"]
    with open(OUT_SAFE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=safe_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(safe_rows)
    print(f"Wrote {OUT_SAFE} ({len(safe_rows)} rows)")

    # Rewrite stale
    stale_fields = [
        "actual_wine_id", "expected_wine_id", "store_id", "url",
        "clean_id", "ws_id_recovered", "triage_reason",
    ]
    stale_rows = [r for r in rows if r["triage_class"] == "stale_or_already_fixed"]
    with open(OUT_STALE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=stale_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(stale_rows)
    print(f"Wrote {OUT_STALE} ({len(stale_rows)} rows)")

    # Rewrite ambiguous (should be 0)
    ambig_fields = [
        "actual_wine_id", "expected_wine_id", "store_id", "url",
        "clean_id", "ws_id_recovered", "triage_reason",
    ]
    ambig_rows = [r for r in rows if r["triage_class"] == "ambiguous"]
    with open(OUT_AMBIGUOUS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ambig_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(ambig_rows)
    print(f"Wrote {OUT_AMBIGUOUS} ({len(ambig_rows)} rows)")

    # Rewrite unresolved (should be 0)
    unresolved_fields = [
        "actual_wine_id", "expected_wine_id", "store_id", "url",
        "clean_id", "ws_id_recovered", "triage_reason",
    ]
    unresolved_rows = [r for r in rows if r["triage_class"] == "unresolved_incomplete"]
    with open(OUT_UNRESOLVED, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=unresolved_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(unresolved_rows)
    print(f"Wrote {OUT_UNRESOLVED} ({len(unresolved_rows)} rows)")

    # Rewrite stats
    stats = {
        "timestamp": datetime.now().isoformat(),
        "input_file": os.path.join(SCRIPT_DIR, "wrong_owner_move_needed_incomplete.csv"),
        "total_input": len(rows),
        "results": counters,
        "correction_applied": {
            "description": "36 ws_ids overlapping with already-executed Classe B safe were reclassified from recoverable_safe to stale_or_already_fixed",
            "reason": "pilot_candidates had actual/expected inverted for these 36 cases; Classe B safe execution already moved them in the correct direction",
            "reclassified_count": reclassified,
            "overlap_ws_ids": sorted(OVERLAP_WS_IDS),
        },
        "output_files": {
            "audit": AUDIT_CSV,
            "recoverable_safe": OUT_SAFE,
            "ambiguous": OUT_AMBIGUOUS,
            "stale_or_already_fixed": OUT_STALE,
            "unresolved_incomplete": OUT_UNRESOLVED,
        },
    }
    with open(OUT_STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"Wrote {OUT_STATS}")

    print("\nDone.")


if __name__ == "__main__":
    main()
