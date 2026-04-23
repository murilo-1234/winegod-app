param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\reviewers_vivino_global.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'reviewers_vivino_global_shadow.log' `
  -Live:$Live `
  -Command @('python', 'sdk/adapters/reviewers_vivino_observer.py', '--apply')
exit $LASTEXITCODE
