# Tail Candidate -- Cacheabilidade (Demanda 6C, Tarefas A + B)

Data de execucao: 2026-04-11
Executor: `scripts/measure_candidate_key_cardinality.py`
Snapshot oficial do projeto ancorado em 2026-04-10.

## Tarefa A -- Medicao de cacheabilidade na cauda inteira

### Universo

- Fonte: `reports/tail_y2_lineage_enriched_2026-04-10.csv.gz` (779.383 render_wine_ids)
- Normalizacao aplicada: **identica a D5** (usa `scripts/build_candidate_controls.py`)
- Stream feito a partir do Render (Oregon) em chunks de 20.000 ids
- Wall time da coleta: ~68s

### Chaves por canal

As chaves sao computadas da mesma maneira que as funcoes `channel_*` da D5 formam a entrada das queries SQL:

| canal | formula da chave |
|---|---|
| `render_nome_produtor` | `f"{produtor_normalizado} {nome_normalizado}".strip()` |
| `render_nome` | `nome_normalizado.strip()` (so se `len >= 3`) |
| `render_produtor` | `produtor_normalizado.strip()` (so se `len >= 3`) |
| `import_nome_produtor` | `(longest_word(nome, 4), longest_word(produtor, 3))` -- exige ambas |
| `import_nome` | `longest_word(nome, 4)` |
| `import_produtor` | `longest_word(produtor, 3)` |

Wines cuja chave fica vazia ou nao cumpre o requisito minimo sao contados como `skipped`.

### Resultados

Fonte: `reports/tail_candidate_cacheability_channels_2026-04-10.csv`

| canal | wines | skipped | queries_if_live | chaves distintas | taxa de repeticao | max_freq |
|---|---|---|---|---|---|---|
| **render_nome_produtor** | 779.383 | 0 | 779.383 | **743.240** | **4,64%** | 54 |
| **render_nome** | 779.383 | **0** | 779.383 | **738.445** | **5,25%** | 54 |
| **render_produtor** | 779.383 | 49.997 | 729.386 | **212.459** | **70,87%** | 6.893 |
| **import_nome_produtor** | 779.383 | 51.500 | 727.883 | **273.583** | **62,41%** | 5.820 |
| **import_nome** | 779.383 | 768 | 778.615 | **113.907** | **85,37%** | 13.004 |
| **import_produtor** | 779.383 | 50.909 | 728.474 | **108.349** | **85,13%** | 19.723 |

> Correcao metodologica: a linha `render_nome` anteriormente exibia `skipped=40.938`, inconsistente
> com o CSV oficial `tail_candidate_cacheability_channels_2026-04-10.csv` (onde `skipped_no_key=0`).
> O CSV esta correto: nenhum wine da cauda tem `nome_normalizado` com `len<3`. O MD foi alinhado
> ao CSV. Esta correcao nao reabre a demanda 6C -- e apenas higiene documental.

### Distribuicao de frequencia (numero de chaves por bucket)

Quantas chaves distintas cabem em cada bucket de numero de ocorrencias:

| canal | 1x | 2x | 3-5x | 6-10x | >10x |
|---|---|---|---|---|---|
| render_nome_produtor | 718.350 | 19.715 | 4.493 | 548 | 134 |
| render_nome | 709.796 | 22.929 | 4.983 | 594 | 143 |
| render_produtor | 137.972 | 30.676 | 24.924 | 9.931 | 8.956 |
| import_nome_produtor | 187.021 | 39.305 | 29.374 | 10.142 | 7.741 |
| import_nome | 60.712 | 17.441 | 17.458 | 8.458 | 9.838 |
| import_produtor | 53.695 | 17.570 | 18.042 | 8.844 | 10.198 |

Valores persistidos em `reports/tail_candidate_cacheability_channels_2026-04-10.csv`, campos `freq_1x`, `freq_2x`, `freq_3_5x`, `freq_6_10x`, `freq_gt_10x`.

### Cobertura acumulada das top chaves

Fracao das `queries_if_live` cobertas pelas top-K chaves mais frequentes:

| canal | top 100 | top 1.000 | top 10.000 |
|---|---|---|---|
| render_nome_produtor | 0,24% | 1,00% | 4,01% |
| render_nome | 0,24% | 1,02% | 4,14% |
| render_produtor | 10,79% | 26,18% | 51,41% |
| import_nome_produtor | 8,64% | 20,15% | 41,40% |
| import_nome | 21,32% | 42,81% | 71,41% |
| import_produtor | 17,13% | 38,12% | 69,18% |

## Tarefa B -- Reducao teorica por canal

Queries atuais no full (sem cache), queries restantes com cache, economia:

