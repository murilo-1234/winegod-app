"""
calc_wcf.py — Atualiza nota_wcf, confianca_nota e nota_wcf_sample_size no Render.
Lê wcf_results.csv (gerado a partir do vivino_db local) e faz UPDATE em lotes.
"""

import csv
import os
import sys
import psycopg2
from psycopg2.extras import execute_values

RENDER_URL = os.environ.get("DATABASE_URL")
if not RENDER_URL:
    sys.exit("ERROR: DATABASE_URL environment variable is required.")

CSV_PATH = os.path.join(os.path.dirname(__file__), "wcf_results.csv")
BATCH_SIZE = 50000


def confianca(total_reviews):
    if total_reviews >= 100:
        return 1.0
    if total_reviews >= 50:
        return 0.8
    if total_reviews >= 25:
        return 0.6
    if total_reviews >= 10:
        return 0.4
    return 0.2


def load_csv():
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(
                (
                    float(r["nota_wcf"]),
                    int(r["total_reviews_wcf"]),
                    int(r["vinho_id"]),
                )
            )
    return rows


def update_render(rows):
    conn = psycopg2.connect(RENDER_URL)
    conn.autocommit = False
    cur = conn.cursor()

    updated = 0
    total = len(rows)

    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        # Build values list for batch update
        values = []
        for nota_wcf, total_reviews, vinho_id in batch:
            values.append(
                (nota_wcf, confianca(total_reviews), total_reviews, vinho_id)
            )

        # Use a temp table approach for efficient batch update
        cur.execute("""
            CREATE TEMP TABLE IF NOT EXISTS _wcf_batch (
                nota_wcf NUMERIC(3,2),
                confianca_nota NUMERIC(3,2),
                nota_wcf_sample_size INTEGER,
                vivino_id INTEGER
            ) ON COMMIT DELETE ROWS;
        """)
        cur.execute("TRUNCATE _wcf_batch;")

        execute_values(
            cur,
            "INSERT INTO _wcf_batch (nota_wcf, confianca_nota, nota_wcf_sample_size, vivino_id) VALUES %s",
            values,
        )

        cur.execute("""
            UPDATE wines w
            SET nota_wcf = b.nota_wcf,
                confianca_nota = b.confianca_nota,
                nota_wcf_sample_size = b.nota_wcf_sample_size
            FROM _wcf_batch b
            WHERE w.vivino_id = b.vivino_id;
        """)

        matched = cur.rowcount
        updated += matched
        conn.commit()

        if (i // BATCH_SIZE) % 100 == 0:
            pct = round(i / total * 100, 1)
            print(f"  {pct}% — {updated:,} atualizados de {i + len(batch):,} processados")

    print(f"\nFinalizado: {updated:,} vinhos atualizados no Render (de {total:,} no CSV)")
    cur.close()
    conn.close()
    return updated


def main():
    print("1. Carregando CSV...")
    rows = load_csv()
    print(f"   {len(rows):,} vinhos no CSV")

    print("2. Atualizando Render...")
    updated = update_render(rows)

    print(f"\n=== RESULTADO ===")
    print(f"Vinhos no CSV:       {len(rows):,}")
    print(f"Vinhos atualizados:  {updated:,}")


if __name__ == "__main__":
    main()
