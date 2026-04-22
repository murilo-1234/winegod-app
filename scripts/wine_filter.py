"""
Filtro centralizado de nao-vinhos.

FONTE UNICA DE VERDADE (DQ V3 Escopo 5 -- 2026-04-21)
=====================================================

Este arquivo (`C:\\winegod-app\\scripts\\wine_filter.py`, ~1.140 linhas,
consolidado 2026-04-15) e a **unica** fonte valida de classificacao
NOT_WINE neste produto. Todos os pipelines de ingestao do repo vivo
`C:\\winegod-app` obtem NOT_WINE daqui -- direta ou indiretamente
atraves de `scripts/pre_ingest_filter.should_skip_wine`.

Qualquer outro arquivo `wine_filter.py` fora deste caminho e **legado
morto** e NAO deve ser importado, sincronizado, nem consultado. Em
particular, `C:\\winegod\\utils\\wine_filter.py` (outro repo, ~43 linhas)
esta obsoleto e e ignorado pelo pipeline vivo. Nao abra trabalho de
sincronizacao com esse arquivo.

Consumidores oficiais (todos via `pre_ingest_filter.should_skip_wine`):
  - `backend/services/bulk_ingest.py` -- pipeline central DQ V3
  - `backend/services/new_wines.py`  -- chat auto-create
  - `scripts/import_render_z.py`     -- importador de scraping
  - `scripts/import_stores.py`       -- importador de lojas (indireto)

Regra operacional (feedback_notwine_propagation):
  Todo padrao novo de NOT_WINE deve ser adicionado AQUI (`_NON_WINE_PATTERNS`)
  e, se for regra procedural (ABV, volume, gramatura, data, case/kit),
  tambem em `scripts/pre_ingest_filter.py`.

Fonte de verdade operacional:
- reports/catalogo_completo_termos_not_wine_2026-04-15.md
- scripts/pre_ingest_filter.py

O filtro trabalha sobre texto normalizado:
- lowercase
- sem acentos
- preservando espacos e hifens relevantes para regex

Isso deixa o matching robusto para entradas como "taca"/"taca",
"navidenas"/"navidenas", "cachaca"/"cachaca" etc.
"""

import re
import unicodedata


