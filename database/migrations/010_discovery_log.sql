-- Discovery log: registra tentativas de resolucao por canal
CREATE TABLE IF NOT EXISTS discovery_log (
    id SERIAL PRIMARY KEY,
    session_id TEXT,
    source_channel TEXT NOT NULL,
    raw_name TEXT NOT NULL,
    raw_producer TEXT,
    extras JSONB DEFAULT '{}'::jsonb,
    enrichment_raw JSONB,
    resolved_wine_id INTEGER REFERENCES wines(id) ON DELETE SET NULL,
    final_status TEXT NOT NULL,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discovery_status ON discovery_log(final_status);
CREATE INDEX IF NOT EXISTS idx_discovery_created ON discovery_log(created_at);
CREATE INDEX IF NOT EXISTS idx_discovery_channel ON discovery_log(source_channel);
