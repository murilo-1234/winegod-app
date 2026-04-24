"""Fila humana: itens que falharam mesmo apos retry V2 via v3.

Gera relatorio markdown em
`reports/data_ops_enrichment_human_queue/<ts>.md`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[3]
HUMAN_DIR = REPO_ROOT / "reports" / "data_ops_enrichment_human_queue"


_MAX_REASONS = 6


def _reasons(item: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not item.get("producer"):
        reasons.append("producer_missing")
    if not item.get("wine_name"):
        reasons.append("wine_name_missing")
    if not item.get("country_code"):
        reasons.append("country_missing")
    conf = item.get("confidence")
    if conf is None:
        reasons.append("confidence_null")
    else:
        try:
            if float(conf) < 0.8:
                reasons.append(f"confidence_low={float(conf):.2f}")
        except (TypeError, ValueError):
            reasons.append("confidence_invalid")
    vintage = item.get("vintage")
    if vintage:
        try:
            y = int(vintage)
            if y > datetime.now(timezone.utc).year or y < 1800:
                reasons.append(f"vintage_out_of_range={y}")
        except (TypeError, ValueError):
            reasons.append(f"vintage_invalid={vintage!r}")
    kind = item.get("kind")
    if kind and kind != "wine":
        reasons.append(f"kind={kind}")
    return reasons[:_MAX_REASONS]


def _vivino_link(item: dict[str, Any]) -> str | None:
    vid = (item.get("wine_identity") or {}).get("vivino_id")
    if vid:
        return f"vivino://{vid}"
    return None


def render_human_queue(items: Iterable[dict[str, Any]]) -> str:
    rows: list[dict[str, Any]] = list(items)
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    lines = [
        "# Enrichment Human Queue",
        "",
        f"- generated_at_utc: `{ts}`",
        f"- items: `{len(rows)}`",
        "",
        "| # | Nome atual | Razoes | Vivino link | Sugestao do router |",
        "|---|---|---|---|---|",
    ]
    for i, item in enumerate(rows, start=1):
        name = (
            item.get("full_name")
            or item.get("wine_name")
            or (item.get("wine_identity") or {}).get("nome")
            or "(sem nome)"
        )
        reasons = ", ".join(_reasons(item)) or "-"
        link = _vivino_link(item) or "-"
        suggestion = item.get("router_suggestion") or "revisao_manual"
        lines.append(f"| {i} | {name} | {reasons} | {link} | {suggestion} |")
    return "\n".join(lines) + "\n"


def persist_queue(items: Iterable[dict[str, Any]], *, timestamp: str | None = None) -> Path:
    HUMAN_DIR.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = HUMAN_DIR / f"{ts}_human_queue.md"
    path.write_text(render_human_queue(items), encoding="utf-8")
    return path


__all__ = ["render_human_queue", "persist_queue", "HUMAN_DIR"]