_NON_WINE_PATTERNS = [
    # A1. Destilados gerais
    r"whisky",
    r"whiskey",
    r"vodka",
    r"gin(?!\s*ger)",
    r"rum",
    r"tequila",
    r"cognac",
    r"bourbon",
    r"mezcal",
    r"aguardiente",
    r"cachaca",
    r"sake",
    r"soju",
    r"grappa",
    r"brandy",
    r"absinth",
    r"schnapps",
    r"pisco",
    r"armagnac",
    r"rye",
    r"distillery",
    r"spirits",
    r"rhum",
    r"negroni",
    r"bitters",
    r"bacardi",
    r"malt(?:s|ed)?",

    # A2. Destilarias escocesas
    r"glenmorangie",
    r"glenfarclas",
    r"glenallachie",
    r"bowmore",
    r"glendronach",
    r"mortlach",
    r"glenrothes",
    r"glenfiddich",
    r"glenlivet",
    r"macallan",
    r"laphroaig",
    r"lagavulin",
    r"ardbeg",
    r"talisker",
    r"highland[\s-]?park",
    r"macphail",
    r"glengoyne",
    r"benriach",
    r"springbank",

    # A3. Sake japones
    r"junmai",
    r"daiginjo",
    r"ginjo",
    r"nihonshu",

    # A4. Whisky context
    r"cask[\s-]?strength",
    r"single[\s-]?cask",
    r"cask",

    # A5. Cerveja e sidra
    r"beer",
    r"cerveja",
    r"cerveza",
    r"bier",
    r"birra",
    r"cider",
    r"sidra",
    r"weihenstephaner",
    r"pils",
    r"biere",
    r"cans",
    r"guinness",

    # A6. Bebidas nao-alcoolicas
    r"water",
    r"agua",
    r"acqua",
    r"eau",
    r"wasser",
    r"juice",
    r"suco",
    r"jugo",
    r"jus",
    r"soft[\s-]?drink",
    r"soda",
    r"refrigerante",
    r"coffee",
    r"cafe",
    r"espresso",
    r"nespresso",
    r"kaffee",
    r"tea",
    r"cha",
    r"tee",
    r"infusion",
    r"tisane",

    # A7. Licores
    r"giffard",
    r"liqueur",
    r"liquor",
    r"licor",
    r"likor",
    r"likoer",
    r"liquore",

    # A8-A16. Comida
    r"cheese",
    r"queijo",
    r"fromage",
    r"queso",
    r"formaggio",
    r"kase",
    r"chocolate",
    r"chocolat",
    r"cacao",
    r"cocoa",
    r"chokolade",
    r"schokolade",
    r"summerbird",
    r"chicken",
    r"frango",
    r"beef",
    r"pork",
    r"carne",
    r"fish",
    r"shrimp",
    r"salmon",
    r"ham",
    r"presunto",
    r"prosciutto",
    r"sausage",
    r"linguica",
    r"chorizo",
    r"salame",
    r"salami",
    r"ketchup",
    r"mayonnaise",
    r"mustard",
    r"vinegar",
    r"olive[\s-]?oil",
    r"azeite",
    r"aceite",
    r"sauce",
    r"molho",
    r"salsa",
    r"honey",
    r"mel",
    r"miel",
    r"jam",
    r"geleia",
    r"mermelada",
    r"pasta",
    r"noodle",
    r"macarrao",
    r"rice",
    r"arroz",
    r"riz",
    r"cereal",
    r"granola",
    r"aveia",
    r"oats",
    r"snack",
    r"chips",
    r"crisp",
    r"glutenfri",
    r"gluten",
    r"kulinarne",
    r"ice[\s-]?cream",
    r"sorvete",
    r"gelato",
    r"glace",
    r"helado",

    # A17. Gift cards e vouchers
    r"gift[\s-]?card",
    r"gutschein",
    r"carte[\s-]?cadeau",
    r"tarjeta[\s-]?regalo",
    r"voucher",
    r"gift",
    r"presente",
    r"regalo",
    r"cadeau",
    r"geschenk",

    # A18. Acessorios de vinho
    r"corkscrew",
    r"saca[\s-]?rolha",
    r"decanter",
    r"wine[\s-]?rack",
    r"wine[\s-]?cooler",
    r"wine[\s-]?fridge",
    r"wine[\s-]?opener",
    r"bottle[\s-]?opener",
    r"abridor",
    r"wine[\s-]?glass",
    r"goblet",
    r"tumbler",
    r"taca",
    r"zalto",
    r"yaxell",
    r"maileg",
    r"glas",
    r"rack",

    # A19. Higiene e beleza
    r"soap",
    r"sabonete",
    r"jabon",
    r"shampoo",
    r"conditioner",
    r"condicionador",
    r"perfume",
    r"fragrance",
    r"cologne",
    r"cream",
    r"creme",
    r"crema",
    r"sahne",
    r"nata",
    r"lotion",
    r"locao",
    r"locion",
    r"moisturizer",
    r"toothpaste",
    r"mouthwash",
    r"razor",
    r"deodorant",
    r"detergent",
    r"detergente",
    r"suavizante",
    r"esponja",
    r"escova",
    r"toilet[\s-]?paper",
    r"papel[\s-]?higienico",

    # A20. Decoracao
    r"candle",
    r"vela",
    r"candela",
    r"bougie",
    r"neon[\s-]?sign",
    r"quadro",
    r"poster",
    r"flower",
    r"flor",
    r"bouquet",
    r"flores",
    r"lampara",

    # A21. Vestuario
    r"t[\s-]?shirt",
    r"camiseta",
    r"shirt",
    r"jeans",
    r"bra",
    r"panties",
    r"lingerie",
    r"underwear",
    r"dress",
    r"vestido",
    r"hoodie",
    r"blouse",
    r"blusa",
    r"roupas",
    r"zapatillas",

    # A22-A26. Outros itens nao-vinho
    r"volleyball",
    r"basketball",
    r"soccer",
    r"dumbbell",
    r"pet[\s-]?food",
    r"dog[\s-]?food",
    r"cat[\s-]?food",
    r"racao",
    r"book",
    r"livro",
    r"libro",
    r"livre",
    r"toy",
    r"brinquedo",
    r"juguete",
    r"laptop",
    r"smartphone",
    r"iphone",
    r"headphone",
    r"speaker",
    r"television",
    r"xiaomi",
    r"led",
    r"espresso[\s-]?machine",
    r"coffee[\s-]?machine",
    r"coffee[\s-]?maker",
    r"grinder",
    r"moedor",
    r"gillette",
    r"temptech",

    # A27-A36. Kits, caixas e packs
    r"box",
    r"kit",
    r"bundle",
    r"dozen",
    r"mixed[\s-]?case",
    r"case[\s-]?of[\s-]?\d+",
    r"subscription",
    r"advent[\s-]?calendar",
    r"owc",
    r"outlet",
    r"tray",
    r"pack",
    r"pacote",
    r"paquet",
    r"paket",
    r"caja",
    r"cajita",
    r"estuche",
    r"canastas",
    r"navidenas",
    r"ancheta",
    r"anteojos",
    r"llavero",
    r"juego",
    r"caixa",
    r"garrafas",
    r"unidades",
    r"lata",
    r"cassetta",
    r"astuccio",
    r"astucciato",
    r"scatola",
    r"confezione",
    r"coffret",
    r"personliche",
    r"empfehlung",
    r"persoonlijke",
    r"aanbeveling",
    r"flessen",
    r"stuks",
    r"fles",
    r"doos",
    r"gavekurv",
    r"flasker",
    r"smagekasse",
    r"gave",
    r"kologiske",
    r"warsztaty",
    r"wytrawne",
    r"personalizacji",
    r"zestaw",
    r"sticle",

    # A37. Estado e siglas
    r"damaged",
    r"arrival",
    r"beige",
    r"ltr",
    r"pcs",
    r"mlt",

    # ==========================================================
    # PARTE B — Expansao multilingua (gerada do piloto Gemini 2026-04-17)
    # Cobre cs, pl, ru, he, el, hr, sr, lt, bg, ka, uk, hy, zh, ja, ko,
    # tr, sv, fi, no, da, nl, hu, ro, ar
    # ==========================================================

    # B1. Vinagre/Vinegar — multilingua
    r"vinagre",         # PT/ES
    r"vinaigre",        # FR
    r"aceto",           # IT
    r"essig",           # DE
    r"azijn",           # NL
    r"wijnazijn",       # NL (wine vinegar)
    r"ocet",            # PL/CZ/SK
    r"ocat",            # HR/SR
    r"sirke",           # TR
    r"otet",            # RO (oțet)
    r"ecet",            # HU
    r"vineddike",       # DA
    r"vinaeger",        # SV (vinäger)
    r"viinietikka",     # FI
    r"eddik",           # NO
    r"уксус",           # RU
    r"оцет",            # UK
    r"оцат",            # SR cyrillic
    r"חומץ",            # HE
    r"خل\b",            # AR
    r"醋\b",            # ZH
    r"식초",            # KO
    r"\bξυδι\b",        # EL (ξύδι without accents after norm)

    # B2. Mead / Hidromel
    r"\bmead\b",
    r"hidromel",
    r"medovina",       # CS/SK/BG
    r"медовина",       # SR/RU cyrillic
    r"meadly",         # marca
    r"dwojniak",       # PL (mead strength)
    r"poltorak",       # PL (mead strength)
    r"trojniak",       # PL
    r"czworniak",      # PL
    r"miod\s+pitny",   # PL (drinking honey = mead)
    r"hydromel",       # FR
    r"hidromiel",      # ES
    r"idromele",       # IT
    r"met\b",          # DE
    r"honingwijn",     # NL (honey wine)
    r"sima\b",         # FI mead
    r"mjod",           # SE/NO mead
    r"miodowina",      # PL alt
    r"蜂蜜酒",          # ZH/JA mead

    # B3. Cidre/Sidra/Perry adicionais
    r"\bcidre\b",      # FR
    r"\bperry\b",      # EN pear cider
    r"poire\b",        # FR (when context cidre)
    r"birnenmost",     # DE pear cider
    r"sidr",           # CS/PL
    r"epleeider",      # NO apple cider
    r"omenasiideri",   # FI
    r"siideri",        # FI cider
    r"appelvin",       # SV apple wine
    r"aebleeider",     # DA æblecider
    r"jablecny\s+mosc",  # CZ apple cider

    # B4. Cerveja adicional por lingua
    r"piwo",           # PL beer
    r"pivo",           # CS/SK/SI/HR/SR
    r"пиво",           # RU/UK/BG/SR cyrillic
    r"\bol\b",         # SV øl/öl beer
    r"olut",           # FI beer
    r"\bbira\b",       # GR (μπύρα → bira after transliteration)
    r"bere\b",         # RO/IT beer
    r"sor\b",          # HU beer
    r"alus",           # LV beer
    r"alaus",          # LT beer
    r"birra",          # IT (already partial)
    r"\bipa\b",        # India Pale Ale
    r"\bapa\b",        # American Pale Ale
    r"\bipl\b",        # India Pale Lager
    r"lager",          # beer
    r"pilsner",        # beer
    r"\bpils\b",       # beer
    r"stout",          # beer
    r"\bporter\b(?!\s*(amarone|barolo|chianti|valpolicella|brunello|prosecco|champagne))",  # beer; exclui pret-a-porter de vinhos
    r"\bale\b",        # beer
    r"\bsaison\b",     # beer
    r"\bgose\b",       # beer
    r"witbier",        # NL beer
    r"weissbier",      # DE beer
    r"weizen",         # DE wheat beer
    r"hefeweizen",     # DE
    r"helles",         # DE beer
    r"dunkel",         # DE dark beer
    r"radler",         # DE shandy
    r"shandy",         # beer mix
    r"zatecky",        # CZ Zatec beer
    r"\blezak\b",      # CZ pilsner
    r"svetly\s+lezak",
    r"cerny\s+lezak",
    r"haandbrygg",     # NO craft beer
    r"haandbryg",      # NO alt
    r"zmajska",        # HR brewery
    r"karmi",          # PL beer brand
    r"perla\b",        # PL beer
    r"żywiec",         # PL beer
    r"tyskie",         # PL beer

    # B5. Refrigerante / Soda / Limonada
    r"napoj",          # PL drink
    r"napoje",         # PL drinks
    r"napitak",        # HR drink
    r"napitka",        # BG/SR drink
    r"lemoniada",      # PL
    r"lemonada",       # CZ/SK/UA
    r"limonata",       # IT
    r"limonade",       # FR/DE
    r"lemonade",       # EN
    r"limonad",        # TR
    r"limonadi",       # FI
    r"oranzada",       # PL orange soda
    r"oranjada",       # PL alt
    r"\btonic\b",
    r"\btonico\b",
    r"napoj\s+gazowany",  # PL carbonated drink
    r"napoj\s+owocowy",   # PL fruit drink
    r"sok\b",             # PL/CZ/SK juice
    r"sumavske",          # CZ mineral water brand
    r"limca",             # IN
    r"isotonic",
    r"energy\s+drink",
    r"sports\s+drink",
    r"smoothie",
    r"shake\b",
    r"milkshake",
    r"vitaminwater",
    r"kombucha",          # may overlap fermented but not wine
    r"коктейль",          # RU cocktail

    # B6. Oleo/Olio/Olej extras (oils)
    r"\bolio\b",       # IT olive oil shorthand
    r"\boleo\b",       # PT/ES alt
    r"\bolej\b",       # CS/PL/SK oil
    r"\boli\b",        # CA oil
    r"\boli ja\b",     # FI oil
    r"\bolja\b",       # SV oil
    r"\bolaj\b",       # HU oil
    r"\bulei\b",       # RO oil
    r"\bbalsamico\b",  # IT vinegar/oil
    r"\bbalsamic\b",   # EN
    r"маслo",          # RU oil
    r"масло",          # RU oil

    # B7. Spirits adicionais
    r"\barak\b",       # MidEast spirit
    r"\barack\b",      # alt spelling
    r"\barrack\b",     # alt
    r"araki",          # alt
    r"shochu",         # JP spirit
    r"shokoshi",       # JP variant
    r"baijiu",         # CN spirit
    r"\bsoju\b",       # KO (already in A1 maybe)
    r"白酒",           # ZH baijiu
    r"焼酎",           # JA shochu
    r"高粱酒",         # ZH gaoliang
    r"\brakija\b",     # Balkan plum brandy
    r"rakia\b",        # alt
    r"slivovica",      # CS/SK plum brandy
    r"slivovice",      # CS
    r"sliwowica",      # PL
    r"palinka",        # HU brandy
    r"palenka",        # SK
    r"borovicka",      # SK juniper brandy
    r"tsipouro",       # GR pomace brandy
    r"τσιπουρο",       # GR
    r"raki",           # TR (already)
    r"ракия",          # BG
    r"zubrowka",       # PL bison vodka
    r"krupnik",        # PL honey vodka
    r"jagermeister",   # DE liqueur
    r"jaegermeister",  # DE alt
    r"underberg",      # DE bitter
    r"becherovka",     # CZ herbal
    r"unicum",         # HU herbal
    r"fernet",         # IT/AR herbal
    r"campari",        # IT bitter
    r"aperol",         # IT bitter
    r"\bamaro\b",      # IT herbal liqueur
    r"\bsambuca\b",    # IT anise
    r"limoncello",     # IT lemon
    r"\bcalvados\b",   # FR apple brandy
    r"\bgrappa\b",     # IT (already)
    r"\borujo\b",      # ES pomace
    r"chacha",         # GE pomace
    r"чача",           # GE/RU chacha
    r"раки",           # cyrillic raki
    r"коньяк",         # RU cognac
    r"водка",          # RU vodka
    r"виски",          # RU whisky
    r"\bsoju\b",       # KO
    r"소주",            # KO soju
    r"막걸리",         # KO makgeolli (rice wine — but not grape, X)
    r"맥주",            # KO beer
    r"꼬냑",            # KO cognac

    # B8. Comida adicional
    r"\bterrine\b",
    r"\bpate\b(?!\s+de\s+vin)",   # pate but not "pate de vin"
    r"\bpate\s+(?:de|en|au)\b",
    r"foie\s+gras",
    r"\brillettes\b",
    r"\bboldo\b",      # herbal tea
    r"zapallo",        # LATAM pumpkin
    r"zapallito",      # LATAM zucchini
    r"\bzeama\b",      # MD broth
    r"\bsupa\b",       # RO soup
    r"\bsoupe\b",      # FR soup
    r"\bsuppe\b",      # DE soup
    r"\bsop\b",        # NL soup
    r"\bzupa\b",       # PL soup
    r"\bpolevka\b",    # CZ/SK soup
    r"\bborscht\b",
    r"\bhummus\b",
    r"\bguacamole\b",
    r"\btahini\b",
    r"\btzatziki\b",
    r"\bfeta\b",
    r"halloumi",
    r"mozzarella",
    r"ricotta",
    r"gorgonzola",
    r"\bbrie\b",
    r"camembert",
    r"\broquefort\b",
    r"manchego",
    r"\bedam\b",
    r"gouda",
    r"emmental",
    r"\bkaas\b",       # NL cheese
    r"queijada",       # PT cheese tart
    r"\bmel\b",        # PT honey (already in A but)
    r"manuka",         # honey
    r"\bnata\b",       # PT cream/dessert (careful — could be wine? rare)
    r"creme\s+brulee",
    r"tiramisu",
    r"panettone",
    r"colomba",
    r"\bstrudel\b",
    r"\bbrownies?\b",
    r"\bcookies?\b",
    r"\bbiscoito\b",
    r"\bbiscuit\b",
    r"galleta",
    r"\bcrackers?\b",
    r"\bbarra\b\s+(?:de|cereal|granola)",
    r"granola",        # already
    r"muesli",
    r"\bkasha\b",      # buckwheat
    r"\bgulasch\b",
    r"goulash",
    r"\bsushi\b",
    r"\bsashimi\b",
    r"\btempura\b",
    r"\bramen\b",
    r"\bpho\b",
    r"\bcurry\b",
    r"masala",
    r"\bbiryani\b",
    r"paella",
    r"risotto",
    r"\bgnocchi\b",
    r"\blasagna\b",
    r"\blasagne\b",
    r"ravioli",
    r"tortellini",
    r"churros",
    r"\bempanada\b",
    r"\btacos?\b",
    r"\bburrito\b",
    r"\bfajita\b",
    r"quesadilla",
    r"\bnachos?\b",
    r"\bsalsa\b",      # already partial
    r"\bsalami\b",     # already
    r"\bjamon\b",
    r"\bchorizo\b",    # already
    r"\bbacon\b",
    r"\bnatas\b",      # PT cream
    r"peprmint",
    r"peppermint\s+bark",
    r"vanilla\s+(?:bean|extract|pod)",
    r"\bzazitek\b",    # CZ experience (when food/beverage)

    # B9. Brands NOT_WINE
    r"\bzassenhaus\b",
    r"\bzansot\b",
    r"\bzendium\b",
    r"\bzbyszko\b",
    r"\bzephir\b",
    r"\bzengaz\b",
    r"\bzbiotics\b",
    r"\bzeolite\b",
    r"\bzeobent\b",
    r"\bzbox\b",
    r"\bzdrov\w*",     # CZ healthy
    r"\bzansibar\b",   # often non-wine context (towel/beach)
    r"\bzelo\b",
    r"\bspiegelau\b",  # glass brand
    r"riedel",         # glass brand
    r"\bzwiesel\b",    # glass brand
    r"\bschott\b",     # glass brand
    r"\bweck\b",       # jar brand
    r"\bvileda\b",     # cleaning
    r"\bganchos?\b",   # ES hooks
    r"perchero",       # ES coat rack
    r"organizador",
    r"caserola",
    r"\bsamsung\b",
    r"\bxiaomi\b",
    r"\bnokia\b",
    r"\bapple\b\s+(iphone|watch|mac|ipad)",
    r"\bhuawei\b",
    r"\boppo\b",

    # B10. Calcado/Roupa extras
    r"\bzapatilla\b",          # singular (filtro tinha so plural)
    r"\bzapatera\b",
    r"\bzapatero\b",
    r"\bzapato\b",
    r"\bzapatos\b",
    r"\bzapatico\b",
    r"\bnike\b",
    r"\badidas\b",
    r"\bpuma\b",
    r"\blacoste\b",
    r"\bjordan\b",
    r"\bmichelin\b\s*(zegama|dobra|kepler|nord)",   # tenis Michelin
    r"\bsneakers?\b",
    r"\btennis\s+(shoes?|sapato)",
    r"\btenis\s+(homem|mulher|infantil|esporte)",
    r"\bcalcado\b",
    r"\bbota\b",
    r"\bbotas\b",
    r"\bsandalia\b",
    r"\bsandal\b",
    r"\bhalterneck\b",
    r"\bswimsuit\b",
    r"\bswimwear\b",
    r"\bbikini\b",
    r"\bbiquini\b",
    r"\bmaillot\b",
    r"\bbadeanzug\b",
    r"trousers",
    r"\bcalcas\b",
    r"\bsaia\b",
    r"\bskirt\b",
    r"\bblusa\b",       # already
    r"\bcamisa\b",
    r"\bcamiseta\b",    # already
    r"\bjacket\b",
    r"jaqueta",
    r"casaco",
    r"\bcalsoes\b",
    r"\bzebra\s+(?:print|pattern|chic)",
    r"\bvestuario\b",
    r"\bmoda\b",

    # B11. Servicos / Experiencias (nao sao produto)
    r"\bdegustace\b",   # CZ tasting
    r"degustacao",     # PT
    r"degustacion",    # ES
    r"\bzazitkov\w*",  # CZ experience
    r"\bzazitky\b",    # CZ
    r"\bpobyt\b",      # CS/PL stay
    r"\bmasaz\b",      # CZ massage
    r"masaje",         # ES
    r"massagem",       # PT
    r"\bspa\b",
    r"\bvouchery\b",
    r"\bcurso\b",
    r"\bcourse\b",
    r"\bworkshop\b",
    r"\bevento\b",
    r"\bhotel\b",
    r"\baluguel\b",
    r"\baulas?\b",
    r"\baulas\s+de\b",
    r"\bsessao\s+de\b",
    r"\bsessoes\b",
    r"\bnoite\b",
    r"\bbalkon\w*",
    r"\bromantic\w*\s+(getaway|stay|escape)",
    r"\bweekend\s+(?:break|getaway|escape)",

    # B12. Cook wine / Test / Mystery / Club
    r"cook[\s-]?wine",
    r"culinary\s+wine",
    r"vinho\s+culinari[oa]",
    r"vino\s+culinari[oa]",
    r"vino\s+para\s+cocinar",
    r"\btest\s+wine\b",
    r"\bsample\s+wine\b",
    r"\bexample\s+wine\b",
    r"vinho\s+exemplo",
    r"mystery\s+(?:box|pack|case|wine|sampler|red|white)",
    r"caja\s+misterio",
    r"caisse\s+mystere",
    r"surprise\s+(?:box|pack|case)",
    r"wine\s+club",
    r"club\s+(?:viners|de\s+vinho|du\s+vin)",
    r"vivino\s+box",
    r"\bsubscription\s+box\b",
    r"monthly\s+(?:box|club|delivery)",
    r"discovery\s+(?:box|pack|case)",
    r"introductory\s+(?:box|pack|sampler)",
    r"starter\s+(?:box|pack|kit)",
    r"sampler\s+(?:pack|kit|set|trio)",
    r"\bgametime\b\s+wine\s+trio",
    r"\bwill\s+go\s+away\s+soon",  # placeholder name
    r"\bdelete\s+me\b",
    r"\btest\s+de\b",
    r"buuue",                       # placeholder

    # B13. UI / promos (REMOVIDOS termos promocionais que aparecem em wines reais —
    # desconto/oferta/promocao/frete gratis/precos sao apenas ruido de scraping
    # e marcam wines validos com texto promocional). Mantemos so o que indica
    # claramente NAO ser um produto:
    r"\bzdarma\b",                  # CZ free (so promo, nao produto)
    r"\bzdarmazdarma\b",

    # B14. Asian scripts (caracteres literais — passam pelo normalize)
    r"葡萄醋",       # ZH grape vinegar
    r"米酒",         # ZH rice wine (not grape — X by our rules: only sake/yakju/huangjiu allowed)
    r"清酒",         # ZH refined sake (already covered by sake)
    r"啤酒",         # ZH beer
    r"果汁",         # ZH juice
    r"汽水",         # ZH soda
    r"茶\b",         # ZH/JA tea
    r"咖啡",         # ZH coffee
    r"ビール",       # JA beer
    r"ジュース",     # JA juice
    r"コーヒー",     # JA coffee
    r"焼酎",         # JA shochu
    r"맥주",         # KO beer
    r"주스",         # KO juice
    r"커피",         # KO coffee
    r"막걸리",       # KO makgeolli rice
    r"소주",         # KO soju

    # B15. Acessorios extras
    r"\bpeeler\b",
    r"\bcorkscrew\b",   # already
    r"\bbottle\s+stopper\b",
    r"vacuum\s+(?:pump|stopper)",
    r"\bzatka\b",       # CS cork/stopper
    r"\bzatky\b",       # CS plural
    r"\bsaca\s+rolha\b",
    r"\bdescortinador\b",
    r"\bsponge\b",
    r"\bloufah\b",
    r"\bloofah\b",
    r"\bluffa\b",
    r"\bbedpan\b",
    r"\bmortar\b",
    r"\bpestle\b",
    r"\balmofariz\b",
    r"\bhair\s+(?:tie|clip|comb|band|brush|clipper)",
    r"\bnail\s+(?:clipper|file|polish)",
    r"\bvegetable\s+peeler\b",
    r"\bsalt\s+mill\b",
    r"\bpepper\s+mill\b",
    r"\bcoffee\s+mill\b",
    r"\bespresso\s+mill\b",
    r"\bespresso[my]?ll\w*",   # FI espressomylly
    r"\bsalty?[my]?ll\w*",
    r"\bmunakello\b",          # FI egg timer
    r"\begg\s+timer\b",
    r"\btimer\b",
    r"\bashtray\b",
    r"\bcinzeiro\b",
    r"пепельница",             # RU ashtray
    r"\bpepelnica\b",
    r"\blighter\b",
    r"\bisqueiro\b",
    r"encendedor",
    r"\bmirror\b",
    r"\bespelho\b",
    r"\bespejo\b",
    r"\bspiegel\b",
    r"\bcabide\b",
    r"\bperchero\b",
    r"\bzbox\b",
    r"\btablecloth\b",
    r"\btoalha\b",
    r"\bnapkin\b",
    r"\bguardanapo\b",
    r"\bservilleta\b",
    r"\bplaca\b",
    r"\btravessa\b",
    r"\bbandeja\b",
    r"\btarjoilulauta\b",   # FI serving board
    r"\bservierbrett\b",
    r"\bcutting\s+board\b",
    r"\btabua\b",
    r"\bfork\b",
    r"\bgarfo\b",
    r"\bspoon\b",
    r"\bcolher\b",
    r"\bknife\b",
    r"\bfaca\b",
    r"\bcuchillo\b",
    r"\bplate\b",
    r"\bprato\b",
    r"\bplato\b",
    r"\btray\b",       # already

    # B16. Sapateira / Mobiliario / Casa
    r"\borganizador\b",
    r"\bcaserola\b",
    r"\bcacerola\b",
    r"\bzucchini\b",
    r"\babobora\b",
    r"\babobrinha\b",
    r"\bcalabaza\b",
    r"\bcalabacin\b",
    r"\bcabutia\b",
    r"\bkabutia\b",
    r"\bzucca\b",
    r"\bkurbis\b",
    r"\btykva\b",
    r"\bmacre\b",       # zapallo macre
    r"\bloche\b",       # zapallo loche
    r"\bjamboree\b",    # zapallo jamboree
    r"\bcoreanito\b",
    r"\bcamote\b",
    r"\bjapones\b\s+x\s+und",  # weird produce listing
    r"\bproduce\b",
    r"\bvegetal\b",
    r"\blegume\b",
    r"\bvegetable\b",
    r"\bkilo\b",
    r"\bbandeja\b",
    r"\bpaqueton\b",
    r"\bvarios\s+sabores\b",

    # B17. Livros / Editoras
    r"\bleather[\s-]?bound\b",
    r"\bartscroll\b",
    r"\bpittau\b",
    r"\bgervais\b",
    r"\bkocharz\b\s+x\s+",     # Pol food collab marker
    r"\bnovela\b",
    r"\bnovel\b",
    r"\baudiobook\b",
    r"\bcd\s+mp3\b",
    r"\bdvd\b",
    r"\bblu[\s-]?ray\b",

    # B18. Servicos extras / Lifestyle nao-vinho
    r"\binstagram\b",
    r"\bfollowers?\b",
    r"\bsubscriber\b",
    r"\binscrição\b",
    r"\bregistro\b",
    r"\baccount\b",
    r"\baplicativo\b",
    r"\bapp\b\s+(de|para|store|gratis|gratuito)",

    # ==========================================================
    # PARTE C — Padroes semanticos (validados 2026-04-17)
    # 14 padroes identificados na analise dos 1000 wines do piloto Gemini
    # + E1/E2/E3 afrouxados. FP rate <= 0.2% em 5k wines aplicados.
    # ==========================================================

    # C1. Rum/destilado envelhecido (marcas Zacapa/Zaya/Kirk)
    r"\bzacapa\b",
    r"\bzaya\b",
    r"\bkirk\s*&\s*sweeney\b",

    # C1b. Plum brandy serbio/eslavo
    r"\bsljiva\b",
    r"šljiva",
    r"\bzavet\s+(\d+\s+)?plum\b",
    r"\bzdanje\s+plum\b",
    r"\b\d+\s*y\.?o\.?\s*lux\b",

    # C3. Alcohol-free / De-alcoholized / Zero (bebida sem alcool != vinho)
    r"\balcohol[\s-]?free\b",
    r"\bnon[\s-]?alcoholic\b",
    r"\bde-?alcoholi[sz]ed\b",
    r"vin\s*\(\s*zero\s*\)",
    r"\bzero\s+(alcohol|vegan)\s+alcohol\s+free\b",
    r"\b0\s*%\s*alcohol\b",

    # C4. Personalize / test / sample / dummy / delete
    r"\bpersonali[sz]e\b",
    r"\btest\s+wine\b",
    r"\bsample\s+wine\b",
    r"\bchateau\s+delete\b",
    r"\bvinho\s+exemplo\b",
    r"\bwill\s+go\s+away\s+soon\b",
    r"\btest\s+de\b",
    r"\bbuuue\b",
    r"\bdummy\s+wine\b",

    # C5. Case only / multipack / sampler
    r"\(case\s+only\)",
    r"\bwine\s+trio\b",
    r"\b\d+\s*btl\b",
    r"\bspeciall[åa]da\b",
    r"\bsortimentl[åa]da\b",
    r"\bsmagek[åa]sse\b",
    r"\b\d+\s*pk\s+\w",

    # C6. Codigo SKU prefixo
    r"\bcod\s+[A-Z]{2}\d{3}\b",
    r"\bcod\.\s*[A-Z0-9]{4,}\b",

    # C7. CJK ideograma NOT_WINE
    r"ウイスキー",          # JA whisky
    r"龍舌蘭",               # ZH tequila/agave
    r"紅酒杯",               # ZH wine glass
    r"本セット",             # JA bottle set
    r"入荷予定",             # JA pre-order
    r"停產",                 # ZH discontinued
    r"先行販売",             # JA pre-sale
    r"啤酒",                 # ZH beer
    r"高原騎士",             # ZH Highland Park whisky
    r"蜂蜜酒",               # ZH mead

    # C8. Eventos / festivais / concertos
    r"\bwijnfestival\b",
    r"\bbor\s+koncert\b",
    r"\bhubnut[ií]\b",
    r"\banal[yý]za\s+t[ěe]la\b",
    r"\bkoncert\s+december\b",
    r"\blekc[ií]\s+i\b",

    # C9. Acessorios/utilidades com medida
    r"\bpeelers?\b",
    r"\bzap\s+cap\b",
    r"\bbadhandduk\b",
    r"\btestp[uú]der\b",
    r"\bmacave\s+s\d+",
    r"\bv[äa]ggspegel\b",
    r"\bspegel\s+\d+\s*cm\b",
    r"\bzdrobitor\b",

    # C10. Livros/filmes/autor
    r"\bfinch\s+by\s+[A-Z]",
    r"\bzealot'?s\s+heart\b",
    r"\bve\s+soytar[iı]\b",
    r"\bzawodowcy\b",
    r"^zlatanka\b",

    # C11. Comida/tempero/lanche
    r"\bzenzero\b",             # IT ginger
    r"\bgeitenkaas\b",          # NL goat cheese
    r"\bzapallo[s]?\s+en\s+alm[ií]bar\b",  # pumpkin dessert
    r"\bbrisket\b",
    r"\bbbq\s+rub\b",
    r"\bbar-b-que\s+rub\b",
    r"\bkapszula\b",            # HU capsule/supplement
    r"\bjátékaut[óo]\b",        # HU toy car
    r"\bsütidoboz\b",           # HU baking box
    r"\bbonbon\b(?!\s*blanc)",  # candy (except wine "bonbon blanc")

    # C12. Numeros romanos completos como nome (MMIX/MMXI/etc)
    r"^\s*M{1,3}[CDLXVI]+\s*$",
    r"^\s*\d{1,3}\s*ad\s*$",

    # C13. Nomes lixo/UI/codigos
    r"\btemporal\s+table\s+bloob\b",
    r"\bzenwtr\b",

    # C14. Grape spirit / licor
    r"\bgrape\s+spirit\b",
    r"\blik[eé]r\b",
    r"\bz[áa]zvor\w+\b",
    r"\bhenequen\s+ba[ñn]o\b",

    # E2. Nome/produtor curto sem espaco (marca misteriosa sem estrutura)
    # Captura palavras 4-12 caracteres SO (sem espacos, sem info).
    # Valida so quando o texto inteiro e isso.
    r"^\s*[a-zA-Z]{4,12}\s*$",

    # E3. Preco com moeda + percentual desconto (UI scraping)
    r"\b\d+\s*(kc|kč|kr|kn|ron|lei|pln|czk|huf|sek|dkk|nok|chf)\b",
    r"–\s*\d+\s*%",
]


