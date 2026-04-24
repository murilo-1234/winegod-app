param(
  [Parameter(Mandatory=$true)] [string]$Source,
  [Parameter(Mandatory=$true)] [string]$ArtifactDir,
  [Parameter(Mandatory=$true)] [string]$ShardId,
  [Parameter(Mandatory=$true)] [string]$ExpectedFamily,
  [Parameter(Mandatory=$true)] [int]$Limit,
  [switch]$DryRun,
  [string]$Phase = "phase_2_execution",
  [string]$Country = "",
  [string]$SourceTable = "",
  [int]$MinFonteId = 0,
  [int]$MaxFonteId = 0,
  [int]$ExpectedRows = 0,
  [string]$DecisionRationale = ""
)

# Wrapper unico de apply por shard (plano 3 fases Codex 2026-04-24).
# Enforca:
#   - limite <= 50000 (MAX_SHARD_ITEMS em base.py + BULK_INGEST_MAX_ITEMS);
#   - env var de autorizacao (COMMERCE_APPLY_AUTHORIZED_<SRC>=1);
#   - validator FULL antes de qualquer apply;
#   - anti-reprocessamento por artifact_sha256 no run_manifest.jsonl;
#   - append automatico no manifest ao fim;
#   - extrai apply_run_id do summary.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logDir = Join-Path $repoRoot 'reports\data_ops_scheduler'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $repoRoot

# --- Gate: limite <= MAX_SHARD_ITEMS
if ($Limit -gt 50000) {
  Write-Host "ABORT: Limit=$Limit excede MAX_SHARD_ITEMS=50000 (plano 3 fases)."
  exit 7
}
if ($Limit -le 0) {
  Write-Host "ABORT: Limit=$Limit invalido."
  exit 7
}

# --- Gate: env var de autorizacao (so pra apply; dry-run pula)
if (-not $DryRun) {
  $envName = "COMMERCE_APPLY_AUTHORIZED_" + $Source.ToUpper()
  $envValue = [System.Environment]::GetEnvironmentVariable($envName, 'Process')
  if ($envValue -ne '1') {
    Write-Host "ABORT: $envName != 1. Setar antes: `$env:$envName = '1'"
    exit 2
  }
}

# --- Gate: ArtifactDir existe
$artifactPath = Join-Path $repoRoot $ArtifactDir
if (-not (Test-Path $artifactPath)) {
  Write-Host "ABORT: ArtifactDir nao existe: $artifactPath"
  exit 3
}

# --- Step: Validator FULL
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$validatorLog = Join-Path $logDir "${timestamp}_apply_${ShardId}_validator.log"
Write-Host "==> Validator FULL: $artifactPath (familia=$ExpectedFamily)"
& $python 'scripts/data_ops_producers/validate_commerce_artifact.py' `
  --artifact-dir $artifactPath `
  --expected-family $ExpectedFamily 2>&1 | Tee-Object -FilePath $validatorLog
if ($LASTEXITCODE -ne 0) {
  Write-Host "ABORT: validator FULL falhou (exit=$LASTEXITCODE). Ver $validatorLog"
  exit $LASTEXITCODE
}

# --- Step: compute artifact_sha256 do JSONL mais recente
$latestJsonl = Get-ChildItem -Path $artifactPath -Filter '*.jsonl' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $latestJsonl) {
  Write-Host "ABORT: nenhum .jsonl em $artifactPath"
  exit 3
}
$artifactSha = & $python 'scripts/data_ops_producers/hash_artifact.py' $latestJsonl.FullName
$artifactSha = $artifactSha.Trim()
if (-not $artifactSha -or $artifactSha.Length -lt 40) {
  Write-Host "ABORT: hash invalido: '$artifactSha'"
  exit 3
}
Write-Host "==> artifact_sha256=$artifactSha"
Write-Host "==> artifact=$($latestJsonl.Name)"

# --- Step: anti-reprocessamento (checa manifest)
$manifestPath = Join-Path $repoRoot 'reports\subida_vinhos_20260424\run_manifest.jsonl'
if ((Test-Path $manifestPath) -and (-not $DryRun)) {
  $lines = Get-Content $manifestPath
  foreach ($line in $lines) {
    if (-not $line.Trim()) { continue }
    try {
      $row = $line | ConvertFrom-Json
    } catch {
      continue
    }
    if ($row.artifact_sha256 -eq $artifactSha -and $row.status -eq 'PASS') {
      Write-Host "ABORT: artifact $artifactSha ja foi aplicado com PASS (shard=$($row.shard_id), apply_run_id=$($row.apply_run_id))."
      exit 5
    }
  }
}

