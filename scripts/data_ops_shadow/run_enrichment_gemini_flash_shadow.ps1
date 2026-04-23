param([switch]$Live)
$ErrorActionPreference = 'Stop'
# Observer READ-ONLY sobre artefatos locais. Gemini pago NAO e acionado aqui.
# A chamada real de Gemini esta fora do escopo desta sessao (CLAUDE.md R6).
& (Join-Path $PSScriptRoot 'invoke_shadow.ps1') `
  -Manifest 'C:\winegod-app\sdk\adapters\manifests\enrichment_gemini_flash.yaml' `
  -Workdir 'C:\winegod-app' `
  -LogName 'enrichment_gemini_flash_shadow.log' `
  -Live:$Live `
  -Command @('python', 'sdk/adapters/enrichment_gemini_observer.py', '--apply')
exit $LASTEXITCODE
