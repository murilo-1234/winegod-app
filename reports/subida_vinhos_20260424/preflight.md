# Preflight subida vinhos 2026-04-24
_gerado_em: 2026-04-24T16:00:03.254389+00:00_

## Branch / Commit
- branch: `data-ops/subida-local-render-3fases-20260424`
- HEAD: `834d37ab5194b537dd83f43c539d0288fc8ef18c` (834d37ab)
- message: docs(subida-3fases): phase1_execution + phase1_tests + decisions log

## DSNs
- winegod_local: `postgres://***:***@localhost/winegod_db`
- render: `postgres://***:***@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod`

## Schema Render
- migration 018 :: `ingestion_run_log` -> OK
- migration 019 :: `not_wine_rejections` -> OK
- migration 020 :: `ingestion_review_queue` -> OK
- migration 021 :: `wcf_pipeline_control` -> FALTA

## Counts baseline
- db_size_pretty: 8426 MB
- wines: 2513197
- wine_sources: 3491687
- stores: 19889
- ingestion_review_queue_pending: 10

## Snapshots audit
- `audit_wines_pre_subida_20260424` -> FALTA CRIAR: `CREATE TABLE audit_wines_pre_subida_20260424 AS SELECT id, ingestion_run_id, created_at FROM wines;`

## Concorrencia
- schtask detectada: `"\BackupVivino08h","25/04/2026 08:00:00","Pronto"`
- schtask detectada: `"\BackupVivino14h","24/04/2026 14:00:00","Pronto"`
- schtask detectada: `"\BackupVivino22h","24/04/2026 22:00:00","Pronto"`
- schtask detectada: `"\WineGod Plug Reviews Vivino Backfill","24/04/2026 13:13:10","Pronto"`
- schtask detectada: `"\WineGod Plug Reviews Vivino Incremental","24/04/2026 13:43:12","Pronto"`

## Gates preflight
- dsn_local_presente: PASS
- dsn_render_presente: PASS
- migration_018_ok: PASS
- migration_019_ok: PASS
- migration_020_ok: PASS
- migration_021_ok: FAIL
- snapshot_audit_presente: FAIL
