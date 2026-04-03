"""
Comprehensive price audit across all 50 country tables.
READ-ONLY — no data modifications.
"""
import psycopg2
import json
import sys

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

COUNTRIES = [
    "ae", "ar", "at", "au", "be", "bg", "br", "ca", "ch", "cl",
    "cn", "co", "cz", "de", "dk", "es", "fi", "fr", "gb", "ge",
    "gr", "hk", "hr", "hu", "ie", "il", "in", "it", "jp", "kr",
    "lu", "md", "mx", "nl", "no", "nz", "pe", "ph", "pl", "pt",
    "ro", "ru", "se", "sg", "th", "tr", "tw", "us", "uy", "za"
]

# Currency minimums for "suspiciously low" detection
# Prices below these are suspicious for wine
CURRENCY_MINS = {
    "EUR": 1, "USD": 1, "GBP": 1, "CHF": 1, "CAD": 1, "AUD": 1,
    "NZD": 1, "SGD": 1, "HKD": 5, "AED": 3, "DKK": 5, "SEK": 5,
    "NOK": 5, "PLN": 3, "CZK": 20, "HUF": 200, "RON": 3, "BGN": 1,
    "HRK": 5, "RUB": 50, "TRY": 5, "GEL": 2, "ILS": 3, "INR": 50,
    "JPY": 100, "KRW": 500, "CNY": 5, "TWD": 20, "THB": 20,
    "PHP": 30, "MXN": 10, "BRL": 5, "ARS": 100, "CLP": 500,
    "COP": 2000, "PEN": 3, "UYU": 30, "ZAR": 10, "MDL": 10,
    "LUF": 1,  # Luxembourg uses EUR
}

# Placeholder values to check
PLACEHOLDERS = [0.01, 0.99, 1.00, 9999, 99999, 999999]


