# Tail Pilot 120 -- R1 Claude Summary (Demanda 8)

Data de execucao: 2026-04-11
Executor: `scripts/classify_pilot_r1.py`
Snapshot oficial do projeto ancorado em 2026-04-10.

## Contexto

- Projeto em modo **sample-first audit** apos D6A/D6B/D6C.
- D7 materializou o `pilot_120` (120 wines estratificados por `pilot_bucket_proxy`, deterministicos, reproduziveis).
- Esta e a R1 **do Claude** sobre os 120 wines. O pilot inteiro vai para revisao humana de Murilo (`needs_murilo_review = 1` em todos).
- **Importante**: `pilot_bucket_proxy` continua sendo rotulo operacional, NAO business_class final. `UNRESOLVED` continua sendo um `review_state`, nao um `business_class`. Esta R1 nao e estimativa populacional -- e calibragem Claude vs Murilo no pilot.

## Taxonomia aplicada

- **business_class**: `MATCH_RENDER` / `MATCH_IMPORT` / `STANDALONE_WINE` / `NOT_WINE`
- **review_state**: `RESOLVED` / `SECOND_REVIEW` / `UNRESOLVED`
- **confidence**: `HIGH` / `MEDIUM` / `LOW`
- **action**: `ALIAS` / `IMPORT_THEN_ALIAS` / `KEEP_STANDALONE` / `SUPPRESS`
- **data_quality**: `GOOD` / `FAIR` / `POOR`
- **product_impact**: `HIGH` / `MEDIUM` / `LOW`

## Arvore de decisao aplicada

Aplicada em ordem, primeiro que bate pronto:

1. `wine_filter.classify_product(nome) == 'not_wine'` com categoria nao-vazia
   -> `NOT_WINE` / `RESOLVED` / `HIGH` / `SUPPRESS`

2. `nome` vazio ou len<3
   -> `STANDALONE_WINE` (best guess) / `UNRESOLVED` / `LOW` / `KEEP_STANDALONE`

3. `y2_any_not_wine_or_spirit=1` (via `reason_short_proxy`) sem bloqueio de wine_filter
   -> `NOT_WINE` (hipotese) / `SECOND_REVIEW` / `MEDIUM` / `SUPPRESS`
   (y2 e baseline nao verdade; precisa confirmacao humana)

4. **Render STRONG**: `r_score >= 0.50` AND `r_gap >= 0.10`
   -> `MATCH_RENDER` / `RESOLVED` / `HIGH` / `ALIAS`

5a. `r_score >= 0.45` (score alto com gap possivelmente baixo)
    -> `MATCH_RENDER` / `SECOND_REVIEW` / `MEDIUM` / `ALIAS`

5b. `r_score >= 0.35` AND `r_gap >= 0.05` (alinha com P4 bucket)
    -> `MATCH_RENDER` / `SECOND_REVIEW` / `MEDIUM` / `ALIAS`

6. **Import STRONG**: `i_score >= 0.40` AND `i_gap >= 0.10`
   -> `MATCH_IMPORT` / `SECOND_REVIEW` / `MEDIUM` / `IMPORT_THEN_ALIAS`

7. **Render weak**: `r_score >= 0.30` sem gap/score alto
   -> `STANDALONE_WINE` / `SECOND_REVIEW` / `LOW` / `KEEP_STANDALONE`

8. **Sem candidato defensavel**
   -> `STANDALONE_WINE` / `UNRESOLVED` / `LOW` / `KEEP_STANDALONE`

`data_quality` e `product_impact` sao funcoes de `(len(nome), len(produtor), safra/tipo, wine_sources_count_live, no_source_flag)` -- regras documentadas no script `classify_pilot_r1.py`.

## Distribuicao por `business_class`

| class | wines | % |
|---|---|---|
| **MATCH_RENDER** | 53 | 44,2% |
| **STANDALONE_WINE** | 46 | 38,3% |
| **NOT_WINE** | 20 | 16,7% |
| **MATCH_IMPORT** | 1 | 0,8% |
| **TOTAL** | **120** | 100% |

## Distribuicao por `review_state`

| state | wines | % |
|---|---|---|
| **SECOND_REVIEW** | 64 | 53,3% |
| **RESOLVED** | 33 | 27,5% |
| **UNRESOLVED** | 23 | 19,2% |

## Distribuicao por `confidence`

| conf | wines | % |
|---|---|---|
| LOW | 46 | 38,3% |
| MEDIUM | 41 | 34,2% |
| HIGH | 33 | 27,5% |

## Distribuicao por `action`

