"""Fix alertas da auditoria: CHECK 10, 14, 17, 20, 21"""
import psycopg2

DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

def main():
    conn = psycopg2.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM wines_clean")
    antes = cur.fetchone()[0]
    print(f"ANTES: {antes:,}")

    # CHECK 10: Produtores falsos -> NULL
    print("\n--- CHECK 10: Produtores falsos ---")
    fake = ('Gift', 'Magnum', 'Chablis', 'Etna', 'Bolgheri', 'Crema',
            'Pack', 'Box', 'Kit', 'Set', 'Combo', 'Mix',
            'Red', 'White', 'Rose', 'Brut', 'Reserva', 'Reserve',
            'Premium', 'Classic', 'Organic', 'Natural', 'Bio')
    ph = ','.join(['%s'] * len(fake))
    cur.execute(f"UPDATE wines_clean SET produtor_extraido = NULL, produtor_normalizado = NULL WHERE produtor_extraido IN ({ph})", fake)
    print(f"  Produtores anulados: {cur.rowcount}")
    conn.commit()

    # CHECK 14: Nomes = so digitos ou <= 2 chars
    print("\n--- CHECK 14: Nomes inuteis ---")
    cur.execute("DELETE FROM wines_clean WHERE nome_normalizado ~ '^[0-9]+$'")
    c14a = cur.rowcount
    cur.execute("DELETE FROM wines_clean WHERE LENGTH(TRIM(nome_normalizado)) <= 2")
    c14b = cur.rowcount
    cur.execute("UPDATE wines_clean SET nome_normalizado = TRIM(nome_normalizado) WHERE nome_normalizado != TRIM(nome_normalizado)")
    c14c = cur.rowcount
    conn.commit()
    print(f"  Deletados (so numeros): {c14a}")
    print(f"  Deletados (<= 2 chars): {c14b}")
    print(f"  Trim nome_norm: {c14c}")

    # CHECK 17: Nome = so uva
    print("\n--- CHECK 17: Nome = so uva ---")
    grapes = ('chardonnay','merlot','cabernet sauvignon','pinot noir','malbec',
              'syrah','shiraz','sauvignon blanc','riesling','tempranillo',
              'sangiovese','grenache','carmenere','tannat','prosecco',
              'rose','brut','reserva','crianza','tinto','blanco','red','white',
              'pinot grigio','cabernet','zinfandel','primitivo','garnacha',
              'monastrell','verdejo','albarino','torrontes','nebbiolo',
              'barbera','dolcetto','champagne','cava','lambrusco')
    ph2 = ','.join(['%s'] * len(grapes))
    cur.execute(f"DELETE FROM wines_clean WHERE LOWER(TRIM(nome_limpo)) IN ({ph2})", grapes)
    print(f"  Deletados: {cur.rowcount}")
    conn.commit()

    # CHECK 20: Nao-vinho expandido
    print("\n--- CHECK 20: Nao-vinho ---")

    # Spirits
    cur.execute(r"""DELETE FROM wines_clean WHERE LOWER(nome_limpo) ~
        '\y(grey goose|southern comfort|jack daniels|johnnie walker|jameson|hennessy|remy martin|patron|bacardi|smirnoff|absolut vodka|tanqueray|bombay sapphire|jagermeister|baileys|kahlua|campari|aperol|pernod|ricard|pastis|ouzo|sambuca|limoncello|amaretto|frangelico|midori|malibu|disaronno|cointreau|grand marnier|drambuie|chartreuse|absinthe|fernet branca)\y'""")
    c20a = cur.rowcount
    conn.commit()

    # Food and non-wine
    cur.execute(r"""DELETE FROM wines_clean WHERE LOWER(nome_limpo) ~
        '\y(ketchup|mayonnaise|mustard|vinegar|olive oil|balsamic vinegar|hummus|peanut butter|hot sauce|soy sauce|fish sauce|bbq sauce|salsa verde|guacamole|humle|hops pellet|barley|malt extract|yeast|coffee bean|tea bag|energy drink|protein powder|supplement|vitamin|shampoo|detergent|toothpaste|deodorant|perfume|t-shirt|jeans|sneaker|jewelry|necklace|bracelet|earring|sunglasses|handbag|backpack|pillow|blanket|towel|curtain|carpet|furniture|flower bouquet|pet food|dog food|cat food|stuffed animal|board game)\y'""")
    c20b = cur.rowcount
    conn.commit()

    # Non-wine beverages
    cur.execute(r"""DELETE FROM wines_clean WHERE LOWER(nome_limpo) ~
        '\y(coca cola|pepsi|fanta|sprite|mountain dew|dr pepper|gatorade|red bull|monster energy|kombucha|lemonade|orange juice|apple juice|coconut water|almond milk|oat milk|soy milk)\y'""")
    c20c = cur.rowcount
    conn.commit()

    print(f"  Spirits: {c20a}")
    print(f"  Food/other: {c20b}")
    print(f"  Beverages: {c20c}")

    # CHECK 21: Grappa/destilados
    print("\n--- CHECK 21: Grappa/destilados ---")
    cur.execute(r"""DELETE FROM wines_clean WHERE LOWER(nome_limpo) ~
        '\y(grappa|aguardente|brandy|eau de vie|marc de bourgogne|pisco|rakija|slivovitz|palinka|tsipouro|zivania|orujo|bagaceira)\y'""")
    print(f"  Deletados: {cur.rowcount}")
    conn.commit()

    # Resultado
    cur.execute("SELECT COUNT(*) FROM wines_clean")
    depois = cur.fetchone()[0]
    print(f"\nDEPOIS: {depois:,}")
    print(f"Total removidos: {antes - depois:,}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
