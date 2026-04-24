[CmdletBinding()]
param(
  [double]$StallHours = 3.0,
  [ValidateSet('json','md')]
  [string]$Format = 'md',
  [string]$WriteMd = $null
)

# Health check observacional do canal canonico vivino_wines_to_ratings.
#
# NAO executa apply. NAO conecta no banco. NAO altera checkpoint.
# So le state + staging + scheduler logs e classifica o dominio em:
#   ok | ok_backfill_done | warning | failed
#
# Exit codes:
#   0 -> ok / ok_backfill_done
#   2 -> warning
#   3 -> failed
#
# Uso tipico:
#   .\run_vivino_reviews_health_check.ps1
#   .\run_vivino_reviews_health_check.ps1 -Format json
#   .\run_vivino_reviews_health_check.ps1 -WriteMd reports\WINEGOD_REVIEWS_HEALTH_LATEST.md

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

# Resolucao robusta do python (mesmo padrao dos wrappers ja em uso).
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

$pyArgs = @(
  '-m', 'sdk.plugs.reviews_scores.health',
  '--stall-hours', "$StallHours",
  '--stdout', $Format
)
if ($WriteMd) {
  $pyArgs += @('--write-md', $WriteMd)
}

& $python @pyArgs
exit $LASTEXITCODE
