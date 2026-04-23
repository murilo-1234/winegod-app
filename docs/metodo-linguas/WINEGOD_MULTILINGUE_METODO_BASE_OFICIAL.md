# WINEGOD MULTILINGUE - METODO BASE OFICIAL

Data: 2026-04-23
Status: V2.1 pronta para congelar
Escopo: abrir um novo locale no WineGod do zero ate producao, com minimo improviso e maxima auditabilidade

---

## 1. Objetivo

Este documento e a regra mestre para qualquer novo locale do WineGod.

Ele transforma o aprendizado do H4 e do fechamento total do rollout atual em um metodo operacional, linear e replicavel. O objetivo nao e repetir a historia do H4, e sim preservar apenas o que virou regra reutilizavel.

O metodo vale para:

- novo idioma completo, como `de-DE`, `it-IT`, `ja-JP`, `zh-CN`
- variante de mercado, como `en-GB`, `es-ES`, `fr-CA`, `pt-PT`
- nova onda de endurecimento i18n quando um locale existe, mas ainda nao esta pronto para producao

O metodo nao vale para:

- ajuste isolado de 1 a 3 strings
- hotfix pequeno de copy
- polimento editorial sem impacto em estrutura, legal, QA ou release

---

## 2. Estado de referencia

O metodo parte do estado fechado em 2026-04-23:

- `pt-BR`, `en-US`, `es-419`, `fr-FR` sao os 4 locales ativos do rollout atual.
- A UI usa snapshots em `frontend/messages/*.json`.
- O gate estrutural principal e `node tools/i18n_parity.mjs`.
- O backend expoe a lista dinamica por `/api/config/enabled-locales`.
- A checagem de consistencia static/dynamic e `node tools/enabled_locales_check.mjs`.
- O release usa `feature_flags.enabled_locales` como fonte dinamica e `NEXT_PUBLIC_ENABLED_LOCALES` como build-time frontend.
- Legal, age gate, routing e smoke de producao sao gates obrigatorios.

Nota operacional: alguns artefatos atuais ainda sao especificos dos 4 locales iniciais. Quando abrir um novo locale, o job precisa tornar esses artefatos conscientes de `<LOCALE>` ou registrar explicitamente que eles foram adaptados.

---

## 3. Fontes que sustentam este metodo

O metodo V2.1 e autocontido no repo principal e em qualquer worktree dedicada criada a partir dele.

Documentos locais obrigatorios consolidados:

- `reports/WINEGOD_MULTILINGUE_METODO_LINEAR_LOCALE_NOVO_RUNBOOK.md`
- `reports/WINEGOD_MULTILINGUE_H4_METODO_REPLICAVEL_OUTRAS_LINGUAS_HANDOFF.md`
- `reports/i18n_execution_log.md`

Documentos complementares usados:

- `reports/WINEGOD_MULTILINGUE_PLANO_EXECUCAO_FECHAMENTO_TOTAL.md`
- `reports/WINEGOD_MULTILINGUE_PLANO_EXECUCAO_V2.5.md`
- `reports/WINEGOD_MULTILINGUE_HANDOFF_OFICIAL.md`
- `DEPLOY.md`

Referencia historica opcional:

- `C:\winegod-app-h4-closeout\reports\*`

Regra: nenhum operador futuro precisa ter `C:\winegod-app-h4-closeout` para usar o metodo. As licoes permanentes daquele fechamento foram copiadas para este pacote.

---

## 4. Regra central

Um locale so pode ir para producao quando os 6 blocos abaixo estiverem resolvidos:

1. Estrutura: chaves, placeholders, rich tags, plurais, routing e middleware coerentes.
2. Editorial: copy natural, sem vazamento de outro idioma, sem calque bloqueante.
3. Legal: docs e age gate coerentes com o locale publicado ou bloqueio consciente registrado.
4. QA: build frio, parity, Playwright i18n, smoke local e smoke de producao.
5. Release: `feature_flags.enabled_locales`, `NEXT_PUBLIC_ENABLED_LOCALES`, canary e rollback documentados.
6. Evidencia: append em `reports/i18n_execution_log.md`, decisions, resultado e handoff salvos em `reports/`.

Fallback silencioso nao conta como locale pronto.

---

## 5. Separacao obrigatoria

### 5.1 Regra universal

Todo job deve separar:

- Codigo estrutural: routing, middleware, config de locale, formatadores, error contracts.
- Conteudo editorial: `frontend/messages/<LOCALE>.json`, tom, naturalidade, DNT e glossary.
- Legal: `shared/legal/<COUNTRY_ISO>/<LOCALE>/*`, age gate e redirects legais.
- QA: parity, build, Playwright, visual, smoke.
- Release: flags, env var, canary, deploy, rollback.
- Documentacao: plano, decisions, resultado, handoff, logs.

Misturar essas trilhas e uma fonte de erro. Se um achado editorial bloquear release, ele deve ser registrado como editorial bloqueante, nao como "bug de routing". Se uma pendencia legal bloquear canary, ela deve ficar em O1, nao escondida em copy.

### 5.2 O que veio do H4 mas nao e universal

Estas coisas foram especificas do H4:

- fechar `es-419` e `fr-FR` ao mesmo tempo
- publicar legal ES/FR por traducao operacional sem revisao juridica local
- aceitar `O2=B` para OG em ingles especificamente em ES/FR
- usar canary comprimido para encerrar o rollout atual
- lidar com 4 hotfix-PRs causados por divida de untracked acumulada

Elas viraram aprendizado, mas nao devem ser copiadas mecanicamente para todo locale.

### 5.3 O que e universal

Estas regras valem sempre:

- F0 com branch/worktree dedicada e gate de dirty write-set antes de editar.
- Build final a frio, removendo `.next`.
- Parity estrutural antes e depois da traducao.
- Cross-review editorial por pelo menos 2 revisores independentes para novo idioma completo.
- O1 legal antes de ativar publicamente.
- Smoke de producao obrigatorio antes de declarar fechamento.
- Residual aceito precisa estar escrito, com dono e racional.

---

## 6. Classes de locale

### Classe A - Variante pequena

Exemplos: `en-GB`, `pt-PT`, `fr-CA`, `es-ES`.

Caracteristicas:

- idioma ja existe no produto ou e proximo de um existente
- risco estrutural baixo
- risco editorial medio
- risco legal depende do mercado

Default:

- source locale proximo, como `en-US` para `en-GB`
- cross-review IA pode bastar se nao houver mercado legal novo
- QA visual focado em rotas principais e legal

### Classe B - Novo idioma latino

Exemplos: `de-DE`, `it-IT`.

Caracteristicas:

- alfabeto latino
- sem RTL/CJK
- risco editorial medio/alto
- risco de texto longo em layout

Default:

- source locale `en-US`
- cross-review multi-IA obrigatorio
- humano nativo recomendado se o locale for mercado comercial importante
- pseudo-loc ou teste visual com textos longos recomendado

### Classe C - Novo idioma com script/convencao distante

Exemplos: `ja-JP`, `zh-CN`, `ko-KR`.

Caracteristicas:

- risco de tom, polidez, segmentacao e layout
- risco de validacao visual maior
- IA pode preservar estrutura, mas nao garante naturalidade

Default:

- cross-review IA obrigatorio
- humano nativo recomendado antes de producao publica
- smoke e QA visual devem ser tratados como gate forte

### Classe D - RTL ou juridicamente sensivel

Exemplos: `ar-*`, `he-*`, mercados com regulacao local pesada.

Caracteristicas:

- suporte RTL nao deve ser assumido
- risco legal pode bloquear release

Default:

- nao abrir sem plano especifico
- founder precisa assinar O1 antes de canary
- revisar gaps tecnicos antes de traducao

---

## 7. Fases oficiais

### F0 - Intake e preflight

Objetivo: provar que o job pode comecar sem herdar sujeira.

Abordagem oficial:

- Default: branch dedicada no clone principal, com nome `i18n/<JOB_NAME>-exec`.
- Alternativa oficial: worktree dedicada criada a partir de `main`, quando o clone principal esta ocupado por outro trabalho.
- Todos os comandos depois da escolha de branch/worktree devem usar `$repoRoot`, nunca assumir caminho fixo.
- Nunca executar job de locale diretamente em `main`.
- Nunca continuar se `frontend/`, `backend/`, `shared/`, `tools/` ou `scripts/` tiverem arquivos tracked modified ou untracked nao explicados.

Checklist minimo:

- `<LOCALE>`, `<LOCALE_SHORT>`, `<SOURCE_LOCALE>`, `<COUNTRY_ISO>`, `<JOB_NAME>` definidos.
- Classe do locale definida.
- Branch dedicada ou worktree dedicada definida.
- Worktree de execucao auditada.
- Baselines salvos em `reports/_backup_<JOB_NAME>/`.
- Nenhum arquivo de producao untracked.
- Nenhum tracked file modified no write-set de producao.
- Entrada inicial append-only em `reports/i18n_execution_log.md`.

Comandos PowerShell, opcao A - branch dedicada no clone principal:

```powershell
$job = "<JOB_NAME>"
$repoRoot = "<REPO_ROOT_DA_EXECUCAO>"  # exemplo: C:\winegod-app
$branch = "i18n/$job-exec"
$backup = "reports/_backup_$job"
$prodPaths = @("frontend", "backend", "shared", "tools", "scripts")

Set-Location $repoRoot
New-Item -ItemType Directory -Force -Path $backup | Out-Null

git status --short | Out-File "$backup/git_status_initial.txt" -Encoding utf8
git branch --show-current | Out-File "$backup/git_branch_initial.txt" -Encoding utf8
git ls-files --others --exclude-standard -- frontend/ backend/ shared/ tools/ scripts/ |
  Out-File "$backup/untracked_production_initial.txt" -Encoding utf8
git status --porcelain -- $prodPaths |
  Out-File "$backup/dirty_production_initial.txt" -Encoding utf8

$dirtyProd = git status --porcelain -- $prodPaths
if ($dirtyProd) {
  Write-Output "ABORT: production write-set is dirty. Resolve before opening <LOCALE>."
  Write-Output $dirtyProd
  Write-Output "Allowed fixes: commit unrelated work on its own branch, move to a dedicated worktree, or remove generated files only after confirming they are disposable."
  exit 1
}

$current = git branch --show-current
if ($current -eq "main") {
  git switch -c $branch
} elseif ($current -ne $branch) {
  Write-Error "ABORT: current branch is '$current', expected '$branch'. Switch to main and create the job branch, or use a dedicated worktree."
  exit 1
}

@"

## $(Get-Date -Format 'yyyy-MM-dd') - <JOB_NAME> - F0 iniciado
- Locale: <LOCALE>
- Execucao: branch dedicada $branch
- Repo root: $repoRoot
- Gate dirty production write-set: OK
- Backup: $backup
"@ | Add-Content -LiteralPath "reports/i18n_execution_log.md" -Encoding utf8
```

Comandos PowerShell, opcao B - worktree dedicada:

```powershell
$job = "<JOB_NAME>"
$sourceRepoRoot = "<SOURCE_REPO_ROOT>"  # exemplo: C:\winegod-app
$branch = "i18n/$job-exec"
$worktree = "<WORKTREE_ROOT>"          # exemplo: C:\winegod-app-i18n-$job
$repoRoot = $worktree

Set-Location $sourceRepoRoot
git worktree add -b $branch $worktree main
Set-Location $repoRoot

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
  Write-Output "ABORT: production write-set is dirty in dedicated worktree."
  Write-Output $dirtyProd
  exit 1
}

@"

## $(Get-Date -Format 'yyyy-MM-dd') - <JOB_NAME> - F0 iniciado
- Locale: <LOCALE>
- Execucao: worktree dedicada
- Repo root: $repoRoot
- Branch: $branch
- Gate dirty production write-set: OK
- Backup: $backup
"@ | Add-Content -LiteralPath "reports/i18n_execution_log.md" -Encoding utf8
```

Saida obrigatoria:

- branch `i18n/<JOB_NAME>-exec` ou worktree dedicada ativa
- baseline salvo
- dirty production write-set vazio
- primeira entrada em `reports/i18n_execution_log.md`
- nenhum inicio de traducao antes desse gate

Se o repo estiver sujo:

- nao fazer stash cego
- nao apagar arquivos sem entender a origem
- se for trabalho do usuario, parar o job e usar worktree dedicada
- se for gerado por teste/build, remover apenas depois de confirmar que e descartavel
- se for mudanca necessaria para o locale, ela so pode existir depois da branch/worktree dedicada e do baseline

### F1 - Ficha do locale

Objetivo: decidir o que esta sendo aberto.

Preencher:

- locale alvo
- prefixo publico
- source locale
- fallback chain
- pais legal
- tipo de locale
- risco legal
- risco editorial
- necessidade de revisor humano

