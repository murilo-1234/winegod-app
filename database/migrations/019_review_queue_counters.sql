-- Migration 019: Review Queue Counters + Fuzzy K3 Index (DQ V3 - Escopo 4)
--
-- Complemento da 018. Adiciona:
--   1. Contadores em `ingestion_run_log` para o ciclo do review (enqueue,
--      auto_merge_strict, approved_merge, approved_new, rejected_review,
--      blocked).
--   2. Indice parcial composto para lookup fuzzy K3 no pipeline de ingestao.
--
-- Idempotente: IF NOT EXISTS em tudo.
-- NAO aplicar automaticamente. Aplicar via protocolo DB_CLEAR + apply + validate.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Contadores novos em ingestion_run_log
-- ---------------------------------------------------------------------------
ALTER TABLE ingestion_run_log
  ADD COLUMN IF NOT EXISTS enqueued_review INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS auto_merge_strict INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS approved_merge INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS approved_new INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rejected_review INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS blocked TEXT;

COMMENT ON COLUMN ingestion_run_log.enqueued_review IS
  'Total de itens enfileirados em ingestion_review_queue por este run.';
COMMENT ON COLUMN ingestion_run_log.auto_merge_strict IS
  'Itens que passaram fuzzy K3 estrito (1 candidato, prefixo claro de produtor, sem conflito de safra) e foram consolidados via UPDATE no canonical.';
COMMENT ON COLUMN ingestion_run_log.approved_merge IS
  'Aprovacoes manuais tipo approve_merge posteriormente (incrementado pelo endpoint /ingest/review).';
COMMENT ON COLUMN ingestion_run_log.approved_new IS
  'Aprovacoes manuais tipo approve_new.';
COMMENT ON COLUMN ingestion_run_log.rejected_review IS
  'Rejeicoes manuais via endpoint /ingest/review.';
COMMENT ON COLUMN ingestion_run_log.blocked IS
  'Preenchido com BLOCKED_QUEUE_EXPLOSION se o cut-off defensivo do Escopo 4 disparou. Nesse caso nenhum write foi feito.';

-- ---------------------------------------------------------------------------
-- 2. Indice composto parcial para fuzzy K3 lookup
--
-- Lookup usado no pipeline (apenas quando item nao bateu em hash nem tripla):
--   SELECT id, produtor_normalizado, safra, nome_normalizado_sem_safra, pais, tipo
--   FROM wines
--   WHERE (nome_normalizado_sem_safra, pais, tipo) IN (...)
--     AND vivino_id IS NOT NULL
--     AND suppressed_at IS NULL;
--
-- Sem este indice, query ficaria full scan em ~1.7M canonicals por batch.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_wines_fuzzy_k3_canonical
  ON wines(nome_normalizado_sem_safra, pais, tipo)
  WHERE vivino_id IS NOT NULL AND suppressed_at IS NULL;

COMMIT;
