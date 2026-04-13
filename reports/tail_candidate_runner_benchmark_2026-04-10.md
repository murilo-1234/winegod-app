# Tail Candidate Runner -- Benchmark e Veredito (Demanda 6B)

Data de execucao: 2026-04-11
Executor: `scripts/run_candidate_fanout_fast.py` em slice real de 250 wines vs baseline oficial D6A.

Snapshot oficial do projeto ancorado em 2026-04-10.

## Resumo executivo

- Runner novo implementado: `scripts/run_candidate_fanout_fast.py`
- Estrategia: pool persistente de 32 worker threads + conexoes reusadas + memoizacao de canais por produtor + prefetch unico de source info
- Ganho medido: **2,66x por batch de 250 wines** vs baseline D6A (806,5s vs 2.139,2s mediana pos-bootstrap)
- Equivalencia funcional: **provada** (ver `tail_candidate_runner_equivalence_2026-04-10.md`)
- Projecao piloto 10.000: **~9,0 horas** (vs 23,6h baseline D6A)
- Projecao full 779.383: **~29 dias** (vs 77,2 dias baseline D6A)
- **VEREDITO: NAO APTO**

## Baseline oficial D6A

Fonte: `tail_candidate_fanout_pilot_checkpoint_2026-04-10.json` + `tail_candidate_fanout_pilot_summary_2026-04-10.md`

| metrica | valor |
|---|---|
| batch_size | 250 |
| batches concluidos | 5 (de 40) |
| itens executados | 1.250 |
| batch 0 (com bootstrap) | 1.442,961s |
| batch 1 (pos-bootstrap) | 2.253,460s |
| batch 2 (pos-bootstrap) | 2.024,929s |
| batch 3 (pos-bootstrap) | 1.970,054s |
| batch 4 (pos-bootstrap) | 2.629,141s |
| **mediana pos-bootstrap** | **2.139,2s por batch** |
| itens por minuto (pos-bootstrap) | ~7,01 |
| projecao 10.000 | **~23,6h** |
| projecao 779.383 | **~77,2 dias** |

## Execucao do fast runner no slice deterministico

Slice: primeiros 250 `render_wine_id` do per_wine oficial D6A (1.740.586 .. 1.740.999).

Invocacao:
```
python scripts/run_candidate_fanout_fast.py --slice 250 --workers 32 --fresh
```

### Tempos crus observados

```
[boot] total: 247,927s       # stream 1,72M vivino_ids do Render (Oregon) + stream 1,74M ids vivino_db (local)
[prefetch] got 250 rows em 1,957s   # 1 query Render para 250 source infos (vs 40 queries no D6A)
[batch 1/1] 250 itens, 806,525s, 2.392 rows
[session] 1 batches em 806,7s
```

### Conversao para comparacao honesta

- **D6A post-bootstrap median**: 2.139,2s por batch de 250.
- **FAST post-bootstrap**: 806,5s por batch de 250. Bootstrap (pago 1x por sessao) nao esta includo aqui.
- **Speedup por batch**: 2.139,2 / 806,5 = **2,65x**.
- **itens por minuto**: 250 / (806,5 / 60) = **18,6** (vs 7,01 do D6A -- ganho de 2,65x).
- **custo por wine**: 806,5 / 250 = **3,23s** (vs 8,56s do D6A).

### Memoizacao observada (do checkpoint)

| cache | hits | misses | taxa |
|---|---|---|---|
| render_produtor | 52 | 183 | 22,1% |
| import_produtor | 54 | 181 | 23,0% |
| import_nome | 48 | 196 | 19,7% |

Em um slice de 250 wines, ~20-23% das queries dos canais de produtor se repetem e sao servidas do cache. Em um piloto maior de 10.000 wines, a taxa de hit tende a ser semelhante (as repeticoes saturam rapido porque a cauda tem producers bem espalhados).

### Round-trips reduzidos

