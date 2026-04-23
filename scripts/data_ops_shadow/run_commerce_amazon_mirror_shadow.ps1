param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\commerce_amazon_mirror.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'commerce_amazon_mirror_shadow.log' `
  -Live:$Live `
  -Command @('python', '-c', "print('execute this wrapper on the approved mirror host with the local amazon runtime')")
exit $LASTEXITCODE
