"""Round 2b: remove spirits restantes e fragmentos — query unica"""
import psycopg2

DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

def main():
    conn = psycopg2.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM wines_clean")
    antes = cur.fetchone()[0]
    print(f"ANTES: {antes:,}")

    # UMA query com todas as marcas em alternation
    print("\n--- Spirits + non-wine (query unica) ---")
    cur.execute(r"""
        DELETE FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(makers mark|jim beam|dewars|monkey shoulder|martini rosso|martini bianco|wild turkey|buffalo trace|woodford reserve|bulleit bourbon|four roses|knob creek|laphroaig|glenfiddich|glenlivet|macallan|lagavulin|ardbeg|talisker|oban|dalmore|highland park|chivas regal|cutty sark|famous grouse|havana club|captain morgan|sailor jerry|kraken rum|hendricks gin|beefeater|gordons gin|roku gin|monkey 47|sipsmith|aviation gin|ketel one|belvedere|ciroc|stolichnaya|titos vodka|don julio|clase azul|casamigos|el tesoro|olmeca|espolon|jose cuervo|patron silver|licor 43|amarula|triple sec|amaro montenegro|amaro averna|cynar|underberg|becherovka|unicum|cachaca 51)\y'
    """)
    c1 = cur.rowcount
    conn.commit()
    print(f"  Deletados: {c1}")

    # Fragmentos inuteis (nome curto, sem dados)
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
    print(f"  Deletados: {c2}")

    # Resultado
    cur.execute("SELECT COUNT(*) FROM wines_clean")
    depois = cur.fetchone()[0]
    print(f"\nDEPOIS: {depois:,}")
    print(f"Removidos: {antes - depois:,}")

    cur.execute("""SELECT nome_normalizado, COUNT(*) FROM wines_clean
        GROUP BY nome_normalizado ORDER BY COUNT(*) DESC LIMIT 15""")
    print("\nTop 15 nomes:")
    for n, c in cur.fetchall():
        print(f"  {n}: {c}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
