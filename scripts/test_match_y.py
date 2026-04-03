"""
Chat Y — Test match approach: multi-strategy token-based matching
Tests on 100 no_match wines from match_results_g2
"""
import psycopg2
import sys
import io
import re
import time
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LOCAL_DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
RENDER_DB = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod"

# Common wine words to de-prioritize as search tokens (not distinctive)
STOPWORDS = {
    'wine', 'wines', 'vino', 'vinos', 'vin', 'wein',
    'red', 'white', 'rose', 'rosé', 'brut', 'dry', 'sweet', 'sec', 'demi',
    'bottle', 'magnum', 'liter', 'ml', 'cl', 'pack', 'box',
    'reserve', 'reserva', 'riserva', 'gran', 'grand', 'grande', 'cru', 'premier',
    'old', 'new', 'single', 'limited', 'special', 'edition', 'selection',
    'usa', 'france', 'italy', 'spain', 'california', 'napa', 'sonoma',
    'valley', 'coast', 'mountain', 'hill', 'hills', 'creek', 'river', 'lake',
    'north', 'south', 'east', 'west', 'central',
    'the', 'de', 'del', 'di', 'du', 'des', 'la', 'le', 'les', 'el', 'los', 'las',
    'and', 'et', 'e', 'y', 'und', 'en',
    'da', 'do', 'dos', 'das', 'von', 'van',
    'tinto', 'branco', 'blanco', 'blanc', 'rouge', 'nero', 'bianco', 'rosso',
    'it', 'us', 'fr', 'es', 'pt', 'br', 'ar', 'au', 'nz', 'za', 'cl', 'de',
}

# Grape varieties — useful for type but not distinctive for matching
GRAPE_WORDS = {
    'cabernet', 'sauvignon', 'merlot', 'pinot', 'noir', 'grigio', 'gris',
    'chardonnay', 'syrah', 'shiraz', 'tempranillo', 'malbec', 'zinfandel',
    'sangiovese', 'nebbiolo', 'barbera', 'riesling', 'gewurztraminer',
    'chenin', 'viognier', 'mourvedre', 'grenache', 'garnacha', 'carmenere',
    'primitivo', 'gamay', 'muscat', 'moscato', 'prosecco', 'champagne',
    'torrontes', 'albarino', 'verdejo', 'gruner', 'veltliner', 'montepulciano',
    'lambrusco', 'corvina', 'glera', 'trebbiano', 'vermentino', 'fiano',
    'aglianico', 'nero', 'davola', 'dolcetto', 'arneis', 'cortese',
    'blanc', 'rose', 'blend',
}

TIPO_MAP = {
    'Tinto': 'tinto',
    'Branco': 'branco',
    'Rose': 'rose',
    'Espumante': 'espumante',
    'Fortificado': 'fortificado',
    'Sobremesa': 'sobremesa',
}


def tokenize(text):
    """Split text into lowercase tokens, remove non-alpha"""
    if not text:
        return []
    return [w for w in re.split(r'[^a-zA-Z0-9àáâãäåèéêëìíîïòóôõöùúûüñç]+', text.lower()) if len(w) > 1]


def get_distinctive_tokens(tokens):
    """Get distinctive tokens (not stopwords, not grapes, not years)"""
    result = []
    for t in tokens:
        if t in STOPWORDS or t in GRAPE_WORDS:
            continue
        if re.match(r'^\d{4}$', t):  # year
            continue
        if len(t) <= 2:
            continue
        result.append(t)
    return result


def get_grape_tokens(tokens):
    """Get grape variety tokens"""
    return [t for t in tokens if t in GRAPE_WORDS]


def token_overlap_score(tokens_a, tokens_b):
    """Score based on how many tokens from A appear in B"""
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    common = set_a & set_b
    if not common:
        return 0.0
    # Weighted: proportion of A tokens found in B
    return len(common) / len(set_a)


