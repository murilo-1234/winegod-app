# Guia Completo — Estratégias de Scraping da Amazon para Vinhos

> **Objetivo**: documentar TODAS as formas de composição de pesquisa usadas para extrair vinhos da Amazon, incluindo: fontes de dados, composição de queries, filtros, validação e resultados. Este documento serve de referência para replicar a mesma abordagem em outros marketplaces (ex: CellarTracker, Wine.com).

> **Atualizado**: 2026-04-17

---

## 1. FONTES DE DADOS (arquivos que alimentam as pesquisas)

### 1.1 Uvas — 150 variedades

**Arquivo**: `C:\natura-automation\amazon\config.py` (linhas 63-97)

Divididas em 3 grupos de 50:

**Tintas (50)**: cabernet sauvignon, merlot, pinot noir, syrah, malbec, tempranillo, sangiovese, nebbiolo, zinfandel, grenache, mourvedre, carmenere, tannat, touriga nacional, primitivo, barbera, montepulciano, pinotage, gamay, petit verdot, cabernet franc, nero d'avola, aglianico, corvina, graciano, bonarda, carignan, cinsault, dolcetto, mencía, petite sirah, blaufrankisch, zweigelt, st laurent, dornfelder, kadarka, plavac mali, xinomavro, sagrantino, negroamaro, lagrein, teroldego, refosco, schioppettino, frappato, nerello mascalese, cannonau, bobal, monastrell, tinta roriz

**Brancas (50)**: chardonnay, sauvignon blanc, riesling, pinot grigio, gewurztraminer, viognier, chenin blanc, albarino, gruner veltliner, torrontes, verdejo, vermentino, muscadet, semillon, marsanne, roussanne, trebbiano, garganega, fiano, falanghina, godello, txakoli, assyrtiko, furmint, moscato, pinot blanc, muller thurgau, silvaner, scheurebe, kerner, arneis, gavi, cortese, pecorino, verdicchio, friulano, ribolla gialla, malvasia, verdelho, encruzado, loureiro, trajadura, fernao pires, arinto, antao vaz, macabeo, xarel lo, parellada, airen, palomino

**Especiais (50)**: prosecco, cava, cremant, lambrusco, vinho verde, champagne blend, bordeaux blend, rhone blend, super tuscan, meritage, port blend, sherry blend, madeira blend, marsala blend, tokaji blend, ice wine, late harvest, noble rot, passito, amarone blend, orange wine, natural wine, pet nat, skin contact, amphora wine, rose blend, blanc de blancs, blanc de noirs, brut nature, extra brut, solera, oloroso, amontillado, fino sherry, manzanilla, tawny port, ruby port, vintage port, lbv port, colheita port, sauternes, barsac, trockenbeerenauslese, beerenauslese, spatlese, auslese, kabinett, eiswein, vin santo, recioto

### 1.2 Regiões vinícolas do mundo — 2.580

**Arquivo**: `C:\natura-automation\amazon\regioes_mundo.py` (2.588 linhas)

**Origem**: Vivino (extraído de `C:\Users\User\Desktop\_vivino_vinicolas_traduzidas.csv` com 213K vinícolas). Ordenado por número de vinícolas na região (descendente).

**Formato**: lista Python de strings. Nomes em inglês ou nome original (Bordeaux, Champagne, Toscana, etc.)

**Top 20** (maior densidade de vinícolas):
1. Bordeaux (7.327 vinícolas)
2. Champagne (5.840)
3. California (5.749)
4. Tuscany (4.184)
5. Veneto (3.759)
6. Mendoza (3.376)
7. Piedmont (3.074)
8. Burgundy (2.836)
9. Napa Valley (2.784)
10. Mosel (2.742)
11. Central Valley Chile (2.409)
12. Languedoc-Roussillon (2.383)
13. Vin de France (2.131)
14. Rioja (2.117)
15. Languedoc (2.059)
16. Rheinhessen (2.037)
17. Terre Siciliane (1.999)
18. Puglia (1.943)
19. Pfalz (1.871)
20. South Australia (1.853)

**Nota**: arquivo anterior em PT (`C:\Users\User\Desktop\regioes_de_vinho.txt`) tinha 2.765 regiões — ~185 perdidas na migração para nomes Vivino. Merge pendente.

### 1.3 Vinícolas do mundo — 87.036

**Arquivo**: `C:\natura-automation\amazon\vinicolas_mundo.py` (87.044 linhas)

