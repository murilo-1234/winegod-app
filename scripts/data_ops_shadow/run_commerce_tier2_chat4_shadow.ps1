param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\commerce_tier2_chat4.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'commerce_tier2_chat4_shadow.log' `
  -Live:$Live `
  -Command @('python', '-c', "print('manual tier2 chat4 shadow package prepared; connect approved live command before execution')")
exit $LASTEXITCODE
