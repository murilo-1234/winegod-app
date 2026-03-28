#!/usr/bin/env python3
"""
calc_score.py — Calcula WineGod Score (custo-beneficio) para todos os vinhos.

Estrategia: SELECT server-side cursor -> compute Python -> COPY to temp -> UPDATE FROM.
"""

import io
import json
import os
import sys
import time
from statistics import median

import psycopg2

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96"
    "@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod",
)

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


def main():
    t0 = time.time()
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # ---------- Passo 1: Mediana global ----------
    print("1. Calculando mediana global de precos em USD...", flush=True)
    cur.execute("SELECT preco_min, moeda FROM wines WHERE preco_min > 0 AND moeda IS NOT NULL")
    precos_usd = []
    for preco, moeda in cur:
        usd = converter_para_usd(preco, moeda)
        if usd and usd > 0:
            precos_usd.append(usd)
    mediana_usd = round(median(precos_usd), 2)
    print(f"   {len(precos_usd)} precos -> mediana USD {mediana_usd}", flush=True)

    # ---------- Passo 2: Paridade e Capilaridade em bulk ----------
    print("2. Carregando paridade e capilaridade...", flush=True)
    cur.execute("""
        SELECT ws.wine_id, COUNT(DISTINCT s.pais)
        FROM wine_sources ws JOIN stores s ON ws.store_id = s.id
        WHERE s.pais IS NOT NULL GROUP BY ws.wine_id
    """)
    paridade = {wid: n for wid, n in cur}

    cur.execute("SELECT wine_id, COUNT(*) FROM wine_sources GROUP BY wine_id")
    capilaridade = {wid: n for wid, n in cur}
    print(f"   paridade: {len(paridade)}, capilaridade: {len(capilaridade)}", flush=True)

    # ---------- Passo 3: Processar todos os vinhos ----------
    print("3. Processando vinhos...", flush=True)
    cur.execute("SELECT COUNT(*) FROM wines WHERE nota_wcf IS NOT NULL")
    total = cur.fetchone()[0]
    print(f"   Total: {total}", flush=True)

    # Create staging table BEFORE opening server-side cursor
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

    # Use a separate connection for reading (server-side cursor)
    conn_read = psycopg2.connect(DATABASE_URL)
    srv = conn_read.cursor(name="wine_cursor")
    srv.itersize = 10000
    srv.execute("""
        SELECT id, nota_wcf, vivino_reviews, preco_min, moeda
        FROM wines WHERE nota_wcf IS NOT NULL ORDER BY id
    """)

    # Build TSV in memory, flush to COPY every 50K rows
    FLUSH_EVERY = 50000
    buf = io.StringIO()
    count = 0
    total_flushed = 0

    for wine_id, nota_wcf, vivino_reviews, preco_min, moeda in srv:
        nwcf = float(nota_wcf)
        reviews = vivino_reviews or 0

        # Micro-ajustes
        m_paridade = 0.02 if paridade.get(wine_id, 0) >= 3 else 0.00
        m_legado = 0.02 if reviews >= 500 and nwcf >= 4.0 else 0.00
        m_capilaridade = 0.01 if capilaridade.get(wine_id, 0) >= 5 else 0.00
        micro_total = min(m_paridade + m_legado + m_capilaridade, 0.05)

        nota_ajustada = min(round(nwcf + micro_total, 2), 5.00)

        preco_min_usd = converter_para_usd(preco_min, moeda)

        if preco_min_usd and preco_min_usd > 0:
            preco_norm = round(preco_min_usd / mediana_usd, 4)
            score = min(round(nota_ajustada / preco_norm, 2), 5.00) if preco_norm > 0 else nota_ajustada
        else:
            preco_min_usd = None
            preco_norm = None
            score = round(nota_ajustada, 2)

        score = min(score, 5.00)
        score_type = "verified" if reviews >= 100 else "estimated"

        components = json.dumps({
            "nota_wcf": nwcf,
            "micro_ajustes": {
                "avaliacoes": 0.00,
                "paridade": m_paridade,
                "legado": m_legado,
                "capilaridade": m_capilaridade,
                "total": round(micro_total, 2),
            },
            "nota_ajustada": nota_ajustada,
            "preco_min_usd": preco_min_usd,
            "mediana_global_usd": mediana_usd,
            "preco_normalizado": preco_norm,
            "score": score,
        })

        # TSV line: wine_id \t score \t score_type \t components
        buf.write(f"{wine_id}\t{score}\t{score_type}\t{components}\n")
        count += 1

        if count % FLUSH_EVERY == 0:
            buf.seek(0)
            copy_cur = conn.cursor()
            copy_cur.copy_from(buf, "tmp_scores", columns=("wine_id", "score", "score_type", "components"))
            conn.commit()
            copy_cur.close()
            buf.close()
            buf = io.StringIO()

            elapsed = time.time() - t0
            rate = count / elapsed if elapsed > 0 else 0
            pct = count * 100 / total
            print(f"   [{count}/{total}] {pct:.1f}% — {rate:.0f}/sec (COPY flush)", flush=True)

    # Final flush
    if count % FLUSH_EVERY != 0:
        buf.seek(0)
        copy_cur = conn.cursor()
        copy_cur.copy_from(buf, "tmp_scores", columns=("wine_id", "score", "score_type", "components"))
        conn.commit()
        copy_cur.close()
    buf.close()
    srv.close()
    conn_read.close()

    elapsed = time.time() - t0
    print(f"   {count} vinhos processados e copiados em {elapsed:.0f}s", flush=True)

    # ---------- Passo 4: UPDATE wines FROM tmp_scores ----------
    print("4. Atualizando tabela wines...", flush=True)

    # Create index on staging table for faster join
    cur.execute("ANALYZE tmp_scores")
    conn.commit()

    # Do UPDATE in batches by ID range to avoid long locks
    cur.execute("SELECT MIN(wine_id), MAX(wine_id) FROM tmp_scores")
    min_id, max_id = cur.fetchone()

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
        pct = updated * 100 / count
        print(f"   UPDATE [{updated}/{count}] {pct:.1f}% — batch {cid}-{bend}: {batch_n}", flush=True)
        cid += UBATCH

    # Cleanup
    cur.execute("DROP TABLE IF EXISTS tmp_scores")
    conn.commit()

    elapsed = time.time() - t0
    print(f"\nConcluido! {updated} vinhos atualizados em {elapsed:.0f}s", flush=True)

    # ---------- Verificacao ----------
    cur.execute("""
        SELECT
            COUNT(*),
            ROUND(AVG(winegod_score)::numeric, 2),
            MIN(winegod_score),
            MAX(winegod_score),
            SUM(CASE WHEN winegod_score_type = 'verified' THEN 1 ELSE 0 END),
            SUM(CASE WHEN winegod_score_type = 'estimated' THEN 1 ELSE 0 END)
        FROM wines WHERE winegod_score IS NOT NULL
    """)
    r = cur.fetchone()
    print(f"\nResumo:")
    print(f"  Total com score: {r[0]}")
    print(f"  Score medio: {r[1]}")
    print(f"  Min: {r[2]}, Max: {r[3]}")
    print(f"  Verified: {r[4]}, Estimated: {r[5]}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
