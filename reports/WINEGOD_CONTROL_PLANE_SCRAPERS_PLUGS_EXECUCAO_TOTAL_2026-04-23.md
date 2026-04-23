# WINEGOD CONTROL PLANE SCRAPERS + PLUGS - EXECUCAO TOTAL

Data: 2026-04-23  
Branch: `data-ops/scraper-plugs-execucao-total-20260423`  
Repositorio: `C:\winegod-app`

## 1. Veredito

`APROVADO_PARCIAL_COM_PENDENCIAS_HUMANAS`

Justificativa: o control plane ficou expandido, todos os scrapers do inventario ficaram mapeados no registry com status honesto, os plugs principais ficaram criados com dry-run/staging funcional, os observers continuaram em `success` e nao houve evidencia de escrita indevida em tabelas finais de negocio. Permaneceram para humano apenas as acoes realmente humanas ou deliberadamente bloqueadas nesta sessao: apply produtivo, deploy Render, Task Scheduler, PC espelho Amazon, Gemini real pago, PR/merge e aprovacoes externas.

## 2. O que foi implementado

- Extensao do contrato de registry/status para suportar `observed`, `blocked_contract_missing` e `blocked_external_host`, com migracao SQL e validacao em SDK/backend.
- Inclusao de dois observers novos:
  - `reviewers_vivino_global`
  - `catalog_vivino_updates`
- Atualizacao dos manifests observados existentes com `registry_status: observed` e tags `plug:*`.
- Inclusao de manifests bloqueados/planejados para commerce tiered e reviews Vivino particionados.
- Sincronizador de registry a partir de manifests: `scripts/data_ops_registry/sync_registry_from_manifests.py`.
- Framework de plugs em `sdk/plugs/` com telemetria consistente para `ops.scraper_runs` e `ops.ingestion_batches`.
- Plug `commerce_dq_v3` com exportacao para staging DQ V3, validacao, resumo Markdown e runner com `--dry-run`.
- Plug `reviews_scores` com staging de reviews/scores, runner somente dry-run e export otimizado para a base Vivino.
- Plug `discovery_stores` com leitura de artefatos locais de discovery, normalizacao de dominio/plataforma e staging sem escrita final.
- Plug `enrichment` com leitura de `reports/gemini_batch_*` e artefatos `ingest_pipeline_enriched`, classificando `ready`, `uncertain` e `not_wine`.
- Contratos/documentacao:
  - `docs/PLUG_REVIEWS_SCORES_CONTRACT.md`
  - `docs/PLUG_DISCOVERY_STORES_CONTRACT.md`
  - `docs/PLUG_ENRICHMENT_GEMINI_CONTRACT.md`
- Dashboard `/ops` ajustado para separar:
  - estado de registry
  - plug associado
  - pendencia
  - modo do ultimo run (`dry_run`, `apply`, `observer`, `shadow`, `planned`, `blocked`)
- Scripts de shadow e scheduler:
  - `scripts/data_ops_shadow/*`
  - `scripts/data_ops_scheduler/*`

## 3. Scrapers cobertos

### Observados e ativos no Control Plane

- `commerce_world_winegod_admin`
- `commerce_br_vinhos_brasil_legacy`
- `commerce_amazon_local`
- `commerce_dq_v3_observer`
- `reviews_vivino_global`
- `reviewers_vivino_global`
- `catalog_vivino_updates`
- `scores_cellartracker`
- `critics_decanter_persisted`
- `critics_wine_enthusiast`
- `market_winesearcher`
- `discovery_agent_global`
- `enrichment_gemini_flash`

### Plugs criados e registrados

- `plug_commerce_dq_v3`
- `plug_reviews_scores`
- `plug_discovery_stores`
- `plug_enrichment`

Estado final do registry em `ops.scraper_registry`: `29` linhas

- `observed = 17`
- `blocked_contract_missing = 8`
- `blocked_external_host = 3`
- `registered = 1` (`canary`)

## 4. Scrapers apenas planejados ou bloqueados

### `blocked_contract_missing`

- `commerce_amazon_mirror`
- `commerce_tier1_global`
- `commerce_tier2_chat1`
- `commerce_tier2_chat2`
- `commerce_tier2_chat3`
- `commerce_tier2_chat4`
- `commerce_tier2_chat5`
- `commerce_tier2_br`

### `blocked_external_host`

- `reviews_vivino_partition_a`
- `reviews_vivino_partition_b`
- `reviews_vivino_partition_c`

## 5. Plugs criados