**Origem**: Vivino (vinícolas com 100+ ratings). Ordenado por popularidade (total de ratings, descendente).

**Top 20**:
1. Antinori (1.009.619 ratings)
2. Casillero del Diablo (696.704)
3. Familia Torres (627.624)
4. Trapiche (582.261)
5. San Marzano (503.381)
6. Santa Rita (502.315)
7. Marqués de Riscal (500.669)
8. Félix Solís (488.280)
9. Louis Jadot (487.707)
10. Masi (487.350)

**Cobertura atual**: usando top 2.000 (de 87.036). ROI cai rapidamente após ~5K (vinícolas obscuras não aparecem na Amazon).

### 1.4 Produtores (lista curta) — 200

**Arquivo**: `C:\natura-automation\amazon\config.py` (linhas 170-218)

200 produtores agrupados por país: França (20), Itália (20), Espanha (15), Portugal (10), USA (25), Argentina (15), Chile (15), Austrália (10), NZ (5), Alemanha (5), África do Sul (5), Globais/Populares (30).

**Nota**: este arquivo não é usado em Fase 1.5 (que usa `vinicolas_mundo.py`). Existe como referência/legado de uma versão anterior do scraper.

### 1.5 Keywords genéricas multi-idioma — 6-7 por idioma

**Arquivo**: `C:\natura-automation\amazon\orchestrator.py` (linhas 108-123)

| Idioma | Keywords |
|---|---|
| en | wine, red wine, white wine, rose wine, sparkling wine, champagne |
| pt | vinho, vinho tinto, vinho branco, espumante, champagne, prosecco, vinho rose |
| es | vino, vino tinto, vino blanco, rosado, cava, champagne |
| fr | vin, vin rouge, vin blanc, champagne, rose, mousseux |
| de | wein, rotwein, weisswein, roseewein, sekt, champagner |
| it | vino, vino rosso, vino bianco, spumante, prosecco, champagne |
| nl | wijn, rode wijn, witte wijn, mousserende wijn, champagne |
| pl | wino, wino czerwone, wino biale, wino musujace, szampan |
| sv | vin, rott vin, vitt vin, mousserande vin, champagne |
| ja | wine, red wine, white wine, sparkling wine |
| ar | wine, red wine, white wine |

### 1.6 Autocomplete Amazon — ~50-160 queries por país

**Arquivo**: `C:\natura-automation\amazon\autocomplete.py` (160 linhas)

Usa a API de autocompletar da Amazon (grátis, sem auth, puro HTTP):
```
https://completion.amazon.{domain}/api/2017/suggestions?alias=aps&mid={marketplace_id}&prefix={seed}
```

**Seeds por idioma** (20 por idioma): "vinho", "vinho tinto", "vinho cab", "vinho mer", "vinho pin", "vinho bor", etc. Cada seed retorna ~10 sugestões reais que compradores buscam. Filtro: deve conter termo de vinho, não pode ser acessório.

**Exemplo de resultado para BR**: "vinho cabernet sauvignon", "vinho espumante brut", "vinho esporão reserva", etc.

### 1.7 Categorias Amazon — 18 nodes conhecidos

**Arquivo**: `C:\natura-automation\amazon\category_discovery.py` (191 linhas)

Nodes hardcoded por marketplace (validados):
```
US: 2983386011 (Wine)        BR: 19778191011 (Vinhos)
MX: 20684299011 (Vinos)      CA: 6681301011 (Wine)
DE: 340846031 (Wein)          FR: 2200005031 (Vin)
IT: 2454166031 (Vino)         ES: 6198075031 (Vino)
GB: 364277031 (Wine)          NL/BE/IE: descobertos dinamicamente
JP/AU/SG/AE/PL/SE: descobertos dinamicamente
```

Se o node hardcoded falhar, discovery automático busca keywords + extrai nodes da sidebar.

---

## 2. COMPOSIÇÃO DE QUERIES (como os dados viram buscas)

### 2.1 Sufixo por idioma

Cada query de uva/região/vinícola recebe um sufixo no idioma local:

```python
suffix = {"pt": "vinho", "es": "vino", "fr": "vin", "de": "wein",
          "it": "vino", "nl": "wijn", "pl": "wino", "sv": "vin",
          "ja": "wine", "ar": "wine"}.get(lang, "wine")
```

**Arquivo**: `C:\natura-automation\amazon\orchestrator.py` (linhas 704-707)

### 2.2 Templates de query (Fase 1.5 — enrich)

