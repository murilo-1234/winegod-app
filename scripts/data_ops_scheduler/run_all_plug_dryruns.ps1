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

# Fontes commerce canonicas pos-finalizacao 2026-04-24 (dry-run only):
# - winegod_admin_world: feed local observed (exporter legacy winegod_db)
# - vinhos_brasil_legacy: feed local observed (exporter legacy vinhos_brasil_db)
# - amazon_local: observer legado (mantido para diagnostico; nao e feed primario)
# - amazon_local_legacy_backfill: backfill controlado do historico Amazon
# - amazon_mirror_primary: feed Amazon oficial (blocked_external_host ate JSONL do PC espelho)
# - tier1_global: feed Tier1 via artefato padronizado
# - tier2_global_artifact: feed Tier2 UNICO global via artefato padronizado
# - tier2_br: Tier2 Brasil por filtro real de pais
# - winegod_admin_legacy_mixed: allowlist explicita (blocked_missing_source sem env)
#
# tier2_chat1..5 foram DEPRECATED e colapsados em tier2_global_artifact (sem
# particao disjunta reproduzivel). amazon_mirror (stub legado) foi substituido
# por amazon_mirror_primary. Ver run_commerce_artifact_dryruns.ps1 para o
# scheduler canonico reduzido focado em fontes por artefato.
$commerceSources = @(
  'winegod_admin_world',
  'vinhos_brasil_legacy',
  'amazon_local',
  'amazon_local_legacy_backfill',
  'amazon_mirror_primary',
  'tier1_global',
  'tier2_global_artifact',
  'tier2_br',
  'winegod_admin_legacy_mixed'
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
