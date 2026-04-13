# Tail Candidate -- Cache Benchmark e Veredito (Demanda 6C, Tarefa E)

Data de execucao: 2026-04-11
Executor: `scripts/build_candidate_cache.py` + `scripts/run_candidate_fanout_cached.py`
Snapshot oficial do projeto ancorado em 2026-04-10.

## Resumo executivo

- Cacheabilidade medida na cauda inteira (779.383 wines, 6 canais) -- ver `tail_candidate_cacheability_2026-04-10.md`.
- **Os 2 canais caros (`render_nome_produtor`, `render_nome`) tem 95%+ de chaves unicas.** Cache nao reduz trabalho onde o trabalho e.
- Cache persistente SQLite implementado e funcional.
- Equivalencia funcional provada (ver `tail_candidate_cache_equivalence_2026-04-10.md`).
- Custo de build (slice 250, POOL-16): **503,6s** (Render) + import concorrente.
- Custo de consume (slice 250): **1,14s** (Python + SQLite, **zero** DB conns).
- Projecao full 779.383 com cache: **~22 dias wall-clock (POOL-32)**.
- **VEREDITO: NAO APTO**.

## Benchmark controlado: slice 250

### Fase 1 -- build cache

Comando:
```
python scripts/build_candidate_cache.py --slice 250 --workers 16
```

Fases medidas:

| fase | tempo |
|---|---|
| prefetch source info (1 query Render) | 1,8s |
| bootstrap `only_vivino_db` (stream 1,7M + 1,7M ids) | 67,0s |
| enumeracao de chaves unicas no slice | <0,1s |
| pool render (16 workers, 659 chaves unicas render) | **503,6s** |
| pool import (16 workers, 541 chaves, concorrente com render) | <503s (concorrente) |
| write SQLite | incluso no pool |
| **total wall** | **~572s (inclui bootstrap)** |
| **total wall sem bootstrap** | **~505s** |

Taxa observada: `659 chaves render / 503,6s = 1,31 chaves/segundo wall-clock` (POOL-16). Rate para import e muito maior porque as queries sao de ~100-500ms.

### Fase 2 -- consume cache

Comando:
```
python scripts/run_candidate_fanout_cached.py --slice 250 --on-miss fail
```

| fase | tempo |
|---|---|
| prefetch source info (1 query Render) | 1,8s |
| abrir SQLite | <0,01s |
| consume 250 wines via cache (Python + SQLite local) | **1,144s** |
| write detail.csv.gz + per_wine.csv.gz | <0,1s |
| **total wall** | **~3s (inclui prefetch)** |

**Consume rate: 250 wines / 1,144s = 218 wines/sec**. Ou equivalentemente: **4,58ms por wine** (todos os 6 canais, com score + top3 + serializacao).

### Build + consume total

| operacao | tempo |
|---|---|
| build cache (slice 250, POOL-16) | ~505s |
| consume cache (slice 250) | ~1s |
| **total** | **~506s** |

### Comparacao com baselines

| runner | slice 250 (s) | wines/min | ms/wine |
|---|---|---|---|
| **D6A** (runner original, pos-bootstrap) | 2.139,2 | 7,01 | 8.557 |
| **D6B** (fast, POOL-32) | 806,5 | 18,6 | 3.226 |
| **D6C build** (POOL-16) | 503,6 | 29,8 | 2.014 |
| **D6C consume** (cached) | 1,14 | **13.108** | **4,58** |
| **D6C build + consume** | 504,7 | 29,7 | 2.019 |

Ganho wall-clock do path D6C **vs D6A** no slice 250: `2139,2 / 504,7 = 4,24x`.
Ganho wall-clock do path D6C **vs D6B** no slice 250: `806,5 / 504,7 = 1,60x`.

Observacao-chave: **no slice 250 (single pass), cache e apenas 1,60x melhor que D6B**, porque o BUILD do cache ainda paga o mesmo custo de query que o fast runner. O valor do cache so aparece quando o build e amortizado em **multiplos** consumes -- e em um fan-out de uma unica passada, isso nao acontece.

## Extrapolacao para 10.000 e 779.383

### Hipotese de escalonamento

