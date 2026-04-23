param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\critics_wine_enthusiast.yaml' `
  -Workdir 'C:\natura-automation' `
  -LogName 'critics_wine_enthusiast_shadow.log' `
  -Live:$Live `
  -Command @('python', '-m', 'winegod_v2', 'start', 'we', 'gemini', '--workers', '1', '--limite', '10')
exit $LASTEXITCODE
