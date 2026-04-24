param(
  [switch]$DryRunOnly,
  [int[]]$Ladder = @(50, 200, 1000),
  [int]$PauseSeconds = 5
)

# Commerce apply Amazon legacy backfill (one-time). Gated por
# COMMERCE_APPLY_AUTHORIZED_AMAZON_LEGACY=1. Gera state
# reports/data_ops_export_state/amazon_legacy_backfill_done.json apos sucesso.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
$stateDir = Join-Path $repoRoot 'reports\data_ops_export_state'
New-Item -ItemType Directory -Force -Path $logDir, $stateDir | Out-Null
Set-Location $repoRoot

if (-not $env:COMMERCE_APPLY_AUTHORIZED_AMAZON_LEGACY -or $env:COMMERCE_APPLY_AUTHORIZED_AMAZON_LEGACY -ne '1') {
  Write-Host 'ABORT: COMMERCE_APPLY_AUTHORIZED_AMAZON_LEGACY != 1'
  exit 2
}

$doneFlag = Join-Path $stateDir 'amazon_legacy_backfill_done.json'
if (Test-Path $doneFlag) {
  Write-Host "ABORT: amazon_legacy_backfill_done.json ja existe ($doneFlag). Backfill e one-time."
  exit 2
}

$artifactDir = Join-Path $repoRoot 'reports\data_ops_artifacts\amazon_local_legacy_backfill'
$validatorLog = Join-Path $logDir ((Get-Date -Format 'yyyyMMdd_HHmmss') + '_apply_amazon_legacy_validator.log')
& $python 'scripts/data_ops_producers/validate_commerce_artifact.py' `
  --artifact-dir $artifactDir `
  --expected-family 'amazon_local_legacy_backfill' 2>&1 | Tee-Object -FilePath $validatorLog
if ($LASTEXITCODE -ne 0) {
  Write-Host "ABORT: validator FULL falhou (exit=$LASTEXITCODE). Ver $validatorLog"
  exit $LASTEXITCODE
}

if ($DryRunOnly) {
  Write-Host '==> DryRunOnly ligado; pulando apply.'
  exit 0
}

$source = 'amazon_local_legacy_backfill'
foreach ($limit in $Ladder) {
  $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $stepLog = Join-Path $logDir "${timestamp}_apply_amazon_legacy_limit_${limit}.log"
  Write-Host "==> apply source=$source limit=$limit"
  & $python '-m' 'sdk.plugs.commerce_dq_v3.runner' `
    --source $source `
    --limit $limit `
    --apply 2>&1 | Tee-Object -FilePath $stepLog
  if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORT: apply limit=$limit exit=$LASTEXITCODE"
    exit $LASTEXITCODE
  }
  if ((Get-Content $stepLog -Raw) -match 'BLOCKED_QUEUE_EXPLOSION') {
    Write-Host "ABORT: BLOCKED_QUEUE_EXPLOSION limit=$limit"
    exit 3
  }
  if ($PauseSeconds -gt 0) { Start-Sleep -Seconds $PauseSeconds }
}

$doneMarker = @{
  completed_at = (Get-Date -Format 'o')
  ladder = $Ladder
} | ConvertTo-Json -Depth 3
Set-Content -Path $doneFlag -Value $doneMarker -Encoding UTF8
Write-Host "==> apply amazon_legacy ladder completa. State: $doneFlag"
exit 0
