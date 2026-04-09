-- ROLLBACK DO PILOTO DE ALIASES
-- Remove exatamente os 10 aliases inseridos pelo piloto.
--
-- Para executar:
--   psql $DATABASE_URL -f reports/rollback_alias_pilot.sql

BEGIN;

DELETE FROM wine_aliases
WHERE source_wine_id IN (
    1796520, 1803853, 1806948, 1792269, 1818495,
    2261784, 2261780, 2261782, 2261778, 1743048
)
AND source_type = 'manual'
AND review_status = 'approved';

COMMIT;

-- Verificar: deve retornar 0
SELECT COUNT(*) FROM wine_aliases
WHERE source_wine_id IN (
    1796520, 1803853, 1806948, 1792269, 1818495,
    2261784, 2261780, 2261782, 2261778, 1743048
);
