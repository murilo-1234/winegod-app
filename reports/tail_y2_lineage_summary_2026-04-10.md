# Tail Y2 + Lineage Enriched -- Summary (Demanda 4)

Data execucao: 2026-04-10 20:27:58
Executor: `scripts/enrich_tail_y2_lineage.py`
Artefato CSV: `tail_y2_lineage_enriched_2026-04-10.csv.gz` (gzip)

## Disciplina Metodologica

- `y2_results` entra como **BASELINE HISTORICO**, NAO como verdade.
- `y2_results.vivino_id` = `wines.id` do Render, **NAO** o `vivino_id` real do Vivino.
- Esta etapa NAO gera candidatos, NAO classifica negocio, NAO faz match.

## Proveniencia

- Banco Render: read-only, fonte de `wines (id, hash_dedup) WHERE vivino_id IS NULL`.
- Banco LOCAL `winegod_db`: read-only, fonte de `wines_clean`, `y2_results`, `vinhos_XX_fontes`.
- Joins via TEMP TABLE local (sem N+1, sem ANY com 779k itens via parametros).
- 50 tabelas `vinhos_XX_fontes` enumeradas via `information_schema.tables` (regex `^vinhos_([a-z]{2})_fontes$`).
- Filtragem de fontes por `vinho_id = ANY(%s)` em batches de 5.000 ids.

## Conteudo do Extract

- Total de linhas: **779,383**
- render_wine_id distintos: **779,383**
- wines com hash_dedup nulo/vazio: **0**

## Colunas do CSV

| coluna | origem | definicao |
|---|---|---|
| `render_wine_id` | `wines.id` | chave primaria do vinho na cauda |
| `hash_dedup` | `wines.hash_dedup` | hash MD5 do vinho no Render |
| `clean_ids_count` | derivado | numero de `wines_clean.id` que casam pelo `hash_dedup` |
| `clean_ids_sample` | derivado | ate 5 menores `clean_id` separados por virgula |
| `y2_present` | derivado | 1 se algum `clean_id` resolveu em `y2_results`, senao 0 |
| `y2_rows_count` | derivado | numero de linhas `y2_results` (1 por clean_id, ja que `clean_id` e unico em y2) |
| `y2_status_set` | derivado | set de statuses unicos, ordenado, separado por `\|` |
| `y2_any_matched` | derivado | 1 se algum row tem `status='matched'` |
| `y2_any_new` | derivado | 1 se algum row tem `status='new'` |
| `y2_any_not_wine_or_spirit` | derivado | 1 se algum row tem `status IN ('not_wine','spirit')` |
| `y2_match_score_max` | derivado | max(`match_score`) entre os rows; vazio se nenhum |
| `y2_match_score_min` | derivado | min(`match_score`) entre os rows; vazio se nenhum |
| `y2_matched_rows_count` | derivado | numero de rows com `status='matched'` |
| `y2_new_rows_count` | derivado | numero de rows com `status='new'` |
| `local_lineage_resolved` | derivado | 1 se `clean_ids_count>0` E `local_fontes_rows_count>0` |
| `local_fontes_rows_count` | derivado | total de linhas em `vinhos_XX_fontes` para todas as `(pais, id_orig)` deste wine |
| `local_fontes_tables_count` | derivado | numero de tabelas `vinhos_XX_fontes` distintas envolvidas |
| `local_urls_count` | derivado | total de `url_original` nao-nulas em `vinhos_XX_fontes` |
| `local_price_rows_count` | derivado | total de linhas com `preco` nao-nulo em `vinhos_XX_fontes` |

## QA -- Cruzamento com Etapa 1

| check | esperado | obtido | resultado |
|---|---|---|---|
| total de linhas do extract | 779,383 | 779,383 | OK |
| render_wine_id unicos = total | 779,383 | 779,383 | OK |

## Cobertura -- hash_dedup -> wines_clean

- wines com pelo menos 1 `clean_id` resolvido: **777,836**
- wines sem nenhum `clean_id` (perda de join): **1,547**
- cobertura de wines_clean: **99.80%**

### Bucket de cardinalidade `clean_ids_count`

| bucket | wines |
|---|---|
| 0 clean_ids | 1,547 |
| 1 clean_id | 754,847 |
| >1 clean_ids | 22,989 |

## Cobertura -- y2_results (BASELINE, nao verdade)

- wines com `y2_present=1`: **777,836**
- cobertura y2: **99.80%**
- wines com `y2_any_matched=1`: **6,208**
- wines com `y2_any_new=1`: **777,836**
- wines com `y2_any_not_wine_or_spirit=1`: **1,939**

### Bucket de cardinalidade `y2_rows_count`

| bucket | wines |
|---|---|
| 0 y2_rows | 1,547 |
| 1 y2_row | 754,847 |
| >1 y2_rows | 22,989 |

### Distribuicao de `y2_status_set` (top 20)

| y2_status_set | wines |
|---|---|
| `new` | 762,158 |
| `duplicate|new` | 7,066 |
| `matched|new` | 4,135 |
| `duplicate|matched|new` | 1,931 |
| `new|not_wine` | 1,217 |
| `error|new` | 532 |
| `new|spirit` | 410 |
| `duplicate|new|not_wine` | 152 |
| `duplicate|new|spirit` | 75 |
| `error|matched|new` | 69 |
| `matched|new|not_wine` | 51 |
| `duplicate|matched|new|not_wine` | 12 |
| `new|not_wine|spirit` | 11 |
| `duplicate|error|new` | 4 |
| `error|new|not_wine` | 3 |
| `duplicate|error|matched|new` | 2 |
| `error|matched|new|spirit` | 2 |
| `matched|new|spirit` | 2 |
| `duplicate|matched|new|spirit` | 2 |
| `error|matched|new|not_wine` | 1 |

## Cobertura -- linhagem local (vinhos_XX_fontes)

- wines com `local_lineage_resolved=1`: **777,364**
- cobertura linhagem: **99.74%**
- wines com `local_fontes_rows_count=0`: **2,019**

- paises com tabela `vinhos_XX_fontes` usada: **50** -- ['ae', 'ar', 'at', 'au', 'be', 'bg', 'br', 'ca', 'ch', 'cl', 'cn', 'co', 'cz', 'de', 'dk', 'es', 'fi', 'fr', 'gb', 'ge', 'gr', 'hk', 'hr', 'hu', 'ie', 'il', 'in', 'it', 'jp', 'kr', 'lu', 'md', 'mx', 'nl', 'no', 'nz', 'pe', 'ph', 'pl', 'pt', 'ro', 'ru', 'se', 'sg', 'th', 'tr', 'tw', 'us', 'uy', 'za']

## Veredito

**EXTRACT VALIDO.** A base enriquecida da cauda esta pronta para a proxima demanda.

## Reexecucao

```bash
cd C:\winegod-app
python scripts/enrich_tail_y2_lineage.py
```

Idempotente. Cada rodada sobrescreve os artefatos. Sem efeito colateral em producao.

