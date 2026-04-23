# WINEGOD - EXECUCAO TOTAL - RESTANTES SCRAPERS NA PLATAFORMA

Data: 2026-04-23
Branch: `data-ops/integracao-restantes-scrapers-total-20260423`
Base: `152cb10b` em `data-ops/execucao-total-commerce-reviews-routing-20260423`
Auditor: Codex admin
Executor: Claude Code (Opus 4.7 1M context)
Prompt: `prompts/PROMPT_CLAUDE_EXECUCAO_TOTAL_RESTANTES_SCRAPERS_PLATAFORMA_2026-04-23.md`

## 16.1 Veredito

```text
APROVADO_PARCIAL_COM_BLOQUEIOS_EXTERNOS
```

Integracao total local do que e seguro: shadows ausentes foram criados, schedulers por familia foram criados, registry continua consistente, observadores refrescados com 13/13 em success. Permanecem bloqueados somente itens externos/contratuais: Amazon mirror (host externo), reviews_vivino_partition_b/c (hosts externos), commerce_tier1_global e commerce_tier2_* (contrato de saida ausente), reviews_vivino_partition_a (contrato de particao local ausente). Zero Gemini pago, zero writer paralelo, zero apply nao autorizado por este executor.

### Regra de escopo obrigatoria desta execucao (atualizada)

**CellarTracker, Decanter, Wine Enthusiast e Wine-Searcher NAO sobem para o Render nesta fase.** Para essas 4 fontes, o escopo desta sessao foi exclusivamente: plataforma / observer / staging / telemetria. Nao foi criada nota de produto, WCF, score final, uso de produto artificial nem mistura com a base local do Vivino. Todos os wrappers e schedulers criados para essas 4 fontes operam em modo dry-run ou wrapper-validation — nenhum apply habilitado para o Render nesta execucao. O unico caminho canonico de reviews com writer final aprovado no repositorio continua sendo `vivino_wines_to_ratings` e ele NAO foi re-executado aqui.

## 16.2 Matriz final dos scrapers restantes

Arquivo dedicado: `reports/WINEGOD_RESTANTES_SCRAPERS_MATRIX_2026-04-23.md`.

Resumo por acao:

### `integrate_shadow_only` (shadows novos criados nesta sessao)

- `critics_wine_enthusiast` -> `scripts/data_ops_shadow/run_critics_wine_enthusiast_shadow.ps1`
- `market_winesearcher` -> `scripts/data_ops_shadow/run_market_winesearcher_shadow.ps1`
- `reviewers_vivino_global` -> `scripts/data_ops_shadow/run_reviewers_vivino_global_shadow.ps1`
- `catalog_vivino_updates` -> `scripts/data_ops_shadow/run_catalog_vivino_updates_shadow.ps1`
- `enrichment_gemini_flash` -> `scripts/data_ops_shadow/run_enrichment_gemini_flash_shadow.ps1`

### `automate_existing_path` (schedulers dedicados novos)

- commerce local (winegod_admin_world, vinhos_brasil_legacy, amazon_local) -> `run_commerce_dryruns.ps1`
- reviews nao-vivino_wines_to_ratings (vivino_reviews, cellartracker, decanter, wine_enthusiast, winesearcher) -> `run_reviews_scores_dryruns.ps1`
- discovery (agent_discovery) -> `run_discovery_stores_dryruns.ps1`
- enrichment (gemini_batch_reports) -> `run_enrichment_dryruns.ps1`
- shadow master `run_all_shadows.ps1` para wrapper-validation de todos os shadows

### `integrate_observer_only`

- Todos os observers em `sdk/adapters/*_observer.py` confirmados OK via `run_all_observers.ps1` (13/13 success).

### `blocked_external_host`

- `commerce_amazon_mirror`
- `reviews_vivino_partition_b`
- `reviews_vivino_partition_c`

### `blocked_contract_missing`

- `commerce_tier1_global`
- `commerce_tier2_chat1..5`, `commerce_tier2_br`
- `reviews_vivino_partition_a`

## 16.3 O que foi integrado de verdade

### Commerce

- `plug_commerce_dq_v3` continua com apply dedicado apenas para `winegod_admin_world` (escada 50/200/1000 aplicada na sessao anterior) e `vinhos_brasil_legacy` (apply 50; 200 gated).
- `amazon_local` continua em dry-run; agora automatizado via `run_commerce_dryruns.ps1` (smoke validado com limit=20).
- `amazon_mirror`, `tier1_global`, `tier2_*` mantidos em blocked - **shadow wrappers pre-existentes ja cobrem o registry** e continuam correto para o dashboard.
- Scheduler novo `run_commerce_dryruns.ps1` cobre somente as fontes locais seguras (nao dispara Tier1/Tier2/mirror).

### Reviews

