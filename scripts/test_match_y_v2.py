"""
Chat Y — Match Test v2: Producer-first + pg_trgm fallback
Optimized for speed: producer ILIKE (~0.03s) first, trgm (~17s) only when needed.
"""
import psycopg2
import sys
import io
import re
import time
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LOCAL_DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

THRESHOLD_HIGH = 0.50
THRESHOLD_MEDIUM = 0.35
THRESHOLD_LOW = 0.25

TIPO_MAP = {
    'Tinto': 'tinto', 'Branco': 'branco', 'Rose': 'rose',
    'Espumante': 'espumante', 'Fortificado': 'fortificado', 'Sobremesa': 'sobremesa',
}


def tokenize(text):
    if not text:
        return []
    return [w for w in re.split(r'[^a-zA-Z0-9àáâãäåèéêëìíîïòóôõöùúûüñç]+', text.lower()) if len(w) > 1]


def token_overlap(a_tokens, b_tokens):
    if not a_tokens or not b_tokens:
        return 0.0
    sa, sb = set(a_tokens), set(b_tokens)
    return len(sa & sb) / len(sa)


def score_candidate(store, viv):
    """Score 0.0 to 1.0"""
    st = tokenize(store['nome_normalizado'])
    vt = tokenize(f"{viv['produtor_normalizado'] or ''} {viv['nome_normalizado'] or ''}")

    # Forward token overlap (0.45)
    score = token_overlap(st, vt) * 0.45
    # Reverse token overlap (0.20)
    score += token_overlap(vt, st) * 0.20
    # Producer match (0.15)
    sp = tokenize(store.get('produtor_normalizado', ''))
    vp = tokenize(viv.get('produtor_normalizado', ''))
    if sp and vp:
        score += token_overlap(sp, vp) * 0.15
    # Safra (0.12)
    ss = str(store.get('safra', ''))
    vs = str(viv.get('safra', '')).strip()
    if ss and vs and ss == vs:
        score += 0.12
    # Tipo (0.08)
    s_tipo = TIPO_MAP.get(store.get('tipo', ''), '')
    v_tipo = (viv.get('tipo', '') or '').lower()
    if s_tipo and v_tipo and s_tipo == v_tipo:
        score += 0.08
    return score


def make_viv_dict(row):
    return {
        'id': row[0], 'nome_normalizado': row[1], 'produtor_normalizado': row[2],
        'safra': row[3], 'tipo': row[4], 'pais': row[5], 'regiao': row[6],
    }


def search_by_producer(cur, store):
    """Strategy 1: Search by producer keywords (FAST)"""
    produtor = store.get('produtor_normalizado', '') or ''
    if produtor == 'None' or len(produtor) < 3:
        return []

    # Use distinct words as anchors
    words = [w for w in produtor.split() if len(w) >= 3]
    if not words:
        return []

    candidates = []

    # Try longest producer word first
    anchor = max(words, key=len)
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
        FROM vivino_match
        WHERE produtor_normalizado ILIKE %s
        LIMIT 200
    """, (f'%{anchor}%',))
    for row in cur.fetchall():
        candidates.append(make_viv_dict(row))

    # If too few results and we have more words, try second word
    if len(candidates) < 5 and len(words) >= 2:
        second = sorted(words, key=len, reverse=True)[1]
        if len(second) >= 4:
            cur.execute("""
                SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
                FROM vivino_match
                WHERE produtor_normalizado ILIKE %s AND produtor_normalizado ILIKE %s
                LIMIT 100
            """, (f'%{anchor}%', f'%{second}%'))
            extra = [make_viv_dict(row) for row in cur.fetchall()]
            seen = {c['id'] for c in candidates}
            for e in extra:
                if e['id'] not in seen:
                    candidates.append(e)

    return candidates


def search_by_keyword_nome(cur, store):
    """Strategy 2: Search distinctive keywords in Vivino nome (FAST)"""
    tokens = tokenize(store['nome_normalizado'])
    # Get distinctive long tokens (not years)
    distinctive = [t for t in tokens if len(t) >= 5 and not re.match(r'^\d{4}$', t)]
    if not distinctive:
        return []

    candidates = []
    # Try longest distinctive token in nome
    longest = max(distinctive, key=len)
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
        FROM vivino_match
        WHERE nome_normalizado ILIKE %s
        LIMIT 100
    """, (f'%{longest}%',))
    for row in cur.fetchall():
        candidates.append(make_viv_dict(row))

    # Also try in produtor
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
        FROM vivino_match
        WHERE produtor_normalizado ILIKE %s
        LIMIT 100
    """, (f'%{longest}%',))
    seen = {c['id'] for c in candidates}
    for row in cur.fetchall():
        d = make_viv_dict(row)
        if d['id'] not in seen:
            candidates.append(d)

    return candidates


def search_by_trgm(cur, store):
    """Strategy 3: pg_trgm similarity on texto_busca (SLOW - fallback only)"""
    nome = store['nome_normalizado']
    if not nome or len(nome) < 5:
        return []

    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao,
               similarity(texto_busca, %s) as sim
        FROM vivino_match
        WHERE texto_busca %% %s
        ORDER BY sim DESC
        LIMIT 10
    """, (nome, nome))
    candidates = []
    for row in cur.fetchall():
        d = make_viv_dict(row)
        d['trgm_sim'] = row[7]
        candidates.append(d)
    return candidates


