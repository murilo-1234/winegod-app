# Discovery Stores Promotion Contract

Status: executavel
Data: 2026-04-24
Owner: `sdk/plugs/discovery_stores/promotion.py` + `scripts/data_ops_producers/promote_discovery_stores.py`

## Scope

This contract defines the deterministic path that turns a staged
`discovery_stores` candidate into a production row in `public.stores`
and one or more rows in `public.store_recipes`.

**Dry-run is default.** Real apply requires BOTH the env var
`DISCOVERY_PROMOTION_AUTHORIZED=1` AND a code-level flag
`authorized=True`. Anything else raises.

## 1. Promotion gate (must all be true)

A candidate is eligible for promotion when ALL of the following are
true at plan time:

| Gate | Check | Required value |
|---|---|---|
| G1 | `minimum_products_extractable` | `>=10` distinct product URLs observable from sample scrape |
| G2 | `selector_hit_rate` | `>=0.8` (80%+ of declared CSS/JSON selectors match sample HTML) |
| G3 | `catalog_url_pattern_validated` | pattern matched `>=3` distinct product listing URLs |
| G4 | `domain_not_duplicate_after_normalization` | normalized domain NOT already in `public.stores` |
| G5 | `country_iso2_present_and_valid` | `country` is ISO 3166-1 alpha-2 (case-insensitive) |

If any gate fails, the candidate is **skipped** with `reason_code` and
`reason_detail`. No write occurs.

## 2. Field-by-field schema mapping

### 2.1 `public.stores`

| Discovery field | `public.stores` column | Notes |
|---|---|---|
| `normalized_domain` | `dominio` | lowercase, no `www.`, no trailing slash |
| `store_name` | `nome` | title-cased |
| `url` | `url` | as-is from source |
| `country` | `pais` | uppercase ISO-2 |
| `platform` | `plataforma` | null if `unknown` |
| `tier_hint` | `tier` | `tier1_template` -> `1`; `tier1_candidate` -> `1_candidate`; else `2_manual` |
| constant | `origem_descoberta` | `"discovery_agent_global"` |
| constant | `origem_promocao` | `"plug_discovery_stores"` |
| NOW()      | `criado_em` | auto |

### 2.2 `public.store_recipes`

Only created when `recipe_candidate` is non-null AND passes gates.

| Discovery field | `public.store_recipes` column |
|---|---|
| resolved `store_id` | `store_id` |
| `recipe_candidate.metodo_listagem` | `metodo_listagem` |
| `recipe_candidate.metodo_extracao` | `metodo_extracao` |
| `recipe_candidate.usa_playwright` | `usa_playwright` |
| `recipe_candidate.anti_bot` | `anti_bot` |
| `recipe_candidate.notas` | `notas` |
| `recipe_candidate.url_sitemap` | `url_sitemap` |
| constant `"candidate_from_discovery"` | `status` |
| NOW() | `criado_em` |

## 3. Reversal criteria

A promoted recipe must be reverted (status -> `quarantined`) when ANY
of these occur in production:

- 3 consecutive scrape runs produce zero products
- domain returns HTTP 5xx for 24h straight
- selectors hit rate drops below 0.3 on a recent sample
- DNS no longer resolves
- legal/compliance flag lands in `ops.scraper_runs.flags`

Reversal is a separate tool (not in this contract). This contract only
guarantees the initial promotion is safe and traceable.

## 4. Lineage

Every promoted store carries:

- `origem_descoberta = "discovery_agent_global"` (raw source)
- `origem_promocao  = "plug_discovery_stores"`   (tool that promoted)
- `recipe_candidate.confidence` persisted in `store_recipes.notas`
  prefix `confidence=<value>`

Every recipe carries:

- `status = "candidate_from_discovery"` on first insert
- same `store_id` resolved from the normalized domain

This ensures downstream jobs can filter by `origem_*` columns and
distinguish discovery-promoted stores from legacy manual inserts.

## 5. Precedence vs legacy `store_recipes`

If a recipe already exists for the same `store_id` from a pre-existing
manual or legacy import:

- the legacy recipe **wins** by default
- the promotion emits a `skipped_recipe_reason="legacy_recipe_exists"`
- the candidate is saved to
  `reports/data_ops_promotion_plans/<ts>_legacy_conflicts.json` for
  manual review

No overwrite of production recipes happens automatically.

## 6. PromotionPlan object

```python
@dataclass
class PromotionPlan:
    generated_at_utc: str
    candidates: list[CandidateEvaluation]
    plan_hash: str          # sha256 of sorted normalized domain list + gate decisions
    total_candidates: int
    approved_stores: int
    approved_recipes: int
    skipped: list[dict]     # [{normalized_domain, reason_code, reason_detail}, ...]
```

The plan is idempotent: **same input produces same plan_hash**.

## 7. apply() semantics

```python
class StorePromoter:
    def plan(self, candidates: list[dict]) -> PromotionPlan: ...
    def apply(
        self,
        plan: PromotionPlan,
        *,
        authorized: bool,
        batch_size: int = 100,
    ) -> PromotionResult: ...
```

`apply()` rules (all enforced):

1. `authorized` must be `True`. Otherwise raise `PermissionError`.
2. `os.environ["DISCOVERY_PROMOTION_AUTHORIZED"] == "1"`. Otherwise raise.
3. Each batch of `batch_size <= 100` runs in ONE Postgres transaction.
4. A batch failure rolls back both `stores` and `store_recipes` of that
   batch. Previous committed batches stay.
5. `plan.plan_hash` is stored in the transaction metadata
   (`stores.notas` JSON key `promotion_plan_hash`) for traceability.
6. Post-apply, a `PromotionResult` is persisted to
   `reports/data_ops_promotion_plans/<ts>_result.json`.

## 8. Deterministic gates — reference implementation pointers

- Gate G1: `minimum_products_extractable` comes from the sample scrape
  JSON; if the sample is missing, G1 fails with `no_sample_scrape`.
- Gate G2: `selector_hit_rate` = `selectors_matched / selectors_declared`.
- Gate G3: validated by `recipe_candidate.catalog_patterns` length and
  uniqueness.
- Gate G4: uses `sdk/plugs/common.normalize_domain` + lookup of the
  resulting canonical domain against `public.stores`.
- Gate G5: regex `^[A-Z]{2}$` on `country.upper()`.

## 9. Never

- Never write directly to `public.stores` outside this promoter.
- Never overwrite an existing `store_recipes` without an explicit
  operator-level override (out of scope for this contract).
- Never bypass gates "just this once".
- Never promote a candidate with missing `source_lineage`.
