param(
  [switch]$SkipRegistrySync
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Invoke-Step {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string[]]$Args
  )
  $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $logPath = Join-Path $logDir "${timestamp}_${Name}.log"
  Write-Host "==> $Name"
  & $python @Args 2>&1 | Tee-Object -FilePath $logPath
  if ($LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $LASTEXITCODE"
  }
}

Set-Location $repoRoot

if (-not $SkipRegistrySync) {
  Invoke-Step -Name 'registry_sync' -Args @('scripts/data_ops_registry/sync_registry_from_manifests.py', '--apply')
}

Invoke-Step -Name 'run_all_observers' -Args @('sdk/adapters/run_all_observers.py', '--apply')
