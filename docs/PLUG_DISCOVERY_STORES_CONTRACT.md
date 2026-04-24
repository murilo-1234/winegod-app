# Plug Discovery Stores Contract

## Scope

Discovery produces candidate stores and recipe hints. It does not create wines, wine sources, or final stores.

## Sources in scope

- `agent_discovery`
- `C:\natura-automation\ecommerces_vinhos_*_v2.json`
- `C:\natura-automation\agent_discovery\discovery_phases.json`

## Minimal record contract

Each staged record should include:

- `source`
- `domain`
- `normalized_domain`
- `url`
- `store_name`
- `country`
- `platform`
- `validation_status`
- `tier_hint`
- `already_known_store`
- `known_store_id` when resolvable
- `recipe_candidate` as a staging hint only
- `source_lineage`

## Safety rules

- No final insert into `stores`
- No final insert into `store_recipes`
- Recipe hints remain advisory until a dedicated contract and approval path exist

## Delivery mode

- This plug is staging-only in this session
- Output goes to `reports/data_ops_plugs_staging/`
- Telemetry goes to `ops.*`

## Automation

- `scripts/data_ops_scheduler/run_discovery_stores_dryruns.ps1` runs the
  canonical dry-run against `agent_discovery`.
- `scripts/data_ops_scheduler/run_discovery_stores_health_check.ps1` runs
  the read-only health snapshot (`sdk.plugs.discovery_stores.health`).
  Exit: `0` ok, `2` warning, `3` failed.

## Health check

`sdk.plugs.discovery_stores.health.assess_health` produces a read-only
snapshot from disk only. It never opens a DB connection, never mutates
state, never calls an external API. The snapshot lists:

- source artifacts in `C:\natura-automation\` (root, phases file, count,
  most recent `ecommerces_vinhos_*_v2.json` with mtime);
- latest staging summary (state, items, known_store_hits);
- latest scheduler log;
- classified status: `ok`, `warning`, `failed`, with
  machine-readable `reasons` and `warnings` arrays.

## Safety test net

`sdk/plugs/discovery_stores/tests/test_manifests_coverage.py` locks:

- the plug manifest is the discovery owner;
- manifests in scope use tag `plug:discovery_stores`;
- no manifest declares final tables (`public.wines`, `public.wine_sources`,
  `public.stores`, `public.store_recipes`) in outputs;
- `can_create_wine_sources`, `requires_dq_v3`, `requires_matching` stay
  `false`.
