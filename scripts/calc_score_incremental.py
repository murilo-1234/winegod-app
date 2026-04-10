#!/usr/bin/env python3
"""
calc_score_incremental.py — Recalcula score para vinhos na fila score_recalc_queue.

Processa pendencias em batches com locking seguro. Para cada vinho alterado:
  1. Recalcula o score do proprio vinho
  2. Enfileira peers do mesmo pais com nota proxima (+/-0.20) para recalculo

Formula: peer_country_note_v1 (identica a calc_score.py)
  score = clamp(nota_base + micro + 0.35 * ln(ref / price), 0, 5)

Uso:
  python scripts/calc_score_incremental.py                    # processa fila
  python scripts/calc_score_incremental.py --sweep            # safety net
  python scripts/calc_score_incremental.py --batch 50         # batch size
  python scripts/calc_score_incremental.py --max-time 300     # time limit (seconds)
"""

import argparse
import bisect
import json
import math
import os
import sys
import time
from statistics import median

import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL environment variable is required.")

# --- Constantes identicas a calc_score.py ---

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
PEER_RECALC_WINDOW = 0.20
MAX_ATTEMPTS = 5


# ------------------------------------------------------------------
# Funcoes de calculo — identicas a calc_score.py
# ------------------------------------------------------------------

def converter_para_usd(preco, moeda):
    if preco is None or moeda is None:
        return None
    p = float(preco)
    if p <= 0:
        return None
    taxa = TAXAS_USD.get(moeda)
    return round(p * taxa, 2) if taxa else None


def compute_nota_base(nota_wcf, vivino_rating, sample_size):
    """Canonical quality note (same logic as display.py / calc_score.py)."""
    nwcf = float(nota_wcf) if nota_wcf is not None else None
    vr = float(vivino_rating) if vivino_rating is not None else None
    ss = int(sample_size) if sample_size is not None else None
    if nwcf is not None and ss is not None and ss >= 25 and vr is not None and vr > 0:
        return round(max(vr - 0.30, min(nwcf, vr + 0.30)), 2)
    if vr is not None and vr > 0:
        return round(vr, 2)
    return None


def compute_nota_source(nota_wcf, vivino_rating, sample_size):
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
    pairs = sorted(zip(prices, weights))
    total = sum(weights)
    cumul = 0.0
    for price, w in pairs:
        cumul += w
        if cumul >= total / 2.0:
            return price
    return pairs[-1][0]


# ------------------------------------------------------------------
# Peer index — identico a calc_score.py
# ------------------------------------------------------------------

def build_peer_index(cur):
    """Build in-memory peer index for all wines with price + nota."""
    cur.execute("""
        SELECT pais_nome, nota_wcf, vivino_rating, nota_wcf_sample_size, preco_min, moeda
        FROM wines
        WHERE preco_min > 0 AND moeda IS NOT NULL
          AND (nota_wcf IS NOT NULL OR (vivino_rating IS NOT NULL AND vivino_rating > 0))
    """)
    country_peers = {}
    country_notas = {}
    all_prices = []
    country_prices = {}

    for pais, nw, vr, ss, pm, mo in cur:
        nb = compute_nota_base(nw, vr, ss)
        pu = converter_para_usd(pm, mo)
        if nb is None or pu is None or pu <= 0:
            continue
        key = pais or "__unknown__"
        if key not in country_peers:
            country_peers[key] = []
            country_prices[key] = []
        country_peers[key].append((nb, pu))
        country_prices[key].append(pu)
        all_prices.append(pu)

    for key in country_peers:
        country_peers[key].sort(key=lambda x: x[0])
        country_notas[key] = [p[0] for p in country_peers[key]]

    global_median = round(median(all_prices), 2) if all_prices else 19.62
    country_medians = {k: round(median(v), 2) for k, v in country_prices.items()}

    return country_peers, country_notas, country_medians, global_median


def find_peer_reference(country_peers, country_notas, target_nota, country,
                        country_medians, global_median):
    """Find peer reference price — returns 5 values (identical to calc_score.py).

    Returns: (ref_price, strategy, window, peer_count, weighting)
    """
    peers = country_peers.get(country)
    if not peers:
        if country in country_medians:
            return country_medians[country], "country_median", None, 0, "none"
        return global_median, "global_median", None, 0, "none"

    notas = country_notas[country]

    for win in [WINDOW_NARROW, WINDOW_WIDE]:
        lo = bisect.bisect_left(notas, target_nota - win)
        hi = bisect.bisect_right(notas, target_nota + win)
        if hi - lo >= MIN_PEERS:
            prices, weights = [], []
            for i in range(lo, hi):
                nota, price = peers[i]
                w = max(1.0 - abs(nota - target_nota) / win, 0.01)
                prices.append(price)
                weights.append(w)
            strategy = "peer_narrow" if win == WINDOW_NARROW else "peer_wide"
            return weighted_median(prices, weights), strategy, win, hi - lo, "triangular"

    if country in country_medians:
        return country_medians[country], "country_median", None, 0, "none"
    return global_median, "global_median", None, 0, "none"


