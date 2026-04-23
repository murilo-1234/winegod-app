param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\critics_decanter_persisted.yaml' `
  -Workdir 'C:\natura-automation' `
  -LogName 'critics_decanter_persisted_shadow.log' `
  -Live:$Live `
  python -m winegod_v2 start decanter gemini --workers 1 --limite 10
exit $LASTEXITCODE
