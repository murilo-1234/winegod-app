# Reviews Dominio Health Check

- source: `vivino_wines_to_ratings`
- status: `ok`
- generated_at_utc: `2026-04-24T06:11:13.123021Z`

## Checkpoint
- present: `True`
- last_id: `2038979`
- runs: `38`
- updated_at: `2026-04-24T05:58:59.917618Z`
- mode: `backfill_windowed`

## Sentinela fim de backfill
- present: `False`

## Ultimo summary
- path: `C:\winegod-app\reports\data_ops_plugs_staging\20260424_055814_vivino_wines_to_ratings_summary.md`
- mtime_utc: `2026-04-24T05:58:59.931046Z`
- mode: `backfill_windowed`
- items: `10000`

### Apply payload
```json
{
  "source": "vivino_wines_to_ratings",
  "processed": 10000,
  "matched": 9944,
  "unmatched": 56,
  "wine_scores_upserted": 9944,
  "wine_scores_changed": 43,
  "wines_rating_updated": 0,
  "skipped_per_review": 0,
  "skipped_no_score": 0,
  "batches_committed": 1,
  "errors": []
}
```

## Backfill ultimo log
- path: `C:\winegod-app\reports\data_ops_scheduler\vivino_reviews_backfill\20260424_025811_backfill.log`
- mtime_utc: `2026-04-24T05:59:02.708409Z`
- exit: `0`

## Incremental ultimo log
- path: `C:\winegod-app\reports\data_ops_scheduler\vivino_reviews_incremental\20260424_024602_incremental.log`
- mtime_utc: `2026-04-24T05:55:21.850437Z`
- exit: `0`
