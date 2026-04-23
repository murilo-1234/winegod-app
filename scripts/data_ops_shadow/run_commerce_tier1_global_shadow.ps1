param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\commerce_tier1_global.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'commerce_tier1_global_shadow.log' `
  -Live:$Live `
  -Command @('python', '-c', "print('review tier1 global command scope before enabling live shadow on this host')")
exit $LASTEXITCODE
