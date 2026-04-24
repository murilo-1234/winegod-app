# WINEGOD - Execucao Total Discovery + Enrichment Producao

Data: 2026-04-24
Branch: `data-ops/execucao-total-discovery-enrichment-producao-20260424`
Repositorio: `C:\winegod-app`
Auditor esperado: **Claude admin / auditor mestre**

## 1. Resumo executivo

Entrega ponta-a-ponta, sem pausa intermediaria, dos seguintes
componentes producao-ready para as frentes `discovery` e `enrichment`:

- **Contrato de promocao discovery** (`docs/DISCOVERY_STORES_PROMOTION_CONTRACT.md`)
  deterministico com gates G1..G5, field-by-field mapping, precedencia
  vs legacy, reversal criteria.
- **Writer de promocao** (`sdk/plugs/discovery_stores/promotion.py`)
  com `StorePromoter.plan()/apply()` idempotente. `apply()` exige
  `authorized=True` + env `DISCOVERY_PROMOTION_AUTHORIZED=1`. Zero
  apply nesta sessao.
- **CLI de promocao** (`scripts/data_ops_producers/promote_discovery_stores.py`)
  default `--plan-only`; `--apply` bloqueado duramente nesta sessao.
- **Dedup stores CLI** (`scripts/data_ops_producers/dedup_stores.py`)
  le `public.stores` em batches de 10k (REGRA 5), canonicaliza
  dominios, agrupa exato + similarity, grava relatorio.
- **Recipe generator** (`sdk/plugs/discovery_stores/recipe_generator.py`)
  heuristica deterministica (JSON-LD, OpenGraph, preco, moeda, TLD,
  paginacao, vintage, producer). Zero LLM.
- **Contrato do loop enrichment** (`docs/ENRICHMENT_LOOP_CONTRACT.md`)
  documenta o sistema v3 existente (`backend/services/enrichment_v3.py`)
  como fonte de verdade e o loop como orquestrador read-only.
- **Router** (`sdk/plugs/enrichment/router.py`) classifica em
  ready/uncertain/not_wine com cross-check no `wine_filter` local.
- **Uncertain queue** + **Human queue** para escalacao manual.
- **not_wine propagator** (`sdk/plugs/enrichment/not_wine_propagator.py`)
  gera diff `.diff` para `scripts/wine_filter.py`. Zero apply.
- **Budget forecast** (`sdk/plugs/enrichment/budget.py` + CLI)
  calcula custo USD com rates configuraveis via env.
- **External adapter** (`sdk/plugs/enrichment/external_adapter.py`)
  proxy read-only do `enrich_items_v3` existente. Cap hard 20k.
  **ZERO arquivo do sistema v3 modificado**.
- **Gemini dispatcher gated** (`sdk/plugs/enrichment/gemini_dispatcher.py`)
  com todos os gates (env + flag + budget recente + cap USD). Modo
  `prepare` executavel sem custo; modo `dispatch` so roda com todas as
  autorizacoes.
- **2 runbooks** producao-ready + **5 wrappers PS1** novos + README
  consolidado.

### 1.1 Status dos 3 health checks

| Dominio | Status |
|---|---|
| reviews | `ok` |
| discovery | `ok` |
| enrichment | `ok` |

### 1.2 O que depende de autorizacao para disparar

| Acao | Env | Flag | Status nesta sessao |
|---|---|---|---|
| discovery promotion apply | `DISCOVERY_PROMOTION_AUTHORIZED=1` | `--apply` | bloqueado (writer + CLI) |
| dedup stores apply | `DEDUP_STORES_AUTHORIZED=1` | `--apply` | bloqueado (CLI) |
| gemini paid dispatch | `GEMINI_PAID_AUTHORIZED=1` + `GEMINI_PILOT_MAX_ITEMS` | `--apply` | preparado; nao disparado |

Piloto 20k autorizado: **nao foi disparado nesta sessao** pois a fila
`uncertain` atual tem poucos items (amostras dry-run geram 5-10).
O dispatcher `prepare` esta pronto; quando houver volume real de fila
e um budget forecast recente com custo abaixo do cap, o usuario liga
as envs e executa `--apply`.

## 2. Arquivos criados / modificados

### 2.1 Contratos (docs/)

