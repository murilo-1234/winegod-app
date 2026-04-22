"""
Pre-ingest filter para novos wines (scraping Natura, e-commerces, etc.)

FONTE UNICA DE VERDADE (DQ V3 Escopo 5 -- 2026-04-21)
=====================================================

Este modulo e o **unico** ponto de entrada oficial para decidir se um
candidato e NOT_WINE no repo vivo `C:\\winegod-app`. Todos os pipelines
(bulk_ingest, new_wines, import_render_z) devem importar EXATAMENTE
este modulo:

    from pre_ingest_filter import should_skip_wine

Por baixo ele delega para `scripts/wine_filter.classify_product` (fonte
da regex multilingua consolidada). Nao importe `wine_filter` diretamente
de outros lugares nem sincronize com copias legadas (incluindo
`C:\\winegod\\utils\\wine_filter.py`, que esta morto).

Uso tipico no pipeline:

    from pre_ingest_filter import should_skip_wine

    for produto in produtos_do_scraping:
        skip, reason = should_skip_wine(produto["nome"])
        if skip:
            log.info(f"skip {produto['id']}: {reason}")
            continue
        # passou: inserir no banco
        db.insert_wine(produto)

Retorna (True, motivo) se o produto NAO e vinho.
Retorna (False, None) se parece ser vinho.

Combina:
  - wine_filter.py (~400 termos multilingua em regex)
  - regras procedurais:
      * ABV fora 10-15%
      * volume nao-padrao (!=750ml/0.75L/1.5L/375ml/500ml/3L/75cl)
      * gramatura (\\d+g, \\d+kg) -- vinho nao se pesa
      * data com sufixo (20th, 21st, 2nd, 3rd) -- e evento
      * case/caisse + numero 2-96 -- e kit
"""
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wine_filter import classify_product  # noqa


ABV_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%\s*\.?\s*abv\b", re.I)
VOL_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(ml|cl|l|oz)\b", re.I)
GRAMAS_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:g|gr|grs|kg|gram|gramm|grams|grammes)\b", re.I)
DATE_TH_RE = re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.I)
CASE_NUM_RE1 = re.compile(r"\b(?:case|caisse)\s*(?:of|with|,|:)?\s*\(?\s*(\d+)\b", re.I)
CASE_NUM_RE2 = re.compile(r"\b(\d+)\s*[-x×]?\s*(?:bottles?|btls?|bot)?\s*[-x×]?\s*\b(?:case|caisse)\b", re.I)
CASE_BASE = re.compile(r"\b(?:case|caisse)\b", re.I)

WINE_VOLUMES = {
    "750ml", "750 ml",
    "0.75l", "0,75l", "0.75 l", "0,75 l",
    "75cl", "75 cl",
    "1.5l", "1,5l", "1.5 l", "1,5 l",
    "375ml", "375 ml",
    "500ml", "500 ml",
    "3l", "3 l",
    "1l", "1 l", "1000ml", "1000 ml",
}


def strip_accents(s):
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def should_skip_wine(nome: str, produtor: str = "") -> tuple[bool, str | None]:
    """
    Retorna (True, motivo) se produto e NOT_WINE.
    Retorna (False, None) se parece vinho.

    Aplica todas as regras consolidadas em 2026-04-15.
    """
    if not nome or len(nome.strip()) < 3:
        return True, "nome_vazio_ou_curto"

    # 1. wine_filter (regex multilingua + produtor, fonte = catalogo 2026-04-15)
    combined = " ".join(part for part in (nome, produtor) if part)
    cls, cat = classify_product(combined)
    if cls == "not_wine":
        return True, f"wine_filter={cat}"

    # Normalize for procedural checks
    nl = strip_accents((nome or "") + " " + (produtor or "")).lower()

    # 2. ABV fora 10-15%
    for m in ABV_RE.finditer(nl):
        try:
            val = float(m.group(1).replace(",", "."))
            if not (10.0 <= val <= 15.0):
                return True, f"abv_fora_10_15={val}%"
        except ValueError:
            pass

    # 3. Volume nao-padrao
    # Nao "aprova" o item por ter volume valido; apenas evita falso bloqueio por volume.
    vol_matches = list(VOL_RE.finditer(nl))
    for m in vol_matches:
        num, unit = m.group(1), m.group(2)
        full = (num + unit).replace(" ", "").lower()
        if full in WINE_VOLUMES:
            continue
        # se e oz mas nao 25.4oz tipico, bloqueia
        if unit == "oz":
            return True, f"volume_oz={full}"
        # ml/cl/l nao-vinho
        return True, f"volume_nao_padrao={full}"

    # 4. Gramatura
    m = GRAMAS_RE.search(nl)
    if m:
        return True, f"gramatura={m.group(0)}"

    # 5. Data com sufixo (20th, 21st, etc)
    m = DATE_TH_RE.search(nl)
    if m:
        return True, f"data_evento={m.group(0)}"

    # 6. Case com numero 2-96
    if CASE_BASE.search(nl):
        for regex in (CASE_NUM_RE1, CASE_NUM_RE2):
            for m in regex.finditer(nl):
                num_str = next((g for g in m.groups() if g), None)
                if not num_str:
                    continue
                try:
                    num = int(num_str)
                    if 2 <= num <= 96:
                        return True, f"case_kit={m.group(0)}"
                except ValueError:
                    pass

    return False, None


if __name__ == "__main__":
    tests = [
        # (nome, esperado_skip)
        ("Château Margaux 2015 Premier Grand Cru", False),
        ("Casillero del Diablo Cabernet Sauvignon 2022 750ml", False),
        ("Penfolds Grange Shiraz 2018", False),
        ("Giacomo Conterno Monfortino Barolo 2015", False),
        # NOT_WINE
        ("Glenmorangie Original 10 Year Old Single Malt", True),
        ("Gift Box Wine Tasting Set 6 Bottles", True),
        ("Magnum Ice Cream Almond 440ml", True),
        ("Rose Water Fee Brothers 4oz", True),
        ("Hoodie Wine Vintage 2024", True),
        ("Caja de Vinos Navidenas 12 unidades", True),
        ("Thursday 20th May Wine Tasting Event", True),
        ("Heineken Beer 355ml Pack of 6", True),
        ("Champagne Dom Pérignon Vintage 2013", False),
        ("Case of 6 Italian Reds", True),
        ("Advent Calendar Wine", True),
    ]
    for nome, expected in tests:
        skip, reason = should_skip_wine(nome)
        status = "OK" if skip == expected else "FAIL"
        print(f"  [{status}] skip={skip:<5} expected={expected:<5}  reason={reason or '-':<25}  {nome}")
