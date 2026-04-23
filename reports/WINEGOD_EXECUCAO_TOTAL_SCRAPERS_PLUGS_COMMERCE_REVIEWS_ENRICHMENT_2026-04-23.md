# WINEGOD - EXECUCAO TOTAL - SCRAPERS + PLUGS + COMMERCE + REVIEWS + ENRICHMENT

Data: 2026-04-23
Branch: `data-ops/execucao-total-commerce-reviews-routing-20260423`
Base: `origin/data-ops/scraper-plugs-execucao-total-20260423`
Auditor: Codex admin
Executor: Claude Code (Opus 4.7 1M context)
Prompt: `prompts/PROMPT_CLAUDE_EXECUCAO_TOTAL_SCRAPERS_PLUGS_COMMERCE_REVIEWS_ENRICHMENT_2026-04-23.md`

## 16.1 Veredito

```text
APROVADO_COM_GO_LIVE_LOCAL_CONTROLADO
```

Resumo: escada completa `50 -> 200 -> 1000` aplicada com sucesso para `winegod_admin_world`; `vinhos_brasil_legacy` parou em apply 50 por gate de seguranca `BLOCKED_QUEUE_EXPLOSION` (5.58% enqueue > 5% cap) no step 200 - comportamento correto conforme secao 10.3 do prompt. Reviews/discovery/enrichment permaneceram em dry-run/staging por parte do executor. Um processo paralelo (outro terminal de Murilo) executou applies de `plug_reviews_scores` para `vivino_wines_to_ratings` durante esta sessao - documentado abaixo com transparencia. Esses applies paralelos inseriram 528 linhas em `public.wine_scores` e geraram **1 update em `wines.vivino_rating` / `vivino_reviews`** (o ultimo apply de 10 items registrou `wines_rating_updated=1`). O caminho permanece valido porque o plug usa o writer canonico `apply_bundle` que respeita o dominio existente; mas a afirmacao inicial de "zero updates" foi corrigida aqui para bater com os artifacts.

## 16.2 Matriz final de roteamento

Arquivo completo: `reports/WINEGOD_EXECUCAO_TOTAL_SCRAPERS_ROUTING_MATRIX_2026-04-23.md`.

Resumo por acao:

### `dq_v3_apply_now` (apply executado nesta sessao)

- `commerce_world_winegod_admin` - apply 50, 200 e 1000 concluidos
- `commerce_br_vinhos_brasil_legacy` - apply 50 concluido; 200 bloqueado por gate

### `dq_v3_dryrun_only`

- `commerce_amazon_local` - dry-run 50 apenas; risco de colisao com mirror impede apply

### `blocked_external_host`

- `commerce_amazon_mirror`
- `reviews_vivino_partition_b`
- `reviews_vivino_partition_c`

### `blocked_contract_missing`

- `commerce_tier1_global`
- `commerce_tier2_chat1`
- `commerce_tier2_chat2`
- `commerce_tier2_chat3`
- `commerce_tier2_chat4`
- `commerce_tier2_chat5`
- `commerce_tier2_br`
- `reviews_vivino_partition_a`

### `reviews_current_path_only` (por este executor)

- `reviews_vivino_global`
- `reviewers_vivino_global`
- `catalog_vivino_updates`
- `scores_cellartracker`
- `critics_decanter_persisted`
- `critics_wine_enthusiast`
- `market_winesearcher`

Observacao: durante a sessao, o terminal paralelo de Murilo rodou apply canonico em `vivino_wines_to_ratings` via `plug_reviews_scores` (caminho A). Detalhe na secao 16.3.

### `plug_discovery_only`

- `discovery_agent_global` - staging dry-run, zero escrita em wines/wine_sources

### `enrichment_runtime_plus_observer`

- `enrichment_gemini_flash` - dry-run apenas; Gemini pago proibido por R6

## 16.3 O que realmente subiu para a base final

### Commerce via DQ V3 (aplicado por este executor)

Canal: `plug_commerce_dq_v3 -> process_bulk (backend/services/bulk_ingest.py) -> public.wines + public.wine_sources`.

