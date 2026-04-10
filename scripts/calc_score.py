#!/usr/bin/env python3
"""
calc_score.py — Calcula WineGod Score (custo-beneficio) para todos os vinhos.

Formula v2 (peer_country_note_v1):
  score = clamp(nota_base + micro + 0.35 * ln(preco_ref / preco_wine), 0, 5)

Referencia de preco por pares:
  1. Mesmo pais + nota ±0.10 com peso triangular (min 20 pares)
  2. Mesmo pais + nota ±0.20 com peso triangular (min 20 pares)
  3. Mediana do pais
  4. Mediana global

Sem preco valido: winegod_score = NULL
"""

import bisect
import io
import json
import math
import os
import sys
import time
from statistics import median

import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL environment variable is required.")

TAXAS_USD = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "BRL": 0.18,
    "ARS": 0.001, "CLP": 0.001, "MXN": 0.058, "COP": 0.00025,
    "AUD": 0.65, "NZD": 0.60, "CAD": 0.74, "CHF": 1.12,
    "JPY": 0.0067, "KRW": 0.00075, "CNY": 0.14, "HKD": 0.13,
    "SGD": 0.75, "TWD": 0.031, "THB": 0.028, "INR": 0.012,
    "ZAR": 0.055, "SEK": 0.096, "NOK": 0.093, "DKK": 0.145,
    "PLN": 0.25, "CZK": 0.043, "HUF": 0.0027, "RON": 0.22,
    "TRY": 0.031, "ILS": 0.28, "AED": 0.27, "RUB": 0.011,
    "GEL": 0.37, "HRK": 0.14, "BGN": 0.55, "PEN": 0.27,
    "UYU": 0.024, "PHP": 0.018, "MDL": 0.056,
}

FORMULA_VERSION = "peer_country_note_v1"
MIN_PEERS = 20
WINDOW_NARROW = 0.10
WINDOW_WIDE = 0.20
LN_COEFF = 0.35


def converter_para_usd(preco, moeda):
    if preco is None or moeda is None:
        return None
    p = float(preco)
    if p <= 0:
        return None
    taxa = TAXAS_USD.get(moeda)
    if taxa is None:
        return None
    return round(p * taxa, 2)


def compute_nota_base(nota_wcf, vivino_rating, sample_size):
    """Canonical quality note (same logic as backend/services/display.py).

    Rules:
      1/2. WCF capped by vivino ±0.30 when sample >= 25
      3.   Vivino fallback
      4.   None
    """
    nwcf = float(nota_wcf) if nota_wcf is not None else None
    vr = float(vivino_rating) if vivino_rating is not None else None
    ss = int(sample_size) if sample_size is not None else None

    if nwcf is not None and ss is not None and ss >= 25 and vr is not None and vr > 0:
        return round(max(vr - 0.30, min(nwcf, vr + 0.30)), 2)
    if vr is not None and vr > 0:
        return round(vr, 2)
    return None


def compute_nota_base_source(nota_wcf, vivino_rating, sample_size):
    """Determine source label for nota_base."""
    nwcf = nota_wcf is not None
    vr = vivino_rating is not None and float(vivino_rating) > 0
    ss = int(sample_size) if sample_size is not None else None

    if nwcf and ss is not None and ss >= 100 and vr:
        return "wcf_verified"
    if nwcf and ss is not None and ss >= 25 and vr:
        return "wcf_estimated"
    if vr:
        return "vivino"
    return None


def weighted_median(prices, weights):
    """Weighted median: sort by price, find value at cumulative weight >= 50%."""
    pairs = sorted(zip(prices, weights))
    total = sum(weights)
    cumul = 0.0
    for price, w in pairs:
        cumul += w
        if cumul >= total / 2.0:
            return price
    return pairs[-1][0]