# ------------------------------------------------------------------
# Score de um vinho — mesma semantica do calc_score.py
# ------------------------------------------------------------------

def score_wine(wine_id, cur, peer_index, paridade, capilaridade):
    """Calculate score for a single wine.

    Returns:
      (score, score_type, components) — score/score_type podem ser None
      None — se o vinho nao existe no banco
    """
    country_peers, country_notas, country_medians, global_median = peer_index

    cur.execute("""
        SELECT nota_wcf, vivino_rating, nota_wcf_sample_size, vivino_reviews,
               preco_min, moeda, pais_nome
        FROM wines WHERE id = %s
    """, (wine_id,))
    row = cur.fetchone()
    if not row:
        return None

    nota_wcf, vr, ss, reviews, preco_min, moeda, pais = row
    nota_base = compute_nota_base(nota_wcf, vr, ss)
    nota_source = compute_nota_source(nota_wcf, vr, ss)

    if nota_base is None:
        return (None, None, {
            "formula_version": FORMULA_VERSION,
            "reason_null": "no_quality_note",
        })

    preco_usd = converter_para_usd(preco_min, moeda)
    if not preco_usd or preco_usd <= 0:
        return (None, None, {
            "formula_version": FORMULA_VERSION,
            "nota_base_score": nota_base,
            "nota_base_source": nota_source,
            "reason_null": "no_price",
        })

    reviews = reviews or 0

    # Micro-adjustments (identical to calc_score.py)
    m_par = 0.02 if paridade.get(wine_id, 0) >= 3 else 0.0
    m_leg = 0.02 if reviews >= 500 and nota_base >= 4.0 else 0.0
    m_cap = 0.01 if capilaridade.get(wine_id, 0) >= 5 else 0.0
    micro = min(m_par + m_leg + m_cap, 0.05)

    country = pais or "__unknown__"
    ref_price, strategy, window, peer_count, weighting = find_peer_reference(
        country_peers, country_notas, nota_base, country, country_medians, global_median
    )

    ln_ratio = math.log(ref_price / preco_usd) if ref_price > 0 else 0
    score = round(max(0.0, min(nota_base + micro + LN_COEFF * ln_ratio, 5.00)), 2)
    score_type = "verified" if nota_source == "wcf_verified" else "estimated"

    components = {
        "formula_version": FORMULA_VERSION,
        "nota_base_score": nota_base,
        "nota_base_source": nota_source,
        "preco_min_usd": preco_usd,
        "preco_reference_strategy": strategy,
        "preco_reference_usd": round(ref_price, 2),
        "peer_country": country,
        "peer_window": window,
        "peer_count": peer_count,
        "peer_weighting": weighting,
        "micro_ajustes": {
            "paridade": m_par,
            "legado": m_leg,
            "capilaridade": m_cap,
            "total": round(micro, 2),
        },
        "score": score,
    }

    return (score, score_type, components)


# ------------------------------------------------------------------
# Enfileiramento de peers — corrigido
# ------------------------------------------------------------------

