-- PILOTO DE ALIASES — 10 pares manualmente aprovados
-- PRE-REQUISITO: tabela wine_aliases ja deve existir no Render
-- (rodar C:\winegod\migrations\003_wine_aliases.sql primeiro)
--
-- Para aplicar:
--   psql $DATABASE_URL -f reports/apply_alias_pilot.sql
--
-- Para reverter:
--   psql $DATABASE_URL -f reports/rollback_alias_pilot.sql

BEGIN;

-- Lock timeout curto: abortar se travar em lock
SET LOCAL lock_timeout = '5s';

INSERT INTO wine_aliases (source_wine_id, canonical_wine_id, source_type, reason, confidence, review_status)
VALUES
  -- Chaski Petit Verdot 2019 => Petit Verdot Chaski (Perez Cruz, rating 4.10)
  (1796520, 94874, 'manual', 'Nome invertido. Mesmo vinho Perez Cruz. Caso critico validado.', 0.435, 'approved'),

  -- FINCA LAS MORAS CABERNET SAUVIGNON => Las Moras Cabernet Sauvignon (rating 3.40)
  (1803853, 40743, 'manual', 'Nome com prefixo Finca. Mesmo vinho. Caso critico validado.', 0.460, 'approved'),

  -- VINO FINCA LAS MORAS CABERNET SAUVIGNON 750CC => Las Moras Cabernet Sauvignon
  (1806948, 40743, 'manual', 'Nome com VINO e 750CC. Mesmo vinho.', 0.400, 'approved'),

  -- MONTES ALPHA MERLOT VALLE COLCHAGUA 2020 => Montes Alpha Merlot (rating 3.80)
  (1792269, 15056, 'manual', 'Nome com regiao e safra. Mesmo vinho Montes.', 0.500, 'approved'),

  -- Santa Rita 120 Sauvignon Blanc => 120 Reserva Especial Sauvignon Blanc (rating 3.40)
  (1818495, 1255, 'manual', 'Mesma linha 120 Santa Rita.', 0.500, 'approved'),

  -- VT MONTES ALPHA CABERNET SAUV => Montes Alpha Cabernet Sauvignon (rating 3.90)
  (2261784, 15054, 'manual', 'VT=Vino Tinto. Nome truncado. Mesmo vinho.', 0.450, 'approved'),

  -- VT MONTES ALPHA Merlot => Montes Alpha Merlot (rating 3.80)
  (2261780, 15056, 'manual', 'VT=Vino Tinto. Mesmo vinho Montes.', 0.550, 'approved'),

  -- VT MONTES ALPHA Carmenere => Montes Alpha Carmenere (rating 4.00)
  (2261782, 15055, 'manual', 'VT=Vino Tinto. Mesmo vinho Montes.', 0.550, 'approved'),

  -- VT MONTES ALPHA Pinot Noir => Montes Alpha Pinot Noir (rating 3.80)
  (2261778, 39131, 'manual', 'VT=Vino Tinto. Mesmo vinho Montes.', 0.500, 'approved'),

  -- Carmen Cabernet Sauvignon Reserva => Carmen Cabernet Sauvignon Reserva (rating 3.50)
  (1743048, 99420, 'manual', 'Nome identico. Produtor Carmen confirmado.', 0.600, 'approved')

ON CONFLICT (source_wine_id) DO NOTHING;

COMMIT;
