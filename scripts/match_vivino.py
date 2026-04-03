"""
Pipeline de classificacao e match em escala — 3.96M vinhos (8 grupos paralelos)
Usage: python match_vivino.py GROUP_NUM
  GROUP_NUM: 1-8
Output: tabela match_results_y{GROUP_NUM} no banco local

Otimizado: vivino_match carregado em memoria (~200MB) com indice invertido.
Matching 100% em Python — sem queries DB no loop principal.
"""
import psycopg2
import sys
import re
import time
from collections import Counter, defaultdict

LOCAL_DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
BATCH_SIZE = 1000
PROGRESS_EVERY = 5000

GROUPS = {
    1: ['us'],
    2: ['br', 'es', 'be', 'in', 'il', 'tw'],
    3: ['au', 'nz', 'ie', 'ro', 'hu', 'bg', 'hr'],
    4: ['gb', 'fr', 'pe', 'gr', 'fi', 'jp', 'tr', 'th'],
    5: ['it', 'pt', 'at', 'za', 'md', 'ge', 'cn'],
    6: ['de', 'mx', 'ca', 'pl', 'se', 'cz', 'ae'],
    7: ['nl', 'hk', 'ph', 'ch', 'co', 'lu', 'no'],
    8: ['dk', 'ar', 'sg', 'uy', 'cl', 'ru', 'kr'],
}

# ═══════════════════════════════════════════════════════════
# FILTROS DE NAO-VINHO
# ═══════════════════════════════════════════════════════════

PALAVRAS_PROIBIDAS = {
    # Comida
    'arroz', 'feijao', 'farinha', 'acucar', 'sal', 'leite', 'manteiga', 'queijo',
    'chocolate', 'biscoito', 'biscuit', 'cookie', 'cracker', 'bread', 'pasta',
    'noodle', 'spaghetti', 'linguine', 'vermicelli', 'sotanghon', 'macaroni',
    'ketchup', 'mustard', 'mayonnaise', 'molho', 'sauce', 'vinegar',
    'honey', 'miel', 'mel', 'jam', 'jelly', 'marmelada', 'mermelada',
    'puree', 'cinnamon', 'garlic', 'pepper', 'oregano', 'tomato', 'pomodori',
    'olive', 'oliva', 'aceite', 'olio', 'beans', 'lentil', 'chickpea',
    'tuna', 'salmon', 'sardine', 'corned', 'sausage', 'ham', 'bacon',
    'chicken', 'frango', 'beef', 'pork', 'lamb', 'meat', 'carne',
    'rice', 'flour', 'sugar', 'butter', 'cheese', 'cream', 'yogurt',
    'cereal', 'granola', 'muesli', 'oat', 'oats', 'samp',
    # Objetos/Eletronicos
    'refrigerador', 'refrigerator', 'microwave', 'blender', 'toaster',
    'speaker', 'parlante', 'headphone', 'earphone', 'cable', 'charger',
    'phone', 'celular', 'tablet', 'laptop', 'computer', 'keyboard', 'mouse',
    'television', 'monitor', 'camera', 'printer', 'router',
    'furniture', 'sofa', 'chair', 'table', 'desk', 'shelf', 'cabinet',
    'pouf', 'cylinder', 'lamp', 'bulb', 'curtain',
    # Cosmeticos/Higiene
    'shampoo', 'conditioner', 'deodorant', 'desodorante', 'perfume', 'cologne',
    'lotion', 'moisturizer', 'sunscreen', 'lipstick', 'mascara', 'foundation',
    'hairspray', 'hair spray', 'pantene', 'dove', 'nivea', 'rexona',
    'toothpaste', 'toothbrush', 'dental', 'soap', 'sabonete', 'detergent',
    'inseticida', 'insecticide', 'repellent', 'aerosol', 'desinfetante',
    # Roupa/Sapatos
    'sapato', 'shoe', 'shoes', 'sneaker', 'sandal', 'boot', 'slipper',
    'camisa', 'shirt', 'blouse', 'dress', 'pants', 'jeans', 'shorts',
    'jacket', 'coat', 'sweater', 'sudadera', 'hoodie', 'sock', 'underwear',
    'jersey', 'uniform',
    # Papelaria/Escritorio
    'caneta', 'lapicero', 'pencil', 'eraser', 'notebook', 'folder', 'binder',
    'stapler', 'scissors', 'tape', 'glue', 'sticker', 'marker', 'crayon',
    # Ferramentas/Hardware
    'screwdriver', 'hammer', 'wrench', 'pliers', 'drill', 'saw', 'nail',
    'screw', 'bolt', 'pipe', 'hose', 'valve', 'filter', 'pump',
    'strainer', 'grifo', 'torneira', 'faucet',
    # Cervejaria/Mead/Outros
    'bryggeri', 'moonshine', 'cigar', 'cigars', 'charuto', 'charutos',
    'stout', 'lager', 'pilsner', 'ipa', 'beer', 'cerveza', 'cerveja',
    'brewery', 'hops',
    # Regioes de whisky
    'lowland', 'islay', 'campbeltown',
    'verjus', 'refill', 'steak', 'lakrids', 'speyside',
    # Brinquedos/Esportes
    'soccer', 'football', 'basketball', 'baseball', 'tennis', 'golf',
    'shin guard', 'helmet', 'racket', 'ball', 'toy', 'doll', 'puzzle',
    # Misc
    'diaper', 'fralda', 'towel', 'toalha', 'pillow', 'blanket', 'manta',
    'bag', 'mochila', 'backpack', 'suitcase', 'wallet', 'purse',
    'card', 'greeting', 'birthday', 'christmas', 'easter', 'valentine',
    'gift basket', 'cesta', 'neceser', 'estuche',
    'thermometer', 'termometro', 'termometer',
    'isqueiro', 'lighter', 'minijet',
}