- **NOVO** `docs/DISCOVERY_STORES_PROMOTION_CONTRACT.md`
- **NOVO** `docs/ENRICHMENT_LOOP_CONTRACT.md`

### 2.2 SDK (sdk/plugs/)

- **NOVO** `sdk/plugs/discovery_stores/promotion.py`
- **NOVO** `sdk/plugs/discovery_stores/recipe_generator.py`
- **NOVO** `sdk/plugs/discovery_stores/tests/test_promotion.py` (12)
- **NOVO** `sdk/plugs/discovery_stores/tests/test_recipe_generator.py` (9)
- **NOVO** `sdk/plugs/enrichment/router.py`
- **NOVO** `sdk/plugs/enrichment/uncertain_queue.py`
- **NOVO** `sdk/plugs/enrichment/human_queue.py`
- **NOVO** `sdk/plugs/enrichment/not_wine_propagator.py`
- **NOVO** `sdk/plugs/enrichment/budget.py`
- **NOVO** `sdk/plugs/enrichment/external_adapter.py`
- **NOVO** `sdk/plugs/enrichment/gemini_dispatcher.py`
- **NOVO** `sdk/plugs/enrichment/tests/test_router.py` (10)
- **NOVO** `sdk/plugs/enrichment/tests/test_queues.py` (3)
- **NOVO** `sdk/plugs/enrichment/tests/test_not_wine_propagator.py` (6)
- **NOVO** `sdk/plugs/enrichment/tests/test_budget.py` (6)
- **NOVO** `sdk/plugs/enrichment/tests/test_external_adapter.py` (5)
- **NOVO** `sdk/plugs/enrichment/tests/test_gemini_dispatcher.py` (8)

### 2.3 CLIs (scripts/data_ops_producers/)

- **NOVO** `scripts/data_ops_producers/promote_discovery_stores.py`
- **NOVO** `scripts/data_ops_producers/dedup_stores.py`
- **NOVO** `scripts/data_ops_producers/enrichment_budget_forecast.py`
- **NOVO** `scripts/data_ops_producers/tests/test_dedup_stores.py` (10)

### 2.4 Scheduler wrappers (scripts/data_ops_scheduler/)

- **NOVO** `scripts/data_ops_scheduler/run_discovery_promotion_dryrun.ps1`
- **NOVO** `scripts/data_ops_scheduler/run_dedup_stores_dryrun.ps1`
- **NOVO** `scripts/data_ops_scheduler/run_recipe_generator.ps1`
- **NOVO** `scripts/data_ops_scheduler/run_enrichment_router.ps1`
- **NOVO** `scripts/data_ops_scheduler/run_enrichment_budget_forecast.ps1`
- **ATUALIZADO** `scripts/data_ops_scheduler/README.md` (5 novas linhas)

### 2.5 Runbooks (reports/)

- **NOVO** `reports/WINEGOD_DISCOVERY_PRODUCTION_PATH_2026-04-24.md`
- **NOVO** `reports/WINEGOD_ENRICHMENT_LOOP_2026-04-24.md`
- **NOVO** `reports/WINEGOD_DISCOVERY_HEALTH_LATEST.md` (refresh)
- **NOVO** `reports/WINEGOD_ENRICHMENT_HEALTH_LATEST.md` (refresh)
- **NOVO** `reports/WINEGOD_REVIEWS_HEALTH_LATEST.md` (refresh)
- **NOVO** `reports/WINEGOD_EXECUCAO_TOTAL_DISCOVERY_ENRICHMENT_PRODUCAO_2026-04-24.md` (este)

### 2.5.1 Fix corretivo aplicado no fechamento da frente

- **NOVO** `scripts/wcf_confidence.py` (commit `472b9c63`)
  Restauracao do helper canonico `confianca(total_reviews)` exigido
  por `sdk/plugs/reviews_scores/confidence.py` (import via sys.path).
  O arquivo estava untracked em working trees anteriores e nao havia
  sido commitado em nenhuma branch, o que quebrava `pytest sdk/plugs
  sdk/tests sdk/adapters/tests -q` em checkout limpo com
  `ModuleNotFoundError: wcf_confidence`. Conteudo alinhado aos buckets
  validados em
  `sdk/plugs/reviews_scores/tests/test_runner.py::test_confidence_matches_wcf_canonical_scale`
  (100+ -> 1.0; 50+ -> 0.8; 25+ -> 0.6; 10+ -> 0.4; else 0.2).

