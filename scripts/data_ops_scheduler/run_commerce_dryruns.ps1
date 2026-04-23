param(
  [int]$Limit = 50,
  [string[]]$Sources = @('winegod_admin_world','vinhos_brasil_legacy','amazon_local')
)

# Scheduler dedicado: roda dry-run do plug_commerce_dq_v3 para as fontes
# commerce LOCAIS (nao aciona mirror / tier1 / tier2 que sao blocked).
# Uso previsto: Task Scheduler diario para manter staging fresco sem apply.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Set-Location $repoRoot

foreach ($src in $Sources) {
  $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $logPath = Join-Path $logDir "${timestamp}_commerce_dryrun_${src}.log"
  Write-Host "==> commerce dry-run source=$src limit=$Limit"
  & $python -m sdk.plugs.commerce_dq_v3.runner `
    --source $src `
    --limit $Limit `
    --dry-run 2>&1 | Tee-Object -FilePath $logPath
  if ($LASTEXITCODE -ne 0) {
    throw "commerce dryrun $src failed with exit code $LASTEXITCODE"
  }
}

Write-Host "==> commerce dryruns done"
