param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\reviews_vivino_partition_b.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'reviews_vivino_partition_b_shadow.log' `
  -Live:$Live `
  -Command @('python', '-c', "print('partition_b shadow wrapper is present, but execution depends on the approved external mirror host and is not runnable from this machine')") 
exit $LASTEXITCODE
