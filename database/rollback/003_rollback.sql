-- Rollback da migracao 003: remover indices de performance

DROP INDEX IF EXISTS idx_wines_pais_rating;
DROP INDEX IF EXISTS idx_wines_tipo_rating;
DROP INDEX IF EXISTS idx_wines_regiao;
DROP INDEX IF EXISTS idx_wines_preco_min;
DROP INDEX IF EXISTS idx_wines_wg_score;
DROP INDEX IF EXISTS idx_wines_score_type;
DROP INDEX IF EXISTS idx_wines_pais_wgscore;
-- NAO remover idx_wines_vivino_id — ja existia antes da migracao
