"""
Investigate non-wine products in vinhos_{country}_fontes tables.
READ-ONLY — does NOT modify any data.
"""
import psycopg2
import json
import re
from collections import defaultdict, Counter
from urllib.parse import urlparse

DB_URL = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

COUNTRIES = ['br', 'us', 'fr', 'it', 'de', 'es', 'gb', 'au', 'ar', 'cl',
             'pt', 'mx', 'in', 'ph', 'gr', 'hk', 'kr', 'th']

# Keywords in URLs that indicate non-wine products
NONWINE_URL_KEYWORDS = [
    'flower', 'flores', 'flor', 'bouquet', 'ramo',
    'gift', 'regalo', 'presente', 'cadeau',
    'chocolate', 'cacao', 'cocoa',
    'coffee', 'cafe', 'caffe', 'espresso', 'nespresso', 'kaffee',
    'cheese', 'queijo', 'fromage', 'queso', 'formaggio',
    'grocery', 'mercado', 'supermarket', 'lebensmittel',
    'snack', 'chips', 'crisp',
    'bra', 'lingerie', 'underwear', 'panties', 'nightwear',
    'clothing', 'fashion', 'ropa', 'roupa', 'vestido', 'dress', 'shirt', 'tshirt',
    'furniture', 'moveis', 'muebles', 'sofa', 'chair',
    'book', 'libro', 'livro', 'livre',
    'toy', 'brinquedo', 'juguete',
    'perfume', 'fragrance', 'cologne',
    'candle', 'vela', 'candela', 'bougie',
    'soap', 'sabonete', 'jabon',
    'cream', 'creme', 'lotion', 'moisturizer',
    'shampoo', 'conditioner', 'hair-care',
    'pet', 'mascota', 'animal',
    'cake', 'bolo', 'torta', 'pastel', 'gateau',
    'tea', 'cha/', 'te/',
    'beer', 'cerveja', 'cerveza', 'bier', 'birra',
    'water', 'agua',
    'juice', 'suco', 'jugo', 'jus',
    'soft-drink', 'soda', 'refrigerante',
    'spirit', 'whisky', 'whiskey', 'vodka', 'rum', 'gin/', 'tequila', 'brandy', 'cognac', 'mezcal',
    'hamper', 'basket', 'cesta',
    'olive', 'azeite', 'aceite',
    'vinegar', 'vinagre',
    'honey', 'mel', 'miel',
    'jam', 'geleia', 'mermelada',
    'sauce', 'molho', 'salsa',
    'pasta', 'noodle', 'macarrao',
    'rice', 'arroz', 'riz',
    'meat', 'carne', 'viande',
    'fish', 'peixe', 'pescado', 'poisson',
    'kitchen', 'cozinha', 'cocina',
    'glass', 'copa', 'taca', 'goblet',
    'corkscrew', 'saca-rolha', 'decanter',
    'accessori', 'acessorio',
    'machine', 'maquina', 'appliance',
    'grinder', 'moedor',
]

# Known non-wine stores to specifically check
KNOWN_NONWINE_STORES = {
    'gr': ['thedistiller.gr', 'ionionmarket.gr', 'ionionmarket'],
    'in': ['tipsy.in', 'starquik.com', 'blacktulipflowers.in', 'blacktulipflowers'],
    'ph': ['rustans.com', 'shopsuki.ph', 'floristella.com', 'floristella'],
    'th': ['urbanflowers.co.th', 'urbanflowers'],
}


def get_domain(url):
    """Extract domain from URL."""
    if not url:
        return ''
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or ''
        # Remove www.
        domain = re.sub(r'^www\.', '', domain)
        return domain.lower()
    except:
        return ''


def url_has_nonwine_keyword(url):
    """Check if URL contains non-wine keywords. Returns list of matched keywords."""
    if not url:
        return []
    url_lower = url.lower()
    matched = []
    for kw in NONWINE_URL_KEYWORDS:
        if kw in url_lower:
            matched.append(kw)
    return matched


