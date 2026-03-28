"""
calc_wcf_step5.py — Estimate nota_wcf for wines without reviews,
using region averages. Batched by wines.id range.
_region_avg table must already exist on Render.
"""

import psycopg2

RENDER_URL = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod"
BATCH = 50000


def main():
    conn = psycopg2.connect(RENDER_URL)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT MIN(id), MAX(id) FROM wines WHERE nota_wcf IS NULL;")
    min_id, max_id = cur.fetchone()
    cur.execute("SELECT count(*) FROM wines WHERE nota_wcf IS NULL;")
    to_update = cur.fetchone()[0]
    print(f"Wines to estimate: {to_update:,} (id range {min_id:,} - {max_id:,})", flush=True)

    updated = 0
    lo = min_id

    while lo <= max_id:
        hi = lo + BATCH
        cur.execute(f"""
            UPDATE wines w
            SET nota_wcf = ra.media_regiao,
                confianca_nota = 0.1,
                winegod_score_type = 'estimated'
            FROM _region_avg ra
            WHERE w.regiao = ra.regiao
              AND w.nota_wcf IS NULL
              AND w.id >= {lo} AND w.id < {hi};
        """)
        batch_updated = cur.rowcount
        conn.commit()
        updated += batch_updated
        if batch_updated > 0 or (lo - min_id) % 200000 < BATCH:
            print(f"  id {lo:>10,} - {hi:>10,} => {batch_updated:,} (total: {updated:,})", flush=True)
        lo = hi

    # Country fallback for any remaining
    cur.execute("SELECT count(*) FROM wines WHERE nota_wcf IS NULL;")
    remaining = cur.fetchone()[0]
    print(f"\nAfter region: {remaining:,} still null", flush=True)

    if remaining > 0:
        print("Creating country averages...", flush=True)
        cur.execute("DROP TABLE IF EXISTS _pais_avg;")
        cur.execute("""
            CREATE TABLE _pais_avg AS
            SELECT pais, ROUND(AVG(nota_wcf)::numeric, 2) as media_pais
            FROM wines WHERE nota_wcf IS NOT NULL AND pais IS NOT NULL
            GROUP BY pais;
        """)
        conn.commit()

        cur.execute("SELECT MIN(id), MAX(id) FROM wines WHERE nota_wcf IS NULL;")
        row = cur.fetchone()
        if row[0] is not None:
            lo2, hi2 = row
            while lo2 <= hi2:
                end2 = lo2 + BATCH
                cur.execute(f"""
                    UPDATE wines w
                    SET nota_wcf = pa.media_pais,
                        confianca_nota = 0.1,
                        winegod_score_type = 'estimated'
                    FROM _pais_avg pa
                    WHERE w.pais = pa.pais
                      AND w.nota_wcf IS NULL
                      AND w.id >= {lo2} AND w.id < {end2};
                """)
                conn.commit()
                lo2 = end2

        cur.execute("DROP TABLE _pais_avg;")
        conn.commit()

    # Cleanup
    cur.execute("DROP TABLE IF EXISTS _region_avg;")
    conn.commit()

    # Final
    cur.execute("SELECT count(*) FROM wines WHERE nota_wcf IS NOT NULL;")
    total_wcf = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM wines WHERE nota_wcf IS NULL;")
    null_left = cur.fetchone()[0]
    print(f"\n=== FINAL ===", flush=True)
    print(f"Total with nota_wcf: {total_wcf:,}", flush=True)
    print(f"Still null: {null_left:,}", flush=True)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