| action | wines | % |
|---|---|---|
| ALIAS | 53 | 44,2% |
| KEEP_STANDALONE | 46 | 38,3% |
| SUPPRESS | 20 | 16,7% |
| IMPORT_THEN_ALIAS | 1 | 0,8% |

## Distribuicao por `data_quality`

| dq | wines | % |
|---|---|---|
| GOOD | 71 | 59,2% |
| FAIR | 28 | 23,3% |
| POOR | 21 | 17,5% |

## Distribuicao por `product_impact`

| impact | wines | % |
|---|---|---|
| LOW | 106 | 88,3% |
| MEDIUM | 12 | 10,0% |
| HIGH | 2 | 1,7% |

Observacao: 88,3% dos wines do pilot tem `product_impact=LOW` porque sao wines da cauda (poucas fontes ativas). E esperado e coerente com a definicao da cauda.

## review_state x business_class (sanity)

| review_state | business_class | wines |
|---|---|---|
| RESOLVED | MATCH_RENDER | 16 |
| RESOLVED | NOT_WINE | 17 |
| RESOLVED | **total** | **33** |
| SECOND_REVIEW | MATCH_RENDER | 37 |
| SECOND_REVIEW | STANDALONE_WINE | 23 |
| SECOND_REVIEW | NOT_WINE | 3 |
| SECOND_REVIEW | MATCH_IMPORT | 1 |
| SECOND_REVIEW | **total** | **64** |
| UNRESOLVED | STANDALONE_WINE | 23 |
| UNRESOLVED | **total** | **23** |

Leitura: `UNRESOLVED` e um estado terminal sem match; Claude propoe `STANDALONE_WINE` como best-guess mas reconhece que nao da para decidir. `SECOND_REVIEW` domina (53%): o pilot foi montado justamente para capturar zona cinzenta.

## bucket_proxy x business_class (calibragem)

| bucket | business_class | wines |
|---|---|---|
| P1_SUSPECT_NOT_WINE_PROXY | NOT_WINE | **20** / 20 (100%) |
| P2_NO_SOURCE_PROXY | MATCH_RENDER | 12 |
| P2_NO_SOURCE_PROXY | STANDALONE_WINE | 8 |
| P3_POOR_DATA_OR_NO_CANDIDATE_PROXY | MATCH_RENDER | 10 |
| P3_POOR_DATA_OR_NO_CANDIDATE_PROXY | STANDALONE_WINE | 10 |
| P4_STRONG_RENDER_PROXY | MATCH_RENDER | **20** / 20 (100%) |
| P5_STRONG_IMPORT_PROXY | MATCH_IMPORT | **1** / 1 (100%) |
| P6_AMBIGUOUS_PROXY | STANDALONE_WINE | 28 |
| P6_AMBIGUOUS_PROXY | MATCH_RENDER | 11 |

Leitura:
- **P1 e P4 convergem 100%** com a expectativa do bucket -- o proxy ajudou a estratificar bem as pontas.
- **P2** divide entre MATCH (12) e STANDALONE (8). Wines sem fonte ativa que ainda batem canonico forte sao o caso para ALIAS de deduplicacao; wines sem fonte ativa E sem match sao candidatos a SUPPRESS/KEEP_STANDALONE operacional.
- **P3** divide 10/10 igualmente. Wines com metadata pobre que ainda conseguem um match decente (top1 render) podem virar MATCH_RENDER; os outros viram STANDALONE_WINE UNRESOLVED/LOW.
- **P6** e onde o humano mais precisa entrar: 28 STANDALONE SECOND_REVIEW (ambiguidade real) e 11 MATCH_RENDER SECOND_REVIEW (tiebreak). Esse bucket existe para alimentar calibragem de thresholds.

## Principais motivos de envio a Murilo

Todos os 120 wines vao para Murilo (`needs_murilo_review = 1`, conforme demanda). A coluna `murilo_review_reason` resume o motivo individual:

| motivo | wines | % |
|---|---|---|
| match render ambiguo (tiebreak) | 37 | 30,8% |
| match fraco -- validar standalone vs match | 23 | 19,2% |
| incerteza real -- Claude nao decidiu | 23 | 19,2% |
| validar calibragem R1 Claude em not_wine bloqueado | 17 | 14,2% |
| validar calibragem R1 Claude em match HIGH | 16 | 13,3% |
| y2 flagou not_wine mas wine_filter nao -- confirmar | 3 | 2,5% |
| import candidato -- validar antes de IMPORT_THEN_ALIAS | 1 | 0,8% |

## Principais fontes de incerteza observadas

