param(
  [int]$Limit = 50,
  [string[]]$Sources = @(
    'vivino_reviews_to_scores_reviews',
    'cellartracker_to_scores_reviews',
    'decanter_to_critic_scores',
    'wine_enthusiast_to_critic_scores',
    'winesearcher_to_market_signals'
  )
)

# Scheduler dedicado: roda dry-run do plug_reviews_scores para TODAS as fontes
# nao-vivino_wines_to_ratings. Mantem staging fresco sem escrever em wine_scores.
# vivino_wines_to_ratings tem scheduler de apply dedicado separado.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Set-Location $repoRoot

foreach ($src in $Sources) {
  $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $logPath = Join-Path $logDir "${timestamp}_reviews_dryrun_${src}.log"
  Write-Host "==> reviews dry-run source=$src limit=$Limit"
  & $python -m sdk.plugs.reviews_scores.runner `
    --source $src `
    --limit $Limit `
    --dry-run 2>&1 | Tee-Object -FilePath $logPath
  if ($LASTEXITCODE -ne 0) {
    throw "reviews dryrun $src failed with exit code $LASTEXITCODE"
  }
}

Write-Host "==> reviews dryruns done"