Cada query é composta por: `"{termo} {sufixo}"`. Exemplos:

| Template | Exemplo (US) | Exemplo (BR) | Exemplo (DE) |
|---|---|---|---|
| enrich_uva | "cabernet sauvignon wine" | "cabernet sauvignon vinho" | "cabernet sauvignon wein" |
| enrich_regiao | "Bordeaux wine" | "Bordeaux vinho" | "Bordeaux wein" |
| enrich_vinicola | "Antinori wine" | "Antinori vinho" | "Antinori wein" |
| enrich_autocomplete | (resultado literal da API) | (resultado literal da API) | (resultado literal da API) |

**Arquivo**: `C:\natura-automation\amazon\orchestrator.py` (linhas 709-728)

### 2.3 Quantidade de queries por país (v2)

| Tipo | Quantidade | Exemplo |
|---|---|---|
| Uvas × sufixo | 150 | "pinot noir wine" |
| Regiões × sufixo | 2.580 | "Barossa Valley wine" |
| Vinícolas × sufixo | 2.000 | "Penfolds wine" |
| Autocomplete | ~50-160 | "wine gift set under 50" |
| **Total por país** | **~4.780-4.890** | |

Cada query pode gerar 1-20+ sub-queries quando split de preço está ativo.

---

## 3. ESTRATÉGIAS DE EXTRAÇÃO (como maximizar resultados por query)

### 3.1 Problema: Amazon corta em ~400 resultados

A Amazon mostra no máximo ~7 páginas (~400 itens) por busca, mesmo que existam milhares. Busca "wine" retorna 400 de 50.000+. Precisamos de formas de **fatiar a busca em pedaços menores** que somem mais do que o todo.

### 3.2 Estratégia 1 — Split por faixa de preço (IMPLEMENTADA ✅)

**Arquivo**: `C:\natura-automation\amazon\orchestrator.py`, função `scrape_faixa_adaptativa()` (linhas 530-606)

**Como funciona**:
1. Faz a busca e lê quantos resultados Amazon declara
2. Se ≤700: pagina tudo normalmente
3. Se >700: divide a faixa ao meio e faz recursão em cada metade
4. Para quando faixa ≤ SPLIT_FLOOR (5 unidades de moeda)

**URL**: `amazon.com/s?k=cabernet+sauvignon+wine&low-price=25&high-price=50`

**Faixas de preço por moeda** (arquivo: orchestrator.py linhas 127-131):
```
USD: 1 até 5.000    EUR: 1 até 5.000    BRL: 1 até 20.000
GBP: 1 até 4.000    JPY: 1 até 750.000  CAD: 1 até 7.000
AUD: 1 até 8.000    MXN: 1 até 100.000  PLN: 1 até 20.000
SEK: 1 até 55.000   SGD: 1 até 7.000    AED: 1 até 20.000
```

**Resultado empírico** (testado em US com "cabernet sauvignon wine"):
- Baseline (sem split): 321 ASINs em 7 páginas
- Split em 6 faixas ($0-25, 25-50, 50-100, 100-300, 300-1K, 1K-10K): **632 ASINs em 16 páginas**
- **Ganho: +97% (quase 2x), com 0.5% de repetição entre faixas**
- **Arquivo do resultado**: `C:\natura-automation\logs\filter_research_US_20260415_190140.json`

### 3.3 Estratégia 2 — Variação de sort order (TESTADA, NÃO IMPLEMENTADA)

**Arquivo**: `C:\natura-automation\amazon\filter_research.py` (linhas 61-68)

A mesma query com sort diferente retorna ASINs diferentes (Amazon prioriza itens distintos por critério).

| Sort | Parâmetro URL | Novos vs baseline |
|---|---|---|
| Relevância (default) | nenhum | — (baseline) |
| Preço crescente | `&s=price-asc-rank` | +52 ASINs |
| Preço decrescente | `&s=price-desc-rank` | +52 ASINs |
| Avaliação | `&s=review-rank` | +55 ASINs |
| Mais recente | `&s=date-desc-rank` | +55 ASINs |

**Custo**: 1 query extra por sort (4 pgs cada = +16 pgs total)
**Arquivo do resultado**: `C:\natura-automation\logs\filter_research_US_20260415_190140.json`

### 3.4 Estratégia 3 — Filtro de rating (TESTADA, NÃO IMPLEMENTADA)

**URL**: `amazon.com/s?k=cabernet+sauvignon+wine&rh=p_72%3A1248879011` (4+ estrelas, US)

