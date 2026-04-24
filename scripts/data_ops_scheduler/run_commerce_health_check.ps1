param(
  [switch]$Md,
  [string]$WriteMd
)

# Commerce health check (read-only).
# Exit:
#   0 = ok
#   2 = warning
#   3 = failed

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
Set-Location $repoRoot

$cmdArgs = @('-m', 'sdk.plugs.commerce_dq_v3.health')
if ($Md) {
  $cmdArgs += @('--stdout', 'md')
} else {
  $cmdArgs += @('--stdout', 'summary')
}
if ($WriteMd) {
  $cmdArgs += @('--write-md', $WriteMd)
}

& $python @cmdArgs
$exitCode = $LASTEXITCODE
exit $exitCode
