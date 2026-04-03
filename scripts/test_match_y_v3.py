"""
Chat Y — Match Test v3: Improved scoring to reduce false positives
Key changes from v2:
- Producer mismatch PENALTY (was only bonus)
- Require minimum token overlap threshold
- Better handling of common words (vineyards, domaine, chateau)
- Score recalibrated with stronger producer weight
"""
import psycopg2
import sys
import io
import re
import time
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LOCAL_DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

THRESHOLD_HIGH = 0.55
THRESHOLD_MEDIUM = 0.40
THRESHOLD_LOW = 0.30

TIPO_MAP = {
    'Tinto': 'tinto', 'Branco': 'branco', 'Rose': 'rose',
    'Espumante': 'espumante', 'Fortificado': 'fortificado', 'Sobremesa': 'sobremesa',
}

# Words that are common in wine names but NOT distinctive of a specific wine
GENERIC_WORDS = {
    'vineyards', 'vineyard', 'winery', 'wines', 'wine', 'estate', 'estates',
    'domaine', 'chateau', 'castello', 'bodega', 'bodegas', 'cantina', 'tenuta',
    'maison', 'cave', 'caves', 'casa', 'clos', 'quinta', 'fazenda',
    'reserve', 'reserva', 'riserva', 'gran', 'grand', 'grande',
    'premier', 'cru', 'village', 'villages', 'classico', 'superiore',
    'selection', 'seleccion', 'crianza', 'roble', 'joven',
    'brut', 'extra', 'nature', 'dosage', 'zero',
    'red', 'white', 'rose', 'blanc', 'rouge', 'rosso', 'bianco', 'blanco',
    'tinto', 'branco', 'nero', 'secco', 'dolce',
    'old', 'vines', 'single', 'limited', 'special', 'edition', 'cuvee',
}


def tokenize(text):
    if not text:
        return []
    return [w for w in re.split(r'[^a-zA-Z0-9àáâãäåèéêëìíîïòóôõöùúûüñç]+', text.lower()) if len(w) > 1]


def distinctive_tokens(tokens):
    """Tokens that are likely unique to a specific wine/producer"""
    return [t for t in tokens if t not in GENERIC_WORDS and not re.match(r'^\d{4}$', t) and len(t) >= 3]


def token_overlap(a_tokens, b_tokens):
    if not a_tokens or not b_tokens:
        return 0.0
    return len(set(a_tokens) & set(b_tokens)) / len(set(a_tokens))


