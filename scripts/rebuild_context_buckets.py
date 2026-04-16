"""Rebuild wine_context_buckets for Cascata B (nota_wcf v2).

Idempotent: uses INSERT ... ON CONFLICT DO UPDATE (no truncate, no empty window).
Feeders: only wines with nota_wcf IS NOT NULL and nota_wcf_sample_size > 0.
Never recycles contextual notes as feeder input.

Usage:
    python scripts/rebuild_context_buckets.py
"""

import os
import sys
import statistics
import time

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
K_SHRINKAGE = 20
MIN_DELTA_COHORT = 5
WEIGHT_CAP = 50

# Cascata B tiers
TIERS = [
    ("sub_regiao_tipo", "LOWER(sub_regiao)", "LOWER(tipo)", 10),
    ("regiao_tipo", "LOWER(regiao)", "LOWER(tipo)", 10),
    ("pais_tipo", "LOWER(pais)", "LOWER(tipo)", 10),
    ("vinicola_tipo", "LOWER(produtor)", "LOWER(tipo)", 2),
]


def main():
    t0 = time.time()
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=30,
                            options="-c statement_timeout=600000")
    try:
        buckets = []
        for level, col_a, col_b, min_n in TIERS:
            tier_buckets = _compute_tier(conn, level, col_a, col_b, min_n)
            buckets.extend(tier_buckets)
            print(f"  [{level}] {len(tier_buckets)} buckets", flush=True)

        _upsert_buckets(conn, buckets)

        elapsed = round(time.time() - t0, 1)
        print(f"\nDone: {len(buckets)} buckets upserted in {elapsed}s", flush=True)
    finally:
        conn.close()


def _compute_tier(conn, level, col_a, col_b, min_n):
    """Compute buckets for a single tier of Cascata B."""
    cur = conn.cursor()

    # Fetch grouped feeders
    sql = f"""
        SELECT
            {col_a} || '_' || {col_b} AS bucket_key,
            nota_wcf,
            nota_wcf_sample_size,
            vivino_rating,
            vivino_reviews
        FROM wines
        WHERE nota_wcf IS NOT NULL
          AND nota_wcf_sample_size > 0
          AND {col_a} IS NOT NULL AND {col_a} != ''
          AND {col_b} IS NOT NULL AND {col_b} != ''
          AND suppressed_at IS NULL
        ORDER BY {col_a}, {col_b}
    """
    cur.execute(sql)

    # Group by bucket_key
    from collections import defaultdict
    groups = defaultdict(list)
    for row in cur:
        groups[row[0]].append({
            "nota_wcf": float(row[1]),
            "sample": int(row[2]),
            "vivino_rating": float(row[3]) if row[3] is not None else None,
            "vivino_reviews": int(row[4]) if row[4] is not None else None,
        })

    buckets = []
    for key, feeders in groups.items():
        if len(feeders) < min_n:
            continue

        nota_base = _weighted_mean(feeders)
        stddev = _stddev(feeders)
        delta, delta_n = _calc_delta(feeders, nota_base)

        buckets.append({
            "bucket_level": level,
            "bucket_key": key,
            "bucket_n": len(feeders),
            "nota_base": round(nota_base, 3) if nota_base is not None else None,
            "bucket_stddev": round(stddev, 3) if stddev is not None else None,
            "delta_contextual": round(delta, 3) if delta is not None else None,
            "delta_n": delta_n,
        })

    return buckets


def _weighted_mean(feeders):
    """Weighted mean of nota_wcf with weight = min(sample, 50)."""
    total_w = 0
    total_v = 0
    for f in feeders:
        w = min(f["sample"], WEIGHT_CAP)
        total_w += w
        total_v += w * f["nota_wcf"]
    if total_w == 0:
        return None
    return total_v / total_w


def _stddev(feeders):
    """Standard deviation of nota_wcf."""
    vals = [f["nota_wcf"] for f in feeders]
    if len(vals) < 2:
        return None
    return statistics.stdev(vals)


def _calc_delta(feeders, nota_base):
    """Contextual delta: median of (shrunk_wcf - vivino) for reliable cohort."""
    if nota_base is None:
        return None, 0

    cohort = [f for f in feeders
              if f["vivino_rating"] is not None and f["vivino_rating"] > 0
              and f["sample"] >= 25
              and f["vivino_reviews"] is not None and f["vivino_reviews"] >= 75]

    if len(cohort) < MIN_DELTA_COHORT:
        return None, 0

    deltas = []
    for f in cohort:
        n = f["sample"]
        shrunk = (n / (n + K_SHRINKAGE)) * f["nota_wcf"] + (K_SHRINKAGE / (n + K_SHRINKAGE)) * nota_base
        deltas.append(shrunk - f["vivino_rating"])

    return statistics.median(deltas), len(cohort)


def _upsert_buckets(conn, buckets):
    """Upsert all buckets using INSERT ... ON CONFLICT DO UPDATE (no empty window)."""
    if not buckets:
        print("No buckets to upsert", flush=True)
        return

    cur = conn.cursor()
    sql = """
        INSERT INTO wine_context_buckets
            (bucket_level, bucket_key, bucket_n, nota_base, bucket_stddev,
             delta_contextual, delta_n, updated_at)
        VALUES %s
        ON CONFLICT (bucket_level, bucket_key) DO UPDATE SET
            bucket_n = EXCLUDED.bucket_n,
            nota_base = EXCLUDED.nota_base,
            bucket_stddev = EXCLUDED.bucket_stddev,
            delta_contextual = EXCLUDED.delta_contextual,
            delta_n = EXCLUDED.delta_n,
            updated_at = NOW()
    """
    rows = [(b["bucket_level"], b["bucket_key"], b["bucket_n"],
             b["nota_base"], b["bucket_stddev"],
             b["delta_contextual"], b["delta_n"])
            for b in buckets]

    template = "(%s, %s, %s, %s, %s, %s, %s, NOW())"
    execute_values(cur, sql, rows, template=template, page_size=500)
    conn.commit()
    print(f"  Upserted {len(rows)} buckets", flush=True)


if __name__ == "__main__":
    print("Rebuilding wine_context_buckets...", flush=True)
    main()
