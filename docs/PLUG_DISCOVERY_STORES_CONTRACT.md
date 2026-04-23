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
