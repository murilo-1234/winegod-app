# Data Ops Scheduler

These scripts prepare the control plane cadence without installing a Windows scheduled task automatically.

## Scripts

- `run_all_observers.ps1` - registry sync + observers
- `run_all_plug_dryruns.ps1` - dry-run completo de todos os plugs (default CI-friendly)
- `run_all_shadows.ps1` - wrapper validation de TODOS os shadows; `-Live` para modo vivo
- `run_commerce_dryruns.ps1` - dry-run dedicado commerce local (winegod_admin_world, vinhos_brasil_legacy, amazon_local)
- `run_reviews_scores_dryruns.ps1` - dry-run dedicado reviews nao-vivino_wines_to_ratings (vivino_reviews, cellartracker, decanter, wine_enthusiast, winesearcher)
- `run_discovery_stores_dryruns.ps1` - dry-run dedicado discovery (agent_discovery)
- `run_enrichment_dryruns.ps1` - dry-run dedicado enrichment (gemini_batch_reports; sem Gemini pago)
- `run_plug_reviews_scores_apply.ps1` - apply canonico de vivino_wines_to_ratings (incremental_recent | backfill_windowed)
- `run_vivino_reviews_backfill.ps1` / `run_vivino_reviews_incremental.ps1` - wrappers instalados no Windows Task Scheduler para o canal Vivino (S4U)
- `install_vivino_reviews_tasks.ps1` - instalador idempotente das duas tasks + `-CheckBackfillDone` para desabilitar o backfill quando a sentinela aparecer
- `status_vivino_reviews_tasks.ps1` - inspecao rapida de LastTaskResult + NextRun + checkpoint
- `run_vivino_reviews_health_check.ps1` - health check observacional (read-only) do dominio reviews; exit `0` ok, `2` warning, `3` failed
- `run_commerce_artifact_dryruns.ps1` - dry-run das fontes commerce canonicas por artefato padronizado: `amazon_mirror_primary`, `tier1_global`, `tier2_global_artifact` (Tier2 UNICO, substitui os extintos chats 1..5), `tier2_br` (Tier2 filtrado por pais real). Sem artefato = `blocked_contract_missing` honesto.

## Artefatos padronizados de commerce

Contrato: `docs/TIER_COMMERCE_CONTRACT.md`.

Diretorios esperados:

```
reports/data_ops_artifacts/amazon_mirror/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier1/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier2_global/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier2/br/<timestamp>_<run_id>.jsonl
```

O diretorio `tier2_global/` substituiu os extintos `tier2/chat1..5/` (colapsados
por falta de particao disjunta reproduzivel). `tier2/br/` continua separado
porque tem filtro real por pais.

Variaveis opcionais: `AMAZON_MIRROR_ARTIFACT_DIR`, `TIER1_ARTIFACT_DIR`, `TIER2_ARTIFACT_DIR`.

## Behavior

- Uses local Python from `PATH`
- Keeps logs in `reports/data_ops_scheduler/`
- Avoids productive apply by default for plugs
- `run_all_observers.ps1` syncs registry before running observers unless `-SkipRegistrySync` is passed

## Example

```powershell
powershell -File scripts/data_ops_scheduler/run_all_observers.ps1
powershell -File scripts/data_ops_scheduler/run_all_plug_dryruns.ps1
```

## Shadow wrappers

Shadow wrappers live in `scripts/data_ops_shadow/`.

- Default execution is wrapper validation only
- Add `-Live` only after reviewing the target command, scope, cost, and host prerequisites
