-- 007_add_score_recalc_trigger.sql
-- Trigger que enfileira recalculo de score quando campos relevantes mudam.
-- Funciona independente de qual script/repo fez o UPDATE.

CREATE OR REPLACE FUNCTION fn_enqueue_score_recalc()
RETURNS trigger AS $$
BEGIN
    -- So enfileira se algum campo relevante para o score mudou
    IF (OLD.preco_min IS DISTINCT FROM NEW.preco_min)
       OR (OLD.moeda IS DISTINCT FROM NEW.moeda)
       OR (OLD.nota_wcf IS DISTINCT FROM NEW.nota_wcf)
       OR (OLD.nota_wcf_sample_size IS DISTINCT FROM NEW.nota_wcf_sample_size)
       OR (OLD.vivino_rating IS DISTINCT FROM NEW.vivino_rating)
       OR (OLD.pais_nome IS DISTINCT FROM NEW.pais_nome)
    THEN
        INSERT INTO score_recalc_queue (wine_id, reason)
        VALUES (NEW.id, 'trigger_update');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop se existir para recriar limpo
DROP TRIGGER IF EXISTS trg_score_recalc ON wines;

CREATE TRIGGER trg_score_recalc
    AFTER UPDATE ON wines
    FOR EACH ROW
    EXECUTE FUNCTION fn_enqueue_score_recalc();

COMMENT ON FUNCTION fn_enqueue_score_recalc IS 'Enfileira wine_id para recalculo de score quando preco/nota/pais mudam';