PADROES_NAO_VINHO = [
    r'\b\d+\s*g\b',
    r'\b\d+\s*kg\b',
    r'\b\d+\s*oz\b',
    r'\b\d+\s*pcs\b',
    r'\b\d+\s*stk\b',
    r'\b\d+\s*tem\b',
    r'\bpack\s+of\b',
    r'\bbox\s+of\b',
    r'\bset\s+of\b',
    r'\brefil\b',
    r'\brecarga\b',
]

DESTILADOS = {
    'whisky', 'whiskey', 'bourbon', 'scotch', 'rye',
    'rum', 'rhum', 'ron',
    'gin', 'genever', 'genepi',
    'vodka',
    'tequila', 'mezcal',
    'cognac', 'armagnac', 'brandy', 'aguardente', 'grappa', 'marc',
    'cachaca', 'cachaça',
    'sake', 'shochu', 'soju', 'baijiu',
    'absinthe', 'absinto',
    'limoncello', 'amaretto', 'sambuca', 'ouzo', 'raki', 'arak',
    'kirsch', 'kirschwasser', 'schnapps', 'schnaps',
    'pisco',
    'liqueur', 'licor', 'likier', 'likor',
}

UVAS = {
    # Internacionais
    'cabernet', 'sauvignon', 'merlot', 'pinot', 'noir', 'grigio', 'gris',
    'chardonnay', 'syrah', 'shiraz', 'tempranillo', 'malbec', 'zinfandel',
    'sangiovese', 'nebbiolo', 'barbera', 'riesling', 'gewurztraminer',
    'chenin', 'viognier', 'mourvedre', 'grenache', 'garnacha', 'carmenere',
    'primitivo', 'gamay', 'muscat', 'moscato', 'moscatel',
    'torrontes', 'albarino', 'verdejo', 'gruner', 'veltliner',
    'montepulciano', 'lambrusco', 'corvina', 'glera', 'trebbiano',
    'vermentino', 'fiano', 'aglianico', 'dolcetto', 'arneis', 'cortese',
    'tannat', 'bonarda', 'touriga', 'tinta', 'bobal', 'monastrell',
    'cinsault', 'carignan', 'mencia', 'godello', 'alvarinho',
    'semillon', 'marsanne', 'roussanne', 'picpoul', 'clairette',
    'blaufrankisch', 'zweigelt', 'saperavi', 'rkatsiteli',
    'pinotage', 'petite', 'sirah', 'petit', 'verdot',
    'semillion', 'gewurz',
    # Sinonimos internacionais
    'spatburgunder', 'blauburgunder', 'grauburgunder', 'weissburgunder',
    'cannonau', 'aragonez', 'cencibel', 'mataro', 'nielluccio',
    'morellino', 'prugnolo', 'kekfrankos', 'lemberger', 'frankovka',
    'mazuelo', 'samso', 'traminer', 'tribidrag', 'chiavennasca',
    # Alemanha/Austria
    'dornfelder', 'silvaner', 'kerner', 'scheurebe', 'trollinger',
    'rotgipfler', 'zierfandler', 'neuburger', 'welschriesling', 'olaszrizling',
    # Portugal
    'castelao', 'trincadeira', 'encruzado', 'arinto', 'loureiro',
    'verdelho', 'boal', 'sercial', 'viosinho', 'gouveio',
    'sousao', 'alfrocheiro', 'rabigato',
    # Grecia
    'assyrtiko', 'xinomavro', 'agiorgitiko', 'moschofilero', 'malagousia',
    'roditis', 'robola', 'mavrodaphne', 'athiri', 'vidiano', 'limnio',
    # Hungria
    'furmint', 'harslevelu', 'kadarka', 'juhfark',
    # Georgia
    'mtsvane', 'kisi', 'khikhvi', 'chinuri', 'tavkveri', 'aladasturi',
    # Romenia
    'feteasca', 'babeasca', 'tamaioasa',
    # Croacia/Eslovenia
    'plavac mali', 'posip', 'grasevina', 'malvazija', 'teran', 'rebula',
    # Bulgaria
    'mavrud', 'melnik', 'gamza', 'dimyat', 'pamid',
    # Turquia
    'okuzgozu', 'bogazkere', 'narince',
    # Japao
    'koshu',
    # Argentina
    'criolla',
    # Libano/Israel
    'obaideh', 'merwah', 'argaman', 'dabouki',
    # Outros
    'spanna', 'ugni blanc',
}

