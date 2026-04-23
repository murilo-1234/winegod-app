-- ============================================================================
-- Migration 023: create_ops_schema
-- ============================================================================
-- WineGod Data Ops — Fase 1 Control Plane Local.
-- Cria schema `ops` e 14 tabelas de telemetria conforme Design Freeze v2:
--   C:\winegod-app\WINEGOD_PLATAFORMA_CENTRAL_SCRAPERS_DESIGN_FREEZE.md
--
-- Princípio: este schema é exclusivamente de OBSERVABILIDADE.
-- Nada em `ops.*` representa inserção em dado de negócio.
-- `items_final_inserted` é sempre 0 no MVP.
--
-- Rollback: 023_create_ops_schema.rollback.sql
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS ops;

-- ----------------------------------------------------------------------------
-- 1) ops.scraper_registry
-- Cadastro único de cada scraper/adapter.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.scraper_registry (
  scraper_id               text        PRIMARY KEY,
  display_name             text        NOT NULL,
  family                   text        NOT NULL,
  source                   text        NOT NULL,
  variant                  text,
  host                     text        NOT NULL,
  owner                    text        NOT NULL DEFAULT 'murilo',
  connector_type           text        NOT NULL,
  contract_name            text        NOT NULL,
  contract_version         text        NOT NULL,
  status                   text        NOT NULL DEFAULT 'draft',
  can_create_wine_sources  boolean     NOT NULL DEFAULT false,
  requires_dq_v3           boolean     NOT NULL DEFAULT false,
  requires_matching        boolean     NOT NULL DEFAULT false,
  schedule_hint            text,
  freshness_sla_hours      integer     NOT NULL DEFAULT 24,
  declared_fields          jsonb       NOT NULL DEFAULT '[]'::jsonb,
  pii_policy               text        NOT NULL DEFAULT 'strict',
  retention_policy         text        NOT NULL DEFAULT 'default',
  manifest_path            text,
  manifest_hash            varchar(64),
  tags                     jsonb       NOT NULL DEFAULT '[]'::jsonb,
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now(),
  deprecated_at            timestamptz,

  CHECK (family IN ('commerce','discovery','catalog_identity','review','reviewer',
                    'community_rating','critic','market','enrichment','canary')),
  CHECK (status IN ('draft','registered','contract_validated','active','paused',
                    'stale','error','blocked_quality','deprecated')),
  CHECK (pii_policy IN ('strict','debug_sample')),
  CHECK (retention_policy IN ('default'))
);

COMMENT ON TABLE ops.scraper_registry IS
  'Cadastro de scrapers/adapters. 1 linha por scraper_id. Permanente.';

CREATE INDEX IF NOT EXISTS idx_registry_family_status
  ON ops.scraper_registry (family, status);
CREATE INDEX IF NOT EXISTS idx_registry_host
  ON ops.scraper_registry (host);
CREATE INDEX IF NOT EXISTS idx_registry_updated
  ON ops.scraper_registry (updated_at DESC);

-- ----------------------------------------------------------------------------
-- 2) ops.scraper_runs
-- Uma linha por execução.
-- UNIQUE (scraper_id, run_id) é target de FKs compostas.
-- items_final_inserted é sempre 0 no MVP.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.scraper_runs (
  run_id                   uuid        PRIMARY KEY,
  scraper_id               text        NOT NULL
                                       REFERENCES ops.scraper_registry(scraper_id),
  status                   text        NOT NULL DEFAULT 'started',
  started_at               timestamptz NOT NULL DEFAULT now(),
  last_heartbeat_at        timestamptz,
  ended_at                 timestamptz,
  duration_ms              bigint,
  items_extracted          bigint      NOT NULL DEFAULT 0,
  items_valid_local        bigint      NOT NULL DEFAULT 0,
  items_sent               bigint      NOT NULL DEFAULT 0,
  items_rejected_schema    bigint      NOT NULL DEFAULT 0,
  items_final_inserted     bigint      NOT NULL DEFAULT 0,
  batches_total            integer     NOT NULL DEFAULT 0,
  error_count_transient    integer     NOT NULL DEFAULT 0,
  error_count_fatal        integer     NOT NULL DEFAULT 0,
  retry_count              integer     NOT NULL DEFAULT 0,
  rate_limit_hits          integer     NOT NULL DEFAULT 0,
  host                     text        NOT NULL,
  contract_name            text        NOT NULL,
  contract_version         text        NOT NULL,
  run_params               jsonb       NOT NULL DEFAULT '{}'::jsonb,
  error_summary            text,
  created_at               timestamptz NOT NULL DEFAULT now(),

  UNIQUE (scraper_id, run_id),
  CHECK (status IN ('started','running','success','failed','timeout','aborted')),
  CHECK (items_extracted >= 0 AND items_valid_local >= 0 AND items_sent >= 0
         AND items_rejected_schema >= 0 AND items_final_inserted >= 0
         AND batches_total >= 0 AND retry_count >= 0
         AND error_count_transient >= 0 AND error_count_fatal >= 0
         AND rate_limit_hits >= 0)
);

