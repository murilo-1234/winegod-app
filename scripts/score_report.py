#!/usr/bin/env python3
"""
score_report.py — Relatorio do WineGod Score apos calculo.

Mostra distribuicao, top vinhos, medias por pais, etc.
"""

import os
import psycopg2
import _env

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # 1. Distribuicao de scores
    print("=" * 60)
    print("DISTRIBUICAO DE SCORES")
    print("=" * 60)
    cur.execute("""
        SELECT
            CASE
                WHEN winegod_score < 1 THEN '0-1'
                WHEN winegod_score < 2 THEN '1-2'
                WHEN winegod_score < 3 THEN '2-3'
                WHEN winegod_score < 4 THEN '3-4'
                WHEN winegod_score <= 5 THEN '4-5'
            END as faixa,
            COUNT(*) as qtd
        FROM wines
        WHERE winegod_score IS NOT NULL
        GROUP BY faixa
        ORDER BY faixa
    """)
    for faixa, qtd in cur.fetchall():
        print(f"  {faixa}: {qtd:>10,}")

    # 2. Verified vs Estimated
    print(f"\n{'=' * 60}")
    print("VERIFIED vs ESTIMATED")
    print("=" * 60)
    cur.execute("""
        SELECT winegod_score_type, COUNT(*)
        FROM wines
        WHERE winegod_score IS NOT NULL
        GROUP BY winegod_score_type
    """)
    for tipo, qtd in cur.fetchall():
        print(f"  {tipo}: {qtd:>10,}")

    # 3. Com preco vs sem preco
    print(f"\n{'=' * 60}")
    print("COM PRECO vs SEM PRECO")
    print("=" * 60)
    cur.execute("""
        SELECT
            CASE WHEN preco_min > 0 THEN 'com_preco' ELSE 'sem_preco' END as grupo,
            COUNT(*),
            ROUND(AVG(winegod_score)::numeric, 2)
        FROM wines
        WHERE winegod_score IS NOT NULL
        GROUP BY grupo
    """)
    for grupo, qtd, avg in cur.fetchall():
        print(f"  {grupo}: {qtd:>10,} (score medio: {avg})")

    # 4. Top 10 por WineGod Score
    print(f"\n{'=' * 60}")
    print("TOP 10 — WINEGOD SCORE (custo-beneficio)")
    print("=" * 60)
    cur.execute("""
        SELECT nome, pais_nome, winegod_score, nota_wcf, preco_min, moeda
        FROM wines
        WHERE winegod_score IS NOT NULL
        ORDER BY winegod_score DESC
        LIMIT 10
    """)
    for i, (nome, pais, score, wcf, preco, moeda) in enumerate(cur.fetchall(), 1):
        nome_curto = (nome or "?")[:50]
        preco_str = f"{moeda} {preco}" if preco else "s/preco"
        print(f"  {i:2}. [{score}] {nome_curto} ({pais}) — WCF {wcf} — {preco_str}")

    # 5. Top 10 por nota_ajustada
    print(f"\n{'=' * 60}")
    print("TOP 10 — NOTA AJUSTADA (qualidade pura)")
    print("=" * 60)
    cur.execute("""
        SELECT nome, pais_nome,
               (winegod_score_components->>'nota_ajustada')::numeric as nota_aj,
               nota_wcf, vivino_reviews
        FROM wines
        WHERE winegod_score_components IS NOT NULL
        ORDER BY nota_aj DESC
        LIMIT 10
    """)
    for i, (nome, pais, nota_aj, wcf, reviews) in enumerate(cur.fetchall(), 1):
        nome_curto = (nome or "?")[:50]
        print(f"  {i:2}. [{nota_aj}] {nome_curto} ({pais}) — WCF {wcf} — {reviews or 0} reviews")

    # 6. Media por pais (top 15)
    print(f"\n{'=' * 60}")
    print("SCORE MEDIO POR PAIS (top 15, min 100 vinhos)")
    print("=" * 60)
    cur.execute("""
        SELECT pais_nome, COUNT(*) as qtd, ROUND(AVG(winegod_score)::numeric, 2) as avg_score
        FROM wines
        WHERE winegod_score IS NOT NULL AND pais_nome IS NOT NULL
        GROUP BY pais_nome
        HAVING COUNT(*) >= 100
        ORDER BY avg_score DESC
        LIMIT 15
    """)
    for pais, qtd, avg in cur.fetchall():
        print(f"  {pais:<25} {qtd:>8,} vinhos — score medio: {avg}")

    cur.close()
    conn.close()
    print(f"\n{'=' * 60}")
    print("Relatorio completo!")


if __name__ == "__main__":
    main()
