-- LOTE 2 DE ALIASES — 21 pares manualmente aprovados
-- PRE-REQUISITO: wine_aliases ja existe no Render (Lote 1 ja aplicado)
--
-- Para aplicar:  psql $DATABASE_URL -f reports/apply_alias_lote2.sql
-- Para reverter: psql $DATABASE_URL -f reports/rollback_alias_lote2.sql

BEGIN;
SET LOCAL lock_timeout = '5s';

INSERT INTO wine_aliases (source_wine_id, canonical_wine_id, source_type, reason, confidence, review_status)
VALUES
  -- Montes Alpha Cabernet Sauvignon
  (1817467, 15054, 'manual', 'Mesmo vinho com safra no nome.', 0.700, 'approved'),
  (1822903, 15054, 'manual', 'Mesmo vinho com safra. Outra loja.', 0.700, 'approved'),
  -- Montes Alpha Carmenere
  (2275023, 15055, 'manual', 'Mesmo vinho com prefixo de loja.', 0.650, 'approved'),
  -- Montes Alpha Merlot
  (2013260, 15056, 'manual', 'Mesmo vinho com prefixo Botella Vino.', 0.600, 'approved'),
  -- Montes Alpha Pinot Noir
  (1804556, 39131, 'manual', 'Mesmo vinho em caixa (caja x6).', 0.650, 'approved'),
  (1843291, 39131, 'manual', 'Mesmo vinho com prefixo Vinho Tinto Chileno.', 0.650, 'approved'),
  (1992433, 39131, 'manual', 'Mesmo vinho em caixa (Caja 6 unidades).', 0.650, 'approved'),
  -- Montes Alpha Chardonnay
  (1992431, 101120, 'manual', 'Mesmo vinho em caixa.', 0.650, 'approved'),
  (2016225, 101120, 'manual', 'Mesmo vinho com prefixo Vinho Branco Seco.', 0.650, 'approved'),
  (2019666, 101120, 'manual', 'Mesmo vinho com safra e prefixo.', 0.650, 'approved'),
  -- Montes Alpha Syrah
  (2275013, 15057, 'manual', 'Mesmo vinho com prefixo de loja.', 0.650, 'approved'),
  -- Montes Alpha Malbec
  (1992456, 134817, 'manual', 'Mesmo vinho em caixa (Caja 6x).', 0.650, 'approved'),
  -- Santa Rita 120 Merlot
  (1848357, 1258, 'manual', 'Mesma linha 120 Santa Rita Merlot.', 0.600, 'approved'),
  -- Chateau du Grand Puch
  (2102010, 887146, 'manual', 'Nome identico. Mesmo chateau Bordeaux.', 0.800, 'approved'),
  -- Almaviva
  (1741179, 2076, 'manual', 'Almaviva safra 2003. Vinho iconico chileno.', 0.700, 'approved'),
  -- Clos Apalta
  (1748299, 7546, 'manual', 'Clos Apalta Vinotheque 2012. Release tardio.', 0.700, 'approved'),
  (1753189, 7546, 'manual', 'Clos Apalta Vinotheque 2013. Release tardio.', 0.700, 'approved'),
  -- Purple Angel
  (1862243, 15052, 'manual', 'Purple Angel com safra e produtor no nome.', 0.700, 'approved'),
  (2271802, 15052, 'manual', 'Purple Angel com prefixo de loja e safra.', 0.650, 'approved'),
  -- Santa Rita 120 Cabernet Sauvignon
  (1820106, 1254, 'manual', 'Mesma linha 120 Santa Rita CS.', 0.600, 'approved'),
  (1851793, 1254, 'manual', 'Mesma linha 120 Santa Rita CS com prefixo.', 0.600, 'approved')
ON CONFLICT (source_wine_id) DO NOTHING;

COMMIT;