UVAS_ABREV = [
    'cab sauv', 'cab franc', 'sauv blanc', 'sav blanc',
    'pinot noir', 'pinot grigio', 'pinot gris',
    'gsm', 'tinta roriz', 'ull de llebre', 'antao vaz',
    'fernao pires', 'tinta negra', 'irsai oliver', 'plavac mali',
    'kalecik karasi', 'muscat bailey', 'ugni blanc', 'st laurent',
    'skin contact', 'vin santo', 'vendange tardive', 'methode traditionnelle',
    'cru classe', 'vino de pago',
    'blanc de blancs', 'blanc de noirs', 'vieilles vignes', 'old vines',
    'vin de france', 'cotes de provence', 'rias baixas',
    'gevrey chambertin', 'vosne romanee', 'chambolle musigny',
    'nuits saint georges', 'chassagne montrachet', 'puligny montrachet',
    'clos de vougeot', 'bonnes mares', 'savigny les beaune',
    'pernand vergelesses', 'crozes hermitage', 'cote rotie',
    'kindzmarauli',
]

TERMOS_VINHO = {
    'cuvee', 'barrique', 'vendemmia', 'vendange', 'millesime', 'annata',
    'cru', 'terroir', 'appellation', 'denominacion', 'denominazione',
    'chateau', 'domaine', 'bodega', 'cantina', 'weingut', 'tenuta', 'quinta',
    'vineyard', 'vignoble', 'vigneto',
    'barolo', 'barbaresco', 'chianti', 'brunello', 'amarone', 'ripasso',
    'bordeaux', 'burgundy', 'bourgogne', 'champagne', 'alsace', 'beaujolais',
    'rioja', 'ribera', 'priorat', 'rueda', 'rias',
    'douro', 'alentejo', 'dao', 'vinho', 'verde',
    'napa', 'sonoma', 'willamette', 'mendoza', 'maipo', 'colchagua',
    'marlborough', 'barossa', 'mclaren', 'yarra', 'hawkes',
    'trocken', 'spatlese', 'auslese', 'kabinett', 'smaragd',
    'brut', 'prosecco', 'franciacorta', 'cremant', 'cava', 'sekt',
    'port', 'porto', 'portwein', 'portwijn', 'portvin', 'oporto',
    'tawny', 'lbv', 'crusted', 'colheita', 'garrafeira', 'ruby',
    'sherry', 'madeira', 'marsala', 'sauternes',
    'amontillado', 'oloroso', 'manzanilla', 'palo cortado',
    'rotwein', 'weisswein', 'rosewein', 'winzer', 'weinberg',
    'halbtrocken', 'feinherb',
    'pradikatswein', 'qualitatswein', 'landwein', 'eiswein',
    'beerenauslese', 'trockenbeerenauslese',
    'federspiel', 'steinfeder',
    'rodvin', 'hvidvin', 'rosevin', 'hedvin',
    'wijn', 'wino',
    'spumant',
    'aszu', 'szamorodni',
    'frizzante', 'spumante', 'mousseux', 'perlwein',
    'metodo classico', 'pet nat',
    'passito', 'recioto', 'sforzato', 'vinsanto',
    'qvevri', 'amphora',
    'cru bourgeois',
    'rose', 'rosado', 'rosato', 'claret',
    'reserva', 'riserva', 'crianza', 'roble', 'joven', 'gran',
    'doc', 'docg', 'dop', 'aoc', 'aop', 'igt', 'igp', 'vdt',
    '1er', 'rosat',
    'likorwein', 'champagner',
    'espumoso', 'sparkling', 'fortified',
    'oinos',
    'valdeorras', 'morgon', 'salento',
    'meursault', 'pommard', 'volnay', 'corton', 'santenay',
    'rully', 'mercurey', 'givry', 'musigny', 'romanee',
    'condrieu', 'vacqueyras', 'gigondas', 'tavel', 'lirac',
    'cairanne', 'fitou',
    'tsinandali', 'mukuzani', 'khvanchkara',
}

