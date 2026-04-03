"""
Test: 200 vinhos 100% aleatorios de wines_unique (sem filtro nenhum).
Mostra TODOS pra verificacao visual.
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
    return [t for t in tokens if t not in GENERIC_WORDS and not re.match(r'^\d{4}$', t) and len(t) >= 3]


def token_overlap(a, b):
    if not a or not b:
        return 0.0
    return len(set(a) & set(b)) / len(set(a))


def score_candidate(store, viv):
    st = tokenize(store['nome_normalizado'])
    vt = tokenize(f"{viv['produtor_normalizado'] or ''} {viv['nome_normalizado'] or ''}")
    store_dist = distinctive_tokens(st)
    viv_dist = distinctive_tokens(vt)
    if store_dist and viv_dist:
        fwd_dist = token_overlap(store_dist, viv_dist)
    else:
        fwd_dist = token_overlap(st, vt)
    score = fwd_dist * 0.35
    score += token_overlap(st, vt) * 0.10
    score += token_overlap(vt, st) * 0.10

    sp = tokenize(store.get('produtor_normalizado', ''))
    vp = tokenize(viv.get('produtor_normalizado', ''))
    sp_d = distinctive_tokens(sp)
    vp_d = distinctive_tokens(vp)
    if sp_d and vp_d:
        prod_score = max(token_overlap(sp_d, vp_d), token_overlap(vp_d, sp_d))
        if prod_score > 0:
            score += prod_score * 0.25
        else:
            score -= 0.10
    elif sp and vp:
        score += token_overlap(sp, vp) * 0.15

    ss = str(store.get('safra', '') or '')
    vs = str(viv.get('safra', '') or '').strip()
    if ss and vs and ss == vs:
        score += 0.12
    elif ss and vs and ss != vs:
        score -= 0.02

    s_tipo = TIPO_MAP.get(store.get('tipo', '') or '', '')
    v_tipo = (viv.get('tipo', '') or '').lower()
    if s_tipo and v_tipo:
        if s_tipo == v_tipo:
            score += 0.08
        elif {s_tipo, v_tipo} & {'tinto', 'branco'} == {s_tipo, v_tipo}:
            score -= 0.05

    return max(0.0, min(1.0, score))


def make_viv(row):
    return {
        'id': row[0], 'nome_normalizado': row[1], 'produtor_normalizado': row[2],
        'safra': row[3], 'tipo': row[4], 'pais': row[5], 'regiao': row[6],
    }


def search_producer(cur, store):
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
    return [make_viv(r) for r in cur.fetchall()]


def search_keyword(cur, store):
    tokens = tokenize(store['nome_normalizado'])
    distinctive = [t for t in tokens if len(t) >= 5 and t not in GENERIC_WORDS and not re.match(r'^\d{4}$', t)]
    if not distinctive:
        return []
    longest = max(distinctive, key=len)
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
        FROM vivino_match
        WHERE nome_normalizado ILIKE %s OR produtor_normalizado ILIKE %s
        LIMIT 150
    """, (f'%{longest}%', f'%{longest}%'))
    return [make_viv(r) for r in cur.fetchall()]


def search_trgm_nome(cur, store):
    tokens = tokenize(store['nome_normalizado'])
    nome_clean = ' '.join(t for t in tokens if not re.match(r'^\d{4}$', t))
    if len(nome_clean) < 5:
        return []
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
        FROM vivino_match WHERE nome_normalizado %% %s
        ORDER BY similarity(nome_normalizado, %s) DESC LIMIT 10
    """, (nome_clean, nome_clean))
    return [make_viv(r) for r in cur.fetchall()]


def search_trgm_combined(cur, store):
    nome = store['nome_normalizado']
    if not nome or len(nome) < 5:
        return []
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao
        FROM vivino_match WHERE texto_busca %% %s
        ORDER BY similarity(texto_busca, %s) DESC LIMIT 10
    """, (nome, nome))
    return [make_viv(r) for r in cur.fetchall()]