| metrica | D6A | FAST |
|---|---|---|
| queries Render (fetch source info) em 250 wines | 1 batch = 1 query | 1 query (prefetch unico) |
| queries Render (fetch source info) em 10.000 wines | 40 | 1 |
| queries local por wine | 6 | 6 - (2 com cache hit ocasional) = ~5 |
| queries local por batch de 250 (sem cache) | 1.500 | 1.500 |
| queries local por batch de 250 (com cache aplicada) | 1.500 | ~1.346 |
| % de round-trips ao local economizados por cache | 0% | ~10,3% |
| round-trips ao Render reduzidos (10k wines) | 40 queries | 1 query (=39 a menos) |

Round-trip count sozinho **nao explica** o ganho. O ganho dominante vem de **paralelismo** (32 workers simultaneos contra o pool local), nao de batching SQL. O memo adiciona ~10% de reducao de queries mas o impacto real em wall-time e menor porque os canais cacheados (`render_produtor`, `import_*`) ja eram os mais baratos individualmente; os gastos dominantes continuam sendo `render_nome_produtor` e `render_nome`, que nao sao cacheaveis (chaves altamente unicas na cauda).

## Projecoes extrapoladas

Usando a taxa medida de 806,5s/batch (POOL-32, pos-bootstrap, sem cache quente cross-batch):

### Piloto 10.000

- Formula: `bootstrap + prefetch + 40 * 806,5s`
- `~248s + 2s + 32.260s = 32.510s = 9,03 horas`
- **FAST piloto 10.000 projetado: ~9,0 horas** (vs 23,6h baseline D6A)
- Ganho: **2,61x**

### Full fan-out 779.383

- Formula: `bootstrap + prefetch + 3.118 batches * 806,5s`
- `~248s + ~30s + 2.514.680s = ~2.514.960s = ~29 dias`
- **FAST full projetado: ~29 dias** (vs 77,2 dias baseline D6A)
- Ganho: **2,66x**

### Projecao por wine (conversao)

| slice | D6A (wine/min) | FAST (wine/min) | FAST tempo |
|---|---|---|---|
| 250 | 7,01 | 18,60 | 806,5s |
| 10.000 | 7,01 | 18,60 | ~9,0h |
| 779.383 | 7,01 | 18,60 | ~29 dias |

## Outros experimentos realizados

### LATERAL JOIN contra VALUES clause

Tentativa de batching SQL: reescrever `channel_render_nome_produtor` como um `WITH batch(wid, q) AS (VALUES ...) SELECT ... FROM batch LEFT JOIN LATERAL (...) c ON TRUE`.

- Canal testado: `render_nome_produtor` em 50 wines.
- Tempo loop sequencial: **72,3s** (1.446ms/wine).
- Tempo LATERAL batch: **96,7s** (1.934ms/wine).
- **Regressao de 1,34x**.

O planner Postgres **nao parametriza bem** o operador `%` (similarity) contra texto vindo de coluna externa no LATERAL. O loop single-row com literal text continua sendo competitivo. **LATERAL descartada como estrategia.**

### Escalonamento de pool

Medicoes de ganho em funcao de numero de workers (25 wines, post-bootstrap):

| workers | tempo | ms/wine | speedup vs sequencial 9s |
|---|---|---|---|
| sequencial (1) | 89,8s (baseline 10 wines) | 8.980 | 1,00x |
| POOL-4  | 41,6s | 1.665 | 5,40x |
| POOL-8  | 32,4s | 1.296 | 6,93x |
| POOL-12 | 39,1s | 1.566 | 5,75x |
| POOL-16 | 30,2s | 1.209 | 7,44x |
| POOL-24 | 31,8s | 1.272 | 7,07x |
| POOL-32 | 30,2s (escalado no slice 50) -> medido end-to-end 806,5s/250 | 1.066 / 3.230 | depende do slice |
| POOL-48 | 51,0s | 1.020 | 8,82x |

**Observacao**: o ganho observado nos microbenchmarks (pool 32 chegando a ~8x sobre slices de 50 wines) NAO se replicou no benchmark de producao do slice 250 (2,65x). A divergencia provavel e mix de variancia per-wine (wines da cauda tem queries de custo muito heterogeneo) + contencao de buffers Postgres quando 64 backends (32 locais + 32 vivino) concorrem sobre os mesmos indices GIN. O slice 250 contem wines que individualmente demoram dezenas de segundos por canal, e esses amortizam mal sob paralelismo.

