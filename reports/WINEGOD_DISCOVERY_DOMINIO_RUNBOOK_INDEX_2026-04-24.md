# WINEGOD - Discovery - Runbook Index

Data: 2026-04-24
Tipo: indice de navegacao do dominio discovery
Status: ATIVO

## 1. Objetivo

Indice unico dos artefatos do dominio discovery hoje. Ajuda jobs futuros a
achar estado/contrato/operacao sem abrir caca ao tesouro no repo.

## 2. Contrato e escopo

- [docs/PLUG_DISCOVERY_STORES_CONTRACT.md](../docs/PLUG_DISCOVERY_STORES_CONTRACT.md)
  contrato oficial do `plug_discovery_stores` (scope, minimal record,
  safety rules, health check, automation, safety test net)
- `sdk/plugs/discovery_stores/manifest.yaml` - manifest do plug

Fronteira semantica:

```
discovery = staging/telemetria/lineage de lojas e recipes candidatas
discovery != writer de wines / wine_sources / stores / store_recipes
```

## 3. Codigo

- `sdk/plugs/discovery_stores/runner.py` - CLI; reject explicito do --apply
- `sdk/plugs/discovery_stores/exporters.py` - `export_agent_discovery`
  (le `C:\natura-automation\ecommerces_vinhos_*_v2.json` e
  `agent_discovery/discovery_phases.json`)
- `sdk/plugs/discovery_stores/schemas.py` - `DiscoveryStoreRecord`,
  `ExportBundle` com estados `observed | registered_planned |
  blocked_external_host | blocked_missing_source | blocked_contract_missing`
- `sdk/plugs/discovery_stores/health.py` - snapshot read-only
  (artifacts + summary + log + status) com exit 0/2/3

## 4. Operacao

- `scripts/data_ops_scheduler/run_discovery_stores_dryruns.ps1` -
  dry-run canonico de `agent_discovery`
- `scripts/data_ops_scheduler/run_discovery_stores_health_check.ps1` -
  health snapshot read-only
- `sdk/adapters/discovery_agent_observer.py` + manifest
  `sdk/adapters/manifests/discovery_agent_global.yaml` - observer
  READ-ONLY que alimenta `ops.*` com telemetria

## 5. Staging e artifacts

- Staging: `reports/data_ops_plugs_staging/<ts>_agent_discovery_discovery_stores.jsonl`
  + `<ts>_agent_discovery_discovery_stores_summary.md`
- Logs do scheduler: `reports/data_ops_scheduler/<ts>_discovery_dryrun_agent_discovery.log`
- Origem: `C:\natura-automation\ecommerces_vinhos_*_v2.json` +
  `C:\natura-automation\agent_discovery\discovery_phases.json`

## 6. Testes

Local: `C:\winegod-app\sdk\plugs\discovery_stores\tests\`

- `test_exporters.py` - inferencia de recipe_candidate + validation_status
- `test_health.py` - artifacts ausentes -> failed; ok; summary stale ->
  warning; summary state nao-observed -> warning; exit code mapping;
  render MD
- `test_manifests_coverage.py` - plug e dono, manifests linkam via tag,
  nenhum declara tabela final, flags de seguranca travadas

Global: `python -m pytest sdk/plugs/discovery_stores -q`

## 7. Health check

```powershell
.\scripts\data_ops_scheduler\run_discovery_stores_health_check.ps1 -Format md
```

Saida classificada em:

- `ok` - artifacts presentes, summary recente, state=observed
- `warning` - summary velho, state nao-observed, ou `discovery_phases.json`
  ausente
- `failed` - natura-automation nao acessivel ou sem arquivos de origem

## 8. O que discovery nao faz nesta fase

- nao cria `public.wines`
- nao cria `public.wine_sources`
- nao cria `public.stores` finais
- nao cria `public.store_recipes` finais
- `recipe_candidate` e hint/staging apenas
- nao usa DQ V3 (dominio proprio)

## 9. Veredito

```
dominio_discovery = STAGING_ONLY_POR_CONTRATO
writer_final = NAO_EXISTE_NESTA_FASE
drift_para_tabelas_finais = BLOQUEADO_POR_TESTE
proxima_fase = DEFINIR_CONTRATO_DE_STORES_E_STORE_RECIPES
```