def enqueue_peers(cur, wine_id):
    """Enqueue peers for recalc: same country, nota_base within +/-0.20.

    Uses SQL to pre-filter candidates (vivino_rating/nota_wcf within +/-0.50
    to account for WCF clamp of +/-0.30), then computes nota_base in Python
    to determine actual peers within PEER_RECALC_WINDOW.

    Returns number of peers enqueued.
    """
    cur.execute("""
        SELECT pais_nome, nota_wcf, vivino_rating, nota_wcf_sample_size
        FROM wines WHERE id = %s
    """, (wine_id,))
    row = cur.fetchone()
    if not row:
        return 0

    pais, nw, vr, ss = row
    nota_base = compute_nota_base(nw, vr, ss)
    if nota_base is None or not pais:
        return 0

    # Pre-filter margin: PEER_RECALC_WINDOW (0.20) + WCF clamp range (0.30) = 0.50
    margin = PEER_RECALC_WINDOW + 0.30
    lo = nota_base - margin
    hi = nota_base + margin

    cur.execute("""
        SELECT id, nota_wcf, vivino_rating, nota_wcf_sample_size
        FROM wines
        WHERE pais_nome = %s AND id != %s
          AND preco_min > 0 AND moeda IS NOT NULL
          AND (
            (vivino_rating BETWEEN %s AND %s)
            OR (nota_wcf BETWEEN %s AND %s)
          )
    """, (pais, wine_id, lo, hi, lo, hi))

    peer_ids = []
    for pid, p_nw, p_vr, p_ss in cur:
        p_nota = compute_nota_base(p_nw, p_vr, p_ss)
        if p_nota is not None and abs(p_nota - nota_base) <= PEER_RECALC_WINDOW:
            peer_ids.append(pid)

    if not peer_ids:
        return 0

    execute_values(
        cur,
        """INSERT INTO score_recalc_queue (wine_id, reason) VALUES %s
           ON CONFLICT (wine_id) WHERE processed_at IS NULL DO NOTHING""",
        [(pid, "peer_of_%s" % wine_id) for pid in peer_ids],
    )
    return len(peer_ids)


# ------------------------------------------------------------------
# Claim + Process — com FOR UPDATE SKIP LOCKED
# ------------------------------------------------------------------

def claim_batch(conn, batch_size):
    """Atomically claim pending queue items.

    Uses FOR UPDATE SKIP LOCKED for safe concurrent access.
    Increments attempts on claimed items.
    Returns list of (queue_id, wine_id, reason).
    """
    cur = conn.cursor()
    cur.execute("""
        WITH batch AS (
            SELECT id FROM score_recalc_queue
            WHERE processed_at IS NULL AND attempts < %s
            ORDER BY created_at
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        )
        UPDATE score_recalc_queue q
        SET attempts = q.attempts + 1
        FROM batch b
        WHERE q.id = b.id
        RETURNING q.id, q.wine_id, q.reason
    """, (MAX_ATTEMPTS, batch_size))
    items = cur.fetchall()
    conn.commit()
    cur.close()
    return items


def _update_wine_score(cur, wine_id, score, score_type, components):
    """Apply computed score to wines table."""
    if score is not None:
        cur.execute("""
            UPDATE wines SET winegod_score = %s, winegod_score_type = %s,
                   winegod_score_components = %s::jsonb
            WHERE id = %s
        """, (score, score_type, json.dumps(components), wine_id))
    else:
        cur.execute("""
            UPDATE wines SET winegod_score = NULL, winegod_score_type = NULL,
                   winegod_score_components = %s::jsonb
            WHERE id = %s
        """, (json.dumps(components), wine_id))


def build_scoring_context(conn):
    """Build peer index + paridade + capilaridade once.

    Returns (peer_index, paridade, capilaridade) to be reused across rounds.
    """
    cur = conn.cursor()
    print("Building peer index...", flush=True)
    peer_index = build_peer_index(cur)

    cur.execute("""
        SELECT ws.wine_id, COUNT(DISTINCT s.pais)
        FROM wine_sources ws JOIN stores s ON ws.store_id = s.id
        WHERE s.pais IS NOT NULL GROUP BY ws.wine_id
    """)
    paridade = dict(cur.fetchall())
    cur.execute("SELECT wine_id, COUNT(*) FROM wine_sources GROUP BY wine_id")
    capilaridade = dict(cur.fetchall())
    cur.close()

    return peer_index, paridade, capilaridade


