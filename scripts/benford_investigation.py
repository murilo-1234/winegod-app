"""
Benford's Law Investigation for 5 countries with worst scores:
  HK (0.32), TH (0.40), TR (0.40), PH (0.26), MX (0.22)

Analyzes vinhos_{cc}_fontes tables. Read-only — no data modifications.
"""

import psycopg2
import numpy as np
from collections import Counter

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

# Expected Benford distribution for first digits 1-9
BENFORD_EXPECTED = {
    1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097,
    5: 0.079, 6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046
}

COUNTRIES = [
    ("hk", "Hong Kong",    0.32),
    ("th", "Thailand",     0.40),
    ("tr", "Turkey",       0.40),
    ("ph", "Philippines",  0.26),
    ("mx", "Mexico",       0.22),
]


def first_digit(price):
    """Extract first non-zero digit from a price."""
    s = f"{price:.2f}".lstrip("0").lstrip(".")
    for ch in s:
        if ch.isdigit() and ch != "0":
            return int(ch)
    return None


def benford_score(digit_counts, total):
    """Compute chi-square-style Benford deviation score (lower = better fit)."""
    if total == 0:
        return None
    score = 0
    for d in range(1, 10):
        observed = digit_counts.get(d, 0) / total
        expected = BENFORD_EXPECTED[d]
        score += abs(observed - expected)
    return round(1 - score, 2)  # normalized so 1.0 = perfect


