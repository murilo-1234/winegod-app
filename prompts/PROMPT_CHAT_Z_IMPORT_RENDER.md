INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# Chat Z — Importar Vinhos Classificados pro Render

## CONTEXTO

WineGod.ai e uma IA sommelier. O banco de producao (Render PostgreSQL) tem 1.72M vinhos importados do Vivino e 12.7K lojas. O pipeline de classificacao (Chat Y) processou 3.96M vinhos de lojas de 50 paises usando 7 IAs (Gemini, Mistral, Grok, Claude, ChatGPT, GLM, Codex). Resultado:

- **1.38M matched** — vinhos que casaram com o Vivino (tem `vivino_id`)
- **762K new** — vinhos reais que nao existem no Vivino
- Dados enriquecidos pelas IAs: produtor, nome, pais, cor/tipo, safra, uva, regiao, subregiao, ABV, denominacao, corpo, harmonizacao, docura
- Todos os campos ja foram normalizados (pais=ISO 2 letras, cor=tinto/branco/etc, regiao=Title Case, safra=4 digitos, ABV=numerico)

Os dados estao no banco LOCAL (`winegod_db` no PC) e precisam ser importados pro banco RENDER (producao).

## TAREFA

Criar o script `scripts/import_render_z.py` que importa os dados do banco local pro Render em 3 fases:

### FASE 1 — Wine Sources dos Matched (1.38M → wine_sources)

Para cada vinho matched (tem `vivino_id` na `y2_results`):

1. Buscar o `wine_id` no Render: `SELECT id FROM wines WHERE vivino_id = %s`
2. Buscar dados da loja na `wines_clean` (JOIN por `clean_id`):
   - `fontes` (JSON array com `{"url": "...", "loja": "..."}`)
   - `preco_min`, `preco_max`, `moeda`
   - `pais_tabela` (pais da loja, ISO 2 letras)
3. Extrair dominio da URL em `fontes` (ex: `www.gourmetmax.com.ar` → `gourmetmax.com.ar`)
4. Buscar `store_id` no Render: `SELECT id FROM stores WHERE dominio = %s`
5. Se loja encontrada → INSERT em `wine_sources`:
   ```sql
   INSERT INTO wine_sources (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
   VALUES (%s, %s, %s, %s, %s, true, NOW(), NOW())
   ON CONFLICT DO NOTHING
   ```
6. Se loja NAO encontrada → pular (nao criar loja nova)
7. Se `fontes` vazio (`[]`) → usar `preco_min` como preco, sem URL, sem store_id (pular)

**IMPORTANTE:** Muitos vinhos na wines_clean tem `fontes = '[]'` (vazio). Para esses, NAO ha URL nem loja. Pular — so importar os que tem fontes com URL.

### FASE 2 — Criar Vinhos Novos (762K → wines + wine_sources)

Para cada vinho `new` (sem `vivino_id`, status='new' na `y2_results`):

1. Criar registro na tabela `wines` do Render com dados do LLM + wines_clean:
   ```sql
   INSERT INTO wines (nome, nome_normalizado, produtor, produtor_normalizado, safra, tipo, pais, regiao, sub_regiao, uvas, teor_alcoolico, harmonizacao, preco_min, preco_max, moeda, total_fontes, descoberto_em, atualizado_em)
   VALUES (...)
   ON CONFLICT DO NOTHING
   RETURNING id
   ```
2. Criar wine_source (mesmo fluxo da Fase 1)

**Mapeamento de campos y2_results + wines_clean → wines Render:**

| Origem | Campo Render | Conversao |
|---|---|---|
| wines_clean.nome_limpo | nome | direto |
| wines_clean.nome_normalizado | nome_normalizado | direto |
| y2_results.prod_banco | produtor_normalizado | direto (ja minusculo) |
| wines_clean.produtor_extraido | produtor | direto (Title Case original) |
| y2_results.safra | safra | direto (ja e ano 4 digitos ou NULL) |
| y2_results.cor | tipo | direto (ja normalizado: tinto/branco/rose/espumante/fortificado/sobremesa) |
| y2_results.pais | pais | direto (ja ISO 2 letras) |
| y2_results.regiao | regiao | direto (ja Title Case) |
| y2_results.subregiao | sub_regiao | direto |
| y2_results.uva | uvas | CONVERTER: texto "pinot noir, merlot" → JSONB `["Pinot Noir", "Merlot"]` (split por virgula, Title Case) |
| y2_results.abv | teor_alcoolico | CONVERTER: texto "13.5" → numeric 13.5 |
| y2_results.harmonizacao | harmonizacao | direto (texto) |
| wines_clean.preco_min | preco_min | direto |
| wines_clean.preco_max | preco_max | direto |
| wines_clean.moeda | moeda | direto |
| wines_clean.total_fontes | total_fontes | direto |
| wines_clean.url_imagem | imagem_url | direto |
| wines_clean.hash_dedup | hash_dedup | direto |
| wines_clean.ean_gtin | ean_gtin | direto |

