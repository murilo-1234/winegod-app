# WINEGOD - MATRIZ DOS SCRAPERS RESTANTES

Data: 2026-04-23
Branch: `data-ops/integracao-restantes-scrapers-total-20260423`
Base: `152cb10b` da branch anterior
Escopo: classificacao dos scrapers que NAO foram go-live na sessao anterior.

## Legenda de `acao_nesta_execucao`

- `integrate_and_apply_now` - implementar + apply controlado local
- `integrate_and_dryrun_only` - integrar e executar apenas dry-run local
- `integrate_observer_only` - completar observer/registry/manifest
- `integrate_shadow_only` - completar shadow wrapper + manifest
- `automate_existing_path` - automatizar path ja pronto via scheduler
- `blocked_external_host` - fora desta maquina
- `blocked_contract_missing` - contrato/saida padronizada ausente
- `blocked_credentials_or_access` - sem credenciais/acesso

## Matriz

| scraper_id | family | path | host | estado_real | saida_atual | canal_correto | acao_nesta_execucao | bloqueio | evidencia |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| commerce_amazon_local | commerce | natura-automation/amazon | este_pc | dry-run validado, risco colisao mirror | winegod_db vinhos_*_fontes | plug_commerce_dq_v3 | `automate_existing_path` | mirror pendente | scheduler novo de dry-run dedicado + manifest ja existe |
| commerce_amazon_mirror | commerce | PC espelho | pc_espelho | shadow wrapper existe | local no espelho | plug_commerce_dq_v3 via shadow | `blocked_external_host` | host externo | manifest + shadow ja existem |
| commerce_tier1_global | commerce | natura-automation/winegod_admin | este_pc | sem isolamento de contrato vs tier2 | winegod_db indistinto | plug_commerce_dq_v3 | `blocked_contract_missing` | saida nao distingue Tier1/Tier2 | manifest + shadow ja existem |
| commerce_tier2_chat1..5 + tier2_br | commerce | chats Codex | este_pc | artefato nao padronizado | saida por chat | plug_commerce_dq_v3 | `blocked_contract_missing` | contrato de saida ausente | manifests + shadows ja existem |
| scores_cellartracker | review | natura-automation/jobs/cellartracker_scraper | este_pc | observer OK | ct_vinhos em winegod_db | plug_reviews_scores (cellartracker_to_scores_reviews) | `integrate_and_dryrun_only` + `automate_existing_path` | - | observer+shadow+manifest OK; falta scheduler dedicado + matching seguro |
| critics_decanter_persisted | review | natura-automation/winegod_v2 | este_pc | observer OK | decanter_vinhos em winegod_db | plug_reviews_scores (decanter_to_critic_scores) | `integrate_and_dryrun_only` + `automate_existing_path` | - | observer+shadow+manifest OK |
| critics_wine_enthusiast | review | natura-automation/winegod_v2 | este_pc | observer OK, shadow **ausente** | we_vinhos em winegod_db | plug_reviews_scores (wine_enthusiast_to_critic_scores) | `integrate_shadow_only` | - | manifest OK, shadow wrapper faltava |
| market_winesearcher | market | natura-automation/winegod_v2 | este_pc | observer OK, shadow **ausente** | ws_vinhos em winegod_db | plug_reviews_scores (winesearcher_to_market_signals) | `integrate_shadow_only` | - | manifest OK, shadow wrapper faltava |
| reviewers_vivino_global | review | natura-automation/vivino | este_pc | observer OK, shadow **ausente** | vivino_reviewers em WINEGOD_DATABASE_URL | plug_reviews_scores (apoio) | `integrate_shadow_only` | - | manifest OK, shadow wrapper faltava |
| catalog_vivino_updates | review | natura-automation/vivino | este_pc | observer OK, shadow **ausente** | vivino_vinhos + vivino_execucoes | plug_reviews_scores (observer) | `integrate_shadow_only` | - | manifest OK, shadow wrapper faltava |
| reviews_vivino_global | review | natura-automation/vivino | este_pc | path apply canonico ativo via vivino_wines_to_ratings | vivino_reviews + vivino_vinhos | plug_reviews_scores | `automate_existing_path` | - | scheduler apply ja existe; scheduler dry-run ja existe |
| reviews_vivino_partition_a | review | particao A (local) | este_pc | contrato local ausente | particao nao isolada | plug_reviews_scores | `blocked_contract_missing` | particao A sem contrato | manifest + shadow ja existem |
| reviews_vivino_partition_b | review | PC espelho | pc_espelho | wrapper shadow OK | local no espelho | plug_reviews_scores via shadow | `blocked_external_host` | host externo | manifest + shadow ja existem |
| reviews_vivino_partition_c | review | WAB | wab_host | wrapper shadow OK | WAB externo | plug_reviews_scores via shadow | `blocked_external_host` | host externo | manifest + shadow ja existem |
| discovery_agent_global | discovery | natura-automation/agent_discovery | este_pc | dry-run OK, scheduler dedicado **ausente** | artefatos locais | plug_discovery_stores | `automate_existing_path` | - | scheduler dedicado novo |
| enrichment_gemini_flash | enrichment | reports/gemini_batch_* | este_pc | observer OK, shadow **ausente** | flash_vinhos + artefatos | plug_enrichment (observer) | `integrate_shadow_only` + documentar | Gemini pago proibido | manifest OK, shadow wrapper faltava |

