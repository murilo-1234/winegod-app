-- 006_add_score_recalc_queue.sql
-- Fila de recalculo de score: enfileira wine_ids quando campos que afetam score mudam.

CREATE TABLE IF NOT EXISTS score_recalc_queue (
    id SERIAL PRIMARY KEY,
    wine_id INTEGER NOT NULL,
    reason VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP,
    CONSTRAINT fk_wine FOREIGN KEY (wine_id) REFERENCES wines(id)
);

CREATE INDEX IF NOT EXISTS idx_recalc_pending ON score_recalc_queue (created_at)
    WHERE processed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_recalc_wine ON score_recalc_queue (wine_id);

COMMENT ON TABLE score_recalc_queue IS 'Fila de recalculo incremental de winegod_score';
