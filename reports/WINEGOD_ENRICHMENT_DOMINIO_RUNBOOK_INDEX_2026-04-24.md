# WINEGOD - Enrichment - Runbook Index

Data: 2026-04-24
Tipo: indice de navegacao do dominio enrichment
Status: ATIVO

## 1. Objetivo

Indice unico dos artefatos do dominio enrichment. Ajuda jobs futuros a
encontrar estado/contrato/operacao sem vasculhar o repo.

## 2. Contrato e escopo

- [docs/PLUG_ENRICHMENT_GEMINI_CONTRACT.md](../docs/PLUG_ENRICHMENT_GEMINI_CONTRACT.md)
  contrato oficial do `plug_enrichment` (scope, minimal record, safety,
  health check, automation, safety test net)
- `sdk/plugs/enrichment/manifest.yaml` - manifest do plug

Fronteira semantica:

```
enrichment = staging/telemetria/observabilidade do loop de duvidosos
enrichment != writer final em tabelas de negocio
```

## 3. Codigo

- `sdk/plugs/enrichment/runner.py` - CLI; reject explicito de --apply
- `sdk/plugs/enrichment/exporters.py` - `export_gemini_batch_reports`
  consome artifacts locais (state json, input/output jsonl, diretorio
  `ingest_pipeline_enriched`) e opcionalmente faz contagens read-only
  em `flash_*` quando disponivel
- `sdk/plugs/enrichment/schemas.py` - `EnrichmentStageRecord`,
  `ExportBundle` com estados `observed | registered_planned |
  blocked_external_host | blocked_missing_source | blocked_contract_missing`
- `sdk/plugs/enrichment/health.py` - snapshot read-only com exit 0/2/3

## 4. Operacao

- `scripts/data_ops_scheduler/run_enrichment_dryruns.ps1` - dry-run
  canonico de `gemini_batch_reports` (nao chama Gemini)
- `scripts/data_ops_scheduler/run_enrichment_health_check.ps1` - health
  snapshot read-only
- `sdk/adapters/enrichment_gemini_observer.py` + manifest
  `sdk/adapters/manifests/enrichment_gemini_flash.yaml` - observer
  READ-ONLY que alimenta `ops.*` com telemetria

## 5. Artifacts

Artefatos locais em `reports/`:

- `gemini_batch_state.json` - estado do batch pipeline
- `gemini_batch_input.jsonl` - input do batch
- `gemini_batch_output.jsonl` - output do batch
- `ingest_pipeline_enriched/**/*.jsonl|csv` - classificados
  (`enriched_ready.jsonl`, `enriched_uncertain_review.csv`,
  `enriched_not_wine.jsonl`)
- Staging: `reports/data_ops_plugs_staging/<ts>_gemini_batch_reports_enrichment.jsonl`
  + `<ts>_gemini_batch_reports_enrichment_summary.md`
- Logs scheduler: `reports/data_ops_scheduler/<ts>_enrichment_dryrun_gemini_batch_reports.log`

Tabelas persisted apenas em read-only (se existirem):

- `public.flash_vinhos`
- `public.flash_queries`

## 6. Testes

Local: `C:\winegod-app\sdk\plugs\enrichment\tests\`

- `test_exporters.py` - ready/uncertain record minimo
- `test_health.py` - artifacts ausentes -> failed, state blocked ->
  warning, summary stale -> warning, enriched_root reconhecido,
  render MD
- `test_manifests_coverage.py` - plug e dono, tag `plug:enrichment`,
  nenhum declara tabela final, flags de seguranca travadas

Global: `python -m pytest sdk/plugs/enrichment -q`

## 7. Health check

```powershell
.\scripts\data_ops_scheduler\run_enrichment_health_check.ps1 -Format md
```

Saida classificada em:

- `ok` - pelo menos 1 artifact presente, summary recente, state=observed
- `warning` - summary velho, state nao-observed, ou summary ausente
- `failed` - zero artifacts locais (pipeline nunca rodou)

## 8. O que enrichment nao faz nesta fase

- nao chama Gemini/Flash ao vivo (R6 CLAUDE.md)
- nao escreve em `public.wines`, `public.wine_sources`, `public.stores`
- nao vira canal de publicacao
- nao criar writer final sem contrato explicito

## 9. Veredito

```
dominio_enrichment = STAGING_ONLY_POR_CONTRATO
writer_final = NAO_EXISTE_NESTA_FASE
chamada_paga = NAO_EXECUTADA_POR_DECISAO
proxima_fase = REENTRADA_NO_LOOP_DE_NORMALIZACAO_DEDUP_DQ
```
