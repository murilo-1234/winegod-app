param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\reviews_vivino_partition_a.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'reviews_vivino_partition_a_shadow.log' `
  -Live:$Live `
  -Command @('python', '-c', "print('partition_a shadow wrapper is present, but live execution remains blocked because the A/B/C contract is not persisted auditably in vivino_db')") 
exit $LASTEXITCODE
