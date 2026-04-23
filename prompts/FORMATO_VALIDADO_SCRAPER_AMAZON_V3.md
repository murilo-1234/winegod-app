# Formato Validado — Scraper Amazon v3 (para replicar no software autônomo)

> **Objetivo**: este documento descreve o modelo de scraping v3 que foi validado empiricamente em produção com resultados comprovados. Serve como especificação para o software autônomo de scraping Amazon. Atualizado em 2026-04-17.

---

## 1. RESULTADO COMPROVADO

### 1.1 Evolução medida

| Versão | Lógica | Vinhos extraídos |
|---|---|---|
| v1 (original) | Busca simples, sem split de preço no enrich | ~245K (18 países) |
| v2 (+split preço) | Split de preço recursivo no enrich, threshold 700, SPLIT_FLOOR 5 | ~293K (+48K) |
| v3 (+sort rotation) | Split com SPLIT_FLOOR 1, threshold 400, sort rotation em faixas saturadas | **~325K em 5h de v3** (crescendo) |

### 1.2 Ganho comprovado do v3 vs v2 (primeiras 5h)

| País | Antes v3 | Depois v3 | Δ |
|---|---|---|---|
| NL | 44.712 | 55.340 | **+10.628** |
| CA | 33.393 | 39.893 | **+6.500** |
| MX | 18.578 | 21.391 | +2.813 |
| IT | 11.897 | 15.192 | +3.295 |
| AU | 11.058 | 11.760 | +702 |

### 1.3 Problema que v3 resolve

A Amazon mostra no máximo ~7 páginas (~400 itens) por busca. Queries populares têm milhares de resultados. Sem segmentação, o scraper perdia a maioria silenciosamente.

**Exemplo real (US, faixa $5-$10)**: Amazon declara 2.001 resultados, scraper v2 extraía ~400 e parava. v3 roda a mesma faixa 4 vezes com sorts diferentes → extrai ~1.200-1.600 únicos.

---

## 2. ALGORITMO v3 — ESPECIFICAÇÃO PARA O SOFTWARE

### 2.1 Fluxo principal: `scrape_faixa_adaptativa(keyword, lo, hi)`

```
ENTRADA: keyword, preço mínimo (lo), preço máximo (hi)

1. Navegar para Amazon: /s?k={keyword}&low-price={lo}&high-price={hi}
2. Ler total de resultados declarados pela Amazon

3. SE total ≤ 400:
     → Paginar normalmente (até 150 páginas ou dedup stall)
     → FIM

4. SE (hi - lo) > SPLIT_FLOOR (1):
     → mid = (lo + hi) / 2
     → Recursão: scrape_faixa_adaptativa(keyword, lo, mid)
     → Recursão: scrape_faixa_adaptativa(keyword, mid, hi)
     → FIM

5. SE (hi - lo) ≤ SPLIT_FLOOR E total > 400:
     → SORT ROTATION: rodar mesma faixa 4 vezes com sorts diferentes:
        a) sort=default (relevância)
        b) sort=price-asc-rank
        c) sort=review-rank
        d) sort=date-desc-rank
     → Cada sort traz ~400 ASINs diferentes
     → Dedup automático pelo hash do banco
     → FIM
```

### 2.2 Constantes validadas

```python
SPLIT_THRESHOLD = 400       # Amazon corta paginação em ~7 pgs (~400 itens)
SPLIT_FLOOR = 1             # Divide até $1 de granularidade
MAX_PAGES_POR_FAIXA = 150   # Cap duro anti-loop
DEDUP_STALL_PAGES = 5       # Para se 5 pgs com <3% novos
DEDUP_STALL_RATIO = 0.03    # 3% = quase tudo duplicata
SAVE_CHUNK_PAGES = 10       # Salva no banco a cada 10 pgs (evita perda em crash)
BROWSER_RESTART_PAGES = 500 # Reinicia browser pra liberar RAM

SORT_ROTATION = [None, "price-asc-rank", "review-rank", "date-desc-rank"]
```

### 2.3 Preço teto por moeda (limita o range de recursão)

```python
PRECO_TETO = {
    "USD": 5000,   "EUR": 5000,   "BRL": 20000,  "GBP": 4000,
    "JPY": 750000, "CAD": 7000,   "AUD": 8000,   "MXN": 100000,
    "PLN": 20000,  "SEK": 55000,  "SGD": 7000,   "AED": 20000,
}
```

### 2.4 URL final (anatomia)

```
https://www.amazon.{domain}/s?k={keyword_encoded}
  &low-price={lo}           # preço mínimo
  &high-price={hi}          # preço máximo
  &page={pg}                # paginação (1-based)
  &s={sort}                 # ordenação (opcional, para sort rotation)
  &rh=n%3A{node}&fs=true    # filtro de categoria (quando aplicável)
  &i={department}           # departamento (quando aplicável)
```