- `plug_commerce_dq_v3`
  - fonte de entrada para commerce/ofertas
  - envia staging/summary para fluxo DQ V3
  - valida `dry_run` explicito e nao roda apply por padrao
- `plug_reviews_scores`
  - consolida staging de reviews/ratings
  - mantido em dry-run apenas nesta sessao
- `plug_discovery_stores`
  - transforma artefatos de discovery em staging de lojas/receitas candidatas
- `plug_enrichment`
  - transforma saidas Gemini/Flash e artefatos enriquecidos em staging auditavel

## 6. Dry-runs executados

### Scheduler de plugs

Executado com sucesso:

```powershell
powershell -File scripts/data_ops_scheduler/run_all_plug_dryruns.ps1
```

Evidencias de staging:

- `reports/data_ops_plugs_staging/20260423_152138_commerce_winegod_admin_world_summary.md`
  - `received=50`
  - `valid=43`
  - `filtered_notwine=7`
  - `would_insert=42`
  - `would_update=1`
- `reports/data_ops_plugs_staging/20260423_152150_commerce_vinhos_brasil_legacy_summary.md`
  - `received=50`
  - `valid=48`
  - `filtered_notwine=2`
  - `would_insert=18`
  - `would_update=29`
  - `would_enqueue_review=1`
- `reports/data_ops_plugs_staging/20260423_152210_commerce_amazon_local_summary.md`
  - `received=50`
  - `valid=40`
  - `filtered_notwine=10`
  - `would_insert=39`
  - `would_update=1`
- `reports/data_ops_plugs_staging/20260423_152328_vivino_reviews_to_scores_reviews_summary.md`
  - `source=vivino_reviews_to_scores_reviews`
  - `delivery_mode=dry_run`
  - `items=50`
- `reports/data_ops_plugs_staging/20260423_152358_agent_discovery_discovery_stores_summary.md`
  - `source=agent_discovery`
  - `delivery_mode=dry_run`
  - `items=100`
  - `known_store_hits=94`
- `reports/data_ops_plugs_staging/20260423_152407_gemini_batch_reports_enrichment_summary.md`
  - `source=gemini_batch_reports`
  - `delivery_mode=dry_run`
  - `items=100`
  - `ready=100`
  - `uncertain=0`
  - `not_wine=0`

### Validacao de wrappers shadow

Dry-run validado com sucesso para:

- `run_commerce_br_vinhos_brasil_legacy_shadow.ps1`
- `run_commerce_world_winegod_admin_shadow.ps1`
- `run_commerce_amazon_local_shadow.ps1`
- `run_discovery_agent_global_shadow.ps1`
- `run_commerce_amazon_mirror_shadow.ps1`
- `run_commerce_tier2_chat1_shadow.ps1`
- `run_reviews_vivino_global_shadow.ps1`

## 7. Applies reais executados

Executados nesta sessao:

- `python scripts/data_ops_registry/sync_registry_from_manifests.py --apply-status-migration --apply`
  - aplicou a migracao `024_ops_scraper_registry_extended_statuses.sql`
  - sincronizou `28` manifests no registry
- `python sdk/adapters/run_all_observers.py --apply`
  - executou observers e escreveu telemetria em `ops.*`
  - os `13` observers terminaram em `success`

Nao executados nesta sessao:

- nenhum `--apply` produtivo dos plugs
- nenhum apply em massa para `public.wines`, `public.wine_sources`, `wine_scores`, `wine_reviews` ou `store_recipes`
- nenhum deploy Render/Vercel
- nenhum scraping pesado real
- nenhum Gemini real pago

## 8. Testes e resultados

Todos os testes abaixo passaram:

- `python -m pytest sdk/plugs -q` -> `7 passed`
- `python -m pytest sdk/tests sdk/adapters/tests -q` -> `119 passed`
- `cd backend && python -m pytest tests/test_ops_dashboard.py tests/test_ops_schema_sql.py tests/test_ops_retention.py tests/test_ops_endpoints.py tests/test_ops_idempotency.py tests/test_ops_validation_runtime.py -q` -> `82 passed`
- `python -m pytest sdk/adapters/tests -q` -> `43 passed`

Validacoes operacionais tambem concluidas com sucesso:

- `python sdk/adapters/run_all_observers.py --apply`
- `powershell -File scripts/data_ops_scheduler/run_all_plug_dryruns.ps1`

## 9. Contagens antes/depois

