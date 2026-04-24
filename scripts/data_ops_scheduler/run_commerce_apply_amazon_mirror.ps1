param(
  [switch]$DryRunOnly,
  [int[]]$Ladder = @(50, 200, 1000),
  [int]$PauseSeconds = 5
)

# Commerce apply Amazon mirror - gated por env COMMERCE_APPLY_AUTHORIZED_AMAZON_MIRROR=1.
# Roda validator FULL antes de qualquer apply. Escada controlada.
# Abort automatico se BLOCKED_QUEUE_EXPLOSION aparecer no summary.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $repoRoot

if (-not $env:COMMERCE_APPLY_AUTHORIZED_AMAZON_MIRROR -or $env:COMMERCE_APPLY_AUTHORIZED_AMAZON_MIRROR -ne '1') {
  Write-Host 'ABORT: COMMERCE_APPLY_AUTHORIZED_AMAZON_MIRROR != 1'
  Write-Host 'Rode:  $env:COMMERCE_APPLY_AUTHORIZED_AMAZON_MIRROR = "1"  antes.'
  exit 2
}

$artifactDir = Join-Path $repoRoot 'reports\data_ops_artifacts\amazon_mirror'
Write-Host "==> Validator FULL antes de aplicar: $artifactDir"
$validatorLog = Join-Path $logDir ((Get-Date -Format 'yyyyMMdd_HHmmss') + '_apply_amazon_mirror_validator.log')
& $python 'scripts/data_ops_producers/validate_commerce_artifact.py' `
  --artifact-dir $artifactDir `
  --expected-family 'amazon_mirror_primary' 2>&1 | Tee-Object -FilePath $validatorLog
if ($LASTEXITCODE -ne 0) {
  Write-Host "ABORT: validator FULL falhou (exit=$LASTEXITCODE). Ver $validatorLog"
  exit $LASTEXITCODE
}

if ($DryRunOnly) {
  Write-Host '==> DryRunOnly ligado; pulando apply.'
  exit 0
}

$source = 'amazon_mirror_primary'
foreach ($limit in $Ladder) {
  $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $stepLog = Join-Path $logDir "${timestamp}_apply_amazon_mirror_limit_${limit}.log"
  Write-Host "==> apply source=$source limit=$limit"
  & $python '-m' 'sdk.plugs.commerce_dq_v3.runner' `
    --source $source `
    --limit $limit `
    --apply 2>&1 | Tee-Object -FilePath $stepLog
  if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORT: apply limit=$limit exit=$LASTEXITCODE. Ver $stepLog"
    exit $LASTEXITCODE
  }
  $summaryContent = Get-Content $stepLog -Raw
  if ($summaryContent -match 'BLOCKED_QUEUE_EXPLOSION') {
    Write-Host "ABORT: BLOCKED_QUEUE_EXPLOSION no limit=$limit"
    exit 3
  }
  if ($PauseSeconds -gt 0) {
    Write-Host "  pausa ${PauseSeconds}s antes do proximo degrau"
    Start-Sleep -Seconds $PauseSeconds
  }
}

Write-Host '==> apply amazon_mirror_primary ladder completa.'
exit 0
