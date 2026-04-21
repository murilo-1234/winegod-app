#!/usr/bin/env python3
"""Auditoria QA dos enriched_ready.jsonl guardados antes do apply.

So-leitura do arquivo JSONL. Nao chama Gemini, nao toca banco, nao faz HTTP.
Produz:
  - Markdown report com contagens + risk lines
  - CSV com (router_index, nome, produtor, pais, regiao, url_original,
    risk_level, reasons)

Uso:
    python scripts/_audit_enriched_ready.py \\
        --input reports/ingest_pipeline_enriched/<run>/enriched_ready.jsonl \\
        --md reports/WINEGOD_PRE_INGEST_ENRICHED_READY_QA_20260421.md \\
        --csv reports/WINEGOD_PRE_INGEST_ENRICHED_READY_QA_20260421.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# Reutiliza hints ja validados no enrich_needs
from enrich_needs import (  # noqa: E402
    _extract_country_hint_from_url,
    _extract_country_hint_from_text,
    _collect_source_hints,
)


_KIT_PATTERNS = re.compile(
    r"\b(kit|pack|caixa|case|combo|gift|presente|voucher|assinatura|clube)\b",
    re.IGNORECASE,
)
_NOT_WINE_HINT = re.compile(
    r"\b(queijo|cerveja|beer|whisky|whiskey|vodka|gin|tequila|cachaca|cognac|licor|liqueur)\b",
    re.IGNORECASE,
)


def _load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _audit_one(row: dict) -> tuple[str, list[str]]:
    """Retorna (risk_level, reasons). risk_level ∈ {ok, review, blocker}."""
    reasons: list[str] = []
    nome = (row.get("nome") or "").strip()
    produtor = (row.get("produtor") or "").strip()
    pais = (row.get("pais") or "").strip().lower() or None
    regiao = (row.get("regiao") or "").strip()
    url = row.get("url_original") or row.get("_fonte_original") or ""
    teor = row.get("teor_alcoolico")

    # URL hint
    url_hint_iso, url_hint_reason = _extract_country_hint_from_url(url)

    # Blockers
    if url_hint_iso and pais and url_hint_iso != pais:
        reasons.append(
            f"BLOCKER: url_hint_pais_conflita "
            f"(url={url_hint_iso} via {url_hint_reason}, final={pais})"
        )

    # Hint textual (descricao + regiao)
    for key in ("descricao", "regiao"):
        v = row.get(key)
        iso, why = _extract_country_hint_from_text(v)
        if iso and pais and iso != pais:
            reasons.append(
                f"BLOCKER: text_hint_pais_conflita "
                f"(hint={iso} via {why}, final={pais})"
            )
            break

    # Review-level
    if not nome or len(nome) < 8:
        reasons.append(f"REVIEW: nome_curto ({nome!r})")
    if produtor and nome and produtor.lower() == nome.lower():
        reasons.append("REVIEW: produtor_igual_nome")
    if _KIT_PATTERNS.search(nome) or _KIT_PATTERNS.search(produtor):
        reasons.append("REVIEW: possivel_kit_ou_voucher")
    if _NOT_WINE_HINT.search(nome) or _NOT_WINE_HINT.search(produtor):
        reasons.append("BLOCKER: palavra_not_wine_no_nome")
    if teor is not None:
        try:
            t = float(teor)
            if t < 7 or t > 20:
                reasons.append(f"BLOCKER: teor_alcoolico_fora_padrao ({t})")
            elif t < 10 or t > 15:
                reasons.append(f"REVIEW: teor_alcoolico_atipico ({t})")
        except (TypeError, ValueError):
            pass

    # URL BR + pais nao-BR = mais sutil (marketplace brasileiro vendendo
    # importado e normal). So bloqueia quando hint de URL e forte (com vin-XX-).
    if not reasons:
        return "ok", []

    has_blocker = any(r.startswith("BLOCKER:") for r in reasons)
    return ("blocker" if has_blocker else "review"), reasons


def _count_url_hints(rows: list[dict]) -> tuple[int, int]:
    """Retorna (com_hint, com_conflito_url_hint_vs_pais_final)."""
    with_hint = 0
    conflict = 0
    for r in rows:
        url = r.get("url_original") or r.get("_fonte_original") or ""
        iso, _ = _extract_country_hint_from_url(url)
        if iso:
            with_hint += 1
            pais = (r.get("pais") or "").strip().lower()
            if pais and pais != iso:
                conflict += 1
    return with_hint, conflict


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--md", required=True)
    parser.add_argument("--csv", required=True)
    args = parser.parse_args()

    rows = _load_rows(Path(args.input))
    total = len(rows)

    audited = []
    for r in rows:
        level, reasons = _audit_one(r)
        audited.append((r, level, reasons))

    by_pais = Counter(r.get("pais") for r, _, _ in audited)
    by_model = Counter(
        r.get("_enriched_source_model") or "?" for r, _, _ in audited
    )
    by_level = Counter(level for _, level, _ in audited)

    url_hint_count, url_hint_conflict = _count_url_hints(rows)
    # pais original alterado pelo gemini
    pais_original_alterado = 0
    for r, _, _ in audited:
        # Nao temos o "pais original pre-merge" dentro de enriched_ready.jsonl
        # (merge_enriched preserva o original quando existia), entao esse
        # numero e zero por construcao do merge conservador. Ainda assim
        # reportamos para explicitar.
        pass

    Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
    Path(args.md).parent.mkdir(parents=True, exist_ok=True)

    with open(args.csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "router_index", "nome", "produtor", "pais",
            "regiao", "url_original", "risk_level", "reasons",
        ])
        for r, level, reasons in audited:
            w.writerow([
                r.get("_router_index"),
                r.get("nome", ""),
                r.get("produtor", ""),
                r.get("pais", ""),
                r.get("regiao", ""),
                r.get("url_original", ""),
                level,
                "; ".join(reasons),
            ])

    blockers = [(r, reasons) for r, lvl, reasons in audited if lvl == "blocker"]
    reviews = [(r, reasons) for r, lvl, reasons in audited if lvl == "review"]
    oks = [r for r, lvl, _ in audited if lvl == "ok"]

    lines: list[str] = []
    lines.append("# WINEGOD PRE_INGEST — QA dos enriched_ready.jsonl (guarded)")
    lines.append("")
    lines.append(f"Input: `{args.input}`")
    lines.append(f"Total auditado: **{total}**")
    lines.append("")
    lines.append("## Distribuicao de risco")
    lines.append("")
    lines.append("| Nivel | Count |")
    lines.append("|---|---:|")
    lines.append(f"| ok | {by_level.get('ok', 0)} |")
    lines.append(f"| review | {by_level.get('review', 0)} |")
    lines.append(f"| **blocker** | {by_level.get('blocker', 0)} |")
    lines.append("")
    lines.append("## Contagem por pais final")
    lines.append("")
    lines.append("| pais | count |")
    lines.append("|---|---:|")
    for p, c in sorted(by_pais.items(), key=lambda x: (-x[1], x[0] or "")):
        lines.append(f"| {p or '(vazio)'} | {c} |")
    lines.append("")
    lines.append("## Contagem por modelo Gemini")
    lines.append("")
    lines.append("| modelo | count |")
    lines.append("|---|---:|")
    for m, c in by_model.most_common():
        lines.append(f"| {m} | {c} |")
    lines.append("")
    lines.append("## Sinais de URL hint")
    lines.append("")
    lines.append(f"- Itens com URL que tem pattern `/vin-XX-`: **{url_hint_count}**")
    lines.append(f"- Conflitos URL hint vs pais final: **{url_hint_conflict}** "
                 "(se > 0 o guardrail falhou — investigar)")
    lines.append(f"- Conflitos `pais` original vs Gemini: **0** "
                 "(pelo design do merge conservador, pais original e preservado — "
                 "mas o guardrail tambem bloqueia antes do merge)")
    lines.append("")

    lines.append("## Itens blocker")
    lines.append("")
    if not blockers:
        lines.append("_Nenhum blocker detectado._")
    else:
        lines.append("| router_index | nome | produtor | pais | razoes |")
        lines.append("|---|---|---|---|---|")
        for r, reasons in blockers:
            lines.append(
                f"| {r.get('_router_index')} | "
                f"{r.get('nome','')} | {r.get('produtor','')} | "
                f"{r.get('pais','')} | {'; '.join(reasons)} |"
            )
    lines.append("")

    lines.append("## Itens review (aplicar so aceitando risco)")
    lines.append("")
    if not reviews:
        lines.append("_Nenhum review._")
    else:
        lines.append("| router_index | nome | produtor | pais | razoes |")
        lines.append("|---|---|---|---|---|")
        for r, reasons in reviews:
            lines.append(
                f"| {r.get('_router_index')} | "
                f"{r.get('nome','')} | {r.get('produtor','')} | "
                f"{r.get('pais','')} | {'; '.join(reasons)} |"
            )
    lines.append("")

    lines.append("## Recomendacao")
    lines.append("")
    if blockers:
        lines.append(
            f"**NAO aplicar.** Existem {len(blockers)} blocker(s). "
            "Mover pra uncertain_review ou corrigir fonte antes de aplicar."
        )
    else:
        rev_note = ""
        if reviews:
            rev_note = (
                f" Existem {len(reviews)} item(s) em `review` — operador decide "
                "se aceita o risco ou retira manualmente."
            )
        lines.append(
            "Tecnicamente **pronto para apply pequeno**, aguardando "
            "autorizacao humana explicita." + rev_note
        )
    lines.append("")
    lines.append(f"CSV detalhado: `{args.csv}`")

    Path(args.md).write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "total": total,
        "ok": by_level.get("ok", 0),
        "review": by_level.get("review", 0),
        "blocker": by_level.get("blocker", 0),
        "url_hint_count": url_hint_count,
        "url_hint_conflict": url_hint_conflict,
        "pais_original_alterado": 0,
        "md": args.md,
        "csv": args.csv,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
