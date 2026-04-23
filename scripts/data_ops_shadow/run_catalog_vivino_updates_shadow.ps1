param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\catalog_vivino_updates.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'catalog_vivino_updates_shadow.log' `
  -Live:$Live `
  -Command @('python', 'sdk/adapters/catalog_vivino_updates_observer.py', '--apply')
exit $LASTEXITCODE