def find_peer_reference(country_peers, country_notas, target_nota, country,
                        country_medians, global_median):
    """Find peer reference price using hierarchical fallback.

    Args:
        country_peers: dict[country] -> list of (nota, price_usd) sorted by nota
        country_notas: dict[country] -> sorted list of notas (for bisect)
        target_nota: canonical quality note of the wine being scored
        country: pais_nome
        country_medians: dict[country] -> median price USD
        global_median: global median price USD

    Returns:
        (price_ref, strategy, window, peer_count, weighting)
    """
    peers = country_peers.get(country)
    if not peers:
        if country in country_medians:
            return country_medians[country], "country_median", None, 0, "none"
        return global_median, "global_median", None, 0, "none"

    notas = country_notas[country]

    # Try narrow window (±0.10)
    result = _try_window(peers, notas, target_nota, WINDOW_NARROW)
    if result and result[1] >= MIN_PEERS:
        return result[0], "peer_narrow", WINDOW_NARROW, result[1], "triangular"

    # Try wide window (±0.20)
    result = _try_window(peers, notas, target_nota, WINDOW_WIDE)
    if result and result[1] >= MIN_PEERS:
        return result[0], "peer_wide", WINDOW_WIDE, result[1], "triangular"

    # Country median
    if country in country_medians:
        return country_medians[country], "country_median", None, 0, "none"

    return global_median, "global_median", None, 0, "none"


def _try_window(peers, notas, target, window):
    """Find peers within [target-window, target+window] and compute weighted median."""
    lo = bisect.bisect_left(notas, target - window)
    hi = bisect.bisect_right(notas, target + window)

    count = hi - lo
    if count < MIN_PEERS:
        return None

    prices = []
    weights = []
    for i in range(lo, hi):
        nota, price = peers[i]
        dist = abs(nota - target)
        w = max(1.0 - dist / window, 0.01)  # triangular kernel, min 0.01
        prices.append(price)
        weights.append(w)

    return weighted_median(prices, weights), count


