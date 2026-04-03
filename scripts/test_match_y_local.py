"""
Chat Y — Test match approach: multi-strategy token-based matching (LOCAL)
Uses vivino_match table imported locally for speed.
Tests on 100 no_match wines from match_results_g2.
"""
import psycopg2
import sys
import io
import re
import time
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LOCAL_DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

# Minimum score thresholds
THRESHOLD_HIGH = 0.50
THRESHOLD_MEDIUM = 0.35
THRESHOLD_LOW = 0.25


def tokenize(text):
    """Split text into lowercase tokens"""
    if not text:
        return []
    return [w for w in re.split(r'[^a-zA-Z0-9àáâãäåèéêëìíîïòóôõöùúûüñç]+', text.lower()) if len(w) > 1]


def token_overlap(tokens_a, tokens_b):
    """Fraction of A tokens found in B"""
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    common = set_a & set_b
    return len(common) / len(set_a) if set_a else 0.0


TIPO_MAP = {
    'Tinto': 'tinto', 'Branco': 'branco', 'Rose': 'rose',
    'Espumante': 'espumante', 'Fortificado': 'fortificado', 'Sobremesa': 'sobremesa',
}


def score_candidate(store_wine, viv):
    """Score a candidate match. Returns 0.0-1.0"""
    store_tokens = tokenize(store_wine['nome_normalizado'])
    viv_tokens = tokenize(f"{viv['produtor_normalizado'] or ''} {viv['nome_normalizado'] or ''}")

    # Token overlap: store→vivino (weight 0.45)
    fwd = token_overlap(store_tokens, viv_tokens)
    # Token overlap: vivino→store (weight 0.20)
    rev = token_overlap(viv_tokens, store_tokens)
    score = fwd * 0.45 + rev * 0.20

    # Producer match (weight 0.15)
    store_prod = tokenize(store_wine.get('produtor_normalizado', ''))
    viv_prod = tokenize(viv.get('produtor_normalizado', ''))
    if store_prod and viv_prod:
        score += token_overlap(store_prod, viv_prod) * 0.15

    # Safra match (weight 0.12)
    s_safra = str(store_wine.get('safra', ''))
    v_safra = str(viv.get('safra', '')).strip()
    if s_safra and v_safra and s_safra == v_safra:
        score += 0.12

    # Tipo match (weight 0.08)
    s_tipo = TIPO_MAP.get(store_wine.get('tipo', ''), '')
    v_tipo = (viv.get('tipo', '') or '').lower()
    if s_tipo and v_tipo and s_tipo == v_tipo:
        score += 0.08

    return score