1. **Empates SQL na fronteira do LIMIT 100** (~37 wines). Os canais render retornam multiplos candidatos com o mesmo score; o tiebreak `candidate_id ASC` escolhe um, mas em wines onde a fronteira e densa, o top1 pode nao ser o melhor canonico. Alinhado ao drift residual ja documentado em D6B/D6C -- nao e bug do classificador.

2. **Produtor vazio ou muito curto** (~10-20 wines do P3). Fan-out ainda acha algum render candidate decente, mas sem produtor nao da para validar com forca. Precisa de olho humano.

3. **Sem candidato acima de 0.30** (~23 wines UNRESOLVED). Wines com nome muito generico ou metadata quebrada que nao geraram sinal suficiente em nenhum canal.

4. **y2 baseline vs filtro lexical** (~3 wines). y2 flagou como not_wine mas `wine_filter` nao bloqueou. Esse conflito merece decisao humana -- y2 e baseline, nao verdade.

5. **Import rare**: universo import tao pequeno (11.527 wines) que so 1 wine em 120 caiu em `MATCH_IMPORT`. Finding estrutural, nao bug.

## Leitura curta sobre o pilot (nao e estimativa populacional)

> Aviso: o pilot e calibragem. As proporcoes abaixo valem para o pilot e **nao** devem ser extrapoladas para a cauda inteira. Representativa 600 e impacto 120 continuam fora de escopo nesta demanda.

**Quantos parecem backlog real de alias/import?**
- `MATCH_RENDER` confident (RESOLVED HIGH): **16** -> alias claro.
- `MATCH_RENDER` a confirmar (SECOND_REVIEW): **37** -> alias provavel apos Murilo.
- `MATCH_IMPORT` (SECOND_REVIEW): **1** -> IMPORT_THEN_ALIAS.
- **Total backlog potencial**: 16 + 37 + 1 = **54 wines** (45% do pilot).

**Quantos parecem standalone?**
- `STANDALONE_WINE` SECOND_REVIEW (match fraco): 23
- `STANDALONE_WINE` UNRESOLVED (sem candidato): 23
- **Total standalone potencial**: **46 wines** (38% do pilot).

**Quantos parecem not_wine?**
- `NOT_WINE` RESOLVED (wine_filter caught): **17**
- `NOT_WINE` SECOND_REVIEW (y2 baseline): **3**
- **Total not_wine potencial**: **20 wines** (17% do pilot).

**Quanta ambiguidade o pilot revelou?**
- `review_state = SECOND_REVIEW`: **64 wines (53%)** -- a maioria do pilot precisa decisao humana.
- `review_state = UNRESOLVED`: **23 wines (19%)** -- Claude explicitamente nao decidiu.
- Soma de ambiguidade: **72%** do pilot nao tem decisao final automatizada.

Isso valida a escolha metodologica de **sample-first audit**: nao faz sentido rodar full fan-out quando a maioria do sinal precisa de R1/R2 humana de qualquer jeito.

## Escopo reafirmado

Esta demanda **NAO** produz:
- business_class final da cauda
- estimativa populacional
- representativa 600
- impacto 120
- decisoes automatizadas de ALIAS/IMPORT em producao

Esta demanda **produz**:
- R1 Claude completa dos 120 wines
- dossie de trabalho com top3 render/import legivel
- pacote de revisao para Murilo com colunas `murilo_*` vazias para preencher
- este summary

## Artefatos desta etapa

| artefato | rows | descricao |
|---|---|---|
| `reports/tail_pilot_120_dossier_short_2026-04-10.csv` | 120 | pilot + top3 render/import por wine |
| **`reports/tail_pilot_120_r1_claude_2026-04-10.csv`** | **120** | classificacao R1 Claude completa |
| **`reports/tail_pilot_120_for_murilo_2026-04-10.csv`** | **120** | pacote de revisao (R1 + campos `murilo_*`) |
| `reports/tail_pilot_120_r1_summary_2026-04-10.md` | -- | este arquivo |
| `scripts/classify_pilot_r1.py` | -- | classifier + export dos 3 CSVs |

## Proximos passos

1. Murilo revisa os 120 wines no `for_murilo` CSV (todas as colunas `murilo_*` vazias para preencher).
2. Apos revisao, calcular **concordancia Claude vs Murilo** por campo:
   - business_class
   - review_state
   - confidence
   - action
3. Usar a leitura de concordancia para calibrar thresholds (score, gap, etc.) antes de decidir o desenho da representativa 600.
4. Nao abrir representativa 600 sem o gate de concordancia satisfeito.
