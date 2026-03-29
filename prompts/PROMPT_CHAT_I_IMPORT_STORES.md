# CHAT I — Importar 57K Lojas + Popular wine_sources no Render

## CONTEXTO
WineGod.ai tem 57K lojas e 3.78M vinhos de lojas no banco LOCAL do fundador (winegod_db). O banco no Render (producao) tem a tabela `stores` e `wine_sources` VAZIAS. Voce vai importar os dados do local pro Render.

## CONEXOES

```
# Banco LOCAL (fonte — 57K lojas, 3.78M vinhos)
LOCAL_DB=postgresql://postgres:XXXXXXXXX@localhost:5432/winegod_db

# Banco RENDER (destino — tabelas vazias)
RENDER_DB=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod
```

psql local: `"C:\Program Files\PostgreSQL\16\bin\psql.exe"`

## ONDE CRIAR
`C:\winegod-app\scripts\import_stores.py`

## SCHEMA LOCAL (lojas_scraping)

Campos da tabela lojas_scraping no winegod_db local:
- id, nome (nome da loja), url, url_normalizada (UNIQUE)
- pais_codigo (ISO 2 letras), plataforma, dificuldade, status
- tier_usado, modelo_ia_usado, vinhos_extraidos, tentativas, erro_ultimo
- regiao, cidade, abrangencia, tipo, observacoes, descoberta_em, atualizada_em

Filtro importante: so importar lojas com `status = 'sucesso'` (12.428 lojas que realmente tem vinhos).

## SCHEMA RENDER (stores)

```sql
stores (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200),
    url TEXT UNIQUE,
    dominio VARCHAR(200) UNIQUE,
    pais VARCHAR(2),
    tipo VARCHAR(50),
    plataforma VARCHAR(50),
    regiao VARCHAR(100),
    cidade VARCHAR(100),
    abrangencia VARCHAR(20),
    total_vinhos INTEGER DEFAULT 0,
    ativa BOOLEAN DEFAULT TRUE,
    como_descobriu VARCHAR(50),
    observacoes TEXT,
    descoberta_em TIMESTAMPTZ,
    atualizada_em TIMESTAMPTZ
)
```

## PASSO 1 — IMPORTAR LOJAS

Script Python que:
1. Conecta no LOCAL, le lojas com status='sucesso'
2. Mapeia campos:
   - nome → nome
   - url → url
   - url_normalizada → extrair dominio pra `dominio`
   - pais_codigo → pais
   - plataforma → plataforma
   - vinhos_extraidos → total_vinhos
   - status='sucesso' → ativa=TRUE
   - tier_usado ou modelo_ia_usado → como_descobriu
3. Insere no Render em lotes de 500 (INSERT ON CONFLICT DO NOTHING no dominio)
4. Log progresso a cada 1000 lojas

```python
# Extrair dominio da URL
from urllib.parse import urlparse
dominio = urlparse(url).netloc.replace('www.', '')
```

## PASSO 2 — MAPEAR VINHOS LOCAL → RENDER

O desafio: vinhos no LOCAL estao em tabelas separadas por pais (vinhos_br, vinhos_us, etc.) com IDs locais. Vinhos no RENDER estao na tabela `wines` com IDs diferentes.

A ponte e o `hash_dedup` — ambos os bancos tem esse campo (MD5 do nome+produtor+safra).

Estrategia:
1. Para cada tabela vinhos_{pais} no LOCAL
2. Ler vinhos que tem fontes (JOIN com vinhos_{pais}_fontes)
3. Buscar o wine_id no RENDER pelo hash_dedup
4. Se encontrar → criar wine_source
5. Se NAO encontrar → o vinho existe localmente mas nao no Render (pode ignorar por enquanto)

## PASSO 3 — POPULAR wine_sources

