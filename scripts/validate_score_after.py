#!/usr/bin/env python3
"""
validate_score_after.py — Captura snapshot do score DEPOIS da nova formula.
Gera relatorio em reports/score_after.txt e compara com baseline.
"""

import os
import time

import psycopg2
import _env

DATABASE_URL = os.environ["DATABASE_URL"]

REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
REPORT_PATH = os.path.join(REPORT_DIR, "score_after.txt")


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
    log("VALIDATION REPORT — DEPOIS da nova formula")
    log(f"Data: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    log("=" * 60)

    # 1. Distribuicao geral
    log("\n--- 1. DISTRIBUICAO GERAL DO WINEGOD_SCORE ---")
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE winegod_score IS NOT NULL) AS com_score,
            COUNT(*) FILTER (WHERE winegod_score IS NULL AND nota_wcf IS NOT NULL) AS wcf_sem_score,
            COUNT(*) AS total,
            ROUND(AVG(winegod_score)::numeric, 2) AS media,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY winegod_score)::numeric, 2) AS mediana,
            MIN(winegod_score) AS minimo,
            MAX(winegod_score) AS maximo,
            ROUND(STDDEV(winegod_score)::numeric, 2) AS desvio
        FROM wines
    """)
    r = cur.fetchone()
    log(f"  Total wines:         {r[2]:,}")
    log(f"  Com score:           {r[0]:,}")
    log(f"  WCF sem score (NULL):{r[1]:,}")
    log(f"  Media:               {r[3]}")
    log(f"  Mediana:             {r[4]}")
    log(f"  Min:                 {r[5]}")
    log(f"  Max:                 {r[6]}")
    log(f"  Desvio padrao:       {r[7]}")

    # 2. Saturacao em 5.00
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
    log(f"  Score = 5.00:        {r[0]:,} ({r[0]*100/total_score:.1f}%)")
    log(f"  Score >= 4.90:       {r[1]:,} ({r[1]*100/total_score:.1f}%)")
    log(f"  Score >= 4.50:       {r[2]:,} ({r[2]*100/total_score:.1f}%)")

    # 3. Score NULL sem preco (VALIDACAO CRITICA)
    log("\n--- 3. SCORE NULL SEM PRECO (VALIDACAO) ---")
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE winegod_score IS NULL AND nota_wcf IS NOT NULL AND (preco_min IS NULL OR preco_min = 0)) AS null_sem_preco,
            COUNT(*) FILTER (WHERE winegod_score IS NOT NULL AND (preco_min IS NULL OR preco_min = 0)) AS score_sem_preco,
            COUNT(*) FILTER (WHERE winegod_score IS NOT NULL AND preco_min > 0) AS score_com_preco
        FROM wines
    """)
    r = cur.fetchone()
    log(f"  NULL score + sem preco:     {r[0]:,} (esperado: alto)")
    log(f"  Score existente + sem preco:{r[1]:,} (esperado: 0)")
    log(f"  Score existente + com preco:{r[2]:,}")

    # 4. Estrategia de referencia de preco
    log("\n--- 4. ESTRATEGIA DE REFERENCIA DE PRECO ---")
    cur.execute("""
        SELECT
            winegod_score_components->>'preco_reference_strategy' AS strategy,
            COUNT(*)
        FROM wines
        WHERE winegod_score_components IS NOT NULL
          AND winegod_score_components->>'preco_reference_strategy' IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
    """)
    for row in cur.fetchall():
        log(f"  {row[0]}: {row[1]:,}")

    # 5. Formula version
    log("\n--- 5. FORMULA VERSION ---")
    cur.execute("""
        SELECT
            winegod_score_components->>'formula_version' AS version,
            COUNT(*)
        FROM wines
        WHERE winegod_score_components IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
    """)
    for row in cur.fetchall():
        log(f"  {row[0]}: {row[1]:,}")

    # 6. Score por faixa de preco
    log("\n--- 6. SCORE POR FAIXA DE PRECO (USD) ---")
    cur.execute("""
        SELECT
            CASE
                WHEN (winegod_score_components->>'preco_min_usd')::float < 10 THEN '< $10'
                WHEN (winegod_score_components->>'preco_min_usd')::float < 20 THEN '$10-$20'
                WHEN (winegod_score_components->>'preco_min_usd')::float < 50 THEN '$20-$50'
                WHEN (winegod_score_components->>'preco_min_usd')::float < 100 THEN '$50-$100'
                ELSE '$100+'
            END AS faixa,
            COUNT(*),
            ROUND(AVG(winegod_score)::numeric, 2),
            ROUND(MIN(winegod_score)::numeric, 2),
            ROUND(MAX(winegod_score)::numeric, 2)
        FROM wines
        WHERE winegod_score IS NOT NULL
          AND winegod_score_components->>'preco_min_usd' IS NOT NULL
        GROUP BY 1
        ORDER BY MIN((winegod_score_components->>'preco_min_usd')::float)
    """)
    log(f"  {'Faixa':<12} {'Count':>8} {'Media':>8} {'Min':>8} {'Max':>8}")
    for row in cur.fetchall():
        log(f"  {row[0]:<12} {row[1]:>8,} {row[2]:>8} {row[3]:>8} {row[4]:>8}")

    # 7. Score type distribution
    log("\n--- 7. DISTRIBUICAO POR SCORE TYPE ---")
    cur.execute("""
        SELECT winegod_score_type, COUNT(*)
        FROM wines
        WHERE winegod_score IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
    """)
    for row in cur.fetchall():
        log(f"  {row[0]}: {row[1]:,}")

    # 8. Histograma
    log("\n--- 8. HISTOGRAMA DO SCORE ---")
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

    # 9. Exemplos
    log("\n--- 9. EXEMPLOS ---")
    log("\n  5 vinhos com score mais alto:")
    cur.execute("""
        SELECT id, nome, winegod_score, winegod_score_components->>'nota_base_score',
               winegod_score_components->>'preco_reference_strategy',
               winegod_score_components->>'preco_min_usd',
               winegod_score_components->>'preco_reference_usd'
        FROM wines
        WHERE winegod_score IS NOT NULL
        ORDER BY winegod_score DESC
        LIMIT 5
    """)
    for row in cur.fetchall():
        log(f"    ID {row[0]}: {str(row[1])[:40]} | score={row[2]} | nota_base={row[3]} | strategy={row[4]} | price={row[5]} | ref={row[6]}")

    log("\n  5 vinhos com score = 5.00 (se houver):")
    cur.execute("""
        SELECT id, nome, winegod_score_components->>'nota_base_score',
               winegod_score_components->>'preco_min_usd',
               winegod_score_components->>'preco_reference_usd',
               winegod_score_components->>'preco_reference_strategy'
        FROM wines
        WHERE winegod_score = 5.00
        ORDER BY RANDOM()
        LIMIT 5
    """)
    for row in cur.fetchall():
        log(f"    ID {row[0]}: {str(row[1])[:40]} | nota_base={row[2]} | price={row[3]} | ref={row[4]} | strategy={row[5]}")

    log("\n  5 vinhos com score NULL (tem nota_wcf):")
    cur.execute("""
        SELECT id, nome, nota_wcf, preco_min, moeda,
               winegod_score_components->>'reason_null'
        FROM wines
        WHERE winegod_score IS NULL AND nota_wcf IS NOT NULL
        ORDER BY RANDOM()
        LIMIT 5
    """)
    for row in cur.fetchall():
        log(f"    ID {row[0]}: {str(row[1])[:40]} | wcf={row[2]} | preco={row[3]} {row[4]} | reason={row[5]}")

    # 10. nota_wcf_sample_size coverage
    log("\n--- 10. COBERTURA nota_wcf_sample_size ---")
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE nota_wcf_sample_size IS NOT NULL) AS com_sample,
            COUNT(*) FILTER (WHERE nota_wcf_sample_size IS NULL AND nota_wcf IS NOT NULL) AS sem_sample
        FROM wines
    """)
    r = cur.fetchone()
    log(f"  Com sample_size: {r[0]:,}")
    log(f"  Sem sample_size (tem wcf): {r[1]:,}")

    # 11. Comparacao com baseline
    log("\n--- 11. COMPARACAO ANTES vs DEPOIS ---")
    log("  (Compare manualmente com reports/baseline_score_before.txt)")
    log("  Pontos-chave a verificar:")
    log("  - Score = 5.00 reduziu?")
    log("  - Score NULL sem preco aumentou?")
    log("  - Formula version = peer_country_note_v1?")
    log("  - Estrategias peer_narrow/peer_wide dominam?")
    log("  - Media de score razoavel (3.0-4.5)?")

    log("\n" + "=" * 60)
    log("FIM DA VALIDACAO")
    log("=" * 60)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nRelatorio salvo em: {REPORT_PATH}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
