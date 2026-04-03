"""
Analise de 250 vinhos por letra — classificacao em A/B/C2/D/E (C1 eliminado na v5)
Usage: python analise_letra.py LETRA
Output: C:\winegod-app\scripts\analise_letra_X.txt
"""
import psycopg2
import sys
import io
import re
import time
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LOCAL_DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
SAMPLE_SIZE = 250

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
    # NAO incluido: 'ale' (ginger ale, wafer ale = falso positivo)
    # NAO incluido: 'bier' (bierzo = regiao vinicola espanhola)
    # NAO incluido: 'highland' (santa lucia highlands = vinho)
    # Regioes de whisky
    'lowland', 'islay', 'campbeltown',
    # Tabaco/acessorios/aperitivos
    'tabaco', 'riedel', 'carafe', 'caraffe', 'aperitivo',
    # Cerveja
    'pabst',
    # Textil/cama
    'sabana', 'hilos',
    # Comida/massa
    'fabada', 'penne', 'paccheri', 'fettuccine',
    # Xarope
    'szirup', 'sirop', 'topping',
    # Papelaria/eletronico
    'ballpen', 'samsung',
    # Higiene
    'rollon',
    # NAO incluido: 'fumo' — "bulfon fumo rosso" e vinho italiano real
    # NAO incluido: 'snaps' — "ginger snaps" = biscoito
    # NAO incluido: 'spritz' — vinhos naturais usam "spritz"
    # NAO incluido: 'vermouth' — base de vinho
    # NAO incluido: 'keg' — "drikkeglas" (copo DK) falso positivo
    # NAO incluido: 'distillery' — pode pegar wine distillery
    # sirop validado — 918 registros, 0 vinhos reais (xaropes com tipo errado no banco)
    'verjus',       # mosto nao fermentado (191 registros, 0 vinhos)
    'refill',       # recarga de caneta (1.2K, 0 vinhos)
    'steak',        # carne (1.2K, 0 vinhos)
    'lakrids',      # bala de alcacuz DK (1.5K, 0 vinhos)
    'speyside',     # regiao de whisky (903, 0 vinhos)
    # NAO incluido: 'mosto' (mostoflor.com.br = loja de vinho, URL no nome)
    # NAO incluido: 'porter' (piesporter = vinho alemao real, porterbass = vinicola)
    # NAO incluido: 'must'/'most' (muito curtos, substring em tudo)
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
    r'\b\d+\s*g\b',           # "500g", "130 g"
    r'\b\d+\s*kg\b',          # "1kg"
    r'\b\d+\s*oz\b',          # "16oz"
    r'\b\d+\s*pcs\b',         # "2pcs"
    r'\b\d+\s*stk\b',         # "3 stk" (Scandinavian "pieces")
    r'\b\d+\s*tem\b',         # "12tem" (Greek "pieces")
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
    'tequila', 'mezcal', 'mezcal',
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
    # Internacionais (ja existiam)
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
    # Sinonimos internacionais (validados contra base)
    'spatburgunder',    # Pinot Noir DE (3.8K loja + 15.7K vivino)
    'blauburgunder',    # Pinot Noir AT (339 + 929)
    'grauburgunder',    # Pinot Grigio DE (1.6K + 4.7K)
    'weissburgunder',   # Pinot Blanc DE (1.6K + 7.3K)
    'cannonau',         # Grenache Sardegna (1.1K + 841)
    'aragonez',         # Tempranillo PT (103 + 161)
    'cencibel',         # Tempranillo ES (27 + 101)
    'mataro',           # Mourvedre AU (765 + 556)
    'nielluccio',       # Sangiovese Corsica (15 + 19)
    'morellino',        # Sangiovese Toscana (689 + 676)
    'prugnolo',         # Sangiovese Montepulciano (48 + 13)
    'kekfrankos',       # Blaufrankisch HU (635 + 1.1K)
    'lemberger',        # Blaufrankisch DE (326 + 2.2K)
    'frankovka',        # Blaufrankisch CZ/SK (224 + 1.5K)
    'mazuelo',          # Carignan ES (90 + 59)
    'samso',            # Carignan Catalunya (140 + 196)
    'traminer',         # Gewurztraminer (7.5K + 15K)
    'tribidrag',        # Zinfandel/Primitivo HR (23 + 12)
    'chiavennasca',     # Nebbiolo Lombardia (4 + 9)
    # Alemanha/Austria
    'dornfelder',       # (508 + 7K)
    'silvaner',         # (1K + 5.3K)
    'kerner',           # (546 + 3.5K)
    'scheurebe',        # (494 + 3.4K)
    'trollinger',       # (207 + 1.6K)
    'rotgipfler',       # (155 + 271)
    'zierfandler',      # (57 + 132)
    'neuburger',        # (151 + 429)
    'welschriesling',   # (554 + 1.8K)
    'olaszrizling',     # (460 + 765)
    # Portugal
    'castelao',         # (338 + 211)
    'trincadeira',      # (180 + 152)
    'encruzado',        # (730 + 221)
    'arinto',           # (1K + 593)
    'loureiro',         # (992 + 453)
    'verdelho',         # (976 + 1.2K)
    'boal',             # (393 + 170) — seguro, quase tudo Madeira
    'sercial',          # (380 + 109)
    'viosinho',         # (132 + 67)
    'gouveio',          # (122 + 56)
    'sousao',           # (149 + 48)
    'alfrocheiro',      # (225 + 114)
    'rabigato',         # (116 + 46)
    # Grecia
    'assyrtiko',        # (1.2K + 492)
    'xinomavro',        # (575 + 223)
    'agiorgitiko',      # (387 + 368)
    'moschofilero',     # (244 + 230)
    'malagousia',       # (245 + 128)
    'roditis',          # (203 + 148)
    'robola',           # (68 + 49)
    'mavrodaphne',      # (87 + 53)
    'athiri',           # (62 + 66)
    'vidiano',          # (232 + 117)
    'limnio',           # (161 + 71)
    # Hungria
    'furmint',          # (1.6K + 1.3K)
    'harslevelu',       # (376 + 518)
    'kadarka',          # (304 + 412)
    'juhfark',          # (118 + 111)
    # Georgia
    'mtsvane',          # (442 + 706)
    'kisi',             # (586 + 532) — cuidado mas maioria e vinho georgiano
    'khikhvi',          # (140 + 232)
    'chinuri',          # (112 + 152)
    'tavkveri',         # (77 + 170)
    'aladasturi',       # (44 + 70)
    # Romenia
    'feteasca',         # (1.9K + 1.6K)
    'babeasca',         # (80 + 41)
    'tamaioasa',        # (206 + 200)
    # Croacia/Eslovenia
    'plavac mali',      # (227 + 325) — multi-palavra mas seguro
    'posip',            # (221 + 238)
    'grasevina',        # (250 + 331)
    'malvazija',        # (522 + 618)
    'teran',            # (407 + 390) — cuidado com "veterano"
    'rebula',           # (300 + 231)
    # Bulgaria
    'mavrud',           # (183 + 316)
    'melnik',           # (139 + 227)
    'gamza',            # (61 + 88)
    'dimyat',           # (39 + 53)
    'pamid',            # (16 + 71)
    # Turquia
    'okuzgozu',         # (123 + 274)
    'bogazkere',        # (81 + 155)
    'narince',          # (61 + 113)
    # Japao
    'koshu',            # (245 + 538)
    # Argentina
    'criolla',          # (775 + 210)
    # Libano/Israel
    'obaideh',          # (3 + 1)
    'merwah',           # (44 + 9)
    'argaman',          # (45 + 19)
    'dabouki',          # (18 + 9)
    # Sinonimos PT
    'spanna',           # Nebbiolo (447 + 187)
    # Outros
    'ugni blanc',       # Trebbiano FR (123 + 184) — multi-palavra mas seguro
}

