# WINEGOD - EXECUCAO TOTAL - MATRIZ DE ROTEAMENTO DE SCRAPERS

Data: 2026-04-23
Branch: `data-ops/execucao-total-commerce-reviews-routing-20260423`
Escopo: classificacao final de TODOS os scrapers do inventario + destino correto + acao desta execucao.
Base de referencia: `WINEGOD_SCRAPERS_INVENTARIO_HANDOFF.md`, `WINEGOD_CONTROL_PLANE_SCRAPERS_PLUGS_EXECUCAO_TOTAL_2026-04-23.md`, `sdk/plugs/commerce_dq_v3/exporters.py`, `sdk/plugs/reviews_scores/runner.py`, `sdk/plugs/discovery_stores/runner.py`, `sdk/plugs/enrichment/runner.py`.

## Legenda de `acao_nesta_execucao`

- `dq_v3_apply_now` - plug_commerce_dq_v3 em apply controlado (escada 50->200->1000)
- `dq_v3_dryrun_only` - plug_commerce_dq_v3 em dry-run; sem apply nesta sessao
- `reviews_current_path_only` - plug_reviews_scores em staging/telemetria; sem writer final nesta sessao
- `reviews_writer_safe_now` - existe writer canonico seguro e ele roda nesta sessao
- `plug_discovery_only` - plug_discovery_stores em staging; nao cria wine/wine_source
- `enrichment_runtime_plus_observer` - subetapa do funil DQ; plug_enrichment apenas observabilidade
- `blocked_external_host` - depende de outra maquina/PC espelho
- `blocked_contract_missing` - contrato/saida padronizada ausente
- `observer_only` - observer ja existe, apenas refresh

## Matriz final

| scraper_id | family | origem_local_ou_host | contrato_atual | destino_correto | acao_nesta_execucao | evidencia |
| --- | --- | --- | --- | --- | --- | --- |
| commerce_world_winegod_admin | commerce | este_pc (winegod_db local) | vinhos_* + vinhos_*_fontes | plug_commerce_dq_v3 -> bulk_ingest -> public.wines + public.wine_sources | `dq_v3_apply_now` | `sdk/plugs/commerce_dq_v3/exporters.py::export_winegod_admin_world_to_dq`; smoke dry-run existente em `reports/data_ops_plugs_staging/20260423_152138_commerce_winegod_admin_world_summary.md` (received=50 valid=43 filtered_notwine=7 would_insert=42 would_update=1) |
| commerce_br_vinhos_brasil_legacy | commerce | este_pc (vinhos_brasil_db) | vinhos_brasil + vinhos_brasil_fontes via `scripts/export_vinhos_brasil_to_router.py` | plug_commerce_dq_v3 -> bulk_ingest -> public.wines + public.wine_sources | `dq_v3_apply_now` | `sdk/plugs/commerce_dq_v3/exporters.py::export_vinhos_brasil_legacy_to_dq`; smoke dry-run em `reports/data_ops_plugs_staging/20260423_152150_commerce_vinhos_brasil_legacy_summary.md` (received=50 valid=48 filtered_notwine=2 would_insert=18 would_update=29 would_enqueue_review=1) |
| commerce_amazon_local | commerce | este_pc (winegod_db local com fonte amazon) | vinhos_*_fontes filtrando fonte amazon | plug_commerce_dq_v3 (mesmo canal) | `dq_v3_dryrun_only` | `sdk/plugs/commerce_dq_v3/exporters.py::export_amazon_local_to_dq`; smoke dry-run em `reports/data_ops_plugs_staging/20260423_152210_commerce_amazon_local_summary.md` (received=50 valid=40 filtered_notwine=10 would_insert=39 would_update=1); risco de colisao com mirror amazon impede apply nesta sessao |
| commerce_amazon_mirror | commerce | PC espelho (externo) | sem integracao local | plug_commerce_dq_v3 via wrapper shadow | `blocked_external_host` | `sdk/plugs/commerce_dq_v3/exporters.py::export_amazon_mirror_to_dq_stub` retorna `blocked_external_host`; wrapper `scripts/data_ops_shadow/run_commerce_amazon_mirror_shadow.ps1` |
| commerce_tier1_global | commerce | natura-automation/winegod_admin (APIs globais, este PC) | escrita direta em `winegod_db` sem adaptador | plug_commerce_dq_v3 (precisa adaptador) | `blocked_contract_missing` | Inventario 1.2; exporter stub `export_tier1_global_to_dq_stub` marca `blocked_contract_missing` |
| commerce_tier2_chat1 | commerce | chats Codex paralelos | saida por chat, sem artefato local padronizado | plug_commerce_dq_v3 (precisa contrato de saida) | `blocked_contract_missing` | `export_tier2_to_dq_stub` marca todos os chats; wrapper shadow disponivel |
| commerce_tier2_chat2 | commerce | chats Codex paralelos | idem | plug_commerce_dq_v3 | `blocked_contract_missing` | idem |
| commerce_tier2_chat3 | commerce | chats Codex paralelos | idem | plug_commerce_dq_v3 | `blocked_contract_missing` | idem |
| commerce_tier2_chat4 | commerce | chats Codex paralelos | idem | plug_commerce_dq_v3 | `blocked_contract_missing` | idem |
| commerce_tier2_chat5 | commerce | chats Codex paralelos | idem | plug_commerce_dq_v3 | `blocked_contract_missing` | idem |
| commerce_tier2_br | commerce | chats Codex paralelos (BR) | idem | plug_commerce_dq_v3 | `blocked_contract_missing` | idem |
| reviews_vivino_global | review | este_pc (vivino_db local) | staging ja coberto por `sdk/plugs/reviews_scores` | plug_reviews_scores (staging + telemetria) | `reviews_current_path_only` | smoke em `reports/data_ops_plugs_staging/20260423_152328_vivino_reviews_to_scores_reviews_summary.md` (source=vivino_reviews_to_scores_reviews items=50); sem writer final canonico aprovado nesta sessao |
| reviews_vivino_partition_a | review | este_pc (particao A) | adaptador de particao ausente | plug_reviews_scores | `blocked_contract_missing` | handoff `2026-04-17_handoff_re_scrape_reviews_vivino.md` lista 3-way partition; particao A precisa contrato local |
| reviews_vivino_partition_b | review | PC espelho (externo) | sem integracao local | plug_reviews_scores via shadow | `blocked_external_host` | wrapper `scripts/data_ops_shadow/run_reviews_vivino_partition_b_shadow.ps1` |
| reviews_vivino_partition_c | review | WAB (externo) | sem integracao local | plug_reviews_scores via shadow | `blocked_external_host` | wrapper `scripts/data_ops_shadow/run_reviews_vivino_partition_c_shadow.ps1` |
| reviewers_vivino_global | review | este_pc (reviewers vivino) | observer registrado | plug_reviews_scores (observer/apoio) | `reviews_current_path_only` | registry ja `observed`; nao promover a writer nesta sessao |
| catalog_vivino_updates | review | este_pc (catalog vivino) | observer registrado | plug_reviews_scores (observer) | `reviews_current_path_only` | registry ja `observed`; nao promover a writer nesta sessao |
| scores_cellartracker | review | este_pc (ct_vinhos) | plug de staging ja cobre | plug_reviews_scores | `reviews_current_path_only` | manifest registra `registry_status: observed` |
| critics_decanter_persisted | review | este_pc (decanter_vinhos) | plug de staging ja cobre | plug_reviews_scores | `reviews_current_path_only` | manifest registra `registry_status: observed` |
| critics_wine_enthusiast | review | este_pc (we_vinhos) | plug de staging ja cobre | plug_reviews_scores | `reviews_current_path_only` | manifest registra `registry_status: observed` |
| market_winesearcher | review | este_pc (ws_vinhos) | plug de staging ja cobre | plug_reviews_scores | `reviews_current_path_only` | manifest registra `registry_status: observed` |
| discovery_agent_global | discovery | este_pc (agent_discovery artefatos) | plug de staging ja cobre | plug_discovery_stores | `plug_discovery_only` | smoke em `reports/data_ops_plugs_staging/20260423_152358_agent_discovery_discovery_stores_summary.md` (items=100 known_store_hits=94) |
| enrichment_gemini_flash | enrichment | artefatos `reports/gemini_batch_*` + `ingest_pipeline_enriched` | plug de staging ja cobre em observabilidade | enrichment de negocio e SUBETAPA do funil DQ/normalizacao/dedup; plug_enrichment apenas observer | `enrichment_runtime_plus_observer` | smoke em `reports/data_ops_plugs_staging/20260423_152407_gemini_batch_reports_enrichment_summary.md` (items=100 ready=100); proibido Gemini real pago nesta sessao |