GARANTIA_VINHO = {
    'vineyard', 'vineyards', 'winery', 'wineries',
    'vinicola', 'vigneron', 'vignerons', 'vignoble',
    'weingut', 'winzer', 'winzergenossenschaft',
    'bodega', 'bodegas',
    'cantina',
    'chateau',
    'domaine',
    'quinta',
    'tenuta', 'fattoria', 'podere',
    'herdade', 'adega',
    'kellerei',
    'clos',
    'castello', 'schloss',
}

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


# ═══════════════════════════════════════════════════════════
# CLASSIFICACAO
# ═══════════════════════════════════════════════════════════

def tokenize(text):
    if not text: return []
    return [w for w in re.split(r'[^a-zA-Z0-9àáâãäåèéêëìíîïòóôõöùúûüñç]+', text.lower()) if len(w) > 1]


def chars_uteis(nome):
    if not nome: return 0
    return len(re.sub(r'[^a-zA-Z]', '', nome))


def has_forbidden_word(nome):
    tokens = set(tokenize(nome))
    for w in tokens:
        if w in PALAVRAS_PROIBIDAS:
            return True
    nome_lower = nome.lower() if nome else ''
    for phrase in ['gift basket', 'hair spray', 'shin guard', 'corned tuna',
                   'olive oil', 'sesame oil', 'oat cakes', 'greeting card',
                   'wine cabinet', 'wine fridge', 'wine cooler', 'espresso martini',
                   'pure malt', 'single malt', 'ice drink', 't bone',
                   'creme de menthe', 'creme de cassis', 'creme de mure',
                   'creme de peche', 'creme de framboise', 'creme de violette',
                   'creme de cacao', 'creme de mandarine', 'creme de moka']:
        if phrase in nome_lower:
            return True
    return False


def has_nonwine_pattern(nome):
    if not nome: return False
    for p in PADROES_NAO_VINHO:
        if re.search(p, nome.lower()):
            return True
    return False


def is_spirit(nome):
    tokens = set(tokenize(nome))
    return bool(tokens & DESTILADOS)


def wine_likeness(wine, idx=None):
    score = 0
    tipo = wine.get('tipo', '') or ''
    safra = wine.get('safra')
    regiao = wine.get('regiao', '') or ''
    nome = wine.get('nome_normalizado', '') or ''
    produtor = wine.get('produtor_normalizado', '') or ''
    tokens = set(tokenize(nome))

    if tipo in TIPO_MAP:
        score += 1

    if safra and 1900 <= int(safra) <= 2026:
        score += 1

    if regiao and len(regiao) > 2:
        score += 1

    nome_lower = nome.lower()
    if tokens & UVAS:
        score += 1
    elif any(abbr in nome_lower for abbr in UVAS_ABREV):
        score += 1

    if tokens & TERMOS_VINHO:
        score += 1

    if tokens & GARANTIA_VINHO:
        score = max(score, 3)

    # Producer check via in-memory index (replaces DB query)
    if idx and produtor and produtor != 'None' and len(produtor) >= 3:
        words = [w for w in produtor.split() if len(w) >= 3]
        if words:
            anchor = max(words, key=len)
            if len(anchor) >= 4 and idx.has_producer(anchor):
                score += 2

    return score


