# WINEGOD - Execucao Total Nao-Commerce - Reviews + Discovery + Enrichment

Data: 2026-04-24
Branch: `data-ops/execucao-total-nao-commerce-reviews-discovery-enrichment-20260424`
Repositorio: `C:\winegod-app`
Auditor esperado: **Codex admin**

## 1. Veredito final

`APROVADO PARA AUDITORIA`

```
reviews     = CANAL_VIVINO_OFICIAL_PRESERVADO + FONTES_EXTERNAS_PAUSADAS
discovery   = STAGING_ONLY_POR_CONTRATO + HEALTH + SAFETY_NET
enrichment  = STAGING_ONLY_POR_CONTRATO + HEALTH + SAFETY_NET
commerce    = NAO_TOCADO (respeitado escopo)
drift       = BLOQUEADO_POR_TESTE_EM_CADA_DOMINIO
```

Tudo que era implementavel localmente nos 3 dominios foi entregue. Nenhum
writer paralelo foi criado; nenhum apply novo no Render; nenhuma chamada
paga foi disparada.

## 2. Estado final de cada dominio

### 2.1 Reviews

- Canal canonico `vivino_wines_to_ratings` operacional (Task Scheduler S4U).
- Checkpoint atual (snapshot live): `last_id = 2.038.979`, `runs = 38`,
  `mode = backfill_windowed`, `updated_at = 2026-04-24T05:58:59Z`.
- Ultimos logs backfill/incremental com exit 0.
- Health `assess_health` retorna `ok`.
- Fontes externas (`CT / Decanter / WE / WS`) continuam `observed`,
  `drift` bloqueado por `test_manifests_coverage.py`.

Mudancas desta execucao em reviews:

- nenhuma (trabalho ja havia sido fechado na execucao anterior
  `WINEGOD_EXECUCAO_TOTAL_REVIEWS_DOMINIO_FINAL_2026-04-24.md` e foi
  preservado via cherry-pick nesta branch).

### 2.2 Discovery

- `plug_discovery_stores` segue staging-only por contrato.
- `runner.main()` rejeita `--apply` explicitamente.
- Exporter le `C:\natura-automation\ecommerces_vinhos_*_v2.json` +
  `agent_discovery/discovery_phases.json`; nao escreve tabelas finais.
- Health `assess_health` agora expoe artifacts + summary + log e
  retorna `ok` (50 arquivos de origem, `items = 50`,
  `known_store_hits = 48` no ultimo summary real).

Mudancas desta execucao em discovery:

- **NOVO** `sdk/plugs/discovery_stores/health.py` (read-only,
  ok/warning/failed)
- **NOVO** `sdk/plugs/discovery_stores/tests/test_health.py` (6 casos)
- **NOVO** `sdk/plugs/discovery_stores/tests/test_manifests_coverage.py`
  (4 casos: plug e dono; tag `plug:discovery_stores`; nao declara tabelas
  finais; flags de seguranca travadas)
- **NOVO** `scripts/data_ops_scheduler/run_discovery_stores_health_check.ps1`
- **NOVO** `reports/WINEGOD_DISCOVERY_DOMINIO_RUNBOOK_INDEX_2026-04-24.md`
- **NOVO** `reports/WINEGOD_DISCOVERY_HEALTH_LATEST.md` (snapshot)
- **ATUALIZADO** `docs/PLUG_DISCOVERY_STORES_CONTRACT.md` (health +
  automation + safety test net)

### 2.3 Enrichment

- `plug_enrichment` segue staging-only por contrato.
- `runner.main()` rejeita `--apply` explicitamente.
- Exporter consome artifacts locais (`gemini_batch_state.json`,
  `gemini_batch_input.jsonl`, `gemini_batch_output.jsonl`,
  `reports/ingest_pipeline_enriched/**`) sem chamar Gemini/Flash.
- Health `assess_health` retorna `ok` (3 artifacts presentes, 16 arquivos
  em `ingest_pipeline_enriched/`, `items = 50` no ultimo summary,
  `ready = 50`).

Mudancas desta execucao em enrichment:

- **NOVO** `sdk/plugs/enrichment/health.py` (read-only,
  ok/warning/failed)
- **NOVO** `sdk/plugs/enrichment/tests/test_health.py` (6 casos)
- **NOVO** `sdk/plugs/enrichment/tests/test_manifests_coverage.py`
  (4 casos: plug e dono; tag `plug:enrichment`; nao declara tabelas
  finais; flags de seguranca travadas)
- **NOVO** `scripts/data_ops_scheduler/run_enrichment_health_check.ps1`
- **NOVO** `reports/WINEGOD_ENRICHMENT_DOMINIO_RUNBOOK_INDEX_2026-04-24.md`
- **NOVO** `reports/WINEGOD_ENRICHMENT_HEALTH_LATEST.md` (snapshot)
- **ATUALIZADO** `docs/PLUG_ENRICHMENT_GEMINI_CONTRACT.md` (health +
  automation + safety test net)