COMMENT ON TABLE ops.scraper_runs IS
  '1 linha por execução. items_final_inserted = 0 sempre no MVP.';
COMMENT ON COLUMN ops.scraper_runs.items_final_inserted IS
  'Inseridos em DADO DE NEGÓCIO. Sempre 0 no MVP (nenhum endpoint escreve fora de ops.*).';

CREATE INDEX IF NOT EXISTS idx_runs_scraper_started
  ON ops.scraper_runs (scraper_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status_started
  ON ops.scraper_runs (status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_ended
  ON ops.scraper_runs (ended_at DESC) WHERE ended_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_runs_last_hb
  ON ops.scraper_runs (last_heartbeat_at DESC)
  WHERE status IN ('started','running');

-- ----------------------------------------------------------------------------
-- 3) ops.scraper_heartbeats
-- 1 linha por heartbeat. FK composta (scraper_id, run_id) → scraper_runs.
-- Retenção 30d (preparada, não ativa no MVP).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.scraper_heartbeats (
  id                      bigserial   PRIMARY KEY,
  run_id                  uuid        NOT NULL,
  scraper_id              text        NOT NULL,
  ts                      timestamptz NOT NULL DEFAULT now(),
  agent_id                text        NOT NULL DEFAULT 'default',
  items_collected_so_far  bigint      NOT NULL DEFAULT 0,
  items_per_minute        numeric(8,2),
  mem_mb                  integer,
  cpu_pct                 numeric(5,2),
  note                    text,

  UNIQUE (run_id, ts, agent_id),
  FOREIGN KEY (scraper_id, run_id)
    REFERENCES ops.scraper_runs(scraper_id, run_id)
    ON DELETE CASCADE
);

COMMENT ON TABLE ops.scraper_heartbeats IS
  'Heartbeats (1/min tipicamente). Retenção 30d preparada, não ativa no MVP.';

CREATE INDEX IF NOT EXISTS idx_heartbeats_run_ts
  ON ops.scraper_heartbeats (run_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_heartbeats_ts_cleanup
  ON ops.scraper_heartbeats (ts);

-- ----------------------------------------------------------------------------
-- 4) ops.scraper_events
-- Log estruturado. run_id pode ser NULL (evento fora de run).
-- FK composta usando ON DELETE SET NULL (run_id) — Postgres 15+ permite
-- set null em colunas específicas. Preserva evento histórico mesmo se run
-- for deletado (raro; runs são permanentes no MVP).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.scraper_events (
  event_id        uuid        PRIMARY KEY,
  run_id          uuid,
  scraper_id      text        NOT NULL,
  ts              timestamptz NOT NULL DEFAULT now(),
  level           text        NOT NULL DEFAULT 'info',
  code            text        NOT NULL,
  message         text        NOT NULL,
  payload_hash    varchar(64),
  payload_sample  text,
  payload_pointer text,
  created_at      timestamptz NOT NULL DEFAULT now(),

  CHECK (level IN ('info','warn','error','anomaly','audit')),
  CHECK (payload_sample IS NULL OR length(payload_sample) <= 1024),
  FOREIGN KEY (scraper_id, run_id)
    REFERENCES ops.scraper_runs(scraper_id, run_id)
    ON DELETE SET NULL (run_id)
);

COMMENT ON TABLE ops.scraper_events IS
  'Eventos estruturados (info/warn/error/anomaly/audit). run_id opcional. Retenção 30d preparada, não ativa.';

CREATE INDEX IF NOT EXISTS idx_events_scraper_ts
  ON ops.scraper_events (scraper_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_level
  ON ops.scraper_events (level, ts DESC)
  WHERE level IN ('error','anomaly');
CREATE INDEX IF NOT EXISTS idx_events_run
  ON ops.scraper_events (run_id, ts DESC)
  WHERE run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_ts_cleanup
  ON ops.scraper_events (ts);

-- ----------------------------------------------------------------------------
-- 5) ops.ingestion_batches
-- 1 linha por batch enviado. UNIQUE (scraper_id, run_id, batch_id) é target
-- de FKs compostas das tabelas filhas.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.ingestion_batches (
  batch_id                       uuid        PRIMARY KEY,
  run_id                         uuid        NOT NULL,
  scraper_id                     text        NOT NULL,
  seq                            integer     NOT NULL,
  started_at                     timestamptz NOT NULL DEFAULT now(),
  ended_at                       timestamptz,
  duration_ms                    bigint,
  items_count                    bigint      NOT NULL DEFAULT 0,
  items_final_inserted           bigint      NOT NULL DEFAULT 0,
  items_duplicate_intra          bigint      NOT NULL DEFAULT 0,
  items_duplicate_cross_run      bigint      NOT NULL DEFAULT 0,
  items_duplicate_cross_scraper  bigint      NOT NULL DEFAULT 0,
  items_rejected_schema          bigint      NOT NULL DEFAULT 0,
  delivery_target                text        NOT NULL DEFAULT 'ops',
  delivery_status                text        NOT NULL DEFAULT 'ok',
  retry_count                    integer     NOT NULL DEFAULT 0,
  created_at                     timestamptz NOT NULL DEFAULT now(),

  UNIQUE (scraper_id, run_id, batch_id),
  UNIQUE (run_id, seq),
  CHECK (delivery_target IN ('ops','dq_v3_stub','matching_stub','final_stub')),
  CHECK (delivery_status IN ('ok','failed','buffered','replayed')),
  CHECK (items_count >= 0 AND items_final_inserted >= 0
         AND items_duplicate_intra >= 0 AND items_duplicate_cross_run >= 0
         AND items_duplicate_cross_scraper >= 0 AND items_rejected_schema >= 0
         AND retry_count >= 0),
  FOREIGN KEY (scraper_id, run_id)
    REFERENCES ops.scraper_runs(scraper_id, run_id)
    ON DELETE CASCADE
);

COMMENT ON TABLE ops.ingestion_batches IS
  'Lotes de dados enviados. items_final_inserted = 0 no MVP. Target de FKs compostas.';
COMMENT ON COLUMN ops.ingestion_batches.items_final_inserted IS
  'Sempre 0 no MVP. Reservado para futura ingestão em dado de negócio.';

CREATE INDEX IF NOT EXISTS idx_batches_run_seq
  ON ops.ingestion_batches (run_id, seq);
CREATE INDEX IF NOT EXISTS idx_batches_scraper_started
  ON ops.ingestion_batches (scraper_id, started_at DESC);

-- ----------------------------------------------------------------------------
-- 6) ops.batch_metrics
-- Métricas granulares por batch. FK composta (scraper_id, run_id, batch_id).
-- Retenção 30d preparada, não ativa no MVP.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.batch_metrics (
  batch_id                  uuid        PRIMARY KEY,
  run_id                    uuid        NOT NULL,
  scraper_id                text        NOT NULL,
  ts                        timestamptz NOT NULL DEFAULT now(),
  items_extracted           bigint      NOT NULL DEFAULT 0,
  items_valid_local         bigint      NOT NULL DEFAULT 0,
  items_sent                bigint      NOT NULL DEFAULT 0,
  items_accepted_ready      bigint      NOT NULL DEFAULT 0,
  items_rejected_notwine    bigint      NOT NULL DEFAULT 0,
  items_needs_enrichment    bigint      NOT NULL DEFAULT 0,
  items_uncertain           bigint      NOT NULL DEFAULT 0,
  items_duplicate           bigint      NOT NULL DEFAULT 0,
  items_final_inserted      bigint      NOT NULL DEFAULT 0,
  items_errored_transport   bigint      NOT NULL DEFAULT 0,
  items_per_second          numeric(10,2),
  time_to_first_item_ms     bigint,
  field_coverage            jsonb       NOT NULL DEFAULT '{}'::jsonb,

  CHECK (items_final_inserted >= 0 AND items_extracted >= 0
         AND items_valid_local >= 0 AND items_sent >= 0
         AND items_accepted_ready >= 0 AND items_rejected_notwine >= 0
         AND items_needs_enrichment >= 0 AND items_uncertain >= 0
         AND items_duplicate >= 0 AND items_errored_transport >= 0),
  FOREIGN KEY (scraper_id, run_id, batch_id)
    REFERENCES ops.ingestion_batches(scraper_id, run_id, batch_id)
    ON DELETE CASCADE
);

