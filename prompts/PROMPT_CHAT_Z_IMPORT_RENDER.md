INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# Chat Z — Importar Vinhos Classificados pro Render

## CONTEXTO

WineGod.ai e uma IA sommelier. O banco de producao (Render PostgreSQL, 15GB) tem 1.72M vinhos importados do Vivino, 12.7K lojas e 66K wine_sources. Usa 2.6GB atualmente.

O pipeline de classificacao (Chat Y) processou 3.96M vinhos de lojas de 50 paises usando 7 IAs. Resultado no banco LOCAL:

- **1.38M matched** — vinhos que casaram com o Vivino (tem `vivino_id`, score 0.2-1.0)
- **762K new** — vinhos reais que nao existem no Vivino
- Campos normalizados: pais=ISO 2 letras, cor=tinto/branco/etc, regiao=Title Case, safra=4 digitos, ABV=numerico

## PRINCIPIO FUNDAMENTAL

**Dados do Vivino NUNCA sao sobrescritos.** Campos que ja tem valor no Render ficam intactos. So preenchemos campos NULL.

## TAREFA

Criar `scripts/import_render_z.py` com 3 fases + verificacao anti-duplicata.

---

### FASE 0 — Pre-carregamento (OBRIGATORIO, roda antes de qualquer fase)

Carregar em memoria pra evitar queries individuais:

```python
from psycopg2.extras import execute_values
from urllib.parse import urlparse
import json, time, sys, argparse

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
RENDER_DB = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod?sslmode=require"

# 1. Mapa vivino_id → wine_id do Render (1.72M, ~200MB)
print("Carregando vivino_id → wine_id do Render...")
render_cur.execute("SELECT vivino_id, id FROM wines WHERE vivino_id IS NOT NULL")
vivino_to_wine = {row[0]: row[1] for row in render_cur}
print(f"  {len(vivino_to_wine):,} vinhos")

# 2. Mapa dominio → store_id do Render (12.7K)
render_cur.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
domain_to_store = {row[0]: row[1] for row in render_cur}
print(f"  {len(domain_to_store):,} lojas")

# 3. Mapa produtor → [(wine_id, nome_normalizado)] do Render (pra dedup da Fase 2)
# Carregar produtor_normalizado + nome_normalizado de TODOS os wines no Render
print("Carregando produtores Render pra dedup...")
render_cur.execute("SELECT id, produtor_normalizado, nome_normalizado FROM wines WHERE produtor_normalizado IS NOT NULL AND produtor_normalizado != ''")
render_by_prod = {}
for wid, prod, nome in render_cur:
    if prod not in render_by_prod:
        render_by_prod[prod] = []
    render_by_prod[prod].append((wid, nome))
print(f"  {len(render_by_prod):,} produtores unicos no Render")
```

### Funcoes auxiliares

```python
def get_domain(url):
    """'https://www.gourmetmax.com.ar/path' → 'gourmetmax.com.ar'"""
    try:
        d = urlparse(url).netloc
        return d.replace('www.', '') if d else None
    except:
        return None

def uva_to_jsonb(uva_text):
    """'pinot noir, merlot' → '["Pinot Noir", "Merlot"]'"""
    if not uva_text:
        return None
    parts = [u.strip().title() for u in uva_text.split(',') if u.strip()]
    return json.dumps(parts) if parts else None

def parse_fontes(fontes_text):
    """Retorna lista de {url, loja} ou [] se vazio."""
    if not fontes_text or fontes_text == '[]':
        return []
    try:
        return json.loads(fontes_text)
    except:
        return []

STOPWORDS = frozenset({"de","du","la","le","les","des","del","di","the","and","et"})
def make_word_set(text):
    return frozenset(w for w in text.split() if len(w) >= 3 and w not in STOPWORDS)

def check_exists_in_render(prod, nome):
    """Verifica se vinho ja existe no Render. Retorna wine_id ou None."""
    candidates = render_by_prod.get(prod)
    if not candidates:
        # Tentar palavras do produtor
        prod_words = [w for w in prod.split() if len(w) >= 4]
        if not prod_words:
            return None
        candidates = []
        for rp in render_by_prod:
            if prod in rp or rp in prod:
                candidates.extend(render_by_prod[rp])
                if len(candidates) > 50:
                    break
    if not candidates:
        return None

    nome_words = make_word_set(nome) if nome else frozenset()
    best_id = None
    best_score = 0
    for wid, wnome in candidates:
        wnome_words = make_word_set(wnome) if wnome else frozenset()
        if nome_words and wnome_words:
            overlap = len(nome_words & wnome_words)
            total_w = max(len(nome_words), len(wnome_words))
            score = overlap / total_w if total_w > 0 else 0
        else:
            score = 0
        if prod in render_by_prod and candidates == render_by_prod[prod]:
            score += 0.3
        if score > best_score:
            best_score = score
            best_id = wid
    return best_id if best_score >= 0.4 else None
```

