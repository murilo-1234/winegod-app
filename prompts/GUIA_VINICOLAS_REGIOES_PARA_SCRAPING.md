# Guia — Como usar Vinícolas e Regiões para Scraping (Amazon + CellarTracker)

> **Objetivo**: explicar exatamente como as listas de vinícolas e regiões são usadas nas extrações Amazon, e como podem ser plugadas no scraper CellarTracker. Inclui caminhos de todos os arquivos relevantes.

---

## 1. OS DOIS DATASETS CENTRAIS

### 1.1 Regiões vinícolas — 2.580

**Arquivo**: `C:\natura-automation\amazon\regioes_mundo.py`
- **Formato**: lista Python de strings (`REGIOES_MUNDO = ["Bordeaux", "Champagne", ...]`)
- **Origem**: Vivino (extraído de `C:\Users\User\Desktop\_vivino_vinicolas_traduzidas.csv`)
- **Ordenação**: por número de vinícolas na região (descendente — Bordeaux primeiro com 7.327 vinícolas)
- **Idioma**: inglês ou nome original (Bordeaux, não Bordéus; Toscana, não Tuscany)

### 1.2 Vinícolas do mundo — 87.036

**Arquivo**: `C:\natura-automation\amazon\vinicolas_mundo.py`
- **Formato**: lista Python de strings (`VINICOLAS_MUNDO = ["Antinori", "Casillero del Diablo", ...]`)
- **Origem**: Vivino (vinícolas com 100+ ratings)
- **Ordenação**: por popularidade/total de ratings (descendente — Antinori primeiro com 1M ratings)
- **Cobertura atual**: usando top 2.000 (de 87.036) no scraper Amazon

---

## 2. COMO A AMAZON USA ESSES DATASETS

### 2.1 Composição da query

Cada região ou vinícola vira uma busca na Amazon combinando o nome + sufixo do idioma local:

```
Query = "{nome}" + " " + "{sufixo_idioma}"
```

**Sufixos por idioma** (arquivo: `C:\natura-automation\amazon\orchestrator.py`, linhas 704-707):
```python
suffix = {"pt": "vinho", "es": "vino", "fr": "vin", "de": "wein",
          "it": "vino", "nl": "wijn", "pl": "wino", "sv": "vin",
          "ja": "wine", "ar": "wine"}.get(lang, "wine")
```

**Exemplos reais por template:**

| Template | País | Query gerada |
|---|---|---|
| enrich_regiao | US | `"Bordeaux wine"` |
| enrich_regiao | BR | `"Bordeaux vinho"` |
| enrich_regiao | DE | `"Bordeaux wein"` |
| enrich_regiao | JP | `"Bordeaux wine"` |
| enrich_vinicola | US | `"Antinori wine"` |
| enrich_vinicola | BR | `"Antinori vinho"` |
| enrich_vinicola | NL | `"Antinori wijn"` |

### 2.2 Ordem de execução

**Arquivo**: `C:\natura-automation\amazon\orchestrator.py` (linhas 709-728)

```python
enrich_queries = []

# 1. Uvas (150 queries)
for uva in UVAS[:ENRICH_UVAS_MAX]:
    enrich_queries.append(("enrich_uva_x_preco", f"{uva} {suffix}", {"uva": uva}))

# 2. Regiões (2.580 queries)
for reg in REGIOES_MUNDO:
    enrich_queries.append(("enrich_regiao_x_preco", f"{reg} {suffix}", {"regiao": reg}))

# 3. Vinícolas (2.000 queries)
for vin in VINICOLAS_MUNDO[:ENRICH_VINICOLAS_MAX]:
    enrich_queries.append(("enrich_vinicola_x_preco", f"{vin} {suffix}", {"vinicola": vin}))

# 4. Autocomplete (~50-160 queries)
auto_queries = descobrir_queries_autocomplete(pais)
```

### 2.3 Split de preço recursivo (v3)

Cada query acima NÃO é uma busca simples — ela passa por `scrape_faixa_adaptativa()`:

```
1. Buscar "Bordeaux wine" na Amazon US (range $1-$5000)
2. Amazon declara 3.000 resultados? → dividir: $1-$2500 + $2500-$5000
3. $1-$2500 ainda tem 2.000? → dividir: $1-$1250 + $1250-$2500
4. Continuar até range ≤ $1
5. Se range=$1 e ainda >400 resultados → SORT ROTATION (4 sorts diferentes)
```

**Arquivo**: `C:\natura-automation\amazon\orchestrator.py`, função `scrape_faixa_adaptativa()` (linhas 530-606)

### 2.4 Resultados medidos por template

**Dados reais de US (2026-04-20):**

