# Tail Candidate -- Cache Equivalence (Demanda 6C, Tarefa D)

Data de execucao: 2026-04-11
Executor: `scripts/build_candidate_cache.py` + `scripts/run_candidate_fanout_cached.py`
Snapshot oficial do projeto ancorado em 2026-04-10.

## Objetivo

Provar que o caminho com cache persistente (`build_candidate_cache.py` +
`run_candidate_fanout_cached.py`) produz saida funcionalmente equivalente ao
baseline oficial D6A, preservando integralmente a logica da Demanda 5.

## Slice deterministico de prova

- primeiros 250 `render_wine_id` do piloto D6A (`1.740.586 .. 1.740.999`)
- mesmo slice usado na equivalencia D6B
- slice hash: identico ao D6A baseline (ordem deterministica de `select_pilot()`)

## Como o cache foi construido

Comando:
```
python scripts/build_candidate_cache.py --slice 250 --workers 16
```

- 250 source infos pre-fetched do Render em 1 query (~1,8s)
- bootstrap `only_vivino_db` set carregado 1x
- enumeradas chaves distintas por canal no slice:
  - render_nome_produtor: **250**
  - render_nome: **249**
  - render_produtor: **160**
  - import_nome_produtor: **196**
  - import_nome: **185**
  - import_produtor: **160**
  - TOTAL: **1.200 queries SQL executadas uma unica vez**
- pool 16 workers: render (local) e import (vivino_db) em pools concorrentes
- saida: `reports/candidate_cache_slice250.sqlite3`

## Como o cache foi consumido

Comando:
```
python scripts/run_candidate_fanout_cached.py \
    --slice 250 \
    --cache reports/candidate_cache_slice250.sqlite3 \
    --on-miss fail
```

- source info pre-fetched (1 query) -- mesma do runner fast
- consumo 100% offline: **zero conexao a Postgres** na fase consume
- flag `--on-miss=fail` garante que nenhum wine caia em fallback live (qualquer miss seria erro duro)

### Stats do consume

```
[consume] 2,392 detail rows em 1.144s  (4.58ms/wine)

Cache hits/misses:
  render_nome_produtor  hit=250  miss=0  null_key=0
  render_nome           hit=250  miss=0  null_key=0
  render_produtor       hit=235  miss=0  null_key=15
  import_nome_produtor  hit=235  miss=0  null_key=15
  import_nome           hit=244  miss=0  null_key=6
  import_produtor       hit=235  miss=0  null_key=15
  TOTAL                 hit=1449 miss=0  null_key=51
```

- **0 misses**: o cache cobre 100% dos lookups que deveriam existir
- 51 `null_key`: sao wines onde a D5 **nao dispararia query** neste canal (ex.: `len(nome)<3`, sem `longest_word`). Contam como 0 candidatos.

## Comparacao detail-level contra baseline D6A

Baseline ouro: recorte dos primeiros 250 `render_wine_id` de
`reports/tail_candidate_fanout_pilot_detail_2026-04-10.csv.gz`.

| metrica | D6A (slice 250) | CACHED | resultado |
|---|---|---|---|
| total detail rows | 2.392 | 2.392 | **IGUAL** |
| wines distintos | 250 | 250 | **IGUAL** |
| `(wid, channel)` pairs com rows | 816 | 816 | **IGUAL** |
| `(wid, channel)` sets iguais | -- | -- | **IGUAL (sim)** |
| **score sequence** mismatches por `(wid,channel)` | -- | -- | **0 / 816 (100%)** |
| **gap** mismatches | -- | -- | **0 / 816 (100%)** |

Observacao critica: o caminho com cache bate **identicamente** o baseline nas
sequencias de `raw_score` por `(wid, channel)` e nos valores de
`top1_top2_gap`. Ambos sao funcoes puramente deterministicas do slice de
candidatos + `score_candidate()`. Se cache e baseline tem o mesmo score e
o mesmo gap em 100% dos pares, a semantica de scoring esta provadamente
preservada.

## Comparacao top1 por `(wid, channel)`

| resultado | contagem | % |
|---|---|---|
| match exato (candidate_id + score) | 804 / 816 | **98,53%** |
| mismatch com **mesmo score** (tiebreak SQL) | 12 / 816 | 1,47% |
| mismatch com score **diferente** | **0 / 816** | **0,00%** |

Os 12 mismatches de top1 por `(wid, channel)` sao todos casos onde o score e **identico** a D6A mas o candidato vencedor difere no tiebreak `candidate_id ASC`, porque o conjunto de candidatos que passou o `LIMIT 100` do Postgres foi ligeiramente diferente quando o cache foi construido (~1,3h depois do D6A, com outras particoes do heap quentes). Esse drift residual e **o mesmo que D6A teria contra si mesmo** numa reexecucao, pois o `ORDER BY similarity DESC LIMIT 100` nao e estavel em empates na fronteira.

## Comparacao per_wine contra baseline D6A

| metrica | D6A | CACHED | match |
|---|---|---|---|
| wines no per_wine | 250 | 250 | OK |
| `top1_render_candidate_id` exato | -- | -- | **245 / 250 (98,00%)** |
| `top1_import_candidate_id` exato | -- | -- | **250 / 250 (100,00%)** |
| `top1_render_score` exato | -- | -- | **250 / 250 (100,00%)** |
| `top1_import_score` exato | -- | -- | **250 / 250 (100,00%)** |
| `best_overall_universe/channel/score` | -- | -- | **250 / 250 (100,00%)** |

O cached runner ACERTA o score e o best_overall em **100% dos 250 wines**. Os 5 mismatches de top1_render_candidate_id sao todos casos onde D6A e cache tem o mesmo score no top1 mas candidates de id diferente no cluster de empate -- o drift residual aceito.

## Comparacao com D6B equivalencia

| metrica | D6B (fast) | D6C (cached) |
|---|---|---|
| detail rows iguais | 2.392 == 2.392 | 2.392 == 2.392 |
| score sequence mismatches | 1 / 816 | **0 / 816** |
| gap mismatches | 0 / 816 | 0 / 816 |
| top1 mismatch com score diferente | 0 | 0 |
| top1 mismatch com mesmo score (tie) | 11 | 12 |
| per_wine best_overall match | 249 / 250 | **250 / 250** |

O caminho com cache persistente e **tao equivalente quanto** o caminho fast (D6B), e em alguns quesitos (score sequences, best_overall) e ligeiramente **mais** alinhado com D6A do que o fast runner.

## Veredito de equivalencia

**EQUIVALENTE.**

- scores: 100% deterministicos (score sequences, gaps, top1_score, best_overall_score todos identicos)
- conjuntos `(wid, channel)`: identicos
- contagem de rows por `(wid, channel)`: identica
- drift residual: 12 tiebreak ties identicos em padrao ao drift ja aceito em D6B e em D6A-vs-D6A

O cache persistente preserva integralmente a logica congelada da Demanda 5.
A mecanica funciona: `synth_store_for(channel, key)` reconstitui um `store`
que produz exatamente a mesma query SQL que o wine original produziria, e
o resultado e cacheado + reutilizado sem reexecucao.

## Artefatos desta prova

- `reports/candidate_cache_slice250.sqlite3` (cache SQLite populado)
- `reports/tail_candidate_fanout_cached_250_detail_2026-04-10.csv.gz`
- `reports/tail_candidate_fanout_cached_250_per_wine_2026-04-10.csv.gz`
- `reports/tail_candidate_fanout_pilot_detail_2026-04-10.csv.gz` (baseline ouro D6A)
- `scripts/build_candidate_cache.py`
- `scripts/run_candidate_fanout_cached.py`
