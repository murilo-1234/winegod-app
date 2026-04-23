param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\commerce_br_vinhos_brasil_legacy.yaml' `
  -Workdir 'C:\natura-automation\vinhos_brasil' `
  -LogName 'commerce_br_vinhos_brasil_legacy_shadow.log' `
  -Live:$Live `
  python main.py vtex
exit $LASTEXITCODE
