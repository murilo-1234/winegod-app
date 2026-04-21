#!/usr/bin/env python3
"""Fase 4 — enrichment Gemini de items needs_enrichment.

Consome `needs_enrichment.jsonl` gerado pelo `pre_ingest_router.py` e
produz:
  - enriched_ready.jsonl          (mergeados + classificados como ready)
  - enriched_not_wine.jsonl       (Gemini disse not_wine/spirit)
  - enriched_uncertain_review.csv (unknown, sem ancora, sem campos minimos)
  - enriched_summary.md           (contadores + WARNING se > 20% unknown)
  - raw_gemini_response.jsonl     (auditoria: 1 linha por item com parsed_raw)

Seguranca:
  - default NAO chama Gemini — mostra plano e sai (exit 0).
  - exige `--confirm-gemini` pra chamada real (REGRA 6).
  - nao grava no banco (nenhum import de db.connection).
  - nao chama ingest_via_bulk.py --apply.
  - nao imprime GEMINI_API_KEY, DATABASE_URL nem tokens.

Pos-enrichment:
  1. Segundo filtro: kind=not_wine/spirit -> enriched_not_wine.
  2. kind=unknown ou sem produtor/nome pos-merge -> uncertain_review.
  3. kind=wine -> merge campos uteis no item original.
  4. Reclassifica via `_ingest_classifier.classify()`:
     - ready -> enriched_ready.jsonl
     - needs_enrichment/uncertain -> uncertain_review (Gemini nao
       resolveu a ambiguidade).

Uso:
    # Plano-only (sem custo, sem Gemini):
    python scripts/enrich_needs.py \\
        --input reports/ingest_pipeline/<out>/needs_enrichment.jsonl \\
        --source vinhos_brasil_vtex_<ts> \\
        --limit 53

    # Rodar com Gemini real (custo autorizado):
    python scripts/enrich_needs.py \\
        --input ...needs_enrichment.jsonl \\
        --source vinhos_brasil_vtex_<ts> \\
        --limit 53 --confirm-gemini
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent

# O classifier mora no mesmo dir de scripts.
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from _ingest_classifier import classify  # noqa: E402

# Reusar o enrichment_v3 do backend.
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


_MAX_LIMIT_SAFE = 500

_DEFAULT_OUT_DIR = _REPO_ROOT / "reports" / "ingest_pipeline_enriched"

UNCERTAIN_CSV_COLS = [
    "router_index",
    "source",
    "nome_original",
    "produtor_original",
    "nome_enriquecido",
    "produtor_enriquecido",
    "pais_enriquecido",
    "kind",
    "confidence",
    "reasons",
    "raw_json",
]


# ---------- Guardrails de consistencia factual ----------
#
# Regra: Gemini NAO pode contradizer evidencia presente na fonte.
# Se o pais do Gemini bate contra uma pista de URL/descricao ou contra o
# `pais` original, o item vai pra uncertain_review.csv com reason
# `qa_conflict:country_hint_mismatch`.

# Padrao WorldWine e semelhantes: .../vin-XX-<slug>/p
_WORLDWINE_URL_RE = re.compile(r"/vin-([a-z]{2,4})-", re.IGNORECASE)

# Mapa prefixo-URL -> ISO-2. Nota: 'ch'/'chl'/'chil' apontam pra Chile ('cl')
# conforme convencao da WorldWine, embora ISO-2 'ch' seja Suica. Decisao do
# brief: o contexto da fonte prevalece sobre ISO-2 porque o prefixo da URL
# foi escolhido pelo scraper pra mapear pra Chile.
_URL_COUNTRY_HINT = {
    "fr": "fr",
    "es": "es",
    "it": "it",
    "pt": "pt",
    "ar": "ar",
    "ch": "cl", "chl": "cl", "chil": "cl",
    "cl": "cl",
    "uy": "uy", "ur": "uy",
    "us": "us", "usa": "us",
    "au": "au",
    "nz": "nz",
    "za": "za",
    "de": "de",
    "br": "br",
}

# Evidencias textuais de pais/regiao. Curta e conservadora pra evitar FP.
# Match como substring em texto normalizado (lower + sem acentos).
_TEXT_COUNTRY_HINT_RULES: list[tuple[str, str]] = [
    # Franca
    ("vin de france", "fr"),
    ("languedoc", "fr"),
    ("roussillon", "fr"),
    ("bordeaux", "fr"),
    ("bourgogne", "fr"),
    ("burgundy", "fr"),
    ("champagne", "fr"),
    ("rhone", "fr"),
    ("cotes du rhone", "fr"),
    ("loire", "fr"),
    ("alsace", "fr"),
    ("provence", "fr"),
    ("beaujolais", "fr"),
    # Espanha
    ("rioja", "es"),
    ("ribera del duero", "es"),
    ("priorat", "es"),
    ("rias baixas", "es"),
    # Italia
    ("toscana", "it"),
    ("tuscany", "it"),
    ("chianti", "it"),
    ("barolo", "it"),
    ("piemonte", "it"),
    ("veneto", "it"),
    ("sicilia", "it"),
    ("amarone", "it"),
    # Portugal
    ("vinho do porto", "pt"),
    ("douro", "pt"),
    ("vinho verde", "pt"),
    ("alentejo", "pt"),
    # Argentina
    ("mendoza", "ar"),
    # Chile
    ("valle del maule", "cl"),
    ("maipo", "cl"),
    ("colchagua", "cl"),
    ("casablanca", "cl"),
    # Alemanha
    ("mosel", "de"),
    ("rheingau", "de"),
    # EUA
    ("napa valley", "us"),
    ("sonoma county", "us"),
    # Australia / NZ / SA
    ("barossa", "au"),
    ("mclaren vale", "au"),
    ("marlborough", "nz"),
    ("stellenbosch", "za"),
]


def _norm_for_hint(text: str) -> str:
    import unicodedata
    if not text:
        return ""
    s = unicodedata.normalize("NFD", str(text))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


def _extract_country_hint_from_url(url) -> tuple[str | None, str | None]:
    """Retorna (iso_hint, reason) ou (None, None)."""
    if not url:
        return None, None
    m = _WORLDWINE_URL_RE.search(str(url))
    if not m:
        return None, None
    prefix = m.group(1).lower()
    iso = _URL_COUNTRY_HINT.get(prefix)
    if iso:
        return iso, f"url_prefix:vin-{prefix}"
    return None, None


def _extract_country_hint_from_text(text) -> tuple[str | None, str | None]:
    """Procura evidencia textual forte de pais via regioes/expressoes."""
    if not text:
        return None, None
    norm = _norm_for_hint(text)
    if not norm:
        return None, None
    for phrase, iso in _TEXT_COUNTRY_HINT_RULES:
        if phrase in norm:
            return iso, f"text:{phrase.replace(' ', '_')}"
    return None, None


def _collect_source_hints(original: dict) -> list[tuple[str, str]]:
    """Lista ordenada de (iso, reason) de maior pra menor confianca.

    Ordem:
      1. `pais` ja preenchido no item original (evidencia mais forte).
      2. Hint via URL (`url_original` ou `_fonte_original`).
      3. Hint textual em `descricao`, `regiao`, `sub_regiao`, `nome`.
    """
    hints: list[tuple[str, str]] = []

    pais_orig = original.get("pais")
    if isinstance(pais_orig, str):
        iso = pais_orig.strip().lower()
        if len(iso) == 2 and iso.isalpha():
            hints.append((iso, "original_pais"))

    for key in ("url_original", "_fonte_original", "imagem_url"):
        url = original.get(key)
        iso, reason = _extract_country_hint_from_url(url)
        if iso:
            hints.append((iso, reason))
            break  # primeira URL decisiva basta

    for key in ("descricao", "regiao", "sub_regiao", "nome"):
        text = original.get(key)
        iso, reason = _extract_country_hint_from_text(text)
        if iso:
            hints.append((iso, reason))
            break

    return hints


def _detect_country_conflict(original: dict, enriched: dict) -> dict | None:
    """Retorna detalhes do conflito ou None.

    Conflito existe quando:
      - Gemini emite `country_code` nao-vazio,
      - A fonte tem pelo menos um hint de pais,
      - E o hint discorda do Gemini.

    Retorno: {
        "gemini_pais": "cl",
        "source_hint_pais": "fr",
        "source_hint_reason": "url_prefix:vin-fr",
    }
    """
    gemini_iso = _iso2(enriched.get("country_code"))
    if not gemini_iso:
        return None
    hints = _collect_source_hints(original)
    if not hints:
        return None
    # Pega o primeiro hint que discorda — ordenado por confianca.
    for hint_iso, reason in hints:
        if hint_iso != gemini_iso:
            return {
                "gemini_pais": gemini_iso,
                "source_hint_pais": hint_iso,
                "source_hint_reason": reason,
            }
    return None


# ---------- Utils ----------

def _clean(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return str(v)


def _iso2(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    return s if len(s) == 2 and s.isalpha() else None


def _to_jsonl_uvas(grape: str | None) -> str | None:
    if not grape:
        return None
    parts = [p.strip() for p in str(grape).split(",") if p.strip()]
    return json.dumps(parts, ensure_ascii=False) if parts else None


def _vintage_to_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if len(s) == 4 and s.isdigit() and 1900 <= int(s) <= 2099:
        return s
    return None


def _abv_to_float(v):
    if v is None:
        return None
    try:
        s = str(v).replace("%", "").replace(",", ".").strip()
        f = float(s)
        if 0 < f < 30:
            return f
    except (ValueError, TypeError):
        pass
    return None


_STYLE_MAP = {
    "red": "tinto", "tinto": "tinto", "R": "tinto",
    "white": "branco", "branco": "branco", "W": "branco",
    "rose": "rose", "rosé": "rose", "P": "rose",
    "sparkling": "espumante", "espumante": "espumante", "S": "espumante",
    "fortified": "fortificado", "fortificado": "fortificado", "F": "fortificado",
    "sweet": "sobremesa", "sobremesa": "sobremesa", "D": "sobremesa",
}


def _map_style(value) -> str | None:
    if not value:
        return None
    key = str(value).strip().lower()
    return _STYLE_MAP.get(key)


# ---------- Conversao payload -> formato OCR ----------

def item_to_ocr(item: dict) -> dict:
    """Converte item do `needs_enrichment.jsonl` pro formato esperado
    pelo `enrichment_v3.enrich_items_v3`.
    """
    nome = _clean(item.get("nome"))
    produtor = _clean(item.get("produtor"))
    safra = _clean(item.get("safra"))
    regiao = _clean(item.get("regiao"))
    # `uvas` pode ser JSON string ou lista
    grape = item.get("uvas")
    if isinstance(grape, str):
        try:
            parsed = json.loads(grape)
            if isinstance(parsed, list):
                grape = ", ".join(str(x) for x in parsed)
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(grape, list):
        grape = ", ".join(str(x) for x in grape)
    return {
        "ocr": {
            "name": nome or "",
            "producer": produtor or "",
            "vintage": safra or "",
            "region": regiao or "",
            "grape": _clean(grape) or "",
            # "line" e "classification" nao existem no schema do router,
            # ficam vazios — enrichment_v3 aceita.
            "line": "",
            "classification": _clean(item.get("tipo")) or "",
        }
    }


# ---------- Merge campos uteis Gemini -> item original ----------

def merge_enriched(original: dict, enriched: dict) -> dict:
    """Aplica merge conservador dos campos Gemini no item original.

    Regra: so preenche onde o original esta vazio.
    Nao altera os `_router_*` e `_source_*` ja existentes.
    """
    out = dict(original)

    def _fill(key: str, value):
        cur = out.get(key)
        if cur is None or (isinstance(cur, str) and not cur.strip()):
            if value not in (None, ""):
                out[key] = value

    full_name = _clean(enriched.get("full_name")) or _clean(enriched.get("wine_name"))
    _fill("nome", full_name)
    _fill("produtor", _clean(enriched.get("producer")))

    vintage = _vintage_to_str(enriched.get("vintage"))
    _fill("safra", vintage)

    pais_iso = _iso2(enriched.get("country_code"))
    _fill("pais", pais_iso)

    _fill("regiao", _clean(enriched.get("region")))
    _fill("sub_regiao", _clean(enriched.get("sub_region")))

    tipo = _map_style(enriched.get("style"))
    _fill("tipo", tipo)

    uvas = _to_jsonl_uvas(enriched.get("grape"))
    _fill("uvas", uvas)

    abv = _abv_to_float(enriched.get("abv"))
    if abv is not None and out.get("teor_alcoolico") is None:
        out["teor_alcoolico"] = abv

    _fill("harmonizacao", _clean(enriched.get("pairing")))

    # Anota metadata da rodada de enrichment
    out["_enriched_at"] = datetime.now(timezone.utc).isoformat()
    out["_enriched_kind"] = enriched.get("kind")
    out["_enriched_confidence"] = enriched.get("confidence")
    out["_enriched_source_model"] = enriched.get("source_model")
    out["_enriched_escalated"] = enriched.get("escalated", False)
    return out


def _has_minimum_fields(item: dict) -> bool:
    """Tem nome + (produtor OR ean_gtin) + ao menos uma ancora geo?"""
    if not (item.get("nome") and str(item.get("nome")).strip()):
        return False
    if not (item.get("produtor") or item.get("ean_gtin")):
        return False
    return any(
        item.get(k)
        for k in ("pais", "regiao", "sub_regiao", "ean_gtin")
    )


# ---------- Classificacao pos-enrichment ----------

def classify_post_enrichment(original: dict, enriched: dict) -> tuple[str, dict, list[str]]:
    """Aplica o segundo filtro e retorna (bucket, item_final, reasons).

    bucket ∈ {"enriched_ready", "enriched_not_wine", "enriched_uncertain"}
    """
    kind = enriched.get("kind")
    reasons: list[str] = []

    if kind in ("not_wine", "spirit"):
        reasons.append(f"gemini_kind={kind}")
        return "enriched_not_wine", {**original, **{
            "_enriched_kind": kind,
            "_enriched_confidence": enriched.get("confidence"),
            "_enriched_source_model": enriched.get("source_model"),
        }}, reasons

    if kind != "wine":
        # unknown ou ausente
        reasons.append(f"gemini_kind={kind or 'missing'}")
        return "enriched_uncertain", {**original, **{
            "_enriched_kind": kind,
            "_enriched_confidence": enriched.get("confidence"),
        }}, reasons

    # kind == "wine": guardrail factual ANTES do merge
    conflict = _detect_country_conflict(original, enriched)
    if conflict is not None:
        # Guardrail: Gemini contradiz a fonte. Nunca vai pra ready.
        reasons.append("qa_conflict:country_hint_mismatch")
        reasons.append(f"gemini_pais={conflict['gemini_pais']}")
        reasons.append(f"source_hint_pais={conflict['source_hint_pais']}")
        reasons.append(f"source_hint_reason={conflict['source_hint_reason']}")
        # Marca o item: NAO aplica merge do pais conflitante — preserva original.
        out = dict(original)
        out["_enriched_kind"] = "wine"
        out["_enriched_confidence"] = enriched.get("confidence")
        out["_enriched_source_model"] = enriched.get("source_model")
        out["_qa_conflict"] = conflict
        return "enriched_uncertain", out, reasons

    # Sem conflito — merge normal e reclassifica
    merged = merge_enriched(original, enriched)
    if not _has_minimum_fields(merged):
        reasons.append("post_merge_sem_campos_minimos")
        merged.setdefault("_enriched_reasons", []).extend(reasons)
        return "enriched_uncertain", merged, reasons

    status, classifier_reasons = classify(merged)
    merged["_post_enrich_status"] = status
    merged["_post_enrich_reasons"] = classifier_reasons

    if status == "ready":
        return "enriched_ready", merged, reasons + classifier_reasons

    # Gemini nao foi suficiente — uncertain lateral
    reasons.append(f"post_enrich_status={status}")
    reasons.extend(classifier_reasons)
    return "enriched_uncertain", merged, reasons


# ---------- IO ----------

def _read_jsonl(path: Path) -> list[dict]:
    items: list[dict] = []
    if not path.exists():
        raise FileNotFoundError(f"input_nao_existe: {path}")
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"jsonl_invalido linha={lineno}: {e.msg}")
            if not isinstance(obj, dict):
                raise ValueError(f"jsonl_linha_nao_objeto linha={lineno}")
            items.append(obj)
    return items


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_uncertain_csv(path: Path, rows: list[dict], source: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=UNCERTAIN_CSV_COLS)
        w.writeheader()
        for row in rows:
            raw = {
                k: v for k, v in row.items()
                if not k.startswith("_router_") and not k.startswith("_enriched_")
            }
            w.writerow({
                "router_index": row.get("_router_index", ""),
                "source": source,
                "nome_original": row.get("nome", "") or "",
                "produtor_original": row.get("produtor", "") or "",
                "nome_enriquecido": row.get("nome", "") or "",
                "produtor_enriquecido": row.get("produtor", "") or "",
                "pais_enriquecido": row.get("pais", "") or "",
                "kind": row.get("_enriched_kind", "") or "",
                "confidence": row.get("_enriched_confidence", "") or "",
                "reasons": ";".join(
                    (row.get("_enriched_reasons") or []) +
                    (row.get("_post_enrich_reasons") or [])
                ),
                "raw_json": json.dumps(raw, ensure_ascii=False),
            })


def _pct(n: int, total: int) -> float:
    return (n * 100.0 / total) if total else 0.0


def _write_summary(path: Path, *, input_path: str, source: str, out_dir: Path,
                   counters: dict, confirmed_gemini: bool, mode: str) -> None:
    total = counters["input_needs"]
    unknown = counters["gemini_unknown"]
    unknown_pct = _pct(unknown, total)
    lines = []
    lines.append(f"# enrich_needs — summary")
    lines.append("")
    lines.append(f"- Input: `{input_path}`")
    lines.append(f"- Source: `{source}`")
    lines.append(f"- Output dir: `{out_dir.as_posix()}`")
    lines.append(f"- Modo: `{mode}` (gemini_chamado={confirmed_gemini})")
    lines.append("")
    lines.append("## Contadores")
    lines.append("")
    lines.append("| Metrica | Valor |")
    lines.append("|---|---:|")
    for k in (
        "input_needs", "gemini_wine", "gemini_not_wine", "gemini_spirit",
        "gemini_unknown", "post_ready", "post_uncertain", "qa_conflicts",
    ):
        lines.append(f"| {k} | {counters[k]} |")
    lines.append("")
    if unknown_pct > 20.0:
        lines.append("## WARNING")
        lines.append("")
        lines.append(
            f"`gemini_unknown / input_needs = {unknown_pct:.2f}%` > 20%. "
            "Revisar a fonte ou o prompt antes de escalar volume. "
            "Nao bloqueia o pipeline."
        )
        lines.append("")
    lines.append("## Proximo passo sugerido (sem --apply)")
    lines.append("")
    lines.append("```bash")
    lines.append(
        "python scripts/ingest_via_bulk.py \\"
    )
    lines.append(
        f"  --input {(out_dir / 'enriched_ready.jsonl').as_posix()} \\"
    )
    lines.append(
        f"  --source {source}"
    )
    lines.append("```")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------- Nucleo ----------

def run_enrich(
    input_path: str,
    source: str,
    *,
    limit: int = _MAX_LIMIT_SAFE,
    out_dir: Path | None = None,
    confirm_gemini: bool = False,
    enrich_fn=None,
    raw_cache_path: str | None = None,
) -> dict:
    """Roda a Fase 4.

    Args:
        input_path: path do needs_enrichment.jsonl.
        source: identificador (A-Za-z0-9_.-).
        limit: max items (ceil 500, smoke).
        out_dir: override do diretorio de saida.
        confirm_gemini: True libera chamada real ao Gemini.
        enrich_fn: injecao pra testes (mock). Se None, resolve
            `backend.services.enrichment_v3.enrich_items_v3`.

    Returns dict com contadores + paths. Em plano-only retorna
    counters zerados e `mode="plan_only"`.
    """
    import re
    if not re.match(r"^[A-Za-z0-9_.\-]+$", source or ""):
        raise ValueError(f"source_invalido: {source!r}")
    if limit <= 0 or limit > _MAX_LIMIT_SAFE:
        raise ValueError(f"limit_invalido: {limit} (use 1..{_MAX_LIMIT_SAFE})")

    items = _read_jsonl(Path(input_path))
    items = items[:limit]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_out = out_dir or _DEFAULT_OUT_DIR
    run_out = Path(base_out) / f"{ts}_{source}"

    counters = {
        "input_needs": len(items),
        "gemini_wine": 0,
        "gemini_not_wine": 0,
        "gemini_spirit": 0,
        "gemini_unknown": 0,
        "post_ready": 0,
        "post_uncertain": 0,
        "qa_conflicts": 0,
    }

    # --from-raw: nao precisa de --confirm-gemini, ja foi autorizado antes.
    if raw_cache_path and not confirm_gemini:
        # Considera autorizado pra fins de fluxo — o custo foi pago antes.
        effective_real_run = True
    else:
        effective_real_run = confirm_gemini

    if not effective_real_run:
        # Plano-only: nao gera arquivos, nao chama Gemini.
        return {
            "mode": "plan_only",
            "confirmed_gemini": False,
            "planned_out_dir": run_out.as_posix(),
            "input_needs": counters["input_needs"],
            "limit_requested": limit,
            "note": "passe --confirm-gemini pra executar (custo real).",
        }

    # Modo real — cria dir e chama Gemini (ou le cache).
    run_out.mkdir(parents=True, exist_ok=True)

    if raw_cache_path:
        # Modo cache: reprocessa raw_gemini_response.jsonl anterior
        # sem nenhuma chamada de API.
        raw_rows = _read_jsonl(Path(raw_cache_path))
        raw_by_idx: dict = {}
        for row in raw_rows:
            key = row.get("router_index")
            if key is None:
                key = row.get("index")
            # Usa o `enriched` (pos to_auto_create_enriched) ou `parsed`
            e = row.get("enriched") or row.get("parsed") or {"kind": "unknown"}
            raw_by_idx[key] = e

        def enrich_fn_impl(ocr_items, source_channel=None):
            out_items = []
            for i, original in enumerate(items):
                idx = original.get("_router_index", i)
                e = raw_by_idx.get(idx)
                if e is None:
                    e = {"kind": "unknown", "index": i + 1}
                out_items.append(dict(e))
            return {
                "items": out_items,
                "raw_primary": "",
                "raw_escalated": "",
                "stats": {"from_raw": True, "raw_rows": len(raw_rows)},
            }

        def post(parsed: dict) -> dict:
            return parsed  # enriched ja veio pronto do cache
    elif enrich_fn is None:
        # Resolucao tardia evita importar enrichment_v3 em plano-only
        from services.enrichment_v3 import enrich_items_v3, to_auto_create_enriched  # type: ignore
        enrich_fn_impl = enrich_items_v3
        post = to_auto_create_enriched
    else:
        enrich_fn_impl = enrich_fn

        def post(parsed: dict) -> dict:
            """Default post: passa o dict como-esta (mocks ja devolvem shape OK)."""
            return parsed

    ocr_items = [item_to_ocr(it) for it in items]
    v3 = enrich_fn_impl(ocr_items, source_channel=f"enrich_needs:{source}")
    parsed_items = v3.get("items", []) or []

    ready_rows: list[dict] = []
    not_wine_rows: list[dict] = []
    uncertain_rows: list[dict] = []
    raw_audit: list[dict] = []

    for idx, original in enumerate(items):
        parsed = parsed_items[idx] if idx < len(parsed_items) else {}
        enriched = post(parsed) if parsed else {"kind": "unknown"}

        kind = enriched.get("kind")
        if kind == "wine":
            counters["gemini_wine"] += 1
        elif kind == "not_wine":
            counters["gemini_not_wine"] += 1
        elif kind == "spirit":
            counters["gemini_spirit"] += 1
        else:
            counters["gemini_unknown"] += 1

        bucket, final_item, reasons = classify_post_enrichment(original, enriched)
        final_item["_enriched_reasons"] = reasons

        # Contador separado: quantos foram desviados de ready por guardrail factual
        if any(r == "qa_conflict:country_hint_mismatch" for r in reasons):
            counters["qa_conflicts"] += 1

        if bucket == "enriched_ready":
            ready_rows.append(final_item)
            counters["post_ready"] += 1
        elif bucket == "enriched_not_wine":
            not_wine_rows.append(final_item)
        else:
            uncertain_rows.append(final_item)
            counters["post_uncertain"] += 1

        raw_audit.append({
            "router_index": original.get("_router_index"),
            "nome_original": original.get("nome"),
            "produtor_original": original.get("produtor"),
            "parsed": parsed,
            "enriched": enriched,
            "bucket": bucket,
            "reasons": reasons,
        })

    _write_jsonl(run_out / "enriched_ready.jsonl", ready_rows)
    _write_jsonl(run_out / "enriched_not_wine.jsonl", not_wine_rows)
    _write_uncertain_csv(run_out / "enriched_uncertain_review.csv",
                         uncertain_rows, source)
    _write_jsonl(run_out / "raw_gemini_response.jsonl", raw_audit)
    _write_summary(
        run_out / "enriched_summary.md",
        input_path=input_path,
        source=source,
        out_dir=run_out,
        counters=counters,
        confirmed_gemini=True,
        mode="gemini_cached" if raw_cache_path else "gemini_real",
    )

    return {
        "mode": "gemini_cached" if raw_cache_path else "gemini_real",
        "confirmed_gemini": True,
        "out_dir": run_out.as_posix(),
        "limit_requested": limit,
        "from_raw": bool(raw_cache_path),
        **counters,
        "ready_path": (run_out / "enriched_ready.jsonl").as_posix(),
    }


# ---------- CLI ----------

def main() -> int:
    parser = argparse.ArgumentParser(description="Fase 4 enrichment Gemini")
    parser.add_argument("--input", required=True, help="needs_enrichment.jsonl")
    parser.add_argument("--source", required=True, help="[A-Za-z0-9_.-]")
    parser.add_argument("--limit", type=int, default=_MAX_LIMIT_SAFE,
                        help=f"ceil smoke {_MAX_LIMIT_SAFE}")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--confirm-gemini", action="store_true",
                        help="LIBERA chamada real ao Gemini (custo)")
    parser.add_argument("--from-raw", default=None,
                        help=("REPROCESSA com guardrails sobre raw_gemini_response.jsonl "
                              "de uma rodada anterior — ZERO chamada Gemini nova"))
    args = parser.parse_args()

    try:
        result = run_enrich(
            input_path=args.input,
            source=args.source,
            limit=args.limit,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            confirm_gemini=args.confirm_gemini,
            raw_cache_path=args.from_raw,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"[enrich_needs] ERRO: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        # Mensagem sem vazar segredo
        print(f"[enrich_needs] ERRO: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
