# Data Ops Scheduler

These scripts prepare the control plane cadence without installing a Windows scheduled task automatically.

## Scripts

- `run_all_observers.ps1`
- `run_all_plug_dryruns.ps1`

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
