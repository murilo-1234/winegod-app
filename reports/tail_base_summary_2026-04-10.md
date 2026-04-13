# Tail Base Extract -- Summary (Demanda 3)

Data execucao: 2026-04-10 19:49:58
Executor: `scripts/extract_tail_base.py`
Fonte: Render (live, read-only)
Artefato CSV: `tail_base_extract_2026-04-10.csv.gz` (gzip)

## Proveniencia

- Banco: Render PostgreSQL (DATABASE_URL via backend/.env)
- Modo: read-only, nenhuma escrita feita
- Conexao: psycopg2 com keepalives e statement_timeout=300s
- Estrategia: agregacao server-side de wine_sources (`GROUP BY wine_id`) +
  cursor server-side da cauda (`WHERE vivino_id IS NULL`) com LEFT JOIN em memoria
- Sem loop por item, sem consulta por wine_id

## Conteudo do Extract

- Total de linhas: **779,383**
- render_wine_id distintos: **779,383**
- has_sources = 1: **771,312**
- no_source_flag = 1: **8,071**

## Colunas do CSV

| coluna | origem | definicao |
|---|---|---|
| `render_wine_id` | `wines.id` | chave primaria do vinho no Render |
| `nome` | `wines.nome` | nome do vinho (raw) |
| `produtor` | `wines.produtor` | produtor (raw) |
| `safra` | `wines.safra` | safra (varchar) |
| `tipo` | `wines.tipo` | tipo (tinto/branco/etc) |
| `preco_min` | `wines.preco_min` | preco minimo registrado em wines (numeric) |
| `moeda` | `wines.moeda` | moeda associada ao preco_min |
| `wine_sources_count_live` | `COUNT(*) FROM wine_sources WHERE wine_id = w.id` | numero de linhas em wine_sources para esse wine, contado live nesta execucao |
| `stores_count_live` | `COUNT(DISTINCT store_id) FROM wine_sources WHERE wine_id = w.id` | numero de stores distintas que tem esse wine, contado live |
| `has_sources` | derivado | `1` se `wine_sources_count_live > 0`, senao `0` |
| `no_source_flag` | derivado | `1` se `wine_sources_count_live = 0`, senao `0` |
| `total_fontes_raw` | `wines.total_fontes` | valor cru da coluna no Render. **Nao usar como fonte primaria.** Ver secao total_fontes abaixo. |

## QA -- Cruzamento com Etapa 1

| check | esperado (Etapa 1) | obtido (Demanda 3) | resultado |
|---|---|---|---|
| total de linhas do extract | 779,383 | 779,383 | OK |
| render_wine_id unicos = total | 779,383 | 779,383 | OK |
| SUM(no_source_flag) | 8,071 | 8,071 | OK |
| SUM(has_sources) | 771,312 | 771,312 | OK |
| has + no = total (particao) | 779,383 | 779,383 | OK |
| stores_count_live <= wine_sources_count_live (invariante) | violacoes = 0 | violacoes = 0 | OK |

## QA -- Filtro de cauda (vivino_id IS NULL)

A query do extract usa `WHERE vivino_id IS NULL` no proprio SELECT, portanto **nenhum item do extract pode ter `vivino_id IS NOT NULL`** por construcao. Esta condicao e estrutural (filtro SQL), nao requer verificacao por amostragem.

## QA -- total_fontes (decisao documentada)

- itens com `total_fontes = wine_sources_count_live`: **428,700**
- itens com `total_fontes != wine_sources_count_live`: **349,136**
- itens com `total_fontes IS NULL`: **1,547**
- concordancia entre nao-nulos: **55.11%**

**Status: BLOQUEADO -- semantica nao verificada**

wines.total_fontes diverge da contagem live em 349,136 de 777,836 casos nao-nulos (44.89% de discrepancia). Semantica nao confirmada. NAO usar. Usar wine_sources_count_live.

## Veredito

**EXTRACT VALIDO.** Todos os checks de QA passaram. A base operacional da cauda esta pronta para a proxima demanda (enriquecimento, candidatos, etc).

## Reexecucao

```bash
cd C:\winegod-app
python scripts/extract_tail_base.py
```

O script e idempotente: cada rodada sobrescreve `tail_base_extract_2026-04-10.csv.gz` e `tail_base_summary_2026-04-10.md`. Sem efeito colateral em producao.