# Abreviacoes multi-palavra de uva (checadas separadamente)
UVAS_ABREV = [
    'cab sauv',         # cabernet sauvignon (1.3K)
    'cab franc',        # cabernet franc (476)
    'sauv blanc',       # sauvignon blanc (813)
    'sav blanc',        # sauvignon blanc (46)
    'pinot noir',       # ja coberto por tokens individuais
    'pinot grigio',
    'pinot gris',
    'gsm',              # grenache shiraz mourvedre (1.3K)
    'tinta roriz',      # Tempranillo PT (257 + 155)
    'ull de llebre',    # Tempranillo Catalunya (38 + 96)
    'antao vaz',        # Portugal (112 + 101)
    'fernao pires',     # Portugal (154 + 133)
    'tinta negra',      # Madeira (136 + 45)
    'irsai oliver',     # Hungria (255 + 540)
    'plavac mali',      # Croacia (227 + 325)
    'kalecik karasi',   # Turquia (37 + 137)
    'muscat bailey',    # Japao (44 + 331)
    'ugni blanc',       # Trebbiano FR (123 + 184)
    'st laurent',       # Austria (524 + 1.4K)
    'skin contact',     # Orange wine (784 + 286)
    'vin santo',        # Toscana (956 + 885)
    'vendange tardive', # Late harvest FR (81 + 295)
    'methode traditionnelle', # Espumante (404 + 624)
    'cru classe',       # Bordeaux (10.3K + 347)
    'vino de pago',     # Espanha (95 + 5)
    # Multi-palavra fortissimos (validados — 100% vinho)
    'blanc de blancs',  # 19K + 8.4K
    'blanc de noirs',   # 5.5K + 2.7K
    'vieilles vignes',  # 13K + 9.2K
    'old vines',        # 1.9K + 1.1K
    'vin de france',    # 6K + 131
    'cotes de provence', # 4K + 3.7K
    'rias baixas',      # 1.7K + 151
    # Borgonha vilas (todas validadas — 100% vinho)
    'gevrey chambertin',    # 4.3K + 173
    'vosne romanee',        # 3.2K + 101
    'chambolle musigny',    # 3K + 77
    'nuits saint georges',  # 2K + 114
    'chassagne montrachet', # 3.2K + 123
    'puligny montrachet',   # 2.9K + 87
    'clos de vougeot',      # 2.9K + 282
    'bonnes mares',         # 1.7K + 75
    'savigny les beaune',   # 1.2K + 113
    'pernand vergelesses',  # 638 + 62
    'crozes hermitage',     # 1.4K + 102
    # Rhone vilas (validadas)
    'cote rotie',       # 3.6K + 80
    # Georgia denominacoes (validadas)
    'kindzmarauli',     # 316 + 607 — multi-palavra no UVAS_ABREV, mas seguro aqui tb
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
    # Sherry estilos
    'amontillado', 'oloroso', 'manzanilla', 'palo cortado',
    # Alemao (validados — excluido 'wein' por falso positivo)
    'rotwein', 'weisswein', 'rosewein', 'winzer', 'weinberg',
    'spatlese', 'auslese', 'kabinett', 'halbtrocken', 'feinherb',
    'pradikatswein', 'qualitatswein', 'landwein', 'eiswein',
    'beerenauslese', 'trockenbeerenauslese',
    # Austria
    'smaragd', 'federspiel', 'steinfeder',
    # Escandinavo
    'rodvin', 'hvidvin', 'rosevin', 'hedvin',
    # Holandes/Polones
    'wijn', 'wino',
    # Romeno
    'spumant',
    # Hungaro
    'aszu', 'szamorodni',
    # Espumantes
    'frizzante', 'spumante', 'mousseux', 'perlwein',
    'metodo classico', 'pet nat',
    # Late harvest / Passito
    'passito', 'recioto', 'sforzato', 'vinsanto',
    # Natural / Orange
    'qvevri', 'amphora',
    # Classificacoes
    'cru bourgeois',
    'rose', 'rosado', 'rosato', 'claret',
    'reserva', 'riserva', 'crianza', 'roble', 'joven', 'gran',
    'doc', 'docg', 'dop', 'aoc', 'aop', 'igt', 'igp', 'vdt',
    '1er',              # Premier Cru abreviado (49K loja, 15K vivino, 0 falsos)
    'rosat',            # Rose em catalao (501 + 9.2K, 0 falsos)
    # Novos (validados por 3 IAs — Gemini, Kimi, ChatGPT)
    'likorwein', 'champagner',      # alemao
    'espumoso', 'sparkling', 'fortified',  # espanhol/ingles
    'oinos',                        # grego
    'valdeorras', 'morgon', 'salento',     # regioes
    # Borgonha vilas (validadas — 1K-14K cada, 100% vinho)
    'meursault', 'pommard', 'volnay', 'corton', 'santenay',
    'rully', 'mercurey', 'givry', 'musigny', 'romanee',
    # Rhone (validadas)
    'condrieu', 'vacqueyras', 'gigondas', 'tavel', 'lirac',
    'cairanne', 'fitou',
    # Georgia denominacoes (validadas)
    'tsinandali', 'mukuzani', 'khvanchkara',
}

