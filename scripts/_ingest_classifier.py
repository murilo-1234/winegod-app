"""Classificador deterministico de prontidao para ingestao.

Fase 1 do fluxo `WINEGOD_PRE_INGEST_ROUTER` (ver `reports/WINEGOD_PRE_INGEST_ROUTER_ANALISE.md`).

Funcao pura:
    classify(item: dict) -> tuple[status, reasons]

onde:
    status ∈ {"ready", "needs_enrichment", "not_wine", "uncertain"}
    reasons ∈ list[str]

Regras (ordem de avaliacao):

1. Filtro deterministico NOT_WINE via `pre_ingest_filter.should_skip_wine`.
   Se bloqueado -> status="not_wine".

2. READY requer TODAS:
   - nome normalizado >= 8 chars
   - produtor normalizado >= 3 chars
   - nome NAO e so termos genericos
   - pelo menos um de: pais, regiao, sub_regiao, ean_gtin

3. NEEDS_ENRICHMENT: nao e ready, mas tem ancora util (nome forte,
   produtor conhecido, ean, descricao longa, pistas de uva/regiao).

4. UNCERTAIN: sem ancora util para Gemini resolver sem inventar.

Sem banco, sem HTTP, sem Gemini, sem side effects.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pre_ingest_filter import should_skip_wine  # noqa: E402


# Termos genericos que, quando cobrem todo o nome, indicam identidade fraca.
GENERIC_TERMS = {
    "red", "white", "blanc", "blanco", "bianco", "rouge", "rosso",
    "rose", "rosé", "blend", "reserva", "reserve", "brut", "cuvee",
    "cuvée", "house", "wine", "vino", "vin", "wein", "sparkling",
    # comuns em rotulos mas sem identidade por si so
    "tinto", "branco", "rosado",
}

# Padroes tipicos de uva / produtor / topônimo — sinal de nao-generico.
# Nao e exaustivo; qualquer token fora de GENERIC_TERMS ja conta como
# nao-generico. Esta lista e so referencia.
_NON_GENERIC_EXAMPLES = {
    "malbec", "merlot", "cabernet", "sauvignon", "chardonnay", "pinot",
    "syrah", "shiraz", "tempranillo", "riesling", "carmenere",
    "sangiovese", "nebbiolo", "grenache", "tannat", "margaux",
}

_TOKEN_RE = re.compile(r"[a-z0-9']+")


def _strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _normalize(s: str | None) -> str:
    """Lowercase + ASCII fold + colapsa espacos. Nao remove pontuacao."""
    if not s:
        return ""
    return _strip_accents(str(s)).lower().strip()


def _norm_len(s: str | None) -> int:
    """Tamanho do texto normalizado sem contar espacos de borda."""
    return len(_normalize(s))


def _clean(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() == "null":
            return None
        return s
    return str(v).strip() or None


def _is_generic_name(nome: str | None) -> bool:
    """Nome generico = composto APENAS por termos genericos (ou safra).

    Regras:
      - normaliza, tokeniza em [a-z0-9']+
      - remove tokens curtos (<= 2) e tokens que sao ano (4 digitos 1900-2099)
      - se sobra lista vazia -> generico (ex: nome so tinha numero)
      - se todos os tokens restantes estao em GENERIC_TERMS -> generico
      - senao -> nao-generico
    """
    norm = _normalize(nome)
    if not norm:
        return True
    tokens = _TOKEN_RE.findall(norm)
    meaningful: list[str] = []
    for tok in tokens:
        if len(tok) <= 2:
            continue
        if tok.isdigit() and len(tok) == 4 and 1900 <= int(tok) <= 2099:
            # safra — ignora pra decisao
            continue
        meaningful.append(tok)
    if not meaningful:
        return True
    return all(tok in GENERIC_TERMS for tok in meaningful)


def _has_geo_anchor(item: dict) -> bool:
    return any(_clean(item.get(k)) for k in ("pais", "regiao", "sub_regiao", "ean_gtin"))


def _has_strong_name(item: dict) -> bool:
    """Nome util como ancora de enrichment mesmo sem produtor.

    Criterio: nome com >= 3 tokens significativos E nao-generico.
    """
    nome = _clean(item.get("nome"))
    if not nome:
        return False
    norm = _normalize(nome)
    tokens = _TOKEN_RE.findall(norm)
    meaningful = [
        t for t in tokens
        if len(t) > 2 and not (t.isdigit() and len(t) == 4)
    ]
    if len(meaningful) < 3:
        return False
    return not _is_generic_name(nome)


def _has_long_description(item: dict) -> bool:
    desc = _clean(item.get("descricao"))
    return bool(desc) and len(desc) >= 100


def _has_grape_hint(item: dict) -> bool:
    """Alguma pista de uva (campo uvas OU nome contem uva conhecida)."""
    if _clean(item.get("uvas")):
        return True
    norm = _normalize(item.get("nome"))
    tokens = set(_TOKEN_RE.findall(norm))
    return bool(tokens & _NON_GENERIC_EXAMPLES)


def classify(item: dict) -> tuple[str, list[str]]:
    """Classifica um item de ingestao em {ready, needs_enrichment, not_wine, uncertain}.

    Args:
        item: dict com campos tipicos: nome, produtor, safra, pais, regiao,
            sub_regiao, uvas, ean_gtin, teor_alcoolico, volume_ml, descricao,
            harmonizacao, preco_min, preco_max, moeda, imagem_url.

    Returns:
        (status, reasons) — reasons e sempre lista de strings.
    """
    reasons: list[str] = []

    if not isinstance(item, dict):
        return "uncertain", ["item_nao_e_dict"]

    nome = _clean(item.get("nome"))
    produtor = _clean(item.get("produtor"))

    # -------- 1. NOT_WINE deterministico --------
    # "nome_vazio_ou_curto" nao e descarte — vira uncertain no fluxo bifurcado
    # (pode ter EAN/produtor que salvem). Outros motivos sao descarte real.
    skip, filter_reason = should_skip_wine(nome or "", produtor or "")
    if skip and filter_reason != "nome_vazio_ou_curto":
        return "not_wine", [f"pre_ingest_filter={filter_reason}"]

    # -------- 2. Ancoras minimas pra ancorar decisao --------
    nome_len = _norm_len(nome)
    produtor_len = _norm_len(produtor)
    has_nome = nome is not None and nome_len >= 3
    has_ean = bool(_clean(item.get("ean_gtin")))
    has_geo = _has_geo_anchor(item)
    has_strong_nome = _has_strong_name(item)
    has_long_desc = _has_long_description(item)
    has_grape = _has_grape_hint(item)
    has_produtor = produtor is not None and produtor_len >= 3

    # -------- 3. READY (todas juntas) --------
    ready_checks = {
        "nome_len_ge_8": nome_len >= 8,
        "produtor_len_ge_3": produtor_len >= 3,
        "nome_nao_generico": not _is_generic_name(nome),
        "tem_pais_regiao_ou_ean": has_geo,
    }
    if all(ready_checks.values()):
        reasons.append("ready_all_conditions_met")
        return "ready", reasons

    # Anota por que nao ficou ready (para needs_enrichment/uncertain)
    for name, ok in ready_checks.items():
        if not ok:
            reasons.append(f"nao_ready:{name}")

    # -------- 4. UNCERTAIN duro (sem ancora pra Gemini) --------
    # 4.1 nome + produtor ambos vazios E sem EAN
    if not has_nome and not has_produtor and not has_ean:
        reasons.append("uncertain:nome_e_produtor_vazios")
        return "uncertain", reasons

    # 4.2 nome muito curto (< 8) e sem EAN e sem produtor
    if nome_len < 8 and not has_ean and not has_produtor:
        reasons.append("uncertain:nome_curto_sem_ean_sem_produtor")
        return "uncertain", reasons

    # 4.3 nome generico sem produtor e sem EAN -> Gemini inventaria
    if has_nome and _is_generic_name(nome) and not has_produtor and not has_ean:
        reasons.append("uncertain:nome_generico_sem_produtor_sem_ean")
        return "uncertain", reasons

    # -------- 5. NEEDS_ENRICHMENT: tem ancora util --------
    enrich_anchors: list[str] = []
    if has_strong_nome and not has_produtor:
        enrich_anchors.append("ancora:nome_forte_sem_produtor")
    if has_produtor and not has_geo:
        enrich_anchors.append("ancora:produtor_sem_pais_regiao_ean")
    if has_ean and nome_len < 8:
        enrich_anchors.append("ancora:ean_com_nome_fraco")
    if has_long_desc:
        enrich_anchors.append("ancora:descricao_longa")
    if has_grape and (not has_produtor or not has_geo):
        enrich_anchors.append("ancora:pista_uva_ou_regiao")
    if has_produtor and has_nome and _is_generic_name(nome):
        # produtor salva o nome generico
        enrich_anchors.append("ancora:produtor_compensa_nome_generico")

    if enrich_anchors:
        reasons.extend(enrich_anchors)
        return "needs_enrichment", reasons

    # -------- 6. Fallback: uncertain --------
    reasons.append("uncertain:sem_ancora_util")
    return "uncertain", reasons


__all__ = ["classify", "GENERIC_TERMS"]
