"""Estimador de custo Gemini do loop de enrichment.

Calcula um forecast deterministico em USD a partir do numero de items
e rates publicas dos modelos do hibrido v3.

Rates default baseiam-se na documentacao publica do Gemini para
`gemini-2.5-flash-lite` e `gemini-3.1-flash-lite-preview`. Como o
preview muda com frequencia, os valores sao intencionalmente
conservadores e podem ser sobrescritos via env vars.

ENV override:
  - ENRICHMENT_INPUT_RATE_USD_PER_1M   (default abaixo)
  - ENRICHMENT_OUTPUT_RATE_USD_PER_1M  (default abaixo)
  - ENRICHMENT_INPUT_TOKENS_PER_ITEM   (default 220)
  - ENRICHMENT_OUTPUT_TOKENS_PER_ITEM  (default 180)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any


getcontext().prec = 18


# Rates default - documentacao publica do Gemini (em USD por 1M tokens).
# Conservative defaults; real app should confirm rates on Google's pricing page.
DEFAULT_INPUT_RATE_USD_PER_1M = Decimal("0.10")
DEFAULT_OUTPUT_RATE_USD_PER_1M = Decimal("0.40")
DEFAULT_INPUT_TOKENS_PER_ITEM = 220
DEFAULT_OUTPUT_TOKENS_PER_ITEM = 180


def _env_decimal(name: str, default: Decimal) -> Decimal:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return Decimal(raw)
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default


@dataclass
class BudgetEstimate:
    items: int
    input_tokens_per_item: int
    output_tokens_per_item: int
    input_rate_usd_per_1m: Decimal
    output_rate_usd_per_1m: Decimal
    total_input_tokens: int
    total_output_tokens: int
    input_cost_usd: Decimal
    output_cost_usd: Decimal
    total_cost_usd: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "input_tokens_per_item": self.input_tokens_per_item,
            "output_tokens_per_item": self.output_tokens_per_item,
            "input_rate_usd_per_1m": str(self.input_rate_usd_per_1m),
            "output_rate_usd_per_1m": str(self.output_rate_usd_per_1m),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "input_cost_usd": str(self.input_cost_usd),
            "output_cost_usd": str(self.output_cost_usd),
            "total_cost_usd": str(self.total_cost_usd),
        }


def estimate_cost(
    items: int,
    *,
    input_tokens_per_item: int | None = None,
    output_tokens_per_item: int | None = None,
    input_rate_usd_per_1m: Decimal | None = None,
    output_rate_usd_per_1m: Decimal | None = None,
) -> BudgetEstimate:
    if items < 0:
        raise ValueError("items must be non-negative")
    in_tokens = input_tokens_per_item or _env_int(
        "ENRICHMENT_INPUT_TOKENS_PER_ITEM", DEFAULT_INPUT_TOKENS_PER_ITEM
    )
    out_tokens = output_tokens_per_item or _env_int(
        "ENRICHMENT_OUTPUT_TOKENS_PER_ITEM", DEFAULT_OUTPUT_TOKENS_PER_ITEM
    )
    in_rate = input_rate_usd_per_1m or _env_decimal(
        "ENRICHMENT_INPUT_RATE_USD_PER_1M", DEFAULT_INPUT_RATE_USD_PER_1M
    )
    out_rate = output_rate_usd_per_1m or _env_decimal(
        "ENRICHMENT_OUTPUT_RATE_USD_PER_1M", DEFAULT_OUTPUT_RATE_USD_PER_1M
    )
    total_in = items * in_tokens
    total_out = items * out_tokens
    input_cost = (Decimal(total_in) / Decimal(1_000_000)) * in_rate
    output_cost = (Decimal(total_out) / Decimal(1_000_000)) * out_rate
    return BudgetEstimate(
        items=items,
        input_tokens_per_item=in_tokens,
        output_tokens_per_item=out_tokens,
        input_rate_usd_per_1m=in_rate,
        output_rate_usd_per_1m=out_rate,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        input_cost_usd=input_cost.quantize(Decimal("0.0001")),
        output_cost_usd=output_cost.quantize(Decimal("0.0001")),
        total_cost_usd=(input_cost + output_cost).quantize(Decimal("0.0001")),
    )


def recommended_batch_cap(
    cost_cap_usd: Decimal,
    *,
    input_tokens_per_item: int | None = None,
    output_tokens_per_item: int | None = None,
    input_rate_usd_per_1m: Decimal | None = None,
    output_rate_usd_per_1m: Decimal | None = None,
) -> int:
    """Maior batch que cabe dentro do cap USD."""
    in_tokens = input_tokens_per_item or _env_int(
        "ENRICHMENT_INPUT_TOKENS_PER_ITEM", DEFAULT_INPUT_TOKENS_PER_ITEM
    )
    out_tokens = output_tokens_per_item or _env_int(
        "ENRICHMENT_OUTPUT_TOKENS_PER_ITEM", DEFAULT_OUTPUT_TOKENS_PER_ITEM
    )
    in_rate = input_rate_usd_per_1m or _env_decimal(
        "ENRICHMENT_INPUT_RATE_USD_PER_1M", DEFAULT_INPUT_RATE_USD_PER_1M
    )
    out_rate = output_rate_usd_per_1m or _env_decimal(
        "ENRICHMENT_OUTPUT_RATE_USD_PER_1M", DEFAULT_OUTPUT_RATE_USD_PER_1M
    )
    per_item = (
        (Decimal(in_tokens) / Decimal(1_000_000)) * in_rate
        + (Decimal(out_tokens) / Decimal(1_000_000)) * out_rate
    )
    if per_item <= 0:
        return 0
    return int((Decimal(cost_cap_usd) / per_item).to_integral_value(rounding="ROUND_DOWN"))


def report_md(estimate: BudgetEstimate, *, by_route: dict[str, int] | None = None) -> str:
    lines = [
        "# Enrichment Budget Forecast",
        "",
        f"- items: `{estimate.items}`",
        f"- input_tokens_per_item: `{estimate.input_tokens_per_item}`",
        f"- output_tokens_per_item: `{estimate.output_tokens_per_item}`",
        f"- input_rate_usd_per_1m: `{estimate.input_rate_usd_per_1m}`",
        f"- output_rate_usd_per_1m: `{estimate.output_rate_usd_per_1m}`",
        f"- total_input_tokens: `{estimate.total_input_tokens}`",
        f"- total_output_tokens: `{estimate.total_output_tokens}`",
        f"- input_cost_usd: `{estimate.input_cost_usd}`",
        f"- output_cost_usd: `{estimate.output_cost_usd}`",
        f"- **total_cost_usd**: `{estimate.total_cost_usd}`",
    ]
    if by_route:
        lines.append("")
        lines.append("## Items por rota")
        for route, count in sorted(by_route.items()):
            lines.append(f"- `{route}`: `{count}`")
    return "\n".join(lines) + "\n"


__all__ = [
    "BudgetEstimate",
    "estimate_cost",
    "recommended_batch_cap",
    "report_md",
    "DEFAULT_INPUT_RATE_USD_PER_1M",
    "DEFAULT_OUTPUT_RATE_USD_PER_1M",
    "DEFAULT_INPUT_TOKENS_PER_ITEM",
    "DEFAULT_OUTPUT_TOKENS_PER_ITEM",
]