NON_WINE_RE = re.compile(r"\b(" + "|".join(_NON_WINE_PATTERNS) + r")\b")


def _normalize_text(text):
    text = text or ""
    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    return text.casefold()


def is_wine(nome):
    """Retorna True se o produto provavelmente e vinho."""
    if not nome or len(nome.strip()) < 3:
        return False
    return not NON_WINE_RE.search(_normalize_text(nome))


def classify_product(nome):
    """Retorna ('wine', None) ou ('not_wine', 'termo_detectado')."""
    if not nome or len(nome.strip()) < 3:
        return "not_wine", "nome_vazio_ou_curto"

    normalized = _normalize_text(nome)
    match = NON_WINE_RE.search(normalized)
    if match:
        return "not_wine", match.group(0)

    return "wine", None


if __name__ == "__main__":
    should_block = [
        "Johnnie Walker Black Label Whisky 750ml",
        "Giffard Liqueur Gift Pack",
        "Caja de Vinos Navidenas 12 unidades",
        "Rose Water Fee Brothers 4oz",
        "Ice Cream Almond 440ml",
        "Glenmorangie Original 10 Year Old",
        "Taca Cristal Bohemia 450ml",
        "Samsung Galaxy S24 Smartphone",
    ]

    should_pass = [
        "Chateau Margaux 2015 Premier Grand Cru",
        "Casillero del Diablo Cabernet Sauvignon 2022",
        "Penfolds Grange Shiraz 2018",
        "Dom Perignon Vintage 2013",
    ]

    print("=== DEVEM SER BLOQUEADOS ===")
    for nome in should_block:
        result, cat = classify_product(nome)
        status = "OK BLOQUEADO" if result == "not_wine" else "FALHA"
        print(f"[{status}] {nome} => {cat}")

    print("\n=== DEVEM PASSAR ===")
    for nome in should_pass:
        result, cat = classify_product(nome)
        status = "OK PASSOU" if result == "wine" else f"FALHA ({cat})"
        print(f"[{status}] {nome}")