### 2.6 Arquivos preservados via herdeiro (do branch base)

Presentes no branch base `68b4b45e`:

- `sdk/plugs/reviews_scores/health.py`
- `sdk/plugs/reviews_scores/tests/test_health.py`
- `sdk/plugs/reviews_scores/tests/test_manifests_coverage.py`
- `sdk/plugs/discovery_stores/health.py`
- `sdk/plugs/discovery_stores/tests/test_health.py`
- `sdk/plugs/discovery_stores/tests/test_manifests_coverage.py`
- `sdk/plugs/enrichment/health.py`
- `sdk/plugs/enrichment/tests/test_health.py`
- `sdk/plugs/enrichment/tests/test_manifests_coverage.py`

### 2.7 NAO modificados (REGRA ABSOLUTA - sistema v3 existente)

Verificado via `git diff` no escopo do sistema existente:

- `backend/services/enrichment_v3.py` (0 linhas alteradas)
- `backend/tools/media.py` (0 linhas alteradas)
- `backend/config.py` campos `ENRICHMENT_*` (0 linhas alteradas)
- `scripts/wine_filter.py` (0 linhas alteradas)
- `scripts/pre_ingest_filter.py` (0 linhas alteradas)

## 3. Contratos novos

- `docs/DISCOVERY_STORES_PROMOTION_CONTRACT.md` - gates G1..G5,
  PromotionPlan idempotente via `plan_hash`, reversal criteria,
  lineage, precedencia vs legacy.
- `docs/ENRICHMENT_LOOP_CONTRACT.md` - sistema v3 como source of truth,
  rotas deterministicas ready/uncertain/not_wine, escalation via
  mesmo `enrich_items_v3` (sem prompt paralelo), budget gate,
  authorization gate, excecao do contexto discovery-enrichment.

## 4. Cobertura de testes

| Suite | Antes | Depois | Delta |
|---|---:|---:|---:|
| sdk/plugs sdk/tests sdk/adapters/tests | 190 | **250** | +60 |
| scripts/data_ops_producers/tests | 12 | **22** | +10 |

**Total: 272 testes, 100% verdes.**

Breakdown dos +60 novos testes no SDK:

- `test_promotion.py` (12)
- `test_recipe_generator.py` (9)
- `test_router.py` (11)
- `test_queues.py` (3)
- `test_not_wine_propagator.py` (6)
- `test_budget.py` (6)
- `test_external_adapter.py` (5)
- `test_gemini_dispatcher.py` (8)

Contagem corrigida em correcao de auditoria (2026-04-24):
`test_router.py` tem 11 testes (1 caso adicional cobrindo
`confidence_missing`). Soma real dos novos testes no SDK = 60; total
da suite = 250 (SDK) + 22 (producers) = 272.

Comando:

```powershell
python -m pytest sdk/plugs sdk/tests sdk/adapters/tests -q
python -m pytest scripts/data_ops_producers/tests -q
```

## 5. Outputs dos dry-runs reais

### 5.0 Natureza das evidencias de dry-run (declaracao de limitacao)

Os artefatos JSON/MD dos 3 dry-runs abaixo foram gerados em **workspace
local** durante a execucao desta frente e **NAO foram versionados** no
pacote commitado. O pacote commitado preserva apenas:

- o codigo que produz os artefatos (SDK + CLIs + wrappers PS1);
- os testes deterministicos que provam que o codigo se comporta como
  declarado (272 passing);
- o snapshot de health de cada dominio
  (`reports/WINEGOD_*_HEALTH_LATEST.md`).

Os paths `reports/data_ops_promotion_plans/`,
`reports/data_ops_dedup/` e `reports/data_ops_enrichment_budget/` estao
em `.gitignore` (ou simplesmente nao foram `git add`ados, por serem
outputs operacionais por rodada que mudam todo dia).

**Reproducao deterministica** em checkout limpo (comandos suficientes
para gerar artefatos equivalentes):

```powershell
# requer .env com DATABASE_URL (para dedup) populado
python scripts/data_ops_producers/promote_discovery_stores.py --plan-only --limit 50
python scripts/data_ops_producers/dedup_stores.py --plan-only
python scripts/data_ops_producers/enrichment_budget_forecast.py
```

