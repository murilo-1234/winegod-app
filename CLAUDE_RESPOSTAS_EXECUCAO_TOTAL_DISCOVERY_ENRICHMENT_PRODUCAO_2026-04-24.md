# CLAUDE_RESPOSTAS - Execucao Total Discovery + Enrichment Producao

Sessao: 2026-04-24
Branch: `data-ops/execucao-total-discovery-enrichment-producao-20260424`

=== ULTIMA RESPOSTA - ESTA E A QUE INTERESSA (com correcoes de auditoria aplicadas) ===

## Pergunta original

```
C:\winegod-app\prompts\PROMPT_CLAUDE_EXECUCAO_TOTAL_DISCOVERY_ENRICHMENT_PRODUCAO_2026-04-24.md
```

## Veredito

Execucao ponta-a-ponta completada, sem gate humano intermediario.
Discovery e enrichment agora tem writer/CLI producao-ready, contratos
executaveis, testes unitarios, runbooks e health checks verdes.
Sistema v3 existente (`backend/services/enrichment_v3.py`) nao foi
tocado em linha alguma.

## O que foi feito (resumo)

- Contratos novos:
  - `docs/DISCOVERY_STORES_PROMOTION_CONTRACT.md`
  - `docs/ENRICHMENT_LOOP_CONTRACT.md`
- Writer + CLI discovery (dry-run):
  - `sdk/plugs/discovery_stores/promotion.py`
  - `scripts/data_ops_producers/promote_discovery_stores.py`
- Dedup stores CLI (dry-run real rodado, 19.889 lojas):
  - `scripts/data_ops_producers/dedup_stores.py`
- Recipe generator deterministico (zero LLM):
  - `sdk/plugs/discovery_stores/recipe_generator.py`
- Router + filas + patch propagator de enrichment:
  - `sdk/plugs/enrichment/router.py`
  - `sdk/plugs/enrichment/uncertain_queue.py`
  - `sdk/plugs/enrichment/human_queue.py`
  - `sdk/plugs/enrichment/not_wine_propagator.py`
- Budget forecast + CLI (rates configuraveis):
  - `sdk/plugs/enrichment/budget.py`
  - `scripts/data_ops_producers/enrichment_budget_forecast.py`
- Adapter read-only + dispatcher gated:
  - `sdk/plugs/enrichment/external_adapter.py`
  - `sdk/plugs/enrichment/gemini_dispatcher.py`
- 5 wrappers PS1 novos + README atualizado
- 2 runbooks de producao (discovery + enrichment)
- Relatorio tecnico + esta resposta
- Fix corretivo no fechamento (commit `472b9c63`):
  - `scripts/wcf_confidence.py` (helper canonico restaurado para
    destravar pytest em checkout limpo)

## Testes

- `pytest sdk/plugs sdk/tests sdk/adapters/tests -q` -> **250 passed**
- `pytest scripts/data_ops_producers/tests -q` -> **22 passed**
- Total: **272 testes**, 100% verdes.
- +60 testes no SDK (promotion 12, recipe_generator 9, router 11,
  queues 3, not_wine 6, budget 6, external_adapter 5,
  gemini_dispatcher 8).
- +10 testes em producers (dedup_stores).

## Dry-runs reais

- Discovery promotion: 50 candidatos, 0 approved (skipped por
  `minimum_products_below_threshold` - esperado nesta fase).
- Dedup stores: 19.889 lojas lidas, 19.883 canonicos unicos,
  6 grupos de duplicata exata, 232 similarity hits (>0.9).
- Enrichment budget: 5 items atuais na fila, cost_usd=0.0005,
  `items_within_cap=531.914` para cap $50.

**Natureza das evidencias**: os artefatos JSON/MD dos 3 dry-runs acima
foram gerados em **workspace local** e **nao foram versionados** no
pacote commitado (`reports/data_ops_promotion_plans/`,
`reports/data_ops_dedup/` e `reports/data_ops_enrichment_budget/` sao
outputs operacionais). O pacote commitado preserva o codigo, os
testes deterministicos e os snapshots de health. Para reproduzir em
checkout limpo, ver secao 5.0 do relatorio tecnico.

## Health checks (snapshots versionados no branch)

- reviews: `ok` (last_id=2.227.129, runs=43, mode=backfill_windowed)
- discovery: `ok` (50 arquivos fonte, summary items=10, known_store_hits=10)
- enrichment: `ok` (artifacts presentes, summary items=10 ready=10,
  uncertain=0, not_wine=0)

**Numeros ajustados em correcao de auditoria**: a versao anterior
deste documento citava `summary items=5 ready=5` para enrichment -
valor do PRIMEIRO dry-run da frente. O snapshot commitado no branch
(`reports/WINEGOD_ENRICHMENT_HEALTH_LATEST.md @ 472b9c63`) reflete o
REFRESH final com `items=10 ready=10`. Os numeros acima batem com o
snapshot commitado, que e a evidencia auditavel.

## Piloto Gemini 20k

NAO disparado. Motivos:

- fila atual e pequena (<10 items em staging dry-run);
- budget forecast ja roda, mas dispatcher exige cap USD respeitado
  E volume real;
- conforme contrato, o piloto so faz sentido com dado real.

O sistema esta pronto. Quando a fila enrichment tiver volume,
o usuario:

1. gera budget forecast atualizado;
2. `$env:GEMINI_PAID_AUTHORIZED=1`;
3. `$env:GEMINI_PILOT_MAX_ITEMS=20000`;
4. `python -m sdk.plugs.enrichment.gemini_dispatcher --mode dispatch --apply --input <jsonl>`.

## Zero violacoes de rails de seguranca

- Zero apply em `public.stores / store_recipes / wines / wine_sources / wine_scores`.
- Zero `git reset --hard`, `git push --force`, merge em `main`.
- Zero deploy no Render/Vercel.
- Zero mudanca em `.env`.
- Zero arquivo do sistema v3 modificado (adapter fino, proxy only).
- Zero chamada Gemini pago.
- Zero gate humano pulado.

## Autorizacoes pendentes (usuario dispara depois)

- `DISCOVERY_PROMOTION_AUTHORIZED=1` + `--apply`
- `DEDUP_STORES_AUTHORIZED=1` + `--apply`
- `GEMINI_PAID_AUTHORIZED=1` + `--apply`

## Git

Branch: `data-ops/execucao-total-discovery-enrichment-producao-20260424`
Base: `68b4b45e`
Commits: granulares por fase (ver final do relatorio tecnico).
Push: origin (tip `472b9c63`).

## Historico de correcoes de auditoria

- 2026-04-24: correcao de consistencia documental (contagem de
  `test_router.py` de 10 -> 11, health enrichment alinhado ao snapshot
  commitado 10/10, inclusao de `scripts/wcf_confidence.py` na lista de
  arquivos, declaracao explicita de que os artefatos de dry-run nao
  estao versionados com instrucao de reproducao). Veredito tecnico
  (CONCLUIDO) preservado.

---

Arquivo a repassar para o Claude admin/auditor mestre:

```
C:\winegod-app\reports\WINEGOD_EXECUCAO_TOTAL_DISCOVERY_ENRICHMENT_PRODUCAO_2026-04-24.md
C:\winegod-app\CLAUDE_RESPOSTAS_EXECUCAO_TOTAL_DISCOVERY_ENRICHMENT_PRODUCAO_2026-04-24.md
```
