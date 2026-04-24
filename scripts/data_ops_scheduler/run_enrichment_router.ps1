param(
  [int]$Limit = 50
)

# Roda router em cima do staging mais recente de gemini_batch_reports.
# Gera buckets ready/uncertain/not_wine + retry/human queues + patch diff.

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
$logPath = Join-Path $logDir "${ts}_enrichment_router.log"

$script = @"
import json
from pathlib import Path
from sdk.plugs.enrichment.router import classify_batch
from sdk.plugs.enrichment import uncertain_queue, human_queue, not_wine_propagator as nwp

repo_root = Path(r'$repoRoot')
staging = repo_root / 'reports' / 'data_ops_plugs_staging'
latest = None
for p in sorted(staging.glob('*_gemini_batch_reports_enrichment.jsonl'),
                key=lambda x: x.stat().st_mtime, reverse=True):
    latest = p
    break

if not latest:
    print('[enrichment_router] sem staging jsonl - nada para classificar')
    raise SystemExit(0)

items = []
with latest.open('r', encoding='utf-8') as fh:
    for line in fh:
        line = line.strip()
        if line:
            items.append(json.loads(line))

items = items[:$Limit]
buckets = classify_batch(items)
print(f'[enrichment_router] source={latest.name} ready={len(buckets[\"ready\"])} '
      f'uncertain={len(buckets[\"uncertain\"])} not_wine={len(buckets[\"not_wine\"])}')

if buckets['uncertain']:
    uq = uncertain_queue.persist_queue(buckets['uncertain'])
    print(f'[enrichment_router] uncertain_queue={uq}')
if buckets['uncertain']:
    hq = human_queue.persist_queue(buckets['uncertain'])
    print(f'[enrichment_router] human_queue={hq}')
if buckets['not_wine']:
    result = nwp.propose_patch(buckets['not_wine'])
    patch = nwp.persist_patch(result)
    print(f'[enrichment_router] not_wine new_patterns={len(result.new_patterns)} patch={patch}')
"@

& $python -c "$script" 2>&1 | Tee-Object -FilePath $logPath
exit $LASTEXITCODE
