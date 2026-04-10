#!/usr/bin/env python3
"""dedup_report.py — Estatísticas de wine_sources e cross-reference."""

import os
import psycopg2
import _env

RENDER_URL = os.environ["getenv" == "getenv" and "DATABASE_URL" or "DATABASE_URL"]


def main():
    conn = psycopg2.connect(RENDER_URL)
    cur = conn.cursor()

    print("=" * 60)
    print("RELATORIO — WineGod Cross-Reference")
    print("=" * 60)

    # Total wines
    cur.execute("SELECT count(*) FROM wines")
    print(f"\nTotal wines no Render: {cur.fetchone()[0]:,}")

    # Total wine_sources
    cur.execute("SELECT count(*) FROM wine_sources")
    print(f"Total wine_sources:    {cur.fetchone()[0]:,}")

    # Wines com pelo menos 1 fonte
    cur.execute("SELECT count(DISTINCT wine_id) FROM wine_sources")
    print(f"Wines com fontes:      {cur.fetchone()[0]:,}")

    # Top 10 países com mais wine_sources
    print("\nTop 10 paises (wine_sources):")
    cur.execute("""
        SELECT w.pais, count(*) AS total
        FROM wine_sources ws
        JOIN wines w ON w.id = ws.wine_id
        GROUP BY w.pais
        ORDER BY total DESC
        LIMIT 10
    """)
    for pais, total in cur.fetchall():
        print(f"  {(pais or '??').upper():>4}: {total:,}")

    # Top 10 lojas
    print("\nTop 10 lojas:")
    cur.execute("""
        SELECT s.nome, s.pais, count(*) AS total
        FROM wine_sources ws
        JOIN stores s ON s.id = ws.store_id
        GROUP BY s.nome, s.pais
        ORDER BY total DESC
        LIMIT 10
    """)
    for nome, pais, total in cur.fetchall():
        safe = nome.encode("ascii", "replace").decode("ascii") if nome else "?"
        print(f"  {safe} ({pais}): {total:,}")

    # Wines com preço
    cur.execute("SELECT count(*) FROM wines WHERE preco_min IS NOT NULL AND preco_min > 0")
    print(f"\nWines com preco: {cur.fetchone()[0]:,}")

    # Faixa de preços
    cur.execute("""
        SELECT
            count(*) FILTER (WHERE preco_min < 10) AS ate10,
            count(*) FILTER (WHERE preco_min >= 10 AND preco_min < 30) AS de10a30,
            count(*) FILTER (WHERE preco_min >= 30 AND preco_min < 100) AS de30a100,
            count(*) FILTER (WHERE preco_min >= 100) AS acima100
        FROM wines
        WHERE preco_min IS NOT NULL AND preco_min > 0
    """)
    row = cur.fetchone()
    print(f"\nFaixas de preco (preco_min em moeda local):")
    print(f"  < 10:     {row[0]:,}")
    print(f"  10 - 30:  {row[1]:,}")
    print(f"  30 - 100: {row[2]:,}")
    print(f"  > 100:    {row[3]:,}")

    # Stores ativas
    cur.execute("SELECT count(*) FROM stores WHERE ativa = TRUE")
    print(f"\nStores ativas: {cur.fetchone()[0]:,}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
