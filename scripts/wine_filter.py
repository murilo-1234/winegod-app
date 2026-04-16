"""
Filtro centralizado de nao-vinhos.

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
