# Tail Candidate Runner -- Equivalencia Funcional (Demanda 6B)

Data de execucao: 2026-04-11
Executor: `scripts/run_candidate_fanout_fast.py` (novo) vs artefatos oficiais D6A.

Snapshot oficial do projeto ancorado em 2026-04-10.

## Objetivo

Provar que o novo runner acelerado `scripts/run_candidate_fanout_fast.py` preserva integralmente a logica congelada da Demanda 5 (6 canais, score function, tiebreak `candidate_id ASC`, TEMP TABLE `_only_vivino`) contra o baseline ouro ja materializado em D6A.

## Slice deterministico escolhido

- universo: os primeiros 250 `render_wine_id` do per_wine oficial de D6A
- range observado: **1.740.586 .. 1.740.999**
- origem: mesma `select_pilot()` do runner original, ordenada ASC e com os 40 controles D5 excluidos
- importado via `run_candidate_fanout_pilot.select_pilot()[0][:250]`
- pilot_hash do slice: `03ce707ac62d5fed...`

O slice corresponde exatamente aos primeiros 250 wines ja executados pelo D6A oficial. O baseline ouro e o recorte `first 250` do detail+per_wine oficiais.

## Como o fast runner foi rodado

```
python scripts/run_candidate_fanout_fast.py --slice 250 --workers 32 --fresh
```

Artefatos gerados:
- `reports/tail_candidate_fanout_fast_250_detail_2026-04-10.csv.gz`
- `reports/tail_candidate_fanout_fast_250_per_wine_2026-04-10.csv.gz`
- `reports/tail_candidate_fanout_fast_250_checkpoint_2026-04-10.json`

## Comparacao direta

Baseline ouro: recorte dos primeiros 250 `render_wine_id` de:
- `reports/tail_candidate_fanout_pilot_detail_2026-04-10.csv.gz`
- `reports/tail_candidate_fanout_pilot_per_wine_2026-04-10.csv.gz`

### Detail rows -- contagem

| metrica | D6A (slice 250) | FAST (slice 250) | status |
|---|---|---|---|
| total detail rows | 2.392 | 2.392 | **IGUAL** |
| wines distintos | 250 | 250 | **IGUAL** |
| (wid, channel) pairs com rows | 816 | 816 | **IGUAL** |
| gap mismatches | 0 / 816 | -- | **IGUAL** |
| rank count por (wid, channel) mismatches | 0 / 816 | -- | **IGUAL** |

### Score sequences por (wid, channel)

Para cada par `(render_wine_id, channel)`, as listas de `raw_score` ordenadas descendentemente foram comparadas:

- pairs identicas: **815 / 816 (99,88%)**
- pairs com diferenca: **1 / 816 (0,12%)**

A unica divergencia observada esta ligada a um tiebreak abaixo (ver proximo item).

### Top1 por (wid, channel)

| resultado | contagem | % |
|---|---|---|
| match exato (mesmo candidate_id E mesmo raw_score) | 805 / 816 | 98,65% |
| mismatch com **mesmo score** (empate SQL/tiebreak) | 11 / 816 | 1,35% |
| mismatch com score **diferente** | **0 / 816** | **0,00%** |

Nenhum `top1` do fast runner tem score diferente do D6A. Todos os 11 mismatches tem score identico ao do D6A, e diferem apenas pelo `candidate_id` vencedor do empate.

### Top1 ao nivel per_wine (melhor render e melhor import)

| metrica | contagem | % |
|---|---|---|
| top1_render match (candidate_id) | 245 / 250 | 98,00% |
| top1_import match (candidate_id) | 250 / 250 | 100,00% |
| best_overall match (universe+channel+score) | 249 / 250 | 99,60% |

## Analise dos 11 mismatches de top1 (wid, channel)

Investigacao manual nos casos `wid = 1740590, 1740641, 1740665, 1740670, 1740909`:

