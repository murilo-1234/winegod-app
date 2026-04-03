#!/usr/bin/env python3
import os
import re
import unicodedata
from pathlib import Path

SRC = Path(os.environ.get("CODEX_SRC", r"C:\winegod-app\lotes_codex\lote_z_006.txt"))
OUT = Path(os.environ.get("CODEX_OUT", r"C:\winegod-app\lotes_codex\resposta_z_006.txt"))

raw_lines = SRC.read_text(encoding="utf-8").splitlines()
items = []
started = False
for line in raw_lines:
    if not started:
        if re.match(r"^\s*4\.\s+W\|.*\|=3\s*$", line):
            started = True
            continue
        else:
            continue
    m = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
    if m:
        items.append((int(m.group(1)), m.group(2).strip()))
if not items:
    raise SystemExit("no numbered items found")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def has_any(text: str, needles) -> bool:
    return any(n in text for n in needles)


WINE_PREFIXES = {
    "domaine", "chateau", "clos", "mas", "tenuta", "bodega", "bodegas",
    "weingut", "cantina", "cantine", "azienda", "castello", "finca", "podere",
    "villa", "maison", "estate", "winery", "vignobles", "vignoble", "quinta",
    "domain", "dominio", "cellar", "cave", "caves",
}

WINE_TERMS = {
    "aoc", "doc", "docg", "doca", "dop", "igt", "igp", "beaujolais", "bourgogne",
    "burgundy", "bordeaux", "champagne", "cremant", "cotes", "cote", "jura",
    "morgon", "fleurie", "chenas", "julienas", "saint", "amour", "meursault",
    "puligny", "montrachet", "chablis", "gevrey", "chambertin", "morey", "corton",
    "pommard", "volnay", "santenay", "chassagne", "pouilly", "fuisse", "fume",
    "sancerre", "anjou", "touraine", "loire", "alsace", "valais", "rioja",
    "ribera", "duero", "rueda", "priorat", "penedes", "cava", "jerez", "mendoza",
    "patagonia", "salta", "napa", "sonoma", "barossa", "marlborough", "tokaj",
    "tokaji", "barolo", "barbaresco", "chianti", "brunello", "montalcino",
    "valpolicella", "amarone", "soave", "prosecco", "franciacorta", "lambrusco",
    "verdicchio", "montepulciano", "salice", "salentino", "puglia", "sicilia",
    "sicily", "sardegna", "veneto", "toscana", "piemonte", "lombardia",
    "alto", "adige", "trentino", "frascati", "etna", "navarra",
}

NON_WINE_HINTS = {
    "soap", "shampoo", "conditioner", "body wash", "body lotion", "lotion",
    "hand cream", "candles", "candle", "glass", "glasses", "cup", "cups", "mug",
    "plates", "plate", "bottle opener", "opener", "gift basket", "basket", "chocolate",
    "sweet", "snack", "snacks", "cheese", "ham", "pasta", "rice", "sauce", "tea",
    "coffee", "water", "juice", "beer", "cider", "hoodie", "shirt", "bag",
    "accessory", "accessories", "sign", "neon", "zippo", "lighter", "book",
    "vela", "vela aromatica", "vela aromática", "acessorio",
}


def year(text: str) -> str:
    m = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if m:
        return m.group(1)
    m = re.search(r"(?<!\d)(\d{2})(?!\d)", text)
    if m:
        yy = int(m.group(1))
        if 0 <= yy <= 30:
            return f"20{yy:02d}"
    if "nv" in text:
        return "NV"
    return "NV"


