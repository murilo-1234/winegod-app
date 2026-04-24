param(
  [int]$Limit = 50
)

# Scheduler dedicado para fontes de artefato:
#   - amazon_mirror_primary (feed oficial)
#   - tier1_global (via artefato padronizado)
#   - tier2_* (via artefato padronizado)
#
# NAO roda apply. Apenas dry-run. Fontes sem artefato ainda cairao em
# blocked_contract_missing ou blocked_external_host, conforme esperado.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Set-Location $repoRoot

$sources = @(
  'amazon_mirror_primary',
  'tier1_global',
  'tier2_chat1',
  'tier2_chat2',
  'tier2_chat3',
  'tier2_chat4',
  'tier2_chat5',
  'tier2_br'
)

foreach ($src in $sources) {
  $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $logPath = Join-Path $logDir "${timestamp}_commerce_artifact_dryrun_${src}.log"
  Write-Host "==> commerce artifact dry-run source=$src limit=$Limit"
  try {
    & $python -m sdk.plugs.commerce_dq_v3.runner `
      --source $src `
      --limit $Limit `
      --dry-run 2>&1 | Tee-Object -FilePath $logPath
    if ($LASTEXITCODE -ne 0) {
      Write-Warning "$src exit=$LASTEXITCODE (ver $logPath)"
    }
  } catch {
    Write-Warning "$src threw: $($_.Exception.Message)"
  }
}

Write-Host "==> commerce artifact dryruns done"