Com base em:
1. Chaves distintas medidas na cauda inteira (Tarefa A):
   - render_nome_produtor: 743.240
   - render_nome: 738.445
   - render_produtor: 212.459
   - import_nome_produtor: 273.583
   - import_nome: 113.907
   - import_produtor: 108.349
   - **TOTAL chaves unicas para build no full: ~2.190.000**
2. Taxa de build observada (POOL-16): 1,31 keys/s wall-clock para a mistura 250/249/160 de render no slice 250.
3. Rate de consume observada: 4,58ms/wine (basicamente limitada por Python/SQLite).

### Extrapolacao POOL-16 (cenario observado)

| alvo | unique keys | wall build | wall consume | wall total | vs D6B |
|---|---|---|---|---|---|
| 250 | 1.200 | 503,6s | 1,14s | ~505s | 1,60x |
| 10.000 | ~41.500 (linear scale do slice 250) | ~9,0h | 46s | **~9,0h** | ~1x |
| 779.383 | ~2.190.000 | ~14 dias | 1h | **~14 dias** | ~2x |

### Extrapolacao POOL-32 (assumindo rendimento medio, D6B nominal)

Assumindo que POOL-32 extrai ~1,3x o throughput de POOL-16 (observado em benchmark do runner fast, ver D6B):

| alvo | wall build | wall consume | wall total |
|---|---|---|---|
| 250 | ~390s | ~1s | ~390s |
| 10.000 | ~7,0h | ~45s | **~7,0h** |
| 779.383 | ~11 dias | ~1h | **~11 dias** |

### Extrapolacao otimista (POOL-48 / 2x POOL-16)

| alvo | wall build | wall consume | wall total |
|---|---|---|---|
| 779.383 | ~7 dias | ~1h | **~7 dias** |

Mesmo sob o cenario mais otimista, o full **permanece na casa de semanas**.

## Cenarios de reuso e amortizacao

O cache so vira um ganho significativo em cenarios de **build-once consume-many**:

| cenario | build | consume | total |
|---|---|---|---|
| single run full (cold) | ~11 dias | 1h | ~11 dias |
| 2 runs full (2x consume) | ~11 dias | 2h | ~11 dias (ganho marginal) |
| 5 runs full (5x consume) | ~11 dias | 5h | ~11 dias + 5h |
| N runs full | ~11 dias | N h | marginal |

Como o consume e ~1h e o build e ~11 dias, **reuso nao resgata o full**. O cache so faria sentido se tivessemos um cenario onde o mesmo cache fosse reconsumido 100+ vezes, o que nao e o caso de um fan-out de auditoria de cauda.

## Custo ponderado por canal (dados reais D6B)

Tempo CPU-Postgres estimado por canal no full (sequencial, 1 backend):

| canal | queries sem cache | queries com cache | tempo sem cache (s) | tempo com cache (s) | economia (s) | economia % |
|---|---|---|---|---|---|---|
| render_nome_produtor | 779.383 | 743.240 | 3.896.915 | 3.716.200 | 180.715 | 4,64% |
| render_nome | 779.383 | 738.445 | 1.401.898 | 1.329.201 | 72.697 | 5,19% |
| render_produtor | 729.386 | 212.459 | 1.094.079 | 318.689 | 775.390 | 70,87% |
| import_nome_produtor | 727.883 | 273.583 | 582.306 | 218.866 | 363.440 | 62,41% |
| import_nome | 778.615 | 113.907 | 233.585 | 34.172 | 199.412 | 85,37% |
| import_produtor | 728.474 | 108.349 | 218.542 | 32.505 | 186.038 | 85,13% |
| **TOTAL** | | | **7.427.425** | **5.649.633** | **1.777.792** | **23,93%** |

Ou seja: o **teto teorico** do cache e cortar ~24% do custo CPU-Postgres total. Sob POOL-32 real:
- D6B (sem cache): ~29 dias
- D6C (com cache): ~29 × 0,76 = **~22 dias**

Esta e a melhor projecao defensavel com os dados reais.

## Meta de aceite

Criterios da demanda:
- chaves quase todas unicas nos canais caros → **CONFIRMADO** (94,8% e 95,4%)
- ganho potencial pequeno → **CONFIRMADO** (~24% no agregado, ~5% nos canais caros)
- caminho com cache ainda em muitos dias para o full → **CONFIRMADO** (~11-22 dias)

As tres condicoes de **NAO APTO** sao disparadas.