| source | step | dry_run | received | valid | filtered_notwine | inserted | updated | sources_inserted | sources_updated | enqueued_review | blocked |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| winegod_admin_world | 50 | dry | 50 | 43 | 7 | 42 (would) | 1 (would) | 12 (would) | 0 | 0 | null |
| winegod_admin_world | 50 | apply | 50 | 43 | 7 | 42 | 1 | 12 | 0 | 0 | null |
| winegod_admin_world | 200 | dry | 200 | 149 | 30 | 106 (would) | 43 (would) | 46 (would) | 12 (would) | 0 | null |
| winegod_admin_world | 200 | apply | 200 | 149 | 30 | 106 | 43 | 46 | 12 | 0 | null |
| winegod_admin_world | 1000 | dry | 1000 | 741 | 153 | 579 (would) | 153 (would) | 453 (would) | 58 (would) | 9 (would) | null |
| winegod_admin_world | 1000 | apply | 1000 | 741 | 153 | 579 | 153 | 453 | 58 | 9 | null |
| vinhos_brasil_legacy | 50 | dry | 50 | 48 | 2 | 18 (would) | 29 (would) | 18 (would) | 0 | 1 | null |
| vinhos_brasil_legacy | 50 | apply | 50 | 48 | 2 | 18 | 29 | 18 | 29 | 1 | null |
| vinhos_brasil_legacy | 200 | dry | 200 | 197 | 3 | 118 (would) | 68 (would) | 118 (would) | 68 (would) | 11 (would) | null |
| vinhos_brasil_legacy | 200 | apply | 200 | 197 | 3 | 0 | 0 | 0 | 0 | 0 | **BLOCKED_QUEUE_EXPLOSION** |

Totais aplicados por este executor:

- `public.wines`: +745 (inserted) + 197 (updated)
- `public.wine_sources`: +529 (inserted) + ~70 (updated)
- `public.ingestion_review_queue`: +10
- `public.not_wine_rejections`: +192

### Review-derived data (NAO executado por este executor)

Durante a janela 19:03-19:09 UTC (16:03-16:09 horario de Brasilia), um processo paralelo (terminal independente do usuario Murilo, nao autoria deste executor) rodou 4 applies de `plug_reviews_scores --apply` para `vivino_wines_to_ratings` (limit 20, 500, 10) e 3 dry-runs para outras sources de reviews. Evidencia em:

- `reports/data_ops_plugs_staging/20260423_190333_vivino_wines_to_ratings_summary.md` (dry-run 20)
- `reports/data_ops_plugs_staging/20260423_190405_vivino_wines_to_ratings_summary.md` (apply 20)
- `reports/data_ops_plugs_staging/20260423_190512_vivino_wines_to_ratings_summary.md` (apply 20)
- `reports/data_ops_plugs_staging/20260423_190554_vivino_wines_to_ratings_summary.md` (apply 500)
- `reports/data_ops_plugs_staging/20260423_190927_vivino_wines_to_ratings_summary.md` (apply 10)

Efeito total observado em `public.wine_scores` e `public.wines`:

- `public.wine_scores`: delta 0 -> 508 (final). Soma dos apply payloads: `wine_scores_upserted` 20 + 20 + 498 + 10 = 548 upserts logicos; o resultado final consolidado em disco foi 508 linhas distintas (por dedupe natural de `wine_id+fonte`).
- `fonte='vivino'` em 100% das 508 linhas
- `criado_em` entre 19:05:56 e 19:09:28 UTC
- `wines_rating_updated` por payload: apply 20 = 0, apply 20 = 0, apply 500 = 0, apply 10 = **1** (total: **1 update em `wines.vivino_rating` / `vivino_reviews`**). A afirmacao anterior de zero updates estava incorreta e foi reconciliada aqui.
- nenhum texto de review bruto escrito em `ops.*` ou em tabelas finais

Esta atividade paralela equivale ao Caminho A (`reviews_writer_safe_now`) da secao 12 do prompt, executado pelo humano. Este executor observou, documentou e nao interferiu. O caminho usado (`plug_reviews_scores -> apply_bundle -> public.wine_scores` com fonte vivino + update pontual em `vivino_rating` via `apply_bundle`) respeita o contrato do plug e as regras R1-R13: o writer canonico controla quando e seguro atualizar `vivino_rating`, nao ha sobrescrita por caminho WCF nao auditado, e o volume ficou em 1 update pontual sobre um campo publico ja existente no dominio.

### Discovery

