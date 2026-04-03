"""
Gera lista compacta dos 200 vinhos aleatorios com seus matches.
Salva em arquivo TXT para o fundador verificar.
"""
import psycopg2
import sys
import io
import re
import time

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
    if not text: return []
    return [w for w in re.split(r'[^a-zA-Z0-9àáâãäåèéêëìíîïòóôõöùúûüñç]+', text.lower()) if len(w) > 1]

def distinctive_tokens(tokens):
    return [t for t in tokens if t not in GENERIC_WORDS and not re.match(r'^\d{4}$', t) and len(t) >= 3]

def token_overlap(a, b):
    if not a or not b: return 0.0
    return len(set(a) & set(b)) / len(set(a))

def score_candidate(store, viv):
    st = tokenize(store['nome_normalizado'])
    vt = tokenize(f"{viv['produtor_normalizado'] or ''} {viv['nome_normalizado'] or ''}")
    store_dist, viv_dist = distinctive_tokens(st), distinctive_tokens(vt)
    fwd = token_overlap(store_dist, viv_dist) if store_dist and viv_dist else token_overlap(st, vt)
    score = fwd * 0.35 + token_overlap(st, vt) * 0.10 + token_overlap(vt, st) * 0.10
    sp, vp = tokenize(store.get('produtor_normalizado', '')), tokenize(viv.get('produtor_normalizado', ''))
    sp_d, vp_d = distinctive_tokens(sp), distinctive_tokens(vp)
    if sp_d and vp_d:
        ps = max(token_overlap(sp_d, vp_d), token_overlap(vp_d, sp_d))
        score += ps * 0.25 if ps > 0 else -0.10
    elif sp and vp:
        score += token_overlap(sp, vp) * 0.15
    ss, vs = str(store.get('safra', '') or ''), str(viv.get('safra', '') or '').strip()
    if ss and vs and ss == vs: score += 0.12
    elif ss and vs and ss != vs: score -= 0.02
    st2 = TIPO_MAP.get(store.get('tipo', '') or '', '')
    vt2 = (viv.get('tipo', '') or '').lower()
    if st2 and vt2:
        if st2 == vt2: score += 0.08
        elif {st2, vt2} & {'tinto', 'branco'} == {st2, vt2}: score -= 0.05
    return max(0.0, min(1.0, score))

def make_viv(row):
    return {'id': row[0], 'nome_normalizado': row[1], 'produtor_normalizado': row[2],
            'safra': row[3], 'tipo': row[4], 'pais': row[5], 'regiao': row[6]}

def search_producer(cur, store):
    p = store.get('produtor_normalizado', '') or ''
    if p == 'None' or len(p) < 3: return []
    words = [w for w in p.split() if len(w) >= 3 and w not in GENERIC_WORDS]
    if not words: words = [w for w in p.split() if len(w) >= 3]
    if not words: return []
    anchor = max(words, key=len)
    cur.execute("SELECT id,nome_normalizado,produtor_normalizado,safra,tipo,pais,regiao FROM vivino_match WHERE produtor_normalizado ILIKE %s LIMIT 200", (f'%{anchor}%',))
    return [make_viv(r) for r in cur.fetchall()]

def search_keyword(cur, store):
    tokens = tokenize(store['nome_normalizado'])
    dist = [t for t in tokens if len(t) >= 5 and t not in GENERIC_WORDS and not re.match(r'^\d{4}$', t)]
    if not dist: return []
    longest = max(dist, key=len)
    cur.execute("SELECT id,nome_normalizado,produtor_normalizado,safra,tipo,pais,regiao FROM vivino_match WHERE nome_normalizado ILIKE %s OR produtor_normalizado ILIKE %s LIMIT 150", (f'%{longest}%', f'%{longest}%'))
    return [make_viv(r) for r in cur.fetchall()]

def search_trgm_nome(cur, store):
    tokens = tokenize(store['nome_normalizado'])
    nc = ' '.join(t for t in tokens if not re.match(r'^\d{4}$', t))
    if len(nc) < 5: return []
    cur.execute("SELECT id,nome_normalizado,produtor_normalizado,safra,tipo,pais,regiao FROM vivino_match WHERE nome_normalizado %% %s ORDER BY similarity(nome_normalizado, %s) DESC LIMIT 10", (nc, nc))
    return [make_viv(r) for r in cur.fetchall()]

