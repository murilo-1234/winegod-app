param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\commerce_amazon_local.yaml' `
  -Workdir 'C:\natura-automation' `
  -LogName 'commerce_amazon_local_shadow.log' `
  -Live:$Live `
  python amazon/main.py run --pais BR --limite 20
exit $LASTEXITCODE