**Para evitar duplicatas de vinhos novos:** usar hash_dedup como constraint natural (se ja existir hash_dedup, pular).

### FASE 3 — Enriquecer Vinhos Existentes (atualizar wines Render)

Para vinhos matched que ja existem no Render mas tem campos NULL:

```sql
UPDATE wines SET
    tipo = COALESCE(wines.tipo, %s),
    regiao = COALESCE(wines.regiao, %s),
    sub_regiao = COALESCE(wines.sub_regiao, %s),
    uvas = COALESCE(wines.uvas, %s),
    teor_alcoolico = COALESCE(wines.teor_alcoolico, %s),
    harmonizacao = COALESCE(wines.harmonizacao, %s),
    atualizado_em = NOW()
WHERE id = %s
AND (tipo IS NULL OR regiao IS NULL OR uvas IS NULL OR teor_alcoolico IS NULL)
```

Usa COALESCE — so preenche campos que estao NULL no Render. NUNCA sobrescreve dados existentes.

## CREDENCIAIS

```python
# Banco LOCAL (PC)
LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")

# Banco RENDER (producao) — SEMPRE com sslmode=require
RENDER_DB = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod?sslmode=require"
```

## SCHEMAS RENDER (referencia)

```sql
-- wines (ja existe, 1.72M registros)
CREATE TABLE wines (
    id SERIAL PRIMARY KEY,
    hash_dedup VARCHAR,
    nome TEXT,
    nome_normalizado TEXT,
    produtor TEXT,
    produtor_normalizado TEXT,
    safra VARCHAR,
    tipo VARCHAR,            -- tinto, branco, rose, espumante, fortificado, sobremesa
    pais VARCHAR,            -- ISO 2 letras: fr, it, us
    pais_nome VARCHAR,       -- France, Italy (opcional)
    regiao TEXT,
    sub_regiao TEXT,
    uvas JSONB,              -- ["Pinot Noir", "Merlot"]
    teor_alcoolico NUMERIC,
    volume_ml INTEGER,
    ean_gtin VARCHAR,
    imagem_url TEXT,
    descricao TEXT,
    harmonizacao TEXT,
    vivino_id BIGINT,
    vivino_rating NUMERIC,
    vivino_reviews INTEGER,
    vivino_url TEXT,
    preco_min NUMERIC,
    preco_max NUMERIC,
    moeda VARCHAR,
    total_fontes INTEGER,
    fontes JSONB,
    descoberto_em TIMESTAMPTZ,
    atualizado_em TIMESTAMPTZ,
    winegod_score NUMERIC,
    winegod_score_type VARCHAR,
    winegod_score_components JSONB,
    nota_wcf NUMERIC,
    confianca_nota NUMERIC
);

-- stores (ja existe, 12.7K registros)
-- Coluna chave: dominio (ex: "gourmetmax.com.ar")
CREATE TABLE stores (
    id SERIAL PRIMARY KEY,
    nome TEXT,
    url TEXT,
    dominio TEXT,
    pais VARCHAR,
    tipo TEXT,
    plataforma TEXT,
    regiao TEXT,
    cidade TEXT,
    abrangencia TEXT,
    total_vinhos INTEGER,
    ativa BOOLEAN,
    como_descobriu TEXT,
    observacoes TEXT,
    descoberta_em TIMESTAMPTZ,
    atualizada_em TIMESTAMPTZ
);

-- wine_sources (ja existe, 66K registros)
CREATE TABLE wine_sources (
    id SERIAL PRIMARY KEY,
    wine_id INTEGER REFERENCES wines(id),
    store_id INTEGER REFERENCES stores(id),
    url TEXT,
    preco NUMERIC,
    preco_anterior NUMERIC,
    moeda VARCHAR,
    disponivel BOOLEAN,
    em_promocao BOOLEAN,
    descoberto_em TIMESTAMPTZ,
    atualizado_em TIMESTAMPTZ
);
```

## SCHEMAS LOCAL (referencia)

```sql
-- y2_results (3.74M registros, resultado da classificacao)
-- Campos relevantes:
--   id, clean_id, classificacao (W/X/S), status (matched/new/not_wine/duplicate/spirit/error)
--   prod_banco, vinho_banco, pais, cor, safra, uva, regiao, subregiao, abv, denominacao, corpo, harmonizacao, docura
--   vivino_id, vivino_produtor, vivino_nome, match_score, fonte_llm

-- wines_clean (3.96M registros, dados originais limpos)
-- Campos relevantes:
--   id (= clean_id na y2_results), nome_limpo, nome_normalizado, produtor_extraido, produtor_normalizado
--   safra, tipo, pais, regiao, preco_min, preco_max, moeda, url_imagem, fontes (JSON text), total_fontes, hash_dedup, ean_gtin, pais_tabela
```

## ESPECIFICACOES TECNICAS

### Performance
- Render e banco remoto (Oregon) — queries sao lentas (~100ms cada)
- Processar em BATCHES de 500-1000
- Usar `execute_values` do `psycopg2.extras` pra batch inserts (MUITO mais rapido que executemany)
- Pre-carregar em memoria: mapa vivino_id → wine_id, mapa dominio → store_id
- Mostrar progresso: `Fase 1: 50,000 / 1,380,000 (3%) | 120/seg | ETA 3h`

