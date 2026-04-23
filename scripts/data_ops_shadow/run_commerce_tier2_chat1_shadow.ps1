param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\commerce_tier2_chat1.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'commerce_tier2_chat1_shadow.log' `
  -Live:$Live `
  -Command @('python', '-c', "print('manual tier2 chat1 shadow package prepared; connect approved live command before execution')")
exit $LASTEXITCODE
