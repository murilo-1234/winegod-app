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
- `run_commerce_artifact_dryruns.ps1` - dry-run das fontes commerce canonicas por artefato padronizado: `amazon_mirror_primary`, `tier1_global`, `tier2_global_artifact` (Tier2 UNICO, substitui os extintos chats 1..5), `tier2_br` (Tier2 filtrado por pais real). Sem artefato = `blocked_contract_missing` honesto.
- `run_vivino_reviews_backfill.ps1` / `run_vivino_reviews_incremental.ps1` - wrappers S4U para o canal Vivino
- `install_vivino_reviews_tasks.ps1` - instalador idempotente das duas tasks + `-CheckBackfillDone`
- `status_vivino_reviews_tasks.ps1` - inspecao LastTaskResult + NextRun + checkpoint
- `run_vivino_reviews_health_check.ps1` - health do dominio reviews (read-only; exit 0/2/3)
- `run_discovery_stores_health_check.ps1` - health do dominio discovery (read-only; exit 0/2/3)
- `run_enrichment_health_check.ps1` - health do dominio enrichment (read-only; exit 0/2/3)

## Health checks rapidos por dominio

```
reviews     -> sdk.plugs.reviews_scores.health        (ok/ok_backfill_done/warning/failed)
discovery   -> sdk.plugs.discovery_stores.health      (ok/warning/failed)
enrichment  -> sdk.plugs.enrichment.health            (ok/warning/failed)
```

Todos usam apenas artifacts locais; nao conectam banco nem chamam APIs externas.

## Artefatos padronizados de commerce

Contrato: `docs/TIER_COMMERCE_CONTRACT.md`.

Diretorios esperados:

```
reports/data_ops_artifacts/amazon_mirror/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier1/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier2_global/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier2/br/<timestamp>_<run_id>.jsonl
```

`tier2_global/` substituiu os extintos `tier2/chat1..5/` (colapsados em
`tier2_global_artifact` por falta de particao disjunta reproduzivel).
`tier2/br/` permanece separado porque tem filtro real por pais.

Variaveis opcionais: `AMAZON_MIRROR_ARTIFACT_DIR`, `TIER1_ARTIFACT_DIR`,
`TIER2_ARTIFACT_DIR` (aplica tanto a `tier2_global/` quanto a `tier2/<pais>/`).

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
