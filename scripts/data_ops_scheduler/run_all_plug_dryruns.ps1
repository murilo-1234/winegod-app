param(
  [int]$CommerceLimit = 50,
  [int]$ReviewsLimit = 50,
  [int]$DiscoveryLimit = 100,
  [int]$EnrichmentLimit = 100
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

$commerceSources = @(
  'winegod_admin_world',
  'vinhos_brasil_legacy',
  'amazon_local',
  'amazon_mirror',
  'tier1_global',
  'tier2_chat1',
  'tier2_chat2',
  'tier2_chat3',
  'tier2_chat4',
  'tier2_chat5',
  'tier2_br'
)

foreach ($source in $commerceSources) {
  Invoke-Step -Name "commerce_$source" -Args @(
    '-m', 'sdk.plugs.commerce_dq_v3.runner',
    '--source', $source,
    '--limit', "$CommerceLimit",
    '--dry-run'
  )
}

$reviewSources = @(
  'vivino_reviews_to_scores_reviews',
  'cellartracker_to_scores_reviews',
  'decanter_to_critic_scores',
  'wine_enthusiast_to_critic_scores',
  'winesearcher_to_market_signals'
)

foreach ($source in $reviewSources) {
  Invoke-Step -Name "reviews_$source" -Args @(
    '-m', 'sdk.plugs.reviews_scores.runner',
    '--source', $source,
    '--limit', "$ReviewsLimit",
    '--dry-run'
  )
}

Invoke-Step -Name 'discovery_agent' -Args @(
  '-m', 'sdk.plugs.discovery_stores.runner',
  '--source', 'agent_discovery',
  '--limit', "$DiscoveryLimit",
  '--dry-run'
)

Invoke-Step -Name 'enrichment_gemini_batch_reports' -Args @(
  '-m', 'sdk.plugs.enrichment.runner',
  '--source', 'gemini_batch_reports',
  '--limit', "$EnrichmentLimit",
  '--dry-run'
)
