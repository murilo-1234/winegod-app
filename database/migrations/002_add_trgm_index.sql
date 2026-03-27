-- Habilitar pg_trgm para busca fuzzy
-- Data: 2026-03-27

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Indice trigram no nome normalizado (para busca fuzzy)
CREATE INDEX IF NOT EXISTS idx_wines_nome_trgm
ON wines USING gin (nome_normalizado gin_trgm_ops);

-- Indice trigram no nome original tambem (fallback)
CREATE INDEX IF NOT EXISTS idx_wines_nome_original_trgm
ON wines USING gin (nome gin_trgm_ops);

-- Configurar threshold de similaridade
-- 0.3 e bom para vinhos (nomes longos, muita variacao)
ALTER DATABASE winegod SET pg_trgm.similarity_threshold = 0.3;
