# Enrichment Loop Contract

Status: executavel
Data: 2026-04-24
Owner: `sdk/plugs/enrichment/*`

## 0. Existing enrichment system (source of truth - READ-ONLY)

The WineGod product **already has a production enrichment system** for
wines. This loop orchestrates that system; it does not replace it and
does not modify it.

- Path: `backend/services/enrichment_v3.py`
- Public interface (stable):
  - `enrich_items_v3(items, source_channel=None, trace=None) -> dict`
    returns `{items, raw_primary, raw_escalated, stats}`
  - `to_discovery_enriched(parsed) -> dict | None`
  - `to_auto_create_enriched(parsed) -> dict`
  - `needs_escalation(parsed, ocr_name) -> bool`
- Model stack (intocavel):
  - primary: `Config.ENRICHMENT_GEMINI_25_MODEL` (`gemini-2.5-flash-lite`)
  - escalated: `Config.ENRICHMENT_GEMINI_31_MODEL`
    (`gemini-3.1-flash-lite-preview`)
- Input format expected by `enrich_items_v3`:
  `[{"ocr": {...}}, ...]`
- Output item structure (per-item in `result["items"]`):
  `{index, kind, producer, wine_name, full_name, country_code, style,
    grape, region, sub_region, vintage, abv, classification, body,
    pairing, sweetness, source_model, escalated, duplicate_of, ...}`
  with `kind in {"wine", "spirit", "not_wine", "unknown"}`.

**This contract does not change any of the above.** The loop invokes
the public interface only, via a thin read-only adapter
(`sdk/plugs/enrichment/external_adapter.py`).

## 1. Deterministic route definitions (post-v3)

After `enrich_items_v3` returns, the loop classifies each item into one
of three routes:

| Route | Rule (all-of) |
|---|---|
| `ready` | `kind == "wine"` AND core fields present (`producer`, `wine_name`, `country_code`) AND `confidence >= threshold` (see below) |
| `not_wine` | `kind in {"not_wine", "spirit"}` OR local `wine_filter.should_skip_wine` marks the `full_name` / `wine_name` |
| `uncertain` | anything else: `kind == "unknown"`, missing core fields, low confidence, or conflicting fields (e.g. `vintage > current_year`) |

Threshold comes from `ENRICHMENT_CONFIDENCE_THRESHOLD` env (default `0.8`).
Confidence is computed by `_confidence_from_parsed` of `enrichment_v3`.

## 2. Escalation flow

1. `ready` -> production apply queue (out of scope of this repo session).
2. `uncertain` -> retry by **calling the same `enrich_items_v3`** (no
   parallel prompt, no V2 clone). The adapter exposes `retry(item)`
   which rebuilds the `ocr` payload and re-submits. If `enrich_items_v3`
   returns `kind == "wine"` with confidence >= threshold, the item
   moves to `ready`.
3. Still `uncertain` after retry -> goes to
   `reports/data_ops_enrichment_human_queue/<timestamp>.md` for human
   review. Format includes: current name, uncertain fields, Vivino
   link if resolvable, router suggestions.
4. `not_wine` -> the propagator (`not_wine_propagator.py`) extracts a
   candidate pattern and produces a patch against `wine_filter.py`.
   The patch is saved in `reports/data_ops_not_wine_patches/` only;
   apply is manual.

## 3. not_wine propagation

- Source of truth for `NOT_WINE`: `scripts/wine_filter.py`.
- Rule: `feedback_notwine_propagation` - novo pattern NOT_WINE deve ir
  para `wine_filter.py` (regex) E, quando for regra procedural (ABV,
  volume, gramatura), tambem para `scripts/pre_ingest_filter.py`.
- The loop only emits `reports/data_ops_not_wine_patches/<ts>_wine_filter_patch.diff`.
  It never commits to the repo `winegod` externo. It never edits
  `wine_filter.py` directly.

## 4. Budget

The loop must run a budget forecast before any paid dispatch:

- Rates are documented in `sdk/plugs/enrichment/budget.py` default
  constants based on public Gemini pricing (both models of the hybrid).
  Override via env `ENRICHMENT_INPUT_RATE_USD_PER_1M` and
  `ENRICHMENT_OUTPUT_RATE_USD_PER_1M`.
- Forecast CLI: `scripts/data_ops_producers/enrichment_budget_forecast.py`
- Output: `reports/data_ops_enrichment_budget/<ts>_budget.md` with
  items counts, tokens estimate, USD estimate, recommended batch cap.

## 5. Authorization gate for dispatch

Paid dispatch only runs when ALL of these are true:

- env `GEMINI_PAID_AUTHORIZED=1`
- env `GEMINI_PILOT_MAX_ITEMS=<int <= 20000>`
- CLI flag `--apply`
- a **recent** budget forecast exists in
  `reports/data_ops_enrichment_budget/` (within 24h) and the estimated
  USD cost is `<= GEMINI_PILOT_MAX_USD` (default `50`).

Else: `parser.error`. No exceptions.

In this session, the user authorized a pilot of up to `20,000` items.
The dispatcher must cap hard at that number and also cap at the queue
size if smaller. It persists results in
`reports/data_ops_enrichment_pilot/<ts>_result.jsonl`.

## 6. Discovery context exception (new prompt allowed here)

The rule "do not create a new enrichment prompt" applies to **wine
enrichment** only. If a future job needs to enrich a **store / domain**
candidate coming from discovery (e.g., to classify whether the domain
is really a wine e-commerce), it can use a dedicated prompt in:

```
sdk/plugs/enrichment/prompts/discovery_context.py
```

Wine enrichment remains untouched and uses the existing v3 system.

## 7. Never

- Never duplicate the v3 prompt. Reuse the existing one via the adapter.
- Never modify files in `backend/services/enrichment_v3.py`,
  `backend/tools/media.py`, or `backend/config.py` fields `ENRICHMENT_*`.
- Never push output of this loop into `public.wines`, `public.wine_sources`,
  or `public.wine_scores` in this session.
- Never call Gemini in `prepare` mode. `prepare` is pure file I/O.
- Never bypass the budget gate.