def classify_prewine(wine, idx=None):
    nome = wine.get('nome_normalizado', '') or ''
    cu = chars_uteis(nome)
    if cu <= 2:
        return 'D', f'nome_curto({cu}chars)'
    if has_forbidden_word(nome):
        return 'D', 'palavra_proibida'
    if has_nonwine_pattern(nome):
        return 'D', 'padrao_peso'
    if is_spirit(nome):
        return 'E', 'destilado'
    wl = wine_likeness(wine, idx)
    if wl == 0:
        return 'D', 'wine_likeness=0'
    return 'OK', wl


# ═══════════════════════════════════════════════════════════
# MATCH
# ═══════════════════════════════════════════════════════════

def distinctive_tokens(tokens):
    return [t for t in tokens if t not in GENERIC_WORDS and not re.match(r'^\d{4}$', t) and len(t) >= 3]


def token_overlap(a, b):
    if not a or not b: return 0.0
    return len(set(a) & set(b)) / len(set(a))


def score_candidate(store, viv):
    st = tokenize(store['nome_normalizado'])
    vt = tokenize(f"{viv['produtor_normalizado'] or ''} {viv['nome_normalizado'] or ''}")
    sd, vd = distinctive_tokens(st), distinctive_tokens(vt)
    fwd = token_overlap(sd, vd) if sd and vd else token_overlap(st, vt)
    score = fwd * 0.35 + token_overlap(st, vt) * 0.10 + token_overlap(vt, st) * 0.10

    sp = tokenize(store.get('produtor_normalizado', ''))
    vp = tokenize(viv.get('produtor_normalizado', ''))
    sp_d, vp_d = distinctive_tokens(sp), distinctive_tokens(vp)
    producer_matched = False
    if sp_d and vp_d:
        ps = max(token_overlap(sp_d, vp_d), token_overlap(vp_d, sp_d))
        if ps > 0:
            score += ps * 0.25
            producer_matched = True
        else:
            score -= 0.10
    elif sp and vp:
        ps = token_overlap(sp, vp)
        score += ps * 0.15
        if ps > 0.5:
            producer_matched = True

    ss = str(store.get('safra', '') or '')
    vs = str(viv.get('safra', '') or '').strip()
    if ss and vs and ss == vs: score += 0.12
    elif ss and vs and ss != vs: score -= 0.02

    s_tipo = TIPO_MAP.get(store.get('tipo', '') or '', '')
    v_tipo = (viv.get('tipo', '') or '').lower()
    tipo_conflict = False
    if s_tipo and v_tipo:
        if s_tipo == v_tipo:
            score += 0.08
        elif {s_tipo, v_tipo} == {'tinto', 'branco'}:
            tipo_conflict = True
            score -= 0.15

    return max(0.0, min(1.0, score)), producer_matched, tipo_conflict


def make_viv(row):
    return {'id': row[0], 'nome_normalizado': row[1], 'produtor_normalizado': row[2],
            'safra': row[3], 'tipo': row[4], 'pais': row[5], 'regiao': row[6]}


# ═══════════════════════════════════════════════════════════
# IN-MEMORY INDEX (substitui queries DB)
# ═══════════════════════════════════════════════════════════