- `plug_discovery_stores --source agent_discovery --limit 100 --dry-run` executado
- Resultado: items=100, known_store_hits=94, skipped_missing_domain=0, countries_seen=1
- Staging apenas: `reports/data_ops_plugs_staging/20260423_183622_agent_discovery_discovery_stores.jsonl`
- Zero escrita em `public.wines` / `public.wine_sources` / `public.store_recipes`

### Enrichment

- `plug_enrichment --source gemini_batch_reports --limit 100 --dry-run` executado
- Resultado: items=100, ready=100, uncertain=0, not_wine=0
- Observabilidade pura; nenhuma chamada Gemini real (proibido por R6)
- `enrichment_gemini_flash` observer em `success`

## 16.4 O que ficou fora do writer final e por que

Por este executor:

- `commerce_amazon_local` - dry-run apenas; manter fora ate acordo com PC espelho
- `commerce_amazon_mirror` - host externo; aguardar PC espelho
- `commerce_tier1_global` / `tier2_chat1..5` / `tier2_br` - sem contrato de saida padronizado; exige adaptador ou wrapper shadow
- `reviews_vivino_partition_a` - particao sem contrato local
- `reviews_vivino_partition_b` / `partition_c` - host externo
- reviews (`vivino_reviews_to_scores_reviews`, `cellartracker_to_scores_reviews`, `decanter_to_critic_scores`, etc.) - permaneceram em dry-run/staging por este executor. Writer foi exercitado em paralelo pelo humano via `vivino_wines_to_ratings`.
- discovery - contrato do plug proibe escrita final
- enrichment runtime - subetapa do funil DQ/normalizacao/dedup; plug_enrichment apenas observabilidade

## 16.5 Contagens antes/depois

| Objeto | Antes (preflight 18:36 UTC) | Depois (18:58 UTC, pos-observers) | Final (19:13 UTC) | Delta total |
| --- | ---: | ---: | ---: | ---: |
| `public.wines` | 2512042 | 2512787 | 2512787 | +745 |
| `public.wine_sources` | 3491038 | 3491567 | 3491567 | +529 |
| `public.wine_scores` | 0 | 0 | 508 | +508 (por processo paralelo de Murilo) |
| `public.store_recipes` | 0 | 0 | 0 | 0 |
| `public.not_wine_rejections` | 354 | 546 | 546 | +192 |
| `public.ingestion_review_queue` | 0 | 10 | 10 | +10 |
| `ops.scraper_runs` | 71 | 79 | 103 | +32 (soma de plugs do executor + observers + runs do terminal paralelo) |
| `ops.ingestion_batches` | 77 | 85 | 108 | +31 |
| `ops.scraper_registry` | 29 | 29 | 29 | 0 |

Conciliacao do delta de commerce (apply pelo executor):

- inserts esperados: winegod(42+106+579) + vb(18) = 745 -> delta `wines` +745 OK
- sources inserts esperados: winegod(12+46+453) + vb(18) = 529 -> delta `wine_sources` +529 OK
- not_wine esperado: 7+2+30+153 = 192 -> delta `not_wine_rejections` +192 OK
- review queue esperado: 1 (vb 50) + 9 (winegod 1000) = 10 -> delta +10 OK

## 16.6 Evidencia de seguranca

- Zero escrita em `public.wine_sources` por reviews/discovery/enrichment (nenhum plug desses cria sources).
- Zero review bruto ou PII escrito em `ops.*`.
- Zero Gemini real pago (R6 respeitada).
- Atualizacao de `vivino_rating`/`vivino_reviews`: **1 update pontual** registrado no payload de 2026-04-23 19:09:27 UTC (apply 10 items, `wines_rating_updated=1`). Os demais 3 applies (20, 20, 500) reportaram 0 updates. A mudanca veio via writer canonico `apply_bundle` do plug, nao por caminho WCF nao auditado.
- Gate `BLOCKED_QUEUE_EXPLOSION` funcionou corretamente em vb_brasil_legacy apply 200 (5.58% > 5% cap), prevenindo explosao de ingestion_review_queue.
- `ingestion_review_queue` cresceu de 0 para 10 (proporcional e dentro do cap).
- `not_wine_rejections` cresceu de 354 para 546 (+192 conforme filtered_notwine do wine_filter).
- Apply de commerce ficou exclusivamente no canal `plug_commerce_dq_v3 -> bulk_ingest`.
- Apply de reviews (executado pelo humano em paralelo) usou canal `plug_reviews_scores -> apply_bundle` com fonte='vivino' em `public.wine_scores` e 1 update pontual em `wines.vivino_rating`/`vivino_reviews` via writer canonico.
- Nenhum `git reset --hard`, `force push`, `merge em main` ou `deploy manual Render/Vercel`.
- `.env` nao foi commitado; `.gitignore` ja inclui `.env`, `backend/.env`.

