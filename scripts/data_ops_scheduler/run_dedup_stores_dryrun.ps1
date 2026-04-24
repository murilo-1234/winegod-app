param(
  [int]$BatchSize = 10000,
  [int]$Limit = 0
)

# Dry-run do dedup_stores. Le public.stores em batches de 10k,
# canonicaliza, agrupa e reporta. Zero apply.

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
$logPath = Join-Path $logDir "${ts}_dedup_stores_dryrun.log"

$pyArgs = @('scripts/data_ops_producers/dedup_stores.py', '--plan-only', '--batch-size', "$BatchSize")
if ($Limit -gt 0) { $pyArgs += @('--limit', "$Limit") }

& $python @pyArgs 2>&1 | Tee-Object -FilePath $logPath
exit $LASTEXITCODE
