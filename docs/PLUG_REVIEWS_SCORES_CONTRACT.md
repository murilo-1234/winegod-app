# Plug Reviews Scores Contract

## Scope

Use this plug for reviews, ratings, critic notes, and market signals that are not
commerce offers. The plug is the official owner of the review-derived data domain
inside Winegod Data Ops.

## Sources in scope

- `vivino_wines_to_ratings` (canonical apply path: per-wine aggregates from `vivino_vinhos`)
- `vivino_reviews_to_scores_reviews` (per-review staging only; not applied to `wine_scores`)
- `cellartracker_to_scores_reviews`
- `decanter_to_critic_scores`
- `wine_enthusiast_to_critic_scores`
- `winesearcher_to_market_signals`

## Minimal record contract

Each staged record must include:

- `source`
- `wine_identity` (vivino_id for Vivino sources; source_wine_id for others)
- `score` (`{value, scale}`) when present
- `review` (PII-safe subset) when present
- `reviewer_ref` without raw PII in `ops.*`
- `source_lineage`

## Derived fields

- `signal_kind` — `vivino`, `vivino_review`, `cellartracker`, `decanter`,
  `wine_enthusiast`, `winesearcher`
- `score_normalized_100` — rating projected onto 0..100 scale (5→*20, 100→id)
- `review_text_present` — boolean flag (not the text itself)
- `review_freshness_at` — ISO8601 timestamp of source update
- `canonical_match_key` — sha256 of `nome|produtor|safra|pais` (lowercased)
- `source_confidence` — derived from `sample_size`. **Formula lives in a single
  place**: `scripts/wcf_confidence.py::confianca`. Both `scripts/calc_wcf.py`
  and `sdk/plugs/reviews_scores/confidence.py` import from it. Never duplicate.
- `market_price_signal` — `avg_price_usd` when source is Wine-Searcher

## PII rules

- No reviewer full text, email, phone, avatar URL, or profile URL in `ops.*` or
  in `public.wine_scores.dados_extra`
- Use hashes or source references for reviewer and review body material
- `reviewer_ref` is `null` for the canonical Vivino aggregate source
- Apply writer persists no review text in `wine_scores`

## Delivery modes

### Dry-run (default for every source)

- Output: JSONL + Markdown summary in `reports/data_ops_plugs_staging/`
- Telemetry: `ops.scraper_runs`, `ops.ingestion_batches` (when `OPS_BASE_URL`
  and `OPS_TOKEN` are set)
- No writes to business tables

### Apply (canonical source `vivino_wines_to_ratings`)

Two explicit automation modes:

1. **`incremental_recent`** (default) — `ORDER BY atualizado_em DESC LIMIT N`.
   Picks the freshest slice every time. Useful for continuous sync of the top
   of the distribution. **Does not progress through the whole base on its
   own**; re-running picks up the same top slice.
2. **`backfill_windowed`** — `WHERE id > last_id ORDER BY id ASC LIMIT N`.
   Uses a persistent cursor stored at
   `reports/data_ops_plugs_state/<source>.json`. Each successful apply advances
   `last_id` to the max id of the batch, so repeated runs progress through the
   entire base. When the exporter returns 0 items, the backfill has reached
   the end.

Both modes:

- UPSERT into `public.wine_scores` using `UNIQUE(wine_id, fonte)`.
- The `ON CONFLICT DO UPDATE` has `WHERE wine_scores.score IS DISTINCT FROM
  EXCLUDED.score OR ... (for score_raw, confianca, dados_extra)`. **`criado_em`
  is never mutated**. So an identical re-apply produces `wine_scores_changed=0`
  real row changes (though `wine_scores_upserted` still reports how many rows
  were sent for upsert).
- UPDATE `public.wines.vivino_rating` and `public.wines.vivino_reviews` guarded
  by `IS DISTINCT FROM` — zero rows update when value is unchanged. The trigger
  `trg_score_recalc` enqueues the wine in `score_recalc_queue` only when a real
  delta lands, so the WCF pipeline does not get spammed with no-op recomputes.
- **Atomic per batch**: each window of `batch_size` (default 10,000) contains
  its `wine_scores` upsert AND its corresponding `wines` update in a single
  transaction. A failure mid-batch rolls both back. `batches_committed` in the
  result payload counts atomic commits.
- MVP telemetry rule respected: `items_final_inserted` reported as `0` in
  `ops.scraper_runs`/`ops.ingestion_batches`; the real apply counters
  (`wine_scores_upserted`, `wine_scores_changed`, `wines_rating_updated`,
  `batches_committed`) live in the `plug.reviews_scores.summary` event payload
  and in the Markdown staging summary (including `checkpoint_before` and
  `checkpoint_after` fields for `backfill_windowed`).

### Apply (non-Vivino sources)

- Currently staging-only; the writer skips them because there is no
  deterministic `vivino_id` linkage with `public.wines`. All derived fields are
  already emitted; a future matching pass using `canonical_match_key` unlocks
  their apply without schema changes.
- `backfill_windowed` is rejected by the runner for these sources.

## Idempotency (strong)

- `wine_scores`: `ON CONFLICT (wine_id, fonte) DO UPDATE ... WHERE IS DISTINCT
  FROM` — a re-apply of identical rows reports `wine_scores_changed=0`. Verified
  twice against the live Render DB on 2026-04-23:
  - backfill_windowed limit=5 from scratch (5 new rows) → changed=5
  - reset checkpoint + rerun same window → changed=0
  - reset + rerun again → changed=0
- `wines.vivino_rating/vivino_reviews`: guarded by `IS DISTINCT FROM`; no-op
  when inputs equal current state; never touches `atualizado_em` unnecessarily.

## Atomicity

- Each batch closes a single Postgres transaction containing BOTH the
  `wine_scores` upsert and the `wines` update for that batch's wine_ids. If
  either fails, the whole batch is rolled back. Unit test
  `test_batch_atomicity_rollback_on_wines_update_failure` forces the `wines`
  update to raise and asserts no commit leaked.

## Automation

- `scripts/data_ops_scheduler/run_all_plug_dryruns.ps1` runs every source in
  dry-run.
- `scripts/data_ops_scheduler/run_plug_reviews_scores_apply.ps1` runs the
  canonical apply path. Parameters:
  - `-Mode incremental_recent` (default): fresh-slice sync.
  - `-Mode backfill_windowed`: progress-through-base cursor.
  Schedule both — incremental for minutes-to-hours cadence, backfill
  continuously until it reports `items=0`.

## Never

- Never write a separate review-derived plug; always evolve this one.
- Never persist raw review text to the main DB.
- Never write directly to `public.wines` or `wine_sources` outside the apply
  path defined here.
- Never duplicate the WCF confidence formula. Single source of truth:
  `scripts/wcf_confidence.py`.
- Never claim the scheduler "sweeps the base naturally" in
  `incremental_recent`; that is only true of `backfill_windowed`.
