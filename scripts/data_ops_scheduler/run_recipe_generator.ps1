param(
  [string]$Domain = "example.com",
  [string]$SampleHtml = "",
  [string]$SampleUrl = "",
  [string]$ProductName = ""
)

# Recipe generator standalone (deterministico, sem LLM).
# Util como smoke test do heuristic. Gera candidato em
# reports/data_ops_recipe_candidates/.

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
$logPath = Join-Path $logDir "${ts}_recipe_generator.log"

$script = @"
from sdk.plugs.discovery_stores.recipe_generator import generate_recipe, persist_candidate

cand = generate_recipe(
    domain='$Domain',
    platform='unknown',
    sample_html='$SampleHtml',
    sample_url='$SampleUrl',
    sample_product_name='$ProductName',
)
path = persist_candidate(cand)
print(f'[recipe_generator] domain={cand.domain} confidence={cand.confidence} path={path}')
"@

& $python -c "$script" 2>&1 | Tee-Object -FilePath $logPath
exit $LASTEXITCODE