---

### FASE 1 — Wine Sources dos Matched (score >= 0.5 → wine_sources)

**Filtro: `status = 'matched' AND match_score >= 0.5`** (~1.0M registros, exclui 380K de baixa confianca)

Para cada vinho matched:

1. Buscar `wine_id` no dict `vivino_to_wine[vivino_id]`
2. JOIN com `wines_clean` (por clean_id) pra pegar `fontes`, `preco_min`, `moeda`
3. Parsear `fontes` (JSON) → extrair URL → extrair dominio → buscar `store_id`
4. INSERT em `wine_sources` com ON CONFLICT DO NOTHING

```sql
INSERT INTO wine_sources (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
VALUES (%s, %s, %s, %s, %s, true, NOW(), NOW())
ON CONFLICT DO NOTHING
```

**Se fontes vazio:** pular (nao ha URL nem loja)
**Se loja nao encontrada:** pular (nao criar loja nova)
**Se vivino_id nao encontrado no Render:** pular e logar

Query local pra buscar batch:
```sql
SELECT y.vivino_id, y.clean_id, wc.fontes, wc.preco_min, wc.moeda
FROM y2_results y
JOIN wines_clean wc ON wc.id = y.clean_id
WHERE y.status = 'matched' AND y.match_score >= 0.5
LIMIT 1000 OFFSET %s
```

---

### FASE 2 — Vinhos Novos com Verificacao Anti-Duplicata (762K → verificar → wines + wine_sources)

**ANTES de criar cada vinho novo, verificar se ja existe no Render.**

Para cada vinho com `status = 'new'`:

1. **Verificar** com `check_exists_in_render(prod_banco, vinho_banco)`
2. **Se achou no Render** → NAO criar vinho novo → criar wine_source no vinho existente (como na Fase 1)
3. **Se NAO achou** → criar vinho novo + wine_source

Criar vinho novo:
```sql
INSERT INTO wines (nome, nome_normalizado, produtor, produtor_normalizado, safra, tipo, pais,
    regiao, sub_regiao, uvas, teor_alcoolico, harmonizacao, imagem_url,
    preco_min, preco_max, moeda, total_fontes, hash_dedup, ean_gtin,
    descoberto_em, atualizado_em)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
RETURNING id
```

**Mapeamento de campos y2_results + wines_clean → wines Render:**

| Origem | Campo Render | Conversao |
|---|---|---|
| wines_clean.nome_limpo | nome | direto |
| wines_clean.nome_normalizado | nome_normalizado | direto |
| y2_results.prod_banco | produtor_normalizado | direto (ja minusculo) |
| wines_clean.produtor_extraido | produtor | direto (Title Case original) |
| y2_results.safra | safra | direto |
| y2_results.cor | tipo | direto (tinto/branco/rose/espumante/fortificado/sobremesa) |
| y2_results.pais | pais | direto (ISO 2 letras) |
| y2_results.regiao | regiao | direto (Title Case) |
| y2_results.subregiao | sub_regiao | direto |
| y2_results.uva | uvas | `uva_to_jsonb()`: "pinot noir, merlot" → `["Pinot Noir", "Merlot"]` |
| y2_results.abv | teor_alcoolico | `float()` ou None |
| y2_results.harmonizacao | harmonizacao | direto |
| wines_clean.preco_min | preco_min | direto |
| wines_clean.preco_max | preco_max | direto |
| wines_clean.moeda | moeda | direto |
| wines_clean.total_fontes | total_fontes | direto |
| wines_clean.url_imagem | imagem_url | direto |
| wines_clean.hash_dedup | hash_dedup | direto |
| wines_clean.ean_gtin | ean_gtin | direto |

