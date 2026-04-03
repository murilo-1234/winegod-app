"""Match Vivino via pg_trgm pra todos os pending_match. Batches de 500."""
import sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import psycopg2

DB = dict(host="localhost", port=5432, dbname="winegod_db",
          user="postgres", password="postgres123",
          options="-c client_encoding=UTF8")
BATCH = 500
THRESHOLD = 0.30

conn = psycopg2.connect(**DB)
conn.autocommit = False
cur = conn.cursor()

# Contar total
cur.execute("SELECT COUNT(*) FROM y2_results WHERE status='pending_match' AND prod_banco IS NOT NULL AND prod_banco != '' AND prod_banco != '??'")
total = cur.fetchone()[0]
print(f"Pendentes: {total}")

done = 0
matched = 0
new = 0
start = time.time()

while True:
    # Pegar batch de IDs pendentes
    cur.execute("""
        SELECT id, prod_banco, vinho_banco
        FROM y2_results
        WHERE status = 'pending_match'
        AND prod_banco IS NOT NULL AND prod_banco != '' AND prod_banco != '??'
        LIMIT %s
    """, (BATCH,))
    rows = cur.fetchall()
    if not rows:
        break

    for row_id, prod, vin in rows:
        search = f"{prod} {vin}".strip()
        if len(search) < 4:
            cur.execute("UPDATE y2_results SET status='new' WHERE id=%s", (row_id,))
            new += 1
            continue

        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(texto_busca, %s) as ts
            FROM vivino_match WHERE texto_busca %% %s
            ORDER BY similarity(texto_busca, %s) DESC LIMIT 1
        """, (search, search, search))
        cand = cur.fetchone()

        if cand and cand[3] >= THRESHOLD:
            cur.execute("""UPDATE y2_results SET vivino_id=%s, vivino_produtor=%s, vivino_nome=%s,
                          match_score=%s, status='matched' WHERE id=%s""",
                       (cand[0], cand[1], cand[2], round(cand[3], 3), row_id))
            matched += 1
        else:
            cur.execute("UPDATE y2_results SET status='new' WHERE id=%s", (row_id,))
            new += 1

    conn.commit()
    done += len(rows)

    elapsed = time.time() - start
    speed = done / elapsed if elapsed > 0 else 0
    remaining = (total - done) / speed / 60 if speed > 0 else 0
    pct = done * 100 // total

    print(f"  {done:>7}/{total} ({pct}%) | matched={matched} new={new} | {speed:.1f}/seg | ETA {remaining:.0f}min", flush=True)

conn.close()
elapsed = time.time() - start
print(f"\nFINALIZADO em {elapsed/60:.1f} min")
print(f"  Matched: {matched}")
print(f"  New: {new}")
print(f"  Total: {done}")