| canal | queries no full | queries com cache | economia abs | economia % |
|---|---|---|---|---|
| render_nome_produtor | 779.383 | 743.240 | **36.143** | **4,64%** |
| render_nome | 779.383 | 738.445 | **40.938** | **5,25%** |
| render_produtor | 729.386 | 212.459 | **516.927** | **70,87%** |
| import_nome_produtor | 727.883 | 273.583 | **454.300** | **62,41%** |
| import_nome | 778.615 | 113.907 | **664.708** | **85,37%** |
| import_produtor | 728.474 | 108.349 | **620.125** | **85,13%** |

> Formula aplicada: `queries_no_full = queries_if_live` do CSV oficial; `queries_com_cache =
> distinct_keys`; `economia_abs = queries_no_full - queries_com_cache`. Aplicada uniformemente a
> todos os 6 canais. A linha de `render_nome` foi alinhada ao CSV oficial nesta correcao documental
> (Demanda 8 -- Tarefa 0). A correcao e apenas higiene documental e nao reabre D6C.

### Ponderacao pelo custo real de query por canal (dados de D6A/D6B)

Os tempos medios por query (ms) foram derivados da diagnose D6B (3 wines reais):

| canal | tempo medio/query (s) |
|---|---|
| render_nome_produtor | ~5,0 (2,8 - 8,5) |
| render_nome | ~1,8 (1,4 - 2,2) |
| render_produtor | ~1,5 (1,2 - 1,7) |
| import_nome_produtor | ~0,8 (0,3 - 1,8) |
| import_nome | ~0,3 |
| import_produtor | ~0,3 |

Custo total sequencial do full (segundos) com e sem cache:

| canal | sem cache (s) | com cache (s) | economia (s) | % economia |
|---|---|---|---|---|
| render_nome_produtor | 3.896.915 | 3.716.200 | 180.715 | 4,64% |
| render_nome | 1.401.998 | 1.329.201 | 72.797 | 5,19% |
| render_produtor | 1.094.079 | 318.689 | 775.390 | 70,87% |
| import_nome_produtor | 582.306 | 218.866 | 363.440 | 62,41% |
| import_nome | 233.585 | 34.172 | 199.412 | 85,37% |
| import_produtor | 218.542 | 32.505 | 186.038 | 85,13% |
| **TOTAL** | **7.427.425 s** | **5.649.633 s** | **1.777.792 s** | **23,93%** |

- 7.427.425 s sequencial = **86 dias** (ideal, 1 core) na estimativa otimista
- 5.649.633 s sequencial com cache = **65 dias** (ideal, 1 core)

Aplicando o speedup real de POOL-32 observado em D6B (**2,66x**):

- sem cache com parallelismo = 86/2,66 = **~32 dias** (bate com D6B: ~29 dias)
- com cache com parallelismo = 65/2,66 = **~24 dias**

**Reducao total esperada do full com cache: ~24% (de ~29 dias para ~22 dias wall-clock).**

## Leitura interpretativa

**O gargalo nao esta onde o cache ajuda.**

Os dois canais mais caros do runner (`render_nome_produtor` e `render_nome`) juntos representam **~71% do custo total** da D6A/D6B. Eles tem **4,64%** e **5,25%** de duplicacao respectivamente. Em outras palavras:

- 743.240 / 779.383 das chaves de `render_nome_produtor` sao unicas (95,4%)
- 738.445 / 779.383 das chaves de `render_nome` sao unicas (94,8%)

Cache NAO reduz trabalho onde o trabalho e. Cache reduz queries dos canais de produtor e import, que juntos representam apenas ~29% do custo total.

**Onde o cache realmente ajuda:**

- `render_produtor`: 70,87% dedup, top1.000 chaves cobrem 26,2% das queries, top10.000 cobrem 71,4%. **Alvo otimo para cache.**
- `import_nome`: 85,37% dedup, top1.000 chaves cobrem 42,8%, top10.000 cobrem 86,9%. **Alvo excelente**, mas canal ja e barato.
- `import_produtor`: 85,13% dedup, cobertura semelhante. **Alvo excelente**, canal ja e barato.

A assimetria e brutal: os canais com pior dedup sao justamente os caros (nome e nome_produtor, que combinam texto altamente variavel), e os canais com melhor dedup sao os baratos (produtor e anchors, que tem milhares de valores repetidos).

## Conclusao da tarefa A + B

- Cacheabilidade medida objetivamente na cauda inteira (779.383 wines).
- A economia teorica de query count soma **~24% do custo total do fan-out full**.
- O cache persistente NAO muda a ordem de grandeza do problema. Os canais dominantes (`render_nome_produtor`, `render_nome`) tem >94% de chaves unicas.
- Cache persistente vale a pena nos canais de produtor e import, mas o ganho isolado nao destrava o full.

Proxima etapa: construir o prototipo, provar equivalencia, medir wall-clock real, e avaliar se 24% de reducao teorica realmente tira o full do patamar de "muitos dias" -- ou se confirma o limite.

Ver: `tail_candidate_cache_equivalence_2026-04-10.md` e `tail_candidate_cache_benchmark_2026-04-10.md`.