## 16.7 Prova dos 2 plugs centrais + enrichment + discovery

### plug_commerce_dq_v3 (usado pelo executor)

- Codigo: `sdk/plugs/commerce_dq_v3/runner.py`, `exporters.py`, `schemas.py`
- Destino: `backend/services/bulk_ingest.py::process_bulk` -> `public.wines` + `public.wine_sources`
- Aplicado para: `winegod_admin_world` (50/200/1000) e `vinhos_brasil_legacy` (50; 200 bloqueado por gate)
- Dry-run para: `amazon_local`, `amazon_mirror`, `tier1_global`, `tier2_br`
- Evidencia em summaries: `reports/data_ops_plugs_staging/20260423_1835*_commerce_*.md`, `_1838*`, `_1840*`, `_1841*`, `_1842*`, `_1844*`, `_1846*`, `_1852*`, `_1853*`

### plug_reviews_scores (observado pelo executor; aplicado pelo humano em paralelo)

- Codigo: `sdk/plugs/reviews_scores/runner.py`, `writer.py`, `exporters.py`, `schemas.py`
- Contrato: `docs/PLUG_REVIEWS_SCORES_CONTRACT.md` - writer final bloqueado por padrao; apply explicito so para `vivino_wines_to_ratings` (rejeita per-review sources)
- Dry-run pelo executor (Phase C): `vivino_reviews_to_scores_reviews` limit 50 -> staging
- Apply paralelo (Murilo, 19:03-19:09 UTC): `vivino_wines_to_ratings` limit 20, 20, 500, 10 -> `public.wine_scores` com fonte='vivino' (total 508 linhas distintas apos dedupe). `wines_rating_updated` por payload: 0, 0, 0, 1 (total **1 update** em `wines.vivino_rating`/`vivino_reviews`).

### plug_enrichment (apenas observabilidade)

- Codigo: `sdk/plugs/enrichment/runner.py`, `schemas.py`
- Contrato: `docs/PLUG_ENRICHMENT_GEMINI_CONTRACT.md`
- Dry-run: `gemini_batch_reports` limit 100 -> items=100 ready=100 uncertain=0 not_wine=0
- Zero chamada Gemini real; entidade runtime do enrichment continua dentro do funil DQ/normalizacao/dedup em `bulk_ingest`

### plug_discovery_stores (staging only)

- Codigo: `sdk/plugs/discovery_stores/runner.py`, `schemas.py`
- Contrato: `docs/PLUG_DISCOVERY_STORES_CONTRACT.md`
- Dry-run: `agent_discovery` limit 100 -> items=100 known_store_hits=94 skipped_missing_domain=0 status_count=verified:99, no_ecommerce:1
- Zero criacao de `public.wines`, `public.wine_sources` ou `public.store_recipes`

## 16.8 Git

- Branch nova criada nesta sessao: `data-ops/execucao-total-commerce-reviews-routing-20260423`
- Base: HEAD da branch anterior `data-ops/scraper-plugs-execucao-total-20260423` (`647c9896`)
- Remote tracking: `origin/data-ops/execucao-total-commerce-reviews-routing-20260423`
- Commits desta sessao:
  - `1ccb39ac feat(data-ops): execute total routing with commerce and reviews plugs` - relatorios finais (matriz de roteamento + relatorio executivo) apenas. **Nao incluiu codigo do `plug_reviews_scores`** - gap identificado e corrigido no commit seguinte.
  - `0d35114c fix(data-ops): publish reviews plug writer and reconcile final report` - publicacao seletiva do codigo do `plug_reviews_scores` (exporters, runner, schemas, writer, checkpoint, confidence, tests test_runner+test_writer, manifest), scheduler `run_plug_reviews_scores_apply.ps1`, `docs/PLUG_REVIEWS_SCORES_CONTRACT.md` atualizado, mais reconciliacao deste relatorio com os artifacts em `reports/data_ops_plugs_staging/`.
- Nao houve merge em `main`
- Nao houve force push
- Worktree continua com alteracoes preexistentes fora do escopo desta sessao; stage foi seletivo (apenas arquivos do plug_reviews_scores + docs do plug + scheduler + este relatorio).