def score_candidate(store_wine, vivino_wine):
    """
    Score a Vivino candidate against a store wine.
    Returns 0.0-1.0 score.
    """
    score = 0.0

    # Tokenize both sides
    store_tokens = tokenize(store_wine['nome_normalizado'])

    # Vivino combined tokens
    viv_text = f"{vivino_wine['produtor_normalizado'] or ''} {vivino_wine['nome_normalizado'] or ''}"
    viv_tokens = tokenize(viv_text)

    # 1. Token overlap (main signal, weight 0.50)
    overlap = token_overlap_score(store_tokens, viv_tokens)
    score += overlap * 0.50

    # 2. Reverse overlap: how many Vivino tokens are in store name (weight 0.20)
    rev_overlap = token_overlap_score(viv_tokens, store_tokens)
    score += rev_overlap * 0.20

    # 3. Producer match (weight 0.15)
    store_prod_tokens = tokenize(store_wine.get('produtor_normalizado', ''))
    viv_prod_tokens = tokenize(vivino_wine.get('produtor_normalizado', ''))
    if store_prod_tokens and viv_prod_tokens:
        prod_overlap = token_overlap_score(store_prod_tokens, viv_prod_tokens)
        score += prod_overlap * 0.15

    # 4. Safra match (weight 0.10)
    store_safra = store_wine.get('safra')
    viv_safra = vivino_wine.get('safra')
    if store_safra and viv_safra:
        try:
            if str(store_safra) == str(viv_safra).strip():
                score += 0.10
        except:
            pass

    # 5. Tipo match (weight 0.05)
    store_tipo = TIPO_MAP.get(store_wine.get('tipo', ''), '')
    viv_tipo = (vivino_wine.get('tipo', '') or '').lower()
    if store_tipo and viv_tipo and store_tipo == viv_tipo:
        score += 0.05

    return score


