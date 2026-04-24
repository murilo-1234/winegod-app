"""Fila de retry simulado para itens `uncertain`.

Consome o bucket `uncertain` do staging, prepara o payload para uma
segunda passada do sistema existente `enrich_items_v3` (via adapter),
e grava em `reports/data_ops_enrichment_retry_queue/<ts>.jsonl`.

Nao chama Gemini de verdade. O dispatch real e gated em
`gemini_dispatcher.py`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[3]
QUEUE_DIR = REPO_ROOT / "reports" / "data_ops_enrichment_retry_queue"


@dataclass
class RetryPayload:
    ocr: dict[str, Any]
    hints: dict[str, Any]
    retry_round: int = 2  # esta fila sempre dispara V2 via v3 existente

    def to_dict(self) -> dict[str, Any]:
        return {"ocr": self.ocr, "hints": self.hints, "retry_round": self.retry_round}


def build_retry_payload(item: dict[str, Any]) -> RetryPayload:
    name = (
        item.get("full_name")
        or item.get("wine_name")
        or (item.get("wine_identity") or {}).get("nome")
    )
    ocr = {"name": name}
    if item.get("producer"):
        ocr["producer"] = item["producer"]
    hints = {
        "previous_kind": item.get("kind"),
        "previous_confidence": item.get("confidence"),
        "previous_reasons": item.get("_enriched_reasons"),
        "router_note": "second_pass_via_v3",
    }
    return RetryPayload(ocr=ocr, hints=hints)


def persist_queue(items: Iterable[dict[str, Any]], *, timestamp: str | None = None) -> Path:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = QUEUE_DIR / f"{ts}_uncertain_retry.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            payload = build_retry_payload(item).to_dict()
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


__all__ = ["RetryPayload", "build_retry_payload", "persist_queue", "QUEUE_DIR"]
