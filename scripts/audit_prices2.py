#!/usr/bin/env python
"""
Audit duplicate and stale price problems across vinhos_{cc}_fontes tables.
Read-only — no data modifications.
Outputs to audit_output2.txt with flushing after each section.
"""
import psycopg2
import sys
import time

COUNTRIES = ['us','br','au','gb','it','fr','nl','de','dk','es','hk','mx','nz','pt','ca']
DSN = 'postgresql://postgres:postgres123@localhost:5432/winegod_db'
NON_PRODUCT_PATTERNS = ['/cart', '/checkout', '/login', '/account', '/collection', '/category', '/search']

out = open('C:/winegod-app/scripts/audit_output2.txt', 'w', buffering=1)

def p(msg=''):
    out.write(msg + '\n')
    out.flush()

def run_audit():
    t0 = time.time()
    p(f"Connecting to database...")
    try:
        conn = psycopg2.connect(DSN, connect_timeout=15)
    except Exception as e:
        p(f"CONNECTION ERROR: {e}")
        return
    conn.set_session(readonly=True)
    cur = conn.cursor()
    p(f"Connected. Starting audit of {len(COUNTRIES)} countries.\n")

    summary = {}

    for cc in COUNTRIES:
        tc = time.time()
        table = f'vinhos_{cc}_fontes'
        p(f"{'='*80}")
        p(f"  COUNTRY: {cc.upper()}  --  table: {table}")
        p(f"{'='*80}")

        # Check table exists
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)", (table,))
        if not cur.fetchone()[0]:
            p(f"  TABLE NOT FOUND, skipping")
            summary[cc] = {'total': 0}
            continue

        # Total records
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        total = cur.fetchone()[0]
        p(f"\nTotal records: {total:,}")
        if total == 0:
            p("  (empty table, skipping)")
            summary[cc] = {'total': 0}
            continue

        # Get column info upfront
        cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,))
        all_cols = [r[0] for r in cur.fetchall()]

        # =====================================================================
        # 1) EXACT DUPLICATE URLs
        # =====================================================================
        p(f"\n--- 1. Exact Duplicate URLs ---")
        if 'url_original' in all_cols:
            cur.execute(f"""
                SELECT COUNT(*), COALESCE(SUM(cnt - 1), 0)
                FROM (
                    SELECT url_original, COUNT(*) AS cnt
                    FROM {table}
                    WHERE url_original IS NOT NULL
                    GROUP BY url_original
                    HAVING COUNT(*) > 1
                ) sub
            """)
            row = cur.fetchone()
            dup_urls = row[0] or 0
            extra_records = row[1] or 0
        else:
            p(f"  (no url_original column)")
            dup_urls = 0
            extra_records = 0

        pct_extra = (extra_records / total * 100) if total > 0 else 0
        p(f"  Duplicate URLs: {dup_urls:,}")
        p(f"  Extra records (above 1st): {extra_records:,}")
        p(f"  Extra as % of total: {pct_extra:.2f}%")

        if 'url_original' in all_cols and dup_urls > 0:
            cur.execute(f"""
                SELECT url_original, COUNT(*) AS cnt,
                       ARRAY_AGG(DISTINCT preco ORDER BY preco) AS distinct_prices
                FROM {table}
                WHERE url_original IS NOT NULL
                GROUP BY url_original
                HAVING COUNT(*) > 1
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """)
            top5 = cur.fetchall()
            if top5:
                p(f"  Top 5 most duplicated URLs:")
                for i, (url, cnt, prices) in enumerate(top5, 1):
                    url_short = (url[:90] + '...') if url and len(url) > 90 else str(url)
                    prices_str = ', '.join(str(pp) for pp in (prices or []))
                    p(f"    {i}. ({cnt}x) prices=[{prices_str}]")
                    p(f"       {url_short}")

        # =====================================================================
        # 2) SAME PRICE ACROSS MANY PRODUCTS
        # =====================================================================
        p(f"\n--- 2. Stores with ALL same price (stddev=0) ---")
        group_col = None
        for c in ['fonte', 'dominio', 'loja']:
            if c in all_cols:
                group_col = c
                break

        same_price_stores = 0
        if group_col and 'preco' in all_cols:
            cur.execute(f"""
                SELECT {group_col}, COUNT(*) AS cnt,
                       MIN(preco) AS min_price, MAX(preco) AS max_price,
                       STDDEV(preco) AS sd
                FROM {table}
                WHERE preco IS NOT NULL AND preco > 0
                GROUP BY {group_col}
                HAVING COUNT(*) >= 10 AND STDDEV(preco) = 0
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """)
            same_price = cur.fetchall()
            same_price_stores = len(same_price)
            if same_price:
                p(f"  WARNING: {len(same_price)} store(s) with 10+ products ALL at same price:")
                for store, cnt, minp, maxp, sd in same_price:
                    store_short = str(store)[:60]
                    p(f"    - {store_short}: {cnt} products, all at {minp}")
            else:
                p(f"  OK -- no stores with 10+ products all at same price")
        else:
            p(f"  (missing columns for this check)")

        # =====================================================================
        # 3) disponivel = false
        # =====================================================================
        p(f"\n--- 3. disponivel = false records ---")
        unavail = 0
        unavail_with_price = 0
        has_disponivel = 'disponivel' in all_cols
        if has_disponivel:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE disponivel = false")
            unavail = cur.fetchone()[0]
            if 'preco' in all_cols:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE disponivel = false AND preco IS NOT NULL AND preco > 0")
                unavail_with_price = cur.fetchone()[0]
            pct_unavail = (unavail / total * 100) if total > 0 else 0
            p(f"  disponivel=false: {unavail:,} ({pct_unavail:.1f}% of total)")
            p(f"  ...of those, with price > 0: {unavail_with_price:,}")
        else:
            p(f"  (no disponivel column)")

        # =====================================================================
        # 4) VERY OLD DATA
        # =====================================================================
        p(f"\n--- 4. Stale data ---")
        date_col = None
        for c in ['atualizado_em', 'updated_at', 'data_coleta']:
            if c in all_cols:
                date_col = c
                break

        stale_1y = 0
        stale_2y = 0
        if date_col:
            cur.execute(f"""
                SELECT
                    COUNT(*) FILTER (WHERE {date_col} < NOW() - INTERVAL '1 year') AS older_1y,
                    COUNT(*) FILTER (WHERE {date_col} < NOW() - INTERVAL '2 years') AS older_2y,
                    MIN({date_col}) AS oldest,
                    MAX({date_col}) AS newest
                FROM {table}
                WHERE {date_col} IS NOT NULL
            """)
            row = cur.fetchone()
            stale_1y = row[0] or 0
            stale_2y = row[1] or 0
            p(f"  Using column: {date_col}")
            p(f"  > 1 year old: {stale_1y:,}")
            p(f"  > 2 years old: {stale_2y:,}")
            p(f"  Oldest record: {row[2]}")
            p(f"  Newest record: {row[3]}")
        else:
            p(f"  (no date column found among: atualizado_em, updated_at, data_coleta)")

        # =====================================================================
        # 5) PRICE COLUMN TYPE
        # =====================================================================
        p(f"\n--- 5. Price column type ---")
        cur.execute(f"""
            SELECT data_type, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'preco'
        """, (table,))
        prow = cur.fetchone()
        price_type = 'N/A'
        if prow:
            price_type = prow[0]
            if prow[0] == 'numeric':
                p(f"  preco: NUMERIC({prow[1]},{prow[2]}) -- OK (DECIMAL)")
            elif any(x in prow[0].lower() for x in ['double', 'float', 'real']):
                p(f"  preco: {prow[0]} -- WARNING: float type can cause precision issues!")
            else:
                p(f"  preco: {prow[0]} (precision={prow[1]}, scale={prow[2]})")
        else:
            p(f"  (no preco column found!)")

        # =====================================================================
        # 6) NON-PRODUCT URLS
        # =====================================================================
        p(f"\n--- 6. Non-product URLs ---")
        bad_urls = 0
        if 'url_original' in all_cols:
            conditions = " OR ".join([f"url_original ILIKE '%%{pat}%%'" for pat in NON_PRODUCT_PATTERNS])
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE url_original IS NOT NULL AND ({conditions})")
            bad_urls = cur.fetchone()[0]
            p(f"  URLs matching non-product patterns: {bad_urls:,}")

            if bad_urls > 0:
                for pat in NON_PRODUCT_PATTERNS:
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE url_original ILIKE '%%{pat}%%'")
                    cnt = cur.fetchone()[0]
                    if cnt > 0:
                        p(f"    {pat}: {cnt:,}")
                cur.execute(f"SELECT url_original FROM {table} WHERE url_original IS NOT NULL AND ({conditions}) LIMIT 3")
                examples = cur.fetchall()
                if examples:
                    p(f"  Examples:")
                    for (u,) in examples:
                        p(f"    {str(u)[:100]}")
        else:
            p(f"  (no url_original column)")

        elapsed = time.time() - tc
        p(f"\n  [{cc.upper()} completed in {elapsed:.1f}s]")

        summary[cc] = {
            'total': total,
            'dup_urls': dup_urls,
            'extra_records': extra_records,
            'pct_extra': pct_extra,
            'unavail': unavail if has_disponivel else 'N/A',
            'stale_1y': stale_1y,
            'stale_2y': stale_2y,
            'bad_urls': bad_urls,
            'price_type': price_type,
            'same_price_stores': same_price_stores,
        }

    # =========================================================================
    # FINAL OVERVIEW
    # =========================================================================
    p(f"\n\n{'#'*80}")
    p(f"  FINAL OVERVIEW -- ALL 15 COUNTRIES")
    p(f"{'#'*80}")

    p(f"\n{'CC':<5} {'Total':>10} {'DupURLs':>10} {'Extra':>10} {'%Extra':>7} {'Unavail':>10} {'Stale1Y':>10} {'Stale2Y':>10} {'BadURLs':>10} {'SameP':>6}")
    p('-' * 100)

    total_all = 0
    total_extra = 0
    total_bad = 0
    total_stale1 = 0
    total_stale2 = 0
    total_unavail = 0

    for cc in COUNTRIES:
        s = summary.get(cc, {})
        t = s.get('total', 0)
        total_all += t
        extra = s.get('extra_records', 0)
        total_extra += extra
        bad = s.get('bad_urls', 0)
        total_bad += bad
        st1 = s.get('stale_1y', 0)
        total_stale1 += st1
        st2 = s.get('stale_2y', 0)
        total_stale2 += st2
        unav = s.get('unavail', 'N/A')
        if isinstance(unav, int):
            total_unavail += unav
        sp = s.get('same_price_stores', 0)

        p(f"{cc.upper():<5} {t:>10,} {s.get('dup_urls',0):>10,} {extra:>10,} {s.get('pct_extra',0):>6.1f}% "
          f"{str(unav):>10} {st1:>10,} {st2:>10,} {bad:>10,} {sp:>6}")

    p('-' * 100)
    p(f"{'TOTAL':<5} {total_all:>10,} {'':>10} {total_extra:>10,} {'':>7} {total_unavail:>10,} {total_stale1:>10,} {total_stale2:>10,} {total_bad:>10,}")

    p(f"\n{'='*80}")
    p(f"  BIGGEST PROBLEMS FOUND")
    p(f"{'='*80}")

    worst_dups = sorted(COUNTRIES, key=lambda c: summary.get(c, {}).get('extra_records', 0), reverse=True)
    p(f"\n  Worst duplicate problems:")
    for cc in worst_dups:
        s = summary.get(cc, {})
        if s.get('extra_records', 0) > 0:
            p(f"    {cc.upper()}: {s['extra_records']:,} extra records ({s.get('pct_extra',0):.1f}% of table)")

    worst_stale = sorted(COUNTRIES, key=lambda c: summary.get(c, {}).get('stale_1y', 0), reverse=True)
    p(f"\n  Worst stale data (>1 year old):")
    for cc in worst_stale:
        s = summary.get(cc, {})
        if s.get('stale_1y', 0) > 0:
            pct = (s['stale_1y'] / s['total'] * 100) if s['total'] > 0 else 0
            p(f"    {cc.upper()}: {s['stale_1y']:,} records ({pct:.1f}% of table)")

    worst_unavail = sorted(COUNTRIES, key=lambda c: summary.get(c, {}).get('unavail', 0) if isinstance(summary.get(c, {}).get('unavail', 0), int) else 0, reverse=True)
    p(f"\n  Most unavailable products (disponivel=false):")
    for cc in worst_unavail:
        s = summary.get(cc, {})
        u = s.get('unavail', 0)
        if isinstance(u, int) and u > 0:
            pct = (u / s['total'] * 100) if s['total'] > 0 else 0
            p(f"    {cc.upper()}: {u:,} records ({pct:.1f}% of table)")

    worst_bad = sorted(COUNTRIES, key=lambda c: summary.get(c, {}).get('bad_urls', 0), reverse=True)
    p(f"\n  Most non-product URLs:")
    for cc in worst_bad:
        s = summary.get(cc, {})
        if s.get('bad_urls', 0) > 0:
            p(f"    {cc.upper()}: {s['bad_urls']:,} records")

    float_countries = [cc for cc in COUNTRIES if any(x in str(summary.get(cc, {}).get('price_type', '')).lower() for x in ['double', 'float', 'real'])]
    if float_countries:
        p(f"\n  PRICE PRECISION WARNING -- float types detected in:")
        for cc in float_countries:
            p(f"    {cc.upper()}: {summary[cc]['price_type']}")
    else:
        p(f"\n  Price types: all OK (no float precision issues detected)")

    same_price_countries = [cc for cc in COUNTRIES if summary.get(cc, {}).get('same_price_stores', 0) > 0]
    if same_price_countries:
        p(f"\n  SCRAPING FAILURE (same price across all products):")
        for cc in same_price_countries:
            p(f"    {cc.upper()}: {summary[cc]['same_price_stores']} store(s) affected")

    p(f"\n  GRAND TOTALS:")
    p(f"    Total records across 15 countries: {total_all:,}")
    p(f"    Total extra duplicate records: {total_extra:,}")
    p(f"    Total non-product URLs: {total_bad:,}")
    p(f"    Total stale >1yr: {total_stale1:,}")
    p(f"    Total stale >2yr: {total_stale2:,}")
    p(f"    Total unavailable: {total_unavail:,}")

    elapsed = time.time() - t0
    p(f"\n  Total audit time: {elapsed:.1f}s")

    conn.close()
    out.close()
    print(f"Done. Output written to C:/winegod-app/scripts/audit_output2.txt")

if __name__ == '__main__':
    run_audit()