def analyze_country(cur, cc, name, reported_score):
    table = f"vinhos_{cc}_fontes"
    sep = "=" * 80
    print(f"\n{sep}")
    print(f"  COUNTRY: {name} ({cc.upper()}) — Reported Benford Score: {reported_score}")
    print(f"{sep}")

    # --- 0. Total count ---
    cur.execute(f"SELECT count(*) FROM {table}")
    total = cur.fetchone()[0]
    print(f"\nTotal records: {total:,}")

    # --- 1. Distribution by fonte (store) ---
    print(f"\n{'-'*60}")
    print("1. DISTRIBUTION BY FONTE (store)")
    print(f"{'-'*60}")
    cur.execute(f"""
        SELECT fonte,
               count(*) as cnt,
               round(avg(preco)::numeric, 2) as avg_price,
               round(min(preco)::numeric, 2) as min_price,
               round(max(preco)::numeric, 2) as max_price
        FROM {table}
        WHERE preco IS NOT NULL AND preco > 0
        GROUP BY fonte
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    print(f"{'Fonte':<40} {'Count':>8} {'Avg Price':>12} {'Min':>10} {'Max':>12}")
    print("-" * 82)
    for r in rows:
        print(f"{(r[0] or 'NULL')[:39]:<40} {r[1]:>8,} {r[2]:>12} {r[3]:>10} {r[4]:>12}")

    # --- 2. Distribution by moeda (currency) ---
    print(f"\n{'-'*60}")
    print("2. DISTRIBUTION BY MOEDA (currency)")
    print(f"{'-'*60}")
    cur.execute(f"""
        SELECT moeda, count(*) as cnt
        FROM {table}
        GROUP BY moeda
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    print(f"{'Moeda':<20} {'Count':>10} {'%':>8}")
    print("-" * 40)
    for r in rows:
        pct = (r[1] / total * 100) if total > 0 else 0
        print(f"{(r[0] or 'NULL'):<20} {r[1]:>10,} {pct:>7.1f}%")

    # --- 3. Sample 10 records ---
    print(f"\n{'-'*60}")
    print("3. SAMPLE 10 RECORDS")
    print(f"{'-'*60}")
    cur.execute(f"""
        SELECT id, fonte, preco, moeda, url_original
        FROM {table}
        WHERE preco IS NOT NULL AND preco > 0
        ORDER BY random()
        LIMIT 10
    """)
    rows = cur.fetchall()
    print(f"{'ID':>8} {'Fonte':<25} {'Preco':>12} {'Moeda':<6} {'URL (truncated)':<50}")
    print("-" * 105)
    for r in rows:
        url_short = (r[4] or "")[:49]
        print(f"{r[0]:>8} {(r[1] or '')[:24]:<25} {r[2]:>12.2f} {(r[3] or ''):<6} {url_short}")

    # --- 4. Benford first-digit histogram ---
    print(f"\n{'-'*60}")
    print("4. BENFORD FIRST-DIGIT ANALYSIS")
    print(f"{'-'*60}")
    cur.execute(f"""
        SELECT preco FROM {table}
        WHERE preco IS NOT NULL AND preco > 0
    """)
    prices = [row[0] for row in cur.fetchall()]
    digits = [first_digit(p) for p in prices if first_digit(p) is not None]
    digit_counts = Counter(digits)
    total_digits = len(digits)

    print(f"\nTotal prices analyzed: {total_digits:,}")
    print(f"\n{'Digit':>6} {'Count':>10} {'Observed%':>10} {'Benford%':>10} {'Diff':>8} {'Status':<15}")
    print("-" * 65)
    for d in range(1, 10):
        cnt = digit_counts.get(d, 0)
        obs_pct = (cnt / total_digits * 100) if total_digits > 0 else 0
        exp_pct = BENFORD_EXPECTED[d] * 100
        diff = obs_pct - exp_pct
        if abs(diff) > 5:
            status = "*** MAJOR ***"
        elif abs(diff) > 2:
            status = "* moderate *"
        else:
            status = "OK"
        print(f"{d:>6} {cnt:>10,} {obs_pct:>9.1f}% {exp_pct:>9.1f}% {diff:>+7.1f}% {status}")

    computed_score = benford_score(digit_counts, total_digits)
    print(f"\nComputed Benford score: {computed_score}")

    # --- 4b. Benford by fonte ---
    print(f"\n  Benford breakdown BY FONTE:")
    cur.execute(f"SELECT DISTINCT fonte FROM {table} WHERE preco > 0 AND preco IS NOT NULL")
    fontes = [r[0] for r in cur.fetchall()]
    for fonte in sorted(fontes, key=lambda x: x or ""):
        cur.execute(f"""
            SELECT preco FROM {table}
            WHERE preco IS NOT NULL AND preco > 0 AND fonte = %s
        """, (fonte,))
        fp = [row[0] for row in cur.fetchall()]
        fd = [first_digit(p) for p in fp if first_digit(p) is not None]
        if len(fd) < 10:
            continue
        fc = Counter(fd)
        bs = benford_score(fc, len(fd))
        # Find the most over-represented digit
        worst_digit = None
        worst_diff = 0
        for d in range(1, 10):
            obs = fc.get(d, 0) / len(fd)
            exp = BENFORD_EXPECTED[d]
            if abs(obs - exp) > abs(worst_diff):
                worst_diff = obs - exp
                worst_digit = d
        print(f"    {(fonte or 'NULL')[:35]:<36} n={len(fd):>7,}  score={bs}  worst_digit={worst_digit}({worst_diff:+.2f})")

    # --- 5. Round number clustering ---
    print(f"\n{'-'*60}")
    print("5. ROUND NUMBER CLUSTERING")
    print(f"{'-'*60}")

    # Check prices ending in common round patterns
    round_targets = [9, 49, 50, 89, 90, 95, 99, 100, 149, 150, 199, 200, 249, 250,
                     299, 300, 349, 399, 400, 449, 499, 500, 599, 699, 799, 899, 999,
                     1000, 1499, 1999, 2000, 2999, 4999, 5000, 9999]

    # Integer prices
    int_prices = [int(round(p)) for p in prices]
    int_counter = Counter(int_prices)
    most_common_prices = int_counter.most_common(25)

    print("\n  Top 25 most common prices (rounded to integer):")
    print(f"  {'Price':>10} {'Count':>8} {'%':>7}")
    print("  " + "-" * 28)
    for price, cnt in most_common_prices:
        pct = cnt / len(prices) * 100
        print(f"  {price:>10,} {cnt:>8,} {pct:>6.2f}%")

    # Prices ending in .99, .00, .50
    endings_99 = sum(1 for p in prices if abs(p - round(p) + 0.01) < 0.02)  # x.99
    endings_00 = sum(1 for p in prices if abs(p - round(p)) < 0.02)  # x.00
    endings_50 = sum(1 for p in prices if abs((p % 1) - 0.50) < 0.02)  # x.50
    endings_95 = sum(1 for p in prices if abs((p % 1) - 0.95) < 0.02)  # x.95

    print(f"\n  Price endings analysis:")
    print(f"    Ending .99: {endings_99:>8,} ({endings_99/len(prices)*100:.1f}%)")
    print(f"    Ending .00: {endings_00:>8,} ({endings_00/len(prices)*100:.1f}%)")
    print(f"    Ending .50: {endings_50:>8,} ({endings_50/len(prices)*100:.1f}%)")
    print(f"    Ending .95: {endings_95:>8,} ({endings_95/len(prices)*100:.1f}%)")

    # Check for "charm pricing" at X99, X999 boundaries
    charm_prices = sum(1 for p in int_prices if p % 100 == 99 or p % 1000 == 999)
    print(f"    Charm pricing (ends 99/999): {charm_prices:>6,} ({charm_prices/len(prices)*100:.1f}%)")

    # --- 6. Median price per fonte ---
    print(f"\n{'-'*60}")
    print("6. MEDIAN PRICE PER FONTE")
    print(f"{'-'*60}")
    cur.execute(f"""
        SELECT fonte,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY preco) as median_price,
               percentile_cont(0.25) WITHIN GROUP (ORDER BY preco) as p25,
               percentile_cont(0.75) WITHIN GROUP (ORDER BY preco) as p75,
               count(*) as cnt
        FROM {table}
        WHERE preco IS NOT NULL AND preco > 0
        GROUP BY fonte
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    print(f"{'Fonte':<40} {'Median':>10} {'P25':>10} {'P75':>10} {'Count':>8}")
    print("-" * 80)
    for r in rows:
        print(f"{(r[0] or 'NULL')[:39]:<40} {r[1]:>10.2f} {r[2]:>10.2f} {r[3]:>10.2f} {r[4]:>8,}")

    # --- Extra: Price range distribution to understand scale ---
    print(f"\n  Price range distribution:")
    ranges = [(0, 10), (10, 50), (50, 100), (100, 500), (500, 1000),
              (1000, 5000), (5000, 10000), (10000, 50000), (50000, 100000), (100000, float('inf'))]
    for lo, hi in ranges:
        cnt = sum(1 for p in prices if lo < p <= hi)
        if cnt > 0:
            pct = cnt / len(prices) * 100
            label = f"({lo:>8,} - {hi:>8,}]" if hi != float('inf') else f"({lo:>8,} - inf)"
            print(f"    {label}  {cnt:>8,}  ({pct:>5.1f}%)")


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("=" * 80)
    print("  BENFORD'S LAW INVESTIGATION — 5 WORST-SCORING COUNTRIES")
    print("  HK (0.32), TH (0.40), TR (0.40), PH (0.26), MX (0.22)")
    print("=" * 80)

    for cc, name, score in COUNTRIES:
        analyze_country(cur, cc, name, score)

    # --- SUMMARY ---
    print("\n\n" + "=" * 80)
    print("  CROSS-COUNTRY SUMMARY")
    print("=" * 80)

    for cc, name, score in COUNTRIES:
        table = f"vinhos_{cc}_fontes"
        cur.execute(f"SELECT count(*), count(DISTINCT fonte), count(DISTINCT moeda) FROM {table} WHERE preco > 0")
        r = cur.fetchone()
        print(f"\n  {name} ({cc.upper()}) — Benford={score}")
        print(f"    Records: {r[0]:,}, Stores: {r[1]}, Currencies: {r[2]}")

        cur.execute(f"SELECT preco FROM {table} WHERE preco > 0")
        prices = [row[0] for row in cur.fetchall()]
        digits = [first_digit(p) for p in prices if first_digit(p) is not None]
        dc = Counter(digits)
        td = len(digits)

        # Find top 3 deviations
        devs = []
        for d in range(1, 10):
            obs = dc.get(d, 0) / td if td > 0 else 0
            exp = BENFORD_EXPECTED[d]
            devs.append((d, obs - exp))
        devs.sort(key=lambda x: abs(x[1]), reverse=True)
        top3 = devs[:3]
        print(f"    Top deviations: ", end="")
        for d, diff in top3:
            print(f"digit {d}: {diff:+.1%}  ", end="")
        print()

    conn.close()
    print("\n\nDone.")


if __name__ == "__main__":
    main()