## Veredito

**NAO APTO.**

### Justificativa numerica

- **Slice 250**: cache corta wall-clock vs D6A em 4,24x, mas **so 1,60x vs D6B** -- porque o build e a parte dominante em single-pass.
- **Full 779.383**: projecao com cache (POOL-32) em **~22 dias** (vs ~29 dias D6B e ~77 dias D6A). Melhoria de ~24%, mas ainda "muitos dias".
- **Alvo inalcancavel com cache sozinho**: o gargalo real (`render_nome_produtor` + `render_nome`) tem 95%+ chaves unicas. Cache e semanticamente correto mas estruturalmente impotente para essa parte do custo.

### Justificativa estrutural

O problema nao e round-trip nem cache. O problema e o **custo intrinseco de cada query individual** contra `vivino_match` no canal de texto longo combinado. O cache deduplica 5% dessas queries. Para destravar seria preciso:

1. **reduzir o custo de cada query** individual (troca de engine FTS, sharding por chave, indice dedicado para pares (nome, produtor))
2. **ou mudar a logica** (tirar um canal, reduzir LIMIT, etc.) -- fora do escopo, proibido
3. **ou precomputar tudo num one-shot massivo** (levaria as mesmas ~11 dias, mas reusavel)

## Bloqueios reais que restam

1. **render_nome_produtor** e **render_nome** tem 94-95% de chaves unicas. Nenhum cache por chave resolve. Qualquer ataque de performance precisa ir **abaixo da query** (engine, indice, datapath).
2. **Cache build e basicamente equivalente ao fan-out full em custo CPU**. A unica economia vem da dedup, que agrega 24% (casca do problema).
3. **Cenarios de reuso nao compensam**: consume custa 1h, build custa 11+ dias. Mesmo com 10 reexecucoes, o total e dominado pelo build. O modelo build-once-consume-many **nao e a forma desta carga de trabalho**.
4. **Similaridade trgm e CPU-bound no Postgres**. Nao melhora por paralelismo driver-side alem de um certo ponto (POOL-32 ja saturou em D6B).
5. **Consume e praticamente gratis** (4,58ms/wine, ~1h para full). Se um dia o build fosse barato, o fan-out seria rapido. Mas o build e caro, e e a parte que precisa de solucao arquitetonica.

## Caminhos fora deste escopo

Registrados apenas como direcoes possiveis para futuras demandas (nao foram avaliados aqui):

1. **Troca de engine de busca**: substituir `pg_trgm` por ParadeDB `pg_search` (BM25 nativo), ou fora do Postgres (Meilisearch, Tantivy, Lucene). Pode reduzir o custo por query em 1-2 ordens de grandeza, mas requer migracao de indice e validacao semantica nao-trivial.
2. **Materializacao de candidate set por produtor**: uma tabela pre-computada `produtor -> top100 wines` manutida offline. Se o dataset de produtores fosse estavel, seria uma materialized view com custo de refresh isolado.
3. **Rodar o runner colocado ao banco** (mesmo data center), eliminando qualquer latencia de rede de bootstrap.
4. **Sharding de `vivino_match`** por `pais_codigo` ou prefix de `produtor_normalizado`: cada query opera numa particao menor, reduzindo custo de trgm walk.
5. **Limitar a cauda** a um subset prioritario primeiro (ex: wines com y2_any_matched=0 e que tem URLs ativas), rodando o fan-out em ~50k em vez de 779k.

Estas direcoes devem ser avaliadas em demandas subsequentes, nao neste benchmark.

## Artefatos gerados

- `scripts/measure_candidate_key_cardinality.py`
- `scripts/build_candidate_cache.py`
- `scripts/run_candidate_fanout_cached.py`
- `reports/candidate_cache_slice250.sqlite3`
- `reports/tail_candidate_cacheability_channels_2026-04-10.csv`
- `reports/tail_candidate_cacheability_2026-04-10.md`
- `reports/tail_candidate_cache_equivalence_2026-04-10.md`
- `reports/tail_candidate_cache_benchmark_2026-04-10.md` (este arquivo)
- `reports/tail_candidate_fanout_cached_250_detail_2026-04-10.csv.gz`
- `reports/tail_candidate_fanout_cached_250_per_wine_2026-04-10.csv.gz`