COMMENT ON TABLE ops.batch_metrics IS
  'Métricas granulares por batch (funil, velocidade, coverage). Retenção 30d preparada, não ativa.';

CREATE INDEX IF NOT EXISTS idx_bm_scraper_ts
  ON ops.batch_metrics (scraper_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_bm_ts_cleanup
  ON ops.batch_metrics (ts);

-- ----------------------------------------------------------------------------
-- 7) ops.batch_metrics_hourly
-- Agregação horária. Populada por management command MANUAL no MVP (D-F0-05).
-- Retenção 180d preparada, não ativa.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.batch_metrics_hourly (
  scraper_id              text        NOT NULL
                                      REFERENCES ops.scraper_registry(scraper_id)
                                      ON DELETE CASCADE,
  hour_bucket             timestamptz NOT NULL,
  runs_total              integer     NOT NULL DEFAULT 0,
  batches_total           integer     NOT NULL DEFAULT 0,
  items_extracted         bigint      NOT NULL DEFAULT 0,
  items_sent              bigint      NOT NULL DEFAULT 0,
  items_final_inserted    bigint      NOT NULL DEFAULT 0,
  items_duplicate         bigint      NOT NULL DEFAULT 0,
  items_rejected_notwine  bigint      NOT NULL DEFAULT 0,
  errors_transient        integer     NOT NULL DEFAULT 0,
  errors_fatal            integer     NOT NULL DEFAULT 0,
  avg_items_per_second    numeric(10,2),
  updated_at              timestamptz NOT NULL DEFAULT now(),

  PRIMARY KEY (scraper_id, hour_bucket),
  CHECK (items_final_inserted >= 0 AND runs_total >= 0 AND batches_total >= 0
         AND items_extracted >= 0 AND items_sent >= 0
         AND items_duplicate >= 0 AND items_rejected_notwine >= 0
         AND errors_transient >= 0 AND errors_fatal >= 0)
);