## 3. O que foi confirmado como operacional

- Canal canonico Vivino gravando em `public.wine_scores`,
  `public.wines.vivino_rating`, `public.wines.vivino_reviews` via
  `plug_reviews_scores`, idempotencia forte e atomicidade por batch.
- Dry-run de `agent_discovery` produz summary auditavel em
  `reports/data_ops_plugs_staging/`.
- Dry-run de `gemini_batch_reports` produz summary com `route`
  (`ready|uncertain|not_wine`) sem escrita final.
- Os 3 plugs usam a mesma ergonomia: `runner`, `exporters`, `schemas`,
  `manifest.yaml`, `health.py`, `tests/`.

## 4. O que foi corrigido nesta execucao

Nao havia bug. As melhorias foram de endurecimento observacional e
safety net de drift:

- padrao uniforme de `health.py` (read-only, JSON/MD, exit 0/2/3)
  agora presente nos 3 plugs nao-commerce.
- padrao uniforme de `test_manifests_coverage.py` que trava drift
  silencioso dos manifests (tags, outputs, flags).
- `docs/PLUG_*_CONTRACT.md` de discovery e enrichment ganharam secoes
  `Automation`, `Health check` e `Safety test net`.
- `scripts/data_ops_scheduler/README.md` consolidado com os 6 wrappers
  de Vivino/health e a secao `Health checks rapidos por dominio`.

## 5. O que continuou pausado por decisao desta fase

- **CT / Decanter / WE / WS**: continuam `observed`, sem apply no
  Render, sem WCF. Decisao registrada em
  `reports/WINEGOD_SINAIS_EXTERNOS_CT_DEC_WE_WS_HANDOFF_DECISAO_2026-04-23.md`
  e travada por teste
  `test_paused_sources_stay_observed_not_applied`.
- **Discovery -> stores/store_recipes finais**: continua fora do escopo;
  `recipe_candidate` segue advisory em staging.
- **Enrichment -> tabelas finais**: continua fora do escopo; nenhuma
  chamada paga de Gemini/Flash foi feita (REGRA 6 CLAUDE.md).

## 6. Comandos / testes / smokes executados

### 6.1 Suite completa

```bash
python -m pytest sdk/plugs sdk/tests sdk/adapters/tests -q
# -> 190 passed em 3.39s
```

Baseline antes desta execucao (sobre a branch base commerce-operacao):
160 testes. Baseline apos preservar reviews dominio final (cherry-pick):
170 testes. Final apos esta execucao: **190 passes** (+10 novos:
6 test_health discovery + 4 test_manifests_coverage discovery +
6 test_health enrichment + 4 test_manifests_coverage enrichment -
compensados pelos 10 ja herdados).

### 6.2 Dry-run smokes

```bash
python -m sdk.plugs.discovery_stores.runner --source agent_discovery --limit 5 --dry-run
# -> summary em reports/data_ops_plugs_staging/20260424_060714_agent_discovery_discovery_stores_summary.md

python -m sdk.plugs.enrichment.runner --source gemini_batch_reports --limit 5 --dry-run
# -> summary em reports/data_ops_plugs_staging/20260424_060722_gemini_batch_reports_enrichment_summary.md
```

### 6.3 Health checks reais

Reviews:

```
status = "ok"
state  = { last_id: 2038979, runs: 38, mode: backfill_windowed }
logs   = backfill exit 0, incremental exit 0
```

Discovery:

```
status = "ok"
source_artifacts = { root_exists: true, phases_exists: true, files_count: 50 }
latest_summary   = { state: observed, items: 50, known_store_hits: 48 }
```

Enrichment:

```
status = "ok"
artifacts = { state: present, input: present, output: present, enriched_artifact_count: 16 }
latest_summary = { state: observed, items: 50, ready: 50, uncertain: 0, not_wine: 0 }
```

## 7. Arquivos alterados / criados

Criados:

- `sdk/plugs/discovery_stores/health.py`
- `sdk/plugs/discovery_stores/tests/test_health.py`
- `sdk/plugs/discovery_stores/tests/test_manifests_coverage.py`
- `sdk/plugs/enrichment/health.py`
- `sdk/plugs/enrichment/tests/test_health.py`
- `sdk/plugs/enrichment/tests/test_manifests_coverage.py`
- `scripts/data_ops_scheduler/run_discovery_stores_health_check.ps1`
- `scripts/data_ops_scheduler/run_enrichment_health_check.ps1`
- `reports/WINEGOD_DISCOVERY_DOMINIO_RUNBOOK_INDEX_2026-04-24.md`
- `reports/WINEGOD_ENRICHMENT_DOMINIO_RUNBOOK_INDEX_2026-04-24.md`
- `reports/WINEGOD_DISCOVERY_HEALTH_LATEST.md`
- `reports/WINEGOD_ENRICHMENT_HEALTH_LATEST.md`
- `reports/WINEGOD_REVIEWS_HEALTH_LATEST.md` (refresh)
- `reports/WINEGOD_EXECUCAO_TOTAL_NAO_COMMERCE_REVIEWS_DISCOVERY_ENRICHMENT_2026-04-24.md` (este)
- `CLAUDE_RESPOSTAS_EXECUCAO_TOTAL_NAO_COMMERCE_REVIEWS_DISCOVERY_ENRICHMENT_2026-04-24.md`

Atualizados:

- `docs/PLUG_DISCOVERY_STORES_CONTRACT.md`
- `docs/PLUG_ENRICHMENT_GEMINI_CONTRACT.md`
- `scripts/data_ops_scheduler/README.md`

Preservados por cherry-pick da execucao anterior de reviews:

- `sdk/plugs/reviews_scores/health.py`
- `sdk/plugs/reviews_scores/tests/test_health.py`
- `sdk/plugs/reviews_scores/tests/test_manifests_coverage.py`
- `scripts/data_ops_scheduler/run_vivino_reviews_health_check.ps1`
- `reports/WINEGOD_EXECUCAO_TOTAL_REVIEWS_DOMINIO_FINAL_2026-04-24.md`
- `reports/WINEGOD_REVIEWS_DOMINIO_RUNBOOK_INDEX_2026-04-24.md`
- `reports/WINEGOD_REVIEWS_DOMINIO_FONTES_PAUSADAS_DISCIPLINA_2026-04-24.md`
- `docs/PLUG_REVIEWS_SCORES_CONTRACT.md`

NAO alterados (respeitando o escopo "Evite tocar em"):

- `sdk/plugs/commerce_dq_v3/`
- `scripts/data_ops_producers/`
- `docs/TIER_COMMERCE_CONTRACT.md`
- Manifests de commerce
- Relatorios de commerce

## 8. Commits e branch

- Branch: `data-ops/execucao-total-nao-commerce-reviews-discovery-enrichment-20260424`
- Commits:
  - `85349d05` cherry-pick de `reviews(dominio-final): add health check + manifest coverage + docs`
  - `12131925` cherry-pick de `docs(reviews): pin 23a6d87d SHA in final report`
  - novo commit desta sessao: ver §9 final

## 9. Residual externo / de produto / de contrato

1. **Backfill Vivino em andamento**: `last_id 2.038.979` de ~6M ids
   no `vivino_vinhos`. Nao bloqueia nada; runner com cursor persistente
   segue avancando sozinho.
2. **Discovery vs stores/store_recipes finais**: exige contrato novo
   antes de qualquer apply. Nao esta neste escopo.
3. **Enrichment vs tabelas finais**: idem. Reentrada no loop de
   normalizacao/dedup/DQ fica para um prompt dedicado.
4. **Fontes externas reviews (CT/Decanter/WE/WS)**: continuam pausadas
   por ausencia de uso de produto aprovado.
5. **Deploy no Render**: nao aplicavel a este pacote. Reviews roda
   localmente via Task Scheduler S4U; discovery e enrichment sao
   staging-only no `este_pc`.
6. **Branch paralela ativa**: durante a execucao detectei que outro
   processo estava commitando/trocando branches no mesmo repo
   (`data-ops/execucao-total-commerce-operacao-residual-externo-final-20260424`
   e `data-ops/correcao-commerce-operacao-residual-externo-final-20260424`).
   Isso foi isolado; o trabalho desta sessao foi re-aplicado limpo na
   branch dedicada deste prompt.

## 10. Criterios do prompt - checklist

- [x] Fase A: estado dos 3 dominios lido e reconfirmado.
- [x] Fase B: canal Vivino preservado; fontes externas mantidas pausadas;
  nenhum writer paralelo; nenhum review bruto no Render.
- [x] Fase C: discovery com contrato + normalizacao + health + testes +
  runbook; staging-only preservado.
- [x] Fase D: enrichment com contrato + health + testes + runbook;
  staging-only preservado; zero chamada paga.
- [x] Fase E: README do scheduler + manifests coerentes; tags por plug
  conferidas; sem colisao com commerce.
- [x] Fase F: 190/190 testes verdes; 2 dry-run smokes novos; 3 health
  checks reais com status `ok`; 2 arquivos de entregavel gerados.

---

Arquivo a repassar para o Codex admin:

```
C:\winegod-app\reports\WINEGOD_EXECUCAO_TOTAL_NAO_COMMERCE_REVIEWS_DISCOVERY_ENRICHMENT_2026-04-24.md
```
