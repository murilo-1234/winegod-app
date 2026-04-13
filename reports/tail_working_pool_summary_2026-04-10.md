# Tail Working Pool 1.200 -- Summary (Demanda 7, Tarefas A + B)

Data de execucao: 2026-04-11
Executores: `scripts/build_working_pool.py` + `scripts/run_fanout_on_pool.py`
Snapshot oficial do projeto ancorado em 2026-04-10.

## Contexto

A frente de performance do full fan-out foi **encerrada** apos D6A/D6B/D6C.
O projeto pivotou para **sample-first audit**: usar o runner rapido (D6B)
apenas em lotes pequenos e operacionalmente viaveis, para calibrar revisao
R1 e produzir um pilot humano-revisavel. Este summary descreve o working
pool de 1.200 wines que alimentara o `pilot_120`.

## Tarefa A -- Composicao do working pool (1.200 wines)

Artefato: `reports/tail_working_pool_1200_2026-04-10.csv`

Construcao deterministica via `scripts/build_working_pool.py`.

### Seed e hash de ordenacao

- Seed determinstica: `winegod-demanda-7-working-pool-2026-04-10`
- Chave de ordenacao pseudo-aleatoria estavel:
  `sha1(f"{seed}:{render_wine_id}").hexdigest()`
- Universo base = tail_base_extract menos os 40 controles da Demanda 5
  (`tail_candidate_controls_positive_2026-04-10.csv` +
  `tail_candidate_controls_negative_2026-04-10.csv`)

### Blocos exclusivos

| bloco | target | obtido | criterio |
|---|---|---|---|
| block1_main_random | 800 | **800** | sorteio random deterministico (hash_key) sobre o universo (779.343) |
| block2_no_source | 200 | **200** | `no_source_flag = 1`, ordem hash_key, excluindo block1 |
| block3_suspect_not_wine | 200 | **200** | `wine_filter.classify_product(nome) != 'wine'` OR `y2_any_not_wine_or_spirit = 1`, ordem hash_key, excluindo block1 + block2 |
| **TOTAL** | **1.200** | **1.200** | |

### Validacoes obrigatorias (Tarefa A)

| check | resultado |
|---|---|
| total = 1.200 | **OK** |
| blocks 800 + 200 + 200 = 1.200 | **OK** |
| zero overlap entre blocos | **OK** (`len(set) == len(list)`) |
| 40 controles D5 excluidos | **OK** (`pool & controls == empty`) |
| seed determinstica registrada | **OK** (seed + `hash_key` no CSV) |
| candidatos no_source disponiveis | 8.068 wines (fora do block1) -> 200 take |
| candidatos suspect_not_wine disponiveis | 17.102 wines (fora dos blocks 1+2) -> 200 take |

## Tarefa B -- Fan-out rapido D6B no working pool

Artefatos:
- `reports/tail_working_pool_fanout_detail_2026-04-10.csv.gz`
- `reports/tail_working_pool_fanout_per_wine_2026-04-10.csv.gz`

Executor: `scripts/run_fanout_on_pool.py` (wrapper READ-ONLY do fast runner
D6B que aceita lista explicita de `render_wine_id`). Zero drift de logica:
reusa `bcc.CHANNELS_RENDER` / `CHANNELS_IMPORT`, `score_candidate`,
`rank_top3`, `prefetch_source_info`, `worker_loop` verbatim.

### Runtime observado

| fase | tempo |
|---|---|
| bootstrap (stream 1,7M vivino_ids Render + 1,7M vivino_db) | **64,4s** |
| prefetch source info (1 query Render para 1.200 wines) | **2,1s** |
| batch 1 (wines 1-250) | 755,8s |
| batch 2 (wines 251-500) | 693,5s |
| batch 3 (wines 501-750) | 710,2s |
| batch 4 (wines 751-1000) | 796,1s |
| batch 5 (wines 1001-1200, 200 itens) | 442,2s |
| session run total | **3.397,8s** |
| **wall total** | **3.464,2s = ~57,7 min** |

- POOL-32 workers (`run_candidate_fanout_fast.worker_loop`)
- Mediana por batch de 250 wines: ~725s (bateu com D6B: ~806s)
- Throughput: 1.200 / (3464 / 60) = **20,8 wines/minuto**