# Palavras que GARANTEM vinho (forca wl=3 minimo)
# Testadas: <0.1% falso positivo na base de lojas de vinho
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
    # NAO incluido: 'mas' (42% falso positivo — palavra comum em ES/PT)
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


def has_forbidden_word(nome):
    """Checa se o nome contem palavras proibidas"""
    tokens = set(tokenize(nome))
    # Check single words
    for w in tokens:
        if w in PALAVRAS_PROIBIDAS:
            return True
    # Check bigrams
    nome_lower = nome.lower() if nome else ''
    for phrase in ['gift basket', 'hair spray', 'shin guard', 'corned tuna',
                   'olive oil', 'sesame oil', 'oat cakes', 'greeting card',
                   'wine cabinet', 'wine fridge', 'wine cooler', 'espresso martini',
                   'pure malt', 'single malt', 'ice drink', 't bone',
                   'presente gourmet', 'pata negra',
                   'creme de menthe', 'creme de cassis', 'creme de mure',
                   'creme de peche', 'creme de framboise', 'creme de violette',
                   'creme de cacao', 'creme de mandarine', 'creme de moka']:
        if phrase in nome_lower:
            return True
    return False


def has_nonwine_pattern(nome):
    """Checa padroes de peso/quantidade"""
    if not nome: return False
    for p in PADROES_NAO_VINHO:
        if re.search(p, nome.lower()):
            return True
    return False