Query local:
```sql
SELECT y.id, y.prod_banco, y.vinho_banco, y.pais, y.cor, y.safra, y.uva,
    y.regiao, y.subregiao, y.abv, y.harmonizacao, y.clean_id,
    wc.nome_limpo, wc.nome_normalizado, wc.produtor_extraido,
    wc.preco_min, wc.preco_max, wc.moeda, wc.url_imagem, wc.fontes,
    wc.total_fontes, wc.hash_dedup, wc.ean_gtin
FROM y2_results y
JOIN wines_clean wc ON wc.id = y.clean_id
WHERE y.status = 'new'
LIMIT 1000 OFFSET %s
```

**Contadores esperados no final:**
- `criados`: vinhos realmente novos inseridos no Render
- `encontrados_render`: vinhos que pareciam novos mas ja existiam → criou wine_source
- `pulados`: sem fontes ou sem dados suficientes

---

### FASE 3 — Enriquecer Vinhos Existentes (score >= 0.7 → UPDATE wines)

**Filtro: `status = 'matched' AND match_score >= 0.7`** (~613K registros)

So preenche campos que estao NULL no Render. NUNCA sobrescreve.

```sql
UPDATE wines SET
    tipo = COALESCE(wines.tipo, %s),
    pais = COALESCE(wines.pais, %s),
    regiao = COALESCE(wines.regiao, %s),
    sub_regiao = COALESCE(wines.sub_regiao, %s),
    uvas = COALESCE(wines.uvas, %s::jsonb),
    teor_alcoolico = COALESCE(wines.teor_alcoolico, %s),
    harmonizacao = COALESCE(wines.harmonizacao, %s),
    imagem_url = COALESCE(wines.imagem_url, %s),
    atualizado_em = NOW()
WHERE id = %s
AND (tipo IS NULL OR pais IS NULL OR regiao IS NULL OR uvas IS NULL
     OR teor_alcoolico IS NULL OR harmonizacao IS NULL OR imagem_url IS NULL)
```

Query local:
```sql
SELECT y.vivino_id, y.cor, y.pais, y.regiao, y.subregiao, y.uva, y.abv, y.harmonizacao,
    wc.url_imagem
FROM y2_results y
JOIN wines_clean wc ON wc.id = y.clean_id
WHERE y.status = 'matched' AND y.match_score >= 0.7
AND (y.cor IS NOT NULL OR y.pais IS NOT NULL OR y.regiao IS NOT NULL
     OR y.uva IS NOT NULL OR y.abv IS NOT NULL OR y.harmonizacao IS NOT NULL)
LIMIT 1000 OFFSET %s
```

---

## CREDENCIAIS

```python
LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
RENDER_DB = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod?sslmode=require"
```

## SCHEMAS RENDER (referencia)

