# Plug Enrichment Gemini Contract

## Scope

Enrichment consumes incomplete or uncertain candidates and stages the result for later routing.

## Sources in scope

- `reports/gemini_batch_state.json`
- `reports/gemini_batch_input.jsonl`
- `reports/gemini_batch_output.jsonl`
- `reports/ingest_pipeline_enriched/**`
- optional persisted `flash_*` tables for read-only counts

## Minimal record contract

Each staged record should include:

- `source`
- `route` with one of `ready`, `uncertain`, `not_wine`
- `wine_identity`
- `enrichment`
- `source_lineage`

## Safety rules

- Do not call Gemini or Flash live in this session
- Do not write enriched results into final business tables
- Use hashes for bulky raw payloads when a reference is enough

## Delivery mode

- This plug is staging-only in this session
- Output goes to `reports/data_ops_plugs_staging/`
- Telemetry goes to `ops.*`

## Automation

- `scripts/data_ops_scheduler/run_enrichment_dryruns.ps1` runs the
  canonical dry-run against `gemini_batch_reports`.
- `scripts/data_ops_scheduler/run_enrichment_health_check.ps1` runs the
  read-only health snapshot (`sdk.plugs.enrichment.health`). Exit:
  `0` ok, `2` warning, `3` failed.

## Health check

`sdk.plugs.enrichment.health.assess_health` produces a read-only snapshot
from disk only. It never calls Gemini/Flash, never opens a DB write
connection, never mutates state or staging. The snapshot lists:

- presence/size/mtime of `gemini_batch_state.json`, `gemini_batch_input.jsonl`,
  `gemini_batch_output.jsonl`;
- count of artifacts in `reports/ingest_pipeline_enriched/`;
- latest staging summary (state, items, ready, uncertain, not_wine);
- latest scheduler log;
- classified status: `ok`, `warning`, `failed`, with machine-readable
  `reasons` and `warnings` arrays.

## Safety test net

`sdk/plugs/enrichment/tests/test_manifests_coverage.py` locks:

- the plug manifest is the enrichment owner;
- manifests in scope use tag `plug:enrichment`;
- no manifest declares final tables (`public.wines`, `public.wine_sources`,
  `public.stores`, `public.store_recipes`) in outputs;
- `can_create_wine_sources`, `requires_dq_v3`, `requires_matching` stay
  `false`.
