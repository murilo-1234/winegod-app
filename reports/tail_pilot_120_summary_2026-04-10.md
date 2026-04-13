# Tail Pilot 120 -- Summary (Demanda 7, Tarefas C + D + E)

Data de execucao: 2026-04-11
Executor: `scripts/assign_pilot_buckets.py` + `scripts/export_pilot_review_pack.py`
Snapshot oficial do projeto ancorado em 2026-04-10.

## Mudanca de regime

Apos D6A/D6B/D6C declararem **NAO APTO** para fan-out full, o projeto
pivotou para **sample-first audit**:

> O runner rapido D6B e usado apenas em lotes pequenos e operacionalmente
> viaveis. Em vez de tentar estimativa populacional, montamos um pilot de
> 120 wines diverso e deterministico, para calibracao R1 humana.

**Importante**: `pilot_bucket_proxy` **NAO** e business_class final. E um
rotulo operacional usado apenas para estratificar a selecao do pilot.
`UNRESOLVED` continua NAO sendo business_class.

## Input do pilot

Input: `reports/tail_working_pool_with_buckets_2026-04-10.csv` (1.200 wines
do working pool com `pilot_bucket_proxy` e `reason_short_proxy` atribuidos).

Ver `tail_working_pool_summary_2026-04-10.md` para a composicao do working pool.

## Tarefa C -- Regras dos proxy buckets

Atribuicao exclusiva em ordem de prioridade descendente (primeiro que bate, pronto).
Os thresholds sao DOCUMENTADOS abaixo; eles nao sao business_class final -- sao
apenas criterios operacionais para estratificacao.

### Thresholds usados

- `STRONG_SCORE = 0.35` (score minimo para "forte")
- `STRONG_GAP = 0.05` (gap minimo top1-top2 para "sem ambiguidade obvia")
- `POOR_SCORE = 0.20` (abaixo disto e "poor data or weak candidate")
- `MIN_PROD_LEN = 3` (produtor com menos de 3 chars = poor data)
- `MIN_NOME_LEN = 5` (nome com menos de 5 chars = poor data)

### P1 -- `P1_SUSPECT_NOT_WINE_PROXY`

Regra: `wine_filter.classify_product(nome) != 'wine'` OR `y2_any_not_wine_or_spirit == '1'`

Cobre wines que o filtro de palavras-chave bloqueia (whisky, queijo, gift card, etc.) ou que o snapshot de y2 marcou como "not_wine_or_spirit" em pelo menos uma run.

### P2 -- `P2_NO_SOURCE_PROXY`

Regra: `no_source_flag == '1'`

Wines sem fonte ativa na base (stores_count_live = 0). Estes sao candidatos a `UNRESOLVED` operacional mas sem business_class definida nesta demanda.

### P3 -- `P3_POOR_DATA_OR_NO_CANDIDATE_PROXY`

Regra:
- `len(produtor.strip()) < 3`
- OR `len(nome.strip()) < 5`
- OR `render_any_candidate == 0 AND import_any_candidate == 0`
- OR `best_overall_score < 0.20` (ou vazio)

Wines cuja metadata e tao fraca que nem o fan-out consegue produzir um candidato minimamente defensavel.

### P4 -- `P4_STRONG_RENDER_PROXY`

Regra:
- `best_overall_universe == 'render'`
- AND `best_overall_score >= 0.35`
- AND `top1_render_gap >= 0.05`

Match forte e sem empate na fronteira: candidato top1 claramente a frente do top2 no universo Render.

### P5 -- `P5_STRONG_IMPORT_PROXY`

Regra:
- `best_overall_universe == 'import'`
- AND `best_overall_score >= 0.35`
- AND `top1_import_gap >= 0.05`

Match forte exclusivamente no universo Import (`_only_vivino_db`, 11.527 wines). Este bucket e estruturalmente raro (ver observacao abaixo).

### P6 -- `P6_AMBIGUOUS_PROXY`

Sobra:
- `best_overall_score >= 0.20` mas
- gap pequeno (`< 0.05`)
- OR empate forte entre render e import
- OR `render_score ~= import_score`

Zona cinzenta. Alvo principal da revisao R1: sao os wines mais informativos para calibrar R1/R2.

## Distribuicao no working pool 1.200

