# Preflight subida vinhos 2026-04-24
_gerado_em: 2026-04-24T19:13:14.595979+00:00_

## Branch / Commit
- branch: `data-ops/subida-local-render-3fases-20260424`
- HEAD: `7ce4c9a3c05e4c3bc49f8565330be65e9560b637` (7ce4c9a3)
- message: fix(subida-3fases): phase1_execution correcao final (PASS falsos + concorrencia)

## DSNs
- winegod_local: `postgres://***:***@localhost/winegod_db`
- render: `postgres://***:***@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod`

## Schema Render
- migration 018 :: `ingestion_run_log` -> OK
- migration 019 :: `not_wine_rejections` -> OK
- migration 020 :: `ingestion_review_queue` -> OK
- migration 021 :: `wcf_pipeline_control` -> FALTA

## Counts baseline
- db_size_pretty: 8834 MB
- wines: 2513197
- wine_sources: 3491687
- stores: 19889
- ingestion_review_queue_pending: 10

## Snapshots audit
- `audit_wines_pre_subida_20260424` -> OK (presente)
- `audit_wine_sources_pre_subida_20260424` -> OK (presente)

## Concorrencia
- schtask detectada: `"\BackupVivino08h","25/04/2026 08:00:00","Pronto"`
- schtask detectada: `"\BackupVivino14h","25/04/2026 14:00:00","Em execu��o"`
- schtask detectada: `"\BackupVivino22h","24/04/2026 22:00:00","Pronto"`
- schtask detectada: `"\WineGod Plug Reviews Vivino Backfill","24/04/2026 16:28:10","Em execu��o"`
- schtask detectada: `"\WineGod Plug Reviews Vivino Incremental","24/04/2026 16:43:12","Pronto"`

## Gates preflight
- dsn_local_presente: PASS
- dsn_render_presente: PASS
- migration_018_ok: PASS
- migration_019_ok: PASS
- migration_020_ok: PASS
- migration_021_ok: FAIL
- snapshot_audit_wines_presente: PASS
- snapshot_audit_wine_sources_presente: PASS