**Resultado**: +78 ASINs novos vs baseline. A Amazon reorganiza os resultados quando filtra rating, mostrando itens que ficam escondidos na busca sem filtro.

**Nota**: o ID `p_72:1248879011` é específico do marketplace US. Outros marketplaces têm IDs diferentes para o filtro de rating.

### 3.5 Estratégia 4 — Discovery pages (TESTADA, NÃO IMPLEMENTADA)

**Arquivo**: `C:\natura-automation\amazon\filter_research.py` (linhas 73-79)

Páginas especiais da Amazon que listam vinhos por popularidade:
```
/Best-Sellers-Grocery-Wines/zgbs/grocery/{node_id}     (Top 100 mais vendidos)
/gp/new-releases/grocery/{node_id}                      (Novos lançamentos)
/gp/movers-and-shakers/grocery/{node_id}                (Em alta)
/gp/most-wished-for/grocery/{node_id}                   (Mais desejados)
```

**Resultado**: +49 ASINs únicos (4 páginas). Pouco volume, mas traz ASINs que podem não aparecer em buscas por keyword.

### 3.6 Estratégia 5 — Categoria × keyword × sem filtro de preço (IMPLEMENTADA ✅)

**Arquivo**: `C:\natura-automation\amazon\orchestrator.py` (linhas 654-693)

Para cada node de categoria descoberto, cruza com cada keyword genérica:
```
URL: amazon.com/s?k=wine&rh=n%3A2983386011&fs=true
```

**Nota**: Amazon ignora `low-price`/`high-price` quando combinado com `rh=n:...`. Verificado empiricamente em IE. Por isso Fase 1 não usa split de preço.

### 3.7 Estratégia 6 — Autocomplete real da Amazon (IMPLEMENTADA ✅)

**Arquivo**: `C:\natura-automation\amazon\autocomplete.py`

Diferente das queries compostas artificialmente (uva+sufixo), o autocomplete traz queries que **compradores reais** digitam. Exemplos:
- "wine gift set under 50"
- "organic red wine from spain"
- "champagne for wedding"

Essas queries alcançam vinhos que não aparecem com nomes de uva/região. É gratuito, sem autenticação, ~50-160 queries por país.

### 3.8 Estratégia 7 — Keyword sem categoria (IMPLEMENTADA ✅)

**Arquivo**: `C:\natura-automation\amazon\orchestrator.py` (linhas 809-832)

Mesmas keywords genéricas, mas SEM filtro de categoria (`rh=n:...`). Captura vinhos classificados fora do node "Wine" (ex: em "Grocery", "Gourmet Food", etc.).

### 3.9 Estratégia 8 — Catch-all sem filtro de preço (IMPLEMENTADA ✅)

**Arquivo**: `C:\natura-automation\amazon\orchestrator.py` (linhas 834-845)

Query genérica sem preço nem categoria. Captura produtos sem preço listado (ex: "Currently unavailable" mas com ficha no catálogo).

### 3.10 Estratégia descartada — Combo split+sort

**Arquivo**: `C:\natura-automation\logs\filter_research_US_20260415_190140.json`

Split de preço + sort=price-asc trouxe **MENOS** do que split puro (265 vs 632 ASINs). O sort comprime resultados dentro de cada faixa. Não combinar.

### 3.11 Estratégia descartada — Departamento Grocery (&i=grocery)

**Arquivo**: `C:\natura-automation\amazon\orchestrator.py` (linhas 806-808, comentado)

Testado empiricamente: `&i=grocery` retorna bebidas mistas (whisky, cerveja, suco) e apenas 2 ASINs exclusivos de vinho vs busca normal. Não compensa.

---

## 4. CONSTRUÇÃO DA URL FINAL

### 4.1 Função `build_search_url()`

**Arquivo**: `C:\natura-automation\amazon\orchestrator.py` (linhas 138-165)

```
https://www.amazon.{domain}/s?k={keyword_encoded}
  &low-price={lo}                   # opcional: preço mínimo
  &high-price={hi}                  # opcional: preço máximo
  &page={pg}                        # opcional: paginação (1-based)
  &rh=n%3A{category_node}&fs=true   # opcional: filtro de categoria
  &i={department}                   # opcional: departamento (grocery, wine)
  &s={sort}                         # opcional: ordenação
```

### 4.2 Exemplos concretos de URLs geradas