| bucket | wines | % |
|---|---|---|
| P1_SUSPECT_NOT_WINE_PROXY | **222** | 18,50% |
| P2_NO_SOURCE_PROXY | **198** | 16,50% |
| P3_POOR_DATA_OR_NO_CANDIDATE_PROXY | **225** | 18,75% |
| P4_STRONG_RENDER_PROXY | **153** | 12,75% |
| P5_STRONG_IMPORT_PROXY | **1** | 0,08% |
| P6_AMBIGUOUS_PROXY | **401** | 33,42% |
| **TOTAL** | **1.200** | 100,00% |

### Observacao critica sobre P5

Apenas **1 wine em 1.200** (0,08%) qualifica como `P5_STRONG_IMPORT_PROXY`. Isto e **estrutural**, nao um bug:

1. O universo Import e a TEMP TABLE `_only_vivino`, que contem apenas **11.527 rows** -- os ids que existem em `vivino_vinhos` mas NAO tem par `vivino_id` no Render.
2. Para um wine da cauda ter `best_overall = import`, seu top1 import precisa bater tanto o top1 render em score absoluto. Com Render tendo 1,7M canonicos disponiveis, o render quase sempre ganha.
3. O runner D6B inteiro so observou 1 wine no working pool cujo top1 import e mais forte que o top1 render, com `gap >= 0.05`.

Esse numero e consistente com a premissa metodologica da cauda: wines da cauda sao **rastros residuais** dentro do universo Render-principal. O canal import existe para **tentar recuperar** wines com vivino_id-only-in-vivino, nao para ser o dominante.

## Tarefa D -- Pilot 120 (selecao deterministica)

- Ordenacao dentro de cada bucket: **por hash_key sha1** (ja computado no working pool, com seed `winegod-demanda-7-working-pool-2026-04-10`)
- Alvo inicial: 20 por bucket
- Overflow rule: quando um bucket tem <20, o deficit e preenchido em ordem deterministica de prioridade de doacao:
  `P6 -> P3 -> P4 -> P5 -> P1 -> P2`.
- Total final: exatamente **120** wines.

### Resultado

| bucket | alvo | obtido | deficit | preenchimento |
|---|---|---|---|---|
| P1_SUSPECT_NOT_WINE_PROXY | 20 | **20** | 0 | -- |
| P2_NO_SOURCE_PROXY | 20 | **20** | 0 | -- |
| P3_POOR_DATA_OR_NO_CANDIDATE_PROXY | 20 | **20** | 0 | -- |
| P4_STRONG_RENDER_PROXY | 20 | **20** | 0 | -- |
| P5_STRONG_IMPORT_PROXY | 20 | **1** | **19** | overflow P6 (19 wines) |
| P6_AMBIGUOUS_PROXY | 20 | **39** | 0 | 20 nativos + 19 overflow donors p/ P5 |
| **TOTAL** | 120 | **120** | -- | -- |

### Deficit documentado: P5_STRONG_IMPORT_PROXY

- **19 vagas do P5 foram preenchidas por overflow do P6_AMBIGUOUS_PROXY**.
- Razao: so 1 wine do pool 1.200 cumpriu os thresholds de P5.
- Decisao: P6 foi escolhido como primeiro doador porque e o bucket mais abundante (401) e o mais relevante para calibracao R1 (zona cinzenta e o que mais precisa de revisao humana).
- Os 19 wines doados do P6 mantem seu rotulo `pilot_bucket_proxy = P6_AMBIGUOUS_PROXY` e sao marcados com `overflow_from = P6_AMBIGUOUS_PROXY` na coluna de trilha.

### Origem dos 120 wines por bloco do working pool

| bloco | count | % do pilot |
|---|---|---|
| block1_main_random (800) | 100 | 83,33% |
| block2_no_source (200) | 17 | 14,17% |
| block3_suspect_not_wine (200) | 3 | 2,50% |
| **TOTAL** | **120** | 100% |

Observacao: block2 e block3 sao supplementais pequenos; a maior parte do pilot vem do block1 (random).

## Tarefa E -- Review pack

Artefato: `reports/tail_pilot_120_2026-04-10.csv`

