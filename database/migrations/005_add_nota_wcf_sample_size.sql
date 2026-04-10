-- 005_add_nota_wcf_sample_size.sql
-- Adiciona coluna para persistir quantas reviews individuais entraram no calculo WCF.
-- Necessario para a regra canonica de nota (verified vs estimated vs fallback).

ALTER TABLE wines ADD COLUMN IF NOT EXISTS nota_wcf_sample_size INTEGER;

COMMENT ON COLUMN wines.nota_wcf_sample_size IS 'Quantidade de reviews individuais usadas no calculo WCF';
