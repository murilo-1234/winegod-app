param(
  [int]$Items = 0,
  [string]$CapUsd = "50"
)

# Forecast do loop de enrichment. ZERO chamada Gemini.
# Gera md+json em reports/data_ops_enrichment_budget/.

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
$logPath = Join-Path $logDir "${ts}_enrichment_budget_forecast.log"

$pyArgs = @('scripts/data_ops_producers/enrichment_budget_forecast.py', '--cap-usd', $CapUsd)
if ($Items -gt 0) { $pyArgs += @('--items', "$Items") }

& $python @pyArgs 2>&1 | Tee-Object -FilePath $logPath
exit $LASTEXITCODE