def classify_type(t: str) -> str:
    if has_any(t, ["zobrazit ", "zjistit ", "zoeken ", "znovu skladem", "ziua ", "ziskejte ", "ziskana "]):
        return "X"
    if has_any(t, ["vodka", "wodka", "gin ", "rum", "tequila", "grappa", "cachaca", "cachaça", "brandy", "calvados",
                   "pisco", "soju", "baijiu", "shochu", "genever", "tuica", "viljamovka", "sljiva", "kajsija",
                   "dunja", "jablkovica", "ceresnovica", "pelinkovac", "vinjak", "liqueur", "likor", "liker",
                   "zoladkowa",
                   "pacharan", "geist", "coincoin", "cointreau", "zirbenz", "zirbel", "zlatni pelin", "zlatni vinjak",
                   "zlatna dolina", "zlatiborski vrh pelinkovac", "zlivowitz", "zizak "]):
        return "S"
    if any(h in t for h in NON_WINE_HINTS):
        return "X"
    if has_any(t, ["wine", "vino", "vinho", "prosecco", "champagne", "cava", "cremant", "secco", "sparkling", "brut",
                   "rose", "rosato", "malbec", "cabernet", "merlot", "chardonnay", "sauvignon", "riesling",
                   "torrontes", "susumaniello", "primitivo", "lagrein", "furmint", "tokaji", "muscat", "moscato",
                   "shiraz", "syrah", "tempranillo", "zinfandel", "plavac", "posip", "babic", "cannonau", "gruner",
                   "veltelini", "veltlinski", "veltlinske", "gewurztraminer", "sylvaner", "albarino", "grillo",
                   "inzolia", "passerina", "montepulciano", "nero davola", "nero d'avola", "icewine", "beerenauslese",
                   "passito", "doc", "aoc", "igt", "igp", "dac", "erste lage", "reserva", "reserve", "cuvee", "blend",
                   "gluhwein", "gluhwein", "gluwein", "port", "porto", "sherry", "marsala", "madeira", "manzanilla"]):
        return "W"
    if has_any(t, ["zold ", "zoldv", "zoldveltelini", "zold veltelini", "zom ", "zolo ", "zolla ", "zoltan ", "zoetendal",
                   "zoe ", "zoehlhof", "zoinos", "zohrer", "zohlhof", "zocker", "znovin", "znojemsky", "zmora",
                   "zmeurica", "zlatan", "zlahtina", "zita wines", "zisola", "ziro ", "ziru ", "zizz", "zobinger",
                   "zobbobourg", "zojosu", "zoilo ", "ziva ", "zodiac", "zodiaque", "zocker", "zome", "zofie",
                   "zobl ", "zoleta", "zola ", "zolotaya balka", "zlomek vavra"]):
        return "W"
    return "W"


def color(t: str) -> str:
    if has_any(t, ["champagne", "prosecco", "cava", "cremant", "secco", "sparkling", "brut", "frizzante", "penina"]):
        return "s"
    if has_any(t, ["rose", "rosato", "blush", "pink"]):
        return "p"
    if has_any(t, ["porto", "port ", "sherry", "marsala", "madeira", "manzanilla", "amontillado", "oloroso", "palo cortado"]):
        return "f"
    if has_any(t, ["white", "blanc", "bianco", "branco", "weiss", "veltelini", "veltlinske", "veltlinski", "riesling",
                   "chardonnay", "sauvignon blanc", "torrontes", "albarino", "grillo", "inzolia", "sylvaner",
                   "muscat", "moscato", "passerina"]):
        return "w"
    if has_any(t, ["icewine", "beerenauslese", "passito", "sweet", "dolce", "doce", "semisweet", "semi sweet",
                   "polosladke", "polosladke", "dessert", "tokaji"]):
        return "d"
    return "r"


def grape(t: str) -> str:
    grapes = [
        "cabernet sauvignon", "cabernet franc", "malbec", "merlot", "chardonnay", "sauvignon blanc", "sauvignon",
        "torrontes", "susumaniello", "primitivo", "negroamaro", "malvasia nera", "pinot noir", "pinot grigio",
        "pinot gris", "muscat", "moscato", "gruner veltliner", "veltelini", "furmint", "riesling", "shiraz",
        "syrah", "tempranillo", "grenache", "mataro", "garnacha", "cannonau", "plavac mali", "posip", "babic",
        "crljenak", "zinfandel", "petit verdot", "semillon", "vermentino", "lagrein", "gewurztraminer", "sylvaner",
        "trebbiano", "grillo", "inzolia", "passerina", "montepulciano", "nero davola", "nero d'avola", "corvina",
        "rondinella", "molinara", "white blend", "red blend"
    ]
    for g in grapes:
        if g in t:
            return g
    return "??"


