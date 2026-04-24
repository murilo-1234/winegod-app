param([switch]$Live)
$ErrorActionPreference = 'Stop'
# Feed primario Amazon via artefato do PC espelho.
# Le reports/data_ops_artifacts/amazon_mirror/<timestamp>_<run_id>.jsonl
# Contrato: docs/TIER_COMMERCE_CONTRACT.md
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\commerce_amazon_mirror_primary.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'commerce_amazon_mirror_primary_shadow.log' `
  -Live:$Live `
  -Command @('python', '-m', 'sdk.plugs.commerce_dq_v3.runner', '--source', 'amazon_mirror_primary', '--limit', '50', '--dry-run')
exit $LASTEXITCODE
