param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\scores_cellartracker.yaml' `
  -Workdir 'C:\natura-automation' `
  -LogName 'scores_cellartracker_shadow.log' `
  -Live:$Live `
  python -m winegod_v2 start ct gemini --workers 1 --limite 10
exit $LASTEXITCODE
