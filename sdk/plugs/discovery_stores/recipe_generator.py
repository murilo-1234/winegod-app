"""Deterministic recipe generator - staging only.

Converte um `recipe_candidate` (hint do discovery) + amostra HTML/JSON
em um `store_recipe` candidato executavel. NAO chama LLM externo; usa
heuristicas deterministicas:

  - JSON-LD `Product` (schema.org)
  - OpenGraph `product.*`
  - meta tags comuns
  - regex de paginacao
  - extracao de preco e moeda
  - inferencia de moeda por TLD
  - safra por nome do produto
  - produtor por marca/brand

Nunca acessa a rede. O `sample_html` e `sample_json` sao passados pelo
chamador.

Escreve o candidato em `reports/data_ops_recipe_candidates/`.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
CANDIDATES_DIR = REPO_ROOT / "reports" / "data_ops_recipe_candidates"


_TLD_CURRENCY = {
    "br": "BRL",
    "ar": "ARS",
    "cl": "CLP",
    "uy": "UYU",
    "pt": "EUR",
    "es": "EUR",
    "fr": "EUR",
    "it": "EUR",
    "de": "EUR",
    "uk": "GBP",
    "co": "COP",
    "mx": "MXN",
    "us": "USD",
    "ca": "CAD",
}

_PRICE_REGEXES = [
    # R$ 1.234,56  ou  R$1234,56  ou  R$ 99
    (re.compile(r"R\$\s*([0-9\.]+,?[0-9]{0,2})"), "BRL"),
    # $ 1,234.56  ou  $99.99
    (re.compile(r"\$\s*([0-9,]+\.?[0-9]{0,2})"), "USD"),
    # 1.234,56 EUR
    (re.compile(r"([0-9\.]+,?[0-9]{0,2})\s*EUR", re.IGNORECASE), "EUR"),
    # 1,234.56 USD
    (re.compile(r"([0-9,]+\.?[0-9]{0,2})\s*USD", re.IGNORECASE), "USD"),
]

_PAGINATION_PATTERNS = [
    re.compile(r"[?&]page=\d+"),
    re.compile(r"[?&]p=\d+"),
    re.compile(r"/page/\d+"),
    re.compile(r"[?&]offset=\d+"),
]

_VINTAGE_RE = re.compile(r"\b(19[5-9][0-9]|20[0-2][0-9])\b")
_BRAND_RE = re.compile(
    r'<meta[^>]+property=["\']og:brand["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_OG_PRODUCT_RE = re.compile(
    r'<meta[^>]+property=["\']og:type["\'][^>]+content=["\']product[^"\']*["\']',
    re.IGNORECASE,
)


@dataclass
class RecipeCandidate:
    domain: str
    platform: str | None
    confidence: float
    signals: dict[str, Any]
    proposed_recipe: dict[str, Any]
    needs_manual_review: bool
    generated_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _contains_jsonld_product(sample_html: str) -> bool:
    for block in _JSONLD_RE.findall(sample_html or ""):
        try:
            data = json.loads(block)
        except Exception:
            continue
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict) and entry.get("@type") in ("Product", "ProductGroup"):
                    return True
        elif isinstance(data, dict):
            if data.get("@type") in ("Product", "ProductGroup"):
                return True
            graph = data.get("@graph")
            if isinstance(graph, list):
                for g in graph:
                    if isinstance(g, dict) and g.get("@type") in ("Product", "ProductGroup"):
                        return True
    return False


def _contains_og_product(sample_html: str) -> bool:
    return bool(_OG_PRODUCT_RE.search(sample_html or ""))


def infer_currency_from_tld(domain: str | None) -> str | None:
    if not domain:
        return None
    parts = domain.lower().split(".")
    if len(parts) >= 2:
        last = parts[-1]
        prev = parts[-2]
        if last == "br":
            return "BRL"
        if prev == "co" and last in {"uk"}:
            return "GBP"
        return _TLD_CURRENCY.get(last)
    return None


def extract_price_signal(sample_html: str, domain: str | None) -> dict[str, Any] | None:
    for regex, currency in _PRICE_REGEXES:
        m = regex.search(sample_html or "")
        if m:
            raw = m.group(1)
            return {"raw": raw, "currency": currency, "pattern": regex.pattern}
    tld_currency = infer_currency_from_tld(domain)
    if tld_currency:
        return {"raw": None, "currency": tld_currency, "pattern": "tld_fallback"}
    return None


def detect_pagination(url: str | None) -> str | None:
    if not url:
        return None
    for pat in _PAGINATION_PATTERNS:
        if pat.search(url):
            return pat.pattern
    return None


def extract_vintage_from_name(name: str | None) -> int | None:
    if not name:
        return None
    m = _VINTAGE_RE.search(name)
    if m:
        return int(m.group(1))
    return None


def extract_producer_from_html(sample_html: str) -> str | None:
    m = _BRAND_RE.search(sample_html or "")
    return m.group(1).strip() if m else None


def generate_recipe(
    *,
    domain: str,
    platform: str | None,
    sample_html: str | None,
    sample_url: str | None,
    sample_product_name: str | None = None,
    recipe_candidate_hint: dict[str, Any] | None = None,
) -> RecipeCandidate:
    sample_html = sample_html or ""
    signals: dict[str, Any] = {
        "jsonld_product": _contains_jsonld_product(sample_html),
        "og_product": _contains_og_product(sample_html),
        "pagination_detected": detect_pagination(sample_url),
        "price_signal": extract_price_signal(sample_html, domain),
        "vintage": extract_vintage_from_name(sample_product_name),
        "producer_from_og_brand": extract_producer_from_html(sample_html),
    }

    # Confidence model:
    # - JSON-LD Product -> +0.5
    # - OpenGraph product -> +0.2
    # - pagination detected -> +0.1
    # - price signal with explicit currency (not tld_fallback) -> +0.1
    # - vintage found -> +0.05
    # - producer from brand -> +0.05
    confidence = 0.0
    if signals["jsonld_product"]:
        confidence += 0.5
    if signals["og_product"]:
        confidence += 0.2
    if signals["pagination_detected"]:
        confidence += 0.1
    if signals["price_signal"] and signals["price_signal"].get("pattern") != "tld_fallback":
        confidence += 0.1
    if signals["vintage"]:
        confidence += 0.05
    if signals["producer_from_og_brand"]:
        confidence += 0.05
    confidence = round(min(confidence, 1.0), 3)

    needs_manual_review = confidence < 0.4

    hint = recipe_candidate_hint or {}
    proposed = {
        "plataforma": platform or hint.get("plataforma") or "unknown",
        "metodo_listagem": (
            "jsonld" if signals["jsonld_product"]
            else ("opengraph" if signals["og_product"]
                  else (hint.get("metodo_listagem") or "sitemap"))
        ),
        "metodo_extracao": hint.get("metodo_extracao") or "html",
        "usa_playwright": bool(hint.get("usa_playwright", not signals["jsonld_product"])),
        "anti_bot": hint.get("anti_bot") or "basic",
        "url_sitemap": hint.get("url_sitemap"),
        "pagination_pattern": signals["pagination_detected"],
        "moeda_default": (signals["price_signal"] or {}).get("currency") or infer_currency_from_tld(domain),
        "needs_manual_review": needs_manual_review,
    }

    return RecipeCandidate(
        domain=domain,
        platform=platform,
        confidence=confidence,
        signals=signals,
        proposed_recipe=proposed,
        needs_manual_review=needs_manual_review,
    )


def persist_candidate(candidate: RecipeCandidate, *, timestamp: str | None = None) -> Path:
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = CANDIDATES_DIR / f"{ts}_{candidate.domain.replace('.', '_')}.json"
    path.write_text(
        json.dumps(candidate.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


__all__ = [
    "RecipeCandidate",
    "generate_recipe",
    "persist_candidate",
    "infer_currency_from_tld",
    "extract_price_signal",
    "detect_pagination",
    "extract_vintage_from_name",
    "extract_producer_from_html",
    "CANDIDATES_DIR",
]