## Decisoes por scraper nesta execucao

### Commerces

- Amazon local: manter dry-run. Mirror Amazon ainda bloqueia. Adicionar scheduler dedicado `run_commerce_dryruns.ps1` para rodar batch dry-run dos locais (winegod_admin_world, vinhos_brasil_legacy, amazon_local) sem disparar applies.
- Amazon mirror + Tier1 + Tier2: manter blocked. Documentar claramente no relatorio, shadow ja existe.

### Reviews

- vivino_wines_to_ratings: path apply canonico ja validado. Scheduler existente `run_plug_reviews_scores_apply.ps1` suporta `incremental_recent` e `backfill_windowed`. Nao re-executar apply sem autorizacao.
- cellartracker_to_scores_reviews / decanter_to_critic_scores / wine_enthusiast_to_critic_scores / winesearcher_to_market_signals: rodar dry-run no scheduler dedicado `run_reviews_scores_dryruns.ps1`.
- reviewers_vivino_global / catalog_vivino_updates: completar shadow wrappers + confirmar observer via `run_all_observers.ps1`.

### Discovery + enrichment

- discovery_agent_global: dry-run via scheduler dedicado `run_discovery_stores_dryruns.ps1`.
- enrichment_gemini_flash: dry-run via scheduler dedicado `run_enrichment_dryruns.ps1`; shadow wrapper novo; Gemini pago NAO acionado.

## Entregaveis desta execucao

1. 5 novos shadow wrappers:
   - `run_critics_wine_enthusiast_shadow.ps1`
   - `run_market_winesearcher_shadow.ps1`
   - `run_reviewers_vivino_global_shadow.ps1`
   - `run_catalog_vivino_updates_shadow.ps1`
   - `run_enrichment_gemini_flash_shadow.ps1`
2. Scheduler mestre novo `run_all_shadows.ps1` (chama todos os shadows locais em modo wrapper-validation).
3. Schedulers dedicados por familia:
   - `run_commerce_dryruns.ps1` (commerces locais)
   - `run_reviews_scores_dryruns.ps1` (reviews)
   - `run_discovery_stores_dryruns.ps1` (discovery)
   - `run_enrichment_dryruns.ps1` (enrichment)
4. README atualizado em `scripts/data_ops_scheduler/README.md`.
5. Relatorio final + CLAUDE_RESPOSTAS.
