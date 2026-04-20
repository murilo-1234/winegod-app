-- Rollback gerado automaticamente antes do alias suppress
BEGIN;
UPDATE wines SET suppressed_at = NULL, suppress_reason = NULL WHERE suppress_reason = 'd18_alias_suppress_20260419_224202';
COMMIT;