| Template | Queries | Vinhos novos | Novos/query |
|---|---|---|---|
| enrich_uva_x_preco | 150 | +1.006 | 6.7 |
| enrich_regiao_x_preco | 2.580 | +12.761 | 4.9 |
| enrich_vinicola_x_preco | 1.953 | +11.186 | 5.7 |
| enrich_autocomplete_x_preco | 32 | +1.343 | 42.0 |

**Insight**: regiões e vinícolas têm ROI similar (~5 novos/query). Autocomplete é o mais eficiente (42/query) mas tem poucas queries.

---

## 3. COMO O CELLARTRACKER FUNCIONA HOJE

### 3.1 Arquitetura diferente

O scraper CellarTracker **NÃO** faz scraping direto do site. Usa **Gemini** (IA do Google) como proxy inteligente — pergunta ao Gemini sobre vinhos do CellarTracker e parseia a resposta JSON.

**Arquivo principal**: `C:\natura-automation\cellartracker\query_executor.py`
- Modelo: `gemini-2.5-flash-lite` (gratuito, 1.000 req/dia)
- Cada query retorna ~20-50 vinhos em JSON
- Sem paginação — Gemini devolve tudo em 1 resposta

### 3.2 Templates atuais (6 templates, ~28K queries)

**Arquivo**: `C:\natura-automation\cellartracker\query_generator.py`

| Template | Composição | Queries | Exemplo |
|---|---|---|---|
| A: pais_tipo | 70 países × 7 tipos | 490 | "Top 50 red wines from France on CellarTracker" |
| B: regiao | ~500 regiões | 500 | "All notable wines from Bordeaux, France on CellarTracker" |
| C: uva_pais | 150 uvas × 30 países | 4.500 | "All Cabernet Sauvignon wines from USA on CellarTracker" |
| E: mega | 32 temáticas | 32 | "All wines with CT score >= 95" |
| F: regiao_uva_safra | 200 regiões × 20 uvas × 5 safras | 20.000 | "All Pinot Noir from Burgundy vintage 2020 on CellarTracker" |
| G: preco_regiao | 500 regiões × 5 faixas | 2.500 | "Best wines from Napa Valley under $50 on CellarTracker" |

### 3.3 Datasets atuais do CellarTracker (HARDCODED)

**Arquivo**: `C:\natura-automation\cellartracker\config.py`

| Dados | Quantidade | Localização |
|---|---|---|
| Países | 70 | config.py linhas 32-49 |
| Regiões | **~500** | config.py linhas 58-181 (dict por país) |
| Uvas | 150 | config.py linhas 196-227 |
| Vinícolas | **0 (NÃO TEM)** | — |
| Faixas de preço | 5 | config.py linhas 236-242 |
| Safras | 14 (8 recentes + 6 clássicas) | config.py linhas 248-249 |

### 3.4 O que NÃO usa

- **Nenhuma importação de `regioes_mundo.py`** (Amazon)
- **Nenhuma importação de `vinicolas_mundo.py`** (Amazon)
- **Nenhum template baseado em vinícola** — não existe template "vinhos da Antinori no CellarTracker"

---

## 4. OPORTUNIDADES DE INTEGRAÇÃO

### 4.1 Regiões: 500 → 2.580 (5x expansão)

**Hoje**: CellarTracker usa ~500 regiões hardcoded em `config.py`
**Proposta**: importar `REGIOES_MUNDO` do Amazon (2.580 regiões, ordenadas por importância)

**Impacto nos templates:**
- Template B (região): 500 → 2.580 queries
- Template F (região × uva × safra): 20.000 → ~100.000+ queries (precisa limitar)
- Template G (preço × região): 2.500 → 12.900 queries

**Cuidado**: 1.000 queries/dia no Gemini gratuito. Expansão precisa ser prioritizada (top 500 regiões primeiro, expandir gradualmente).

### 4.2 Vinícolas: 0 → 87.036 (template NOVO)

**Hoje**: CellarTracker NÃO tem queries por vinícola
**Proposta**: criar Template H usando `VINICOLAS_MUNDO`

```
"List ALL wines from {vinicola} as tracked on CellarTracker.org
 with community scores, drinking windows, and flavor keywords."
```

**Exemplos**:
- "List ALL wines from Antinori as tracked on CellarTracker.org..."
- "List ALL wines from Penfolds as tracked on CellarTracker.org..."

**Volume**: top 500 vinícolas = 500 queries. Top 2.000 = 2.000 queries.

### 4.3 Combo: vinícola × uva (template NOVO)

```
"List ALL Cabernet Sauvignon wines from Opus One as tracked on CellarTracker.org..."
```

**Volume**: 500 vinícolas × 50 uvas = 25.000 queries (alto, executar em semanas).

---

## 5. TODOS OS ARQUIVOS RELEVANTES

### Datasets de entrada (regiões e vinícolas)

