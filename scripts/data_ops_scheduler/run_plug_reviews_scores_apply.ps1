param(
  [int]$Limit = 10000,
  [ValidateSet('incremental_recent','backfill_windowed')]
  [string]$Mode = 'incremental_recent'
)

# Scheduler automatico do plug_reviews_scores em modo apply.
#
# Dois modos suportados (use os DOIS quando quiser cobertura total):
#
# 1) incremental_recent (default, delta contino):
#    ORDER BY atualizado_em DESC LIMIT N.
#    Sempre reprocessa o topo mais recente. Idempotente (ON CONFLICT DO UPDATE
#    WHERE IS DISTINCT FROM: zero mudanca quando o input e identico).
#    NAO progride automaticamente para o resto da base.
#
# 2) backfill_windowed (progressao real):
#    WHERE id > last_id ORDER BY id ASC LIMIT N.
#    Persiste `last_id` em reports/data_ops_plugs_state/<source>.json e avanca
#    a cada run. Use para varrer a base inteira. Quando o exporter retornar
#    0 items, significa que o backfill chegou ao fim.
#
# REGRA 5: writer aplica cada lote em UMA transacao atomica (wine_scores +
# wines sobem juntos ou rollback juntos).
# REGRA 7: este script nao faz deploy Render; roda localmente ou em Task Scheduler.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Set-Location $repoRoot

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$logPath = Join-Path $logDir "${timestamp}_plug_reviews_scores_apply_${Mode}.log"
Write-Host "==> plug_reviews_scores apply (mode=$Mode limit=$Limit)"

& $python -m sdk.plugs.reviews_scores.runner `
  --source vivino_wines_to_ratings `
  --limit $Limit `
  --mode $Mode `
  --apply 2>&1 | Tee-Object -FilePath $logPath

if ($LASTEXITCODE -ne 0) {
  throw "plug_reviews_scores apply failed with exit code $LASTEXITCODE"
}

Write-Host "==> done. log: $logPath"
