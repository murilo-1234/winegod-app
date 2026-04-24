"""Orquestra uso do external_adapter (sistema v3 existente).

Dois modos:

  prepare  -> gera batch input file em
              `reports/data_ops_enrichment_gemini_batches/<ts>_input.jsonl`
              + metadata. ZERO chamada Gemini.

  dispatch -> requer TUDO abaixo, senao raise:
                * env GEMINI_PAID_AUTHORIZED=1
                * env GEMINI_PILOT_MAX_ITEMS (int, <= 20000)
                * flag --apply
                * budget forecast recente (<= 24h) em
                  reports/data_ops_enrichment_budget/ com custo estimado
                  <= GEMINI_PILOT_MAX_USD (default 50).

  Salva resultado em
  `reports/data_ops_enrichment_pilot/<ts>_result.jsonl`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[3]
BATCHES_DIR = REPO_ROOT / "reports" / "data_ops_enrichment_gemini_batches"
PILOT_DIR = REPO_ROOT / "reports" / "data_ops_enrichment_pilot"
BUDGET_DIR = REPO_ROOT / "reports" / "data_ops_enrichment_budget"

AUTH_ENV = "GEMINI_PAID_AUTHORIZED"
PILOT_MAX_ITEMS_ENV = "GEMINI_PILOT_MAX_ITEMS"
PILOT_MAX_USD_ENV = "GEMINI_PILOT_MAX_USD"

HARD_CAP = 20_000
DEFAULT_MAX_USD = Decimal("50")
BUDGET_MAX_AGE = timedelta(hours=24)


@dataclass
class DispatchResult:
    mode: str
    items: int
    path: Path
    elapsed_ms: int | None = None
    adapter_stats: dict[str, Any] | None = None


def _pilot_cap(max_items_env: str | None = None) -> int | None:
    raw = max_items_env if max_items_env is not None else os.environ.get(PILOT_MAX_ITEMS_ENV)
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{PILOT_MAX_ITEMS_ENV} invalid: {raw!r}")
    if value <= 0 or value > HARD_CAP:
        raise ValueError(
            f"{PILOT_MAX_ITEMS_ENV} must be in [1, {HARD_CAP}] (got {value})"
        )
    return value


def _latest_budget_json() -> Path | None:
    if not BUDGET_DIR.exists():
        return None
    files = sorted(
        BUDGET_DIR.glob("*_budget.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def _verify_budget(cap_usd: Decimal) -> Path:
    latest = _latest_budget_json()
    if latest is None:
        raise RuntimeError(
            f"dispatch requires recent budget in {BUDGET_DIR}; run "
            "scripts/data_ops_producers/enrichment_budget_forecast.py first"
        )
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(
        latest.stat().st_mtime, tz=timezone.utc
    )
    if age > BUDGET_MAX_AGE:
        raise RuntimeError(
            f"latest budget too old ({age} > {BUDGET_MAX_AGE}); regenerate"
        )
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise RuntimeError(f"latest budget unreadable: {latest}")
    total = Decimal(str(data.get("estimate", {}).get("total_cost_usd", "0")))
    if total > cap_usd:
        raise RuntimeError(
            f"budget total_cost_usd={total} exceeds cap {cap_usd} (file {latest})"
        )
    return latest


def prepare(items: list[dict[str, Any]], *, timestamp: str | None = None) -> DispatchResult:
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = BATCHES_DIR / f"{ts}_input.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    metadata = BATCHES_DIR / f"{ts}_metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "items": len(items),
                "file": str(path),
                "mode": "prepare",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return DispatchResult(mode="prepare", items=len(items), path=path)


def dispatch(
    items: list[dict[str, Any]],
    *,
    enrich_fn: Callable[[list[dict[str, Any]], str], list[dict[str, Any]]] | None = None,
    timestamp: str | None = None,
    cap_usd: Decimal | None = None,
) -> DispatchResult:
    if os.environ.get(AUTH_ENV) != "1":
        raise PermissionError(f"dispatch requires env {AUTH_ENV}=1")
    pilot_cap = _pilot_cap()
    if pilot_cap is None:
        raise PermissionError(
            f"dispatch requires env {PILOT_MAX_ITEMS_ENV} (int, <= {HARD_CAP})"
        )
    if len(items) > pilot_cap:
        raise ValueError(
            f"items={len(items)} exceeds pilot cap {pilot_cap}"
        )
    cap = cap_usd or Decimal(os.environ.get(PILOT_MAX_USD_ENV, str(DEFAULT_MAX_USD)))
    _verify_budget(cap)
    if enrich_fn is None:
        from .external_adapter import enrich_batch  # lazy import
        enrich_fn = lambda batch, channel: enrich_batch(batch, source_channel=channel)  # noqa: E731
    t0 = datetime.now(timezone.utc)
    parsed = enrich_fn(items, "enrichment_pilot")
    elapsed_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)

    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = PILOT_DIR / f"{ts}_result.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for entry in parsed:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return DispatchResult(
        mode="dispatch",
        items=len(items),
        path=path,
        elapsed_ms=elapsed_ms,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Gemini dispatcher (gated)")
    parser.add_argument(
        "--mode",
        choices=("prepare", "dispatch"),
        default="prepare",
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="JSONL com items a despachar (formato do adapter)",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--cap-usd", type=str, default=None)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"input file missing: {input_path}")
    items: list[dict[str, Any]] = []
    with input_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))

    if args.mode == "prepare":
        if args.apply:
            parser.error("prepare mode ignores --apply; use mode=dispatch")
        result = prepare(items)
        print(f"[gemini_dispatcher] prepare -> {result.path} (items={result.items})")
        return 0

    # dispatch
    if not args.apply:
        parser.error("dispatch requires --apply")
    try:
        cap = Decimal(args.cap_usd) if args.cap_usd else None
        result = dispatch(items, cap_usd=cap)
    except Exception as exc:
        parser.error(f"dispatch refused: {type(exc).__name__}: {exc}")
    print(
        f"[gemini_dispatcher] dispatch -> {result.path} (items={result.items}, "
        f"elapsed_ms={result.elapsed_ms})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