**NOTA**: Amazon ignora `low-price`/`high-price` quando combinado com `rh=n:...` (filtro de categoria). Split de preço funciona apenas em buscas SEM categoria.

---

## 3. COMPOSIÇÃO DE QUERIES — O QUE BUSCAR

### 3.1 Queries por país (ordem de execução validada)

| Fase | Template | Como compor a query | Qtd/país | Usa split preço? |
|---|---|---|---|---|
| 1 | cat_keyword | Categoria × keyword genérica | ~6-7 | ❌ (Amazon ignora preço com categoria) |
| 1.5 | enrich_uva | "{uva} {sufixo_idioma}" | 150 | ✅ |
| 1.5 | enrich_regiao | "{região} {sufixo_idioma}" | 2.580 | ✅ |
| 1.5 | enrich_vinicola | "{vinícola} {sufixo_idioma}" | 2.000 | ✅ |
| 1.5 | enrich_autocomplete | resultado literal da API autocomplete | ~50-160 | ✅ |
| 2 | keyword_preco | keyword genérica × split preço | ~6-7 | ✅ |
| 3 | catch_all | keyword principal, sem filtro | 1 | ❌ |

### 3.2 Sufixo por idioma (adicionado ao final de cada query de uva/região/vinícola)

```python
SUFFIX = {
    "pt": "vinho",  "es": "vino",   "fr": "vin",    "de": "wein",
    "it": "vino",   "nl": "wijn",   "pl": "wino",   "sv": "vin",
    "ja": "wine",   "ar": "wine",   "en": "wine",
}
```

**Exemplos reais:**
- Uva + BR: `"cabernet sauvignon vinho"`
- Região + US: `"Napa Valley wine"`
- Vinícola + DE: `"Antinori wein"`

### 3.3 Fontes de dados para as queries

| Dados | Arquivo | Quantidade | Origem |
|---|---|---|---|
| Uvas | `C:\natura-automation\amazon\config.py` (linhas 63-97) | 150 | Curadoria manual (50 tintas + 50 brancas + 50 especiais) |
| Regiões | `C:\natura-automation\amazon\regioes_mundo.py` | 2.580 | Vivino — ordenadas por nº de vinícolas (descendente) |
| Vinícolas | `C:\natura-automation\amazon\vinicolas_mundo.py` | 87.036 (usando top 2.000) | Vivino — ordenadas por popularidade/ratings (descendente) |
| Keywords | `C:\natura-automation\amazon\orchestrator.py` (linhas 108-123) | 6-7 por idioma | Multi-idioma: "wine", "red wine", "white wine" etc |
| Autocomplete | `C:\natura-automation\amazon\autocomplete.py` | ~50-160 por país | Amazon Autocomplete API (grátis, sem auth) |
| Categorias | `C:\natura-automation\amazon\category_discovery.py` | 18 nodes | Hardcoded + discovery dinâmico |
| Marketplaces | `C:\natura-automation\amazon\config.py` (linhas 15-39) | 18 países | Domínios, idiomas, moedas, formato decimal |

Origem original dos datasets de regiões e vinícolas:
- `C:\Users\User\Desktop\_vivino_vinicolas_traduzidas.csv` — 213K vinícolas Vivino (fonte master)

---

## 4. ANTI-BOT — 3 TIERS VALIDADOS

### 4.1 Tiers por marketplace

| Tier | Marketplaces | Delay entre requests | Rotação de browser |
|---|---|---|---|
| Normal | BR US MX CA JP NL SE IE SG BE AU DE IT ES | 0.3s (+jitter) | A cada 500 páginas |
| Sensitive | GB | 3.0s (+jitter) | A cada 50 páginas |
| Ultra | FR PL AE | 6.0s (+jitter) | A cada 15 páginas |

### 4.2 Delay adaptativo

```
- Sucesso: após 20 pgs limpas consecutivas, delay *= 0.9 (acelera)
- Bloqueio: delay *= 2.0 (freia), reseta contador de sucesso
- Mínimo: Normal 0.2s, Sensitive 2.0s, Ultra 4.0s
- Máximo: Normal 10s, Sensitive 20s, Ultra 30s
```

### 4.3 Recovery de bloqueio (3 tentativas por tipo)

| Tipo | Detecção | Ação |
|---|---|---|
| Captcha | "captcha" no HTML ou URL | Espera 60-90s + recria contexto browser |
| 503/dog_page | "Service Unavailable" ou "just need to make sure" | Espera 30-90s (progressivo) |
| Página vazia | HTML < 5000 chars | Espera 30s |
| Redirect login | "/ap/signin" na URL | Recria browser inteiro + espera 10s |

