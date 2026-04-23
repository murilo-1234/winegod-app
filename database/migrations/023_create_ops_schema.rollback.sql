-- ============================================================================
-- Migration 023 ROLLBACK: drop_ops_schema
-- ============================================================================
-- Remove o schema `ops` e TODAS as suas 14 tabelas, índices e constraints.
-- Zero impacto no resto do banco (schema isolado).
--
-- AVISO: Usar apenas enquanto só houver dados do canário sintético.
-- Depois que adapters observacionais reais escreverem em ops.*, este
-- rollback apaga auditoria — use feature flag OPS_WRITE_ENABLED=false
-- em vez disso.
-- ============================================================================

BEGIN;

DROP SCHEMA IF EXISTS ops CASCADE;

COMMIT;