COMMENT ON TABLE ops.batch_metrics_hourly IS
  'Agregação horária (stub no MVP — populada só via management command manual). items_final_inserted = 0.';

CREATE INDEX IF NOT EXISTS idx_bmh_hour
  ON ops.batch_metrics_hourly (hour_bucket DESC);

-- ----------------------------------------------------------------------------
-- 8) ops.contract_validation_errors
-- Erros de schema na fronteira. Sem FK composta (pode ocorrer antes do
-- registry/run existir). Regra em nível de endpoint (backend deriva
-- scraper_id e valida coerência).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.contract_validation_errors (
  id                bigserial   PRIMARY KEY,
  scraper_id        text        NOT NULL,
  run_id            uuid,
  batch_id          uuid,
  contract_name     text        NOT NULL,
  contract_version  text        NOT NULL,
  error_hash        varchar(64) NOT NULL,
  error_type        text        NOT NULL,
  error_message     text        NOT NULL,
  field_path        text,
  payload_sample    text,
  occurrences       integer     NOT NULL DEFAULT 1,
  first_seen        timestamptz NOT NULL DEFAULT now(),
  last_seen         timestamptz NOT NULL DEFAULT now(),

  UNIQUE (scraper_id, contract_name, contract_version, error_hash),
  CHECK (payload_sample IS NULL OR length(payload_sample) <= 1024)
);

