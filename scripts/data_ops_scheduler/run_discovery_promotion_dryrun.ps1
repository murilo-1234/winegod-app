param(
  [int]$Limit = 50
)

# Dry-run do promote_discovery_stores. Gera plan em
# reports/data_ops_promotion_plans/<ts>_plan.json. Zero apply.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

$pythonCandidates = @(
  'C:\Users\muril\AppData\Local\Python\pythoncore-3.14-64\python.exe',
  'C:\Users\muril\AppData\Local\Programs\Python\Python314\python.exe',
  'C:\Users\muril\AppData\Local\Programs\Python\Python313\python.exe',
  'C:\Users\muril\AppData\Local\Programs\Python\Python312\python.exe'
)
$python = $null
foreach ($c in $pythonCandidates) {
  if (Test-Path $c) { $python = $c; break }
}
if (-not $python) {
  try { $python = (Get-Command python -ErrorAction Stop).Source } catch {
    throw "python.exe nao encontrado"
  }
}

Set-Location $repoRoot
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$logPath = Join-Path $logDir "${ts}_discovery_promotion_dryrun.log"

& $python scripts/data_ops_producers/promote_discovery_stores.py --plan-only --limit $Limit 2>&1 | Tee-Object -FilePath $logPath
exit $LASTEXITCODE