Saida obrigatoria:

- template de job preenchido
- decisions preparado

### F2 - Preparacao estrutural

Objetivo: garantir que a arquitetura aceita o novo locale.

Checar:

- `frontend/messages/<LOCALE>.json`
- `frontend/i18n/routing.ts`
- `frontend/i18n/request.ts`
- `frontend/middleware.ts`
- `frontend/lib/i18n/fallbacks.ts`
- `frontend/lib/i18n/formatters.ts`
- `shared/i18n/markets.json`
- `tools/i18n_parity.mjs`
- specs em `frontend/tests/i18n/`

Regra:

- se um script estiver hardcoded para os 4 locales atuais, o job deve adapta-lo ou criar forma temporaria auditavel para incluir `<LOCALE>`.

### F3 - Criacao do snapshot de mensagens

Objetivo: criar o JSON do locale com estrutura identica ao source.

Comando base:

```powershell
Copy-Item -LiteralPath "frontend/messages/<SOURCE_LOCALE>.json" -Destination "frontend/messages/<LOCALE>.json"
node tools/i18n_parity.mjs
```

Se `tools/i18n_parity.mjs` ainda nao reconhecer `<LOCALE>`, esse e um bloqueio estrutural do job. Resolver antes de prosseguir.

### F4 - Populacao editorial

Objetivo: traduzir `frontend/messages/<LOCALE>.json` preservando estrutura.

Regras:

- preservar placeholders ICU exatamente
- preservar rich tags exatamente
- preservar branches plural/select
- nao traduzir nomes de vinho, marca, `winegod.ai`, Baco e DNT
- nao expor jargao tecnico para usuario final
- respeitar variante regional
- registrar prompt usado e resposta recebida

Saida obrigatoria:

- JSON valido
- parity OK
- build local OK

### F5 - Gate editorial universal

Objetivo: detectar calques, vazamentos e copy artificial.

Padrao minimo:

- 2 revisores independentes para novo idioma completo
- 1 revisor independente para variante pequena, salvo risco legal/comercial alto
- classificar cada achado como `bug`, `editorial`, `residual` ou `decisao operacional`
- classificar severidade como `S1`, `S2`, `S3`, `S4`

Regra de bloqueio:

- qualquer `S1` bloqueia
- qualquer `S2` precisa ser corrigido ou aceito explicitamente
- `S3` pode ir para backlog se nao afetar confianca
- `S4` nao bloqueia

### F6 - Gate legal e age gate

Objetivo: decidir se o locale pode ser publico legalmente.

O1 e obrigatorio:

- O1=A: legal proprio existe e sera publicado.
- O1=B: legal proprio nao existe; locale fica fora de `enabled_locales` publico.
- O1=C: legal publicado como traducao operacional, com risco aceito e sem revisao local.

Checar:

- `shared/legal/<COUNTRY_ISO>/<LOCALE>/privacy.md`
- `shared/legal/<COUNTRY_ISO>/<LOCALE>/terms.md`
- `shared/legal/<COUNTRY_ISO>/<LOCALE>/data-deletion.md`
- `shared/legal/<COUNTRY_ISO>/<LOCALE>/cookies.md`
- redirects legacy
- links do age gate

### F7 - QA determinista e visual

Objetivo: provar que o locale funciona em runtime.

Comandos PowerShell:

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

Gate minimo:

- parity exit 0
- build frio exit 0
- Playwright i18n exit 0 ou falhas explicadas e corrigidas
- screenshots visuais por locale nao podem ser identicos quando o conteudo deveria divergir

### F8 - Decisions de release

Objetivo: registrar decisoes antes de ativar.

Obrigatorio:

- O1 legal
- O2 OG image
- O3 OG alt/static residual
- fonte de locale/fallback
- canary strategy
- rollback owner

Sem decisions preenchido, nao ativar.

### F9 - Ativacao e canary

Objetivo: ativar o locale com rollback claro.

Regra:

- nao editar producao sem autorizacao operacional explicita no job
- `feature_flags.enabled_locales` e fonte dinamica
- `NEXT_PUBLIC_ENABLED_LOCALES` exige rebuild/redeploy frontend
- Vercel dashboard pode ser intervencao humana inevitavel
- override local de `NEXT_PUBLIC_ENABLED_LOCALES` nao prova frontend publicado

