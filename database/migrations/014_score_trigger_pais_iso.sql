-- 014_score_trigger_pais_iso.sql
-- Migra trigger de score recalc: monitora 'pais' (ISO) em vez de 'pais_nome'.
-- Motivo: pais (ISO) e o campo canonico. pais_nome passa a ser apenas display.
-- Isso tambem evita que backfills em pais_nome gerem avalanche na fila de recalculo.

CREATE OR REPLACE FUNCTION fn_enqueue_score_recalc()
RETURNS trigger AS $$
BEGIN
    -- INSERT: enfileira se o vinho novo tem dados relevantes para score
    IF TG_OP = 'INSERT' THEN
        IF NEW.preco_min IS NOT NULL
           OR NEW.nota_wcf IS NOT NULL
           OR (NEW.vivino_rating IS NOT NULL AND NEW.vivino_rating > 0)
        THEN
            INSERT INTO score_recalc_queue (wine_id, reason)
            VALUES (NEW.id, 'trigger_insert')
            ON CONFLICT (wine_id) WHERE processed_at IS NULL DO NOTHING;
        END IF;
        RETURN NEW;
    END IF;

    -- UPDATE: so enfileira se campo que afeta score mudou
    IF TG_OP = 'UPDATE' THEN
        IF (OLD.preco_min IS DISTINCT FROM NEW.preco_min)
           OR (OLD.moeda IS DISTINCT FROM NEW.moeda)
           OR (OLD.nota_wcf IS DISTINCT FROM NEW.nota_wcf)
           OR (OLD.nota_wcf_sample_size IS DISTINCT FROM NEW.nota_wcf_sample_size)
           OR (OLD.vivino_rating IS DISTINCT FROM NEW.vivino_rating)
           OR (OLD.pais IS DISTINCT FROM NEW.pais)
        THEN
            INSERT INTO score_recalc_queue (wine_id, reason)
            VALUES (NEW.id, 'trigger_update')
            ON CONFLICT (wine_id) WHERE processed_at IS NULL DO NOTHING;
        END IF;
        RETURN NEW;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recriar trigger (mesma assinatura, funcao atualizada)
DROP TRIGGER IF EXISTS trg_score_recalc ON wines;

CREATE TRIGGER trg_score_recalc
    AFTER INSERT OR UPDATE ON wines
    FOR EACH ROW
    EXECUTE FUNCTION fn_enqueue_score_recalc();

COMMENT ON FUNCTION fn_enqueue_score_recalc IS
    'Enfileira wine_id para recalculo de score quando preco/nota/pais(ISO) mudam (INSERT + UPDATE, com dedup)';
