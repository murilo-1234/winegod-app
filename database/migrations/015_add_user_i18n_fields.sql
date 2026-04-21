-- 015: Add i18n fields to users (ui_locale, market_country, currency_override)
--
-- F1.4 do rollout multilingue WineGod.
-- Migration aditiva e idempotente: pode ser re-executada em LOCAL sem efeito
-- colateral. Em producao, seguir REGRA 7 do CLAUDE.md (deploy manual).
--
-- Nao adiciona NOT NULL nesta fase. Forward-fix preenche NULLs existentes.
-- Constraint de whitelist de locales adicionada via DO block idempotente.

ALTER TABLE users
ADD COLUMN IF NOT EXISTS ui_locale TEXT DEFAULT 'pt-BR';

ALTER TABLE users
ADD COLUMN IF NOT EXISTS market_country TEXT DEFAULT 'BR';

ALTER TABLE users
ADD COLUMN IF NOT EXISTS currency_override TEXT;

-- Forward-fix: preencher ui_locale/market_country em linhas legadas que
-- possam ter sido criadas com NULL antes do DEFAULT entrar em vigor.
-- Idempotente: WHERE ... IS NULL faz a operacao ser no-op em reexecucao.
UPDATE users SET ui_locale = 'pt-BR' WHERE ui_locale IS NULL;
UPDATE users SET market_country = 'BR' WHERE market_country IS NULL;

-- Constraint de whitelist de ui_locale (Tier 1: pt-BR, en-US, es-419, fr-FR).
-- Postgres nao tem ADD CONSTRAINT IF NOT EXISTS universal; usamos DO block
-- consultando pg_constraint para garantir idempotencia.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'users_ui_locale_check'
          AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE users
        ADD CONSTRAINT users_ui_locale_check
        CHECK (ui_locale IN ('pt-BR', 'en-US', 'es-419', 'fr-FR'));
    END IF;
END $$;
