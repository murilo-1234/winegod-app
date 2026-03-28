#!/usr/bin/env python3
"""
fix_prices_v2.py -- Correcao abrangente de precos e moedas.

4 passes:
  1. Centavos BR: garrafeiranacional (/100 + EUR), vinhosevinhos (/100), trivino (/100)
  2. Placeholders: preco = 1.00 e >= 99999 -> NULL
  3. Non-wine stores: preco -> -1
  4. Moedas restantes: CO, RU, IL, TW, PL, NO, SE, HU (USD -> local)

Uso:
  python fix_prices_v2.py --dry-run
  python fix_prices_v2.py
"""

import argparse
import psycopg2

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"


def safe_print(msg):
    print(msg.encode("ascii", "replace").decode())


def count_match(cur, tabela, where_clause, params=None):
    cur.execute(f'SELECT COUNT(*) FROM "{tabela}" WHERE {where_clause}', params or ())
    return cur.fetchone()[0]


def run_update(cur, tabela, set_clause, where_clause, params, dry_run):
    n = count_match(cur, tabela, where_clause, params)
    if n == 0:
        return 0
    if not dry_run:
        cur.execute(f'UPDATE "{tabela}" SET {set_clause} WHERE {where_clause}', params)
    return n


# ── PASSO 1: Centavos BR ────────────────────────────────────────────────────

def fix_centavos(cur, dry_run):
    print("\n" + "=" * 60)
    print("PASSO 1 -- CENTAVOS (BR)")
    print("=" * 60)
    total = 0

    # 1a. garrafeiranacional.com — EUR centimos, moeda errada (BRL -> EUR)
    # fonte = magento
    n = run_update(
        cur, "vinhos_br_fontes",
        "preco = preco / 100, moeda = 'EUR'",
        "url_original LIKE %s AND fonte = %s AND preco > 0 AND moeda = 'BRL'",
        ("%garrafeiranacional.com%", "magento"),
        dry_run,
    )
    print(f"  garrafeiranacional.com (magento): {n:,} registros /100 + moeda=EUR")
    total += n

    # 1b. garrafeiranacional.com — fonte 'Garrafeira Nacional' (9 records, preco ja em EUR, so moeda errada)
    n = run_update(
        cur, "vinhos_br_fontes",
        "moeda = 'EUR'",
        "url_original LIKE %s AND fonte = %s AND preco > 0 AND moeda = 'BRL'",
        ("%garrafeiranacional.com%", "Garrafeira Nacional"),
        dry_run,
    )
    print(f"  garrafeiranacional.com (Garrafeira Nacional): {n:,} registros moeda=EUR")
    total += n

    # 1c. vinhosevinhos.com — BRL centavos, SÓ magento
    n = run_update(
        cur, "vinhos_br_fontes",
        "preco = preco / 100",
        "url_original LIKE %s AND fonte = %s AND preco > 0",
        ("%vinhosevinhos.com%", "magento"),
        dry_run,
    )
    print(f"  vinhosevinhos.com (magento): {n:,} registros /100")
    total += n

    # 1d. trivino.com.br — BRL centavos
    n = run_update(
        cur, "vinhos_br_fontes",
        "preco = preco / 100",
        "url_original LIKE %s AND preco > 1000",
        ("%trivino.com.br%",),
        dry_run,
    )
    print(f"  trivino.com.br: {n:,} registros /100")
    total += n

    # 1e. loja.peterlongo.com.br — parcial, so > 1000
    n = run_update(
        cur, "vinhos_br_fontes",
        "preco = preco / 100",
        "url_original LIKE %s AND fonte = %s AND preco > 1000",
        ("%peterlongo.com.br%", "magento"),
        dry_run,
    )
    print(f"  peterlongo.com.br (magento, >1000): {n:,} registros /100")
    total += n

    # 1f. domoexpress.com.br — parcial, so > 1000
    n = run_update(
        cur, "vinhos_br_fontes",
        "preco = preco / 100",
        "url_original LIKE %s AND fonte = %s AND preco > 1000",
        ("%domoexpress.com.br%", "magento"),
        dry_run,
    )
    print(f"  domoexpress.com.br (magento, >1000): {n:,} registros /100")
    total += n

    print(f"\n  TOTAL centavos: {total:,}")
    return total


# ── PASSO 2: Placeholders ───────────────────────────────────────────────────

def fix_placeholders(cur, dry_run):
    print("\n" + "=" * 60)
    print("PASSO 2 -- PLACEHOLDERS -> NULL")
    print("=" * 60)
    total = 0

    # Preco = 1.00 (placeholder em varios paises)
    placeholder_100 = [
        ("se", 1.00), ("fr", 1.00), ("gr", 1.00), ("us", 1.00),
        ("nl", 1.00), ("uy", 1.00), ("br", 1.00),
    ]
    for pais, valor in placeholder_100:
        tabela = f"vinhos_{pais}_fontes"
        n = run_update(
            cur, tabela,
            "preco = NULL",
            "preco = %s",
            (valor,),
            dry_run,
        )
        print(f"  {pais.upper()}: {n:,} registros com preco={valor} -> NULL")
        total += n

    # BR: preco >= 99999 (interfood placeholders)
    n = run_update(
        cur, "vinhos_br_fontes",
        "preco = NULL",
        "preco >= 99999",
        (),
        dry_run,
    )
    print(f"  BR: {n:,} registros com preco >= 99999 -> NULL")
    total += n

    print(f"\n  TOTAL placeholders: {total:,}")
    return total


