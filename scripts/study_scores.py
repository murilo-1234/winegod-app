#!/usr/bin/env python3
"""
study_scores.py — Estudo estatístico de scores e notas do WineGod.
Apenas SELECT, não altera nada.
"""
import psycopg2
import sys
import os
import _env

DB = os.environ["DATABASE_URL"]

def run():
    conn = psycopg2.connect(DB)
    cur = conn.cursor()

    print("Conectado ao banco.\n")

    # ============ Q1: ESTATISTICAS GERAIS DO DELTA ============
    cur.execute("""
    SELECT
      COUNT(*) as total_vinhos,
      ROUND(AVG(nota_wcf - vivino_rating)::numeric, 4) as media_delta,
      ROUND(STDDEV(nota_wcf - vivino_rating)::numeric, 4) as desvio_padrao,
      ROUND(MIN(nota_wcf - vivino_rating)::numeric, 2) as min_delta,
      ROUND(MAX(nota_wcf - vivino_rating)::numeric, 2) as max_delta,
      ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY nota_wcf - vivino_rating)::numeric, 2) as p25,
      ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY nota_wcf - vivino_rating)::numeric, 2) as mediana,
      ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY nota_wcf - vivino_rating)::numeric, 2) as p75,
      SUM(CASE WHEN (nota_wcf - vivino_rating) > 0.10 THEN 1 ELSE 0 END) as acima_010,
      SUM(CASE WHEN (nota_wcf - vivino_rating) > 0.20 THEN 1 ELSE 0 END) as acima_020,
      SUM(CASE WHEN (nota_wcf - vivino_rating) > 0.50 THEN 1 ELSE 0 END) as acima_050,
      SUM(CASE WHEN (nota_wcf - vivino_rating) < -0.10 THEN 1 ELSE 0 END) as abaixo_010,
      SUM(CASE WHEN (nota_wcf - vivino_rating) < -0.20 THEN 1 ELSE 0 END) as abaixo_020
    FROM wines
    WHERE nota_wcf IS NOT NULL AND vivino_rating IS NOT NULL AND vivino_rating > 0
    """)
    r = cur.fetchone()
    print("=== Q1: ESTATISTICAS GERAIS DO DELTA (nota_wcf - vivino_rating) ===")
    labels = ['total','media','desvio','min','max','p25','mediana','p75',
              'acima_0.10','acima_0.20','acima_0.50','abaixo_-0.10','abaixo_-0.20']
    for l, v in zip(labels, r):
        print(f"  {l}: {v}")
    print()
    sys.stdout.flush()

    # ============ Q2: DISTRIBUICAO POR BUCKETS ============
    cur.execute("""
    SELECT
      ROUND((nota_wcf - vivino_rating)::numeric, 1) as delta_bucket,
      COUNT(*) as qtd
    FROM wines
    WHERE nota_wcf IS NOT NULL AND vivino_rating IS NOT NULL AND vivino_rating > 0
    GROUP BY delta_bucket
    ORDER BY delta_bucket
    """)
    print("=== Q2: DISTRIBUICAO DO DELTA (buckets de 0.1) ===")
    for row in cur.fetchall():
        bar = '#' * min(int(row[1] / 5000), 80)
        print(f"  {float(row[0]):>5.1f} | {row[1]:>8} {bar}")
    print()
    sys.stdout.flush()

    # ============ Q3: TOP 20 INFLACOES ============
    cur.execute("""
    SELECT nome, vivino_rating, nota_wcf, ROUND((nota_wcf - vivino_rating)::numeric, 2) as delta,
           vivino_reviews, pais_nome
    FROM wines
    WHERE nota_wcf IS NOT NULL AND vivino_rating > 0
    ORDER BY (nota_wcf - vivino_rating) DESC
    LIMIT 20
    """)
    print("=== Q3: TOP 20 MAIORES INFLACOES (WCF > Vivino) ===")
    for r in cur.fetchall():
        nome = str(r[0] or '')[:45]
        print(f"  {nome:<45} Viv={r[1]} WCF={r[2]} D={r[3]:+} Rev={r[4] or 0} {r[5] or ''}")
    print()
    sys.stdout.flush()

    # ============ Q4: TOP 20 DEFLACOES ============
    cur.execute("""
    SELECT nome, vivino_rating, nota_wcf, ROUND((nota_wcf - vivino_rating)::numeric, 2) as delta,
           vivino_reviews, pais_nome
    FROM wines
    WHERE nota_wcf IS NOT NULL AND vivino_rating > 0
    ORDER BY (nota_wcf - vivino_rating) ASC
    LIMIT 20
    """)
    print("=== Q4: TOP 20 MAIORES DEFLACOES (WCF < Vivino) ===")
    for r in cur.fetchall():
        nome = str(r[0] or '')[:45]
        print(f"  {nome:<45} Viv={r[1]} WCF={r[2]} D={r[3]:+} Rev={r[4] or 0} {r[5] or ''}")
    print()
    sys.stdout.flush()

    # ============ Q5: DELTA POR FAIXA DE REVIEWS ============
    cur.execute("""
    SELECT
      CASE
        WHEN vivino_reviews >= 10000 THEN '10K+'
        WHEN vivino_reviews >= 1000 THEN '1K-10K'
        WHEN vivino_reviews >= 100 THEN '100-1K'
        WHEN vivino_reviews >= 10 THEN '10-100'
        ELSE '0-9'
      END as faixa_reviews,
      COUNT(*) as qtd,
      ROUND(AVG(nota_wcf - vivino_rating)::numeric, 3) as media_delta,
      ROUND(STDDEV(nota_wcf - vivino_rating)::numeric, 3) as desvio_delta,
      ROUND(AVG(vivino_rating)::numeric, 2) as media_vivino,
      ROUND(AVG(nota_wcf)::numeric, 2) as media_wcf
    FROM wines
    WHERE nota_wcf IS NOT NULL AND vivino_rating > 0
    GROUP BY faixa_reviews
    ORDER BY MIN(COALESCE(vivino_reviews, 0))
    """)
    print("=== Q5: DELTA POR FAIXA DE REVIEWS ===")
    print(f"  {'Faixa':<10} {'Qtd':>8} {'Media D':>8} {'Desvio':>7} {'VivMed':>7} {'WCFMed':>7}")
    print("  " + "-" * 55)
    for r in cur.fetchall():
        print(f"  {r[0]:<10} {r[1]:>8} {r[2]:>+8} {r[3]:>7} {r[4]:>7} {r[5]:>7}")
    print()
    sys.stdout.flush()

    # ============ Q6: DELTA POR FAIXA DE VIVINO RATING ============
    cur.execute("""
    SELECT
      CASE
        WHEN vivino_rating >= 4.5 THEN '4.5-5.0'
        WHEN vivino_rating >= 4.0 THEN '4.0-4.4'
        WHEN vivino_rating >= 3.5 THEN '3.5-3.9'
        WHEN vivino_rating >= 3.0 THEN '3.0-3.4'
        WHEN vivino_rating >= 2.5 THEN '2.5-2.9'
        ELSE '<2.5'
      END as faixa_rating,
      COUNT(*) as qtd,
      ROUND(AVG(nota_wcf - vivino_rating)::numeric, 3) as media_delta,
      ROUND(AVG(nota_wcf)::numeric, 3) as media_wcf
    FROM wines
    WHERE nota_wcf IS NOT NULL AND vivino_rating > 0
    GROUP BY faixa_rating
    ORDER BY MIN(vivino_rating)
    """)
    print("=== Q6: DELTA POR FAIXA DE VIVINO RATING ===")
    print(f"  {'Faixa':<10} {'Qtd':>8} {'Media D':>8} {'WCF Med':>8}")
    print("  " + "-" * 40)
    for r in cur.fetchall():
        print(f"  {r[0]:<10} {r[1]:>8} {r[2]:>+8} {r[3]:>8}")
    print()
    sys.stdout.flush()

    # ============ Q7: DISTRIBUICAO DO WINEGOD SCORE ============
    cur.execute("""
    SELECT
      CASE
        WHEN winegod_score = 5.00 THEN '5.00 (cap)'
        WHEN winegod_score >= 4.50 THEN '4.50-4.99'
        WHEN winegod_score >= 4.00 THEN '4.00-4.49'
        WHEN winegod_score >= 3.50 THEN '3.50-3.99'
        WHEN winegod_score >= 3.00 THEN '3.00-3.49'
        WHEN winegod_score >= 2.50 THEN '2.50-2.99'
        WHEN winegod_score >= 2.00 THEN '2.00-2.49'
        WHEN winegod_score >= 1.00 THEN '1.00-1.99'
        ELSE '<1.00'
      END as faixa,
      COUNT(*) as qtd,
      ROUND(COUNT(*)::numeric / SUM(COUNT(*)) OVER () * 100, 1) as pct
    FROM wines WHERE winegod_score IS NOT NULL
    GROUP BY faixa ORDER BY faixa
    """)
    print("=== Q7: DISTRIBUICAO DO WINEGOD SCORE ===")
    for r in cur.fetchall():
        bar = '#' * min(int(float(r[2])), 80)
        print(f"  {r[0]:<12} | {r[1]:>8} ({float(r[2]):>5.1f}%) {bar}")
    print()
    sys.stdout.flush()

    # ============ Q8: COM vs SEM PRECO ============
    cur.execute("""
    SELECT
      COUNT(*) as total_com_score,
      SUM(CASE WHEN preco_min IS NOT NULL AND preco_min > 0 THEN 1 ELSE 0 END) as com_preco,
      SUM(CASE WHEN preco_min IS NULL OR preco_min = 0 THEN 1 ELSE 0 END) as sem_preco,
      ROUND(AVG(CASE WHEN preco_min IS NOT NULL AND preco_min > 0 THEN winegod_score END)::numeric, 2) as score_com,
      ROUND(AVG(CASE WHEN preco_min IS NULL OR preco_min = 0 THEN winegod_score END)::numeric, 2) as score_sem
    FROM wines WHERE winegod_score IS NOT NULL
    """)
    r = cur.fetchone()
    print("=== Q8: VINHOS COM vs SEM PRECO ===")
    print(f"  Total com score: {r[0]}")
    print(f"  Com preco: {r[1]} (score medio: {r[3]})")
    print(f"  Sem preco: {r[2]} (score medio: {r[4]})")
    print()
    sys.stdout.flush()

    # ============ Q9: SCORE POR FAIXA DE PRECO ============
    cur.execute("""
    SELECT faixa, COUNT(*) as qtd,
           ROUND(AVG(score)::numeric, 2) as score_medio,
           SUM(CASE WHEN score = 5.00 THEN 1 ELSE 0 END) as qtd_500,
           ROUND(AVG(wcf)::numeric, 2) as wcf_medio,
           ROUND(MIN(score)::numeric, 2) as score_min,
           ROUND(MAX(score)::numeric, 2) as score_max
    FROM (
      SELECT
        CASE
          WHEN preco_usd < 10 THEN '01: <$10'
          WHEN preco_usd < 20 THEN '02: $10-20'
          WHEN preco_usd < 50 THEN '03: $20-50'
          WHEN preco_usd < 100 THEN '04: $50-100'
          WHEN preco_usd < 200 THEN '05: $100-200'
          ELSE '06: $200+'
        END as faixa,
        winegod_score as score,
        nota_wcf as wcf,
        preco_usd
      FROM (
        SELECT winegod_score, nota_wcf,
          preco_min * CASE moeda
            WHEN 'USD' THEN 1.0 WHEN 'EUR' THEN 1.08 WHEN 'GBP' THEN 1.27
            WHEN 'BRL' THEN 0.18 WHEN 'ARS' THEN 0.001 WHEN 'CLP' THEN 0.001
            WHEN 'AUD' THEN 0.65 WHEN 'CAD' THEN 0.74 WHEN 'CHF' THEN 1.12
            WHEN 'MXN' THEN 0.058 WHEN 'ZAR' THEN 0.055 WHEN 'SEK' THEN 0.096
            WHEN 'NOK' THEN 0.093 WHEN 'DKK' THEN 0.145 WHEN 'PLN' THEN 0.25
            WHEN 'NZD' THEN 0.60 WHEN 'JPY' THEN 0.0067 WHEN 'CZK' THEN 0.043
            WHEN 'HUF' THEN 0.0027 WHEN 'GEL' THEN 0.37 WHEN 'TRY' THEN 0.031
            ELSE NULL END as preco_usd
        FROM wines
        WHERE winegod_score IS NOT NULL AND preco_min > 0 AND moeda IS NOT NULL
      ) sub WHERE preco_usd IS NOT NULL AND preco_usd > 0
    ) sub2
    GROUP BY faixa ORDER BY faixa
    """)
    print("=== Q9: SCORE POR FAIXA DE PRECO (USD) ===")
    print(f"  {'Faixa':<14} {'Qtd':>7} {'ScoreMed':>9} {'Sc=5.00':>8} {'WCFMed':>7} {'ScMin':>6} {'ScMax':>6}")
    print("  " + "-" * 60)
    for r in cur.fetchall():
        print(f"  {r[0]:<14} {r[1]:>7} {r[2]:>9} {r[3]:>8} {r[4]:>7} {r[5]:>6} {r[6]:>6}")
    print()
    sys.stdout.flush()

    # ============ Q10: QUANTOS SEM nota_wcf ============
    cur.execute("""
    SELECT
      COUNT(*) as total_wines,
      SUM(CASE WHEN nota_wcf IS NOT NULL THEN 1 ELSE 0 END) as com_wcf,
      SUM(CASE WHEN nota_wcf IS NULL THEN 1 ELSE 0 END) as sem_wcf,
      SUM(CASE WHEN winegod_score IS NOT NULL THEN 1 ELSE 0 END) as com_score,
      SUM(CASE WHEN vivino_rating IS NOT NULL AND vivino_rating > 0 THEN 1 ELSE 0 END) as com_vivino
    FROM wines
    """)
    r = cur.fetchone()
    print("=== Q10: COBERTURA DE CAMPOS ===")
    print(f"  Total vinhos: {r[0]}")
    print(f"  Com nota_wcf: {r[1]}")
    print(f"  Sem nota_wcf: {r[2]}")
    print(f"  Com winegod_score: {r[3]}")
    print(f"  Com vivino_rating > 0: {r[4]}")
    print()

    cur.close()
    conn.close()
    print("=== FIM ===")


if __name__ == "__main__":
    run()
