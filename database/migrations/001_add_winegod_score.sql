-- WineGod Score — campos novos na tabela wines
-- Executar com cuidado: tabela tem 1.72M registros
-- Data: 2026-03-27
-- NOTA: nome_normalizado ja existe e esta populado

-- 1. Score final (custo-beneficio) — escala 0 a 5, 2 casas decimais
ALTER TABLE wines ADD COLUMN IF NOT EXISTS winegod_score DECIMAL(3,2);

-- 2. Tipo do score: se a nota e verificada (100+ reviews) ou estimada (0-99)
-- 'verified' = nota WCF pura (100+ reviews)
-- 'estimated' = nota estimada por IA (0-99 reviews)
-- 'none' = sem dados suficientes
ALTER TABLE wines ADD COLUMN IF NOT EXISTS winegod_score_type VARCHAR(20) DEFAULT 'none';

-- 3. Componentes do score (quais termos proprietarios ativaram)
-- Exemplo: {"paridade": true, "legado": true, "capilaridade": false, "avaliacoes": true}
ALTER TABLE wines ADD COLUMN IF NOT EXISTS winegod_score_components JSONB DEFAULT '{}';

-- 4. Nota WCF (Weighted Collaborative Filtering) — qualidade pura, sem preco
-- Escala 0 a 5. Esta e a "nota do vinho", diferente do "score" (custo-beneficio)
ALTER TABLE wines ADD COLUMN IF NOT EXISTS nota_wcf DECIMAL(3,2);

-- 5. Nome normalizado para deduplicacao e busca (JA EXISTE — seguro com IF NOT EXISTS)
ALTER TABLE wines ADD COLUMN IF NOT EXISTS nome_normalizado TEXT;

-- 6. Confianca da nota (0.0 a 1.0)
-- 1.0 = nota verificada com muitos reviews
-- 0.5 = nota estimada com alguns dados
-- 0.1 = nota estimada com poucos dados
ALTER TABLE wines ADD COLUMN IF NOT EXISTS confianca_nota DECIMAL(3,2);

-- Comentarios para documentacao
COMMENT ON COLUMN wines.winegod_score IS 'WineGod Score: custo-beneficio, escala 0-5';
COMMENT ON COLUMN wines.winegod_score_type IS 'verified (100+ reviews), estimated (0-99), none';
COMMENT ON COLUMN wines.winegod_score_components IS 'Termos proprietarios: paridade, legado, capilaridade, avaliacoes';
COMMENT ON COLUMN wines.nota_wcf IS 'Nota WCF: qualidade pura sem preco, escala 0-5';
COMMENT ON COLUMN wines.nome_normalizado IS 'Nome normalizado para dedup e busca fuzzy';
COMMENT ON COLUMN wines.confianca_nota IS 'Confianca da nota: 0.0 (nenhuma) a 1.0 (total)';