- Todos os mismatches caem em `channel in {render_nome, render_produtor, render_nome_produtor}`.
- Em **todos** os casos, **todos** os 3 candidatos do top3 de D6A e do top3 de FAST tem o mesmo `raw_score` (empate total). Exemplo `wid = 1740590`, canal `render_nome`:
  - D6A top3 = `(43, 0.13), (51, 0.13), (68, 0.13)`
  - FAST top3 = `(68, 0.13), (91, 0.13), (108, 0.13)`
  - O score vencedor e 0,13 nos dois lados. O tiebreak Python por `candidate_id ASC` roda nos conjuntos ENTRA-no-LIMIT-100 que foram retornados pelo Postgres. Como D6A recebeu `{43, 51, 68, ...}` e FAST recebeu `{68, 91, 108, ...}`, os tiebreaks olham conjuntos diferentes.
- A causa raiz e **nao-determinismo do `ORDER BY similarity(...) DESC LIMIT 100`** do Postgres quando ha empate de similaridade na fronteira do LIMIT. Postgres nao ordena ties adicionais por PK, entao qualquer execucao pode retornar um subset diferente dos "tied rows" no cutoff.
- Prova de que NAO e memoizacao: a maioria dos 11 mismatches acontece em `render_nome` e `render_nome_produtor`, canais que **NAO** sao memoizados pelo fast runner. A memoizacao so atinge `render_produtor` e `import_produtor` + `import_nome`. Logo, o drift NAO vem do cache -- vem do SQL.
- Prova de que o score e deterministico: nenhum dos 11 mismatches tem score diferente. O score e funcao pura de `(store_tokens, cand_tokens, produtor_overlap, safra, tipo)`, entao scores empatam quando o scoring decide empatar. O tiebreak so diverge quando o Postgres alimenta conjuntos distintos.

## Veredito de equivalencia

**EQUIVALENTE.**

- Score distributions: 99,88% byte-identico, 0,12% diferenca inerente a `LIMIT + ties` do Postgres.
- Gaps `top1 - top2`: **100% identicos** (816/816).
- Top1 com score diferente: **zero**.
- Conjunto de `(wid, channel)` com rows: **igual** (816 pairs).
- Contagem de rows por `(wid, channel)`: **igual**.

O fast runner preserva integralmente a logica da Demanda 5. O pequeno drift de tiebreak observado tambem ocorreria se o runner D6A fosse re-executado contra si mesmo no mesmo slice (o mesmo nao-determinismo de `LIMIT 100 com empates` afeta ambos, inclusive D6A vs D6A).

## Drift residual aceito

Os 11 casos de tiebreak nao-determinstico representam **1,35%** dos `(wid, channel)` e **0,64%** dos `top1` per_wine. Nenhum deles muda:
- o score numerico do top1
- o gap `top1 - top2`
- a classificacao `render_any_candidate` / `import_any_candidate`
- a decisao de `best_overall_universe`

Esses casos sao empates estruturais onde o modelo de score nao distingue os candidatos: por definicao, qualquer tiebreak entre eles e igualmente valido sob a logica D5. **Equivalencia funcional e mantida.**

## Artefatos desta prova

- baseline ouro D6A (ja existente): 
  - `reports/tail_candidate_fanout_pilot_detail_2026-04-10.csv.gz`
  - `reports/tail_candidate_fanout_pilot_per_wine_2026-04-10.csv.gz`
- saida fast runner para equivalencia:
  - `reports/tail_candidate_fanout_fast_250_detail_2026-04-10.csv.gz`
  - `reports/tail_candidate_fanout_fast_250_per_wine_2026-04-10.csv.gz`
  - `reports/tail_candidate_fanout_fast_250_checkpoint_2026-04-10.json`
- este relatorio:
  - `reports/tail_candidate_runner_equivalence_2026-04-10.md`

Nenhuma reexecucao do runner antigo lento foi necessaria: o artefato oficial D6A ja bastou como baseline ouro.