| Arquivo | O que contém | Tamanho |
|---|---|---|
| `C:\natura-automation\amazon\regioes_mundo.py` | 2.580 regiões vinícolas (Vivino) | 2.588 linhas |
| `C:\natura-automation\amazon\vinicolas_mundo.py` | 87.036 vinícolas (Vivino) | 87.044 linhas |
| `C:\natura-automation\amazon\config.py` | 150 uvas, 250 regiões (curta), 200 produtores, keywords, marketplaces | 347 linhas |
| `C:\Users\User\Desktop\_vivino_vinicolas_traduzidas.csv` | 213K vinícolas Vivino (fonte master) | CSV |

### Scraper Amazon (onde as queries são compostas e executadas)

| Arquivo | Função |
|---|---|
| `C:\natura-automation\amazon\orchestrator.py` | Pipeline principal — compõe queries, executa, salva |
| `C:\natura-automation\amazon\utils_playwright.py` | Browser, extração de preço, anti-bot, validação |
| `C:\natura-automation\amazon\autocomplete.py` | Autocomplete API da Amazon (grátis) |
| `C:\natura-automation\amazon\category_discovery.py` | Descobre nodes Wine por marketplace |
| `C:\natura-automation\amazon\filter_research.py` | Estudo empírico de estratégias de busca |
| `C:\natura-automation\amazon\db_amazon.py` | Tracking de queries (amazon_queries) |

### Scraper CellarTracker (onde as queries Gemini são compostas e executadas)

| Arquivo | Função |
|---|---|
| `C:\natura-automation\cellartracker\config.py` | Datasets hardcoded (500 regiões, 150 uvas, 70 países) |
| `C:\natura-automation\cellartracker\query_generator.py` | Gera ~28K queries com 6 templates |
| `C:\natura-automation\cellartracker\query_executor.py` | Executa queries via Gemini API |
| `C:\natura-automation\cellartracker\db_cellartracker.py` | Banco local (ct_vinhos, ct_queries) |
| `C:\natura-automation\cellartracker\main.py` | CLI (setup, generate, run, status) |
| `C:\natura-automation\cellartracker\CLAUDE.md` | Documentação arquitetural (486 linhas) |
| `C:\natura-automation\cellartracker\vivino_ct_enrichment.py` | Enrich Vivino → CT via DeepSeek |

### Handoffs CellarTracker

| Arquivo | Conteúdo |
|---|---|
| `C:\natura-automation\prompt_handoff_cellartracker_via_vivino.md` | Enrich Vivino→CT via DeepSeek (287 linhas) |
| `C:\natura-automation\prompt_handoff_grok_ct_via_vivino.md` | Enrich Vivino→CT via Grok experimental (291 linhas) |

### Documentos de estratégia (criados nesta sessão)

| Arquivo | Conteúdo |
|---|---|
| `C:\winegod-app\prompts\HANDOFF_SCRAPER_AMAZON_ESTADO_ATUAL.md` | Estado atual do scraper Amazon (v3, processos, tracking) |
| `C:\winegod-app\prompts\FORMATO_VALIDADO_SCRAPER_AMAZON_V3.md` | Especificação v3 para software autônomo |
| `C:\winegod-app\prompts\GUIA_ESTRATEGIAS_SCRAPING_AMAZON.md` | 15 estratégias de extração documentadas |
| `C:\winegod-app\prompts\GUIA_VINICOLAS_REGIOES_PARA_SCRAPING.md` | **ESTE DOCUMENTO** |

### Resultados de estudo

| Arquivo | Conteúdo |
|---|---|
| `C:\natura-automation\logs\filter_research_US_20260415_190140.json` | Resultado do estudo de 10 estratégias de filtro |

---

## 6. DIFERENÇAS CHAVE ENTRE OS DOIS SCRAPERS

| Aspecto | Amazon | CellarTracker |
|---|---|---|
| **Método** | Playwright (browser real) | Gemini API (IA como proxy) |
| **Custo** | Grátis (só CPU/rede) | Grátis (Gemini free tier, 1K/dia) |
| **Limite** | Anti-bot (delays, captcha) | 1.000 req/dia, 15 RPM |
| **Paginação** | ~400 itens/busca (split de preço resolve) | Sem limite (Gemini devolve tudo) |
| **Regiões** | 2.580 (Vivino) | 500 (hardcoded) |
| **Vinícolas** | 87.036 (Vivino, usando 2.000) | 0 (não tem) |
| **Dados extraídos** | Nome, preço, imagem, produtor, rating | Nome, produtor, CT score, drink window, sabores |
| **Volume** | ~486K vinhos (18 países) | Projetado ~300-500K únicos |
| **Tracking** | `amazon_queries` (banco PostgreSQL) | `ct_queries` (banco PostgreSQL) |
