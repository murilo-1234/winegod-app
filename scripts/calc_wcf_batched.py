"""
calc_wcf_batched.py — Update wines from _wcf_bulk (already on Render) in 50K batches.
"""

import psycopg2

RENDER_URL = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod"
BATCH = 50000


def main():
    conn = psycopg2.connect(RENDER_URL)
    conn.autocommit = False
    cur = conn.cursor()

    # Get min/max vivino_id range from _wcf_bulk
    cur.execute("SELECT MIN(vivino_id), MAX(vivino_id), COUNT(*) FROM _wcf_bulk;")
    min_id, max_id, total = cur.fetchone()
    print(f"_wcf_bulk: {total:,} rows, vivino_id range {min_id} - {max_id}", flush=True)

    cur.execute("SELECT count(*) FROM wines WHERE nota_wcf IS NOT NULL;")
    already = cur.fetchone()[0]
    print(f"Already updated: {already:,}", flush=True)

    updated_total = 0
    lo = min_id

    while lo <= max_id:
        hi = lo + BATCH
        cur.execute(f"""
            UPDATE wines w
            SET nota_wcf = b.nota_wcf,
                confianca_nota = b.confianca_nota,
                winegod_score_type = b.winegod_score_type
            FROM _wcf_bulk b
            WHERE w.vivino_id = b.vivino_id
              AND b.vivino_id >= {lo}
              AND b.vivino_id < {hi};
        """)
        batch_updated = cur.rowcount
        conn.commit()
        updated_total += batch_updated
        print(f"  vivino_id {lo:>10,} - {hi:>10,} => {batch_updated:,} updated (total: {updated_total:,})", flush=True)
        lo = hi

    # Final count
    cur.execute("SELECT count(*) FROM wines WHERE nota_wcf IS NOT NULL;")
    final = cur.fetchone()[0]
    print(f"\n=== DONE ===", flush=True)
    print(f"Total updated this run: {updated_total:,}", flush=True)
    print(f"Total wines with nota_wcf: {final:,}", flush=True)

    # Cleanup
    cur.execute("DROP TABLE IF EXISTS _wcf_bulk;")
    conn.commit()
    print("_wcf_bulk dropped.", flush=True)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