Verificacao antes do deploy ou logo apos alterar flags dinamicas:

```powershell
$env:NEXT_PUBLIC_ENABLED_LOCALES='["pt-BR","en-US","es-419","fr-FR","<LOCALE>"]'
node tools/enabled_locales_check.mjs
Remove-Item Env:\NEXT_PUBLIC_ENABLED_LOCALES -ErrorAction SilentlyContinue
```

Essa verificacao prova apenas que a lista esperada bate com o backend dinamico. Ela nao fecha o gate final sozinha, porque o frontend publicado pode ainda estar rodando um build antigo sem `<LOCALE>` em `NEXT_PUBLIC_ENABLED_LOCALES`.

Saida obrigatoria de F9:

- evidencia da alteracao dinamica em `feature_flags.enabled_locales`, quando aplicavel
- evidencia de update de `NEXT_PUBLIC_ENABLED_LOCALES` no Vercel, quando aplicavel
- id, URL ou timestamp do redeploy frontend
- append em `reports/i18n_execution_log.md` com status da ativacao

### F10 - Smoke de producao

Objetivo: nao declarar fechamento sem validar a superficie real publicada.

Este gate existe porque o backend dinamico pode estar correto enquanto o frontend publicado ainda esta com build-time env antigo. O smoke final precisa provar os dois lados:

- runtime dinamico: backend retorna `<LOCALE>` em `/api/config/enabled-locales`
- build publicado: rotas prefixadas reais do frontend publicado aceitam `/<LOCALE_SHORT>`
- share publicado: `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>` nao e 404/5xx e nao perde o prefixo por fallback de locale desligado

PowerShell base:

```powershell
$base = "https://chat.winegod.ai"
$apiBase = "https://winegod-app.onrender.com"
$locale = "<LOCALE>"
$short = "<LOCALE_SHORT>"
$shareId = "<SMOKE_SHARE_ID_VALIDO>"
$cookie = "wg_age_verified=BR:18:2026-01-01T00:00:00Z; wg_locale_choice=$locale"
$paths = @("/", "/ajuda", "/plano", "/conta", "/favoritos", "/privacy", "/terms", "/data-deletion")

if ($shareId -like "<*>" -or [string]::IsNullOrWhiteSpace($shareId)) {
  Write-Error "ABORT: configure a real public share id in <SMOKE_SHARE_ID_VALIDO>."
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
  Write-Error "FAIL: prefixed share route is not published correctly."
  exit 1
}
if (($shareCode -ge 300 -and $shareCode -lt 400) -and ($shareLocation -match "(^|https?://[^/]+)/c/$shareId($|[?#])")) {
  Write-Error "FAIL: prefixed share route redirected to unprefixed share. This suggests published frontend does not accept $locale."
  exit 1
}
```

Gate:

- zero 5xx
- zero 404 em rotas principais
- backend dinamico inclui `<LOCALE>`
- frontend publicado responde rotas prefixadas `/<LOCALE_SHORT>/...`
- share prefixado real `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>` validado
- conteudo localizado visivel em `/ajuda`
- legal correto para O1 escolhido
- append final em `reports/i18n_execution_log.md`

### F11 - Fechamento

Objetivo: deixar a proxima pessoa capaz de auditar sem memoria do chat.

Arquivos minimos:

- `reports/WINEGOD_<JOB_NAME>_RESULTADO.md`
- `reports/WINEGOD_<JOB_NAME>_HANDOFF_FINAL.md`
- bloco de decisions atualizado
- evidencias ou links para logs de QA

---

## 8. Gates oficiais

### Gate estrutural universal

Passa somente se:

- `<LOCALE>.json` existe
- parity estrutural passa
- placeholders/tags/plurals batem
- middleware/routing conhece o locale ou nao precisa conhecer por desenho documentado
- fallback chain esta definida

### Gate editorial universal

Passa somente se:

- 0 S1
- 0 S2 sem correcao ou decisao explicita
- DNT preservado
- variant/regiao respeitada
- calques conhecidos revisados

### Gate legal universal

Passa somente se:

- O1 preenchido
- age gate aponta para docs coerentes
- privacy/terms/data-deletion/cookies resolvem como esperado
- ausencia de revisao juridica local esta registrada quando aplicavel

### Gate de QA universal

Passa somente se:

- parity OK
- build frio OK
- Playwright i18n OK
- smoke local OK quando aplicavel
- screenshot/hash nao mascara fallback indevido

### Gate de release universal

Passa somente se:

- static esperado e dynamic enabled locales batem como pre-check
- frontend publicado foi redeployado depois de alterar `NEXT_PUBLIC_ENABLED_LOCALES`
- smoke de rota prefixada publicada prova que o build ativo conhece `<LOCALE>`
- rollback documentado
- deploy/redeploy necessario executado
- O2/O3 registrados

### Gate de canary universal

Passa somente se:

- canary ativado no escopo decidido
- smoke de producao verde
- `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>` validado em producao
- logs ou observabilidade checados quando disponiveis
- residual aceito registrado
- append-only log atualizado

---

## 9. Evidencias obrigatorias

Todo resultado final precisa conter:

- hash da branch/commit ou indicacao de que nao houve commit
- `git status --short` inicial e final
- saida resumida de `node tools/i18n_parity.mjs`
- saida resumida de build frio
- saida resumida de Playwright i18n
- saida de `node tools/enabled_locales_check.mjs` como pre-check quando houver ativacao
- prova de frontend publicado: id/URL/timestamp do deploy Vercel ou header de resposta em producao
- smoke de producao por rota quando houver deploy
- smoke da rota share prefixada `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>`
- entradas append-only em `reports/i18n_execution_log.md`
- decisions O1/O2/O3
- lista de residuais aceitos
- pendencias humanas residuais

Momentos minimos de append em `reports/i18n_execution_log.md`:

- F0 aprovado ou abortado
- gate estrutural/editorial concluido
- decisions O1/O2/O3 preenchidas
- ativacao/canary iniciada ou explicitamente nao executada
- smoke final aprovado/falhou
- fechamento/handoff emitido

---

## 10. Intervencoes humanas inevitaveis

Nao parar o job por elas se for possivel avancar em outras trilhas. Registrar no fim.

Humanas inevitaveis:

- O1 quando envolve risco legal/comercial.
- Acesso a dashboard Vercel quando `NEXT_PUBLIC_ENABLED_LOCALES` precisa mudar.
- Manual Redeploy quando a env var build-time muda.
- Credenciais ou secrets ausentes.
- Revisao juridica local quando o founder exigir mercado comercial regulado.
- Revisor nativo humano para Classe C/D ou mercado de receita alta.

Nao humanas:

- parity
- build
- Playwright
- smoke local
- producao de templates
- consolidacao de achados IA
- registro de resultado/handoff

---

## 11. Defaults oficiais

Defaults, salvo decisao diferente:

- `SOURCE_LOCALE=en-US` para idioma novo.
- fallback chain `<LOCALE> -> en-US -> pt-BR`.
- O2 default: aceitar OG em ingles como residual para primeiro canary, se nao houver regressao de uso.
- O3 default: aceitar alt/static OG em ingles quando a limitacao do runtime continuar existindo.
- Canary default: ativacao fechada ou gradual, nunca declarar full rollout antes do smoke.
- Editor default: cross-review multi-IA; humano nativo e escalacao, nao requisito para todo caso.
- Windows default: comandos oficiais em PowerShell.

---

## 12. Anti-padroes bloqueados

Nao fazer:

- abrir locale so copiando `en-US` sem revisar
- ativar locale sem legal/O1
- confiar em build incremental
- declarar pronto sem smoke de producao
- deixar arquivo de producao untracked
- deixar tracked file modificado no write-set de producao antes de F0
- aceitar `enabled_locales_check` com override local como prova final de frontend publicado
- fechar canary sem testar `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>`
- misturar change de app com change de metodo sem necessidade
- pedir microconfirmacoes quando a decisao e inferivel
- esconder risco juridico como "residual editorial"
- deixar decisions, append-only log e handoff para depois

---

## 13. Criterio de pronto

Um novo locale esta pronto quando:

- gates estrutural, editorial, legal, QA, release e canary passaram
- evidencias foram salvas
- decisions foram preenchidas
- `reports/i18n_execution_log.md` foi atualizado em append-only
- resultado final foi gerado
- handoff final permite retomada sem memoria do chat
- gaps remanescentes estao isolados

Se qualquer item acima faltar, o locale pode estar "implementado", mas nao esta fechado pelo metodo oficial.