def country(t: str) -> str:
    if has_any(t, ["argentina", "mendoza"]):
        return "ar"
    if has_any(t, ["italia", "sicilia", "sicily", "puglia", "salento", "veneto", "toscana", "tuscany", "piemonte",
                   "alto adige", "sudtirol", "gragnano", "sardegna", "sardinia", "bolgheri", "noto"]):
        return "it"
    if has_any(t, ["austria", "kremstal", "wachau", "weinviertel", "ruppersthal", "heiligenstein", "gaisberg"]):
        return "at"
    if has_any(t, ["france", "bordeaux", "bourgogne", "burgund", "aoc", "champagne", "cremant", "loire", "valais"]):
        return "fr"
    if has_any(t, ["spain", "rioja", "navarro", "cava", "jerez", "andalucia", "navarra"]):
        return "es"
    if has_any(t, ["croatia", "dalmacija", "hvar", "sibenik", "plavac", "zlatan otok"]):
        return "hr"
    if has_any(t, ["czech", "znojmo", "znovin"]):
        return "cz"
    if has_any(t, ["hungary", "tokaji", "tokaj", "demeter", "zoldveltelini", "veltelini", "balaton"]):
        return "hu"
    if has_any(t, ["israel", "zmora", "ben ami"]):
        return "il"
    if has_any(t, ["south africa", "zoetendal"]):
        return "za"
    if has_any(t, ["greece", "greek", "epirus", "zoinos"]):
        return "gr"
    if has_any(t, ["slovenia", "radgona"]):
        return "si"
    if has_any(t, ["poland", "zoladkowa", "gorzka"]):
        return "pl"
    if has_any(t, ["romania", "transylvania", "zmeurica"]):
        return "ro"
    if has_any(t, ["germany", "pfalz", "beerenauslese"]):
        return "de"
    if has_any(t, ["new zealand"]):
        return "nz"
    return "??"


def cls(t: str) -> str:
    if "docg" in t:
        return "DOCG"
    if "doca" in t:
        return "DOCa"
    if "aoc" in t:
        return "AOC"
    if "dac" in t:
        return "DAC"
    if "igt" in t:
        return "IGT"
    if "igp" in t:
        return "IGP"
    if "dop" in t:
        return "DOP"
    if "doc " in t or t.endswith(" doc"):
        return "DOC"
    if "reserva" in t:
        return "Reserva"
    if "reserve" in t:
        return "Reserve"
    if "erste lage" in t:
        return "Erste Lage"
    if "beerenauslese" in t:
        return "Beerenauslese"
    if "icewine" in t:
        return "Icewine"
    if "cap classique" in t:
        return "Cap Classique"
    return "??"


def abv(t: str, c: str) -> str:
    if "nonalcoholic" in t or "alcohol free" in t or re.search(r"\b0\b", t):
        return "0"
    if c == "s":
        return "12"
    if c == "f":
        return "19.5"
    if c == "d":
        return "8.5"
    if c == "p":
        return "12"
    if any(x in t for x in ["amarone", "reserve", "reserva", "barrique", "grand cru"]):
        return "14"
    if c == "w":
        return "12.5"
    return "13"


def body(t: str, g: str, c: str) -> str:
    if c == "s":
        return "leve"
    if c in {"f", "d"}:
        return "encorpado"
    if any(x in g for x in ["riesling", "sauvignon blanc", "torrontes", "albarino", "gruner veltliner", "sylvaner"]):
        return "leve"
    if any(x in g for x in ["malbec", "cabernet sauvignon", "cabernet franc", "primitivo", "shiraz", "syrah",
                            "plavac mali", "susumaniello", "montepulciano", "negroamaro", "merlot"]):
        return "encorpado"
    if c == "p":
        return "medio"
    return "medio"