### Pre-carregamento (CRITICO pra performance)
```python
from psycopg2.extras import execute_values

# Carregar mapa vivino_id → wine_id do Render (1.72M, ~200MB RAM)
# Fazer em 1 query grande no inicio, guardar em dict
print("Carregando mapa vivino_id → wine_id...")
render_cur.execute("SELECT vivino_id, id FROM wines WHERE vivino_id IS NOT NULL")
vivino_to_wine = {row[0]: row[1] for row in render_cur}
print(f"  {len(vivino_to_wine):,} vinhos carregados")

# Carregar mapa dominio → store_id do Render (12.7K, trivial)
render_cur.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
domain_to_store = {row[0]: row[1] for row in render_cur}
print(f"  {len(domain_to_store):,} lojas carregadas")
```

### Extrair dominio da URL
```python
from urllib.parse import urlparse
def get_domain(url):
    """Extrai dominio sem www: 'https://www.gourmetmax.com.ar/path' → 'gourmetmax.com.ar'"""
    try:
        d = urlparse(url).netloc
        return d.replace('www.', '') if d else None
    except:
        return None
```

### Conversao uva texto → JSONB
```python
import json
def uva_to_jsonb(uva_text):
    """'pinot noir, merlot' → '["Pinot Noir", "Merlot"]'"""
    if not uva_text:
        return None
    parts = [u.strip().title() for u in uva_text.split(',') if u.strip()]
    return json.dumps(parts) if parts else None
```

### Dedup de wine_sources
Criar UNIQUE constraint antes de inserir:
```sql
-- No Render, antes de importar:
CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_wine_store_url ON wine_sources(wine_id, store_id, url);
```

### Parsing fontes (wines_clean.fontes)
O campo `fontes` e TEXT contendo JSON. Exemplo:
```
[{"url": "https://www.gourmetmax.com.ar/casa-de-la-torre", "loja": "Gourmet Max"}]
```
Muitos tem `[]` (vazio) — nesses casos, pular.

```python
import json
def parse_fontes(fontes_text):
    """Retorna lista de {url, loja} ou [] se vazio."""
    if not fontes_text or fontes_text == '[]':
        return []
    try:
        return json.loads(fontes_text)
    except:
        return []
```

## ESTRUTURA DO SCRIPT

```
scripts/import_render_z.py
```

O script deve:
1. Aceitar argumento `--fase` (1, 2, 3, ou `all`)
2. Aceitar argumento `--limite` (processar N registros, pra teste)
3. Aceitar argumento `--dry-run` (simular sem inserir)
4. Mostrar progresso em tempo real
5. Ser idempotente (rodar 2x nao cria duplicatas)
6. Tratar erros graciosamente (se 1 registro falhar, continuar com os outros)
7. Commit a cada batch (nao acumular transacao gigante)

```bash
# Teste com 100 registros
python scripts/import_render_z.py --fase 1 --limite 100

# Rodar fase 1 completa
python scripts/import_render_z.py --fase 1

# Rodar tudo
python scripts/import_render_z.py --fase all
```

## O QUE NAO FAZER

- **NAO modificar tabelas existentes** no Render (nao alterar schema de wines, stores, wine_sources)
- **NAO deletar dados** existentes no Render
- **NAO sobrescrever** campos que ja tem valor no Render (usar COALESCE)
- **NAO criar lojas novas** — se a loja nao existe em `stores`, pular o wine_source
- **NAO fazer git commit/push** — o CTO faz isso
- **NAO modificar app.py** nem nenhum arquivo do backend/frontend
- **NAO importar vinhos com status not_wine, duplicate, spirit, ou error** — so matched e new
- **NAO usar variaveis de ambiente** — credenciais estao hardcoded neste prompt

## COMO TESTAR

```bash
# 1. Testar com --dry-run primeiro
python scripts/import_render_z.py --fase 1 --limite 100 --dry-run

# 2. Testar fase 1 com 100 registros reais
python scripts/import_render_z.py --fase 1 --limite 100

# 3. Verificar no Render
python -c "
import psycopg2
conn = psycopg2.connect('postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod?sslmode=require')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM wine_sources')
print(f'Wine sources: {cur.fetchone()[0]:,}')
cur.execute('SELECT COUNT(*) FROM wines')
print(f'Wines: {cur.fetchone()[0]:,}')
conn.close()
"

# 4. Testar fase 2 com 100 registros
python scripts/import_render_z.py --fase 2 --limite 100

# 5. Testar fase 3 com 100 registros
python scripts/import_render_z.py --fase 3 --limite 100
```

## ENTREGAVEL

1. Script `scripts/import_render_z.py` funcional
2. Testado com --limite 100 em cada fase (sem erros)
3. Relatorio no terminal com: quantos wine_sources criados, quantos wines novos, quantos enriquecidos, quantos pulados e por que
