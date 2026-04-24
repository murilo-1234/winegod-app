# Reviews Dominio Health Check

- source: `vivino_wines_to_ratings`
- status: `ok`
- generated_at_utc: `2026-04-24T07:42:10.078629Z`

## Checkpoint
- present: `True`
- last_id: `2227129`
- runs: `43`
- updated_at: `2026-04-24T07:39:29.154872Z`
- mode: `backfill_windowed`

## Sentinela fim de backfill
- present: `False`

## Ultimo summary
- path: `C:\winegod-app\reports\data_ops_plugs_staging\20260424_073723_vivino_wines_to_ratings_summary.md`
- mtime_utc: `2026-04-24T07:39:30.295965Z`
- mode: `backfill_windowed`
- items: `10000`

### Apply payload
```json
{
  "source": "vivino_wines_to_ratings",
  "processed": 10000,
  "matched": 9940,
  "unmatched": 60,
  "wine_scores_upserted": 9940,
  "wine_scores_changed": 40,
  "wines_rating_updated": 1,
  "skipped_per_review": 0,
  "skipped_no_score": 0,
  "batches_committed": 1,
  "errors": []
}
```

## Backfill ultimo log
- path: `C:\winegod-app\reports\data_ops_scheduler\vivino_reviews_backfill\20260424_043719_backfill.log`
- mtime_utc: `2026-04-24T07:37:19.188042Z`
- exit: `None`

## Incremental ultimo log
- path: `C:\winegod-app\reports\data_ops_scheduler\vivino_reviews_incremental\20260424_034328_incremental.log`
- mtime_utc: `2026-04-24T06:44:48.955835Z`
- exit: `0`