Schema do wine_sources no Render:
```sql
wine_sources (
    id SERIAL PRIMARY KEY,
    wine_id INTEGER REFERENCES wines(id),
    store_id INTEGER REFERENCES stores(id),
    url TEXT,
    preco DECIMAL(10,2),
    preco_anterior DECIMAL(10,2),
    moeda VARCHAR(3),
    disponivel BOOLEAN DEFAULT TRUE,
    em_promocao BOOLEAN DEFAULT FALSE,
    descoberto_em TIMESTAMPTZ,
    atualizado_em TIMESTAMPTZ,
    UNIQUE(wine_id, store_id, url)
)
```

Script:
1. Para cada pais (50 tabelas):
   a. Ler vinhos_{pais}_fontes (vinho_id, fonte, url_original, preco, moeda)
   b. Buscar wine_id no Render via hash_dedup do vinho local
   c. Buscar store_id no Render via dominio extraido da url_original
   d. Se ambos existem → INSERT wine_sources
2. Fazer em lotes de 1000
3. ON CONFLICT (wine_id, store_id, url) DO NOTHING

## PASSO 4 — ATUALIZAR preco_min/preco_max em wines

Apos popular wine_sources, recalcular precos agregados:
```sql
UPDATE wines w SET
  preco_min = sub.min_preco,
  preco_max = sub.max_preco,
  total_fontes = sub.total
FROM (
  SELECT wine_id,
    MIN(preco) FILTER (WHERE preco > 0) as min_preco,
    MAX(preco) as max_preco,
    COUNT(DISTINCT store_id) as total
  FROM wine_sources
  WHERE disponivel = TRUE AND preco > 0
  GROUP BY wine_id
) sub
WHERE w.id = sub.wine_id;
```

## OTIMIZACAO (IMPORTANTE)

Isso envolve cruzar MILHOES de registros. Otimizacoes necessarias:

1. **Criar indice hash_dedup no Render** (se nao existir):
```sql
CREATE INDEX IF NOT EXISTS idx_wines_hash ON wines(hash_dedup);
```

2. **Carregar mapa hash→id em memoria**:
```python
# Carregar de uma vez (1.72M registros, ~200MB RAM)
cursor.execute("SELECT id, hash_dedup FROM wines WHERE hash_dedup IS NOT NULL")
hash_to_id = {row[1]: row[0] for row in cursor.fetchall()}
```

3. **Carregar mapa dominio→store_id em memoria**:
```python
cursor.execute("SELECT id, dominio FROM stores")
domain_to_id = {row[1]: row[0] for row in cursor.fetchall()}
```

4. **Processar pais por pais** pra nao estourar memoria

5. **Batch inserts** de 1000 registros por vez

## O QUE NAO FAZER
- NAO importar lojas com status diferente de 'sucesso'
- NAO importar lojas com url_morta ou dificuldade=5
- NAO alterar schema do banco
- NAO deletar dados existentes no Render
- NAO fazer git commit/push
- NAO tentar importar lojas que ja existem (ON CONFLICT DO NOTHING)

## COMO VERIFICAR

```sql
-- No Render: lojas importadas
SELECT count(*) FROM stores;
-- Deve ser ~12K (lojas com sucesso)

SELECT pais, count(*) FROM stores GROUP BY pais ORDER BY count(*) DESC LIMIT 10;

-- wine_sources populados
SELECT count(*) FROM wine_sources;

-- Precos atualizados
SELECT count(*) FROM wines WHERE preco_min IS NOT NULL;

-- Top lojas por vinhos
SELECT s.nome, s.pais, count(*) as vinhos
FROM wine_sources ws JOIN stores s ON ws.store_id = s.id
GROUP BY s.nome, s.pais
ORDER BY vinhos DESC LIMIT 10;
```

## ENTREGAVEL
1. Script `C:\winegod-app\scripts\import_stores.py`
2. ~12K lojas importadas na tabela stores do Render
3. wine_sources populado (cruzamento vinhos x lojas)
4. preco_min/preco_max atualizados em wines
5. Relatorio: quantas lojas, quantos wine_sources, quantos matches por hash
