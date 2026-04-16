-- Migration 013: Create wine_context_buckets for Cascata B (nota_wcf v2)
-- Aditiva, nao destrutiva. Pode ser aplicada multiplas vezes (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS wine_context_buckets (
    id SERIAL PRIMARY KEY,
    bucket_level VARCHAR(30) NOT NULL,
    bucket_key TEXT NOT NULL,
    bucket_n INTEGER NOT NULL DEFAULT 0,
    nota_base NUMERIC(4,3),
    bucket_stddev NUMERIC(4,3),
    delta_contextual NUMERIC(4,3),
    delta_n INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(bucket_level, bucket_key)
);

CREATE INDEX IF NOT EXISTS idx_wcb_level_key ON wine_context_buckets(bucket_level, bucket_key);