- `plug_reviews_scores` com writer canonico publicado na sessao anterior (commit `d68ecddd`).
- Shadows novos: `critics_wine_enthusiast`, `market_winesearcher`, `reviewers_vivino_global`, `catalog_vivino_updates`.
- Scheduler dedicado `run_reviews_scores_dryruns.ps1` cobre 5 sources em dry-run sem tocar `public.wine_scores`.
- Scheduler `run_plug_reviews_scores_apply.ps1` (apply canonico de `vivino_wines_to_ratings` com `incremental_recent`/`backfill_windowed`) continua disponivel - NAO re-executado nesta sessao.
- Zero review bruto escrito em `ops.*`. Zero escrita em `wine_sources`.
- **CellarTracker, Decanter, Wine Enthusiast, Wine-Searcher** - integrados apenas na plataforma/observer/staging/telemetria. NENHUM desses 4 sobe para o Render nesta fase. Nenhum uso de produto, WCF ou score final criado. Dados dessas fontes permanecem em `winegod_db` local (ct_vinhos, decanter_vinhos, we_vinhos, ws_vinhos) e NAO sao misturados na base local do Vivino nem replicados para `public.wine_scores`/`public.wines` no Render.

### Discovery

- `plug_discovery_stores` continua como staging only.
- Scheduler dedicado `run_discovery_stores_dryruns.ps1` cobre `agent_discovery` em dry-run.
- Observer `discovery_agent_global` refrescado com `stores=243633 countries=50 files=50`.

### Enrichment

- `plug_enrichment` mantem papel de observer-only.
- Shadow novo `run_enrichment_gemini_flash_shadow.ps1` (nao aciona Gemini pago).
- Scheduler dedicado `run_enrichment_dryruns.ps1` cobre `gemini_batch_reports` (items=50 dry-run).
- Observer `enrichment_gemini_flash` refrescado com `total_wines=300428 ready=208 uncertain=53`.

## 16.4 O que foi automatizado

### Novos arquivos

- `scripts/data_ops_shadow/run_critics_wine_enthusiast_shadow.ps1`
- `scripts/data_ops_shadow/run_market_winesearcher_shadow.ps1`
- `scripts/data_ops_shadow/run_reviewers_vivino_global_shadow.ps1`
- `scripts/data_ops_shadow/run_catalog_vivino_updates_shadow.ps1`
- `scripts/data_ops_shadow/run_enrichment_gemini_flash_shadow.ps1`
- `scripts/data_ops_scheduler/run_all_shadows.ps1`
- `scripts/data_ops_scheduler/run_commerce_dryruns.ps1`
- `scripts/data_ops_scheduler/run_reviews_scores_dryruns.ps1`
- `scripts/data_ops_scheduler/run_discovery_stores_dryruns.ps1`
- `scripts/data_ops_scheduler/run_enrichment_dryruns.ps1`

### Arquivos atualizados

- `scripts/data_ops_scheduler/README.md` - lista os 9 scripts atuais com descricao e uso.

### Reuso

- `sdk/plugs/*` nao foi tocado (ja estavam completos apos sessao anterior).
- `sdk/adapters/*_observer.py` nao foi tocado (ja funcionam).
- Manifests em `sdk/adapters/manifests/*.yaml` nao foram tocados (ja estao coerentes com `registry_status`).

### Smokes executados com sucesso

- `run_commerce_dryruns.ps1 -Limit 20` -> 3 fontes commerce
- `run_reviews_scores_dryruns.ps1 -Limit 20` -> 5 fontes reviews
- `run_discovery_stores_dryruns.ps1 -Limit 50` -> 1 fonte discovery
- `run_enrichment_dryruns.ps1 -Limit 50` -> 1 fonte enrichment
- 5 novos shadows em wrapper-validation mode retornaram `shadow_wrapper=ok`
- `run_all_observers.ps1` -> 13/13 observers em success

## 16.5 O que realmente foi aplicado na base final

Este executor NAO aplicou nada novo na base final nesta sessao.

Delta observado entre preflight e postcheck:

| Objeto | Antes (sessao atual inicio) | Depois (final) | Delta | Origem |
| --- | ---: | ---: | ---: | --- |
| `public.wines` | 2512787 | 2512787 | 0 | nenhum apply |
| `public.wine_sources` | 3491567 | 3491567 | 0 | nenhum apply |
| `public.wine_scores` | 508 | 530 | +22 | NAO executado por este executor (provavel apply paralelo de Murilo em `vivino_wines_to_ratings` fora desta sessao; os 22 seguem a mesma assinatura `fonte='vivino'` e mesmo writer canonico) |
| `public.store_recipes` | 0 | 0 | 0 | - |
| `public.not_wine_rejections` | 546 | 546 | 0 | - |
| `public.ingestion_review_queue` | 10 | 10 | 0 | - |
| `ops.scraper_runs` | 103 | 138 | +35 | observers refresh + 10 smokes de schedulers + 5 smokes de shadows |
| `ops.ingestion_batches` | 108 | 143 | +35 | mesmos motivos acima |
| `ops.scraper_registry` | 29 | 29 | 0 | registry nao mudou |

