param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\reviews_vivino_partition_c.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'reviews_vivino_partition_c_shadow.log' `
  -Live:$Live `
  -Command @('python', '-c', "print('partition_c shadow wrapper is present, but execution depends on the approved external wab/render host and is not runnable from this machine')") 
exit $LASTEXITCODE
