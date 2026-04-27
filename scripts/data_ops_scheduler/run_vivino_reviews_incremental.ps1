param(
  [int]$Limit = 10000
)

# WineGod - Vivino Reviews Plug Incremental (Windows Task Scheduler wrapper)
# ============================================================================
# Este script e a "fonte da verdade" rodada pela Scheduled Task
# "WineGod Plug Reviews Vivino Incremental" a cada 1 hora.
#
# IMPORTANTE: este arquivo e VERSIONADO em git. NAO deletar do disco para
# pausar a Scheduled Task - use o caminho oficial:
#   schtasks /Change /TN "WineGod Plug Reviews Vivino Incremental" /DISABLE
# (precisa shell admin). Apagar o arquivo so faz a task falhar silenciosamente
# com 0xFFFD0000.
#
# Modo incremental_recent: ORDER BY atualizado_em DESC LIMIT N. Sempre
# reprocessa o topo recente. Idempotente (ON CONFLICT DO UPDATE WHERE IS
# DISTINCT FROM: zero mudanca quando input e identico). NAO progride
# automaticamente para o resto da base - quem varre e o backfill.
#
# REGRA 5: limit padrao 10k. REGRA 7: nao toca em Render config.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler\vivino_reviews_incremental'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$logPath = Join-Path $logDir "${timestamp}_incremental.log"

"started_at=$(Get-Date -Format o)" | Out-File -FilePath $logPath -Encoding utf8
"mode=incremental_recent"          | Out-File -FilePath $logPath -Encoding utf8 -Append
"limit=$Limit"                     | Out-File -FilePath $logPath -Encoding utf8 -Append
"script=$PSCommandPath"            | Out-File -FilePath $logPath -Encoding utf8 -Append

$python = (Get-Command python -ErrorAction Stop).Source
"python=$python" | Out-File -FilePath $logPath -Encoding utf8 -Append

Set-Location $repoRoot

& $python -m sdk.plugs.reviews_scores.runner `
  --source vivino_wines_to_ratings `
  --limit $Limit `
  --mode incremental_recent `
  --apply 2>&1 | Tee-Object -FilePath $logPath -Append
$exitCode = $LASTEXITCODE

"---"            | Out-File -FilePath $logPath -Encoding utf8 -Append
"exit=$exitCode" | Out-File -FilePath $logPath -Encoding utf8 -Append

exit $exitCode