def find_best_match(cur, store):
    all_cands = {}
    for c in search_producer(cur, store):
        all_cands[c['id']] = (c, 'producer')
    for c in search_keyword(cur, store):
        if c['id'] not in all_cands:
            all_cands[c['id']] = (c, 'keyword')

    best, best_score, best_strat = None, 0, 'none'
    for cid, (cand, strat) in all_cands.items():
        s = score_candidate(store, cand)
        if s > best_score:
            best_score, best, best_strat = s, cand, strat

    if best_score >= THRESHOLD_MEDIUM:
        level = 'high' if best_score >= THRESHOLD_HIGH else 'medium'
        return best, best_score, best_strat, level

    for c in search_trgm_nome(cur, store):
        s = score_candidate(store, c)
        if s > best_score:
            best_score, best, best_strat = s, c, 'trgm_nome'

    if best_score >= THRESHOLD_LOW:
        level = 'high' if best_score >= THRESHOLD_HIGH else ('medium' if best_score >= THRESHOLD_MEDIUM else 'low')
        return best, best_score, best_strat, level

    for c in search_trgm_combined(cur, store):
        s = score_candidate(store, c)
        if s > best_score:
            best_score, best, best_strat = s, c, 'trgm_combined'

    if best and best_score >= THRESHOLD_LOW:
        level = 'high' if best_score >= THRESHOLD_HIGH else ('medium' if best_score >= THRESHOLD_MEDIUM else 'low')
        return best, best_score, best_strat, level

    return best, best_score, best_strat, 'no_match'


def main():
    conn = psycopg2.connect(LOCAL_DB)
    cur = conn.cursor()
    cur.execute("SET pg_trgm.similarity_threshold = 0.15")

    # 200 vinhos 100% aleatorios — SEM filtro nenhum
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais_tabela, regiao
        FROM wines_unique
        ORDER BY random()
        LIMIT 200
    """)

    wines = [{
        'id': r[0], 'nome_normalizado': r[1], 'produtor_normalizado': r[2],
        'safra': r[3], 'tipo': r[4], 'pais_tabela': r[5], 'regiao': r[6],
    } for r in cur.fetchall()]

    print(f"200 vinhos aleatorios carregados\n")

    all_results = []
    stats = Counter()
    t0 = time.time()

    for i, wine in enumerate(wines):
        best, score, strat, level = find_best_match(cur, wine)
        stats[level] += 1
        all_results.append({
            'store': wine, 'vivino': best, 'score': score,
            'strategy': strat, 'level': level,
        })
        if (i + 1) % 20 == 0:
            h, m = stats['high'], stats['medium']
            print(f"  [{i+1}/200] high={h} med={m} rate={(h+m)/(i+1)*100:.0f}%")

    elapsed = time.time() - t0
    h, m, lo, no = stats['high'], stats['medium'], stats['low'], stats['no_match']

    # ── RESUMO ──
    print("\n" + "=" * 90)
    print(f"RESULTADO: {h+m}/200 matched ({(h+m)/200*100:.0f}%)  |  high={h} med={m} low={lo} no_match={no}  |  {elapsed:.0f}s")
    print("=" * 90)

    # ── LISTA COMPLETA PRA VERIFICACAO VISUAL ──
    # Separar por nivel
    for level_name, emoji in [('high', 'OK'), ('medium', '??'), ('low', '~'), ('no_match', 'XX')]:
        items = [r for r in all_results if r['level'] == level_name]
        if not items:
            continue
        print(f"\n{'='*90}")
        print(f"  [{emoji}] {level_name.upper()} — {len(items)} vinhos")
        print(f"{'='*90}")

        for idx, r in enumerate(items, 1):
            s = r['store']
            v = r['vivino']
            nome_loja = s['nome_normalizado'] or '(vazio)'
            prod_loja = s['produtor_normalizado'] or ''
            safra_loja = s['safra'] or ''
            tipo_loja = s['tipo'] or ''
            pais_loja = s['pais_tabela'] or ''

            if v:
                nome_viv = f"{v['produtor_normalizado'] or ''} — {v['nome_normalizado'] or ''}"
                safra_viv = v['safra'] or ''
                tipo_viv = v['tipo'] or ''
                pais_viv = v['pais'] or ''
                print(f"\n  {idx:3d}. LOJA:   \"{nome_loja}\"  [{tipo_loja}] [{pais_loja}] [{safra_loja}]")
                print(f"       VIVINO: \"{nome_viv}\"  [{tipo_viv}] [{pais_viv}] [{safra_viv}]")
                print(f"       Score={r['score']:.3f}  Strat={r['strategy']}")
            else:
                print(f"\n  {idx:3d}. LOJA:   \"{nome_loja}\"  [{tipo_loja}] [{pais_loja}] [{safra_loja}]")
                print(f"       → SEM CANDIDATO")

    conn.close()
    print(f"\n\nFim. Verifique visualmente se os matches estao corretos.")


if __name__ == '__main__':
    main()
