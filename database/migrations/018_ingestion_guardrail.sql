-- Migration 018: Ingestion Guardrail (DQ V3 - Escopo 1 + 2)
--
-- Objetivo: preparar o endpoint POST /api/ingest/bulk para upload grande
-- futuro (Amazon/marketplaces, ate ~1M items) com:
--   1. Coluna `ingestion_run_id` em `wines` e `wine_sources` para tracking
--      e rollback granular por run.
--   2. Tabela `ingestion_run_log` para auditoria de cada execucao.
--   3. Tabela `not_wine_rejections` para persistir NOT_WINE filtrados.
--   4. Tabela `ingestion_review_queue` (placeholder para Escopo 4 futuro;
--      nao usada pelo bulk_ingest deste patch).
--
-- Idempotente: usa IF NOT EXISTS em todas as operacoes.
-- Read-only ate aplicacao explicita via `psql -f ...`.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Colunas de tracking em wines e wine_sources
-- ---------------------------------------------------------------------------
ALTER TABLE wines
  ADD COLUMN IF NOT EXISTS ingestion_run_id TEXT;

ALTER TABLE wine_sources
  ADD COLUMN IF NOT EXISTS ingestion_run_id TEXT;

CREATE INDEX IF NOT EXISTS idx_wines_ingestion_run_id
  ON wines(ingestion_run_id)
  WHERE ingestion_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_wine_sources_ingestion_run_id
  ON wine_sources(ingestion_run_id)
  WHERE ingestion_run_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 2. Log de runs de ingestao
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion_run_log (
    id                      SERIAL PRIMARY KEY,
    run_id                  TEXT UNIQUE NOT NULL,
    source                  TEXT NOT NULL,
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at             TIMESTAMPTZ,
    dry_run                 BOOLEAN NOT NULL DEFAULT FALSE,

    received                INT,
    valid                   INT,
    duplicates_in_input     INT,

    -- wines
    would_insert            INT,
    would_update            INT,
    inserted                INT,
    updated                 INT,

    -- wine_sources
    sources_in_input        INT,
    sources_duplicates_in_input INT,
    sources_rejected_count  INT,
    would_insert_sources    INT,
    would_update_sources    INT,
    sources_inserted        INT,
    sources_updated         INT,

    -- NOT_WINE / errors
    filtered_notwine        INT,
    rejected                INT,
    errors                  INT,

    params                  JSONB
);

CREATE INDEX IF NOT EXISTS idx_run_log_started
  ON ingestion_run_log(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_log_source
  ON ingestion_run_log(source);

-- ---------------------------------------------------------------------------
-- 3. NOT_WINE rejections persistidas
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS not_wine_rejections (
    id               SERIAL PRIMARY KEY,
    run_id           TEXT,
    source           TEXT,
    index_in_payload INT,
    nome             TEXT,
    produtor         TEXT,
    reason           TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notwine_run
  ON not_wine_rejections(run_id);
CREATE INDEX IF NOT EXISTS idx_notwine_created
  ON not_wine_rejections(created_at DESC);

-- ---------------------------------------------------------------------------
-- 4. Review queue (PLACEHOLDER para Escopo 4 futuro).
--
-- ATENCAO: esta tabela e criada aqui para estar pronta quando o tier fuzzy
-- for implementado. O bulk_ingest do Escopo 1+2 NAO escreve nela ainda.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion_review_queue (
    id                  SERIAL PRIMARY KEY,
    run_id              TEXT,
    source              TEXT,
    source_payload      JSONB NOT NULL,
    match_tier          TEXT NOT NULL,
    candidate_wine_ids  INTEGER[] NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
    reviewed_by         TEXT,
    reviewed_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_queue_status
  ON ingestion_review_queue(status);
CREATE INDEX IF NOT EXISTS idx_review_queue_run
  ON ingestion_review_queue(run_id);

-- ---------------------------------------------------------------------------
-- Comentarios de documentacao
-- ---------------------------------------------------------------------------
COMMENT ON COLUMN wines.ingestion_run_id IS
  'run_id da ultima ingestao bulk que tocou este wine; usado para rollback granular por run.';
COMMENT ON COLUMN wine_sources.ingestion_run_id IS
  'run_id da ultima ingestao bulk que criou/atualizou esta source.';
COMMENT ON TABLE ingestion_run_log IS
  'Auditoria de cada execucao do bulk_ingest (dry-run ou apply).';
COMMENT ON TABLE not_wine_rejections IS
  'Registros filtrados como NOT_WINE antes de chegar em wines (scripts/pre_ingest_filter).';
COMMENT ON TABLE ingestion_review_queue IS
  'PLACEHOLDER: fila de revisao humana para matches fuzzy (Escopo 4, nao ativa ainda).';

COMMIT;