def is_spirit(nome):
    """Checa se e destilado"""
    tokens = set(tokenize(nome))
    return bool(tokens & DESTILADOS)


def wine_likeness(wine, cur=None):
    """Score 0-6: quao provavel e vinho"""
    score = 0
    tipo = wine.get('tipo', '') or ''
    safra = wine.get('safra')
    regiao = wine.get('regiao', '') or ''
    nome = wine.get('nome_normalizado', '') or ''
    produtor = wine.get('produtor_normalizado', '') or ''
    tokens = set(tokenize(nome))

    # +1 tipo reconhecido
    if tipo in TIPO_MAP or tipo in ('NaN', 'Sake', 'Wine', 'Hidden product'):
        if tipo in TIPO_MAP:
            score += 1

    # +1 safra valida
    if safra and 1900 <= int(safra) <= 2026:
        score += 1

    # +1 regiao preenchida
    if regiao and len(regiao) > 2:
        score += 1

    # +1 nome contem uva (palavra individual ou abreviacao multi-palavra)
    nome_lower = nome.lower()
    if tokens & UVAS:
        score += 1
    elif any(abbr in nome_lower for abbr in UVAS_ABREV):
        score += 1

    # +1 nome contem termo de vinho
    if tokens & TERMOS_VINHO:
        score += 1

    # GARANTIA: palavra que confirma vinho (forca minimo 3)
    if tokens & GARANTIA_VINHO:
        score = max(score, 3)

    # +2 produtor existe no Vivino (forte indicador de vinho real)
    if cur and produtor and produtor != 'None' and len(produtor) >= 3:
        # Pega a palavra mais longa do produtor como ancora
        words = [w for w in produtor.split() if len(w) >= 3]
        if words:
            anchor = max(words, key=len)
            if len(anchor) >= 4:
                cur.execute(
                    "SELECT 1 FROM vivino_match WHERE produtor_normalizado ILIKE %s LIMIT 1",
                    (f'%{anchor}%',)
                )
                if cur.fetchone():
                    score += 2

    return score