Smokes de plug runners (dry-run) geraram telemetria em `ops.scraper_runs` e `ops.ingestion_batches`, sem tocar tabelas de negocio.

## 16.6 O que permaneceu bloqueado

Bloqueios reais, com motivo:

- `commerce_amazon_mirror` - roda em PC espelho, sem acesso local; shadow wrapper esta pronto para ser disparado no host correto.
- `reviews_vivino_partition_b` / `reviews_vivino_partition_c` - hosts externos (PC espelho, WAB). Shadows prontos.
- `commerce_tier1_global` - saida persistida em `winegod_db` nao distingue Tier1 de Tier2; criar adaptador exige isolamento contratual que envolve mudar o scraper de origem.
- `commerce_tier2_chat1..5` e `commerce_tier2_br` - saida por chat Codex sem artefato local padronizado; para integrar exige definir protocolo de artefato de saida com o operador dos chats.
- `reviews_vivino_partition_a` - particao local existe mas nao esta isolada contratualmente.
- Gemini pago real - bloqueado pela REGRA 6 do `CLAUDE.md`; shadow esta pronto mas so roda read-only.
- Deploy Render - bloqueado pela REGRA 7 (deploy manual, nao ha caminho nao-interativo pronto).
- PR/merge em main - bloqueado por politica (sem solicitacao explicita do usuario).

## 16.7 Evidencia de seguranca

- Zero canal errado: commerce continua apenas em `plug_commerce_dq_v3`; reviews em `plug_reviews_scores`; discovery em `plug_discovery_stores`; enrichment em `plug_enrichment`.
- Zero review em `wine_sources` (count inalterado em `public.wine_sources` nesta sessao).
- Zero enrichment direto na base final (plug_enrichment permanece staging only).
- Zero DQ V3 para fontes nao-commerce (nao foi criado canal novo).
- Zero segredo exposto: nenhum `.env` lido para stdout, nenhum token em log, nenhum `.env` commitado.
- Zero writer paralelo criado.
- Zero Gemini pago disparado.
- Zero escrita em `wines`/`wine_sources`/`store_recipes`.
- **Zero upload para Render** de `cellartracker`, `decanter`, `wine_enthusiast`, `winesearcher` - nenhuma linha dessas 4 fontes entrou em `public.wine_scores` no Render nesta sessao.
- **Zero mistura** das 4 fontes acima com a base local do Vivino (`vivino_vinhos`, `vivino_reviews`): dados continuam isolados em `ct_vinhos`, `decanter_vinhos`, `we_vinhos`, `ws_vinhos` (locais ao `winegod_db`).
- **Zero criacao de nota/WCF/score de produto** para essas 4 fontes - nenhum writer novo, nenhum adapter de merge, nenhum campo derivado escrito.
- Observador `dq_v3_observer` continua em `success`.
- Registry `ops.scraper_registry` permanece com 29 entradas, sem mudancas indevidas de `blocked_*` -> `observed` fabricadas.

Baseline de `.env` / `backend/.env` confirmado **somente por lista de chaves** (nunca valores) durante a preflight da sessao anterior.

## 16.8 Git

- Branch: `data-ops/integracao-restantes-scrapers-total-20260423`
- Base: `152cb10b` (HEAD da branch anterior `data-ops/execucao-total-commerce-reviews-routing-20260423`)
- Commits desta sessao:
  - `acf8b91b feat(data-ops): integrate remaining scrapers into central platform` - criacao dos 5 shadows, 5 schedulers e atualizacao do README.
  - `<preenchido apos amend/novo commit>` - adiciona regra explicita "CellarTracker/Decanter/Wine Enthusiast/Wine-Searcher NAO sobem para Render" na matriz e no relatorio + CLAUDE_RESPOSTAS.
- Push remoto: `origin/data-ops/integracao-restantes-scrapers-total-20260423` (apos commit final)
- Diff resumido: 10 arquivos novos (5 shadows + 5 schedulers) + 1 README atualizado + 2 relatorios + 1 CLAUDE_RESPOSTAS.
- Nenhum merge em main, nenhum force push, nenhum deploy Render/Vercel.

## Apendice A - Testes (Phase H)

- `python -m pytest sdk/plugs -q` -> 28 passed
- `python -m pytest sdk/tests sdk/adapters/tests -q` -> 119 passed

Total: 147 passed, 0 failed. Backend pytest nao executado nesta sessao por NAO ter tocado backend nem runtime de ingestao (apenas scripts PowerShell, shadows e relatorios).

## Apendice B - Arquivo a repassar para o Codex admin

```text
C:\winegod-app\reports\WINEGOD_EXECUCAO_TOTAL_RESTANTES_SCRAPERS_PLATAFORMA_2026-04-23.md
```
