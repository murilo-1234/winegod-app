param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\reviews_vivino_global.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'reviews_vivino_global_shadow.log' `
  -Live:$Live `
  -Command @('python', '-c', "print('configure vivino live command before approved shadow execution')")
exit $LASTEXITCODE