def analyze_dados_extras(dados):
    """Check dados_extras for non-wine indicators."""
    if not dados:
        return []
    indicators = []
    text = json.dumps(dados).lower() if isinstance(dados, dict) else str(dados).lower()

    nonwine_categories = [
        'flower', 'gift', 'chocolate', 'coffee', 'espresso', 'cheese',
        'grocery', 'snack', 'bra', 'lingerie', 'clothing', 'furniture',
        'book', 'toy', 'perfume', 'candle', 'soap', 'cream', 'shampoo',
        'pet', 'cake', 'tea', 'beer', 'whisky', 'vodka', 'gin',
        'hamper', 'basket', 'machine', 'appliance', 'grinder',
        'bouquet', 'ramo', 'flores', 'presente',
    ]
    for cat in nonwine_categories:
        if cat in text:
            indicators.append(cat)
    return indicators


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("=" * 100)
    print("NON-WINE PRODUCTS INVESTIGATION")
    print("=" * 100)

    # =========================================================================
    # PART 1: Per-country analysis with URL sampling
    # =========================================================================
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
            country_results[cc] = {'total': 0, 'nonwine_pct': 0, 'nonwine_stores': {}}
            continue

        # Sample 500 random URLs for analysis
        sample_size = min(500, total)
        cur.execute(f"""
            SELECT url_original, dados_extras, preco, fonte
            FROM {table}
            ORDER BY RANDOM()
            LIMIT {sample_size}
        """)
        rows = cur.fetchall()

        nonwine_count = 0
        nonwine_by_domain = defaultdict(lambda: {'count': 0, 'examples': [], 'keywords': Counter(), 'prices': []})
        domain_counts = Counter()

        for url, dados, preco, fonte in rows:
            domain = get_domain(url) or (fonte or '')
            domain_counts[domain] += 1

            url_kws = url_has_nonwine_keyword(url)
            dados_kws = analyze_dados_extras(dados)
            all_kws = url_kws + dados_kws

            if all_kws:
                nonwine_count += 1
                d = nonwine_by_domain[domain]
                d['count'] += 1
                if len(d['examples']) < 3:
                    d['examples'].append(url[:150] if url else 'N/A')
                for kw in all_kws:
                    d['keywords'][kw] += 1
                if preco:
                    d['prices'].append(preco)

        pct = (nonwine_count / sample_size * 100) if sample_size > 0 else 0
        print(f"Sample size: {sample_size}")
        print(f"Non-wine in sample: {nonwine_count} ({pct:.1f}%)")
        print(f"Estimated non-wine records: ~{int(total * pct / 100):,}")

        if nonwine_by_domain:
            print(f"\n  Non-wine by domain (from sample):")
            for domain, info in sorted(nonwine_by_domain.items(), key=lambda x: -x[1]['count']):
                avg_price = sum(info['prices']) / len(info['prices']) if info['prices'] else 0
                top_kws = ', '.join([f"{k}({v})" for k, v in info['keywords'].most_common(5)])
                total_in_sample = domain_counts.get(domain, info['count'])
                domain_pct = info['count'] / total_in_sample * 100 if total_in_sample else 0
                print(f"    {domain}")
                print(f"      Non-wine hits: {info['count']}/{total_in_sample} in sample ({domain_pct:.0f}%)")
                print(f"      Keywords: {top_kws}")
                print(f"      Avg price: {avg_price:.2f}")
                for ex in info['examples'][:2]:
                    print(f"      Example: {ex}")

        country_results[cc] = {
            'total': total,
            'nonwine_pct': pct,
            'nonwine_stores': dict(nonwine_by_domain),
        }

    # =========================================================================
    # PART 2: Deep-dive into known non-wine stores
    # =========================================================================
    print("\n\n" + "=" * 100)
    print("DEEP DIVE: KNOWN NON-WINE STORES")
    print("=" * 100)

    for cc, store_patterns in KNOWN_NONWINE_STORES.items():
        table = f"vinhos_{cc}_fontes"
        print(f"\n{'=' * 80}")
        print(f"COUNTRY: {cc.upper()}")
        print(f"{'=' * 80}")

        for pattern in store_patterns:
            # Search by fonte field (store name) OR by URL domain
            cur.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE LOWER(fonte) LIKE %s OR LOWER(url_original) LIKE %s
            """, (f'%{pattern.lower()}%', f'%{pattern.lower()}%'))
            cnt = cur.fetchone()[0]

            if cnt == 0:
                print(f"\n  Store pattern '{pattern}': 0 records found")
                continue

            print(f"\n  Store pattern '{pattern}': {cnt:,} records")

            # Get sample with details
            cur.execute(f"""
                SELECT url_original, preco, moeda, dados_extras, fonte
                FROM {table}
                WHERE LOWER(fonte) LIKE %s OR LOWER(url_original) LIKE %s
                ORDER BY RANDOM()
                LIMIT 20
            """, (f'%{pattern.lower()}%', f'%{pattern.lower()}%'))
            samples = cur.fetchall()

            prices = [r[1] for r in samples if r[1] is not None]
            avg_price = sum(prices) / len(prices) if prices else 0
            print(f"  Average price: {avg_price:.2f} ({samples[0][2] if samples else '?'})")
            print(f"  Source (fonte): {samples[0][4] if samples else '?'}")
            print(f"  Sample URLs:")
            for url, preco, moeda, dados, fonte in samples[:10]:
                dados_str = ''
                if dados:
                    # Show product name from dados_extras if present
                    if isinstance(dados, dict):
                        name = dados.get('nome', dados.get('name', dados.get('titulo', dados.get('title', ''))))
                        cat = dados.get('categoria', dados.get('category', dados.get('type', '')))
                        if name:
                            dados_str = f" | name={name[:80]}"
                        if cat:
                            dados_str += f" | cat={cat[:50]}"
                print(f"    {preco:>10.2f} {moeda or '?':3s} | {(url or 'N/A')[:120]}{dados_str}")

    # =========================================================================
    # PART 3: Find ALL distinct fontes (stores) and check for suspicious ones
    # =========================================================================
    print("\n\n" + "=" * 100)
    print("ALL STORES PER COUNTRY — CHECKING FOR SUSPICIOUS STORES")
    print("=" * 100)

    suspicious_keywords_in_store_name = [
        'flower', 'flor', 'gift', 'chocolate', 'coffee', 'cafe', 'caffe',
        'grocery', 'market', 'super', 'pet', 'book', 'toy', 'fashion',
        'beauty', 'tulip', 'urban', 'tipsy', 'suki', 'rustan', 'distiller',
        'ionion', 'starquik', 'hamper', 'basket', 'cesta',
    ]

    for cc in COUNTRIES:
        table = f"vinhos_{cc}_fontes"
        cur.execute(f"""
            SELECT fonte, COUNT(*) as cnt, AVG(preco) as avg_price
            FROM {table}
            GROUP BY fonte
            ORDER BY cnt DESC
        """)
        stores = cur.fetchall()

        print(f"\n--- {cc.upper()} ({len(stores)} stores) ---")

        # Show ALL stores with counts
        for fonte, cnt, avg_p in stores:
            fonte_lower = (fonte or '').lower()
            suspicious = any(kw in fonte_lower for kw in suspicious_keywords_in_store_name)
            flag = " *** SUSPICIOUS ***" if suspicious else ""
            print(f"  {cnt:>8,} records | avg {avg_p or 0:>10.2f} | {fonte or 'NULL'}{flag}")

    # =========================================================================
    # PART 4: Deeper dados_extras analysis for each country
    # =========================================================================
    print("\n\n" + "=" * 100)
    print("DADOS_EXTRAS ANALYSIS — PRODUCT NAMES/CATEGORIES")
    print("=" * 100)

    for cc in COUNTRIES:
        table = f"vinhos_{cc}_fontes"

        # Check what keys exist in dados_extras
        cur.execute(f"""
            SELECT DISTINCT jsonb_object_keys(dados_extras)
            FROM {table}
            WHERE dados_extras IS NOT NULL
            LIMIT 100
        """)
        keys = [r[0] for r in cur.fetchall()]

        if not keys:
            print(f"\n--- {cc.upper()}: No dados_extras keys found ---")
            continue

        print(f"\n--- {cc.upper()}: dados_extras keys: {', '.join(sorted(keys))} ---")

        # Check for product names/categories that suggest non-wine
        for key in ['nome', 'name', 'titulo', 'title', 'categoria', 'category', 'type', 'product_name', 'product_type']:
            if key in keys:
                cur.execute(f"""
                    SELECT dados_extras->>'{key}' as val, COUNT(*) as cnt
                    FROM {table}
                    WHERE dados_extras->>'{key}' IS NOT NULL
                    GROUP BY val
                    ORDER BY cnt DESC
                    LIMIT 20
                """)
                vals = cur.fetchall()
                if vals:
                    print(f"  Top values for '{key}':")
                    for val, cnt in vals:
                        print(f"    {cnt:>6,} | {(val or '')[:100]}")

    # =========================================================================
    # PART 5: Summary
    # =========================================================================
    print("\n\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)

    total_all = 0
    total_nonwine_est = 0

    for cc in COUNTRIES:
        r = country_results.get(cc, {})
        total = r.get('total', 0)
        pct = r.get('nonwine_pct', 0)
        est_nonwine = int(total * pct / 100)
        total_all += total
        total_nonwine_est += est_nonwine
        print(f"  {cc.upper():3s} | {total:>10,} records | ~{pct:>5.1f}% non-wine | ~{est_nonwine:>8,} non-wine records")

    print(f"\n  TOTAL: {total_all:>10,} records across {len(COUNTRIES)} countries")
    overall_pct = total_nonwine_est / total_all * 100 if total_all else 0
    print(f"  Estimated non-wine: ~{total_nonwine_est:>8,} ({overall_pct:.1f}%)")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
