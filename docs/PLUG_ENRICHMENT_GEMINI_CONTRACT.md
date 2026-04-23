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