class VividIndex:
    """Indice invertido em memoria para vivino_match — matching sem DB"""

    def __init__(self):
        t0 = time.time()
        conn = psycopg2.connect(LOCAL_DB)
        cur = conn.cursor(name='load_vivino')
        cur.itersize = 50000
        cur.execute("SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais, regiao FROM vivino_match")

        self.wines = {}           # id -> dict
        self.prod_index = defaultdict(list)   # word -> [id, ...]
        self.name_index = defaultdict(list)   # word -> [id, ...]
        self.prod_set = set()     # all producer anchor words (for wine_likeness)

        count = 0
        while True:
            rows = cur.fetchmany(50000)
            if not rows:
                break
            for r in rows:
                vid = r[0]
                viv = {'id': vid, 'nome_normalizado': r[1], 'produtor_normalizado': r[2],
                       'safra': r[3], 'tipo': r[4], 'pais': r[5], 'regiao': r[6]}
                self.wines[vid] = viv

                # Index producer words
                prod = r[2] or ''
                for w in prod.lower().split():
                    if len(w) >= 3:
                        self.prod_index[w].append(vid)
                        if len(w) >= 4:
                            self.prod_set.add(w)

                # Index name words (tokens >= 4 chars for selectivity)
                nome = r[1] or ''
                for w in tokenize(nome):
                    if len(w) >= 4:
                        self.name_index[w].append(vid)

                count += 1

        cur.close()
        conn.close()
        elapsed = time.time() - t0
        print(f"  VividIndex loaded: {count:,} wines, "
              f"{len(self.prod_index):,} prod words, {len(self.name_index):,} name words "
              f"in {elapsed:.1f}s", flush=True)

    def has_producer(self, anchor):
        """Check if producer anchor word exists in vivino (for wine_likeness)"""
        return anchor.lower() in self.prod_set

    def search_producer(self, store):
        """Find candidates by producer word match"""
        p = store.get('produtor_normalizado', '') or ''
        if p == 'None' or len(p) < 3: return []
        words = [w for w in p.lower().split() if len(w) >= 3 and w not in GENERIC_WORDS]
        if not words: words = [w for w in p.lower().split() if len(w) >= 3]
        if not words: return []
        anchor = max(words, key=len)
        ids = self.prod_index.get(anchor, [])
        # Limit to 200 like the original
        return [self.wines[vid] for vid in ids[:200]]

    def search_keyword(self, store):
        """Find candidates by distinctive name keyword"""
        tokens = tokenize(store['nome_normalizado'])
        dist = [t for t in tokens if len(t) >= 5 and t not in GENERIC_WORDS and not re.match(r'^\d{4}$', t)]
        if not dist: return []
        longest = max(dist, key=len)
        # Search in both name and producer indexes
        ids = set()
        for vid in self.name_index.get(longest, []):
            ids.add(vid)
            if len(ids) >= 150: break
        for vid in self.prod_index.get(longest, []):
            ids.add(vid)
            if len(ids) >= 200: break
        return [self.wines[vid] for vid in ids]

    def search_multi_keyword(self, store):
        """Fallback: find candidates by multiple distinctive tokens (replaces trgm)"""
        tokens = tokenize(store['nome_normalizado'])
        dist = [t for t in tokens if len(t) >= 4 and t not in GENERIC_WORDS and not re.match(r'^\d{4}$', t)]
        if len(dist) < 2: return []
        # Find candidates that match at least 2 distinctive tokens
        candidate_counts = Counter()
        for token in dist[:6]:  # limit tokens to check
            for vid in self.name_index.get(token, [])[:500]:
                candidate_counts[vid] += 1
            for vid in self.prod_index.get(token, [])[:500]:
                candidate_counts[vid] += 1
        # Return candidates with 2+ token matches
        return [self.wines[vid] for vid, cnt in candidate_counts.most_common(30) if cnt >= 2]


def find_best_match(idx, store):
    """Find best vivino match using in-memory index"""
    cands = {}
    for c in idx.search_producer(store): cands[c['id']] = (c, 'prod')
    for c in idx.search_keyword(store):
        if c['id'] not in cands: cands[c['id']] = (c, 'kw')

    best, bs, bst, bpm, btc = None, 0, 'none', False, False
    for cid, (c, st) in cands.items():
        s, pm, tc = score_candidate(store, c)
        if s > bs: bs, best, bst, bpm, btc = s, c, st, pm, tc

    if bs >= 0.40 and bpm:
        return best, bs, bst, bpm, btc

    # Multi-keyword fallback (replaces trgm)
    for c in idx.search_multi_keyword(store):
        if c['id'] not in cands:
            s, pm, tc = score_candidate(store, c)
            if s > bs: bs, best, bst, bpm, btc = s, c, 'mkw', pm, tc

    return best, bs, bst, bpm, btc