# ── PASSO 3: Non-wine stores ────────────────────────────────────────────────

def fix_nonwine(cur, dry_run):
    print("\n" + "=" * 60)
    print("PASSO 3 -- LOJAS NAO-VINHO -> preco = -1")
    print("=" * 60)
    total = 0

    # Pure non-wine stores: (tabela, dominio, descricao)
    nonwine_stores = [
        ("vinhos_in_fontes", "starquik.com", "groceries"),
        ("vinhos_ph_fontes", "rustans.com", "department store"),
        ("vinhos_ph_fontes", "shopsuki.ph", "general store"),
        ("vinhos_hk_fontes", "cerqular.hk", "fashion"),
        ("vinhos_us_fontes", "thesipshop.com", "sports equipment"),
        ("vinhos_gr_fontes", "ionionmarket.gr", "general grocery"),
        ("vinhos_gr_fontes", "thedistiller.gr", "coffee machines"),
        ("vinhos_gr_fontes", "e-joymarket.gr", "grocery"),
        ("vinhos_th_fontes", "urbanflowers.co.th", "flowers"),
        ("vinhos_hk_fontes", "growsfresh.com", "meat/grocery"),
        ("vinhos_in_fontes", "tipsy.in", "lingerie"),
        ("vinhos_in_fontes", "blacktulipflowers.in", "flowers"),
        ("vinhos_ph_fontes", "floristella.com.ph", "flowers"),
    ]

    for tabela, dominio, desc in nonwine_stores:
        n = run_update(
            cur, tabela,
            "preco = -1",
            "url_original LIKE %s AND preco != -1",
            (f"%{dominio}%",),
            dry_run,
        )
        print(f"  {dominio:40s} ({desc:20s}): {n:,}")
        total += n

    # BR: dados corrompidos (SKUs como preco, anos como preco, preco unico)
    br_bad = [
        ("dlpvinhos.com.br", "SKU as price"),
        ("distritowine.com.br", "all same price artifact"),
        ("baccovineria.com.br", "vintage year as price"),
        ("cavenacional.com.br", "vintage year as price"),
        ("icelebra.com.br", "vintage year as price"),
        ("vinicolamariaherminda.com.br", "vintage year as price"),
    ]
    for dominio, desc in br_bad:
        n = run_update(
            cur, "vinhos_br_fontes",
            "preco = -1",
            "url_original LIKE %s AND preco > 0",
            (f"%{dominio}%",),
            dry_run,
        )
        if n > 0:
            print(f"  {dominio:40s} ({desc:20s}): {n:,}")
            total += n

    print(f"\n  TOTAL non-wine: {total:,}")
    return total


# ── PASSO 4: Moedas restantes ───────────────────────────────────────────────

def fix_moedas_restantes(cur, dry_run):
    print("\n" + "=" * 60)
    print("PASSO 4 -- MOEDAS RESTANTES (USD -> local)")
    print("=" * 60)
    total = 0

    # Todos os USD nesses paises sao registros sem preco (preco=0 ou NULL)
    # que o scraper defaultou para USD. Corrigir label de moeda.
    paises_moeda = {
        "co": "COP", "ru": "RUB", "il": "ILS", "tw": "TWD",
        "pl": "PLN", "no": "NOK", "se": "SEK", "hu": "HUF",
    }

    for pais, moeda_local in sorted(paises_moeda.items()):
        tabela = f"vinhos_{pais}_fontes"
        n = run_update(
            cur, tabela,
            f"moeda = '{moeda_local}'",
            "moeda = 'USD'",
            (),
            dry_run,
        )
        print(f"  {pais.upper()}: USD -> {moeda_local} ({n:,} registros)")
        total += n

    print(f"\n  TOTAL moedas: {total:,}")
    return total


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    if args.dry_run:
        print("*** DRY-RUN ***\n")

    n1 = fix_centavos(cur, args.dry_run)
    n2 = fix_placeholders(cur, args.dry_run)
    n3 = fix_nonwine(cur, args.dry_run)
    n4 = fix_moedas_restantes(cur, args.dry_run)

    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"  Centavos corrigidos:  {n1:>8,}")
    print(f"  Placeholders -> NULL: {n2:>8,}")
    print(f"  Non-wine -> -1:       {n3:>8,}")
    print(f"  Moedas corrigidas:    {n4:>8,}")
    grand = n1 + n2 + n3 + n4
    print(f"  TOTAL:                {grand:>8,}")

    if args.dry_run:
        conn.rollback()
        print("\n*** ROLLBACK (dry-run) ***")
    else:
        conn.commit()
        print("\n*** COMMIT ***")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
