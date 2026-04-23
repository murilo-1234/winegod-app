param(
  [Parameter(Mandatory = $true)][string]$Manifest,
  [Parameter(Mandatory = $true)][string]$Workdir,
  [Parameter(Mandatory = $true)][string]$LogName,
  [switch]$Live,
  [string[]]$Command,
  [Parameter(ValueFromRemainingArguments = $true)][string[]]$RemainingCommand
)

$ErrorActionPreference = 'Stop'

if ((-not $Command -or $Command.Count -eq 0) -and $RemainingCommand) {
  $Command = $RemainingCommand
}

if (-not $Command -or $Command.Count -eq 0) {
  throw "Command is required after wrapper parameters."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$logPath = Join-Path $repoRoot "reports\data_ops_shadow\$LogName"

$args = @(
  (Join-Path $repoRoot 'scripts\data_ops_shadow\run_shadow.py'),
  '--manifest', $Manifest,
  '--workdir', $Workdir,
  '--log', $logPath
)

if (-not $Live) {
  $args += '--dry-run'
}

$args += '--'
$args += $Command

& $python @args
exit $LASTEXITCODE
