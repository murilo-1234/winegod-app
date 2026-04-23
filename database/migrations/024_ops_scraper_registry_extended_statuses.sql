-- ============================================================================
-- Migration 024: extend ops.scraper_registry status taxonomy
-- ============================================================================
-- Pos-MVP control plane: permite registrar scrapers observados, planejados
-- e bloqueados de forma honesta, sem mascarar como "failed" ou "registered".
-- Nao toca tabelas de negocio.
-- ============================================================================

BEGIN;

ALTER TABLE ops.scraper_registry
  DROP CONSTRAINT IF EXISTS scraper_registry_status_check;

ALTER TABLE ops.scraper_registry
  ADD CONSTRAINT scraper_registry_status_check
  CHECK (
    status IN (
      'draft',
      'registered',
      'observed',
      'registered_planned',
      'blocked_external_host',
      'blocked_missing_source',
      'blocked_contract_missing',
      'contract_validated',
      'active',
      'paused',
      'stale',
      'error',
      'blocked_quality',
      'deprecated'
    )
  );

COMMIT;