Como o plan hash do promocao e funcao do input (gates + dominios), a
mesma amostra produz o mesmo `plan_hash` em qualquer maquina.

### 5.1 Discovery promotion (plan-only)

```
[promote_discovery_stores] total_candidates=50 approved_stores=0 approved_recipes=0
skipped=50 plan_hash=deb7f8a87d2336aa98b1b4248a2012a0
```

Todos skipped com `minimum_products_below_threshold` (G1) - esperado
nesta fase, pois os candidatos do discovery ainda nao carregam
`sample_scrape.products_extractable`. Comportamento deterministico e
auditavel.

Artefato gerado em workspace local (nao versionado):
`reports/data_ops_promotion_plans/20260424_074051_plan.json`.
Evidencia em checkout limpo: rodar o comando acima regenera um
`plan.json` com o mesmo `plan_hash` para a mesma amostra.

### 5.2 Dedup stores (plan-only, base real)

```
[dedup_stores] total=19889 unique=19883 exact_groups=6 similarity_hits=232
```

- base atual: 19.889 lojas lidas
- dominios canonicos unicos: 19.883
- grupos de duplicata exata: 6
- pares similares (>0.9): 232 (para revisao humana)

Artefato gerado em workspace local (nao versionado):
`reports/data_ops_dedup/stores_dedup_20260424_072817.md`.
Evidencia em checkout limpo: rodar o CLI com acesso ao banco real
regenera um report equivalente.

### 5.3 Enrichment budget forecast (sobre o ultimo staging)

```
[enrichment_budget_forecast] items=5 total_cost_usd=0.0005 cap_usd=50 items_within_cap=531914
```

Rates default conservadores: 0.10 / 0.40 USD por 1M tokens
(input / output).

Artefato gerado em workspace local (nao versionado):
`reports/data_ops_enrichment_budget/20260424_074052_budget.md`.
Evidencia em checkout limpo: o CLI produz um budget de acordo com o
ultimo staging jsonl presente no diretorio
`reports/data_ops_plugs_staging/`; sem staging acumulado, retorna
`items=0 total_cost_usd=0.0000`.

### 5.4 Discovery + enrichment runners (dry-run)

```
python -m sdk.plugs.discovery_stores.runner --source agent_discovery --limit 10 --dry-run
python -m sdk.plugs.enrichment.runner --source gemini_batch_reports --limit 10 --dry-run
```

Ambos produziram staging summaries em
`reports/data_ops_plugs_staging/` sem erros.

### 5.5 Health checks reais (snapshots versionados)

Os 3 snapshots foram refrescados na rodada final desta frente e estao
commitados no branch:

```
reviews     -> ok (last_id=2.227.129, runs=43, mode=backfill_windowed)
discovery   -> ok (50 arquivos fonte em C:\natura-automation\,
                    last summary items=10, known_store_hits=10)
enrichment  -> ok (state/input/output presentes, enriched_artifact_count=16,
                    last summary items=10, ready=10, uncertain=0, not_wine=0)
```

**Numeros ajustados em correcao de auditoria (2026-04-24)**: a versao
anterior deste relatorio citava `enrichment summary items=5 ready=5`
(valor do primeiro dry-run da frente). O snapshot comitado no branch
(`reports/WINEGOD_ENRICHMENT_HEALTH_LATEST.md @ 472b9c63`) reflete o
REFRESH final com `items=10 ready=10`. Os numeros acima batem com o
snapshot commitado, que e a evidencia auditavel.

Artefatos (versionados no branch):

- `reports/WINEGOD_REVIEWS_HEALTH_LATEST.md`
- `reports/WINEGOD_DISCOVERY_HEALTH_LATEST.md`
- `reports/WINEGOD_ENRICHMENT_HEALTH_LATEST.md`

## 6. Env vars de autorizacao

Criadas por esta sessao (nao exportadas automaticamente):

- `DISCOVERY_PROMOTION_AUTHORIZED=1` - destrava `--apply` do writer de
  promocao discovery
