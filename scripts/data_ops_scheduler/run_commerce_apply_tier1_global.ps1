param(
  [switch]$DryRunOnly,
  [int[]]$Ladder = @(50, 200, 500),
  [int]$PauseSeconds = 5
)

# Commerce apply Tier1 global. Gated por COMMERCE_APPLY_AUTHORIZED_TIER1=1.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $repoRoot

if (-not $env:COMMERCE_APPLY_AUTHORIZED_TIER1 -or $env:COMMERCE_APPLY_AUTHORIZED_TIER1 -ne '1') {
  Write-Host 'ABORT: COMMERCE_APPLY_AUTHORIZED_TIER1 != 1'
  exit 2
}

$artifactDir = Join-Path $repoRoot 'reports\data_ops_artifacts\tier1'
$validatorLog = Join-Path $logDir ((Get-Date -Format 'yyyyMMdd_HHmmss') + '_apply_tier1_validator.log')
& $python 'scripts/data_ops_producers/validate_commerce_artifact.py' `
  --artifact-dir $artifactDir `
  --expected-family 'tier1' 2>&1 | Tee-Object -FilePath $validatorLog
if ($LASTEXITCODE -ne 0) {
  Write-Host "ABORT: validator FULL falhou (exit=$LASTEXITCODE)"
  exit $LASTEXITCODE
}

if ($DryRunOnly) { exit 0 }

$source = 'tier1_global'
foreach ($limit in $Ladder) {
  $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $stepLog = Join-Path $logDir "${timestamp}_apply_tier1_limit_${limit}.log"
  Write-Host "==> apply source=$source limit=$limit"
  & $python '-m' 'sdk.plugs.commerce_dq_v3.runner' `
    --source $source `
    --limit $limit `
    --apply 2>&1 | Tee-Object -FilePath $stepLog
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  if ((Get-Content $stepLog -Raw) -match 'BLOCKED_QUEUE_EXPLOSION') {
    Write-Host "ABORT: BLOCKED_QUEUE_EXPLOSION limit=$limit"
    exit 3
  }
  if ($PauseSeconds -gt 0) { Start-Sleep -Seconds $PauseSeconds }
}
Write-Host '==> apply tier1_global ladder completa.'
exit 0
