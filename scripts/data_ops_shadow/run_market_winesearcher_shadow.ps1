param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\market_winesearcher.yaml' `
  -Workdir 'C:\natura-automation' `
  -LogName 'market_winesearcher_shadow.log' `
  -Live:$Live `
  -Command @('python', '-m', 'winegod_v2', 'start', 'ws', 'gemini', '--workers', '1', '--limite', '10')
exit $LASTEXITCODE
