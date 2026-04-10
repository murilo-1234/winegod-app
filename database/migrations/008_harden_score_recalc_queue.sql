-- 008_harden_score_recalc_queue.sql
-- Evolui score_recalc_queue criada em 006: adiciona attempts, last_error,
-- e indice unico parcial para deduplicacao de pendentes.
-- Nao-destrutiva: so adiciona colunas e indice a tabela existente.

-- Coluna de tentativas (max retries controlado pelo worker)
ALTER TABLE score_recalc_queue ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;

-- Ultima mensagem de erro (util para debug)
ALTER TABLE score_recalc_queue ADD COLUMN IF NOT EXISTS last_error TEXT;

-- Indice unico parcial: no maximo 1 entrada pendente por wine_id.
-- O trigger e os helpers usam ON CONFLICT neste indice para dedup.
CREATE UNIQUE INDEX IF NOT EXISTS idx_recalc_pending_dedup
    ON score_recalc_queue (wine_id)
    WHERE processed_at IS NULL;
