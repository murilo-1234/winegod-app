param([switch]$Live)

# Roda TODOS os shadow wrappers em modo wrapper-validation (default).
# Se -Live for passado, ainda assim cada wrapper respeita suas proprias
# restricoes (blocked_external_host nao executa scraping real).

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$shadowDir = Join-Path $repoRoot 'scripts\data_ops_shadow'
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$shadows = Get-ChildItem -Path $shadowDir -Filter 'run_*_shadow.ps1' | Sort-Object Name

foreach ($shadow in $shadows) {
  $name = $shadow.BaseName
  $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $logPath = Join-Path $logDir "${timestamp}_${name}.log"
  Write-Host "==> $name"
  try {
    if ($Live) {
      & (Join-Path $shadowDir $shadow.Name) -Live 2>&1 | Tee-Object -FilePath $logPath
    } else {
      & (Join-Path $shadowDir $shadow.Name) 2>&1 | Tee-Object -FilePath $logPath
    }
    if ($LASTEXITCODE -ne 0) {
      Write-Warning "$name exited with $LASTEXITCODE (ver log $logPath)"
    }
  } catch {
    Write-Warning "$name threw: $($_.Exception.Message)"
  }
}

Write-Host "==> all shadows done"
