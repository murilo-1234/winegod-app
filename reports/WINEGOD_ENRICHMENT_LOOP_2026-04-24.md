# WINEGOD - Enrichment Loop

Data: 2026-04-24
Branch: `data-ops/execucao-total-discovery-enrichment-producao-20260424`
Contrato: [docs/ENRICHMENT_LOOP_CONTRACT.md](../docs/ENRICHMENT_LOOP_CONTRACT.md)
Sistema existente (READ-ONLY): [`backend/services/enrichment_v3.py`](../backend/services/enrichment_v3.py)

## 1. O que foi entregue

Codigo:

- `sdk/plugs/enrichment/router.py` - `route_item` deterministico
  (`ready / uncertain / not_wine`) com cross-check no
  `scripts/pre_ingest_filter.should_skip_wine`
- `sdk/plugs/enrichment/uncertain_queue.py` - prepara payload de retry V2
  via v3 existente (sem chamar Gemini)
- `sdk/plugs/enrichment/human_queue.py` - report markdown da fila humana
- `sdk/plugs/enrichment/not_wine_propagator.py` - extrai pattern e gera
  patch diff para `scripts/wine_filter.py` (sem aplicar)
- `sdk/plugs/enrichment/budget.py` - estimador USD (rates via env ou
  default conservador), `recommended_batch_cap` para cap
- `sdk/plugs/enrichment/external_adapter.py` - proxy read-only do
  `enrich_items_v3` existente, cap hard 20k
- `sdk/plugs/enrichment/gemini_dispatcher.py` - prepare/dispatch com
  TODOS os gates (env, flag, budget recent, cap USD)
- `scripts/data_ops_producers/enrichment_budget_forecast.py` - CLI

Testes:

- `sdk/plugs/enrichment/tests/test_router.py` (10 casos)
- `sdk/plugs/enrichment/tests/test_queues.py` (3 casos)
- `sdk/plugs/enrichment/tests/test_not_wine_propagator.py` (6 casos)
- `sdk/plugs/enrichment/tests/test_budget.py` (6 casos)
- `sdk/plugs/enrichment/tests/test_external_adapter.py` (5 casos)
- `sdk/plugs/enrichment/tests/test_gemini_dispatcher.py` (8 casos)

## 2. Sistema existente - como e usado

A regra zero: **nao alteramos nada de `backend/services/enrichment_v3.py`**.

O adapter `external_adapter.py` faz apenas:

1. lazy import de `enrich_items_v3` ja em producao;
2. cap hard de 20k items por chamada;
3. proxy 1:1 do resultado;
4. `describe_interface()` documenta onde o sistema mora e qual a
   assinatura publica.

Modelo: `Config.ENRICHMENT_GEMINI_25_MODEL` (primary) +
`Config.ENRICHMENT_GEMINI_31_MODEL` (escalated). Zero mudanca.

## 3. Como rodar dry-runs

```powershell
# Router + fila (pega o ultimo staging e classifica)
python -m sdk.plugs.enrichment.runner --source gemini_batch_reports --limit 10 --dry-run

# Budget forecast (usa a fila atual)
python scripts/data_ops_producers/enrichment_budget_forecast.py

# Gemini dispatcher em modo prepare (ZERO chamada Gemini)
python -m sdk.plugs.enrichment.gemini_dispatcher \
  --mode prepare --input reports/data_ops_enrichment_retry_queue/<ts>_uncertain_retry.jsonl

# Wrappers PS1
powershell -File scripts/data_ops_scheduler/run_enrichment_router.ps1
powershell -File scripts/data_ops_scheduler/run_enrichment_budget_forecast.ps1
```

Artefatos gerados:

- `reports/data_ops_enrichment_retry_queue/<ts>_uncertain_retry.jsonl`
- `reports/data_ops_enrichment_human_queue/<ts>_human_queue.md`
- `reports/data_ops_not_wine_patches/<ts>_wine_filter_patch.diff`
- `reports/data_ops_enrichment_budget/<ts>_budget.md` + `.json`
- `reports/data_ops_enrichment_gemini_batches/<ts>_input.jsonl`
  (prepare)
- `reports/data_ops_enrichment_pilot/<ts>_result.jsonl` (dispatch,
  so se autorizado)

## 4. O que precisa autorizacao explicita para ativar

| Acao | Env var | Flag |
|---|---|---|
| dispatch via adapter (chama Gemini de verdade) | `GEMINI_PAID_AUTHORIZED=1` + `GEMINI_PILOT_MAX_ITEMS=<N<=20000>` | `--apply` |
| apply patch `wine_filter.py` | (manual `git apply`) | - |

Condicoes extras do dispatcher:

- budget forecast recente (<=24h) em `reports/data_ops_enrichment_budget/`
- custo total estimado no budget json <= `GEMINI_PILOT_MAX_USD`
  (default 50)

Nesta sessao, o piloto de 20k **nao foi disparado** porque a fila
atual tem muito poucos items (default dry-runs produziram 5 items).
O comportamento esta documentado; o dispatcher esta pronto para
rodar quando a fila tiver volume real.

## 5. Fluxo operacional do loop

```
v3_result.jsonl (do enrichment_v3 ou staging)
  -> router.route_item
       -> ready     -> fila de apply (fora deste escopo)
       -> uncertain -> uncertain_queue.persist_queue -> retry via v3 -> (se ainda uncertain) human_queue
       -> not_wine  -> not_wine_propagator -> diff em reports/
```

Todos os arquivos ficam em `reports/`; nenhum toca em tabela de
producao.

## 6. Criterios de sucesso operacional

- Rodar pytest -q da suite enrichment: 100% verde.
- Router nao aumenta a fila uncertain em mais de X% entre duas execucoes
  com mesmo input (criterio de idempotencia/determinismo).
- Budget forecast retorna custo USD coerente com volume real.
- Prepare gera jsonl valido ingestavel pelo dispatch.

## 7. Riscos conhecidos

- **Rates Gemini no budget**: defaults sao conservadores (0.10
  input + 0.40 output USD/1M). Para producao, override via env com
  valores reais da pagina de preco do Google naquele momento.
- **Cap USD default 50**: o dispatcher bloqueia qualquer dispatch com
  custo estimado acima disso. Para escalar, operador sobrescreve via
  `GEMINI_PILOT_MAX_USD`.
- **Propagador de not_wine** gera so diff; se ninguem aplicar o patch,
  patterns ficam como backlog.
- **Sistema v3 evolui** por outro time. O adapter nao trava em tipo
  estatico; se `enrich_items_v3` mudar assinatura, o adapter precisa de
  uma atualizacao pontual. Documentado em `describe_interface()`.

## 8. Rollback procedure

Esta sessao entregou so prepare + tests + docs. Zero chamada Gemini,
zero escrita em producao. Rollback = remover commits da branch.

Se um `dispatch --apply` for executado no futuro:

1. localizar `reports/data_ops_enrichment_pilot/<ts>_result.jsonl`;
2. diff contra `enrich_items_v3` historico se necessario (estatisticas
   em `stats`);
3. NAO ha rollback de apply em tabela de producao porque este escopo
   nao escreve em tabelas finais.