## Meta de aceite de performance -- avaliacao

Criterios declarados na demanda:

> Se o novo runner ainda projetar algo como:
> - muitas horas para 10.000
> - ou muitos dias para 779.383
> entao marcar `NAO APTO`.

Avaliacao:
- 9,0 horas para 10.000: **fronteira**. Operacionalmente usavel para uma execucao overnight. Sair de 23,6h (2 noites) para 9h (1 noite) e uma melhoria material.
- 29 dias para 779.383: **claramente "muitos dias"**. Nao viavel para fan-out operacional.

O ganho material foi medido (2,66x por batch, 2,61x piloto 10k, 2,66x full) e a equivalencia funcional foi comprovada. Mas a regra minima explicita aciona:

> - se a nova projecao continuar em muitos dias para o full, marcar `NAO APTO`
> - se o ganho for marginal, marcar `NAO APTO`

2,66x nao e "ordem de grandeza". 29 dias e "muitos dias". As duas clausulas do criterio minimo sao disparadas.

## Veredito

**NAO APTO.**

Justificativa:
- Piloto 10.000 ficou operacionalmente usavel (9h = overnight feasibile). Isso e um ganho material no caminho de operacao do piloto.
- Full 779.383 continua projetado em ~29 dias. Melhoria de 2,66x NAO e suficiente para atingir o criterio de **ordem de grandeza** exigido pela demanda.
- A alavanca usada (parallelismo driver-side com conexao persistente + memo) extraiu o ganho razoavel possivel sem mudar logica. **A raiz do custo e o `similarity(texto_busca, $q) DESC LIMIT 100` do Postgres**, que e CPU-bound no GIN trgm walk e contem-se com oversubscription de backends a partir de 16 workers.

## Bloqueios reais que restam para liberar fan-out full

1. **CPU do Postgres local**: o trgm walk por query nao diminui por parallelismo driver-side a partir de ~16 backends. Para ganhar mais, precisa SHARD/particionar `vivino_match` ou colocar uma replica/worker mais proximo para absorver a carga.
2. **Nao-determinismo de LIMIT com empates**: aceito como inerente, mas em fan-out grande o drift per wine aumenta a variancia no per_wine. Nao afeta equivalencia mas e um fato a registrar.
3. **Latencia Brasil -> Oregon**: o bootstrap depende de stream de 1,7M rows do Render. Varia entre 67s e 248s por execucao, sem controle. Em execucao long-running com resumes, empilha.
4. **Nao ha memoizacao cross-session persistente**: cache em memoria e perdido quando o runner reinicia. Para full, seria preciso persistir o memo em disco.
5. **O gargalo nao e o numero de queries** -- e o CUSTO DE CADA QUERY. Qualquer otimizacao adicional precisa reduzir o tempo medio por query (e.g. cache materializado dos top100 de cada (produtor, nome) key pair), nao so o volume.

## Caminhos para desbloquear (fora do escopo desta demanda)

Nao implementado. Registrado apenas como direcao:

1. **Precomputar candidatos por chave normalizada e persistir**: construir uma tabela `cauda_candidate_cache(nome_norm, produtor_norm, channel) -> top100_ids` antes do fan-out. O fan-out consulta cache por key em vez de reexecutar trgm. Preserva semantica se o populador usar a mesma query.
2. **Rodar o runner em worker proximo ao Postgres** (mesmo data center): eliminar qualquer latencia de rede para o bootstrap Render.
3. **Sharding de `vivino_match`** por partitioning (e.g. por `pais`, `produtor` prefix): reduz o trgm walk a particoes menores.
4. **Aumentar `shared_buffers` / `effective_cache_size`** do Postgres local para absorver o working set de `vivino_match` (~500MB) -- atenua contencao de backends.
5. **Substituir trgm GIN por BM25/FTS dedicado** (e.g. ParadeDB pg_search) -- fora do escopo mas pode dar ordem de grandeza real.

Essas direcoes precisam de validacao em demanda separada. Nao sao parte deste benchmark.
