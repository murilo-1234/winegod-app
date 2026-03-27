-- Rollback da migracao 002: remover pg_trgm e indices trigram

DROP INDEX IF EXISTS idx_wines_nome_trgm;
DROP INDEX IF EXISTS idx_wines_nome_original_trgm;

-- Resetar threshold
ALTER DATABASE winegod RESET pg_trgm.similarity_threshold;

-- Remover extensao (so se nenhuma outra dependencia existir)
DROP EXTENSION IF EXISTS pg_trgm;