def search_trgm_combined(cur, store):
    nome = store['nome_normalizado']
    if not nome or len(nome) < 5: return []
    cur.execute("SELECT id,nome_normalizado,produtor_normalizado,safra,tipo,pais,regiao FROM vivino_match WHERE texto_busca %% %s ORDER BY similarity(texto_busca, %s) DESC LIMIT 10", (nome, nome))
    return [make_viv(r) for r in cur.fetchall()]

def find_best(cur, store):
    cands = {}
    for c in search_producer(cur, store): cands[c['id']] = (c, 'prod')
    for c in search_keyword(cur, store):
        if c['id'] not in cands: cands[c['id']] = (c, 'kw')
    best, bs, bst = None, 0, 'none'
    for cid, (c, st) in cands.items():
        s = score_candidate(store, c)
        if s > bs: bs, best, bst = s, c, st
    if bs >= THRESHOLD_MEDIUM:
        return best, bs, bst
    for c in search_trgm_nome(cur, store):
        s = score_candidate(store, c)
        if s > bs: bs, best, bst = s, c, 'trgm'
    if bs >= THRESHOLD_LOW:
        return best, bs, bst
    for c in search_trgm_combined(cur, store):
        s = score_candidate(store, c)
        if s > bs: bs, best, bst = s, c, 'trgm'
    return best, bs, bst

def main():
    conn = psycopg2.connect(LOCAL_DB)
    cur = conn.cursor()
    cur.execute("SET pg_trgm.similarity_threshold = 0.15")

    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais_tabela, regiao
        FROM wines_unique ORDER BY random() LIMIT 200
    """)
    wines = [{'id': r[0], 'nome_normalizado': r[1], 'produtor_normalizado': r[2],
              'safra': r[3], 'tipo': r[4], 'pais_tabela': r[5], 'regiao': r[6]} for r in cur.fetchall()]

    out = open('scripts/lista_200_vinhos.txt', 'w', encoding='utf-8')

    def p(text=''):
        print(text)
        out.write(text + '\n')

    p("LISTA DE 200 VINHOS ALEATORIOS — VERIFICACAO VISUAL")
    p("=" * 100)
    p(f"{'#':>3}  {'NIVEL':>6}  {'SCORE':>5}  LOJA → VIVINO")
    p("-" * 100)

    stats = {'HIGH': 0, 'MED': 0, 'LOW': 0, 'NADA': 0}

    for i, w in enumerate(wines):
        best, score, strat = find_best(cur, w)

        if score >= THRESHOLD_HIGH:
            nivel = 'HIGH'
            tag = '  OK '
        elif score >= THRESHOLD_MEDIUM:
            nivel = 'MED'
            tag = '  ?? '
        elif score >= THRESHOLD_LOW:
            nivel = 'LOW'
            tag = '  ~  '
        else:
            nivel = 'NADA'
            tag = '  XX '

        stats[nivel] += 1

        loja = w['nome_normalizado'] or '(vazio)'
        safra_l = w['safra'] or ''
        tipo_l = w['tipo'] or ''

        if best and score >= THRESHOLD_LOW:
            viv = f"{best['produtor_normalizado'] or '?'} — {best['nome_normalizado'] or '?'}"
            safra_v = best['safra'] or ''
            tipo_v = best['tipo'] or ''
            p(f"{i+1:3d} [{tag}] {score:.2f}  \"{loja}\" [{tipo_l}][{safra_l}]")
            p(f"              →  \"{viv}\" [{tipo_v}][{safra_v}]")
        else:
            p(f"{i+1:3d} [{tag}] {score:.2f}  \"{loja}\" [{tipo_l}][{safra_l}]")
            p(f"              →  (sem match)")

        if (i+1) % 20 == 0:
            h, m = stats['HIGH'], stats['MED']
            print(f"  ... {i+1}/200 processados, high={h} med={m}", file=sys.stderr)

    p("")
    p("=" * 100)
    p(f"RESUMO: HIGH={stats['HIGH']}  MEDIUM={stats['MED']}  LOW={stats['LOW']}  SEM_MATCH={stats['NADA']}")
    p(f"TAXA (HIGH+MED): {(stats['HIGH']+stats['MED'])/200*100:.0f}%")
    p("=" * 100)

    out.close()
    conn.close()
    print(f"\nArquivo salvo: scripts/lista_200_vinhos.txt", file=sys.stderr)

if __name__ == '__main__':
    main()
