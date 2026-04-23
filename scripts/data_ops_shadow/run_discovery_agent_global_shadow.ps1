param([switch]$Live)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\discovery_agent_global.yaml' `
  -Workdir 'C:\natura-automation\agent_discovery' `
  -LogName 'discovery_agent_global_shadow.log' `
  -Live:$Live `
  python run_discovery.py
exit $LASTEXITCODE
