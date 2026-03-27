-- Indices para queries frequentes do chat
-- Data: 2026-03-27

-- Busca por pais + rating (ranking por pais)
CREATE INDEX IF NOT EXISTS idx_wines_pais_rating
ON wines (pais, vivino_rating DESC NULLS LAST);

-- Busca por tipo (tinto, branco, etc) + rating
CREATE INDEX IF NOT EXISTS idx_wines_tipo_rating
ON wines (tipo, vivino_rating DESC NULLS LAST);

-- Busca por regiao
CREATE INDEX IF NOT EXISTS idx_wines_regiao
ON wines (regiao) WHERE regiao IS NOT NULL;

-- Busca por faixa de preco
CREATE INDEX IF NOT EXISTS idx_wines_preco_min
ON wines (preco_min) WHERE preco_min IS NOT NULL;

-- Busca por winegod_score (quando estiver populado)
CREATE INDEX IF NOT EXISTS idx_wines_wg_score
ON wines (winegod_score DESC NULLS LAST) WHERE winegod_score IS NOT NULL;

-- Busca por score_type
CREATE INDEX IF NOT EXISTS idx_wines_score_type
ON wines (winegod_score_type) WHERE winegod_score_type != 'none';

-- Indice composto para ranking custo-beneficio por pais
CREATE INDEX IF NOT EXISTS idx_wines_pais_wgscore
ON wines (pais, winegod_score DESC NULLS LAST) WHERE winegod_score IS NOT NULL;

-- Vivino ID para cross-reference (JA EXISTE idx_wines_vivino_id — seguro com IF NOT EXISTS)
CREATE INDEX IF NOT EXISTS idx_wines_vivino_id
ON wines (vivino_id) WHERE vivino_id IS NOT NULL;
