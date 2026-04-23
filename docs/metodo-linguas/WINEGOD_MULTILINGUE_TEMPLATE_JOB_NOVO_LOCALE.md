# WINEGOD MULTILINGUE - TEMPLATE DE JOB PARA NOVO LOCALE

Status: template operacional
Uso: copiar este arquivo para `reports/WINEGOD_<JOB_NAME>_PLANO_EXECUCAO.md` e substituir os placeholders antes de iniciar.

---

## 0. Placeholders

Preencher antes de executar:

```text
<JOB_NAME>       = exemplo: DE_DE_ONDA
<LOCALE>         = exemplo: de-DE
<LOCALE_SHORT>   = exemplo: de
<SOURCE_LOCALE>  = exemplo: en-US
<COUNTRY_ISO>    = exemplo: DEFAULT ou DE
<LOCALE_CLASS>   = A_VARIANTE | B_LATINO | C_SCRIPT_DISTANTE | D_RTL_OU_LEGAL_SENSIVEL
<FALLBACK_CHAIN> = exemplo: de-DE -> en-US -> pt-BR
<PROD_URL>       = exemplo: https://chat.winegod.ai
<API_BASE>       = exemplo: https://winegod-app.onrender.com
<SMOKE_SHARE_ID> = id real de um share publico existente para testar /<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>
<SOURCE_REPO_ROOT> = exemplo: C:\winegod-app
<WORKTREE_ROOT>    = exemplo: C:\winegod-app-i18n-DE_DE_ONDA
<REPO_ROOT_DA_EXECUCAO> = <SOURCE_REPO_ROOT> se usar branch no clone principal, ou <WORKTREE_ROOT> se usar worktree
```

---

## 1. Ficha do job

- Job: `<JOB_NAME>`
- Locale alvo: `<LOCALE>`
- Prefixo publico: `/<LOCALE_SHORT>`
- Source locale: `<SOURCE_LOCALE>`
- Fallback chain: `<FALLBACK_CHAIN>`
- Pais/matriz legal: `<COUNTRY_ISO>`
- Classe do locale: `<LOCALE_CLASS>`
- Escopo: abrir novo locale do zero ate producao/canary
- Fora de escopo: deploy nao autorizado, mudanca remota sem O1/Ops, feature flags reais sem etapa F9

---

## 2. Artefatos que este job deve gerar

Obrigatorios:

- `reports/WINEGOD_<JOB_NAME>_DECISIONS.md`
- `reports/WINEGOD_<JOB_NAME>_REVIEW_CLAUDE.md`
- `reports/WINEGOD_<JOB_NAME>_REVIEW_CODEX.md`
- `reports/WINEGOD_<JOB_NAME>_REVIEW_CONSOLIDADO.md`
- `reports/WINEGOD_<JOB_NAME>_RESULTADO.md`
- `reports/WINEGOD_<JOB_NAME>_HANDOFF_FINAL.md`
- append-only em `reports/i18n_execution_log.md`
- `reports/_backup_<JOB_NAME>/`

Condicionais:

- `shared/legal/<COUNTRY_ISO>/<LOCALE>/*.md`
- snapshots Playwright para `<LOCALE>`
- scripts temporarios de smoke em `reports/_backup_<JOB_NAME>/`

---

## 3. F0 - Preflight

Objetivo: provar que o trabalho comeca limpo.

Abordagem oficial:

- Default: branch dedicada `i18n/<JOB_NAME>-exec` no clone principal.
- Alternativa: worktree dedicada criada a partir de `main` quando o clone principal estiver sujo por trabalho nao relacionado.
- Nao executar locale job direto em `main`.
- Nao continuar se o write-set de producao tiver tracked modified ou untracked.

Se for usar worktree dedicada:

```powershell
$job = "<JOB_NAME>"
$sourceRepoRoot = "<SOURCE_REPO_ROOT>"  # exemplo: C:\winegod-app
$branch = "i18n/$job-exec"
$worktree = "<WORKTREE_ROOT>"          # exemplo: C:\winegod-app-i18n-$job

Set-Location $sourceRepoRoot
git worktree add -b $branch $worktree main
$repoRoot = $worktree
```

Se for usar branch no clone principal, ou depois de entrar na worktree dedicada, rodar:

```powershell
$repoRoot = "<REPO_ROOT_DA_EXECUCAO>"  # branch no clone principal ou worktree dedicada
Set-Location $repoRoot

$job = "<JOB_NAME>"
$branch = "i18n/$job-exec"
$backup = "reports/_backup_$job"
$prodPaths = @("frontend", "backend", "shared", "tools", "scripts")
New-Item -ItemType Directory -Force -Path $backup | Out-Null

git status --short | Out-File "$backup/git_status_initial.txt" -Encoding utf8
git branch --show-current | Out-File "$backup/git_branch_initial.txt" -Encoding utf8
git ls-files --others --exclude-standard -- frontend/ backend/ shared/ tools/ scripts/ |
  Out-File "$backup/untracked_production_initial.txt" -Encoding utf8
git status --porcelain -- $prodPaths |
  Out-File "$backup/dirty_production_initial.txt" -Encoding utf8

$dirtyProd = git status --porcelain -- $prodPaths
if ($dirtyProd) {
  Write-Output "ABORT: production write-set is dirty:"
  Write-Output $dirtyProd
  Write-Output "Resolve by committing unrelated work separately, using a dedicated worktree, or removing disposable generated files only after verification."
  exit 1
}

$current = git branch --show-current
if ($current -eq "main") {
  git switch -c $branch
} elseif ($current -ne $branch) {
  Write-Output "ABORT: current branch is '$current', expected '$branch'."
  exit 1
}

@"

## $(Get-Date -Format 'yyyy-MM-dd') - <JOB_NAME> - F0 iniciado
- Locale: <LOCALE>
- Branch/worktree: $branch
- Repo root: $repoRoot
- Dirty production write-set: OK
- Backup: $backup
"@ | Add-Content -LiteralPath "reports/i18n_execution_log.md" -Encoding utf8
```

Baseline tecnico:

```powershell
$repoRoot = "<REPO_ROOT_DA_EXECUCAO>"
$frontendRoot = Join-Path $repoRoot "frontend"
$backup = Join-Path $repoRoot "reports/_backup_<JOB_NAME>"

Set-Location $repoRoot
node tools/i18n_parity.mjs *> "reports/_backup_<JOB_NAME>/parity_baseline.txt"

Set-Location $frontendRoot
Remove-Item -LiteralPath ".next" -Recurse -Force -ErrorAction SilentlyContinue
npm run build *> (Join-Path $backup "build_baseline.txt")
Set-Location $repoRoot
```

Criterio de saida:

- zero untracked de producao
- zero tracked modified no write-set de producao
- branch dedicada ou worktree dedicada ativa
- baseline salvo
- build baseline conhecido
- append inicial em `reports/i18n_execution_log.md`

Se o repo estiver sujo:

- nao usar stash cego
- nao apagar arquivo sem entender origem
- se a sujeira for trabalho nao relacionado, criar worktree dedicada a partir de `main`
- se a sujeira for gerada por teste/build, remover apenas depois de confirmar que e descartavel

---

## 4. F1 - Preparar estrutura para `<LOCALE>`

Checklist:

- [ ] `frontend/messages/<LOCALE>.json` sera criado a partir de `<SOURCE_LOCALE>`.
- [ ] `frontend/i18n/routing.ts` reconhece `<LOCALE>` ou sera atualizado.
- [ ] `frontend/i18n/request.ts` reconhece fallback `<FALLBACK_CHAIN>` ou sera atualizado.
- [ ] `frontend/lib/i18n/fallbacks.ts` reconhece `<LOCALE>` ou sera atualizado.
- [ ] `frontend/lib/i18n/formatters.ts` tem default coerente de moeda/data para `<LOCALE>` ou fallback documentado.
- [ ] `frontend/middleware.ts` reconhece `/<LOCALE_SHORT>` nas rotas publicas relevantes.
- [ ] `shared/i18n/markets.json` tem pais/mercado necessario.
- [ ] `tools/i18n_parity.mjs` consegue validar `<LOCALE>`.
- [ ] specs Playwright i18n incluem `<LOCALE>` quando aplicavel.

Saida:

- write-set estrutural definido
- nenhum arquivo editorial traduzido antes do gate estrutural

---

## 5. F2 - Criar snapshot base

```powershell
$repoRoot = "<REPO_ROOT_DA_EXECUCAO>"
Set-Location $repoRoot
Copy-Item -LiteralPath "frontend/messages/<SOURCE_LOCALE>.json" -Destination "frontend/messages/<LOCALE>.json"
node tools/i18n_parity.mjs
```

Se parity falhar porque `<LOCALE>` nao foi incluido no validador, corrigir o validador/config primeiro e repetir.

Criterio de saida:

- `frontend/messages/<LOCALE>.json` existe
- parity exit 0

---

## 6. F3 - Traducao inicial

Prompt padrao para IA tradutora:

```text
Voce vai traduzir o JSON de mensagens do WineGod de <SOURCE_LOCALE> para <LOCALE>.

Regras bloqueantes:
- Preserve exatamente placeholders ICU como {name}, {count}, {remaining}.
- Preserve exatamente rich tags como <b>, </b>, <terms>, </terms>, <privacy>, </privacy>.
- Preserve plural/select branches.
- Nao traduza nomes de vinho, Baco, winegod.ai, marcas ou itens DNT.
- Nao use jargao tecnico de engenharia em copy de usuario.
- O texto deve soar nativo em <LOCALE>, nao como app brasileiro traduzido.
- Respeite a variante regional de <LOCALE>.
- Retorne somente JSON valido, sem comentario.

Arquivo fonte:
<colar frontend/messages/<SOURCE_LOCALE>.json>
```

Apos salvar a resposta:

```powershell
$repoRoot = "<REPO_ROOT_DA_EXECUCAO>"
$frontendRoot = Join-Path $repoRoot "frontend"

Set-Location $repoRoot
node tools/i18n_parity.mjs
Set-Location $frontendRoot
npm run build
Set-Location $repoRoot
```

Criterio de saida:

- JSON valido
- parity OK
- build OK

---

## 7. F4 - Cross-review editorial

Executar 2 revisoes independentes.

Prompt padrao:

```text
Voce vai revisar frontend/messages/<LOCALE>.json como usuario nativo exigente de <LOCALE>.

Classifique cada achado:
- Classe: bug | editorial | residual | decisao operacional
- Severidade: S1 | S2 | S3 | S4

Procure:
- vazamento de outro idioma
- calque de metafora ou construcao
- jargao tecnico
- termo nao nativo
- pontuacao/diacritico incorreto
- inconsistencia entre chaves
- texto legal/age gate estranho
- copy que parece traducao literal

Entregue tabela:
| ID | Severidade | Classe | Chave | Texto atual | Problema | Sugestao |

Veredito final:
- PASSA
- PASSA COM AJUSTES
- NAO PASSA

Arquivo:
<colar frontend/messages/<LOCALE>.json>
```

Salvar:

- `reports/WINEGOD_<JOB_NAME>_REVIEW_CLAUDE.md`
- `reports/WINEGOD_<JOB_NAME>_REVIEW_CODEX.md`
- `reports/WINEGOD_<JOB_NAME>_REVIEW_CONSOLIDADO.md`

Regra:

- corrigir todo S1
- corrigir ou decidir todo S2
- S3 pode ser backlog se documentado
- S4 nao bloqueia

---

## 8. F5 - Legal e age gate

Preencher `reports/WINEGOD_<JOB_NAME>_DECISIONS.md`.

O1:

- [ ] A - legal proprio existe e sera publicado.
- [ ] B - legal proprio nao existe; `<LOCALE>` fica fora de enabled_locales publico.
- [ ] C - legal sera publicado como traducao operacional, sem revisao juridica local, com risco aceito.

Checklist:

- [ ] `privacy.md`
- [ ] `terms.md`
- [ ] `data-deletion.md`
- [ ] `cookies.md`
- [ ] redirects legacy coerentes
- [ ] links do age gate coerentes

---

## 9. F6 - QA determinista e visual

```powershell
$repoRoot = "<REPO_ROOT_DA_EXECUCAO>"
$frontendRoot = Join-Path $repoRoot "frontend"

Set-Location $repoRoot
node tools/i18n_parity.mjs

Set-Location $frontendRoot
Remove-Item -LiteralPath ".next" -Recurse -Force -ErrorAction SilentlyContinue
npm run build
npx playwright test tests/i18n/ --project=desktop-chromium
Set-Location $repoRoot
```

Se houver snapshots novos:

- confirmar que representam `<LOCALE>`
- confirmar que hashes/snapshots nao sao identicos indevidamente a outro locale
- registrar paths no resultado

---

## 10. F7 - Release decisions

Preencher:

- O1 legal
- O2 OG image
- O3 OG alt/static
- O4 classe do locale e necessidade de humano nativo
- O5 canary strategy
- O6 rollback

Sem decisions preenchido, nao ativar.

---

## 11. F8 - Ativacao/canary

Nao executar sem autorizacao operacional.

Checklist antes de ativar:

- [ ] O1 permite ativacao publica.
- [ ] `feature_flags.enabled_locales` pode receber `<LOCALE>`.
- [ ] Vercel `NEXT_PUBLIC_ENABLED_LOCALES` sera atualizado.
- [ ] Redeploy frontend sera feito.
- [ ] rollback esta documentado.
- [ ] `reports/i18n_execution_log.md` sera atualizado antes e depois do canary.

Pre-check static/dynamic:

```powershell
$env:API_BASE = "<API_BASE>"
$env:NEXT_PUBLIC_ENABLED_LOCALES = '["pt-BR","en-US","es-419","fr-FR","<LOCALE>"]'
node tools/enabled_locales_check.mjs
Remove-Item Env:\API_BASE -ErrorAction SilentlyContinue
Remove-Item Env:\NEXT_PUBLIC_ENABLED_LOCALES -ErrorAction SilentlyContinue
```

Esse pre-check nao fecha o gate final. Ele usa uma lista esperada local e nao prova que o frontend publicado recebeu o novo build-time env. O fechamento final exige o smoke de producao da F9, incluindo `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>`.

---

## 12. F9 - Smoke de producao

```powershell
$base = "<PROD_URL>"
$apiBase = "<API_BASE>"
$locale = "<LOCALE>"
$short = "<LOCALE_SHORT>"
$shareId = "<SMOKE_SHARE_ID>"
$cookie = "wg_age_verified=BR:18:2026-01-01T00:00:00Z; wg_locale_choice=$locale"
$paths = @("/", "/ajuda", "/plano", "/conta", "/favoritos", "/privacy", "/terms", "/data-deletion")

if ($shareId -like "<*>" -or [string]::IsNullOrWhiteSpace($shareId)) {
  Write-Error "ABORT: configure <SMOKE_SHARE_ID> with a real public share id."
  exit 1
}

$config = Invoke-RestMethod -Uri "$apiBase/api/config/enabled-locales" -TimeoutSec 20
if ($config.enabled_locales -notcontains $locale) {
  Write-Error "FAIL: backend dynamic enabled_locales does not include $locale"
  exit 1
}

foreach ($path in $paths) {
  $url = "$base$path"
  try {
    $resp = Invoke-WebRequest -Uri $url -Headers @{ Cookie = $cookie } -MaximumRedirection 5 -TimeoutSec 20 -ErrorAction Stop
    Write-Output "$($resp.StatusCode) $path"
  } catch {
    $code = 0
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    Write-Output "$code $path"
    exit 1
  }
}

$prefixed = @("/ajuda", "/age-verify", "/privacy")
foreach ($path in $prefixed) {
  $url = "$base/$short$path"
  $resp = Invoke-WebRequest -Uri $url -Headers @{ Cookie = "wg_age_verified=BR:18:2026-01-01T00:00:00Z" } -MaximumRedirection 5 -TimeoutSec 20
  Write-Output "$($resp.StatusCode) /$short$path"
}

$shareUrl = "$base/$short/c/$shareId"
try {
  $shareResp = Invoke-WebRequest -Uri $shareUrl -Headers @{ Cookie = $cookie } -MaximumRedirection 0 -TimeoutSec 20 -ErrorAction Stop
  $shareCode = [int]$shareResp.StatusCode
  $shareLocation = $shareResp.Headers.Location
} catch {
  $shareCode = 0
  $shareLocation = ""
  if ($_.Exception.Response) {
    $shareCode = [int]$_.Exception.Response.StatusCode
    $shareLocation = $_.Exception.Response.Headers["Location"]
  }
}

Write-Output "$shareCode /$short/c/$shareId"
if ($shareCode -eq 404 -or $shareCode -ge 500) {
  Write-Error "FAIL: prefixed share route failed."
  exit 1
}
if (($shareCode -ge 300 -and $shareCode -lt 400) -and ($shareLocation -match "(^|https?://[^/]+)/c/$shareId($|[?#])")) {
  Write-Error "FAIL: share prefix was stripped. Published frontend may not have <LOCALE> enabled."
  exit 1
}
```

Spot check de conteudo:

```powershell
$expected = "<TERMO_LOCALIZADO_ESPERADO>"
$html = Invoke-WebRequest -Uri "$base/ajuda" -Headers @{ Cookie = $cookie } -TimeoutSec 20
if ($html.Content -notmatch [regex]::Escape($expected)) {
  Write-Error "FAIL: expected localized term not found: $expected"
  exit 1
}
```

---

## 13. F10 - Resultado e handoff

Gerar:

- `reports/WINEGOD_<JOB_NAME>_RESULTADO.md`
- `reports/WINEGOD_<JOB_NAME>_HANDOFF_FINAL.md`

Resultado precisa conter:

- docs e fontes usadas
- escopo executado
- arquivos alterados
- validacoes e outputs
- entradas feitas em `reports/i18n_execution_log.md`
- decisions finais
- residuais aceitos
- pendencias humanas residuais
- veredito final

Handoff precisa conter:

- estado atual
- como retomar
- o que esta ativo
- o que nao esta ativo
- rollback
- entradas append-only do log
- trabalho futuro opcional
