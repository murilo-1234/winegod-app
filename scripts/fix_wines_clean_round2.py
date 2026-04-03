"""Round 2: remove spirits restantes e fragmentos inuteis"""
import psycopg2

DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

def main():
    conn = psycopg2.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM wines_clean")
    antes = cur.fetchone()[0]
    print(f"ANTES: {antes:,}")

    # Spirits que escaparam do round 1 (marcas especificas)
    print("\n--- Spirits round 2 ---")
    brands = [
        "makers mark", "jim beam", "dewars", "monkey shoulder",
        "martini rosso", "martini bianco", "wild turkey", "buffalo trace",
        "woodford reserve", "bulleit", "four roses", "knob creek",
        "laphroaig", "glenfiddich", "glenlivet", "macallan",
        "lagavulin", "ardbeg", "talisker", "oban", "dalmore",
        "highland park", "chivas regal", "cutty sark", "famous grouse",
        "havana club", "captain morgan", "sailor jerry", "kraken rum",
        "hendricks gin", "beefeater", "gordons gin", "roku gin",
        "monkey 47", "sipsmith", "aviation gin", "ketel one",
        "belvedere", "ciroc", "stolichnaya", "titos vodka",
        "finlandia vodka", "skyy vodka", "don julio", "clase azul",
        "casamigos", "el tesoro", "olmeca", "espolon",
        "jose cuervo", "patron silver", "licor 43", "amarula",
        "st germain", "triple sec", "curacao", "amaro montenegro",
        "amaro averna", "cynar", "ramazotti", "underberg",
        "becherovka", "unicum", "cachaca 51", "ypicoa",
    ]

    total_spirits = 0
    for brand in brands:
        cur.execute(
            r"DELETE FROM wines_clean WHERE LOWER(nome_limpo) ~ ('\y' || %s || '\y')",
            (brand,)
        )
        if cur.rowcount > 0:
            print(f"  {brand}: {cur.rowcount}")
            total_spirits += cur.rowcount
    conn.commit()
    print(f"  Total spirits: {total_spirits}")

    # Fragmentos inuteis (nome_normalizado curto, sem dados adicionais)
    print("\n--- Fragmentos inuteis ---")
    cur.execute("""
        DELETE FROM wines_clean
        WHERE LENGTH(TRIM(nome_normalizado)) <= 5
          AND produtor_extraido IS NULL
          AND safra IS NULL
          AND rating IS NULL
    """)
    c2 = cur.rowcount
    conn.commit()
    print(f"  Fragmentos deletados: {c2}")

    # Resultado
    cur.execute("SELECT COUNT(*) FROM wines_clean")
    depois = cur.fetchone()[0]
    print(f"\nDEPOIS: {depois:,}")
    print(f"Total removidos: {antes - depois:,}")

    # Top 10 nomes
    cur.execute("""SELECT nome_normalizado, COUNT(*) FROM wines_clean
        GROUP BY nome_normalizado ORDER BY COUNT(*) DESC LIMIT 15""")
    print("\nTop 15 nomes repetidos:")
    for n, c in cur.fetchall():
        print(f"  {n}: {c}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