**Uva + split de preço (US)**:
```
https://www.amazon.com/s?k=cabernet+sauvignon+wine&low-price=25&high-price=50
https://www.amazon.com/s?k=cabernet+sauvignon+wine&low-price=50&high-price=100
```

**Região + sufixo (BR)**:
```
https://www.amazon.com.br/s?k=Bordeaux+vinho
```

**Vinícola + sufixo (DE)**:
```
https://www.amazon.de/s?k=Antinori+wein
```

**Categoria + keyword (JP)**:
```
https://www.amazon.co.jp/s?k=wine&rh=n%3A71588051&fs=true
```

**Sort variado**:
```
https://www.amazon.com/s?k=merlot+wine&s=review-rank
https://www.amazon.com/s?k=merlot+wine&s=date-desc-rank
```

**Rating filter**:
```
https://www.amazon.com/s?k=wine&rh=p_72%3A1248879011
```

---

## 5. VALIDAÇÃO (o que passa e o que é descartado)

### 5.1 Filtro "é vinho?" — multi-camada

**Camada 1** — `eh_vinho()` em `C:\natura-automation\winegod_codex\utils_scraping.py` (linhas 402-409)

Regex com 300+ padrões de exclusão:
- Destilados: whisky, vodka, gin, rum, tequila, cerveja, sake, grappa...
- Outras bebidas: suco, café, água, energético...
- Alimentos: queijo, azeite, chocolate, arroz...
- Acessórios: saca-rolha, taça, decanter, cooler...
- Turismo/experiências: tour, workshop, degustação...
- Tecnologia/higiene: celular, shampoo, sabão...

**Camada 2** — `eh_acessorio()` em `C:\natura-automation\amazon\utils_playwright.py` (linhas 392-394)

BLACKLIST de ~50 termos específicos da Amazon: corkscrew, wine rack, nail polish, acrylic paint, gel polish, dip powder, etc.

**Camada 3** — Filtro ISBN: rejeita ASIN que começa com dígito (livros sobre vinho).

**Camada 4** — `validar_produto()` em `C:\natura-automation\amazon\utils_playwright.py` (linhas 407-429)
- Título ≥10 caracteres
- ASIN = 10 caracteres (formato: B + 9 alfanuméricos)
- Preço dentro do min/max por moeda (ex: USD $2-$30.000)
- Rating entre 0-5

### 5.2 Deduplicação

**Arquivo**: `C:\natura-automation\winegod_codex\utils_scraping.py`, função `gerar_hash_dedup()` (linhas 236-242)

Hash MD5 de: `normalizar(nome) | normalizar(produtor) | safra`

Normalização: lowercase, sem acentos, sem pontuação, espaços comprimidos.

### 5.3 Detecção de bundle/kit

**Arquivo**: `C:\natura-automation\winegod_codex\utils_scraping.py`, função `nome_indica_bundle()` (linhas 312-317)

Regex detecta: "caja de 6", "pack of 12", "2x bottles", "variety pack", "mixed case", "combo", "kit", "sampler".

### 5.4 Tipos de vinho em japonês

Reconhecimento especial para Amazon JP:
- 赤ワイン = Tinto
- 白ワイン = Branco
- ロゼ = Rosé
- スパークリング = Espumante

---

## 6. ANTI-BOT E RESILIÊNCIA

### 6.1 Tiers de delay adaptativo

**Arquivo**: `C:\natura-automation\amazon\utils_playwright.py`, classe `AdaptiveDelay` (linhas 188-244)

| Tier | Marketplaces | Delay | Rotação browser |
|---|---|---|---|
| Normal | BR US MX CA JP NL SE IE SG BE AU DE IT ES | 0.3s | 500 pgs |
| Sensitive | GB | 3.0s | 50 pgs |
| Ultra | FR PL AE | 6.0s | 15 pgs |

Delay aumenta 2x em bloqueio, diminui 10% a cada 20 pgs limpas.

### 6.2 Recovery automático

**Arquivo**: `C:\natura-automation\amazon\utils_playwright.py`, função `lidar_com_bloqueio()` (linhas 138-164)

- Captcha → espera 60-90s + recria contexto
- 503/dog_page/pagina_vazia → espera 30-90s
- Redirect login → recria browser inteiro

### 6.3 Dedup stall (parada inteligente)

**Arquivo**: `C:\natura-automation\amazon\orchestrator.py` (linhas 92-93)

Se 5 páginas consecutivas trazem <3% de ASINs novos → para a query cedo. Evita gastar tempo em queries que já saturaram.

---

