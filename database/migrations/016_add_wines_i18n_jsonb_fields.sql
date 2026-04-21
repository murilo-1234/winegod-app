-- 016_add_wines_i18n_jsonb_fields.sql
-- F1.5 do rollout multilingue WineGod.
-- Adiciona campos i18n em wines: description_i18n e tasting_notes_i18n (JSONB).
-- Migration leve, aditiva, idempotente. Sem NOT NULL. Sem indice. Sem backfill.
-- Nao altera queries existentes; o JSONB default '{}' e seguro para leitura.

ALTER TABLE wines
ADD COLUMN IF NOT EXISTS description_i18n JSONB DEFAULT '{}'::jsonb;

ALTER TABLE wines
ADD COLUMN IF NOT EXISTS tasting_notes_i18n JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN wines.description_i18n IS
    'Descricao do vinho por locale (Tier 1: pt-BR, en-US, es-419, fr-FR). Formato: {"<locale>": "<texto>"}. Default {} vazio.';

COMMENT ON COLUMN wines.tasting_notes_i18n IS
    'Notas de degustacao por locale (Tier 1: pt-BR, en-US, es-419, fr-FR). Formato: {"<locale>": "<texto>"}. Default {} vazio.';