def main():
    t0 = time.time()
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # ========== Step 1: Build peer index ==========
    print("1. Building peer index (country + nota + price)...", flush=True)
    cur.execute("""
        SELECT pais_nome, nota_wcf, vivino_rating, nota_wcf_sample_size, preco_min, moeda
        FROM wines
        WHERE preco_min > 0 AND moeda IS NOT NULL
          AND (nota_wcf IS NOT NULL OR (vivino_rating IS NOT NULL AND vivino_rating > 0))
    """)

    country_peers = {}      # country -> [(nota, price_usd)] sorted by nota
    country_notas = {}      # country -> [nota] sorted (for bisect)
    all_prices_usd = []
    country_prices = {}     # country -> [price_usd] for median fallback

    for pais, nota_wcf, vr, ss, preco_min, moeda in cur:
        nb = compute_nota_base(nota_wcf, vr, ss)
        price_usd = converter_para_usd(preco_min, moeda)
        if nb is None or price_usd is None or price_usd <= 0:
            continue

        key = pais or "__unknown__"
        if key not in country_peers:
            country_peers[key] = []
            country_prices[key] = []
        country_peers[key].append((nb, price_usd))
        country_prices[key].append(price_usd)
        all_prices_usd.append(price_usd)

    # Sort peer lists by nota for binary search
    for key in country_peers:
        country_peers[key].sort(key=lambda x: x[0])
        country_notas[key] = [p[0] for p in country_peers[key]]

    global_median_usd = round(median(all_prices_usd), 2) if all_prices_usd else 19.62
    country_medians = {k: round(median(v), 2) for k, v in country_prices.items()}

    total_peers = sum(len(v) for v in country_peers.values())
    print(f"   {total_peers:,} peers across {len(country_peers)} countries", flush=True)
    print(f"   Global median: USD {global_median_usd}", flush=True)

    # ========== Step 2: Load paridade + capilaridade ==========
    print("2. Loading paridade + capilaridade...", flush=True)
    cur.execute("""
        SELECT ws.wine_id, COUNT(DISTINCT s.pais)
        FROM wine_sources ws JOIN stores s ON ws.store_id = s.id
        WHERE s.pais IS NOT NULL GROUP BY ws.wine_id
    """)
    paridade = {wid: n for wid, n in cur}

    cur.execute("SELECT wine_id, COUNT(*) FROM wine_sources GROUP BY wine_id")
    capilaridade = {wid: n for wid, n in cur}
    print(f"   paridade: {len(paridade):,}, capilaridade: {len(capilaridade):,}", flush=True)

    # ========== Step 3: Process all wines ==========
    print("3. Processing wines...", flush=True)
    cur.execute("SELECT COUNT(*) FROM wines WHERE nota_wcf IS NOT NULL")
    total = cur.fetchone()[0]
    print(f"   Total: {total:,}", flush=True)

    # Staging table
    cur.execute("DROP TABLE IF EXISTS tmp_scores")
    cur.execute("""
        CREATE UNLOGGED TABLE tmp_scores (
            wine_id INTEGER PRIMARY KEY,
            score NUMERIC(5,2),
            score_type VARCHAR(10),
            components TEXT
        )
    """)
    conn.commit()

    # Server-side cursor
    conn_read = psycopg2.connect(DATABASE_URL)
    srv = conn_read.cursor(name="wine_cursor")
    srv.itersize = 10000
    srv.execute("""
        SELECT id, nota_wcf, vivino_rating, nota_wcf_sample_size, vivino_reviews,
               preco_min, moeda, pais_nome
        FROM wines WHERE nota_wcf IS NOT NULL ORDER BY id
    """)

    FLUSH_EVERY = 50000
    buf = io.StringIO()
    count = 0
    stats = {"with_price": 0, "no_price": 0, "no_nota": 0, "strategies": {}}

    for wine_id, nota_wcf, vivino_rating, sample_size, vivino_reviews, preco_min, moeda, pais_nome in srv:
        nota_base = compute_nota_base(nota_wcf, vivino_rating, sample_size)
        nota_source = compute_nota_base_source(nota_wcf, vivino_rating, sample_size)

        if nota_base is None:
            stats["no_nota"] += 1
            components = json.dumps({
                "formula_version": FORMULA_VERSION,
                "nota_base_score": None,
                "nota_base_source": None,
                "reason_null": "no_quality_note",
            })
            buf.write(f"{wine_id}\t\\N\t\\N\t{components}\n")
            count += 1
            if count % FLUSH_EVERY == 0:
                _flush(buf, conn, count, total, t0)
                buf = io.StringIO()
            continue

        reviews = vivino_reviews or 0

        # Micro-adjustments
        m_paridade = 0.02 if paridade.get(wine_id, 0) >= 3 else 0.00
        m_legado = 0.02 if reviews >= 500 and nota_base >= 4.0 else 0.00
        m_capilaridade = 0.01 if capilaridade.get(wine_id, 0) >= 5 else 0.00
        micro_total = min(m_paridade + m_legado + m_capilaridade, 0.05)

        preco_min_usd = converter_para_usd(preco_min, moeda)

        if not preco_min_usd or preco_min_usd <= 0:
            stats["no_price"] += 1
            components = json.dumps({
                "formula_version": FORMULA_VERSION,
                "nota_base_score": nota_base,
                "nota_base_source": nota_source,
                "preco_min_usd": None,
                "reason_null": "no_price",
                "micro_ajustes": {
                    "paridade": m_paridade,
                    "legado": m_legado,
                    "capilaridade": m_capilaridade,
                    "total": round(micro_total, 2),
                },
            })
            buf.write(f"{wine_id}\t\\N\t\\N\t{components}\n")
            count += 1
            if count % FLUSH_EVERY == 0:
                _flush(buf, conn, count, total, t0)
                buf = io.StringIO()
            continue

        stats["with_price"] += 1

        # Peer reference price
        country = pais_nome or "__unknown__"
        ref_price, strategy, window, peer_count, weighting = find_peer_reference(
            country_peers, country_notas, nota_base, country,
            country_medians, global_median_usd
        )
        stats["strategies"][strategy] = stats["strategies"].get(strategy, 0) + 1

        # Score formula: nota_base + micro + 0.35 * ln(ref / price)
        ln_ratio = math.log(ref_price / preco_min_usd) if ref_price > 0 else 0
        raw = nota_base + micro_total + LN_COEFF * ln_ratio
        score = round(max(0.0, min(raw, 5.00)), 2)

        score_type = "verified" if nota_source == "wcf_verified" else "estimated"

        components = json.dumps({
            "formula_version": FORMULA_VERSION,
            "nota_base_score": nota_base,
            "nota_base_source": nota_source,
            "preco_min_usd": preco_min_usd,
            "preco_reference_strategy": strategy,
            "preco_reference_usd": round(ref_price, 2),
            "peer_country": country,
            "peer_window": window,
            "peer_count": peer_count,
            "peer_weighting": weighting,
            "micro_ajustes": {
                "paridade": m_paridade,
                "legado": m_legado,
                "capilaridade": m_capilaridade,
                "total": round(micro_total, 2),
            },
            "score": score,
        })

        buf.write(f"{wine_id}\t{score}\t{score_type}\t{components}\n")
        count += 1

        if count % FLUSH_EVERY == 0:
            _flush(buf, conn, count, total, t0)
            buf = io.StringIO()

    # Final flush
    if buf.tell() > 0:
        _flush(buf, conn, count, total, t0)
    buf.close()
    srv.close()
    conn_read.close()

    elapsed = time.time() - t0
    print(f"   {count:,} wines processed in {elapsed:.0f}s", flush=True)
    print(f"   With price: {stats['with_price']:,}", flush=True)
    print(f"   No price (NULL score): {stats['no_price']:,}", flush=True)
    print(f"   No nota (NULL score): {stats['no_nota']:,}", flush=True)
    print(f"   Strategies: {json.dumps(stats['strategies'], indent=2)}", flush=True)

    # ========== Step 4: UPDATE wines FROM tmp_scores ==========
    print("4. Updating wines table...", flush=True)
    cur.execute("ANALYZE tmp_scores")
    conn.commit()

    cur.execute("SELECT MIN(wine_id), MAX(wine_id) FROM tmp_scores")
    min_id, max_id = cur.fetchone()

    if min_id is None:
        print("   No rows to update.", flush=True)
    else:
        UBATCH = 100000
        updated = 0
        cid = min_id

        while cid <= max_id:
            bend = cid + UBATCH - 1
            cur.execute("""
                UPDATE wines w
                SET winegod_score = t.score,
                    winegod_score_type = t.score_type,
                    winegod_score_components = t.components::jsonb
                FROM tmp_scores t
                WHERE w.id = t.wine_id
                  AND t.wine_id BETWEEN %s AND %s
            """, (cid, bend))
            batch_n = cur.rowcount
            conn.commit()
            updated += batch_n

            elapsed = time.time() - t0
            pct = updated * 100 / count if count > 0 else 0
            print(f"   UPDATE [{updated:,}/{count:,}] {pct:.1f}% — batch {cid}-{bend}: {batch_n:,}", flush=True)
            cid += UBATCH

        print(f"   {updated:,} wines updated", flush=True)

    # Cleanup
    cur.execute("DROP TABLE IF EXISTS tmp_scores")
    conn.commit()

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s", flush=True)

    # ========== Verification ==========
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE winegod_score IS NOT NULL),
            COUNT(*) FILTER (WHERE winegod_score IS NULL AND nota_wcf IS NOT NULL),
            ROUND(AVG(winegod_score)::numeric, 2),
            MIN(winegod_score),
            MAX(winegod_score),
            COUNT(*) FILTER (WHERE winegod_score = 5.00),
            COUNT(*) FILTER (WHERE winegod_score_type = 'verified'),
            COUNT(*) FILTER (WHERE winegod_score_type = 'estimated')
        FROM wines
    """)
    r = cur.fetchone()
    print(f"\nSummary:")
    print(f"  With score:       {r[0]:,}")
    print(f"  NULL (has wcf):   {r[1]:,}")
    print(f"  Avg score:        {r[2]}")
    print(f"  Min: {r[3]}, Max: {r[4]}")
    print(f"  Score = 5.00:     {r[5]:,}")
    print(f"  Verified:         {r[6]:,}")
    print(f"  Estimated:        {r[7]:,}")

    cur.close()
    conn.close()


def _flush(buf, conn, count, total, t0):
    """Flush TSV buffer to tmp_scores via COPY."""
    buf.seek(0)
    copy_cur = conn.cursor()
    copy_cur.copy_from(buf, "tmp_scores",
                       columns=("wine_id", "score", "score_type", "components"),
                       null="\\N")
    conn.commit()
    copy_cur.close()
    elapsed = time.time() - t0
    rate = count / elapsed if elapsed > 0 else 0
    pct = count * 100 / total if total > 0 else 0
    print(f"   [{count:,}/{total:,}] {pct:.1f}% — {rate:.0f}/sec (COPY flush)", flush=True)


if __name__ == "__main__":
    main()