Schema (28 colunas):
```
render_wine_id, nome, produtor, safra, tipo,
preco_min, wine_sources_count_live, stores_count_live, no_source_flag,
y2_present, y2_status_set,
pilot_bucket_proxy,
top1_render_candidate_id, top1_render_channel, top1_render_score, top1_render_gap,
top1_import_candidate_id, top1_import_channel, top1_import_score, top1_import_gap,
best_overall_universe, best_overall_channel, best_overall_score,
reason_short_proxy,
top1_render_human, top1_import_human,
block, hash_key, overflow_from
```

- `top1_render_human` / `top1_import_human`: resumo legivel do candidato
  top1 daquele universo, no formato `"produtor | nome  [canal]  (safra=..., tipo=..., score=...)"`
- `reason_short_proxy`: explicacao curta de por que o wine caiu no bucket
  (ex.: `wine_filter=chocolate`, `no_source_flag=1`, `render score=0.520 gap=0.13`)
- `overflow_from`: vazio para entradas nativas; = bucket doador para entradas via overflow

## Reservas 60

Artefato: `reports/tail_pilot_120_reservas_2026-04-10.csv`

- Alvo: 60 reservas (10 por bucket quando possivel)
- Algoritmo: ordem determinstica por hash_key, ignorando wines ja selecionados no pilot
- Overflow para reservas: mesma regra do pilot (P6 -> P3 -> P4 -> P5 -> P1 -> P2)

### Resultado

| bucket | alvo | obtido | deficit |
|---|---|---|---|
| P1_SUSPECT_NOT_WINE_PROXY | 10 | 10 | 0 |
| P2_NO_SOURCE_PROXY | 10 | 10 | 0 |
| P3_POOR_DATA_OR_NO_CANDIDATE_PROXY | 10 | 10 | 0 |
| P4_STRONG_RENDER_PROXY | 10 | 10 | 0 |
| P5_STRONG_IMPORT_PROXY | 10 | **0** | **10** (preenchido via overflow) |
| P6_AMBIGUOUS_PROXY | 10 | 10 | 0 |
| overflow (P6 donors) | -- | 10 | -- |
| **TOTAL** | **60** | **60** | -- |

Nenhum wine do pilot aparece nas reservas. Reservas sao exclusivamente para substituicao futura caso wines do pilot sejam invalidados durante a revisao R1.

## Validacoes obrigatorias (Tarefa D)

| check | resultado |
|---|---|
| total pilot = 120 | **OK** |
| bucket distribution documentada | **OK** |
| overflow rule documentada | **OK** (P5 -> P6) |
| deficit documentado | **OK** (P5 = 19) |
| reservas = 60 | **OK** |
| selecao deterministica (hash_key estavel) | **OK** |
| reproduzivel via scripts | **OK** (`assign_pilot_buckets.py`) |
| zero overlap pilot <-> reservas | **OK** |

## Mensagem explicita para R1

**O `pilot_bucket_proxy` e um rotulo operacional** usado para estratificar a
selecao dos 120 wines da calibracao. Ele **nao** e `business_class`. Ele
**nao** e decisao de auditoria. Ele **nao** e gate de promocao.

A revisao R1 deve tratar cada wine como um caso individual. O bucket apenas
garante que a revisao vera diversidade suficiente (wines com score forte,
wines com dados fracos, wines ambiguos, wines suspeitos de not_wine, wines
sem fonte) para calibrar os thresholds reais que serao propostos na R2.

O `reason_short_proxy` existe para dar um ponto de partida para a revisao,
nao para substitui-la.

## Artefatos gerados

| artefato | rows | descricao |
|---|---|---|
| `reports/tail_working_pool_with_buckets_2026-04-10.csv` | 1.200 | pool inteiro + bucket + reason |
| **`reports/tail_pilot_120_2026-04-10.csv`** | **120** | review pack final para R1 |
| **`reports/tail_pilot_120_reservas_2026-04-10.csv`** | **60** | reservas para substituicao |
| `scripts/assign_pilot_buckets.py` | -- | atribui bucket + seleciona pilot + reservas |
| `scripts/export_pilot_review_pack.py` | -- | enriquece pilot com top1_human |

## Estado da auditoria

- **Modo atual**: `sample-first audit`
- **Pilot pronto para R1**: sim
- **business_class final**: nao atribuida (fora do escopo desta demanda)
- **Representativa 600 / impacto 120**: nao abertos (fora do escopo)
- **Full fan-out**: bloqueado e nao programado