def sweet(t: str, c: str) -> str:
    if c == "s":
        return "brut" if "brut nature" not in t else "brut nature"
    if c == "f":
        return "doce"
    if c == "d":
        return "doce"
    if "demi sec" in t or "demi-sec" in t:
        return "demi-sec"
    if "brut nature" in t:
        return "brut nature"
    if "extra brut" in t:
        return "extra brut"
    return "seco"


def pairing(t: str, g: str, c: str) -> str:
    if c == "s":
        return "aperitivo, frutos do mar, sushi"
    if c == "f":
        return "foie gras, queijos azuis, sobremesas"
    if c == "d":
        return "sobremesas, queijos, foie gras"
    if any(x in g for x in ["malbec", "cabernet sauvignon", "cabernet franc", "primitivo", "shiraz", "syrah",
                            "plavac mali", "susumaniello", "montepulciano", "negroamaro", "merlot"]):
        return "carne vermelha, churrasco, massas"
    if any(x in g for x in ["chardonnay", "sauvignon blanc", "torrontes", "albarino", "gruner veltliner", "sylvaner",
                            "pinot grigio", "white blend"]):
        return "peixes, aves, saladas"
    if c == "p":
        return "saladas, peixes, aves"
    return "massas, queijos, carnes"


def strip_wine_noise(t: str) -> str:
    s = norm(t)
    s = re.sub(r"\b(19\d{2}|20\d{2}|nv)\b", " ", s)
    s = re.sub(r"\b(case only|damaged label|magnum|box|pack|packs|bottle|bottles|ltr|lt|cc|kg|gr|g|ml|x|0|05|075|12|15|24)\b", " ", s)
    s = re.sub(r"\b(ecologico|bio|dry|trocken|wine|vino|vinho|vin|white|red|rose|blanc|bianco|branco|sparkling|brut|reserve|reserva|selection|classic|classico|estate grown|limited release|special|winery|wines|producer|bodega|tapiz|vigneti|salento|puglia|mendoza|sicilia|sicily|hvar|croatia|croatian|serra gaucha|douro|tokaji|tokaj|balaklava|ruppersthal|kremstal|valais|edna valley|anderson valley|alto adige|sudtirol|sardinia|sardegna|valpolicella|rioja|navarro|czech|moravia|israel|croatia|hvar|hordoz|grand cru|erste lage|aoc|docg|doc|igt|igp|dop|dac)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_w(text: str, producer=None, wine=None, c=None, g=None, region="??", sub="??", vintage=None, ab=None, cl=None, country=None):
    t = norm(text)
    c = c or color(t)
    g = g or grape(t)
    vintage = vintage or year(t)
    cl = cl or cls(t)
    ab = ab or abv(t, c)
    producer = producer or re.sub(r"\s+", " ", producer_from(text))
    country_code = country if country is not None else globals()["country"](t)
    if wine is None:
        base = strip_wine_noise(text)
        prod_norm = norm(producer)
        if base.startswith(prod_norm):
            base = base[len(prod_norm):].strip()
        wine = base or "??"
    country_code = counry_fix(country_code, text)
    line = f"W|{producer}|{wine}|{country_code}|{c}|{g}|{region}|{sub}|{vintage}|{ab}|{cl}|{body(t, g, c)}|{pairing(t, g, c)}|{sweet(t, c)}"
    key = f"W|{producer}|{wine}|{country_code}|{c}|{g}|{region}|{sub}|{vintage}|{cl}"
    return line, key


def make_s(text: str, producer=None):
    t = norm(text)
    producer = producer or producer_from(text)
    product = t
    prod_norm = norm(producer)
    if product.startswith(prod_norm):
        product = product[len(prod_norm):].strip()
    if not product:
        product = t
    return f"S|{producer}|{product}|{country(t)}", f"S|{producer}|{product}|{country(t)}"


def counry_fix(cn: str, text: str) -> str:
    # Keep a few ambiguous cases conservative.
    t = norm(text)
    if "zolotaya balka" in t:
        return "??"
    if cn == "hu" and "zold vulkan" in t:
        return "hu"
    return cn


def producer_from(text: str) -> str:
    t = norm(text)
    specials = [
        ("zolotaya balka", 2), ("zoltan demeter", 2), ("znovin znojmo", 2), ("znojemsky", 1), ("zoetendal", 1),
        ("zoehlhof", 1), ("zohrer", 1), ("zohlhof", 1), ("zocker", 1), ("zoinos winery", 2), ("zita wines", 2),
        ("zlatan otok", 2), ("zlahtina grand cru", 2), ("zobinger", 1), ("zobbobourg", 1), ("zojosu", 1),
        ("zoilo ruizmateos", 2), ("zisola", 1), ("ziva", 1), ("ziro", 1), ("ziru", 1), ("zirouc", 1),
        ("zizzica", 1), ("zizzolo", 1), ("zom", 1), ("zolo", 1), ("zolla", 1), ("zoldveltelini", 1),
        ("zold veltelini", 2), ("zmora", 1), ("zmeurica", 1), ("zlatna radgona", 2), ("zlatna dolina", 2),
        ("zlatni klub", 2), ("zlatni salasi", 2), ("zlatiborski vrh", 3), ("zlatni pelin", 2), ("zlatni vinjak", 2),
    ]
    for pref, n in specials:
        if t.startswith(pref):
            return pref
    words = t.split()
    if not words:
        return "??"
    if words[0] in WINE_PREFIXES:
        end = 1
        for i in range(1, min(len(words), 6)):
            w = words[i]
            if re.fullmatch(r"(19\d{2}|20\d{2}|nv)", w):
                break
            if w in WINE_TERMS:
                break
            end = i + 1
        return " ".join(words[:end]).strip()
    if len(words) >= 2 and words[0] in {"zoe", "zodiac", "zodiaque", "ziva", "zlatna", "zlatni", "zizania", "zittaa", "zitta", "zola", "zojo"}:
        return " ".join(words[:2])
    return words[0]


def wine_line(text: str, idx: int):
    t = norm(text)
    if t.startswith("zom "):
        if "colecao" in t:
            return parse_w(text, producer="zom", wine=strip_wine_noise(text).replace("zom ", ""), c="r", g="??", region="douro", sub="??")
        if "branco" in t or "white" in t:
            return parse_w(text, producer="zom", wine=strip_wine_noise(text).replace("zom ", ""), c="w", g="??", region="douro", sub="??")
        if "rose" in t:
            return parse_w(text, producer="zom", wine=strip_wine_noise(text).replace("zom ", ""), c="p", g="??", region="douro", sub="??")
        return parse_w(text, producer="zom", region="douro")
    if t.startswith("zoltan demeter"):
        return parse_w(text, producer="zoltan demeter", region="tokaj", country="hu")
    if t.startswith("zolotaya balka"):
        return parse_w(text, producer="zolotaya balka", country="??", region="crimea", sub="balaklava")
    if t.startswith("zolo "):
        return parse_w(text, producer="zolo", country="ar", region="mendoza")
    if t == "zolo":
        return parse_w(text, producer="zolo", country="ar", region="mendoza", wine="zolo")
    if t.startswith("zollers winzergluhwein"):
        return parse_w(text, producer="zollers", country="de", region="??", c="r" if "rot" in t else "w", wine=strip_wine_noise(text).replace("zollers ", ""), cl="??")
    if t.startswith("zoller riesling beerenauslese"):
        return parse_w(text, producer="zoller", country="de", region="??", c="w", g="riesling", cl="Beerenauslese")
    if t.startswith("zolla "):
        return parse_w(text, producer="zolla", country="it", region="puglia", sub="salento")
    if t.startswith("zoli inzolia"):
        return parse_w(text, producer="caruso e minini", wine="inzolia", country="it", c="w", g="inzolia", region="sicilia", sub="??")
    if t.startswith("zoleta vino ecologico"):
        return parse_w(text, producer="zoleta", wine="vino ecologico", country="??", region="??")
    if t.startswith("zoldveltelini") or t.startswith("zold veltelini") or t.startswith("zoldveltelini"):
        return parse_w(text, producer=producer_from(text), country="at", region="??", g="gruner veltliner", c="w")
    if t.startswith("zola "):
        return parse_w(text, producer="zola", country="it", region="puglia")
    if t.startswith("zojosu "):
        return parse_w(text, producer="zojosu", country="it", region="sardegna", g="cannonau")
    if t.startswith("zoinos winery") or t.startswith("zoinos "):
        return parse_w(text, producer="zoinos winery", country="gr", region="epirus")
    if t.startswith("zoilo ruizmateos"):
        return parse_w(text, producer="ruiz mateos", wine="reserva privada", country="es", region="??", cl="Reserva")
    if t.startswith("zohrer "):
        return parse_w(text, producer="zohrer", country="at", region="kremstal")
    if t.startswith("zohlhof "):
        return parse_w(text, producer="zohlhof", country="it", region="alto adige")
    if t.startswith("zocker "):
        return parse_w(text, producer="zocker", country="us", region="edna valley")
    if t.startswith("zoetendal "):
        return parse_w(text, producer="zoetendal", country="za", region="western cape", cl="Cap Classique" if "cap classique" in t else "??")
    if t.startswith("znovin "):
        return parse_w(text, producer="znovin znojmo", country="cz", region="moravia")
    if t.startswith("znojemsky "):
        return parse_w(text, producer="znojemsky", country="cz", region="moravia")
    if t.startswith("zmora "):
        return parse_w(text, producer="zmora", country="il", region="israel")
    if t.startswith("zmeurica"):
        return parse_w(text, producer="zmeurica", country="ro", region="??", c="r")
    if t.startswith("zlatan "):
        return parse_w(text, producer="zlatan otok", country="hr", region="hvar", sub="srednja i juzna dalmacija")
    if t.startswith("zlahtina"):
        return parse_w(text, producer="katunar estate winery", country="hr", region="krk")
    if t.startswith("zitta wines"):
        return parse_w(text, producer="zitta wines", country="au", region="barossa", sub="union street")
    if t.startswith("zisola"):
        return parse_w(text, producer="zisola", country="it", region="sicilia", sub="noto")
    if t.startswith("zirudela"):
        return parse_w(text, producer="zirudela", country="it", region="emilia")
    if t.startswith("ziru "):
        return parse_w(text, producer="ziru", country="it", region="sardegna")
    if t.startswith("zirouc"):
        return parse_w(text, producer="zirouc", country="fr", region="valais")
    if t.startswith("ziro prosecco"):
        return parse_w(text, producer="ziro", country="it", region="veneto", c="s", g="glera", cl="DOC")
    if t.startswith("zizzolo") or t.startswith("zizzica"):
        return parse_w(text, producer=producer_from(text), country="it", region="italia")
    if t.startswith("ziva "):
        return parse_w(text, producer="ziva", country="??", region="??")
    if t.startswith("zodiac ") or t.startswith("zodiaque "):
        return parse_w(text, producer=producer_from(text), country="??", region="??")
    if t.startswith("zobinger "):
        return parse_w(text, producer="zobinger", country="at", region="kremstal")
    if t.startswith("zobbobourg"):
        return parse_w(text, producer="zobbobourg", country="fr", region="??")
    if t.startswith("zofie "):
        return parse_w(text, producer="zofie", country="??", region="??")
    if t.startswith("zola winemakers selection"):
        return parse_w(text, producer="zola", country="za", region="??", c="w", g="white blend")
    if t.startswith("zola primitivo"):
        return parse_w(text, producer="zola", country="it", region="puglia", g="primitivo")
    if t.startswith("zoe ") or t.startswith("zoehlhof "):
        return parse_w(text, producer=producer_from(text), country="??", region="??")
    if t.startswith("zobl "):
        return parse_w(text, producer="zobl", country="it", region="alto adige", g="lagrein")
    if t.startswith("zispa agave wine"):
        return parse_w(text, producer="zispa", country="??", region="??")
    if t.startswith("zold vulkan"):
        return parse_w(text, producer="zold vulkan", country="hu", region="??", c="w")
    if t.startswith("zolo signature") or t.startswith("zolo reserve") or t.startswith("zolo reserva") or t.startswith("zolo classic") or t.startswith("zolo sauvignon") or t.startswith("zolo cabernet") or t.startswith("zolo malbec") or t.startswith("zolo chardonnay") or t.startswith("zolo torrontes") or t.startswith("zolo black") or t.startswith("zolo white") or t.startswith("zolo red") or t.startswith("zolo petit verdot"):
        return parse_w(text, producer="zolo", country="ar", region="mendoza")
    return parse_w(text)


# Explicit non-wine and spirit overrides where generic heuristics are noisy.
def classify_item(idx: int, text: str):
    t = norm(text)

    if has_any(t, ["zolotoi koreshok", "shipovnik", "dissolving", "extract", "bitter extract", "chicur"]):
        return "X", f"X|{t}"

    # non-wine products / UI / food / accessories
    if has_any(t, ["zobrazit ", "zjistit ", "zoeken ", "znovu skladem", "ziuta wedrowniczka", "zoldsegleves", "zoldsegkremleves", "zoldseges kuszkusz", "zoldmandula lekvar", "zoldkagylo", "zoldfuszeres barnarizs", "zoldborso kremleves", "zoldborso csiraztatasra", "zoldbors egesz", "zoldbolt ", "zoldbananliszt", "zoldalma szorp", "zold ugar", "zold trio", "zold takaro", "zold szinu labirintus", "zold szappanvirag", "zold olajbogyokrem", "zold olajbogyok ", "zold olajbogyo", "zold mintas ", "zold lencse", "zold fluorit", "zold fem terepjaro", "zold db schmitt", "zold bors egesz", "zold alma formaju", "zold 2020", "zold 2019", "zolita ", "zolfo ", "zollner ", "zoetwaren", "zoethout infusie", "zoete olijven", "zoete dropmix", "zoete aardappel", "zoes nonpareils", "zoetwaren", "zoet brievenbuspakket", "zoet hartig", "zoet dessert", "zografos slim line", "zoglos ", "zogu", "zogi ", "zoku ", "zokni ", "zola winemakers selection white blend 125", "zolda", "zoldike zenit napoj bezalkoholowy z winogron", "zold arpa", "zoldbors", "zold olajbogyok citrommal", "zold olajbogyo es mandula krem", "ziwi peak", "zipthrough hoodie", "zipprix", "zippo ", "zippo wick", "zippo white matte", "zippo vip", "zippo vintage", "zippo venetian", "zippo underwater", "zippo world map", "zippo woodchuck", "zippo wolf", "zippo windy", "zippo tobacco pouch", "zippo the light", "zippo teal", "zippo tattoo", "zippo steampunk", "zippo stamped", "zippo spider", "zippo spade", "zippo solid brass", "zippo slim", "zippo skull", "zippo silver", "zippo shark", "zippo scroll", "zippo script", "zippo scream", "zippo scorpion", "zippo scallops", "zippo satin chrome", "zippo rusty", "zippo running horse", "zippo royal flush", "zippo rose gold", "zippo ring", "zippo resting", "zippo regular street", "zippo reg "]):
        # let obvious wine items through if they have wine keywords
        if not has_any(t, ["wine", "vino", "vinho", "malbec", "cabernet", "merlot", "chardonnay", "sauvignon", "riesling", "prosecco", "brut", "rose", "rosato", "sparkling", "secco", "pinot", "syrah", "shiraz", "tempranillo", "zinfandel", "torrontes", "primitivo", "susumaniello"]):
            return "X", f"X|{t}"

    c = classify_type(t)
    if c == "X":
        return "X", f"X|{t}"
    if c == "S":
        prod = producer_from(text)
        return make_s(text, producer=prod)
    return wine_line(text, idx)


# Duplicate tracking
seen = {}
out_lines = []
for idx, text in items:
    val, key = classify_item(idx, text)
    if key in seen:
        out_lines.append(f"={seen[key]}")
    else:
        seen[key] = idx
        out_lines.append(val)

OUT.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
print(f"written {len(out_lines)} lines to {OUT}")
