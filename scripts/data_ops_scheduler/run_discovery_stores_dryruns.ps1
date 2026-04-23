param(
  [int]$Limit = 100,
  [string[]]$Sources = @('agent_discovery')
)

# Scheduler dedicado: roda dry-run do plug_discovery_stores.
# Discovery NAO cria wine nem wine_source.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Set-Location $repoRoot

foreach ($src in $Sources) {
  $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $logPath = Join-Path $logDir "${timestamp}_discovery_dryrun_${src}.log"
  Write-Host "==> discovery dry-run source=$src limit=$Limit"
  & $python -m sdk.plugs.discovery_stores.runner `
    --source $src `
    --limit $Limit `
    --dry-run 2>&1 | Tee-Object -FilePath $logPath
  if ($LASTEXITCODE -ne 0) {
    throw "discovery dryrun $src failed with exit code $LASTEXITCODE"
  }
}

Write-Host "==> discovery dryruns done"
