"""
upload_wcf_render.py — Upload WCF para o Render em lotes de 10K.
Cada lote faz COMMIT. Se cair no meio, roda de novo (idempotente).

USO (PowerShell):
  cd C:\winegod-app\scripts
  python upload_wcf_render.py
"""

import csv
import os
import sys
import time
import psycopg2
from psycopg2.extras import execute_values

# Carrega DATABASE_URL do .env
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", ".env")
RENDER_URL = None
with open(ENV_PATH, encoding="utf-8") as f:
    for line in f:
        if line.startswith("DATABASE_URL="):
            RENDER_URL = line.strip().split("=", 1)[1]
            break

if not RENDER_URL:
    sys.exit("ERRO: DATABASE_URL nao encontrada em backend/.env")

CSV_PATH = os.path.join(os.path.dirname(__file__), "wcf_results.csv")
BATCH = 10000


def confianca(n):
    if n >= 100: return 1.0
    if n >= 50:  return 0.8
    if n >= 25:  return 0.6
    if n >= 10:  return 0.4
    return 0.2


def score_type(n):
    if n >= 100: return "verified"
    if n >= 1:   return "estimated"
    return "none"


def main():
    print("=" * 60, flush=True)
    print("  UPLOAD WCF -> RENDER (lotes de 10K, com COMMIT)", flush=True)
    print("=" * 60, flush=True)

    print("\n1. Carregando CSV...", flush=True)
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((
                float(r["nota_wcf"]),
                int(r["total_reviews_wcf"]),
                int(r["vinho_id"]),
            ))
    print(f"   {len(rows):,} vinhos no CSV", flush=True)

    print("\n2. Conectando ao Render...", flush=True)
    conn = psycopg2.connect(RENDER_URL)
    conn.autocommit = False
    cur = conn.cursor()
    print("   Conectado!", flush=True)

    t0 = time.time()
    updated = 0
    total = len(rows)
    nbatches = (total + BATCH - 1) // BATCH

    print(f"\n3. Rodando {nbatches} lotes de {BATCH:,}...\n", flush=True)

    for i in range(0, total, BATCH):
        bt = time.time()
        batch = rows[i : i + BATCH]
        values = [
            (nw, confianca(tr), score_type(tr), tr, vid)
            for nw, tr, vid in batch
        ]

        cur.execute(
            "CREATE TEMP TABLE IF NOT EXISTS _wcf_batch ("
            "nota_wcf NUMERIC(3,2), confianca_nota NUMERIC(3,2), "
            "winegod_score_type VARCHAR, nota_wcf_sample_size INTEGER, "
            "vivino_id INTEGER) ON COMMIT DELETE ROWS;"
        )
        cur.execute("TRUNCATE _wcf_batch;")
        execute_values(
            cur,
            "INSERT INTO _wcf_batch (nota_wcf, confianca_nota, "
            "winegod_score_type, nota_wcf_sample_size, vivino_id) VALUES %s",
            values,
        )
        cur.execute(
            "UPDATE wines w SET "
            "nota_wcf = b.nota_wcf, "
            "confianca_nota = b.confianca_nota, "
            "winegod_score_type = b.winegod_score_type, "
            "nota_wcf_sample_size = b.nota_wcf_sample_size "
            "FROM _wcf_batch b WHERE w.vivino_id = b.vivino_id;"
        )
        matched = cur.rowcount
        conn.commit()
        updated += matched

        bn = i // BATCH + 1
        elapsed = time.time() - bt
        total_elapsed = time.time() - t0
        remaining = (total_elapsed / (i + len(batch))) * (total - i - len(batch))
        print(
            f"   Lote {bn:>3}/{nbatches} | "
            f"{matched:>6,} atualizados | "
            f"{elapsed:>5.0f}s | "
            f"total: {updated:>10,} | "
            f"{total_elapsed:>6.0f}s corridos | "
            f"~{remaining/60:>5.0f}min restantes",
            flush=True,
        )

    total_time = time.time() - t0
    print(f"\n{'=' * 60}", flush=True)
    print(f"  CONCLUIDO!", flush=True)
    print(f"  {updated:,} vinhos atualizados em {total_time/60:.1f} minutos", flush=True)
    print(f"{'=' * 60}", flush=True)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
