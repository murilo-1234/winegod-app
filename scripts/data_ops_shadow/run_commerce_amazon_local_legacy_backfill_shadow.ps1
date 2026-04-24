param([switch]$Live)
$ErrorActionPreference = 'Stop'
# Backfill controlado do historico amazon_local. Congelado como legado.
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\commerce_amazon_local_legacy_backfill.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'commerce_amazon_local_legacy_backfill_shadow.log' `
  -Live:$Live `
  -Command @('python', '-m', 'sdk.plugs.commerce_dq_v3.runner', '--source', 'amazon_local_legacy_backfill', '--limit', '50', '--dry-run')
exit $LASTEXITCODE
