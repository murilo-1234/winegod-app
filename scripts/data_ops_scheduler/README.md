# Data Ops Scheduler

These scripts prepare the control plane cadence without installing a Windows scheduled task automatically.

## Scripts

- `run_all_observers.ps1` - registry sync + observers
- `run_all_plug_dryruns.ps1` - dry-run dos caminhos canonicos: commerce + reviews
- `run_all_shadows.ps1` - wrapper validation de TODOS os shadows; `-Live` para modo vivo
- `run_commerce_dryruns.ps1` - dry-run dedicado commerce local (winegod_admin_world, vinhos_brasil_legacy, amazon_local)
- `run_reviews_scores_dryruns.ps1` - dry-run dedicado reviews nao-vivino_wines_to_ratings (vivino_reviews, cellartracker, decanter, wine_enthusiast, winesearcher)
- `run_plug_reviews_scores_apply.ps1` - apply canonico de vivino_wines_to_ratings (incremental_recent | backfill_windowed)
- `run_vivino_reviews_backfill.ps1` / `run_vivino_reviews_incremental.ps1` - **wrappers de producao** invocados pelas Scheduled Tasks `WineGod Plug Reviews Vivino Backfill` (15min) e `WineGod Plug Reviews Vivino Incremental` (1h). NAO DELETAR estes arquivos para pausar as tasks: o caminho oficial e `schtasks /Change /TN "..." /DISABLE` (precisa shell admin). Apagar so faz a task falhar silenciosamente com `0xFFFD0000` e o pipeline para sem alarme. Historico: foram apagados em 2026-04-24 ~16:44 durante a campanha Subida 3-fases por nao terem sido versionados originalmente; restaurados e protegidos via git em 2026-04-27.
- `run_commerce_artifact_dryruns.ps1` - dry-run das fontes commerce canonicas por artefato padronizado: `amazon_mirror_primary`, `tier1_global`, `tier2_global_artifact` (Tier2 UNICO, substitui os extintos chats 1..5), `tier2_br` (Tier2 filtrado por pais real). Sem artefato: `amazon_mirror_primary` -> `blocked_external_host` honesto (aguardando JSONL do PC espelho); Tier1/Tier2 -> `blocked_contract_missing` honesto.

## Caminho canonico

Desde 2026-04-24, o projeto convergiu oficialmente para um unico caminho de
ingestao/enriquecimento de vinhos:

```text
scraper/artefato -> roteamento/triagem -> Commerce Plug -> DQ V3 / bulk_ingest
```

Os trilhos paralelos `plug_discovery_stores`, `plug_enrichment`,
`discovery_agent_observer` e `enrichment_gemini_observer` foram
descontinuados como caminhos operacionais. O codigo pode permanecer no repo
como historico/auditoria, mas nao deve entrar em scheduler, observer cadence
ou handoff como rota ativa.

## Artefatos padronizados de commerce

Contrato: `docs/TIER_COMMERCE_CONTRACT.md`.

Diretorios esperados:

```
reports/data_ops_artifacts/amazon_mirror/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier1/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier2_global/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier2/br/<timestamp>_<run_id>.jsonl
```

`tier2_global/` e o feed Tier2 global unico; `tier2/br/` e o Tier2 Brasil
por filtro real de pais. `tier2/chat1..5/` e historico/deprecated e nao
deve ser usado (colapsados em `tier2_global_artifact` por falta de particao
disjunta reproduzivel entre chats Codex).

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
