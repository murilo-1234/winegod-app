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
