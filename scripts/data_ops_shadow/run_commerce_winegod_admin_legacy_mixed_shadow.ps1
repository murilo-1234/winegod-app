param([switch]$Live)
$ErrorActionPreference = 'Stop'
# Salvamento honesto do legado Tier1/Tier2 misturado (lineage=legacy_mixed).
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\commerce_winegod_admin_legacy_mixed.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'commerce_winegod_admin_legacy_mixed_shadow.log' `
  -Live:$Live `
  -Command @('python', '-m', 'sdk.plugs.commerce_dq_v3.runner', '--source', 'winegod_admin_legacy_mixed', '--limit', '50', '--dry-run')
exit $LASTEXITCODE