### Cobertura de candidatos

Total detail rows: **12.160** (em 1.200 wines x 6 canais).
Total per_wine rows: **1.200** (cobertura 100%).

| metrica | wines | % |
|---|---|---|
| `render_any_candidate == 1` (pelo menos 1 cand Render) | 1.200 | **100,00%** |
| `import_any_candidate == 1` (pelo menos 1 cand Import) | 492 | **41,00%** |
| 0 candidatos em ambos | 0 | 0,00% |

### Distribuicao de `best_overall_universe`

| universe | wines | % |
|---|---|---|
| render | **1.199** | 99,92% |
| import | **1** | 0,08% |

**Observacao critica**: apenas **1 wine em 1.200** tem `best_overall = import`. O universo `only_vivino_db` tem so 11.527 wines (vs 1,7M no Render), entao para um wine da cauda superar o melhor render no score, teria que ter evidencia muito especifica. Em pratica, quase nunca acontece.

### Distribuicao de scores e gaps

| metrica | n | p10 | mediana | p90 |
|---|---|---|---|---|
| `top1_render_score` | 1.200 | 0,1444 | **0,4062** | 0,65 |
| `top1_import_score` | 492 | 0,00 | **0,2167** | 0,4167 |
| `top1_render_gap` | 1.200 | 0,00 | **0,00** | 0,13 |
| `top1_import_gap` | 492 | 0,00 | **0,00** | 0,1625 |

Gap mediano zero em ambos universos indica que **empates no top1** sao o caso dominante (score igual entre top1 e top2). Isso e consistente com o padrao ja observado em D5/D6A/D6B: muitos wines da cauda tem varios candidatos empatando no trgm walk.

### Distribuicao por canal (detail rows)

| canal | rows | % |
|---|---|---|
| render_nome_produtor | 3.600 | 29,6% |
| render_nome | 3.600 | 29,6% |
| render_produtor | 3.408 | 28,0% |
| import_nome | 782 | 6,4% |
| import_produtor | 736 | 6,1% |
| import_nome_produtor | 34 | 0,3% |

Os canais Render entregam >3.000 rows cada (top3 x 1.200 = 3.600 max; 3.408 no render_produtor significa que 192 wines nao tem prod de len>=3). Os canais Import sao muito mais ralos porque o `_only_vivino` tem apenas 11.527 rows, e `import_nome_produtor` exige anchors simultaneos em nome e produtor -- dai os 34 rows (11 wines).

## Disciplina metodologica preservada

- **Nenhum drift** vs D5/D6B: usa `bcc.channel_*` verbatim, mesmo
  `similarity_threshold = 0.10`, mesmo TEMP TABLE `_only_vivino`, mesmo
  `rank_top3` com tiebreak `candidate_id ASC`.
- **Zero escrita em producao**: read-only contra Render e vivino_db.
- **Determinismo**: pool_ids vem de um CSV explicito; seleccao e ordem sao
  reproduzidas por hash_key sha1 + seed fixa.
- **Nao e fan-out full**: 1.200 wines (~0,15% da cauda), selecionados para
  calibracao R1/R2, nao para estimativa populacional.

## Artefatos desta tarefa

- `reports/tail_working_pool_1200_2026-04-10.csv` (1.200 wines, 17 cols)
- `reports/tail_working_pool_fanout_detail_2026-04-10.csv.gz` (12.160 rows)
- `reports/tail_working_pool_fanout_per_wine_2026-04-10.csv.gz` (1.200 rows)
- `reports/tail_working_pool_with_buckets_2026-04-10.csv` (1.200 wines +
  `pilot_bucket_proxy` + `reason_short_proxy`; gerado pela Tarefa C)
- `scripts/build_working_pool.py`
- `scripts/run_fanout_on_pool.py`

## Proximos passos

O working pool esta pronto para consumo pelo `assign_pilot_buckets.py`
(Tarefa C) e pela selecao deterministica do `pilot_120` (Tarefa D).
Ver `tail_pilot_120_summary_2026-04-10.md`.
