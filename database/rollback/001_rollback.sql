-- Rollback da migracao 001: remover campos do WineGod Score
-- CUIDADO: isso apaga dados dessas colunas permanentemente

ALTER TABLE wines DROP COLUMN IF EXISTS winegod_score;
ALTER TABLE wines DROP COLUMN IF EXISTS winegod_score_type;
ALTER TABLE wines DROP COLUMN IF EXISTS winegod_score_components;
ALTER TABLE wines DROP COLUMN IF EXISTS nota_wcf;
-- NAO remover nome_normalizado — ja existia antes da migracao
ALTER TABLE wines DROP COLUMN IF EXISTS confianca_nota;