## 7. RESULTADOS DO ESTUDO EMPÍRICO

### 7.1 Dados do experimento

**Script**: `C:\natura-automation\amazon\filter_research.py`
**Resultado**: `C:\natura-automation\logs\filter_research_US_20260415_190140.json`

Query: "cabernet sauvignon wine" | Marketplace: US | Data: 2026-04-15

| # | Estratégia | ASINs únicos | Novos vs baseline | Novos/página | Status |
|---|---|---|---|---|---|
| 🏆 | Split por preço (6 faixas) | 632 | +329 | 20.6 | ✅ Implementada |
| 2 | Split preço + sort asc | 265 | +125 | 13.9 | ❌ Descartada (inferior ao split puro) |
| 3 | Sort=review-rank | 193 | +55 | 13.8 | Pendente |
| 4 | Sort=date-desc | 194 | +55 | 13.8 | Pendente |
| 5 | Sort=price-asc | 194 | +52 | 13.0 | Pendente |
| 6 | Sort=price-desc | 193 | +52 | 13.0 | Pendente |
| 7 | Discovery pages | 49 | +49 | 12.3 | Pendente |
| 8 | Rating ≥4★ | 325 | +78 | 11.1 | Pendente |
| — | **União de tudo** | **796** | **+475 (+148%)** | — | — |

### 7.2 Dados de produção (tracking v2 — 2026-04-17)

**View SQL**: `SELECT * FROM progresso_estrategias` no banco `winegod_db`

| País | Template | Queries OK | Vinhos novos | Dupes |
|---|---|---|---|---|
| JP | enrich_uva_x_preco | 150 ✅ | 163 | 505 |
| JP | enrich_regiao_x_preco | 2.580 ✅ | 323 | 4.256 |
| JP | enrich_vinicola_x_preco | 1.992 (~99%) | 1.056 | 598 |
| US | enrich_uva_x_preco | 150 ✅ | 377 | 652 |
| US | enrich_regiao_x_preco | 2.416 (94%) | 7.616 | 6.528 |
| DE | enrich_uva_x_preco | 150 ✅ | 226 | 1.363 |
| DE | enrich_regiao_x_preco | 2.570 ✅ | 429 | 3.189 |
| NL | enrich_uva_x_preco | 150 ✅ | 0 | 12 |
| NL | enrich_regiao_x_preco | 162 (6%) | 4.454 | 3.042 |

**Insight**: regiões trazem mais vinhos novos que uvas na maioria dos países. NL é caso extremo — 0 novos nas uvas (tudo duplicata do catálogo IE), mas 4.454 novos nas regiões.

---

## 8. RESUMO — TODAS AS FORMAS DE PESQUISA

| # | Método | Queries/país | Implementada | Ganho estimado |
|---|---|---|---|---|
| 1 | Categoria × keyword genérica | ~6-7 | ✅ | Base (discovery inicial) |
| 2 | Uva × sufixo idioma | 150 | ✅ | +163 a +377/país |
| 3 | Região × sufixo idioma | 2.580 | ✅ | +323 a +7.616/país |
| 4 | Vinícola × sufixo idioma | 2.000 (de 87K) | ✅ | +340 a +1.056/país |
| 5 | Autocomplete Amazon | ~50-160 | ✅ | +25/país |
| 6 | Keyword sem categoria | ~6-7 | ✅ | Complementar |
| 7 | Catch-all sem preço | 1 | ✅ | Complementar |
| 8 | **Split por preço** (recursivo) | multiplica 1-7 acima | ✅ (v2) | **+97% vs baseline** |
| 9 | Sort=review-rank | multiplica queries | ❌ Pendente | +55 ASINs/query |
| 10 | Sort=date-desc | multiplica queries | ❌ Pendente | +55 ASINs/query |
| 11 | Sort=price-asc | multiplica queries | ❌ Pendente | +52 ASINs/query |
| 12 | Sort=price-desc | multiplica queries | ❌ Pendente | +52 ASINs/query |
| 13 | Filtro rating ≥4★ | multiplica queries | ❌ Pendente | +78 ASINs/query |
| 14 | Discovery pages (bestseller etc) | 4 por país | ❌ Pendente | +49 ASINs |
| 15 | Ondas de vinícolas (5K→10K→20K) | +3K a +18K queries | ❌ Pendente | Depende do ROI |

**Filosofia**: todas as formas que trouxerem >0 vinhos serão executadas. Estudo contínuo — sempre buscar novas formas.
