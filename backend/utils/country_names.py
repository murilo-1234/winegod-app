"""Modulo central de paises — fonte unica de verdade para ISO, nomes e aliases.

Tres capacidades:
  iso_to_name(code)  -> "fr" => "Franca"
  text_to_iso(text)  -> "France" | "Franca" | "franca" | "fr" => "fr"
  is_country(text)   -> True/False (substitui _KNOWN_COUNTRIES de resolver.py)
"""

import unicodedata

# ──────────────────────────────────────────────────────────────────────
# ISO 3166-1 alpha-2 → Nome PT-BR
# Cobre todos os ~84 codigos que existem na tabela wines.
# ──────────────────────────────────────────────────────────────────────

_ISO_TO_NAME = {
    "ad": "Andorra",
    "al": "Albânia",
    "am": "Armênia",
    "ar": "Argentina",
    "at": "Áustria",
    "au": "Austrália",
    "az": "Azerbaijão",
    "ba": "Bósnia-Herzegovina",
    "be": "Bélgica",
    "bg": "Bulgária",
    "bo": "Bolívia",
    "br": "Brasil",
    "ca": "Canadá",
    "ch": "Suíça",
    "cl": "Chile",
    "cn": "China",
    "co": "Colômbia",
    "cr": "Costa Rica",
    "cy": "Chipre",
    "cz": "República Tcheca",
    "de": "Alemanha",
    "dk": "Dinamarca",
    "dz": "Argélia",
    "ec": "Equador",
    "ee": "Estônia",
    "eg": "Egito",
    "es": "Espanha",
    "et": "Etiópia",
    "fi": "Finlândia",
    "fr": "França",
    "gb": "Reino Unido",
    "ge": "Geórgia",
    "gr": "Grécia",
    "hr": "Croácia",
    "ht": "Haiti",
    "hu": "Hungria",
    "id": "Indonésia",
    "ie": "Irlanda",
    "il": "Israel",
    "in": "Índia",
    "ir": "Irã",
    "it": "Itália",
    "jp": "Japão",
    "ke": "Quênia",
    "kr": "Coreia do Sul",
    "lb": "Líbano",
    "lt": "Lituânia",
    "lu": "Luxemburgo",
    "lv": "Letônia",
    "ma": "Marrocos",
    "md": "Moldávia",
    "me": "Montenegro",
    "mk": "Macedônia do Norte",
    "mt": "Malta",
    "mu": "Ilhas Maurício",
    "mx": "México",
    "na": "Namíbia",
    "nl": "Holanda",
    "no": "Noruega",
    "np": "Nepal",
    "nz": "Nova Zelândia",
    "pe": "Peru",
    "ph": "Filipinas",
    "pl": "Polônia",
    "ps": "Palestina",
    "pt": "Portugal",
    "py": "Paraguai",
    "ro": "Romênia",
    "rs": "Sérvia",
    "ru": "Rússia",
    "sa": "Arábia Saudita",
    "se": "Suécia",
    "sg": "Singapura",
    "si": "Eslovênia",
    "sk": "Eslováquia",
    "sy": "Síria",
    "th": "Tailândia",
    "tn": "Tunísia",
    "tr": "Turquia",
    "tw": "Taiwan",
    "ua": "Ucrânia",
    "us": "Estados Unidos",
    "uy": "Uruguai",
    "uz": "Uzbequistão",
    "ve": "Venezuela",
    "vn": "Vietnã",
    "xk": "Kosovo",
    "za": "África do Sul",
}

# ──────────────────────────────────────────────────────────────────────
# Aliases em ingles e variantes comuns → ISO
# Usados pelo text_to_iso() para normalizar entrada livre.
# ──────────────────────────────────────────────────────────────────────