def score_candidate(store, viv):
    """
    Improved scoring with producer mismatch penalty.
    Returns 0.0 to 1.0
    """
    store_tokens = tokenize(store['nome_normalizado'])
    viv_text = f"{viv['produtor_normalizado'] or ''} {viv['nome_normalizado'] or ''}"
    viv_tokens = tokenize(viv_text)

    # Get distinctive tokens for more meaningful overlap
    store_dist = distinctive_tokens(store_tokens)
    viv_dist = distinctive_tokens(viv_tokens)

    # 1. Distinctive token overlap: store→vivino (weight 0.35)
    if store_dist and viv_dist:
        fwd_dist = token_overlap(store_dist, viv_dist)
    else:
        fwd_dist = token_overlap(store_tokens, viv_tokens)
    score = fwd_dist * 0.35

    # 2. Full token overlap: store→vivino (weight 0.10)
    fwd_all = token_overlap(store_tokens, viv_tokens)
    score += fwd_all * 0.10

    # 3. Reverse overlap: vivino→store (weight 0.10)
    rev = token_overlap(viv_tokens, store_tokens)
    score += rev * 0.10

    # 4. PRODUCER MATCH (weight 0.25 — most important signal)
    store_prod = tokenize(store.get('produtor_normalizado', ''))
    viv_prod = tokenize(viv.get('produtor_normalizado', ''))
    store_prod_dist = distinctive_tokens(store_prod)
    viv_prod_dist = distinctive_tokens(viv_prod)

    if store_prod_dist and viv_prod_dist:
        # Check if ANY distinctive producer word matches
        prod_fwd = token_overlap(store_prod_dist, viv_prod_dist)
        prod_rev = token_overlap(viv_prod_dist, store_prod_dist)
        prod_score = max(prod_fwd, prod_rev)

        if prod_score > 0:
            score += prod_score * 0.25
        else:
            # PENALTY: producer available but doesn't match at all
            # This catches "kiona vineyards" matching "sterling vineyards"
            score -= 0.10
    elif store_prod and viv_prod:
        # Only generic words in producer — use full overlap
        p_overlap = token_overlap(store_prod, viv_prod)
        score += p_overlap * 0.15

    # 5. Safra match (weight 0.12)
    ss = str(store.get('safra', ''))
    vs = str(viv.get('safra', '')).strip()
    if ss and vs and ss == vs:
        score += 0.12
    elif ss and vs and ss != vs:
        # Safra mismatch is a slight negative signal
        score -= 0.02

    # 6. Tipo match (weight 0.08)
    s_tipo = TIPO_MAP.get(store.get('tipo', ''), '')
    v_tipo = (viv.get('tipo', '') or '').lower()
    if s_tipo and v_tipo:
        if s_tipo == v_tipo:
            score += 0.08
        else:
            # Tinto vs Branco is a strong negative
            if {s_tipo, v_tipo} & {'tinto', 'branco'} == {s_tipo, v_tipo}:
                score -= 0.05

    return max(0.0, min(1.0, score))


def make_viv(row):
    return {
        'id': row[0], 'nome_normalizado': row[1], 'produtor_normalizado': row[2],
        'safra': row[3], 'tipo': row[4], 'pais': row[5], 'regiao': row[6],
    }


def search_by_producer(cur, store):
    produtor = store.get('produtor_normalizado', '') or ''
    if produtor == 'None' or len(produtor) < 3:
        return []
    words = [w for w in produtor.split() if len(w) >= 3 and w not in GENERIC_WORDS]
    if not words:
        words = [w for w in produtor.split() if len(w) >= 3]
    if not words:
        return []

    anchor = max(words, key=len)
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
        FROM vivino_match WHERE produtor_normalizado ILIKE %s LIMIT 200
    """, (f'%{anchor}%',))
    candidates = [make_viv(r) for r in cur.fetchall()]

    # If we have 2+ distinctive words, also search with AND condition for precision
    if len(words) >= 2:
        second = sorted(words, key=len, reverse=True)[1]
        if len(second) >= 3:
            cur.execute("""
                SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
                FROM vivino_match
                WHERE produtor_normalizado ILIKE %s AND produtor_normalizado ILIKE %s
                LIMIT 100
            """, (f'%{anchor}%', f'%{second}%'))
            seen = {c['id'] for c in candidates}
            for r in cur.fetchall():
                d = make_viv(r)
                if d['id'] not in seen:
                    candidates.append(d)
    return candidates


def search_by_keyword(cur, store):
    tokens = tokenize(store['nome_normalizado'])
    distinctive = [t for t in tokens if len(t) >= 5 and t not in GENERIC_WORDS and not re.match(r'^\d{4}$', t)]
    if not distinctive:
        return []

    candidates = []
    longest = max(distinctive, key=len)

    # Search in nome AND produtor
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
        FROM vivino_match
        WHERE nome_normalizado ILIKE %s OR produtor_normalizado ILIKE %s
        LIMIT 150
    """, (f'%{longest}%', f'%{longest}%'))
    for r in cur.fetchall():
        candidates.append(make_viv(r))

    # If 2+ distinctive tokens, try 2-token AND search for precision
    if len(distinctive) >= 2:
        second = sorted(distinctive, key=len, reverse=True)[1]
        cur.execute("""
            SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
            FROM vivino_match
            WHERE (nome_normalizado ILIKE %s OR produtor_normalizado ILIKE %s)
              AND (nome_normalizado ILIKE %s OR produtor_normalizado ILIKE %s)
            LIMIT 50
        """, (f'%{longest}%', f'%{longest}%', f'%{second}%', f'%{second}%'))
        seen = {c['id'] for c in candidates}
        for r in cur.fetchall():
            d = make_viv(r)
            if d['id'] not in seen:
                candidates.append(d)

    return candidates