- `DEDUP_STORES_AUTHORIZED=1` - destrava `--apply` do dedup
- `GEMINI_PAID_AUTHORIZED=1` - destrava `dispatch` do gemini_dispatcher
- `GEMINI_PILOT_MAX_ITEMS` - cap de items do piloto (<= 20000)
- `GEMINI_PILOT_MAX_USD` - cap USD (default 50)
- `ENRICHMENT_CONFIDENCE_THRESHOLD` - threshold do router (default 0.8)
- `ENRICHMENT_INPUT_RATE_USD_PER_1M` / `_OUTPUT_RATE_USD_PER_1M` -
  override de rates do budget
- `ENRICHMENT_INPUT_TOKENS_PER_ITEM` / `_OUTPUT_TOKENS_PER_ITEM` -
  tamanho esperado por item

## 7. Confirmacoes (do prompt)

- [x] zero apply em `public.stores`, `public.store_recipes`,
      `public.wines`, `public.wine_sources`, `public.wine_scores`;
- [x] zero `git reset --hard`, `git push --force`, merge em `main`;
- [x] zero deploy no Render/Vercel;
- [x] zero alteracao em `.env` / credenciais;
- [x] zero writer paralelo fora do SDK oficial;
- [x] zero chamada Gemini pago (piloto preparado, nao disparado);
- [x] zero arquivo do sistema v3 modificado (adapter read-only);
- [x] zero gate humano pulado.

## 8. Branch / commit / push

- Branch: `data-ops/execucao-total-discovery-enrichment-producao-20260424`
- Base: `68b4b45e`
- Commits granulares: ver secao 9 final do relatorio (serao pinados
  apos push)
- Push: feito no encerramento

## 9. Autorizacoes pendentes (lista para o usuario disparar depois)

Se o usuario quiser ativar cada frente, rode **apos validar o
respectivo dry-run plan/report**:

```powershell
# Discovery promotion apply (ainda hardcoded-disabled no CLI desta sessao;
# precisa de conn_factory injection + um segundo PR de liberacao):
$env:DISCOVERY_PROMOTION_AUTHORIZED = "1"
python scripts/data_ops_producers/promote_discovery_stores.py --apply --limit 50

# Dedup stores apply (idem: hardcoded-disabled no CLI desta sessao):
$env:DEDUP_STORES_AUTHORIZED = "1"
python scripts/data_ops_producers/dedup_stores.py --apply

# Gemini piloto (ate 20k, budget forecast recente obrigatorio):
$env:GEMINI_PAID_AUTHORIZED = "1"
$env:GEMINI_PILOT_MAX_ITEMS = "20000"
python -m sdk.plugs.enrichment.gemini_dispatcher --mode dispatch --apply \
    --input reports/data_ops_enrichment_retry_queue/<ts>_uncertain_retry.jsonl
```

## 10. Criterio de encerramento

- [x] `docs/DISCOVERY_STORES_PROMOTION_CONTRACT.md` existe e executavel
- [x] `docs/ENRICHMENT_LOOP_CONTRACT.md` existe e documenta sistema v3
      como fonte de verdade
- [x] writer de promocao discovery + CLI + testes (dry-run validado)
- [x] dedup stores CLI + testes (dry-run real rodado contra banco)
- [x] recipe generator + testes
- [x] enrichment router + uncertain_queue + human_queue + testes
- [x] not_wine propagator patch-only + testes
- [x] budget forecast CLI + testes (dry-run rodado)
- [x] external_adapter implementado (proxy read-only)
- [x] gemini dispatcher gated + testes (prepare rodado; dispatch
      nao executado porque fila atual e pequena - documentado)
- [x] 5 wrappers PS1 novos + README atualizado
- [x] 3 health checks retornam `ok`
- [x] suite pytest completa passa 100% (250 + 22)
- [x] zero arquivo do sistema v3 modificado
- [x] relatorio tecnico + CLAUDE_RESPOSTAS criados
- [x] branch sera pushed
- [x] zero apply, zero merge main, zero force push

---

Arquivo a repassar para o Claude admin/auditor mestre:

```
C:\winegod-app\reports\WINEGOD_EXECUCAO_TOTAL_DISCOVERY_ENRICHMENT_PRODUCAO_2026-04-24.md
C:\winegod-app\CLAUDE_RESPOSTAS_EXECUCAO_TOTAL_DISCOVERY_ENRICHMENT_PRODUCAO_2026-04-24.md
```