def search_candidates(cur, store_wine):
    """
    Multi-strategy search for Vivino candidates.
    Returns list of (candidate_dict, score, strategy) tuples, best first.
    """
    candidates = {}  # id -> (dict, strategy)
    nome = store_wine['nome_normalizado'] or ''
    produtor = store_wine.get('produtor_normalizado', '') or ''

    # ── Strategy 1: pg_trgm similarity on texto_busca (combined field) ──
    # This is the most important strategy: compares full store name against
    # "produtor + nome" from Vivino
    if len(nome) >= 5:
        cur.execute("""
            SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao,
                   similarity(texto_busca, %s) as sim
            FROM vivino_match
            WHERE texto_busca %% %s
            ORDER BY sim DESC
            LIMIT 15
        """, (nome, nome))
        for row in cur.fetchall():
            cid = row[0]
            if cid not in candidates:
                candidates[cid] = ({
                    'id': row[0], 'nome_normalizado': row[1], 'produtor_normalizado': row[2],
                    'safra': row[3], 'tipo': row[4], 'pais': row[5], 'regiao': row[6],
                    'trgm_sim': row[7]
                }, 'trgm_combined')

    # ── Strategy 2: Producer ILIKE + pick best from results ──
    if produtor and produtor != 'None' and len(produtor) >= 3:
        # Use longest word from producer as anchor
        prod_words = [w for w in produtor.split() if len(w) >= 3]
        if prod_words:
            anchor = max(prod_words, key=len)
            if len(anchor) >= 3:
                cur.execute("""
                    SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
                    FROM vivino_match
                    WHERE produtor_normalizado ILIKE %s
                    LIMIT 100
                """, (f'%{anchor}%',))
                for row in cur.fetchall():
                    cid = row[0]
                    if cid not in candidates:
                        candidates[cid] = ({
                            'id': row[0], 'nome_normalizado': row[1], 'produtor_normalizado': row[2],
                            'safra': row[3], 'tipo': row[4], 'pais': row[5], 'regiao': row[6],
                        }, 'producer')

    # ── Strategy 3: pg_trgm on nome_normalizado only ──
    # Useful when store name = just the wine name (no producer)
    tokens = tokenize(nome)
    # Remove year tokens for nome search
    nome_no_year = ' '.join(t for t in tokens if not re.match(r'^\d{4}$', t))
    if len(nome_no_year) >= 5:
        cur.execute("""
            SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao,
                   similarity(nome_normalizado, %s) as sim
            FROM vivino_match
            WHERE nome_normalizado %% %s
            ORDER BY sim DESC
            LIMIT 10
        """, (nome_no_year, nome_no_year))
        for row in cur.fetchall():
            cid = row[0]
            if cid not in candidates:
                candidates[cid] = ({
                    'id': row[0], 'nome_normalizado': row[1], 'produtor_normalizado': row[2],
                    'safra': row[3], 'tipo': row[4], 'pais': row[5], 'regiao': row[6],
                    'trgm_sim': row[7]
                }, 'trgm_nome')

    # ── Strategy 4: Keyword ILIKE on nome ──
    # Fallback: search by the most distinctive long word
    distinctive = [t for t in tokens if len(t) >= 5 and not re.match(r'^\d{4}$', t)]
    if distinctive and not candidates:
        longest = max(distinctive, key=len)
        cur.execute("""
            SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
            FROM vivino_match
            WHERE nome_normalizado ILIKE %s
            LIMIT 50
        """, (f'%{longest}%',))
        for row in cur.fetchall():
            cid = row[0]
            if cid not in candidates:
                candidates[cid] = ({
                    'id': row[0], 'nome_normalizado': row[1], 'produtor_normalizado': row[2],
                    'safra': row[3], 'tipo': row[4], 'pais': row[5], 'regiao': row[6],
                }, 'keyword')

    # Score all candidates
    scored = []
    for cid, (cand, strategy) in candidates.items():
        s = score_candidate(store_wine, cand)
        scored.append((cand, s, strategy))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def main():
    print("=" * 80)
    print("CHAT Y — MATCH TEST v2 (LOCAL)")
    print("Multi-strategy: pg_trgm combined + producer + trgm_nome + keyword")
    print("=" * 80)

    conn = psycopg2.connect(LOCAL_DB)
    cur = conn.cursor()

    # Check vivino_match
    cur.execute("SELECT count(*) FROM vivino_match")
    vcount = cur.fetchone()[0]
    print(f"\nvivino_match: {vcount:,} wines")

    # Set trgm threshold low for broader search
    cur.execute("SET pg_trgm.similarity_threshold = 0.15")

    # Get 100 real wine no_match samples
    cur.execute("""
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
    for row in cur.fetchall():
        test_wines.append({
            'id': row[0], 'nome_normalizado': row[1], 'produtor_normalizado': row[2],
            'safra': row[3], 'tipo': row[4], 'pais_tabela': row[5], 'regiao': row[6],
        })

    print(f"Loaded {len(test_wines)} test wines\n")

    # Run matching
    results = {'high': [], 'medium': [], 'low': [], 'none': []}
    strategy_stats = Counter()
    total_time = 0

    for i, wine in enumerate(test_wines):
        t0 = time.time()
        scored = search_candidates(cur, wine)
        elapsed = time.time() - t0
        total_time += elapsed

        if scored:
            best, best_score, best_strategy = scored[0]
            strategy_stats[best_strategy] += 1

            entry = {
                'store': wine, 'vivino': best, 'score': best_score,
                'strategy': best_strategy, 'n_candidates': len(scored), 'time': elapsed,
            }
            if best_score >= THRESHOLD_HIGH:
                results['high'].append(entry)
            elif best_score >= THRESHOLD_MEDIUM:
                results['medium'].append(entry)
            elif best_score >= THRESHOLD_LOW:
                results['low'].append(entry)
            else:
                results['none'].append(entry)
        else:
            results['none'].append({
                'store': wine, 'vivino': None, 'score': 0,
                'strategy': 'none', 'n_candidates': 0, 'time': elapsed,
            })

        if (i + 1) % 10 == 0:
            h, m = len(results['high']), len(results['medium'])
            pct = (h + m) / (i + 1) * 100
            print(f"  [{i+1}/100] high={h} med={m} rate={pct:.1f}% avg={total_time/(i+1)*1000:.0f}ms/wine")

    # ── RESULTS ──
    h = len(results['high'])
    m = len(results['medium'])
    lo = len(results['low'])
    no = len(results['none'])
    total = len(test_wines)

    print("\n" + "=" * 80)
    print("RESULTADOS")
    print("=" * 80)
    print(f"\nTotal testado: {total}")
    print(f"  Alta confiança (>={THRESHOLD_HIGH}): {h} ({h/total*100:.1f}%)")
    print(f"  Média confiança ({THRESHOLD_MEDIUM}-{THRESHOLD_HIGH}): {m} ({m/total*100:.1f}%)")
    print(f"  Baixa confiança ({THRESHOLD_LOW}-{THRESHOLD_MEDIUM}): {lo} ({lo/total*100:.1f}%)")
    print(f"  Sem match (<{THRESHOLD_LOW}): {no} ({no/total*100:.1f}%)")
    print(f"\n  >>> TAXA DE MATCH (alta+média): {(h+m)/total*100:.1f}% <<<")
    print(f"  >>> TAXA TOTAL (alta+média+baixa): {(h+m+lo)/total*100:.1f}% <<<")
    print(f"  Tempo médio: {total_time/total*1000:.0f}ms/vinho")

    print(f"\nEstratégia vencedora:")
    for s, c in strategy_stats.most_common():
        print(f"  {s}: {c}")

    # Show examples
    for label, key in [("ALTA CONFIANÇA", 'high'), ("MÉDIA CONFIANÇA", 'medium'), ("SEM MATCH", 'none')]:
        print(f"\n{'─'*80}")
        print(f"{label} (top 10)")
        print(f"{'─'*80}")
        for r in results[key][:10]:
            s = r['store']
            v = r['vivino']
            print(f"\n  LOJA:   \"{s['nome_normalizado']}\"")
            print(f"          produtor={s['produtor_normalizado']} safra={s['safra']} tipo={s['tipo']}")
            if v:
                print(f"  VIVINO: \"{v['produtor_normalizado']} — {v['nome_normalizado']}\"")
                print(f"          safra={v['safra']} tipo={v['tipo']} pais={v['pais']}")
                print(f"  Score: {r['score']:.3f} | Strategy: {r['strategy']} | Candidates: {r['n_candidates']}")
            else:
                print(f"  VIVINO: nenhum candidato encontrado")

    conn.close()
    print(f"\n\nDone.")


if __name__ == '__main__':
    main()
