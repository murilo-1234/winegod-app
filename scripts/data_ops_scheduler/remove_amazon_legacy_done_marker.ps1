param([switch]$Force)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$doneFlag = Join-Path $repoRoot 'reports\data_ops_export_state\amazon_legacy_backfill_done.json'
if (-not (Test-Path $doneFlag)) {
  Write-Host "OK: marker nao existe em $doneFlag"
  exit 0
}
if (-not $Force) {
  Write-Host "ABORT: use -Force para remover. Marker atual:"
  Get-Content $doneFlag | Write-Host
  exit 1
}
Remove-Item $doneFlag -Force
Write-Host "==> marker removido: $doneFlag"
exit 0