```sql
-- wines (1.72M registros)
CREATE TABLE wines (
    id SERIAL PRIMARY KEY,
    hash_dedup VARCHAR,
    nome TEXT, nome_normalizado TEXT,
    produtor TEXT, produtor_normalizado TEXT,
    safra VARCHAR, tipo VARCHAR, pais VARCHAR, pais_nome VARCHAR,
    regiao TEXT, sub_regiao TEXT,
    uvas JSONB,              -- ["Pinot Noir", "Merlot"]
    teor_alcoolico NUMERIC,
    volume_ml INTEGER, ean_gtin VARCHAR, imagem_url TEXT, descricao TEXT, harmonizacao TEXT,
    vivino_id BIGINT, vivino_rating NUMERIC, vivino_reviews INTEGER, vivino_url TEXT,
    preco_min NUMERIC, preco_max NUMERIC, moeda VARCHAR,
    total_fontes INTEGER, fontes JSONB,
    descoberto_em TIMESTAMPTZ, atualizado_em TIMESTAMPTZ,
    winegod_score NUMERIC, winegod_score_type VARCHAR,
    winegod_score_components JSONB, nota_wcf NUMERIC, confianca_nota NUMERIC
);

-- stores (12.7K) — chave: dominio
CREATE TABLE stores (id SERIAL PRIMARY KEY, nome TEXT, url TEXT, dominio TEXT, pais VARCHAR, ...);

-- wine_sources (66K)
CREATE TABLE wine_sources (
    id SERIAL PRIMARY KEY,
    wine_id INTEGER REFERENCES wines(id),
    store_id INTEGER REFERENCES stores(id),
    url TEXT, preco NUMERIC, preco_anterior NUMERIC, moeda VARCHAR,
    disponivel BOOLEAN, em_promocao BOOLEAN,
    descoberto_em TIMESTAMPTZ, atualizado_em TIMESTAMPTZ
);
```

## SCHEMAS LOCAL (referencia)

```sql
-- y2_results: id, clean_id, status (matched/new), prod_banco, vinho_banco, pais, cor, safra,
--   uva, regiao, subregiao, abv, harmonizacao, vivino_id, match_score, fonte_llm

-- wines_clean: id (=clean_id), nome_limpo, nome_normalizado, produtor_extraido,
--   preco_min, preco_max, moeda, url_imagem, fontes (JSON text), total_fontes, hash_dedup, ean_gtin
```

## SETUP ANTES DE IMPORTAR

Criar indice unique no Render pra evitar duplicatas de wine_sources:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_wine_store_url ON wine_sources(wine_id, store_id, url);
```

## ESPECIFICACOES TECNICAS

- Processar em batches de 500-1000
- Usar `execute_values` do psycopg2.extras pra batch inserts
- Commit a cada batch (nao acumular transacao gigante)
- Mostrar progresso: `Fase 1: 50,000 / 1,000,000 (5%) | 120/seg | sources=42,000 | pulados=8,000`
- Idempotente (ON CONFLICT DO NOTHING)
- Se 1 registro falhar, logar e continuar

## INTERFACE DO SCRIPT

```bash
# Teste
python scripts/import_render_z.py --fase 1 --limite 100
python scripts/import_render_z.py --fase 2 --limite 100
python scripts/import_render_z.py --fase 3 --limite 100

# Producao
python scripts/import_render_z.py --fase 1
python scripts/import_render_z.py --fase 2
python scripts/import_render_z.py --fase 3

# Tudo
python scripts/import_render_z.py --fase all

# Dry run (simula sem inserir)
python scripts/import_render_z.py --fase 1 --limite 100 --dry-run
```

## O QUE NAO FAZER

- **NAO modificar schema** de tabelas existentes no Render
- **NAO deletar dados** existentes
- **NAO sobrescrever** campos que ja tem valor (usar COALESCE)
- **NAO criar lojas novas** — se a loja nao esta em `stores`, pular
- **NAO importar** status not_wine, duplicate, spirit, error — so matched e new
- **NAO fazer git commit/push**
- **NAO modificar app.py** nem arquivos do backend/frontend

## COMO TESTAR

```bash
# 1. Dry run
python scripts/import_render_z.py --fase 1 --limite 100 --dry-run

# 2. Teste real com 100
python scripts/import_render_z.py --fase 1 --limite 100

# 3. Verificar no Render
python -c "
import psycopg2
c = psycopg2.connect('postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod?sslmode=require')
cur = c.cursor()
cur.execute('SELECT COUNT(*) FROM wine_sources')
print(f'Wine sources: {cur.fetchone()[0]:,}')
cur.execute('SELECT COUNT(*) FROM wines')
print(f'Wines total: {cur.fetchone()[0]:,}')
c.close()
"
```

## ENTREGAVEL

1. Script `scripts/import_render_z.py` funcional
2. Testado com --limite 100 em cada fase (sem erros)
3. Relatorio no terminal: wine_sources criados, wines novos, enriquecidos, duplicatas evitadas, pulados