def chars_uteis(nome):
    """Conta caracteres alfabeticos (sem numeros, espacos, pontuacao)"""
    if not nome:
        return 0
    return len(re.sub(r'[^a-zA-Z]', '', nome))


def classify_prewine(wine, cur=None):
    """
    Classifica ANTES do match.
    Returns: ('D', razao) ou ('E', razao) ou ('OK', wine_likeness_score)
    """
    nome = wine.get('nome_normalizado', '') or ''

    # Nome com 0-2 caracteres uteis → eliminar direto
    # (14.5K registros na base, 99%+ sao codigos/lixo, so 22 vinhos reais no Vivino inteiro)
    cu = chars_uteis(nome)
    if cu <= 2:
        return 'D', f'nome_curto({cu}chars)'

    # Palavra proibida
    if has_forbidden_word(nome):
        return 'D', 'palavra_proibida'

    # Padrao de nao-vinho (peso, pack)
    if has_nonwine_pattern(nome):
        return 'D', 'padrao_peso'

    # Destilado
    if is_spirit(nome):
        return 'E', 'destilado'

    # Wine-likeness (agora checa produtor no Vivino)
    wl = wine_likeness(wine, cur)
    if wl == 0:
        return 'D', f'wine_likeness=0'

    return 'OK', wl


# ═══════════════════════════════════════════════════════════
# MATCH (reutilizado do test_match_y_v3)
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


def find_best_match(cur, store):
    """Returns (best_viv, score, strategy, producer_matched, tipo_conflict)"""
    cands = {}
    for c in search_producer(cur, store): cands[c['id']] = (c, 'prod')
    for c in search_keyword(cur, store):
        if c['id'] not in cands: cands[c['id']] = (c, 'kw')

    best, bs, bst, bpm, btc = None, 0, 'none', False, False
    for cid, (c, st) in cands.items():
        s, pm, tc = score_candidate(store, c)
        if s > bs: bs, best, bst, bpm, btc = s, c, st, pm, tc

    if bs >= 0.40 and bpm:  # producer matched, lower threshold
        return best, bs, bst, bpm, btc
    if bs >= 0.40 and not bpm:
        # Try trgm for better candidate
        pass

    # trgm fallback
    for c in search_trgm_nome(cur, store):
        s, pm, tc = score_candidate(store, c)
        if s > bs: bs, best, bst, bpm, btc = s, c, 'trgm', pm, tc

    if bs >= 0.40:
        return best, bs, bst, bpm, btc

    for c in search_trgm_combined(cur, store):
        s, pm, tc = score_candidate(store, c)
        if s > bs: bs, best, bst, bpm, btc = s, c, 'trgm2', pm, tc

    return best, bs, bst, bpm, btc


def nome_overlap_score(store, viv):
    """Calcula overlap do nome do vinho (sem produtor) entre loja e Vivino"""
    loja_tokens = set(tokenize(store.get('nome_normalizado', '')))
    viv_nome = viv.get('nome_normalizado', '') if viv else ''
    viv_tokens = set(tokenize(viv_nome))
    if not viv_tokens:
        return 0.0
    return len(loja_tokens & viv_tokens) / len(viv_tokens)


def tipo_bate(store, viv):
    """Verifica se tipo da loja bate com tipo do Vivino"""
    s_tipo = TIPO_MAP.get(store.get('tipo', '') or '', '')
    v_tipo = (viv.get('tipo', '') or '').lower() if viv else ''
    return s_tipo != '' and v_tipo != '' and s_tipo == v_tipo


def safra_bate(store, viv):
    """Verifica se safra da loja bate com safra do Vivino"""
    ss = str(store.get('safra', '') or '').strip()
    vs = str(viv.get('safra', '') or '').strip()
    return ss != '' and vs != '' and ss == vs


