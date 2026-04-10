"""
Import Vivino wines from Render to local DB for fast matching.
Only imports columns needed for matching: id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao.
Creates pg_trgm indexes for fast similarity search.
"""
import psycopg2
import psycopg2.extras
import sys
import io
import time
import os
import _env

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LOCAL_DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
RENDER_DB = os.environ["DATABASE_URL"]

BATCH_SIZE = 10000


def main():
    print("=" * 60)
    print("IMPORTING VIVINO WINES TO LOCAL DB")
    print("=" * 60)

    local = psycopg2.connect(LOCAL_DB)
    local.autocommit = False
    lcur = local.cursor()

    # Create table
    lcur.execute("DROP TABLE IF EXISTS vivino_match")
    lcur.execute("""
        CREATE TABLE vivino_match (
            id INTEGER PRIMARY KEY,
            nome_normalizado TEXT,
            produtor_normalizado TEXT,
            safra VARCHAR(10),
            tipo VARCHAR(20),
            pais VARCHAR(5),
            regiao TEXT,
            texto_busca TEXT
        )
    """)
    local.commit()
    print("Created vivino_match table")

    # Connect to Render
    render = psycopg2.connect(RENDER_DB, connect_timeout=60)
    render.autocommit = False
    rcur = render.cursor('vivino_cursor')  # Server-side cursor for streaming

    print("Connected to Render, fetching wines...")

    rcur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
        FROM wines
        ORDER BY id
    """)

    total = 0
    t0 = time.time()

    while True:
        rows = rcur.fetchmany(BATCH_SIZE)
        if not rows:
            break

        # Build insert values with texto_busca
        values = []
        for r in rows:
            wine_id, nome, produtor, safra, tipo, pais, regiao = r
            # Build combined search text: produtor + nome + safra
            parts = []
            if produtor:
                parts.append(produtor)
            if nome:
                parts.append(nome)
            if safra:
                parts.append(str(safra))
            texto_busca = ' '.join(parts)
            values.append((wine_id, nome, produtor, safra, tipo, pais, regiao, texto_busca))

        psycopg2.extras.execute_values(
            lcur,
            "INSERT INTO vivino_match (id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao, texto_busca) VALUES %s",
            values,
            page_size=BATCH_SIZE
        )
        local.commit()

        total += len(rows)
        elapsed = time.time() - t0
        rate = total / elapsed if elapsed > 0 else 0
        print(f"  Imported {total:,} wines ({rate:.0f}/s)")

    rcur.close()
    render.close()

    print(f"\nTotal imported: {total:,} in {time.time()-t0:.0f}s")

    # Create indexes
    print("\nCreating indexes...")

    t1 = time.time()
    lcur.execute("CREATE INDEX idx_vm_texto_trgm ON vivino_match USING gin (texto_busca gin_trgm_ops)")
    local.commit()
    print(f"  texto_busca GIN trgm index: {time.time()-t1:.0f}s")

    t1 = time.time()
    lcur.execute("CREATE INDEX idx_vm_nome_trgm ON vivino_match USING gin (nome_normalizado gin_trgm_ops)")
    local.commit()
    print(f"  nome_normalizado GIN trgm index: {time.time()-t1:.0f}s")

    t1 = time.time()
    lcur.execute("CREATE INDEX idx_vm_produtor_trgm ON vivino_match USING gin (produtor_normalizado gin_trgm_ops)")
    local.commit()
    print(f"  produtor_normalizado GIN trgm index: {time.time()-t1:.0f}s")

    t1 = time.time()
    lcur.execute("CREATE INDEX idx_vm_tipo ON vivino_match (tipo)")
    local.commit()
    print(f"  tipo index: {time.time()-t1:.0f}s")

    t1 = time.time()
    lcur.execute("CREATE INDEX idx_vm_pais ON vivino_match (pais)")
    local.commit()
    print(f"  pais index: {time.time()-t1:.0f}s")

    # Verify
    lcur.execute("SELECT count(*) FROM vivino_match")
    print(f"\nVerify: {lcur.fetchone()[0]:,} wines in vivino_match")

    lcur.execute("SELECT * FROM vivino_match LIMIT 3")
    for r in lcur.fetchall():
        print(f"  {r}")

    local.close()
    print("\nDone!")


if __name__ == '__main__':
    main()