# --- Step: set env var ARTIFACT_DIR para forcar runner a ler deste shard
# Runner chama _tier_artifact_dir(family) que le <FAMILY>_ARTIFACT_DIR env.
# Para amazon_mirror: AMAZON_MIRROR_ARTIFACT_DIR. Para amazon_legacy: nao ha
# override, usa _collect_winegod_candidates (le winegod_db direto).
$artifactEnvName = switch ($ExpectedFamily) {
  'tier1' { 'TIER1_ARTIFACT_DIR' }
  'tier2' { 'TIER2_ARTIFACT_DIR' }
  'amazon_mirror_primary' { 'AMAZON_MIRROR_ARTIFACT_DIR' }
  default { $null }
}
if ($artifactEnvName) {
  [System.Environment]::SetEnvironmentVariable($artifactEnvName, $artifactPath, 'Process')
  Write-Host "==> $artifactEnvName=$artifactPath"
}

# --- Step: run (dry-run ou apply)
$startedAt = Get-Date -Format 'o'
$mode = if ($DryRun) { '--dry-run' } else { '--apply' }
$modeLabel = $mode.Trim('-')
$stepLog = Join-Path $logDir "${timestamp}_apply_${ShardId}_${modeLabel}.log"
Write-Host "==> runner source=$Source limit=$Limit $mode"
& $python '-m' 'sdk.plugs.commerce_dq_v3.runner' `
  --source $Source `
  --limit $Limit `
  $mode 2>&1 | Tee-Object -FilePath $stepLog
$runnerExit = $LASTEXITCODE
$finishedAt = Get-Date -Format 'o'

if ($runnerExit -ne 0) {
  Write-Host "ABORT: runner falhou (exit=$runnerExit). Ver $stepLog"
  # Nao anexar PASS ao manifest; anexar FAIL.
  $status = "FAIL"
} else {
  $logContent = Get-Content $stepLog -Raw
  if ($logContent -match 'BLOCKED_QUEUE_EXPLOSION') {
    Write-Host "ABORT: BLOCKED_QUEUE_EXPLOSION."
    $status = "ABORT"
  } else {
    $status = "PASS"
  }
}

# --- Step: extrair apply_run_id do summary
# Runner escreve summary em reports\data_ops_plugs_staging\<ts>_commerce_<source>_summary.md
$stagingDir = Join-Path $repoRoot 'reports\data_ops_plugs_staging'
$latestSummary = Get-ChildItem -Path $stagingDir -Filter "*_commerce_${Source}_summary.md" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$applyRunId = ''
$metricsJson = '{}'
if ($latestSummary) {
  $summaryContent = Get-Content $latestSummary.FullName -Raw
  if ($summaryContent -match 'run_id:\s*`([^`]+)`') {
    $applyRunId = $matches[1]
  }
  if ($summaryContent -match '```json\s*\r?\n([\s\S]*?)\r?\n```') {
    $resultJson = $matches[1]
    try {
      $parsed = $resultJson | ConvertFrom-Json
      $metricsObj = @{
        received = $parsed.received
        valid = $parsed.valid
        inserted = $parsed.inserted
        updated = $parsed.updated
        sources_inserted = $parsed.sources_inserted
        sources_updated = $parsed.sources_updated
        filtered_notwine_count = $parsed.filtered_notwine_count
        rejected_count = $parsed.rejected_count
        sources_rejected_count = $parsed.sources_rejected_count
        would_enqueue_review = $parsed.would_enqueue_review
        enqueue_for_review_count = $parsed.enqueue_for_review_count
        blocked = $parsed.blocked
        errors = $parsed.errors
      }
      $metricsJson = $metricsObj | ConvertTo-Json -Compress -Depth 5
    } catch {
      $metricsJson = '{}'
    }
  }
}

# --- Step: append no run_manifest.jsonl
$appendLog = Join-Path $logDir "${timestamp}_apply_${ShardId}_manifest_append.log"
$phaseForManifest = if ($DryRun) { "dryrun_${Phase}" } else { $Phase }
$argsList = @(
  'scripts/data_ops_producers/append_run_manifest.py',
  '--phase', $phaseForManifest,
  '--source', $Source,
  '--shard-id', $ShardId,
  '--country', $Country,
  '--source-table', $SourceTable,
  '--min-fonte-id', $MinFonteId,
  '--max-fonte-id', $MaxFonteId,
  '--expected-rows', $ExpectedRows,
  '--artifact-path', $latestJsonl.FullName,
  '--artifact-sha256', $artifactSha,
  '--apply-run-id', $applyRunId,
  '--status', $status,
  '--started-at', $startedAt,
  '--finished-at', $finishedAt,
  '--metrics-json', $metricsJson,
  '--decision-rationale', $DecisionRationale
)
& $python @argsList 2>&1 | Tee-Object -FilePath $appendLog

Write-Host ""
Write-Host "==> shard=$ShardId status=$status apply_run_id=$applyRunId"
Write-Host "==> artifact_sha256=$artifactSha"
Write-Host "==> log=$stepLog"
Write-Host "==> manifest_append=$appendLog"

if ($status -eq "PASS") { exit 0 }
if ($status -eq "FAIL") { exit $runnerExit }
exit 4