def produtor_parcial(store, viv):
    """Verifica se pelo menos 1 palavra do produtor bate"""
    loja_tokens = set(w for w in tokenize(store.get('nome_normalizado', '')) if len(w) >= 4)
    viv_prod_tokens = set(tokenize(viv.get('produtor_normalizado', '') if viv else ''))
    return bool(loja_tokens & viv_prod_tokens)


def classify_match(score, producer_matched, tipo_conflict, wl, nome_chars=99, store=None, viv=None):
    """
    Classifica DEPOIS do match.
    Returns: 'A', 'B', 'C2', 'D'

    C1 eliminado — agora resolve com regra do nome overlap:
    Se nome >= 50% + (tipo OU safra OU produtor parcial) → A
    Senao → B (vinho novo, sem vivino_id)
    """
    # Tipo contradiz (tinto↔branco) = invalida match
    if tipo_conflict:
        if wl >= 3:
            return 'B'  # e vinho mas match errado → vinho novo
        if nome_chars <= 4:
            return 'D'
        return 'C2'

    # Com match — regras originais
    if score >= 0.45 and producer_matched:
        return 'A'
    if score >= 0.70 and not producer_matched:
        return 'A'

    # REGRA NOVA: match duvidoso mas nome confirma
    # Se nome bate >= 50% E pelo menos 1 sinal extra (tipo, safra ou produtor parcial)
    # → promove pra A (match confirmado por evidencia cruzada)
    # Validado: 80% dos C1 promovidos corretamente (324 de 403)
    if score >= 0.30 and store and viv:
        n_overlap = nome_overlap_score(store, viv)
        has_tipo = tipo_bate(store, viv)
        has_safra = safra_bate(store, viv)
        has_prod = produtor_parcial(store, viv)

        if n_overlap >= 0.50 and (has_tipo or has_safra or has_prod):
            return 'A'  # match confirmado por evidencia cruzada

    # Match duvidoso sem confirmacao
    if score >= 0.30:
        if wl >= 3:
            return 'B'  # e vinho, match nao confiavel → vinho novo
        if nome_chars <= 4:
            return 'D'
        return 'C2'

    # Sem match
    if wl >= 3:
        return 'B'  # vinho novo
    if nome_chars <= 4:
        return 'D'
    return 'C2'


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: python analise_letra.py LETRA")
        sys.exit(1)

    letra = sys.argv[1].upper()
    letra_lower = letra.lower()

    conn = psycopg2.connect(LOCAL_DB)
    cur = conn.cursor()
    cur.execute("SET pg_trgm.similarity_threshold = 0.15")

    # Pegar 250 vinhos que comecam com essa letra, ordem alfabetica
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais_tabela, regiao
        FROM wines_unique
        WHERE nome_normalizado LIKE %s
        ORDER BY nome_normalizado
        LIMIT %s
    """, (f'{letra_lower}%', SAMPLE_SIZE))

    wines = [{'id': r[0], 'nome_normalizado': r[1], 'produtor_normalizado': r[2],
              'safra': r[3], 'tipo': r[4], 'pais_tabela': r[5], 'regiao': r[6]} for r in cur.fetchall()]

    if not wines:
        print(f"Nenhum vinho encontrado comecando com '{letra}'")
        sys.exit(1)

    output_path = f'C:\\winegod-app\\scripts\\analise_letra_{letra}.txt'
    out = open(output_path, 'w', encoding='utf-8')

    stats = Counter()
    t0 = time.time()

    def p(text=''):
        out.write(text + '\n')

    p(f"ANALISE LETRA {letra} — {len(wines)} vinhos (ordem alfabetica)")
    p(f"{'='*100}")
    p(f"{'#':>3}  DEST  SCORE  PROD?  NOME LOJA → VIVINO")
    p(f"{'-'*100}")

    for i, w in enumerate(wines):
        nome = w['nome_normalizado'] or '(vazio)'
        tipo = w['tipo'] or ''
        safra = w['safra'] or ''
        pais = w['pais_tabela'] or ''

        # ETAPA 1: Pre-classificacao
        pre_class, pre_detail = classify_prewine(w, cur)

        if pre_class == 'D':
            stats['D'] += 1
            p(f"{i+1:3d}  [D ]  ----  ----  \"{nome}\" [{tipo}][{pais}][{safra}]")
            p(f"              → ELIMINADO ({pre_detail})")
            p()
            continue

        if pre_class == 'E':
            stats['E'] += 1
            p(f"{i+1:3d}  [E ]  ----  ----  \"{nome}\" [{tipo}][{pais}][{safra}]")
            p(f"              → DESTILADO ({pre_detail})")
            p()
            continue

        wl = pre_detail  # wine_likeness score

        # ETAPA 2: Match
        best, score, strat, prod_match, tipo_conf = find_best_match(cur, w)
        cu = chars_uteis(nome)

        if best and score >= 0.30:
            dest = classify_match(score, prod_match, tipo_conf, wl, cu, store=w, viv=best)
        elif wl >= 3:
            dest = 'B'
        elif cu <= 4:
            dest = 'D'  # nome curto + sem match + wl baixo = lixo
        else:
            dest = 'C2'

        stats[dest] += 1
        prod_flag = 'SIM' if prod_match else 'nao'

        dest_label = {'A': 'A ', 'B': 'B ', 'C2': 'C2', 'D': 'D '}[dest]

        if best and score >= 0.30:
            viv_nome = f"{best['produtor_normalizado'] or '?'} — {best['nome_normalizado'] or '?'}"
            viv_tipo = best['tipo'] or ''
            viv_safra = best['safra'] or ''
            viv_pais = best['pais'] or ''
            p(f"{i+1:3d}  [{dest_label}]  {score:.2f}  {prod_flag:>4}  \"{nome}\" [{tipo}][{pais}][{safra}]")
            p(f"              → \"{viv_nome}\" [{viv_tipo}][{viv_pais}][{viv_safra}]  wl={wl}")
        else:
            p(f"{i+1:3d}  [{dest_label}]  {score:.2f}  ----  \"{nome}\" [{tipo}][{pais}][{safra}]")
            p(f"              → (sem match) wl={wl}")
        p()

        if (i+1) % 50 == 0:
            print(f"  [{letra}] {i+1}/{len(wines)} — A={stats['A']} B={stats['B']} C2={stats['C2']} D={stats['D']} E={stats['E']}", file=sys.stderr)

    elapsed = time.time() - t0
    total = len(wines)

    p(f"{'='*100}")
    p(f"RESUMO LETRA {letra} ({total} vinhos, {elapsed:.0f}s)")
    p(f"{'='*100}")
    p(f"  A  (matched Vivino):     {stats['A']:4d}  ({stats['A']/total*100:5.1f}%)")
    p(f"  B  (vinho novo):         {stats['B']:4d}  ({stats['B']/total*100:5.1f}%)")
    p(f"  C1 (eliminado na v5):    {stats.get('C1',0):4d}  ({stats.get('C1',0)/total*100:5.1f}%)")
    p(f"  C2 (quarentena incerto): {stats['C2']:4d}  ({stats['C2']/total*100:5.1f}%)")
    p(f"  D  (nao-vinho):          {stats['D']:4d}  ({stats['D']/total*100:5.1f}%)")
    p(f"  E  (destilado):          {stats['E']:4d}  ({stats['E']/total*100:5.1f}%)")
    p()
    p(f"  SOBE PRO RENDER (A):     {stats['A']:4d}  ({stats['A']/total*100:.1f}%)")
    p(f"  ELIMINADOS (D+E):        {stats['D']+stats['E']:4d}  ({(stats['D']+stats['E'])/total*100:.1f}%)")

    out.close()
    print(f"\n[{letra}] DONE — A={stats['A']} B={stats['B']} C2={stats['C2']} D={stats['D']} E={stats['E']} — {output_path}", file=sys.stderr)


if __name__ == '__main__':
    main()