| Objeto | Antes | Depois | Observacao |
| --- | ---: | ---: | --- |
| `public.wines` | n/d exato (timeout em 25s na auditoria inicial) | `2512042` | sem evidencia de apply produtivo; contagem final coletada com timeout maior |
| `public.wine_sources` | `3491038` | `3491038` | delta `0` |
| `public.wine_scores` | `0` | `0` | delta `0` |
| `public.wine_reviews` | tabela final nao localizada | tabela final nao localizada | sem escrita final possivel por este caminho |
| `public.store_recipes` | `0` | `0` | delta `0` |
| `ops.scraper_runs` | `20` | `65` | aumento esperado por observers/plugs dry-run |
| `ops.ingestion_batches` | `27` | `71` | aumento esperado por staging/dry-run |
| `ops.scraper_registry` | inventario parcial previo, sem baseline final consolidado | `29` | consolidado apos sync de manifests |

## 10. Evidencia de zero escrita indevida

- Os plugs ficaram em `dry_run=True` nas execucoes auditadas.
- O ultimo run de cada plug em `ops.scraper_runs` ficou com assinatura de dry-run:
  - `plug_commerce_dq_v3`: `dry_run=True`
  - `plug_reviews_scores`: `dry_run=True`
  - `plug_discovery_stores`: `dry_run=True`
  - `plug_enrichment`: `dry_run=True`
- `public.wine_sources` permaneceu exatamente em `3491038`.
- `public.wine_scores` permaneceu exatamente em `0`.
- `public.store_recipes` permaneceu exatamente em `0`.
- `public.wine_reviews` final nao apareceu como tabela de destino aplicavel nesta sessao.
- O aumento ficou concentrado em `ops.scraper_runs` e `ops.ingestion_batches`, compativel com telemetria e staging.
- Nao houve execucao de `--apply` nos runners de plugs.
- Conclusao auditavel: zero evidencia de escrita indevida em tabelas finais de negocio.

## 11. Commits criados

- `24499291` - `feat(data-ops): add scraper plug dry-run control plane`
- Este relatorio foi preparado para um commit seletivo de documentacao imediatamente apos a consolidacao final.

## 12. Branch publicada

Branch de trabalho:

```text
data-ops/scraper-plugs-execucao-total-20260423
```

Destino remoto planejado/publicado ao final desta sessao:

```text
origin/data-ops/scraper-plugs-execucao-total-20260423
```

Observacao: o worktree permaneceu muito sujo por alteracoes preexistentes fora do escopo. O stage/commit desta sessao foi seletivo e nao tentou limpar nem reverter itens alheios.

## 13. Pendencias humanas finais

- abrir PR para `main`
- decidir e executar deploy Render para expor a nova semantica do dashboard `/ops`
- instalar/agendar Task Scheduler para `scripts/data_ops_scheduler/*`
- executar apply produtivo pequeno por fonte para `plug_commerce_dq_v3`
- autorizar tabela final e modo apply para reviews/scores, se desejado
- executar pacote no PC espelho Amazon
- autorizar Gemini real pago, se houver interesse em enriquecimento produtivo
- aprovar shadow ou migracao nativa para scrapers externos ainda bloqueados

## 14. Comandos prontos para humans finais

### Commerce DQ V3 apply pequeno

```powershell
python -m sdk.plugs.commerce_dq_v3.runner --source winegod_admin_world --limit 50 --apply
python -m sdk.plugs.commerce_dq_v3.runner --source vinhos_brasil_legacy --limit 50 --apply
python -m sdk.plugs.commerce_dq_v3.runner --source amazon_local --limit 50 --apply
```

### Schedulers

```powershell
powershell -File scripts/data_ops_scheduler/run_all_observers.ps1
powershell -File scripts/data_ops_scheduler/run_all_plug_dryruns.ps1
```

### Shadow wrappers

```powershell
powershell -File scripts/data_ops_shadow/run_commerce_br_vinhos_brasil_legacy_shadow.ps1
powershell -File scripts/data_ops_shadow/run_commerce_br_vinhos_brasil_legacy_shadow.ps1 -Live
powershell -File scripts/data_ops_shadow/run_commerce_world_winegod_admin_shadow.ps1
powershell -File scripts/data_ops_shadow/run_commerce_amazon_local_shadow.ps1
powershell -File scripts/data_ops_shadow/run_reviews_vivino_global_shadow.ps1
```

### Reviews/discovery/enrichment staging

```powershell
python -m sdk.plugs.reviews_scores.runner --source vivino_reviews_to_scores_reviews --limit 50 --dry-run
python -m sdk.plugs.discovery_stores.runner --limit 100 --dry-run
python -m sdk.plugs.enrichment.runner --limit 100 --dry-run
```

### Git publish

```powershell
git push -u origin data-ops/scraper-plugs-execucao-total-20260423
```