def search_by_trgm_nome(cur, store):
    """Strategy 4: pg_trgm on nome only (MEDIUM speed)"""
    tokens = tokenize(store['nome_normalizado'])
    nome_clean = ' '.join(t for t in tokens if not re.match(r'^\d{4}$', t))
    if len(nome_clean) < 5:
        return []

    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao,
               similarity(nome_normalizado, %s) as sim
        FROM vivino_match
        WHERE nome_normalizado %% %s
        ORDER BY sim DESC
        LIMIT 10
    """, (nome_clean, nome_clean))
    candidates = []
    for row in cur.fetchall():
        d = make_viv_dict(row)
        d['trgm_sim'] = row[7]
        candidates.append(d)
    return candidates


def find_best_match(cur, store):
    """Try strategies in order of speed, return best (candidate, score, strategy)"""

    # Phase 1: Fast strategies (producer + keyword)
    all_candidates = {}

    t0 = time.time()
    for c in search_by_producer(cur, store):
        all_candidates[c['id']] = (c, 'producer')
    t_prod = time.time() - t0

    t0 = time.time()
    for c in search_by_keyword_nome(cur, store):
        if c['id'] not in all_candidates:
            all_candidates[c['id']] = (c, 'keyword')
    t_kw = time.time() - t0

    # Score all fast candidates
    best_score = 0
    best = None
    best_strat = 'none'

    for cid, (cand, strat) in all_candidates.items():
        s = score_candidate(store, cand)
        if s > best_score:
            best_score = s
            best = cand
            best_strat = strat

    # If fast strategies found a good match, return it
    if best_score >= THRESHOLD_MEDIUM:
        return best, best_score, best_strat, len(all_candidates), t_prod + t_kw

    # Phase 2: Slow strategies (pg_trgm) — only if no good match yet
    t0 = time.time()
    trgm_candidates = search_by_trgm_nome(cur, store)
    t_trgm = time.time() - t0

    for c in trgm_candidates:
        s = score_candidate(store, c)
        if s > best_score:
            best_score = s
            best = c
            best_strat = 'trgm_nome'

    if best_score >= THRESHOLD_LOW:
        return best, best_score, best_strat, len(all_candidates) + len(trgm_candidates), t_prod + t_kw + t_trgm

    # Phase 3: Slowest fallback — trgm on combined texto_busca
    t0 = time.time()
    trgm2 = search_by_trgm(cur, store)
    t_trgm2 = time.time() - t0

    for c in trgm2:
        s = score_candidate(store, c)
        if s > best_score:
            best_score = s
            best = c
            best_strat = 'trgm_combined'

    total_cand = len(all_candidates) + len(trgm_candidates) + len(trgm2)
    total_time = t_prod + t_kw + t_trgm + t_trgm2
    return best, best_score, best_strat, total_cand, total_time


def main():
    print("=" * 80)
    print("CHAT Y — MATCH TEST v2 (Producer-first + trgm fallback)")
    print("=" * 80)

    conn = psycopg2.connect(LOCAL_DB)
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM vivino_match")
    print(f"vivino_match: {cur.fetchone()[0]:,}")
    cur.execute("SET pg_trgm.similarity_threshold = 0.15")

    # Get 100 test wines
    cur.execute("""
        SELECT m.unique_id, u.nome_normalizado, u.produtor_normalizado, u.safra, u.tipo, u.pais_tabela, u.regiao
        FROM match_results_g2 m
        JOIN wines_unique u ON u.id = m.unique_id
        WHERE m.match_level = 'no_match'
          AND u.tipo IS NOT NULL AND u.tipo NOT IN ('NaN', 'Wine')
          AND u.safra IS NOT NULL
          AND u.produtor_normalizado IS NOT NULL AND u.produtor_normalizado != 'None'
          AND length(u.nome_normalizado) > 10
        ORDER BY random()
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
    phase_counts = {'fast_only': 0, 'needed_trgm': 0}

    for i, wine in enumerate(test_wines):
        best, score, strat, n_cand, elapsed = find_best_match(cur, wine)
        total_time += elapsed
        strat_counts[strat] += 1

        if strat in ('producer', 'keyword'):
            phase_counts['fast_only'] += 1
        elif strat in ('trgm_nome', 'trgm_combined'):
            phase_counts['needed_trgm'] += 1

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
            avg_ms = total_time / (i + 1) * 1000
            print(f"  [{i+1}/100] high={h} med={m} rate={pct:.1f}% avg={avg_ms:.0f}ms/wine")

    # ── RESULTS ──
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
    print(f"  >>> COM BAIXA CONFIANÇA:        {(h+m+lo)/total*100:.1f}% <<<")
    print(f"\n  Tempo médio: {total_time/total*1000:.0f}ms/vinho")
    print(f"  Resolvidos só com busca rápida: {phase_counts['fast_only']}")
    print(f"  Precisaram de trgm:             {phase_counts['needed_trgm']}")

    print(f"\nEstratégia vencedora:")
    for s, c in strat_counts.most_common():
        print(f"  {s}: {c}")

    # Show examples
    for label, key, n in [
        ("ALTA CONFIANÇA", 'high', 15),
        ("MÉDIA CONFIANÇA", 'medium', 10),
        ("BAIXA CONFIANÇA", 'low', 5),
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
            print(f"\n  LOJA:   \"{s['nome_normalizado']}\"")
            print(f"          prod={s['produtor_normalizado']} safra={s['safra']} tipo={s['tipo']}")
            if v:
                print(f"  VIVINO: \"{v['produtor_normalizado']} — {v['nome_normalizado']}\"")
                print(f"          safra={v['safra']} tipo={v['tipo']} pais={v.get('pais')}")
                print(f"  Score={r['score']:.3f} Strategy={r['strategy']} Candidates={r['n_candidates']} Time={r['time']*1000:.0f}ms")
            else:
                print(f"  → 0 candidatos")

    conn.close()
    print("\nDone.")


if __name__ == '__main__':
    main()
