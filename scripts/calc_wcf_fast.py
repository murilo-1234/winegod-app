"""
calc_wcf_fast.py — Bulk update nota_wcf no Render via COPY + single UPDATE.
Much faster than row-by-row batches.
"""

import csv
import io
import os
import sys
import psycopg2

RENDER_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod",
)

CSV_PATH = os.path.join(os.path.dirname(__file__), "wcf_results.csv")


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


def score_type(total_reviews):
    if total_reviews >= 100:
        return "verified"
    return "estimated"


def main():
    print("1. Preparando dados do CSV...", flush=True)

    # Build in-memory TSV with computed columns
    buf = io.StringIO()
    count = 0
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            vinho_id = int(r["vinho_id"])
            nota_wcf = float(r["nota_wcf"])
            total_rev = int(r["total_reviews_wcf"])
            conf = confianca(total_rev)
            stype = score_type(total_rev)
            buf.write(f"{vinho_id}\t{nota_wcf}\t{conf}\t{stype}\n")
            count += 1

    print(f"   {count:,} linhas preparadas", flush=True)

    print("2. Conectando ao Render...", flush=True)
    conn = psycopg2.connect(RENDER_URL)
    cur = conn.cursor()

    print("3. Criando tabela temporaria...", flush=True)
    cur.execute("DROP TABLE IF EXISTS _wcf_bulk;")
    cur.execute("""
        CREATE TABLE _wcf_bulk (
            vivino_id INTEGER,
            nota_wcf NUMERIC(3,2),
            confianca_nota NUMERIC(3,2),
            winegod_score_type VARCHAR(20)
        );
    """)
    conn.commit()

    print("4. COPY bulk load...", flush=True)
    buf.seek(0)
    cur.copy_from(buf, "_wcf_bulk", sep="\t", columns=("vivino_id", "nota_wcf", "confianca_nota", "winegod_score_type"))
    conn.commit()

    cur.execute("SELECT count(*) FROM _wcf_bulk;")
    loaded = cur.fetchone()[0]
    print(f"   {loaded:,} linhas carregadas na tabela temporaria", flush=True)

    print("5. Criando indice na temp table...", flush=True)
    cur.execute("CREATE INDEX idx_wcf_bulk_vid ON _wcf_bulk(vivino_id);")
    conn.commit()

    print("6. UPDATE wines (single query)...", flush=True)
    cur.execute("""
        UPDATE wines w
        SET nota_wcf = b.nota_wcf,
            confianca_nota = b.confianca_nota,
            winegod_score_type = b.winegod_score_type
        FROM _wcf_bulk b
        WHERE w.vivino_id = b.vivino_id;
    """)
    updated = cur.rowcount
    conn.commit()
    print(f"   {updated:,} vinhos atualizados", flush=True)

    print("7. Limpando tabela temporaria...", flush=True)
    cur.execute("DROP TABLE _wcf_bulk;")
    conn.commit()

    cur.close()
    conn.close()

    print(f"\n=== RESULTADO ===", flush=True)
    print(f"Vinhos no CSV:       {count:,}", flush=True)
    print(f"Vinhos atualizados:  {updated:,}", flush=True)


if __name__ == "__main__":
    main()
