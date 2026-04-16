"""Validate note_v2 engine against real wines from the database.

Read-only: no writes to the database.
Compares v2 output against legacy logic side by side.

Usage:
    python scripts/validate_note_v2.py
"""

import os
import sys
import psycopg2
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from services.note_v2 import resolve_note_v2, BucketCache
from services.display import _resolve_note_legacy

DATABASE_URL = os.environ["DATABASE_URL"]

SAMPLE_QUERIES = {
    "309k_verified": """
        SELECT id, nome, vivino_rating, vivino_reviews, nota_wcf, nota_wcf_sample_size,
               confianca_nota, pais, pais_nome, regiao, sub_regiao, tipo, produtor
        FROM wines TABLESAMPLE SYSTEM(5)
        WHERE vivino_reviews >= 75
          AND (nota_wcf_sample_size IS NULL OR nota_wcf_sample_size < 25)
          AND vivino_rating > 0
          AND suppressed_at IS NULL
        LIMIT 50
    """,
    "wcf_robust": """
        SELECT id, nome, vivino_rating, vivino_reviews, nota_wcf, nota_wcf_sample_size,
               confianca_nota, pais, pais_nome, regiao, sub_regiao, tipo, produtor
        FROM wines TABLESAMPLE SYSTEM(5)
        WHERE nota_wcf_sample_size >= 50
          AND vivino_rating > 0
          AND suppressed_at IS NULL
        LIMIT 50
    """,
    "no_vivino_with_wcf": """
        SELECT id, nome, vivino_rating, vivino_reviews, nota_wcf, nota_wcf_sample_size,
               confianca_nota, pais, pais_nome, regiao, sub_regiao, tipo, produtor
        FROM wines TABLESAMPLE SYSTEM(5)
        WHERE vivino_rating IS NULL
          AND nota_wcf IS NOT NULL
          AND nota_wcf_sample_size > 0
          AND suppressed_at IS NULL
        LIMIT 50
    """,
    "estimated_25_74": """
        SELECT id, nome, vivino_rating, vivino_reviews, nota_wcf, nota_wcf_sample_size,
               confianca_nota, pais, pais_nome, regiao, sub_regiao, tipo, produtor
        FROM wines TABLESAMPLE SYSTEM(5)
        WHERE vivino_reviews >= 25 AND vivino_reviews < 75
          AND vivino_rating > 0
          AND suppressed_at IS NULL
        LIMIT 50
    """,
    "no_data": """
        SELECT id, nome, vivino_rating, vivino_reviews, nota_wcf, nota_wcf_sample_size,
               confianca_nota, pais, pais_nome, regiao, sub_regiao, tipo, produtor
        FROM wines TABLESAMPLE SYSTEM(1)
        WHERE vivino_rating IS NULL
          AND nota_wcf IS NULL
          AND suppressed_at IS NULL
        LIMIT 50
    """,
}

COLS = ["id", "nome", "vivino_rating", "vivino_reviews", "nota_wcf", "nota_wcf_sample_size",
        "confianca_nota", "pais", "pais_nome", "regiao", "sub_regiao", "tipo", "produtor"]


def main():
    # Load bucket cache
    cache = BucketCache()
    cache.load()
    print(f"BucketCache: {cache.size} buckets loaded\n")

    conn = psycopg2.connect(DATABASE_URL, connect_timeout=30,
                            options="-c statement_timeout=120000")
    try:
        all_type_counts = Counter()
        all_source_counts = Counter()
        deltas = []

        for scenario, sql in SAMPLE_QUERIES.items():
            print(f"=== {scenario} ===")
            cur = conn.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            print(f"  Fetched: {len(rows)} wines")

            type_counts = Counter()
            source_counts = Counter()

            for row in rows:
                wine = dict(zip(COLS, [float(v) if isinstance(v, __import__('decimal').Decimal) else v for v in row]))

                # v2
                v2 = resolve_note_v2(wine, bucket_lookup_fn=cache.lookup)

                # legacy
                legacy = _resolve_note_legacy(
                    wine.get("nota_wcf"), wine.get("vivino_rating"),
                    wine.get("nota_wcf_sample_size"), wine.get("confianca_nota")
                )

                type_counts[v2["display_note_type"]] += 1
                source_counts[v2["display_note_source"]] += 1
                all_type_counts[v2["display_note_type"]] += 1
                all_source_counts[v2["display_note_source"]] += 1

                # Track delta
                v2_note = v2["display_note"]
                leg_note = legacy["display_note"]
                if v2_note is not None and leg_note is not None:
                    delta = abs(v2_note - leg_note)
                    if delta > 0.01:
                        deltas.append({
                            "id": wine["id"],
                            "scenario": scenario,
                            "v2_note": v2_note,
                            "legacy_note": leg_note,
                            "delta": round(delta, 3),
                            "v2_type": v2["display_note_type"],
                            "v2_source": v2["display_note_source"],
                            "legacy_type": legacy["display_note_type"],
                        })

            print(f"  Types: {dict(type_counts)}")
            print(f"  Sources: {dict(source_counts)}")
            print()

        print("=== SUMMARY ===")
        print(f"Overall type distribution: {dict(all_type_counts)}")
        print(f"Overall source distribution: {dict(all_source_counts)}")
        print(f"Wines with note delta > 0.01: {len(deltas)}")

        if deltas:
            deltas.sort(key=lambda d: d["delta"], reverse=True)
            print(f"\nTop 10 largest deltas (v2 vs legacy):")
            for d in deltas[:10]:
                print(f"  id={d['id']} scenario={d['scenario']} "
                      f"v2={d['v2_note']} legacy={d['legacy_note']} "
                      f"delta={d['delta']} "
                      f"v2_src={d['v2_source']} leg_type={d['legacy_type']}")

        # Integrity check (use sample to avoid timeout on Render)
        print("\n=== INTEGRITY ===")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM wines TABLESAMPLE SYSTEM(1) WHERE vivino_reviews > 500")
        sample_count = cur.fetchone()[0]
        print(f"Wines with vivino_reviews > 500 in 1% sample: {sample_count} (extrapolated ~{sample_count * 100})")

    finally:
        conn.close()

    print("\nValidation complete.")


if __name__ == "__main__":
    main()
