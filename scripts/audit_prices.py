#!/usr/bin/env python
"""
Audit duplicate and stale price problems across vinhos_{cc}_fontes tables.
Read-only — no data modifications.
"""
import psycopg2
import sys

COUNTRIES = ['us','br','au','gb','it','fr','nl','de','dk','es','hk','mx','nz','pt','ca']

DSN = 'postgresql://postgres:postgres123@localhost:5432/winegod_db'

NON_PRODUCT_PATTERNS = ['/cart', '/checkout', '/login', '/account', '/collection', '/category', '/search']

def run_audit():
    conn = psycopg2.connect(DSN, connect_timeout=15)
    conn.set_session(readonly=True)
    cur = conn.cursor()

    # Collect global summary
    summary = {}

    for cc in COUNTRIES:
        table = f'vinhos_{cc}_fontes'
        print(f"\n{'='*80}")
        print(f"  COUNTRY: {cc.upper()}  —  table: {table}")
        print(f"{'='*80}")

        # --- Total records ---
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        total = cur.fetchone()[0]
        print(f"\nTotal records: {total:,}")
        if total == 0:
            print("  (empty table, skipping)")
            summary[cc] = {'total': 0}
            continue

        # =====================================================================
        # 1) EXACT DUPLICATE URLs
        # =====================================================================
        print(f"\n--- 1. Exact Duplicate URLs ---")
        cur.execute(f"""
            SELECT COUNT(*) AS dup_urls,
                   SUM(cnt - 1) AS extra_records
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
        print(f"  Duplicate URLs: {dup_urls:,}")
        print(f"  Extra records (above 1st): {extra_records:,}")
        pct_extra = (extra_records / total * 100) if total > 0 else 0
        print(f"  Extra as % of total: {pct_extra:.2f}%")

        # Top 5 most duplicated URLs with their different prices
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
            print(f"  Top 5 most duplicated URLs:")
            for i, (url, cnt, prices) in enumerate(top5, 1):
                url_short = url[:90] + '...' if len(url) > 90 else url
                prices_str = ', '.join(str(p) for p in (prices or []))
                print(f"    {i}. ({cnt}x) prices=[{prices_str}]")
                print(f"       {url_short}")

        # =====================================================================
        # 2) SAME PRICE ACROSS MANY PRODUCTS (scraping failure)
        # =====================================================================
        print(f"\n--- 2. Stores with ALL same price (stddev=0) ---")
        # Check which columns exist for grouping
        cur.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = '{table}'
            AND column_name IN ('fonte', 'dominio', 'loja')
        """)
        available_cols = [r[0] for r in cur.fetchall()]

        group_col = None
        if 'fonte' in available_cols:
            group_col = 'fonte'
        elif 'dominio' in available_cols:
            group_col = 'dominio'
        elif 'loja' in available_cols:
            group_col = 'loja'

        if group_col:
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
            if same_price:
                print(f"  WARNING: {len(same_price)} store(s) with 10+ products ALL at same price:")
                for store, cnt, minp, maxp, sd in same_price:
                    store_short = str(store)[:60]
                    print(f"    - {store_short}: {cnt} products, all at {minp}")
            else:
                print(f"  OK — no stores with 10+ products all at same price")

            # Also check near-zero stddev (very suspicious)
            cur.execute(f"""
                SELECT {group_col}, COUNT(*) AS cnt,
                       MIN(preco), MAX(preco), STDDEV(preco)
                FROM {table}
                WHERE preco IS NOT NULL AND preco > 0
                GROUP BY {group_col}
                HAVING COUNT(*) >= 20 AND STDDEV(preco) < 0.01 AND STDDEV(preco) > 0
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """)
            near_zero = cur.fetchall()
            if near_zero:
                print(f"  Also suspicious — stddev < 0.01 with 20+ products:")
                for store, cnt, minp, maxp, sd in near_zero:
                    store_short = str(store)[:60]
                    print(f"    - {store_short}: {cnt} products, stddev={sd:.4f}, range [{minp}-{maxp}]")
        else:
            print(f"  (no fonte/dominio/loja column found, skipping)")

        # =====================================================================
        # 3) disponivel = false but has price
        # =====================================================================
        print(f"\n--- 3. disponivel = false records ---")
        cur.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = '{table}' AND column_name = 'disponivel'
        """)
        has_disponivel = cur.fetchone()

        if has_disponivel:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE disponivel = false")
            unavail = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE disponivel = false AND preco IS NOT NULL AND preco > 0")
            unavail_with_price = cur.fetchone()[0]
            pct_unavail = (unavail / total * 100) if total > 0 else 0
            print(f"  disponivel=false: {unavail:,} ({pct_unavail:.1f}% of total)")
            print(f"  ...of those, with price > 0: {unavail_with_price:,}")
        else:
            print(f"  (no disponivel column)")

        # =====================================================================
        # 4) VERY OLD DATA (atualizado_em)
        # =====================================================================
        print(f"\n--- 4. Stale data (atualizado_em) ---")
        cur.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = '{table}' AND column_name IN ('atualizado_em', 'updated_at', 'data_coleta')
        """)
        date_cols = [r[0] for r in cur.fetchall()]
        date_col = None
        for c in ['atualizado_em', 'updated_at', 'data_coleta']:
            if c in date_cols:
                date_col = c
                break

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
            print(f"  Using column: {date_col}")
            print(f"  > 1 year old: {row[0]:,}")
            print(f"  > 2 years old: {row[1]:,}")
            print(f"  Oldest record: {row[2]}")
            print(f"  Newest record: {row[3]}")
            stale_1y = row[0]
            stale_2y = row[1]
        else:
            print(f"  (no date column found)")
            stale_1y = 0
            stale_2y = 0

        # =====================================================================
        # 5) PRICE COLUMN TYPE
        # =====================================================================
        print(f"\n--- 5. Price column type ---")
        cur.execute(f"""
            SELECT column_name, data_type, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_name = '{table}' AND column_name = 'preco'
        """)
        prow = cur.fetchone()
        if prow:
            dtype = prow[1]
            prec = prow[2]
            scale = prow[3]
            if dtype == 'numeric':
                print(f"  preco: NUMERIC({prec},{scale}) — OK (DECIMAL)")
            elif 'double' in dtype or 'float' in dtype or 'real' in dtype:
                print(f"  preco: {dtype} — WARNING: float type can cause precision issues!")
            elif 'int' in dtype:
                print(f"  preco: {dtype} — WARNING: integer loses decimal cents!")
            else:
                print(f"  preco: {dtype} (precision={prec}, scale={scale})")
        else:
            print(f"  (no preco column found!)")

        # =====================================================================
        # 6) NON-PRODUCT URLS
        # =====================================================================
        print(f"\n--- 6. Non-product URLs ---")
        conditions = " OR ".join([f"url_original ILIKE '%{p}%'" for p in NON_PRODUCT_PATTERNS])
        cur.execute(f"""
            SELECT COUNT(*) FROM {table}
            WHERE url_original IS NOT NULL AND ({conditions})
        """)
        bad_urls = cur.fetchone()[0]
        print(f"  URLs matching non-product patterns: {bad_urls:,}")

        if bad_urls > 0:
            # Break down by pattern
            for pat in NON_PRODUCT_PATTERNS:
                cur.execute(f"""
                    SELECT COUNT(*) FROM {table}
                    WHERE url_original ILIKE '%{pat}%'
                """)
                cnt = cur.fetchone()[0]
                if cnt > 0:
                    print(f"    {pat}: {cnt:,}")

            # Show a few examples
            cur.execute(f"""
                SELECT url_original FROM {table}
                WHERE url_original IS NOT NULL AND ({conditions})
                LIMIT 3
            """)
            examples = cur.fetchall()
            if examples:
                print(f"  Examples:")
                for (u,) in examples:
                    print(f"    {u[:100]}")

        # Store summary
        summary[cc] = {
            'total': total,
            'dup_urls': dup_urls,
            'extra_records': extra_records,
            'pct_extra': pct_extra,
            'unavail': unavail if has_disponivel else 'N/A',
            'stale_1y': stale_1y,
            'stale_2y': stale_2y,
            'bad_urls': bad_urls,
            'price_type': prow[1] if prow else 'N/A',
        }

    # =========================================================================
    # FINAL OVERVIEW
    # =========================================================================
    print(f"\n\n{'#'*80}")
    print(f"  FINAL OVERVIEW — ALL 15 COUNTRIES")
    print(f"{'#'*80}")

    print(f"\n{'CC':<5} {'Total':>10} {'Dup URLs':>10} {'Extra':>10} {'%Extra':>7} {'Unavail':>10} {'Stale1Y':>10} {'Stale2Y':>10} {'BadURLs':>10}")
    print('-' * 95)

    total_all = 0
    total_extra = 0
    total_bad = 0
    total_stale1 = 0
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
        unav = s.get('unavail', 'N/A')
        if isinstance(unav, int):
            total_unavail += unav

        print(f"{cc.upper():<5} {t:>10,} {s.get('dup_urls',0):>10,} {extra:>10,} {s.get('pct_extra',0):>6.1f}% "
              f"{str(unav):>10} {st1:>10,} {s.get('stale_2y',0):>10,} {bad:>10,}")

    print('-' * 95)
    print(f"{'TOTAL':<5} {total_all:>10,} {'':>10} {total_extra:>10,} {'':>7} {total_unavail:>10,} {total_stale1:>10,} {'':>10} {total_bad:>10,}")

    # Highlight biggest problems
    print(f"\n{'='*80}")
    print(f"  BIGGEST PROBLEMS FOUND")
    print(f"{'='*80}")

    # Sort by extra records
    worst_dups = sorted(COUNTRIES, key=lambda c: summary.get(c, {}).get('extra_records', 0), reverse=True)[:5]
    print(f"\n  Worst duplicate problems:")
    for cc in worst_dups:
        s = summary.get(cc, {})
        if s.get('extra_records', 0) > 0:
            print(f"    {cc.upper()}: {s['extra_records']:,} extra records ({s.get('pct_extra',0):.1f}% of table)")

    # Sort by stale
    worst_stale = sorted(COUNTRIES, key=lambda c: summary.get(c, {}).get('stale_1y', 0), reverse=True)[:5]
    print(f"\n  Worst stale data (>1 year old):")
    for cc in worst_stale:
        s = summary.get(cc, {})
        if s.get('stale_1y', 0) > 0:
            pct = (s['stale_1y'] / s['total'] * 100) if s['total'] > 0 else 0
            print(f"    {cc.upper()}: {s['stale_1y']:,} records ({pct:.1f}% of table)")

    # Sort by unavailable
    worst_unavail = sorted(COUNTRIES, key=lambda c: summary.get(c, {}).get('unavail', 0) if isinstance(summary.get(c, {}).get('unavail', 0), int) else 0, reverse=True)[:5]
    print(f"\n  Most unavailable products (disponivel=false):")
    for cc in worst_unavail:
        s = summary.get(cc, {})
        u = s.get('unavail', 0)
        if isinstance(u, int) and u > 0:
            pct = (u / s['total'] * 100) if s['total'] > 0 else 0
            print(f"    {cc.upper()}: {u:,} records ({pct:.1f}% of table)")

    # Sort by bad URLs
    worst_bad = sorted(COUNTRIES, key=lambda c: summary.get(c, {}).get('bad_urls', 0), reverse=True)[:5]
    print(f"\n  Most non-product URLs:")
    for cc in worst_bad:
        s = summary.get(cc, {})
        if s.get('bad_urls', 0) > 0:
            print(f"    {cc.upper()}: {s['bad_urls']:,} records")

    # Price type warnings
    float_countries = [cc for cc in COUNTRIES if 'float' in str(summary.get(cc, {}).get('price_type', '')).lower() or 'double' in str(summary.get(cc, {}).get('price_type', '')).lower() or 'real' in str(summary.get(cc, {}).get('price_type', '')).lower()]
    if float_countries:
        print(f"\n  PRICE PRECISION WARNING — float types detected in:")
        for cc in float_countries:
            print(f"    {cc.upper()}: {summary[cc]['price_type']}")
    else:
        print(f"\n  Price types: all OK (no float precision issues detected)")

    print(f"\n  GRAND TOTALS:")
    print(f"    Total records across 15 countries: {total_all:,}")
    print(f"    Total extra duplicate records: {total_extra:,}")
    print(f"    Total non-product URLs: {total_bad:,}")
    print(f"    Total stale (>1yr): {total_stale1:,}")
    print(f"    Total unavailable: {total_unavail:,}")

    conn.close()
    print("\nDone.")

if __name__ == '__main__':
    run_audit()
