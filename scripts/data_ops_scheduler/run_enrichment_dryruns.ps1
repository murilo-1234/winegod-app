param(
  [int]$Limit = 100,
  [string[]]$Sources = @('gemini_batch_reports')
)

# Scheduler dedicado: roda dry-run do plug_enrichment (observer only).
# Gemini pago NAO e acionado aqui (R6). O plug apenas observa artefatos locais.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Set-Location $repoRoot

foreach ($src in $Sources) {
  $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $logPath = Join-Path $logDir "${timestamp}_enrichment_dryrun_${src}.log"
  Write-Host "==> enrichment dry-run source=$src limit=$Limit"
  & $python -m sdk.plugs.enrichment.runner `
    --source $src `
    --limit $Limit `
    --dry-run 2>&1 | Tee-Object -FilePath $logPath
  if ($LASTEXITCODE -ne 0) {
    throw "enrichment dryrun $src failed with exit code $LASTEXITCODE"
  }
}

Write-Host "==> enrichment dryruns done"