---

## 5. VALIDAÇÃO DE PRODUTO — 4 CAMADAS

### 5.1 Camada 1: É vinho? (`eh_vinho()`)

**Arquivo**: `C:\natura-automation\winegod_codex\utils_scraping.py`

Regex com 300+ padrões de exclusão:
- Destilados: whisky, vodka, gin, rum, tequila, cerveja, sake...
- Outras bebidas: suco, café, água, energético...
- Alimentos: queijo, azeite, chocolate...
- Acessórios: saca-rolha, taça, decanter, cooler...
- Turismo: tour, workshop, degustação...

### 5.2 Camada 2: É acessório? (`eh_acessorio()`)

**Arquivo**: `C:\natura-automation\amazon\utils_playwright.py`

BLACKLIST de ~50 termos Amazon-específicos: corkscrew, wine rack, nail polish, acrylic paint, gel polish...

### 5.3 Camada 3: É livro?

Rejeita ASIN que começa com dígito (livros na Amazon têm ISBN como ASIN).

### 5.4 Camada 4: Produto válido? (`validar_produto()`)

- Título ≥10 caracteres
- ASIN = 10 caracteres (formato: B + 9 alfanuméricos)
- Preço dentro do range por moeda (ex: USD $2-$30.000)
- Rating 0-5 (se presente)

---

## 6. DEDUPLICAÇÃO

### 6.1 Hash de dedup

```python
hash = MD5(normalizar(nome) + "|" + normalizar(produtor) + "|" + safra)
```

Normalização: lowercase, sem acentos, sem pontuação, espaços comprimidos.

### 6.2 Dedup stall (parada inteligente por query)

Se 5 páginas consecutivas trazem <3% de ASINs novos → para a query. Essencial para queries idempotentes (relançamento não perde tempo em queries já cobertas).

### 6.3 Detecção de bundle/kit

Regex detecta: "caja de 6", "pack of 12", "2x bottles", "variety pack", "mixed case", "combo", "kit", "sampler".

---

## 7. EXTRAÇÃO DE PREÇO — 4 FALLBACKS

**Arquivo**: `C:\natura-automation\amazon\utils_playwright.py`

A Amazon usa layouts diferentes por marketplace. Ordem de tentativa:

1. `.a-price:not([data-a-strike]) .a-offscreen` — texto de leitor de tela (mais confiável)
2. `.a-price-whole` + `.a-price-fraction` — DE/JP separam inteiro e decimal
3. `.a-color-price` — preço em badges de bestseller/promo
4. `span[data-a-color='price'] .a-offscreen` — fallback genérico

Parsing locale-aware: vírgula vs ponto decimal por marketplace config.

---

## 8. TRACKING — REGISTRO DE CADA QUERY

### 8.1 Tabela `amazon_queries`

Cada query executada registra:

```sql
pais_codigo, template, query_text, parametros (JSONB),
fase, status (rodando/ok/erro),
paginas_buscadas, itens_encontrados, vinhos_novos, vinhos_duplicados,
tempo_s, erro, executado_em
```

### 8.2 View de progresso

```sql
SELECT pais_codigo, template,
  COUNT(*) FILTER (WHERE status='ok') AS queries_ok,
  COUNT(*) FILTER (WHERE status='erro') AS queries_erro,
  SUM(vinhos_novos) AS vinhos_novos_total,
  MAX(executado_em) AS ultima_execucao
FROM amazon_queries
GROUP BY pais_codigo, template;
```

### 8.3 Templates registrados

- `enrich_uva_x_preco` — uva × split de preço
- `enrich_regiao_x_preco` — região × split de preço
- `enrich_vinicola_x_preco` — vinícola × split de preço
- `enrich_autocomplete_x_preco` — autocomplete × split de preço

---

## 9. OPERAÇÃO — CLI DO ORCHESTRATOR

### 9.1 Comando de lançamento

```bash
cd C:\natura-automation
python -u amazon/orchestrator.py \
  --pais US \
  --fase A \
  --uvas-max 150 \
  --vinicolas-max 2000 \
  --enrich-split-preco
```

### 9.2 Flags disponíveis

| Flag | Default | Descrição |
|---|---|---|
| `--pais XX YY` | Todos os 18 | Quais marketplaces rodar |
| `--fase A B C` | A B C | Quais fases executar |
| `--uvas-max N` | 40 | Quantas uvas buscar (máx 150) |
| `--vinicolas-max N` | 500 | Quantas vinícolas buscar (máx 87.036) |
| `--enrich-split-preco` | Desligado | Ativa split de preço no enrich (Fase 1.5) |

