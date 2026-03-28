#!/usr/bin/env python3
"""
fix_prices_in_kr.py -- Correcao de moeda por dominio para India e Korea.

India: lojas indianas (.in, .co.in, dominios conhecidos) marcadas como USD -> INR
Korea: lojas coreanas com precos altos marcadas como USD -> KRW
"""

import argparse
import psycopg2

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

# ── India: dominios que sao INR (nao USD) ────────────────────────────────────

# Dominios .in e .co.in (claramente indianos)
INDIA_INR_DOT_IN = [
    "fetchnbuy.in", "thegiftstudio.in", "thedottedi.in", "tipsy.in",
    "liquorgenie.in", "thegourmetbox.in", "wraparts.in", "thegifttree.in",
    "blacktulipflowers.in", "sonarys.in", "foodsmith.in", "theliquorestate.in",
    "eternalflowers.in", "thewinecellar.in", "whiskeyprice.in",
    "thewritehouse.co.in", "debon.co.in", "aafiadryfruits.in",
    "highfieldshopping.in", "magsonsgroup.in", "rosegoldwine.in",
    "theliquorwarehouse.in", "finewinesonline.in", "fratelliwines.in",
    "elitewinery.in", "delhiwineclub.in",
]

# Dominios .com que sao lojas indianas (confirmados por nome/cidade/contexto)
INDIA_INR_DOT_COM = [
    "rameshwinestoregoa.com",   # Goa wine store
    "winepalacegoa.com",        # Goa wine store
    "liquorvaultgoa.com",       # Goa liquor store
    "bottlestoreblr.com",       # Bangalore store
    "gustoimports.com",         # Indian wine importer, median 3770
    "tulleeho.com",             # Indian drinks platform, median 1350
    "darudelivery.com",         # daru = alcool em Hindi, median 700
    "gooddropwine.com",         # Indian wine brand, median 750
    "wegiftkerala.com",         # Kerala gift store, median 1399
    "pravaahindia.com",         # "india" no nome, median 569
    "loperaindia.com",          # "india" no nome, median 375
    "chennaigrocers.com",       # Chennai (India), median 180
    "starquik.com",             # Tata StarQuik, Indian grocery, median 107
    "thebarcollective.com",     # Indian bar collective, median 735
    "theblackboxco.com",        # Indian, median 595
    "palmtreeshopping.com",     # Indian shopping, median 349
    "nisargjambhul.com",        # Indian name, median 849
    "raghasdairy.com",          # Indian dairy/store, median 800
    "naaraaaba.com",            # Indian, median 2000
    "smacchen.com",             # Indian, median 599
    "sobrietysips.com",         # Indian non-alc brand, median 699
    "williamswoak.com",         # Indian, median 899
    "bigbanyanwines.com",       # Indian winery, median 800
    "lakshmikrishnanaturals.com",  # Indian name, median 395
]

INDIA_INR_DOMAINS = INDIA_INR_DOT_IN + INDIA_INR_DOT_COM

# ── Korea: dominios que sao KRW (nao USD) ───────────────────────────────────

KOREA_KRW_DOMAINS = [
    "winezip.co.kr",        # median 23,500
    "vintagewine.co.kr",    # median 128,520
    "rarewine.co.kr",       # median 49,000
    "vinylhouse.kr",        # median 40,000
    "koreakosher.com",      # median 9,850
    "gugusubs.com",         # median 16,700
    "winegonggan.com",      # median 96,000
    "wine-bridge.com",      # median 7,700
]


def fix_country(cur, tabela, domains, moeda_nova, dry_run):
    total = 0
    for domain in domains:
        pattern = f"%{domain}%"
        cur.execute(
            f'SELECT COUNT(*) FROM "{tabela}" WHERE moeda = %s AND preco > 0 AND url_original LIKE %s',
            ("USD", pattern),
        )
        n = cur.fetchone()[0]
        if n == 0:
            continue

        # Amostra
        cur.execute(
            f'SELECT id, preco, url_original FROM "{tabela}" '
            f'WHERE moeda = %s AND preco > 0 AND url_original LIKE %s LIMIT 3',
            ("USD", pattern),
        )
        amostras = cur.fetchall()

        print(f"  {domain:45s} | {n:>6,} registros USD -> {moeda_nova}")
        for row in amostras:
            url_short = (row[2][:60] if row[2] else "N/A").encode("ascii", "replace").decode()
            print(f"    ex: id={row[0]} preco={float(row[1]):>12,.2f} | {url_short}")

        if not dry_run:
            cur.execute(
                f'UPDATE "{tabela}" SET moeda = %s WHERE moeda = %s AND preco > 0 AND url_original LIKE %s',
                (moeda_nova, "USD", pattern),
            )

        total += n

    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    if args.dry_run:
        print("*** DRY-RUN ***\n")

    # India
    print("=" * 60)
    print("INDIA: USD -> INR (por dominio)")
    print("=" * 60)
    n_in = fix_country(cur, "vinhos_in_fontes", INDIA_INR_DOMAINS, "INR", args.dry_run)
    print(f"\n  TOTAL India: {n_in:,} registros")

    # Korea
    print("\n" + "=" * 60)
    print("KOREA: USD -> KRW (por dominio)")
    print("=" * 60)
    n_kr = fix_country(cur, "vinhos_kr_fontes", KOREA_KRW_DOMAINS, "KRW", args.dry_run)
    print(f"\n  TOTAL Korea: {n_kr:,} registros")

    print(f"\n  GRAND TOTAL: {n_in + n_kr:,} registros corrigidos")

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
