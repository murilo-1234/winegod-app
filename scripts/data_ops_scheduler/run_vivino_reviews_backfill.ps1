param(
  [int]$Limit = 10000
)

# WineGod - Vivino Reviews Plug Backfill (Windows Task Scheduler wrapper)
# ============================================================================
# Este script e a "fonte da verdade" rodada pela Scheduled Task
# "WineGod Plug Reviews Vivino Backfill" a cada 15 minutos.
#
# IMPORTANTE: este arquivo e VERSIONADO em git. NAO deletar do disco para
# pausar a Scheduled Task - use o caminho oficial:
#   schtasks /Change /TN "WineGod Plug Reviews Vivino Backfill" /DISABLE
# (precisa shell admin). Apagar o arquivo so faz a task falhar silenciosamente
# com 0xFFFD0000 e o backfill para sem ninguem perceber.
#
# Modo backfill_windowed: avanca cursor `last_id` em
# reports/data_ops_plugs_state/vivino_wines_to_ratings.json. Quando o exporter
# retornar 0 items, o runner cria a sentinela
# reports/data_ops_plugs_state/vivino_wines_to_ratings.BACKFILL_DONE e este
# wrapper passa a ser no-op (REGRA 5: nao reprocessar base inteira sem
# necessidade).
#
# REGRA 5: limit padrao 10k. REGRA 7: nao toca em Render config.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler\vivino_reviews_backfill'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$logPath = Join-Path $logDir "${timestamp}_backfill.log"

"started_at=$(Get-Date -Format o)" | Out-File -FilePath $logPath -Encoding utf8
"mode=backfill_windowed"           | Out-File -FilePath $logPath -Encoding utf8 -Append
"limit=$Limit"                     | Out-File -FilePath $logPath -Encoding utf8 -Append
"script=$PSCommandPath"            | Out-File -FilePath $logPath -Encoding utf8 -Append

# Sentinela de fim de backfill - se existe, vira no-op idempotente.
$sentinel = Join-Path $repoRoot 'reports\data_ops_plugs_state\vivino_wines_to_ratings.BACKFILL_DONE'
if (Test-Path $sentinel) {
  "sentinel=present (no-op)" | Out-File -FilePath $logPath -Encoding utf8 -Append
  "exit=0"                   | Out-File -FilePath $logPath -Encoding utf8 -Append
  exit 0
}

$python = (Get-Command python -ErrorAction Stop).Source
"python=$python" | Out-File -FilePath $logPath -Encoding utf8 -Append

Set-Location $repoRoot

& $python -m sdk.plugs.reviews_scores.runner `
  --source vivino_wines_to_ratings `
  --limit $Limit `
  --mode backfill_windowed `
  --apply 2>&1 | Tee-Object -FilePath $logPath -Append
$exitCode = $LASTEXITCODE

"---"               | Out-File -FilePath $logPath -Encoding utf8 -Append
"exit=$exitCode"    | Out-File -FilePath $logPath -Encoding utf8 -Append

# Auto-criar sentinela quando o exporter retornar 0 items (chegou ao fim).
$state = Join-Path $repoRoot 'reports\data_ops_plugs_state\vivino_wines_to_ratings.json'
if ($exitCode -eq 0 -and (Test-Path $state)) {
  $stateRaw = Get-Content $state -Raw -Encoding UTF8
  if ($stateRaw -match '"items_exported"\s*:\s*0' -or $stateRaw -match 'items_exported=0') {
    New-Item -ItemType File -Force -Path $sentinel | Out-Null
    "sentinel=created" | Out-File -FilePath $logPath -Encoding utf8 -Append
  }
}

exit $exitCode
