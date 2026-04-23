# Plug Reviews Scores Contract

## Scope

Use this plug for reviews, ratings, critic notes, and market signals that are not commerce offers.

## Sources in scope

- `vivino_reviews_to_scores_reviews`
- `cellartracker_to_scores_reviews`
- `decanter_to_critic_scores`
- `wine_enthusiast_to_critic_scores`
- `winesearcher_to_market_signals`

## Minimal record contract

Each staged record must include:

- `source`
- `wine_identity`
- `score` when present
- `review` when present
- `reviewer_ref` without raw PII in `ops.*`
- `source_lineage`

## PII rules

- No reviewer full text, email, phone, avatar URL, or profile URL in `ops.*`
- Use hashes or source references for reviewer and review body material
- Final writes stay blocked until a dedicated target table or service is explicitly approved

## Delivery mode

- This plug is staging-only in this session
- Output goes to `reports/data_ops_plugs_staging/`
- Telemetry goes to `ops.*`
- No writes to final review or score tables