_ENGLISH_ALIASES = {
    "albania": "al",
    "algeria": "dz",
    "andorra": "ad",
    "argentina": "ar",
    "armenia": "am",
    "australia": "au",
    "austria": "at",
    "azerbaijan": "az",
    "belgium": "be",
    "bolivia": "bo",
    "bosnia": "ba",
    "bosnia and herzegovina": "ba",
    "bosnia-herzegovina": "ba",
    "brazil": "br",
    "brasil": "br",
    "bulgaria": "bg",
    "canada": "ca",
    "chile": "cl",
    "china": "cn",
    "colombia": "co",
    "costa rica": "cr",
    "croatia": "hr",
    "cyprus": "cy",
    "czech republic": "cz",
    "czechia": "cz",
    "denmark": "dk",
    "dominican republic": "do",
    "ecuador": "ec",
    "egypt": "eg",
    "england": "gb",
    "estonia": "ee",
    "ethiopia": "et",
    "finland": "fi",
    "france": "fr",
    "georgia": "ge",
    "germany": "de",
    "greece": "gr",
    "haiti": "ht",
    "holland": "nl",
    "hungary": "hu",
    "india": "in",
    "indonesia": "id",
    "iran": "ir",
    "ireland": "ie",
    "israel": "il",
    "italy": "it",
    "japan": "jp",
    "kenya": "ke",
    "kosovo": "xk",
    "latvia": "lv",
    "lebanon": "lb",
    "lithuania": "lt",
    "luxembourg": "lu",
    "malta": "mt",
    "mauritius": "mu",
    "macedonia": "mk",
    "north macedonia": "mk",
    "mexico": "mx",
    "moldova": "md",
    "montenegro": "me",
    "morocco": "ma",
    "namibia": "na",
    "nepal": "np",
    "netherlands": "nl",
    "new zealand": "nz",
    "norway": "no",
    "palestine": "ps",
    "state of palestine": "ps",
    "paraguay": "py",
    "peru": "pe",
    "philippines": "ph",
    "poland": "pl",
    "portugal": "pt",
    "romania": "ro",
    "russia": "ru",
    "saudi arabia": "sa",
    "serbia": "rs",
    "singapore": "sg",
    "slovakia": "sk",
    "slovenia": "si",
    "south africa": "za",
    "south korea": "kr",
    "spain": "es",
    "sweden": "se",
    "switzerland": "ch",
    "syria": "sy",
    "taiwan": "tw",
    "thailand": "th",
    "tunisia": "tn",
    "turkey": "tr",
    "turkiye": "tr",
    "ukraine": "ua",
    "united kingdom": "gb",
    "united states": "us",
    "united states of america": "us",
    "uk": "gb",
    "usa": "us",
    "uruguay": "uy",
    "uzbekistan": "uz",
    "venezuela": "ve",
    "vietnam": "vn",
}


# ──────────────────────────────────────────────────────────────────────
# Lookup table completa — construida uma vez no import.
# Chave = texto normalizado (lowercase, sem acentos).
# Valor = codigo ISO.
# ──────────────────────────────────────────────────────────────────────

def _strip_accents(text):
    """Remove acentos de uma string. 'França' -> 'franca'."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _build_lookup():
    """Constroi tabela de lookup completa a partir de todas as fontes."""
    table = {}

    # 1. ISO codes diretos ("fr" -> "fr")
    for code in _ISO_TO_NAME:
        table[code] = code

    # 2. Nomes PT-BR lowercase ("franca" -> "fr", "italia" -> "it")
    for code, name in _ISO_TO_NAME.items():
        low = name.lower()
        table[low] = code
        # Sem acento ("franca" -> "fr")
        stripped = _strip_accents(low)
        if stripped != low:
            table[stripped] = code

    # 3. Aliases em ingles ("france" -> "fr", "italy" -> "it")
    for alias, code in _ENGLISH_ALIASES.items():
        table[alias] = code
        stripped = _strip_accents(alias)
        if stripped != alias:
            table[stripped] = code

    return table


_LOOKUP = _build_lookup()


# ──────────────────────────────────────────────────────────────────────
# API publica
# ──────────────────────────────────────────────────────────────────────

def iso_to_name(code):
    """Converte codigo ISO para nome PT-BR de exibicao.

    >>> iso_to_name("fr")
    'França'
    >>> iso_to_name("FR")
    'França'
    >>> iso_to_name(None)
    ''
    >>> iso_to_name("xx")
    'XX'
    """
    if not code:
        return ""
    return _ISO_TO_NAME.get(code.lower(), code.upper())


def text_to_iso(text):
    """Converte texto livre para codigo ISO.

    Aceita: ISO ("fr"), nome PT-BR ("Franca"), nome EN ("France"),
    sem acento ("franca"), case insensitive.

    >>> text_to_iso("France")
    'fr'
    >>> text_to_iso("França")
    'fr'
    >>> text_to_iso("franca")
    'fr'
    >>> text_to_iso("fr")
    'fr'
    >>> text_to_iso("south africa")
    'za'
    >>> text_to_iso(None) is None
    True
    >>> text_to_iso("Westeros") is None
    True
    """
    if not text:
        return None
    key = _strip_accents(text.strip().lower())
    return _LOOKUP.get(key)


def is_country(text):
    """Verifica se o texto e um nome de pais reconhecido.

    >>> is_country("France")
    True
    >>> is_country("Bordeaux")
    False
    >>> is_country("fr")
    True
    """
    return text_to_iso(text) is not None