COMMENT ON TABLE ops.contract_validation_errors IS
  'Erros de schema. UPSERT por (scraper_id, contract_name, contract_version, error_hash).';

CREATE INDEX IF NOT EXISTS idx_cve_scraper_last
  ON ops.contract_validation_errors (scraper_id, last_seen DESC);

-- ----------------------------------------------------------------------------
-- 9) ops.dq_decisions (STUB no MVP)
-- Stub para pipeline DQ V3 futuro. Não gravada no MVP.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.dq_decisions (
  decision_id   uuid        PRIMARY KEY,
  batch_id      uuid        NOT NULL,
  run_id        uuid        NOT NULL,
  scraper_id    text        NOT NULL,
  decision      text        NOT NULL,
  reason_code   text,
  items_count   bigint      NOT NULL DEFAULT 0,
  decided_at    timestamptz NOT NULL DEFAULT now(),
  notes         text,

  CHECK (decision IN ('ready','needs_enrichment','rejected_notwine','uncertain')),
  CHECK (items_count >= 0),
  FOREIGN KEY (scraper_id, run_id, batch_id)
    REFERENCES ops.ingestion_batches(scraper_id, run_id, batch_id)
    ON DELETE CASCADE
);

COMMENT ON TABLE ops.dq_decisions IS
  'STUB MVP. Decisões futuras do DQ V3 para commerce. Não gravada no MVP.';

CREATE INDEX IF NOT EXISTS idx_dq_decisions_batch
  ON ops.dq_decisions (batch_id);
CREATE INDEX IF NOT EXISTS idx_dq_decisions_scraper
  ON ops.dq_decisions (scraper_id, decided_at DESC);

-- ----------------------------------------------------------------------------
-- 10) ops.matching_decisions (STUB no MVP)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.matching_decisions (
  decision_id      uuid         PRIMARY KEY,
  batch_id         uuid         NOT NULL,
  run_id           uuid         NOT NULL,
  scraper_id       text         NOT NULL,
  external_id      text,
  matched_wine_id  integer,
  match_status     text         NOT NULL,
  confidence       numeric(4,3),
  strategy         text,
  decided_at       timestamptz  NOT NULL DEFAULT now(),

  CHECK (match_status IN ('matched','pending','not_found','ambiguous','skipped')),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  FOREIGN KEY (scraper_id, run_id, batch_id)
    REFERENCES ops.ingestion_batches(scraper_id, run_id, batch_id)
    ON DELETE CASCADE
);

COMMENT ON TABLE ops.matching_decisions IS
  'STUB MVP. matched_wine_id é ponteiro solto (sem FK para public.wines). Isolamento de schema.';

CREATE INDEX IF NOT EXISTS idx_match_batch
  ON ops.matching_decisions (batch_id);
CREATE INDEX IF NOT EXISTS idx_match_status
  ON ops.matching_decisions (match_status, decided_at DESC);

-- ----------------------------------------------------------------------------
-- 11) ops.final_apply_results (STUB no MVP)
-- Resultado de futura gravação em dado de negócio.
-- No MVP, nada grava aqui (adapters são observacionais).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.final_apply_results (
  apply_id              uuid        PRIMARY KEY,
  batch_id              uuid        NOT NULL,
  run_id                uuid        NOT NULL,
  scraper_id            text        NOT NULL,
  target_table          text        NOT NULL,
  items_final_inserted  bigint      NOT NULL DEFAULT 0,
  items_final_updated   bigint      NOT NULL DEFAULT 0,
  items_final_rejected  bigint      NOT NULL DEFAULT 0,
  error_count           bigint      NOT NULL DEFAULT 0,
  applied_at            timestamptz NOT NULL DEFAULT now(),

  CHECK (items_final_inserted >= 0 AND items_final_updated >= 0
         AND items_final_rejected >= 0 AND error_count >= 0),
  FOREIGN KEY (scraper_id, run_id, batch_id)
    REFERENCES ops.ingestion_batches(scraper_id, run_id, batch_id)
    ON DELETE CASCADE
);