def process_queue(conn, batch_size=100, scoring_ctx=None):
    """Process pending items in score_recalc_queue.

    - Claims batch atomically with FOR UPDATE SKIP LOCKED
    - Processes each item individually (error in one doesn't stop batch)
    - Records attempts and last_error per item
    - Enqueues peers for non-peer items (prevents cascading)
    - Accepts optional scoring_ctx to avoid rebuilding peer index per round

    Returns number of successfully processed items.
    """
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) FROM score_recalc_queue WHERE processed_at IS NULL AND attempts < %s",
        (MAX_ATTEMPTS,))
    pending = cur.fetchone()[0]
    if pending == 0:
        print("No pending items in queue.", flush=True)
        return 0

    print(f"Pending: {pending:,} items", flush=True)

    if scoring_ctx:
        peer_index, paridade, capilaridade = scoring_ctx
    else:
        peer_index, paridade, capilaridade = build_scoring_context(conn)

    # Claim batch with locking
    items = claim_batch(conn, batch_size)
    if not items:
        print("No items could be claimed.", flush=True)
        return 0

    processed = 0
    errors = 0
    peers_enqueued = 0

    for queue_id, wine_id, reason in items:
        try:
            result = score_wine(wine_id, cur, peer_index, paridade, capilaridade)

            if result is None:
                # Wine doesn't exist in DB — mark done
                cur.execute(
                    "UPDATE score_recalc_queue SET processed_at = NOW() WHERE id = %s",
                    (queue_id,))
                conn.commit()
                continue

            score, score_type, components = result
            _update_wine_score(cur, wine_id, score, score_type, components)

            # Enqueue peers only for direct changes (not peer-triggered recalcs)
            if not reason.startswith("peer_of_"):
                n = enqueue_peers(cur, wine_id)
                peers_enqueued += n

            cur.execute(
                "UPDATE score_recalc_queue SET processed_at = NOW(), last_error = NULL WHERE id = %s",
                (queue_id,))
            conn.commit()
            processed += 1

        except Exception as e:
            conn.rollback()
            errors += 1
            error_msg = "%s: %s" % (type(e).__name__, e)
            try:
                cur.execute(
                    "UPDATE score_recalc_queue SET last_error = %s WHERE id = %s",
                    (error_msg[:500], queue_id))
                conn.commit()
            except Exception:
                conn.rollback()

    print(f"Processed {processed}, errors {errors}, peers enqueued {peers_enqueued}.", flush=True)
    return processed


# ------------------------------------------------------------------
# Sweep — safety net
# ------------------------------------------------------------------

def sweep_all_with_price(conn, commit_every=500):
    """Safety net: recalculate scores for ALL wines that have price.

    Uses server-side cursor to avoid loading all IDs into memory.
    """
    cur = conn.cursor()

    print("SWEEP: recalculating all wines with price...", flush=True)
    peer_index = build_peer_index(cur)

    cur.execute("""
        SELECT ws.wine_id, COUNT(DISTINCT s.pais)
        FROM wine_sources ws JOIN stores s ON ws.store_id = s.id
        WHERE s.pais IS NOT NULL GROUP BY ws.wine_id
    """)
    paridade = dict(cur.fetchall())
    cur.execute("SELECT wine_id, COUNT(*) FROM wine_sources GROUP BY wine_id")
    capilaridade = dict(cur.fetchall())

    # Server-side cursor to avoid loading all IDs in memory
    conn_read = psycopg2.connect(DATABASE_URL)
    srv = conn_read.cursor(name="sweep_cursor")
    srv.itersize = 5000
    srv.execute("""
        SELECT id FROM wines
        WHERE preco_min > 0 AND moeda IS NOT NULL
          AND (nota_wcf IS NOT NULL OR (vivino_rating IS NOT NULL AND vivino_rating > 0))
        ORDER BY id
    """)

    updated = 0
    errors = 0
    total = 0

    for (wid,) in srv:
        total += 1
        try:
            result = score_wine(wid, cur, peer_index, paridade, capilaridade)
            if result is None:
                continue
            score, score_type, components = result
            _update_wine_score(cur, wid, score, score_type, components)
            if score is not None:
                updated += 1
        except Exception:
            errors += 1
            conn.rollback()

        if total % commit_every == 0:
            conn.commit()
            print(f"  [{total:,}] {updated:,} updated, {errors} errors", flush=True)

    conn.commit()
    srv.close()
    conn_read.close()
    print(f"SWEEP done: {total:,} scanned, {updated:,} updated, {errors} errors", flush=True)
    return updated


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Incremental WineGod Score recalc")
    parser.add_argument("--sweep", action="store_true",
                        help="Recalculate all wines with price (safety net)")
    parser.add_argument("--batch", type=int, default=100,
                        help="Batch size for queue processing (default 100)")
    parser.add_argument("--max-time", type=int, default=300,
                        help="Max processing time in seconds (default 300)")
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)

    if args.sweep:
        sweep_all_with_price(conn)
    else:
        t0 = time.time()
        ctx = build_scoring_context(conn)
        total = 0
        rounds = 0
        while time.time() - t0 < args.max_time:
            n = process_queue(conn, args.batch, scoring_ctx=ctx)
            total += n
            rounds += 1
            if n == 0:
                break
        elapsed = time.time() - t0
        print(f"Total: {total} wines in {rounds} rounds, {elapsed:.0f}s", flush=True)

    conn.close()


if __name__ == "__main__":
    main()
