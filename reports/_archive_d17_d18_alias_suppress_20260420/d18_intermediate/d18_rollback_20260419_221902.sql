-- Rollback gerado automaticamente antes do D18 apply em 20260419_221902
BEGIN;
DELETE FROM wine_aliases
WHERE review_status = 'approved'
  AND source_type = 'd17_20260419_221902';
COMMIT;
