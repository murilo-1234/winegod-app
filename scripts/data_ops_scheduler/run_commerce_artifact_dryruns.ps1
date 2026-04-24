param(
  [int]$Limit = 50
)

# Scheduler dedicado para fontes de commerce via artefato padronizado:
#   - amazon_mirror_primary (feed oficial; residual externo enquanto JSONL nao chega)
#   - tier1_global (via artefato padronizado em reports/data_ops_artifacts/tier1)
#   - tier2_global_artifact (feed Tier2 UNICO; substitui os extintos tier2_chat1..5)
#   - tier2_br (Tier2 filtrado por pais real)
#
# tier2_chat1..5 foram DEPRECATED e colapsados em tier2_global_artifact
# (nao tinham particao disjunta reproduzivel). Seus manifests continuam
# blocked_contract_missing no registry para historico, mas NAO sao rodados
# por este scheduler.
#
# NAO roda apply. Apenas dry-run. Fontes sem artefato caem honestamente em
# blocked_contract_missing ou blocked_external_host.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Set-Location $repoRoot

$sources = @(
  'amazon_mirror_primary',
  'tier1_global',
  'tier2_global_artifact',
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