def audit_country(cur, cc):
    """Run full audit for one country. Returns dict with results."""
    table = f"vinhos_{cc}_fontes"
    result = {
        "country": cc,
        "total": 0,
        "negative": 0,
        "zero": 0,
        "null_count": 0,
        "currencies": {},
        "extreme_outliers": 0,
        "extreme_samples": [],
        "suspicious_low": 0,
        "placeholders": 0,
        "placeholder_detail": {},
        "error": None,
    }

    try:
        # 0. Total records
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        result["total"] = cur.fetchone()[0]
        if result["total"] == 0:
            return result

        # 1. Negative prices (including -1)
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE preco < 0")
        result["negative"] = cur.fetchone()[0]

        # 2. Zero prices
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE preco = 0")
        result["zero"] = cur.fetchone()[0]

        # 3. NULL prices
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE preco IS NULL")
        result["null_count"] = cur.fetchone()[0]

        # 4. Currency distribution
        cur.execute(f"""
            SELECT moeda, COUNT(*) as cnt
            FROM {table}
            WHERE moeda IS NOT NULL
            GROUP BY moeda
            ORDER BY cnt DESC
        """)
        for row in cur.fetchall():
            result["currencies"][row[0]] = row[1]

        # Also check NULL currencies
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE moeda IS NULL")
        null_moeda = cur.fetchone()[0]
        if null_moeda > 0:
            result["currencies"]["NULL"] = null_moeda

        # 5. Extreme outliers: price > 99th percentile * 10
        cur.execute(f"""
            SELECT percentile_cont(0.99) WITHIN GROUP (ORDER BY preco)
            FROM {table}
            WHERE preco > 0
        """)
        row = cur.fetchone()
        p99 = row[0] if row and row[0] else None

        if p99 and p99 > 0:
            threshold = p99 * 10
            cur.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE preco > %s
            """, (threshold,))
            result["extreme_outliers"] = cur.fetchone()[0]
            result["p99"] = round(float(p99), 2)
            result["outlier_threshold"] = round(float(threshold), 2)

            # Sample 3 extreme outliers
            cur.execute(f"""
                SELECT preco, moeda, fonte,
                       COALESCE(dados_extras->>'loja', fonte) as loja
                FROM {table}
                WHERE preco > %s
                ORDER BY preco DESC
                LIMIT 3
            """, (threshold,))
            for r in cur.fetchall():
                result["extreme_samples"].append({
                    "preco": float(r[0]) if r[0] else None,
                    "moeda": r[1],
                    "fonte": r[2],
                    "loja": r[3],
                })

        # 6. Suspiciously low prices (per currency)
        suspicious_total = 0
        for moeda, min_price in CURRENCY_MINS.items():
            cur.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE moeda = %s AND preco > 0 AND preco < %s
            """, (moeda, min_price))
            cnt = cur.fetchone()[0]
            suspicious_total += cnt
        result["suspicious_low"] = suspicious_total

        # 7. Placeholder prices
        placeholder_total = 0
        for pv in PLACEHOLDERS:
            cur.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE preco = %s
            """, (pv,))
            cnt = cur.fetchone()[0]
            if cnt > 0:
                result["placeholder_detail"][str(pv)] = cnt
                placeholder_total += cnt
        result["placeholders"] = placeholder_total

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    conn = psycopg2.connect(DB_URL)
    conn.set_session(readonly=True)
    cur = conn.cursor()

    all_results = []
    print("=" * 100)
    print("WINEGOD PRICE AUDIT — ALL 50 COUNTRIES")
    print("=" * 100)
    print()

    for i, cc in enumerate(COUNTRIES):
        sys.stdout.write(f"\r  Auditing {cc.upper()} ({i+1}/50)...          ")
        sys.stdout.flush()
        r = audit_country(cur, cc)
        all_results.append(r)

    print("\r  Done — all 50 countries audited.            ")
    print()

    # =========================================================================
    # DETAILED PER-COUNTRY REPORTS
    # =========================================================================
    for r in all_results:
        if r["error"]:
            print(f"\n--- {r['country'].upper()} --- ERROR: {r['error']}")
            continue
        if r["total"] == 0:
            print(f"\n--- {r['country'].upper()} --- EMPTY TABLE (0 records)")
            continue

        problems = r["negative"] + r["zero"] + r["null_count"] + r["extreme_outliers"] + r["suspicious_low"] + r["placeholders"]
        mixed = len([c for c in r["currencies"] if c != "NULL"]) > 1

        print(f"\n{'='*70}")
        print(f"  {r['country'].upper()} — {r['total']:,} records | {problems:,} problems")
        print(f"{'='*70}")
        print(f"  Negative prices:     {r['negative']:>10,}")
        print(f"  Zero prices:         {r['zero']:>10,}")
        print(f"  NULL prices:         {r['null_count']:>10,}")
        print(f"  Suspicious low:      {r['suspicious_low']:>10,}")
        print(f"  Extreme outliers:    {r['extreme_outliers']:>10,}", end="")
        if "p99" in r:
            print(f"  (p99={r['p99']}, threshold={r['outlier_threshold']})")
        else:
            print()
        print(f"  Placeholders:        {r['placeholders']:>10,}")
        if r["placeholder_detail"]:
            for pv, cnt in r["placeholder_detail"].items():
                print(f"      price={pv}: {cnt:,}")
        print(f"  Currencies:          {json.dumps(r['currencies'])}")
        if mixed:
            print(f"  *** MIXED CURRENCIES DETECTED ***")
        if r["extreme_samples"]:
            print(f"  Top outlier samples:")
            for s in r["extreme_samples"]:
                print(f"      {s['moeda']} {s['preco']:,.2f} — {s['loja']} ({s['fonte']})")

    # =========================================================================
    # SUMMARY TABLE
    # =========================================================================
    print("\n\n")
    print("=" * 140)
    print("SUMMARY TABLE")
    print("=" * 140)
    header = f"{'Country':<8} {'Total':>10} {'Negative':>10} {'Zero':>10} {'NULL':>10} {'Mixed$':>8} {'Outliers':>10} {'SuspLow':>10} {'Placehld':>10} {'Problems':>10} {'Prob%':>7}"
    print(header)
    print("-" * 140)

    summary_rows = []
    grand_total = grand_neg = grand_zero = grand_null = grand_out = grand_susp = grand_ph = 0

    for r in all_results:
        if r["error"]:
            print(f"{r['country'].upper():<8} {'ERROR':>10}")
            continue
        total = r["total"]
        neg = r["negative"]
        zero = r["zero"]
        null_c = r["null_count"]
        mixed = "YES" if len([c for c in r["currencies"] if c != "NULL"]) > 1 else "no"
        outliers = r["extreme_outliers"]
        susp = r["suspicious_low"]
        ph = r["placeholders"]
        problems = neg + zero + null_c + outliers + susp + ph
        prob_pct = (problems / total * 100) if total > 0 else 0

        grand_total += total
        grand_neg += neg
        grand_zero += zero
        grand_null += null_c
        grand_out += outliers
        grand_susp += susp
        grand_ph += ph

        row = f"{r['country'].upper():<8} {total:>10,} {neg:>10,} {zero:>10,} {null_c:>10,} {mixed:>8} {outliers:>10,} {susp:>10,} {ph:>10,} {problems:>10,} {prob_pct:>6.1f}%"
        summary_rows.append((problems, prob_pct, row, r))
        print(row)

    grand_problems = grand_neg + grand_zero + grand_null + grand_out + grand_susp + grand_ph
    grand_pct = (grand_problems / grand_total * 100) if grand_total > 0 else 0
    print("-" * 140)
    print(f"{'TOTAL':<8} {grand_total:>10,} {grand_neg:>10,} {grand_zero:>10,} {grand_null:>10,} {'':>8} {grand_out:>10,} {grand_susp:>10,} {grand_ph:>10,} {grand_problems:>10,} {grand_pct:>6.1f}%")

    # =========================================================================
    # TOP 20 WORST COUNTRIES
    # =========================================================================
    print("\n\n")
    print("=" * 140)
    print("TOP 20 WORST COUNTRIES (by total problem count)")
    print("=" * 140)

    summary_rows.sort(key=lambda x: x[0], reverse=True)
    for rank, (problems, prob_pct, row_str, r) in enumerate(summary_rows[:20], 1):
        if r["error"] or r["total"] == 0:
            continue
        print(f"\n{'─'*70}")
        print(f"  #{rank}  {r['country'].upper()} — {problems:,} problems ({prob_pct:.1f}% of {r['total']:,} records)")
        print(f"{'─'*70}")
        print(f"    Negative: {r['negative']:,}  |  Zero: {r['zero']:,}  |  NULL: {r['null_count']:,}")
        print(f"    Suspicious low: {r['suspicious_low']:,}  |  Outliers: {r['extreme_outliers']:,}  |  Placeholders: {r['placeholders']:,}")
        currencies = r["currencies"]
        real_currencies = {k: v for k, v in currencies.items() if k != "NULL"}
        if len(real_currencies) > 1:
            print(f"    MIXED CURRENCIES: {json.dumps(real_currencies)}")
        elif real_currencies:
            main_cur = list(real_currencies.keys())[0]
            print(f"    Currency: {main_cur} ({list(real_currencies.values())[0]:,} records)")
        if "NULL" in currencies:
            print(f"    NULL currency: {currencies['NULL']:,} records")
        if r["placeholder_detail"]:
            parts = [f"{pv}={cnt:,}" for pv, cnt in r["placeholder_detail"].items()]
            print(f"    Placeholder breakdown: {', '.join(parts)}")
        if r["extreme_samples"]:
            print(f"    Top extreme prices:")
            for s in r["extreme_samples"]:
                print(f"      {s['moeda']} {s['preco']:,.2f} — {s['loja']}")

    # =========================================================================
    # MIXED CURRENCY COUNTRIES
    # =========================================================================
    print("\n\n")
    print("=" * 100)
    print("COUNTRIES WITH MIXED CURRENCIES")
    print("=" * 100)
    mixed_found = False
    for r in all_results:
        if r["error"] or r["total"] == 0:
            continue
        real_currencies = {k: v for k, v in r["currencies"].items() if k != "NULL"}
        if len(real_currencies) > 1:
            mixed_found = True
            print(f"\n  {r['country'].upper()} ({r['total']:,} records):")
            for cur_name, cnt in sorted(real_currencies.items(), key=lambda x: -x[1]):
                pct = cnt / r["total"] * 100
                print(f"    {cur_name}: {cnt:,} ({pct:.1f}%)")
    if not mixed_found:
        print("  None found — all countries have a single currency.")

    # =========================================================================
    # SPECIAL: -1 PRICES (common sentinel value)
    # =========================================================================
    print("\n\n")
    print("=" * 100)
    print("SENTINEL VALUE CHECK: price = -1 (per country)")
    print("=" * 100)
    for r_data in all_results:
        cc = r_data["country"]
        if r_data["error"] or r_data["total"] == 0:
            continue
        try:
            table = f"vinhos_{cc}_fontes"
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE preco = -1")
            cnt = cur.fetchone()[0]
            if cnt > 0:
                print(f"  {cc.upper()}: {cnt:,} records with preco = -1")
        except:
            pass

    cur.close()
    conn.close()
    print("\n\nAudit complete.")


if __name__ == "__main__":
    main()