def search_by_trgm(cur, store):
    nome = store['nome_normalizado']
    if not nome or len(nome) < 5:
        return []
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
        FROM vivino_match
        WHERE texto_busca %% %s
        ORDER BY similarity(texto_busca, %s) DESC
        LIMIT 10
    """, (nome, nome))
    return [make_viv(r) for r in cur.fetchall()]


def search_by_trgm_nome(cur, store):
    tokens = tokenize(store['nome_normalizado'])
    nome_clean = ' '.join(t for t in tokens if not re.match(r'^\d{4}$', t))
    if len(nome_clean) < 5:
        return []
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
        FROM vivino_match
        WHERE nome_normalizado %% %s
        ORDER BY similarity(nome_normalizado, %s) DESC
        LIMIT 10
    """, (nome_clean, nome_clean))
    return [make_viv(r) for r in cur.fetchall()]


def find_best_match(cur, store):
    """Returns (best_candidate, score, strategy, n_candidates, elapsed)"""
    all_cands = {}
    t_total = time.time()

    # Phase 1: Fast (producer + keyword)
    for c in search_by_producer(cur, store):
        all_cands[c['id']] = (c, 'producer')
    for c in search_by_keyword(cur, store):
        if c['id'] not in all_cands:
            all_cands[c['id']] = (c, 'keyword')

    # Score fast candidates
    best, best_score, best_strat = None, 0, 'none'
    for cid, (cand, strat) in all_cands.items():
        s = score_candidate(store, cand)
        if s > best_score:
            best_score, best, best_strat = s, cand, strat

    if best_score >= THRESHOLD_MEDIUM:
        return best, best_score, best_strat, len(all_cands), time.time() - t_total

    # Phase 2: trgm nome (medium speed)
    for c in search_by_trgm_nome(cur, store):
        s = score_candidate(store, c)
        if s > best_score:
            best_score, best, best_strat = s, c, 'trgm_nome'

    if best_score >= THRESHOLD_LOW:
        return best, best_score, best_strat, len(all_cands), time.time() - t_total

    # Phase 3: trgm combined (slowest)
    for c in search_by_trgm(cur, store):
        s = score_candidate(store, c)
        if s > best_score:
            best_score, best, best_strat = s, c, 'trgm_combined'

    return best, best_score, best_strat, len(all_cands), time.time() - t_total


