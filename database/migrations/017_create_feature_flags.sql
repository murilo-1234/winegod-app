-- 017_create_feature_flags.sql
-- F1.6 do rollout multilingue WineGod.
-- Cria tabela feature_flags (kill switch Plano A decidido em F0.6).
-- Leitura em runtime pelo backend vira em F1.8 (endpoint GET /api/config/enabled-locales).
-- Migration idempotente: CREATE TABLE IF NOT EXISTS + INSERT ... ON CONFLICT DO NOTHING.
-- Nao cria indice extra, nao cria trigger, nao cria constraint alem da PRIMARY KEY.

CREATE TABLE IF NOT EXISTS feature_flags (
    key TEXT PRIMARY KEY,
    value_json JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by TEXT
);

-- Seed inicial: apenas pt-BR habilitado.
-- en-US, es-419 e fr-FR ficam desligados ate canario progressivo (Onda 10).
INSERT INTO feature_flags (key, value_json, description, updated_by)
VALUES (
    'enabled_locales',
    '["pt-BR"]'::jsonb,
    'Locales ativos em producao. Kill switch.',
    'migration_017'
)
ON CONFLICT (key) DO NOTHING;