## Justificativa das decisoes de apply

### Por que `dq_v3_apply_now` apenas para `winegod_admin_world` e `vinhos_brasil_legacy`

- Ambos possuem adaptador canonico implementado e smoke dry-run validado.
- Dados locais no `winegod_db` e `vinhos_brasil_db` permitem leitura read-only e reproducao.
- O canal `plug_commerce_dq_v3 -> bulk_ingest -> public.wines + public.wine_sources` e o unico aprovado nesta arquitetura.

### Por que `amazon_local` fica em `dq_v3_dryrun_only`

- Existe risco de colisao/duplicacao com o PC espelho Amazon (`commerce_amazon_mirror`) que ja coletou 587K vinhos e nao esta integrado.
- Promover apply agora poderia criar `wine_sources` que seriam refeitos pelo writer do espelho depois.
- Decisao conservadora: manter dry-run, deixar apply para depois do acordo com o PC espelho.

### Por que nenhum commerce Tier1/Tier2/mirror tem apply

- Contrato de saida padronizado ausente (Tier1/Tier2) ou host externo sem integracao local (mirror).
- O caminho correto e criar adaptador ou wrapper shadow antes de promover.

### Por que reviews permanecem em `reviews_current_path_only`

- O contrato `PLUG_REVIEWS_SCORES_CONTRACT.md` explicitamente mantem o plug em staging-only nesta sessao ("Final writes stay blocked until a dedicated target table or service is explicitly approved").
- Nao ha writer canonico aprovado neste repo para review-derived data (procurei por tabelas `wine_reviews`, `wine_scores` writers finais, nada esta pronto para escrever campos derivados com seguranca).
- `vivino_rating` e `vivino_reviews` ja vivem no dominio e NUNCA podem ser sobrescritos pelo caminho WCF.
- Caminho B (staging only) confirmado.

### Por que discovery nao cria vinho

- Discovery entrega lojas/recipes candidatos; o dominio `public.wines`/`public.wine_sources` e fechado a commerce via DQ V3.

### Por que enrichment fica observer-only

- Regra arquitetural: enrichment de negocio real roda dentro do funil DQ/normalizacao/dedup em runtime; `plug_enrichment` apenas observa staging.
- Gemini pago proibido nesta sessao por CLAUDE.md R6.
