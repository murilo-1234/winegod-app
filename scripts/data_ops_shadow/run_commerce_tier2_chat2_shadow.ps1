param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\commerce_tier2_chat2.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'commerce_tier2_chat2_shadow.log' `
  -Live:$Live `
  -Command @('python', '-c', "print('manual tier2 chat2 shadow package prepared; connect approved live command before execution')")
exit $LASTEXITCODE
