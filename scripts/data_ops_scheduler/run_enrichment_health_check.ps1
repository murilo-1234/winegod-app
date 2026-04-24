[CmdletBinding()]
param(
  [double]$StaleHours = 168.0,
  [ValidateSet('json','md')]
  [string]$Format = 'md',
  [string]$WriteMd = $null
)

# Health check observacional do dominio enrichment.
#
# READ-ONLY: nao chama Gemini/Flash, nao escreve em banco, nao modifica
# staging/state. Le artifacts locais + staging + logs e classifica em
# ok / warning / failed.
#
# Exit:
#   0 -> ok
#   2 -> warning
#   3 -> failed

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

$pyArgs = @(
  '-m', 'sdk.plugs.enrichment.health',
  '--stale-hours', "$StaleHours",
  '--stdout', $Format
)
if ($WriteMd) { $pyArgs += @('--write-md', $WriteMd) }

& $python @pyArgs
exit $LASTEXITCODE