def main():
    print("=" * 80)
    print("CHAT Y — MATCH TEST v3 (Improved scoring + producer penalty)")
    print("=" * 80)

    conn = psycopg2.connect(LOCAL_DB)
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM vivino_match")
    print(f"vivino_match: {cur.fetchone()[0]:,}")
    cur.execute("SET pg_trgm.similarity_threshold = 0.15")

    # Get 100 test wines — use fixed seed for reproducibility
    cur.execute("""
        SELECT m.unique_id, u.nome_normalizado, u.produtor_normalizado, u.safra, u.tipo, u.pais_tabela, u.regiao
        FROM match_results_g2 m
        JOIN wines_unique u ON u.id = m.unique_id
        WHERE m.match_level = 'no_match'
          AND u.tipo IS NOT NULL AND u.tipo NOT IN ('NaN', 'Wine')
          AND u.safra IS NOT NULL
          AND u.produtor_normalizado IS NOT NULL AND u.produtor_normalizado != 'None'
          AND length(u.nome_normalizado) > 10
        ORDER BY m.unique_id
        LIMIT 100
    """)

    test_wines = [{
        'id': r[0], 'nome_normalizado': r[1], 'produtor_normalizado': r[2],
        'safra': r[3], 'tipo': r[4], 'pais_tabela': r[5], 'regiao': r[6],
    } for r in cur.fetchall()]

    print(f"Test wines: {len(test_wines)}\n")

    results = {'high': [], 'medium': [], 'low': [], 'none': []}
    strat_counts = Counter()
    total_time = 0

    for i, wine in enumerate(test_wines):
        best, score, strat, n_cand, elapsed = find_best_match(cur, wine)
        total_time += elapsed
        strat_counts[strat] += 1

        entry = {
            'store': wine, 'vivino': best, 'score': score,
            'strategy': strat, 'n_candidates': n_cand, 'time': elapsed,
        }

        if score >= THRESHOLD_HIGH:
            results['high'].append(entry)
        elif score >= THRESHOLD_MEDIUM:
            results['medium'].append(entry)
        elif score >= THRESHOLD_LOW:
            results['low'].append(entry)
        else:
            results['none'].append(entry)

        if (i + 1) % 10 == 0:
            h, m = len(results['high']), len(results['medium'])
            pct = (h + m) / (i + 1) * 100
            print(f"  [{i+1}/100] high={h} med={m} rate={pct:.1f}% avg={total_time/(i+1)*1000:.0f}ms")

    h, m, lo, no = len(results['high']), len(results['medium']), len(results['low']), len(results['none'])
    total = len(test_wines)

    print("\n" + "=" * 80)
    print("RESULTADOS")
    print("=" * 80)
    print(f"\nTotal: {total}")
    print(f"  Alta confiança (>={THRESHOLD_HIGH}):       {h:3d} ({h/total*100:5.1f}%)")
    print(f"  Média confiança ({THRESHOLD_MEDIUM}-{THRESHOLD_HIGH}):  {m:3d} ({m/total*100:5.1f}%)")
    print(f"  Baixa confiança ({THRESHOLD_LOW}-{THRESHOLD_MEDIUM}):  {lo:3d} ({lo/total*100:5.1f}%)")
    print(f"  Sem match (<{THRESHOLD_LOW}):            {no:3d} ({no/total*100:5.1f}%)")
    print(f"\n  >>> TAXA DE MATCH (alta+média): {(h+m)/total*100:.1f}% <<<")
    print(f"  >>> COM BAIXA: {(h+m+lo)/total*100:.1f}% <<<")
    print(f"\n  Tempo médio: {total_time/total*1000:.0f}ms/vinho")

    print(f"\nEstratégia:")
    for s, c in strat_counts.most_common():
        print(f"  {s}: {c}")

    # Show ALL results for manual review
    for label, key, n in [
        ("ALTA CONFIANÇA", 'high', 20),
        ("MÉDIA CONFIANÇA", 'medium', 20),
        ("BAIXA CONFIANÇA", 'low', 10),
        ("SEM MATCH", 'none', 10),
    ]:
        items = results[key][:n]
        if not items:
            continue
        print(f"\n{'─'*80}")
        print(f"{label} ({len(results[key])} total, showing {len(items)})")
        print(f"{'─'*80}")
        for r in items:
            s = r['store']
            v = r['vivino']
            print(f"\n  LOJA: \"{s['nome_normalizado']}\"")
            print(f"        prod={s['produtor_normalizado']} safra={s['safra']} tipo={s['tipo']}")
            if v:
                print(f"  VIV:  \"{v['produtor_normalizado']} — {v['nome_normalizado']}\"")
                print(f"        safra={v['safra']} tipo={v['tipo']} pais={v.get('pais')}")
                print(f"  Score={r['score']:.3f} Strat={r['strategy']} Cands={r['n_candidates']} T={r['time']*1000:.0f}ms")
            else:
                print(f"  → 0 candidatos ({r['time']*1000:.0f}ms)")

    conn.close()
    print("\nDone.")


if __name__ == '__main__':
    main()
