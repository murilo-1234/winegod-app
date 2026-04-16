"""
upload_wcf_batched_remaining.py — Usa a staging table _wcf_remaining
que ja esta no Render (398.575 vinhos) e faz UPDATE em lotes de 10K.
Cada lote faz COMMIT. Se cair no meio, roda de novo.

USO (PowerShell):
  Set-Location 'C:\\winegod-app\\scripts'
  python upload_wcf_batched_remaining.py
"""

import os
import sys
import time
import psycopg2

# ---------------------------------------------------------------------------
# Carrega DATABASE_URL do .env
# ---------------------------------------------------------------------------
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", ".env")
RENDER_URL = None
with open(ENV_PATH, encoding="utf-8") as f:
    for line in f:
        if line.startswith("DATABASE_URL="):
            RENDER_URL = line.strip().split("=", 1)[1]
            break

if not RENDER_URL:
    sys.exit("ERRO: DATABASE_URL nao encontrada em backend/.env")

BATCH = 10000


def main():
    print("=" * 60, flush=True)
    print("  UPDATE LOTES — usando _wcf_remaining do Render", flush=True)
    print("=" * 60, flush=True)

    conn = psycopg2.connect(RENDER_URL)
    conn.autocommit = False
    cur = conn.cursor()

    # Verificar staging table
    cur.execute("SELECT COUNT(*) FROM _wcf_remaining;")
    total_staging = cur.fetchone()[0]
    print(f"\n  Staging table: {total_staging:,} vinhos", flush=True)

    if total_staging == 0:
        print("  Nenhum vinho na staging. Nada a fazer.", flush=True)
        cur.close()
        conn.close()
        return

    nbatches = (total_staging + BATCH - 1) // BATCH
    print(f"  Lotes de {BATCH:,} = {nbatches} lotes", flush=True)

    t0 = time.time()
    updated_total = 0

    for i in range(nbatches):
        offset = i * BATCH
        bt = time.time()

        cur.execute("""
            UPDATE wines w
            SET nota_wcf = b.nota_wcf,
                confianca_nota = b.confianca_nota,
                nota_wcf_sample_size = b.nota_wcf_sample_size
            FROM (
                SELECT * FROM _wcf_remaining
                ORDER BY vivino_id
                LIMIT %s OFFSET %s
            ) b
            WHERE w.vivino_id = b.vivino_id;
        """, (BATCH, offset))

        matched = cur.rowcount
        conn.commit()
        updated_total += matched

        elapsed = time.time() - bt
        total_elapsed = time.time() - t0
        remaining_batches = nbatches - (i + 1)
        avg_per_batch = total_elapsed / (i + 1)
        eta = remaining_batches * avg_per_batch

        print(
            f"  Lote {i+1:>3}/{nbatches} | "
            f"{matched:>6,} atualizados | "
            f"{elapsed:>5.0f}s | "
            f"total: {updated_total:>8,} | "
            f"~{eta/60:>4.0f}min restantes",
            flush=True,
        )

    total_time = time.time() - t0

    # Limpar staging
    print("\n  Limpando staging table...", flush=True)
    cur.execute("DROP TABLE IF EXISTS _wcf_remaining;")
    conn.commit()

    cur.close()
    conn.close()

    print(f"\n{'=' * 60}", flush=True)
    print(f"  CONCLUIDO!", flush=True)
    print(f"  {updated_total:,} vinhos atualizados em {total_time/60:.1f} minutos", flush=True)
    print(f"{'=' * 60}", flush=True)


if __name__ == "__main__":
    main()
