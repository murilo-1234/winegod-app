"""
upload_wcf_remaining.py — Upload somente os vinhos WCF que faltam no Render.

Filtra o CSV para enviar apenas os ~407K vinhos que ainda nao tem
nota_wcf_sample_size, em vez de reenviar todos os 1.36M.

USO (PowerShell):
  Set-Location 'C:\\winegod-app\\scripts'
  python upload_wcf_remaining.py
"""

import csv
import io
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

CSV_PATH = os.path.join(os.path.dirname(__file__), "wcf_results.csv")


def confianca(n):
    if n >= 100: return 1.0
    if n >= 50:  return 0.8
    if n >= 25:  return 0.6
    if n >= 10:  return 0.4
    return 0.2


def main():
    print("=" * 60, flush=True)
    print("  UPLOAD WCF RESTANTE -> RENDER", flush=True)
    print("=" * 60, flush=True)

    # ------------------------------------------------------------------
    # 1. Conectar ao Render e buscar vivino_ids que faltam
    # ------------------------------------------------------------------
    print("\n1. Conectando ao Render...", flush=True)
    conn = psycopg2.connect(RENDER_URL)
    cur = conn.cursor()
    print("   Conectado!", flush=True)

    print("\n2. Buscando vivino_ids que ainda nao tem sample_size...", flush=True)
    t0 = time.time()
    cur.execute("""
        SELECT vivino_id FROM wines
        WHERE vivino_id IS NOT NULL
          AND nota_wcf_sample_size IS NULL
    """)
    missing_ids = set(row[0] for row in cur.fetchall())
    print(f"   {len(missing_ids):,} vivino_ids sem sample_size ({time.time()-t0:.0f}s)", flush=True)

    # ------------------------------------------------------------------
    # 2. Carregar CSV e filtrar so os que faltam
    # ------------------------------------------------------------------
    print("\n3. Carregando CSV e filtrando...", flush=True)
    buf = io.StringIO()
    total_csv = 0
    filtered = 0
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            total_csv += 1
            vid = int(r["vinho_id"])
            if vid not in missing_ids:
                continue
            nwcf = float(r["nota_wcf"])
            trev = int(r["total_reviews_wcf"])
            buf.write(f"{vid}\t{nwcf}\t{confianca(trev)}\t{trev}\n")
            filtered += 1

    print(f"   CSV total: {total_csv:,} vinhos", flush=True)
    print(f"   Filtrados (faltam no Render): {filtered:,} vinhos", flush=True)

    if filtered == 0:
        print("\n   Nenhum vinho para atualizar. Tudo ja esta no Render!", flush=True)
        cur.close()
        conn.close()
        return

    # ------------------------------------------------------------------
    # 3. COPY para staging table
    # ------------------------------------------------------------------
    print(f"\n4. Criando staging table e carregando {filtered:,} linhas...", flush=True)
    t1 = time.time()
    cur.execute("DROP TABLE IF EXISTS _wcf_remaining;")
    cur.execute("""
        CREATE TABLE _wcf_remaining (
            vivino_id INTEGER,
            nota_wcf NUMERIC(3,2),
            confianca_nota NUMERIC(3,2),
            nota_wcf_sample_size INTEGER
        );
    """)
    conn.commit()

    buf.seek(0)
    cur.copy_from(
        buf, "_wcf_remaining", sep="\t",
        columns=("vivino_id", "nota_wcf", "confianca_nota",
                 "nota_wcf_sample_size")
    )
    conn.commit()
    print(f"   {filtered:,} linhas carregadas em {time.time()-t1:.0f}s", flush=True)

    # ------------------------------------------------------------------
    # 4. Criar indice e UPDATE
    # ------------------------------------------------------------------
    print("\n5. Criando indice na staging...", flush=True)
    cur.execute("CREATE INDEX idx_wcf_remaining_vid ON _wcf_remaining(vivino_id);")
    conn.commit()

    print("\n6. UPDATE wines...", flush=True)
    t2 = time.time()
    cur.execute("""
        UPDATE wines w
        SET nota_wcf = b.nota_wcf,
            confianca_nota = b.confianca_nota,
            nota_wcf_sample_size = b.nota_wcf_sample_size
        FROM _wcf_remaining b
        WHERE w.vivino_id = b.vivino_id;
    """)
    updated = cur.rowcount
    conn.commit()
    print(f"   {updated:,} vinhos atualizados em {time.time()-t2:.0f}s", flush=True)

    # ------------------------------------------------------------------
    # 5. Limpar
    # ------------------------------------------------------------------
    print("\n7. Limpando staging table...", flush=True)
    cur.execute("DROP TABLE _wcf_remaining;")
    conn.commit()

    cur.close()
    conn.close()

    total_time = time.time() - t0
    print(f"\n{'=' * 60}", flush=True)
    print(f"  CONCLUIDO!", flush=True)
    print(f"  {updated:,} vinhos atualizados em {total_time/60:.1f} minutos", flush=True)
    print(f"{'=' * 60}", flush=True)


if __name__ == "__main__":
    main()