### 9.3 Idempotência

O scraper é idempotente: dedup por hash (nome+produtor+safra) no upsert. Relançar não duplica; queries já cobertas fecham em 1-2 páginas via dedup stall. Seguro relançar a qualquer momento.

---

## 10. MARKETPLACES — 18 PAÍSES

```python
MARKETPLACES = {
    "US": {"domain": "com",    "lang": "en", "moeda": "USD"},
    "BR": {"domain": "com.br", "lang": "pt", "moeda": "BRL"},
    "MX": {"domain": "com.mx", "lang": "es", "moeda": "MXN"},
    "CA": {"domain": "ca",     "lang": "en", "moeda": "CAD"},
    "DE": {"domain": "de",     "lang": "de", "moeda": "EUR"},
    "FR": {"domain": "fr",     "lang": "fr", "moeda": "EUR"},
    "IT": {"domain": "it",     "lang": "it", "moeda": "EUR"},
    "ES": {"domain": "es",     "lang": "es", "moeda": "EUR"},
    "GB": {"domain": "co.uk",  "lang": "en", "moeda": "GBP"},
    "NL": {"domain": "nl",     "lang": "nl", "moeda": "EUR"},
    "PL": {"domain": "pl",     "lang": "pl", "moeda": "PLN"},
    "SE": {"domain": "se",     "lang": "sv", "moeda": "SEK"},
    "BE": {"domain": "com.be", "lang": "fr", "moeda": "EUR"},
    "IE": {"domain": "ie",     "lang": "en", "moeda": "EUR"},
    "AU": {"domain": "com.au", "lang": "en", "moeda": "AUD"},
    "JP": {"domain": "co.jp",  "lang": "ja", "moeda": "JPY"},
    "SG": {"domain": "sg",     "lang": "en", "moeda": "SGD"},
    "AE": {"domain": "ae",     "lang": "en", "moeda": "AED"},
}
```

---

## 11. ESTRATÉGIAS NÃO IMPLEMENTADAS (validadas, prontas para adicionar)

| Estratégia | Ganho medido | Custo | Como implementar |
|---|---|---|---|
| Sort=review-rank (global) | +55 ASINs/query | 1 query extra | Adicionar ao SORT_ROTATION (já feito nas faixas saturadas) |
| Sort=date-desc (global) | +55 ASINs/query | 1 query extra | Idem |
| Rating ≥4★ filter | +78 ASINs/query | 1 query extra | `&rh=p_72%3A{node_id_rating}` (ID varia por marketplace) |
| Discovery pages | +49 ASINs/país | 4 URLs fixas | `/zgbs/grocery/{node}`, `/gp/new-releases/` etc |
| Vinícolas 5K-10K-20K | Estimado +5-15K/país | +3K-18K queries | Subir `--vinicolas-max` progressivamente |

**Resultado do estudo empírico** (arquivo: `C:\natura-automation\logs\filter_research_US_20260415_190140.json`):

Baseline (sem filtro): 321 ASINs → União de tudo: 796 ASINs (+148%).

---

## 12. LIÇÕES APRENDIDAS (para o software autônomo)

1. **Split de preço é obrigatório** — sem ele, perde 50%+ dos vinhos em mercados densos (US, CA, NL, AU)
2. **SPLIT_FLOOR=1** — mercados com muitos vinhos baratos ($5-$20) saturam em faixas de $5. Dividir até $1 resolve
3. **Threshold 400, não 700** — Amazon corta em ~7 páginas (~400 itens). Acima de 400 = perda certa
4. **Sort rotation é o safety net** — quando não dá mais pra dividir por preço, 4 sorts × 400 itens = ~1.200-1.600 únicos
5. **Dedup stall é essencial** — permite relançar idempotentemente sem custo. 5 pgs com <3% novos = para
6. **Chunk save a cada 10 pgs** — crash não perde mais que 10 pgs de dados
7. **Anti-bot tiers variam muito** — US aguenta 0.3s, FR/PL/AE precisam de 6s. Não usar delay único
8. **Amazon declara números inflados** — "50.001 resultados" geralmente são ~5.000 reais. Não confiar no total, confiar no dedup stall
9. **Tracking por query é crítico** — sem `amazon_queries`, impossível saber o que rodou, o que falta, e o ROI por estratégia
10. **Regiões trazem mais que uvas** — em quase todos os países, `enrich_regiao` produz 3-10x mais vinhos novos que `enrich_uva`
11. **NL: 0 novos em uvas, +10.628 em regiões** — um marketplace "saturado" em uma dimensão pode explodir em outra
12. **Amazon ignora preço com categoria** — `rh=n:...` + `low-price=...` não funciona. Split de preço só em buscas livres