def nome_overlap_score(store, viv):
    loja_tokens = set(tokenize(store.get('nome_normalizado', '')))
    viv_nome = viv.get('nome_normalizado', '') if viv else ''
    viv_tokens = set(tokenize(viv_nome))
    if not viv_tokens:
        return 0.0
    return len(loja_tokens & viv_tokens) / len(viv_tokens)


def tipo_bate(store, viv):
    s_tipo = TIPO_MAP.get(store.get('tipo', '') or '', '')
    v_tipo = (viv.get('tipo', '') or '').lower() if viv else ''
    return s_tipo != '' and v_tipo != '' and s_tipo == v_tipo


def safra_bate(store, viv):
    ss = str(store.get('safra', '') or '').strip()
    vs = str(viv.get('safra', '') or '').strip()
    return ss != '' and vs != '' and ss == vs


def produtor_parcial(store, viv):
    loja_tokens = set(w for w in tokenize(store.get('nome_normalizado', '')) if len(w) >= 4)
    viv_prod_tokens = set(tokenize(viv.get('produtor_normalizado', '') if viv else ''))
    return bool(loja_tokens & viv_prod_tokens)


def classify_match(score, producer_matched, tipo_conflict, wl, nome_chars=99, store=None, viv=None):
    if tipo_conflict:
        if wl >= 3:
            return 'B'
        if nome_chars <= 4:
            return 'D'
        return 'C2'

    if score >= 0.45 and producer_matched:
        return 'A'
    if score >= 0.70 and not producer_matched:
        return 'A'

    if score >= 0.30 and store and viv:
        n_overlap = nome_overlap_score(store, viv)
        has_tipo = tipo_bate(store, viv)
        has_safra = safra_bate(store, viv)
        has_prod = produtor_parcial(store, viv)
        if n_overlap >= 0.50 and (has_tipo or has_safra or has_prod):
            return 'A'

    if score >= 0.30:
        if wl >= 3:
            return 'B'
        if nome_chars <= 4:
            return 'D'
        return 'C2'

    if wl >= 3:
        return 'B'
    if nome_chars <= 4:
        return 'D'
    return 'C2'


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: python match_vivino.py GROUP_NUM (1-8)")
        sys.exit(1)

    group_num = int(sys.argv[1])
    if group_num not in GROUPS:
        print(f"ERROR: GROUP_NUM must be 1-8, got {group_num}")
        sys.exit(1)

    countries = GROUPS[group_num]
    table_name = f"match_results_y{group_num}"
    FETCH_SIZE = 10000

    print(f"[G{group_num}] Starting — countries: {countries}", flush=True)

    conn = psycopg2.connect(LOCAL_DB)
    conn.autocommit = True
    cur = conn.cursor()

    # Load vivino_match into memory (shared across all processing)
    print(f"[G{group_num}] Loading vivino_match into memory...", flush=True)
    idx = VividIndex()

    # Create output table
    cur.execute(f"DROP TABLE IF EXISTS {table_name}")
    cur.execute(f"""
        CREATE TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            clean_id INTEGER NOT NULL,
            vivino_id INTEGER,
            match_score REAL,
            match_strategy VARCHAR(20),
            destino VARCHAR(5),
            wine_likeness INTEGER,
            loja_nome TEXT,
            vivino_nome TEXT
        )
    """)

    # Count total wines first
    placeholders = ','.join(['%s'] * len(countries))
    cur.execute(f"SELECT count(*) FROM wines_clean WHERE pais_tabela IN ({placeholders})", countries)
    total = cur.fetchone()[0]
    print(f"[G{group_num}] Total wines: {total:,}", flush=True)

    # Use server-side cursor to stream rows
    conn2 = psycopg2.connect(LOCAL_DB)
    srv_cur = conn2.cursor(name=f'fetch_g{group_num}')
    srv_cur.itersize = FETCH_SIZE
    srv_cur.execute(f"""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais_tabela, regiao
        FROM wines_clean
        WHERE pais_tabela IN ({placeholders})
        ORDER BY id
    """, countries)

    stats = Counter()
    batch = []
    t0 = time.time()
    errors = 0
    i = 0

    while True:
        rows = srv_cur.fetchmany(FETCH_SIZE)
        if not rows:
            break

        for row in rows:
            w = {
                'id': row[0], 'nome_normalizado': row[1], 'produtor_normalizado': row[2],
                'safra': row[3], 'tipo': row[4], 'pais_tabela': row[5], 'regiao': row[6]
            }
            nome = w['nome_normalizado'] or ''

            try:
                # ETAPA 1: Pre-classificacao (in-memory)
                pre_class, pre_detail = classify_prewine(w, idx)

                if pre_class in ('D', 'E'):
                    dest = pre_class
                    wl = 0
                    vivino_id = None
                    match_score = None
                    match_strategy = None
                    vivino_nome = None
                else:
                    wl = pre_detail

                    # ETAPA 2: Match (in-memory)
                    best, score, strat, prod_match, tipo_conf = find_best_match(idx, w)
                    cu = chars_uteis(nome)

                    if best and score >= 0.30:
                        dest = classify_match(score, prod_match, tipo_conf, wl, cu, store=w, viv=best)
                    elif wl >= 3:
                        dest = 'B'
                    elif cu <= 4:
                        dest = 'D'
                    else:
                        dest = 'C2'

                    if best and score >= 0.30 and dest == 'A':
                        vivino_id = best['id']
                        match_score = round(score, 4)
                        match_strategy = strat
                        vivino_nome = f"{best['produtor_normalizado'] or '?'} — {best['nome_normalizado'] or '?'}"
                    else:
                        vivino_id = None
                        match_score = round(score, 4) if best else None
                        match_strategy = strat if best else None
                        vivino_nome = None

                stats[dest] += 1
                batch.append((w['id'], vivino_id, match_score, match_strategy, dest, wl, nome[:500], vivino_nome[:500] if vivino_nome else None))

            except Exception as e:
                errors += 1
                stats['D'] += 1
                batch.append((w['id'], None, None, None, 'D', 0, nome[:500], None))
                if errors <= 10:
                    print(f"[G{group_num}] ERROR on id={w['id']}: {e}", flush=True)

            # Batch insert
            if len(batch) >= BATCH_SIZE:
                cur.executemany(f"""
                    INSERT INTO {table_name} (clean_id, vivino_id, match_score, match_strategy, destino, wine_likeness, loja_nome, vivino_nome)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, batch)
                batch = []

            i += 1
            # Progress
            if i % PROGRESS_EVERY == 0:
                elapsed = time.time() - t0
                rate = i / elapsed
                eta_s = (total - i) / rate if rate > 0 else 0
                eta_h = eta_s / 3600
                print(f"[G{group_num}] {i:>8,}/{total:,} ({i/total*100:.1f}%) — "
                      f"A={stats['A']:,} B={stats['B']:,} C2={stats['C2']:,} D={stats['D']:,} E={stats['E']:,} — "
                      f"{rate:.0f}/s — ETA {eta_h:.1f}h — errors={errors}",
                      flush=True)

    # Final batch
    if batch:
        cur.executemany(f"""
            INSERT INTO {table_name} (clean_id, vivino_id, match_score, match_strategy, destino, wine_likeness, loja_nome, vivino_nome)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, batch)

    srv_cur.close()
    conn2.close()

    # Index
    cur.execute(f"CREATE INDEX idx_{table_name}_clean ON {table_name} (clean_id)")
    cur.execute(f"CREATE INDEX idx_{table_name}_dest ON {table_name} (destino)")

    elapsed = time.time() - t0

    print(f"\n[G{group_num}] DONE — {total:,} wines in {elapsed:.0f}s ({elapsed/3600:.1f}h)", flush=True)
    print(f"[G{group_num}]   A  = {stats['A']:>8,}  ({stats['A']/total*100:.1f}%)", flush=True)
    print(f"[G{group_num}]   B  = {stats['B']:>8,}  ({stats['B']/total*100:.1f}%)", flush=True)
    print(f"[G{group_num}]   C2 = {stats['C2']:>8,}  ({stats['C2']/total*100:.1f}%)", flush=True)
    print(f"[G{group_num}]   D  = {stats['D']:>8,}  ({stats['D']/total*100:.1f}%)", flush=True)
    print(f"[G{group_num}]   E  = {stats['E']:>8,}  ({stats['E']/total*100:.1f}%)", flush=True)
    print(f"[G{group_num}]   Errors = {errors}", flush=True)

    conn.close()


if __name__ == '__main__':
    main()