COMMENT ON TABLE ops.final_apply_results IS
  'STUB MVP. Registro de futura gravação em dado de negócio. MVP nunca escreve aqui.';

CREATE INDEX IF NOT EXISTS idx_apply_batch
  ON ops.final_apply_results (batch_id);
CREATE INDEX IF NOT EXISTS idx_apply_target
  ON ops.final_apply_results (target_table, applied_at DESC);

-- ----------------------------------------------------------------------------
-- 12) ops.source_lineage
-- Rastro origem→destino. FK composta. Retenção permanente.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.source_lineage (
  batch_id             uuid        PRIMARY KEY,
  run_id               uuid        NOT NULL,
  scraper_id           text        NOT NULL,
  source_system        text        NOT NULL,
  source_kind          text        NOT NULL,
  source_pointer       text        NOT NULL,
  source_record_count  bigint,
  source_read_at       timestamptz NOT NULL DEFAULT now(),
  notes                text,

  CHECK (source_kind IN ('table','file','api','stream','manual','synthetic')),
  FOREIGN KEY (scraper_id, run_id, batch_id)
    REFERENCES ops.ingestion_batches(scraper_id, run_id, batch_id)
    ON DELETE CASCADE
);

COMMENT ON TABLE ops.source_lineage IS
  'Rastro origem→destino. Permanente (auditoria). source_kind inclui synthetic.';

CREATE INDEX IF NOT EXISTS idx_lineage_scraper_read
  ON ops.source_lineage (scraper_id, source_read_at DESC);

-- ----------------------------------------------------------------------------
-- 13) ops.scraper_alerts
-- Alertas P1/P2/P3. MVP: só dashboard, sem envio externo.
-- dedup_key é determinístico (D-F0-08).
-- Endpoint /ops/alerts/ack NÃO existe no MVP (D-F0-03).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.scraper_alerts (
  alert_id         uuid         PRIMARY KEY,
  scraper_id       text,
  run_id           uuid,
  priority         text         NOT NULL,
  code             text         NOT NULL,
  scope_key        text         NOT NULL,
  title            text         NOT NULL,
  description      text,
  dedup_key        varchar(64)  NOT NULL UNIQUE,
  occurrences      integer      NOT NULL DEFAULT 1,
  status           text         NOT NULL DEFAULT 'open',
  first_seen       timestamptz  NOT NULL DEFAULT now(),
  last_seen        timestamptz  NOT NULL DEFAULT now(),
  acknowledged_at  timestamptz,
  resolved_at      timestamptz,
  needs_human      boolean      NOT NULL DEFAULT false,

  CHECK (priority IN ('P1','P2','P3')),
  CHECK (status IN ('open','acknowledged','resolved','suppressed')),
  CHECK (description IS NULL OR length(description) <= 4096)
);

COMMENT ON TABLE ops.scraper_alerts IS
  'Alertas. MVP: sem envio externo (OPS_ALERTS_ENABLED=false). Sem endpoint /ack no MVP. dedup_key determinístico.';

CREATE INDEX IF NOT EXISTS idx_alerts_status_last
  ON ops.scraper_alerts (status, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_scraper_priority
  ON ops.scraper_alerts (scraper_id, priority, last_seen DESC);

-- ----------------------------------------------------------------------------
-- 14) ops.scraper_configs
-- Overrides online por scraper. Precedência: config > manifesto > default.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.scraper_configs (
  scraper_id   text        NOT NULL
                           REFERENCES ops.scraper_registry(scraper_id)
                           ON DELETE CASCADE,
  key          text        NOT NULL,
  value        jsonb       NOT NULL,
  updated_by   text        NOT NULL,
  updated_at   timestamptz NOT NULL DEFAULT now(),
  note         text,

  PRIMARY KEY (scraper_id, key)
);

COMMENT ON TABLE ops.scraper_configs IS
  'Overrides online por scraper. MVP: só cadastro via SQL admin, sem endpoint de edição.';

-- ============================================================================
-- Verificação final (opcional — usada pelos testes).
-- ============================================================================
-- SELECT count(*) FROM information_schema.tables WHERE table_schema='ops';
-- Esperado: 14.

COMMIT;
