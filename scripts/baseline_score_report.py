#!/usr/bin/env python3
"""
baseline_score_report.py — Captura snapshot do score ANTES da nova formula.
Gera relatorio em reports/baseline_score_before.txt
"""

import os
import sys
import time

import psycopg2
import _env

DATABASE_URL = os.environ["DATABASE_URL"]

REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
REPORT_PATH = os.path.join(REPORT_DIR, "baseline_score_before.txt")


def main():
    os.makedirs(REPORT_DIR, exist_ok=True)
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    lines = []

    def log(msg=""):
        safe = msg.encode("ascii", "replace").decode("ascii")
        print(safe, flush=True)
        lines.append(msg)

    log("=" * 60)
    log("BASELINE SCORE REPORT — ANTES da nova formula")
    log(f"Data: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    log("=" * 60)

    # 1. Distribuicao geral
    log("\n--- 1. DISTRIBUICAO GERAL DO WINEGOD_SCORE ---")
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE winegod_score IS NOT NULL) AS com_score,
            COUNT(*) FILTER (WHERE winegod_score IS NULL) AS sem_score,
            COUNT(*) AS total,
            ROUND(AVG(winegod_score)::numeric, 2) AS media,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY winegod_score)::numeric, 2) AS mediana,
            MIN(winegod_score) AS minimo,
            MAX(winegod_score) AS maximo,
            ROUND(STDDEV(winegod_score)::numeric, 2) AS desvio
        FROM wines
    """)
    r = cur.fetchone()
    log(f"  Total wines:    {r[2]:,}")
    log(f"  Com score:      {r[0]:,}")
    log(f"  Sem score:      {r[1]:,}")
    log(f"  Media:          {r[3]}")
    log(f"  Mediana:        {r[4]}")
    log(f"  Min:            {r[5]}")
    log(f"  Max:            {r[6]}")
    log(f"  Desvio padrao:  {r[7]}")

    # 2. Quantos em 5.00
    log("\n--- 2. SATURACAO EM 5.00 ---")
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE winegod_score = 5.00) AS score_500,
            COUNT(*) FILTER (WHERE winegod_score >= 4.90) AS score_490,
            COUNT(*) FILTER (WHERE winegod_score >= 4.50) AS score_450,
            COUNT(*) FILTER (WHERE winegod_score IS NOT NULL) AS total
        FROM wines
    """)
    r = cur.fetchone()
    total_score = r[3] or 1
    log(f"  Score = 5.00:   {r[0]:,} ({r[0]*100/total_score:.1f}%)")
    log(f"  Score >= 4.90:  {r[1]:,} ({r[1]*100/total_score:.1f}%)")
    log(f"  Score >= 4.50:  {r[2]:,} ({r[2]*100/total_score:.1f}%)")

    # 3. Score por faixa de preco
    log("\n--- 3. SCORE POR FAIXA DE PRECO (USD) ---")
    cur.execute("""
        WITH prices AS (
            SELECT winegod_score,
                   CASE moeda
                       WHEN 'USD' THEN preco_min
                       WHEN 'EUR' THEN preco_min * 1.08
                       WHEN 'GBP' THEN preco_min * 1.27
                       WHEN 'BRL' THEN preco_min * 0.18
                       WHEN 'AUD' THEN preco_min * 0.65
                       WHEN 'CAD' THEN preco_min * 0.74
                       WHEN 'CHF' THEN preco_min * 1.12
                       ELSE NULL
                   END AS price_usd
            FROM wines
            WHERE winegod_score IS NOT NULL AND preco_min > 0
        )
        SELECT
            CASE
                WHEN price_usd < 10 THEN '< $10'
                WHEN price_usd < 20 THEN '$10-$20'
                WHEN price_usd < 50 THEN '$20-$50'
                WHEN price_usd < 100 THEN '$50-$100'
                ELSE '$100+'
            END AS faixa,
            COUNT(*),
            ROUND(AVG(winegod_score)::numeric, 2),
            ROUND(MIN(winegod_score)::numeric, 2),
            ROUND(MAX(winegod_score)::numeric, 2)
        FROM prices
        WHERE price_usd IS NOT NULL
        GROUP BY 1
        ORDER BY MIN(price_usd)
    """)
    log(f"  {'Faixa':<12} {'Count':>8} {'Media':>8} {'Min':>8} {'Max':>8}")
    for row in cur.fetchall():
        log(f"  {row[0]:<12} {row[1]:>8,} {row[2]:>8} {row[3]:>8} {row[4]:>8}")

    # 4. Score com preco vs sem preco
    log("\n--- 4. SCORE COM PRECO vs SEM PRECO ---")
    cur.execute("""
        SELECT
            CASE WHEN preco_min > 0 AND moeda IS NOT NULL THEN 'com_preco' ELSE 'sem_preco' END AS grupo,
            COUNT(*),
            ROUND(AVG(winegod_score)::numeric, 2),
            COUNT(*) FILTER (WHERE winegod_score = 5.00)
        FROM wines
        WHERE winegod_score IS NOT NULL
        GROUP BY 1
    """)
    for row in cur.fetchall():
        log(f"  {row[0]}: {row[1]:,} vinhos, media {row[2]}, saturados 5.00: {row[3]:,}")

    # 5. Score type distribution
    log("\n--- 5. DISTRIBUICAO POR SCORE TYPE ---")
    cur.execute("""
        SELECT winegod_score_type, COUNT(*)
        FROM wines
        WHERE winegod_score IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
    """)
    for row in cur.fetchall():
        log(f"  {row[0]}: {row[1]:,}")

    # 6. Histograma do score
    log("\n--- 6. HISTOGRAMA DO SCORE ---")
    cur.execute("""
        SELECT
            ROUND(winegod_score::numeric, 1) AS bin,
            COUNT(*)
        FROM wines
        WHERE winegod_score IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """)
    for row in cur.fetchall():
        bar = "#" * min(int(row[1] / 200), 60)
        log(f"  {float(row[0]):>4.1f}: {row[1]:>8,} {bar}")

    # 7. Exemplos concretos
    log("\n--- 7. EXEMPLOS CONCRETOS ---")
    log("\n  Top 5 scores mais altos COM preco:")
    cur.execute("""
        SELECT id, nome, winegod_score, nota_wcf, vivino_rating, preco_min, moeda
        FROM wines
        WHERE winegod_score IS NOT NULL AND preco_min > 0
        ORDER BY winegod_score DESC
        LIMIT 5
    """)
    for row in cur.fetchall():
        log(f"    ID {row[0]}: {row[1][:50]} | score={row[2]} | wcf={row[3]} | viv={row[4]} | {row[5]} {row[6]}")

    log("\n  Top 5 scores mais altos SEM preco:")
    cur.execute("""
        SELECT id, nome, winegod_score, nota_wcf, vivino_rating, preco_min, moeda
        FROM wines
        WHERE winegod_score IS NOT NULL AND (preco_min IS NULL OR preco_min = 0)
        ORDER BY winegod_score DESC
        LIMIT 5
    """)
    for row in cur.fetchall():
        log(f"    ID {row[0]}: {row[1][:50]} | score={row[2]} | wcf={row[3]} | viv={row[4]} | preco=NULL")

    log("\n  5 vinhos com score = 5.00:")
    cur.execute("""
        SELECT id, nome, winegod_score, nota_wcf, preco_min, moeda
        FROM wines
        WHERE winegod_score = 5.00
        ORDER BY RANDOM()
        LIMIT 5
    """)
    for row in cur.fetchall():
        log(f"    ID {row[0]}: {row[1][:50]} | score=5.00 | wcf={row[2]} | {row[3]} {row[4]}")

    log("\n  5 vinhos com score baixo (<2.0) COM preco:")
    cur.execute("""
        SELECT id, nome, winegod_score, nota_wcf, preco_min, moeda
        FROM wines
        WHERE winegod_score IS NOT NULL AND winegod_score < 2.0 AND preco_min > 0
        ORDER BY winegod_score ASC
        LIMIT 5
    """)
    for row in cur.fetchall():
        log(f"    ID {row[0]}: {row[1][:50]} | score={row[2]} | wcf={row[3]} | {row[4]} {row[5]}")

    # 8. Cobertura nota_wcf_sample_size
    log("\n--- 8. COBERTURA nota_wcf_sample_size ---")
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE nota_wcf_sample_size IS NOT NULL) AS com_sample,
            COUNT(*) FILTER (WHERE nota_wcf_sample_size IS NULL AND nota_wcf IS NOT NULL) AS sem_sample,
            ROUND(AVG(nota_wcf_sample_size)::numeric, 0) AS media_sample,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY nota_wcf_sample_size)::numeric, 0) AS mediana_sample
        FROM wines
    """)
    r = cur.fetchone()
    log(f"  Com sample_size: {r[0]:,}")
    log(f"  Sem sample_size (tem nota_wcf): {r[1]:,}")
    log(f"  Media sample_size: {r[2]}")
    log(f"  Mediana sample_size: {r[3]}")

    log("\n" + "=" * 60)
    log("FIM DO BASELINE")
    log("=" * 60)

    # Save to file
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nRelatorio salvo em: {REPORT_PATH}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