def search_vivino(cur, store_wine, strategy='combined'):
    """
    Search Vivino for matches using different strategies.
    Returns list of (vivino_wine, score) tuples.
    """
    candidates = []
    nome = store_wine['nome_normalizado']
    tokens = tokenize(nome)
    distinctive = get_distinctive_tokens(tokens)
    produtor = store_wine.get('produtor_normalizado', '')
    produtor_tokens = tokenize(produtor) if produtor and produtor != 'None' else []
    prod_distinctive = get_distinctive_tokens(produtor_tokens)

    # Strategy A: Search by producer name (most efficient)
    if prod_distinctive:
        # Use the longest distinctive producer token as anchor
        anchor = max(prod_distinctive, key=len)
        if len(anchor) >= 3:
            try:
                cur.execute("""
                    SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
                    FROM wines
                    WHERE produtor_normalizado ILIKE %s
                    LIMIT 50
                """, (f'%{anchor}%',))
                for row in cur.fetchall():
                    candidates.append({
                        'id': row[0], 'nome_normalizado': row[1],
                        'produtor_normalizado': row[2], 'safra': row[3],
                        'tipo': row[4], 'pais': row[5], 'regiao': row[6],
                        'strategy': 'producer'
                    })
            except Exception as e:
                pass

    # Strategy B: pg_trgm similarity on nome_normalizado
    # Search Vivino nome with the distinctive tokens combined
    if distinctive:
        search_text = ' '.join(distinctive[:5])  # Use top 5 distinctive tokens
        if len(search_text) >= 4:
            try:
                cur.execute("""
                    SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao,
                           similarity(nome_normalizado, %s) as sim
                    FROM wines
                    WHERE nome_normalizado %% %s
                    ORDER BY sim DESC
                    LIMIT 20
                """, (search_text, search_text))
                for row in cur.fetchall():
                    candidates.append({
                        'id': row[0], 'nome_normalizado': row[1],
                        'produtor_normalizado': row[2], 'safra': row[3],
                        'tipo': row[4], 'pais': row[5], 'regiao': row[6],
                        'strategy': 'trgm_nome', 'trgm_sim': row[7]
                    })
            except Exception as e:
                pass

    # Strategy C: pg_trgm on combined produtor+nome
    # Build search from store's full name
    if len(nome) >= 5:
        try:
            cur.execute("""
                SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao,
                       similarity(produtor_normalizado || ' ' || nome_normalizado, %s) as sim
                FROM wines
                WHERE (produtor_normalizado || ' ' || nome_normalizado) %% %s
                ORDER BY sim DESC
                LIMIT 20
            """, (nome, nome))
            for row in cur.fetchall():
                candidates.append({
                    'id': row[0], 'nome_normalizado': row[1],
                    'produtor_normalizado': row[2], 'safra': row[3],
                    'tipo': row[4], 'pais': row[5], 'regiao': row[6],
                    'strategy': 'trgm_combined', 'trgm_sim': row[7]
                })
        except Exception as e:
            pass

    # Strategy D: Search with longest distinctive token in nome
    if distinctive:
        longest = max(distinctive, key=len)
        if len(longest) >= 4:
            try:
                cur.execute("""
                    SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
                    FROM wines
                    WHERE nome_normalizado ILIKE %s
                    LIMIT 50
                """, (f'%{longest}%',))
                for row in cur.fetchall():
                    candidates.append({
                        'id': row[0], 'nome_normalizado': row[1],
                        'produtor_normalizado': row[2], 'safra': row[3],
                        'tipo': row[4], 'pais': row[5], 'regiao': row[6],
                        'strategy': 'keyword_nome'
                    })
            except Exception as e:
                pass

    # Deduplicate candidates by id
    seen = {}
    for c in candidates:
        cid = c['id']
        if cid not in seen:
            seen[cid] = c
        else:
            # Keep the one with higher trgm_sim if available
            if c.get('trgm_sim', 0) > seen[cid].get('trgm_sim', 0):
                seen[cid] = c

    # Score all unique candidates
    scored = []
    for c in seen.values():
        s = score_candidate(store_wine, c)
        scored.append((c, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def main():
    print("=" * 80)
    print("CHAT Y — MATCH TEST: Multi-strategy token-based matching")
    print("=" * 80)

    # Connect to both databases
    local_conn = psycopg2.connect(LOCAL_DB)
    render_conn = psycopg2.connect(RENDER_DB, connect_timeout=30)

    local_cur = local_conn.cursor()
    render_cur = render_conn.cursor()

    # Check pg_trgm threshold
    render_cur.execute("SHOW pg_trgm.similarity_threshold")
    threshold = render_cur.fetchone()[0]
    print(f"\npg_trgm threshold: {threshold}")

    # Lower threshold for more candidates
    render_cur.execute("SET pg_trgm.similarity_threshold = 0.15")
    print("Set threshold to 0.15 for broader search")

    # Get 100 real wine no_match samples
    local_cur.execute("""
        SELECT m.unique_id, u.nome_normalizado, u.produtor_normalizado, u.safra, u.tipo, u.pais_tabela, u.regiao
        FROM match_results_g2 m
        JOIN wines_unique u ON u.id = m.unique_id
        WHERE m.match_level = 'no_match'
          AND u.tipo IS NOT NULL
          AND u.tipo NOT IN ('NaN', 'Wine')
          AND u.safra IS NOT NULL
          AND u.produtor_normalizado IS NOT NULL
          AND u.produtor_normalizado != 'None'
          AND length(u.nome_normalizado) > 10
        ORDER BY random()
        LIMIT 100
    """)

    test_wines = []
    for row in local_cur.fetchall():
        test_wines.append({
            'id': row[0],
            'nome_normalizado': row[1],
            'produtor_normalizado': row[2],
            'safra': row[3],
            'tipo': row[4],
            'pais_tabela': row[5],
            'regiao': row[6],
        })

    print(f"\nLoaded {len(test_wines)} test wines (real wines with tipo+safra+produtor)")

    # Test matching
    results = {
        'match_high': [],     # score >= 0.50 — high confidence
        'match_medium': [],   # score 0.35-0.50 — medium confidence
        'match_low': [],      # score 0.25-0.35 — low confidence
        'no_match': [],       # score < 0.25
    }

    strategy_counts = Counter()
    total_time = 0

    for i, wine in enumerate(test_wines):
        t0 = time.time()
        scored = search_vivino(render_cur, wine)
        elapsed = time.time() - t0
        total_time += elapsed

        if scored:
            best_candidate, best_score = scored[0]
            strategy_counts[best_candidate.get('strategy', 'unknown')] += 1

            result = {
                'store': wine,
                'vivino': best_candidate,
                'score': best_score,
                'n_candidates': len(scored),
                'time': elapsed,
            }

            if best_score >= 0.50:
                results['match_high'].append(result)
            elif best_score >= 0.35:
                results['match_medium'].append(result)
            elif best_score >= 0.25:
                results['match_low'].append(result)
            else:
                results['no_match'].append(result)
        else:
            results['no_match'].append({
                'store': wine,
                'vivino': None,
                'score': 0,
                'n_candidates': 0,
                'time': elapsed,
            })

        # Progress every 10
        if (i + 1) % 10 == 0:
            high = len(results['match_high'])
            med = len(results['match_medium'])
            total_match = high + med
            pct = total_match / (i + 1) * 100
            print(f"  [{i+1}/100] high={high} med={med} match_rate={pct:.1f}% avg_time={total_time/(i+1):.2f}s")

    # Summary
    high = len(results['match_high'])
    med = len(results['match_medium'])
    low = len(results['match_low'])
    no = len(results['no_match'])
    total = len(test_wines)

    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"\nTotal tested: {total}")
    print(f"  High confidence (>=0.50): {high} ({high/total*100:.1f}%)")
    print(f"  Medium confidence (0.35-0.50): {med} ({med/total*100:.1f}%)")
    print(f"  Low confidence (0.25-0.35): {low} ({low/total*100:.1f}%)")
    print(f"  No match (<0.25): {no} ({no/total*100:.1f}%)")
    print(f"\n  MATCH RATE (high+medium): {(high+med)/total*100:.1f}%")
    print(f"  Avg time per wine: {total_time/total:.2f}s")

    print(f"\nStrategy distribution (best candidates):")
    for s, c in strategy_counts.most_common():
        print(f"  {s}: {c}")

    # Show examples
    print("\n" + "-" * 80)
    print("HIGH CONFIDENCE MATCHES (top 10)")
    print("-" * 80)
    for r in results['match_high'][:10]:
        s = r['store']
        v = r['vivino']
        print(f"\n  LOJA:   \"{s['nome_normalizado']}\" (produtor={s['produtor_normalizado']}, safra={s['safra']})")
        print(f"  VIVINO: \"{v['produtor_normalizado']} — {v['nome_normalizado']}\" (safra={v['safra']}, tipo={v['tipo']})")
        print(f"  Score: {r['score']:.3f} | Strategy: {v.get('strategy')} | Candidates: {r['n_candidates']}")

    print("\n" + "-" * 80)
    print("MEDIUM CONFIDENCE MATCHES (top 10)")
    print("-" * 80)
    for r in results['match_medium'][:10]:
        s = r['store']
        v = r['vivino']
        print(f"\n  LOJA:   \"{s['nome_normalizado']}\" (produtor={s['produtor_normalizado']}, safra={s['safra']})")
        print(f"  VIVINO: \"{v['produtor_normalizado']} — {v['nome_normalizado']}\" (safra={v['safra']}, tipo={v['tipo']})")
        print(f"  Score: {r['score']:.3f} | Strategy: {v.get('strategy')} | Candidates: {r['n_candidates']}")

    print("\n" + "-" * 80)
    print("NO MATCH / LOW (10 examples)")
    print("-" * 80)
    for r in (results['no_match'] + results['match_low'])[:10]:
        s = r['store']
        v = r['vivino']
        if v:
            print(f"\n  LOJA:   \"{s['nome_normalizado']}\" (produtor={s['produtor_normalizado']}, safra={s['safra']})")
            print(f"  BEST:   \"{v['produtor_normalizado']} — {v['nome_normalizado']}\" score={r['score']:.3f}")
        else:
            print(f"\n  LOJA:   \"{s['nome_normalizado']}\" — 0 candidates found")

    local_conn.close()
    render_conn.close()

    print("\n\nDone.")


if __name__ == '__main__':
    main()