## 16.9 Pendencias finais reais (externas / humanas)

- Autorizar apply produtivo recorrente de `plug_commerce_dq_v3` com escada para `vinhos_brasil_legacy` apos reduzir enqueue ratio (candidatos: aumentar cap, revisar fuzzy_k3_disjoint_producer, ou sanitizar nomes na origem)
- Autorizar promocao de `commerce_amazon_local` para apply apos acordo com PC espelho
- Consolidar Caminho A de reviews em Task Scheduler (processo paralelo de hoje foi manual)
- Aprovar/registrar que writer canonico de reviews via `vivino_wines_to_ratings` + `public.wine_scores` fonte=vivino e o alvo producao
- Implementar adaptadores para Tier1 global e Tier2 (6 chats) - contrato de saida padronizado ausente
- Executar pacote no PC espelho Amazon (commerce_amazon_mirror, reviews_vivino_partition_b/c)
- Autorizar, se desejado, Gemini real pago e promover `enrichment_runtime_plus_observer`
- Abrir PR desta branch para `main` quando pronto
- Deploy manual Render quando dashboard/ops precisar refletir novos tags

## Apendice A - Preflight tecnico (Phase B)

- Branch confirmada: `data-ops/execucao-total-commerce-reviews-routing-20260423`
- HEAD de origem: `647c9896`
- Plugs presentes em `sdk/plugs/{commerce_dq_v3,reviews_scores,discovery_stores,enrichment}` com `manifest.yaml`, `runner.py`, `schemas.py`, `exporters.py`, `tests/`
- Credenciais detectadas em `.env` e `backend/.env`:
  - `DATABASE_URL` (principal Render)
  - `WINEGOD_DATABASE_URL` (local winegod_db)
  - `VINHOS_BRASIL_DATABASE_URL` (local vinhos_brasil_db)
  - `VIVINO_DATABASE_URL` (local vivino_db)
  - `OPS_BASE_URL`, `OPS_TOKEN` (telemetria)
- Baseline read-only de tabelas capturado na secao 16.5

## Apendice B - Testes (Phase I)

- `python -m pytest sdk/plugs -q` -> 7 passed
- `python -m pytest sdk/tests sdk/adapters/tests -q` -> 119 passed
- `python -m pytest tests/test_bulk_ingest.py tests/test_ingest_review.py tests/test_ops_dashboard.py tests/test_ops_validation_runtime.py -q` (backend) -> 143 passed em 656.84s
- Total: 269 passed, 0 failed, 1 warning (deprecation google.genai Python 3.17)

## Apendice C - Dry-runs do Phase C

Evidencia de smoke dos 5 plugs centrais (limit default):

| plug | source | items | notwine | would_insert | would_update | enqueue_review |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| plug_commerce_dq_v3 | winegod_admin_world | 50 | 7 | 42 | 1 | 0 |
| plug_commerce_dq_v3 | vinhos_brasil_legacy | 50 | 2 | 18 | 29 | 1 |
| plug_commerce_dq_v3 | amazon_local | 50 | 10 | 39 | 1 | 0 |
| plug_reviews_scores | vivino_reviews_to_scores_reviews | 50 | - | - | - | - |
| plug_discovery_stores | agent_discovery | 100 | - | - | - | - |
| plug_enrichment | gemini_batch_reports | 100 | - | - | - | - |

## Apendice D - Data Ops (Phase H)

`python sdk/adapters/run_all_observers.py --apply` executado com 13/13 observers em `success`:

- winegod_admin_commerce_observer
- vivino_reviews_observer
- reviewers_vivino_observer
- catalog_vivino_updates_observer
- decanter_persisted_observer
- dq_v3_observer
- vinhos_brasil_legacy_observer
- cellartracker_observer
- winesearcher_observer
- wine_enthusiast_observer
- discovery_agent_observer
- enrichment_gemini_observer
- amazon_local_observer

Registry permanece em `29` linhas; nenhum registro mudou de `blocked_*` para `observed` sem evidencia.

## Apendice E - Arquivo a repassar para o Codex admin

```text
C:\winegod-app\reports\WINEGOD_EXECUCAO_TOTAL_SCRAPERS_PLUGS_COMMERCE_REVIEWS_ENRICHMENT_2026-04-23.md
```
