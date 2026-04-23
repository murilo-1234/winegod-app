param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\commerce_world_winegod_admin.yaml' `
  -Workdir 'C:\natura-automation\winegod_admin' `
  -LogName 'commerce_world_winegod_admin_shadow.log' `
  -Live:$Live `
  python run_pipeline.py --country PT --only scraping
exit $LASTEXITCODE
