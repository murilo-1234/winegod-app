"""
Investigate non-wine products in vinhos_{country}_fontes tables.
READ-ONLY — does NOT modify any data.

v2: Much more precise keyword matching to avoid false positives.
Uses word-boundary matching and excludes wine-related false positives.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import psycopg2
import json
import re
from collections import defaultdict, Counter
from urllib.parse import urlparse

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

COUNTRIES = ['br', 'us', 'fr', 'it', 'de', 'es', 'gb', 'au', 'ar', 'cl',
             'pt', 'mx', 'in', 'ph', 'gr', 'hk', 'kr', 'th']

# Known non-wine store domains (manual curation)
KNOWN_NONWINE_DOMAINS = {
    # Flowers
    'blacktulipflowers.in', 'floristella.com', 'urbanflowers.co.th',
    # Grocery/supermarket (mixed, high non-wine)
    'deliveryfort.com.br', 'covabra.com.br', 'gbarbosa.com.br',
    'savegnago.com.br', 'prezunic.com.br', 'zonasul.com.br',
    'starquik.com',
    # General marketplace (mixed)
    'amazon.com.br', 'amazon.com', 'amazon.co.uk', 'amazon.de',
    'amazon.fr', 'amazon.it', 'amazon.es', 'amazon.com.au',
    'amazon.com.mx', 'amazon.in', 'amazon.co.jp',
    'mercadolivre.com.br', 'mercadolibre.com.ar', 'mercadolibre.cl',
    'mercadolibre.com.mx',
    # Coffee machines
    'thedistiller.gr',
    # General stores
    'ionionmarket.gr', 'rustans.com', 'shopsuki.ph',
    # Fashion/lingerie
    'tipsy.in',
}


def get_domain(url):
    """Extract domain from URL."""
    if not url:
        return ''
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or ''
        domain = re.sub(r'^www\.', '', domain)
        return domain.lower()
    except:
        return ''


def is_nonwine_url(url, domain):
    """
    Check if a URL clearly points to a non-wine product.
    Uses word-boundary patterns to avoid false positives.
    Returns (is_nonwine: bool, category: str)
    """
    if not url:
        return False, ''
    url_lower = url.lower()
    path = url_lower.split('?')[0]  # ignore query params

    # ---- FLOWERS ----
    if re.search(r'\b(flower|flores|bouquet|floral-arrangement|ramo-de-flores|floristeria)\b', path):
        # But NOT "floral notes" in wine description
        if not re.search(r'(wine|vinho|vino|vin\b|wein)', path):
            return True, 'flowers'

    # ---- COFFEE / ESPRESSO MACHINES ----
    if re.search(r'\b(coffee-machine|espresso-machine|kaffeemaschine|nespresso|coffee-maker|coffee-grinder|coffee-bean|coffee-capsule)\b', path):
        return True, 'coffee-machines'
    if re.search(r'\b(cafe-em-graos?|cafe-em-capsulas?|cafe-moido|cafeteira)\b', path):
        return True, 'coffee'

    # ---- CHOCOLATE ----
    if re.search(r'\b(chocolate|chocolat)\b', path):
        if not re.search(r'(wine|vinho|vino|vin\b|wein|chocolate-wine|chocolate-stout)', path):
            return True, 'chocolate'

    # ---- CHEESE ----
    if re.search(r'\b(cheese|queijo|fromage|queso|formaggio)\b', path):
        if not re.search(r'(wine.*cheese|cheese.*wine|wineandcheese)', path):
            return True, 'cheese'

    # ---- GROCERY / FOOD (non-wine) ----
    grocery_patterns = [
        r'\b(macarrao|massa-grano|instant-noodle|cup-noodle|miojo)\b',
        r'\b(arroz|rice|basmati|jasmine-rice)\b',
        r'\b(desengordurante|limpador|detergente|sabao|cleaning)\b',
        r'\b(abobrinha|brocoli|cenoura|tomate|batata|legume|vegetal)\b',
        r'\b(frango|chicken|carne-bovina|beef|pork|salmon|fish-fillet)\b',
        r'\b(leite|milk|iogurte|yogurt|manteiga|butter|margarina)\b',
        r'\b(papel-higienico|toilet-paper|shampoo|condicionador|sabonete)\b',
        r'\b(racao|pet-food|dog-food|cat-food)\b',
        r'\b(cereal|granola|aveia|oats)\b',
        r'\b(refrigerante|soft-drink|soda|coca-cola|pepsi|guarana)\b',
    ]
    for pat in grocery_patterns:
        if re.search(pat, path):
            return True, 'grocery/food'

    # ---- CLOTHING / FASHION ----
    if re.search(r'\b(lingerie|underwear|panties|nightwear|pijama|calcinha|sutia)\b', path):
        return True, 'clothing/lingerie'
    if re.search(r'\b(dress|vestido|camiseta|t-shirt|jeans|calca|saia|blusa)\b', path):
        if not re.search(r'(wine|vinho|vino|dresser)', path):
            return True, 'clothing'

    # ---- FURNITURE ----
    if re.search(r'\b(sofa|armario|estante|mesa-de-jantar|dining-table|bookshelf|wardrobe)\b', path):
        return True, 'furniture'

    # ---- TOYS ----
    if re.search(r'\b(toy|brinquedo|juguete|lego|puzzle|doll|boneca)\b', path):
        return True, 'toys'

    # ---- PERFUME / BEAUTY ----
    if re.search(r'\b(perfume|fragrance|cologne|eau-de-toilette|eau-de-parfum)\b', path):
        return True, 'perfume/beauty'

    # ---- CANDLES ----
    if re.search(r'\b(candle|vela-aromatica|scented-candle)\b', path):
        return True, 'candles'

    # ---- ELECTRONICS ----
    if re.search(r'\b(laptop|smartphone|iphone|samsung|headphone|speaker|television|tv-led)\b', path):
        return True, 'electronics'

    # ---- SPORTS / RANDOM ----
    if re.search(r'\b(volleyball|basketball|soccer-ball|tennis-racket|yoga-mat)\b', path):
        return True, 'sports'

    # ---- GIFT BASKETS (non-wine specific) ----
    if re.search(r'\b(gift-basket|hamper|cesta-de-presente)\b', path):
        return True, 'gift-baskets'

    # ---- TEA (standalone, not chateau) ----
    if re.search(r'/tea/', path) or re.search(r'\btea-set\b|\btea-cup\b|\bgreen-tea\b|\bblack-tea\b|\bherbal-tea\b', path):
        return True, 'tea'

    # ---- BEER ----
    if re.search(r'\b(cerveja|cerveza|bier|birra)\b', path):
        if not re.search(r'(wine|vinho|vino)', path):
            return True, 'beer'

    # ---- SPIRITS (standalone products, not store name) ----
    spirit_in_product = re.search(
        r'/(whisky|whiskey|vodka|tequila|mezcal|rum|aguardiente|cachaca|sake|soju)/',
        path
    )
    if spirit_in_product:
        return True, 'spirits'

    return False, ''


def check_dados_nonwine(dados):
    """Check dados_extras for clear non-wine indicators."""
    if not dados or not isinstance(dados, dict):
        return False, ''

    # Check product name
    name = ''
    for key in ['nome', 'name', 'titulo', 'title', 'product_name']:
        if key in dados and dados[key]:
            name = str(dados[key]).lower()
            break

    # Check category
    cat = ''
    for key in ['categoria', 'category', 'type', 'product_type']:
        if key in dados and dados[key]:
            cat = str(dados[key]).lower()
            break

    # Non-wine categories
    nonwine_cats = [
        'flower', 'coffee', 'chocolate', 'cheese', 'grocery', 'food',
        'clothing', 'fashion', 'beauty', 'electronics', 'furniture',
        'toy', 'pet', 'book', 'sport', 'candle', 'perfume',
        'gift', 'hamper', 'basket', 'tea', 'beer', 'spirit',
        'whisky', 'vodka', 'rum',
    ]

    for nc in nonwine_cats:
        if nc in cat:
            return True, f'category:{nc}'

    # Non-wine product names (very specific)
    nonwine_names = [
        r'\b(coffee machine|espresso machine|nespresso)\b',
        r'\b(flower arrangement|bouquet|ramo de flores)\b',
        r'\b(bra |panties|lingerie|underwear)\b',
        r'\b(shampoo|conditioner|soap|sabonete)\b',
        r'\b(dog food|cat food|pet food|racao)\b',
        r'\b(volleyball|basketball|soccer)\b',
    ]
    for pat in nonwine_names:
        if name and re.search(pat, name):
            return True, f'name:{pat}'

    return False, ''


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("=" * 100)
    print("NON-WINE PRODUCTS INVESTIGATION (v2 — precise matching)")
    print("=" * 100)

    country_results = {}

    for cc in COUNTRIES:
        table = f"vinhos_{cc}_fontes"
        print(f"\n{'=' * 80}")
        print(f"COUNTRY: {cc.upper()} (table: {table})")
        print(f"{'=' * 80}")

        # Total count
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        total = cur.fetchone()[0]
        print(f"Total records: {total:,}")

        if total == 0:
            country_results[cc] = {'total': 0, 'nonwine_pct': 0}
            continue

        # Sample random URLs for analysis
        sample_size = min(1000, total)
        cur.execute(f"""
            SELECT url_original, dados_extras, preco, fonte
            FROM {table}
            TABLESAMPLE SYSTEM(LEAST(100.0 * {sample_size}::float / GREATEST({total}, 1), 100))
            LIMIT {sample_size}
        """)
        rows = cur.fetchall()
        actual_sample = len(rows)

        nonwine_count = 0
        nonwine_by_domain = defaultdict(lambda: {
            'count': 0, 'total_in_sample': 0,
            'examples': [], 'categories': Counter(), 'prices': []
        })
        domain_counts = Counter()

        for url, dados, preco, fonte in rows:
            domain = get_domain(url) or (fonte or '').lower()
            domain_counts[domain] += 1

            is_nw_url, cat_url = is_nonwine_url(url, domain)
            is_nw_dados, cat_dados = check_dados_nonwine(dados)

            # Also flag known non-wine domains
            is_known = domain in KNOWN_NONWINE_DOMAINS

            if is_nw_url or is_nw_dados:
                nonwine_count += 1
                cat = cat_url or cat_dados
                d = nonwine_by_domain[domain]
                d['count'] += 1
                if len(d['examples']) < 5:
                    d['examples'].append((url[:200] if url else 'N/A', preco, cat))
                d['categories'][cat] += 1
                if preco:
                    d['prices'].append(preco)

        # Update total_in_sample for each domain
        for domain in nonwine_by_domain:
            nonwine_by_domain[domain]['total_in_sample'] = domain_counts.get(domain, 0)

        pct = (nonwine_count / actual_sample * 100) if actual_sample > 0 else 0
        print(f"Sample size: {actual_sample}")
        print(f"Non-wine detected (precise): {nonwine_count} ({pct:.1f}%)")
        print(f"Estimated non-wine records: ~{int(total * pct / 100):,}")

        if nonwine_by_domain:
            print(f"\n  Non-wine by domain:")
            for domain, info in sorted(nonwine_by_domain.items(), key=lambda x: -x[1]['count']):
                avg_price = sum(info['prices']) / len(info['prices']) if info['prices'] else 0
                cats = ', '.join([f"{k}({v})" for k, v in info['categories'].most_common(5)])
                print(f"    {domain}")
                print(f"      Hits: {info['count']}/{info['total_in_sample']} in sample")
                print(f"      Categories: {cats}")
                print(f"      Avg price: {avg_price:.2f}")
                for ex_url, ex_price, ex_cat in info['examples'][:3]:
                    print(f"      [{ex_cat}] {ex_price or 0:.2f} | {ex_url}")

        country_results[cc] = {
            'total': total,
            'nonwine_pct': pct,
            'sample_size': actual_sample,
            'nonwine_count': nonwine_count,
        }

    # =========================================================================
    # PART 2: Deep-dive into known non-wine stores
    # =========================================================================
    print("\n\n" + "=" * 100)
    print("DEEP DIVE: SPECIFIC STORES TO INVESTIGATE")
    print("=" * 100)

    stores_to_check = {
        'gr': {
            'thedistiller': "Coffee machines / distilling equipment",
            'ionion': "General store / market",
        },
        'in': {
            'tipsy': "Lingerie / fashion",
            'starquik': "Groceries",
            'blacktulipflowers': "Flowers",
            'bigbasket': "Groceries",
        },
        'ph': {
            'rustan': "Department store",
            'shopsuki': "General store",
            'floristella': "Flowers",
        },
        'th': {
            'urbanflowers': "Flowers",
        },
    }

    detailed_store_findings = []

    for cc, stores in stores_to_check.items():
        table = f"vinhos_{cc}_fontes"
        print(f"\n{'=' * 80}")
        print(f"COUNTRY: {cc.upper()}")
        print(f"{'=' * 80}")

        for pattern, expected_type in stores.items():
            cur.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE LOWER(fonte) LIKE %s OR LOWER(url_original) LIKE %s
            """, (f'%{pattern}%', f'%{pattern}%'))
            cnt = cur.fetchone()[0]

            if cnt == 0:
                print(f"\n  '{pattern}' ({expected_type}): 0 records")
                continue

            # Get stats
            cur.execute(f"""
                SELECT AVG(preco), MIN(preco), MAX(preco),
                       COUNT(CASE WHEN preco IS NOT NULL THEN 1 END)
                FROM {table}
                WHERE LOWER(fonte) LIKE %s OR LOWER(url_original) LIKE %s
            """, (f'%{pattern}%', f'%{pattern}%'))
            avg_p, min_p, max_p, price_cnt = cur.fetchone()

            # Get sample
            cur.execute(f"""
                SELECT url_original, preco, moeda, dados_extras, fonte
                FROM {table}
                WHERE LOWER(fonte) LIKE %s OR LOWER(url_original) LIKE %s
                ORDER BY RANDOM()
                LIMIT 20
            """, (f'%{pattern}%', f'%{pattern}%'))
            samples = cur.fetchall()

            # Get distinct fontes
            cur.execute(f"""
                SELECT DISTINCT fonte FROM {table}
                WHERE LOWER(fonte) LIKE %s OR LOWER(url_original) LIKE %s
            """, (f'%{pattern}%', f'%{pattern}%'))
            fontes = [r[0] for r in cur.fetchall()]

            print(f"\n  '{pattern}' ({expected_type}):")
            print(f"    Records: {cnt:,}")
            print(f"    Fontes: {', '.join(fontes)}")
            print(f"    Price: avg={avg_p or 0:.2f}, min={min_p or 0:.2f}, max={max_p or 0:.2f}")
            print(f"    Sample URLs:")
            for url, preco, moeda, dados, fonte in samples[:15]:
                dados_info = ''
                if dados and isinstance(dados, dict):
                    for k in ['nome', 'name', 'titulo', 'title', 'product_name']:
                        if k in dados and dados[k]:
                            dados_info = f" | {k}={str(dados[k])[:80]}"
                            break
                    for k in ['categoria', 'category', 'type']:
                        if k in dados and dados[k]:
                            dados_info += f" | cat={str(dados[k])[:50]}"
                            break
                print(f"      {preco or 0:>10.2f} {moeda or '?':3s} | {(url or 'N/A')[:130]}{dados_info}")

            detailed_store_findings.append({
                'pattern': pattern,
                'country': cc,
                'expected_type': expected_type,
                'records': cnt,
                'avg_price': avg_p,
                'fontes': fontes,
            })

    # =========================================================================
    # PART 3: All stores per country — flag suspicious ones
    # =========================================================================
    print("\n\n" + "=" * 100)
    print("ALL STORES PER COUNTRY")
    print("=" * 100)

    suspicious_store_names = [
        'flower', 'flor', 'tulip', 'florist',
        'gift', 'hamper', 'basket', 'cesta',
        'coffee', 'cafe', 'distiller',
        'grocery', 'supermarket', 'mercado', 'market', 'mart',
        'pet', 'toy', 'book', 'fashion', 'beauty',
        'tipsy', 'suki', 'rustan',
    ]

    for cc in COUNTRIES:
        table = f"vinhos_{cc}_fontes"
        cur.execute(f"""
            SELECT fonte, COUNT(*) as cnt, AVG(preco) as avg_price,
                   MIN(preco), MAX(preco)
            FROM {table}
            GROUP BY fonte
            ORDER BY cnt DESC
        """)
        stores = cur.fetchall()

        print(f"\n--- {cc.upper()} ({len(stores)} stores) ---")
        for fonte, cnt, avg_p, min_p, max_p in stores:
            fonte_lower = (fonte or '').lower()
            suspicious = any(kw in fonte_lower for kw in suspicious_store_names)
            flag = " <<< SUSPICIOUS" if suspicious else ""
            print(f"  {cnt:>8,} | avg {avg_p or 0:>10.2f} | range [{min_p or 0:.2f} - {max_p or 0:.2f}] | {fonte or 'NULL'}{flag}")

    # =========================================================================
    # PART 4: dados_extras keys analysis
    # =========================================================================
    print("\n\n" + "=" * 100)
    print("DADOS_EXTRAS KEY ANALYSIS")
    print("=" * 100)

    for cc in COUNTRIES:
        table = f"vinhos_{cc}_fontes"
        cur.execute(f"""
            SELECT DISTINCT jsonb_object_keys(dados_extras)
            FROM {table}
            WHERE dados_extras IS NOT NULL
            LIMIT 200
        """)
        keys = [r[0] for r in cur.fetchall()]

        if not keys:
            print(f"\n--- {cc.upper()}: No dados_extras ---")
            continue

        print(f"\n--- {cc.upper()}: keys = {', '.join(sorted(keys))} ---")

        # Sample some dados_extras content
        cur.execute(f"""
            SELECT dados_extras
            FROM {table}
            WHERE dados_extras IS NOT NULL AND dados_extras != '{{}}'::jsonb
            ORDER BY RANDOM()
            LIMIT 5
        """)
        for (d,) in cur.fetchall():
            print(f"  Sample: {json.dumps(d, ensure_ascii=False)[:200]}")

    # =========================================================================
    # PART 5: URL domain analysis — find domains that appear non-wine
    # =========================================================================
    print("\n\n" + "=" * 100)
    print("DOMAIN-LEVEL ANALYSIS: WHAT PRODUCTS DO THEY SELL?")
    print("=" * 100)

    for cc in COUNTRIES:
        table = f"vinhos_{cc}_fontes"

        # Get top domains by record count
        cur.execute(f"""
            SELECT
                REGEXP_REPLACE(
                    REGEXP_REPLACE(url_original, '^https?://(www\\.)?', ''),
                    '/.*$', ''
                ) as domain,
                COUNT(*) as cnt,
                AVG(preco) as avg_price
            FROM {table}
            WHERE url_original IS NOT NULL
            GROUP BY domain
            HAVING COUNT(*) > 10
            ORDER BY cnt DESC
            LIMIT 50
        """)
        domains = cur.fetchall()

        print(f"\n--- {cc.upper()} (top domains) ---")
        for domain, cnt, avg_p in domains:
            flag = ""
            dl = (domain or '').lower()
            for kw in suspicious_store_names:
                if kw in dl:
                    flag = f" <<< SUSPICIOUS ({kw})"
                    break
            if dl in KNOWN_NONWINE_DOMAINS:
                flag = " <<< KNOWN NON-WINE"
            print(f"  {cnt:>8,} | avg {avg_p or 0:>10.2f} | {domain}{flag}")

    # =========================================================================
    # PART 6: thesipshop.com deep dive (found in v1 as selling volleyball nets)
    # =========================================================================
    print("\n\n" + "=" * 100)
    print("DEEP DIVE: SUSPICIOUS STORES FOUND IN SAMPLING")
    print("=" * 100)

    extra_suspicious = [
        ('us', 'thesipshop'),
        ('us', 'wineandcheese'),
        ('br', 'deliveryfort'),
        ('br', 'covabra'),
        ('br', 'gbarbosa'),
        ('br', 'zonasul'),
        ('br', 'savegnago'),
    ]

    for cc, pattern in extra_suspicious:
        table = f"vinhos_{cc}_fontes"
        cur.execute(f"""
            SELECT COUNT(*) FROM {table}
            WHERE LOWER(url_original) LIKE %s OR LOWER(fonte) LIKE %s
        """, (f'%{pattern}%', f'%{pattern}%'))
        cnt = cur.fetchone()[0]

        if cnt == 0:
            continue

        cur.execute(f"""
            SELECT url_original, preco, moeda, dados_extras
            FROM {table}
            WHERE LOWER(url_original) LIKE %s OR LOWER(fonte) LIKE %s
            ORDER BY RANDOM()
            LIMIT 15
        """, (f'%{pattern}%', f'%{pattern}%'))
        samples = cur.fetchall()

        nonwine_in_sample = 0
        for url, preco, moeda, dados in samples:
            is_nw, cat = is_nonwine_url(url, '')
            if is_nw:
                nonwine_in_sample += 1

        print(f"\n  {cc.upper()} / {pattern}: {cnt:,} records")
        print(f"  Non-wine in 15-sample: {nonwine_in_sample}")
        for url, preco, moeda, dados in samples[:10]:
            print(f"    {preco or 0:>10.2f} {moeda or '?':3s} | {(url or 'N/A')[:140]}")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n\n" + "=" * 100)
    print("FINAL SUMMARY")
    print("=" * 100)

    total_all = 0
    total_nonwine_est = 0

    print(f"\n{'Country':>8s} | {'Total':>12s} | {'Sample':>7s} | {'NonWine':>8s} | {'%':>6s} | {'Est NonWine':>12s}")
    print("-" * 70)
    for cc in COUNTRIES:
        r = country_results.get(cc, {})
        total = r.get('total', 0)
        pct = r.get('nonwine_pct', 0)
        sample = r.get('sample_size', 0)
        nw = r.get('nonwine_count', 0)
        est_nonwine = int(total * pct / 100)
        total_all += total
        total_nonwine_est += est_nonwine
        print(f"  {cc.upper():>5s} | {total:>12,} | {sample:>7,} | {nw:>8,} | {pct:>5.1f}% | {est_nonwine:>12,}")

    print("-" * 70)
    overall_pct = total_nonwine_est / total_all * 100 if total_all else 0
    print(f"  TOTAL | {total_all:>12,} |         |          | {overall_pct:>5.1f}% | {total_nonwine_est:>12,}")

    print("\n\nKNOWN NON-WINE STORE FINDINGS:")
    for f in detailed_store_findings:
        print(f"  {f['country'].upper()} | {f['pattern']:25s} | {f['records']:>8,} records | "
              f"avg price {f['avg_price'] or 0:.2f} | sells: {f['expected_type']} | fontes: {', '.join(f['fontes'])}")

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == '__main__':
    main()
