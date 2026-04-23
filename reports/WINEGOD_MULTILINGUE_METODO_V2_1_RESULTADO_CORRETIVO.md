# WINEGOD MULTILINGUE - METODO V2.1 RESULTADO CORRETIVO

Data: 2026-04-23
Status: concluido
Escopo: ajuste documental cirurgico do suporte real a branch ou worktree

---

## 1. Resumo do ajuste

A V2.1 removeu a ambiguidade restante entre branch dedicada no clone principal e worktree dedicada.

Antes, o metodo dizia que os dois caminhos eram validos, mas ainda havia comandos com `Set-Location C:\winegod-app` e `Set-Location C:\winegod-app\frontend`. Isso podia levar o operador a rodar build, Playwright, baseline ou sanity no root errado quando estivesse usando worktree.

Agora, os comandos operacionais usam:

- `$repoRoot` para o root real da execucao
- `$frontendRoot = Join-Path $repoRoot "frontend"` para entrar no frontend
- `$sourceRepoRoot` apenas para criar worktree a partir do clone fonte
- `$worktree` ou `<WORKTREE_ROOT>` como root quando a execucao ocorre em worktree dedicada

---

## 2. Arquivos editados

- `docs/metodo-linguas/WINEGOD_MULTILINGUE_METODO_BASE_OFICIAL.md`
- `docs/metodo-linguas/WINEGOD_MULTILINGUE_TEMPLATE_JOB_NOVO_LOCALE.md`
- `docs/metodo-linguas/WINEGOD_MULTILINGUE_TEMPLATE_RESULTADO_NOVO_LOCALE.md`
- `docs/metodo-linguas/WINEGOD_MULTILINGUE_TEMPLATE_HANDOFF_FINAL_NOVO_LOCALE.md`
- `docs/metodo-linguas/WINEGOD_MULTILINGUE_METODO_RESUMO_EXECUTIVO.md`
- `reports/WINEGOD_MULTILINGUE_METODO_RESULTADO_DA_CONSTRUCAO.md`
- `reports/i18n_execution_log.md`
- `reports/WINEGOD_MULTILINGUE_METODO_V2_1_RESULTADO_CORRETIVO.md`

Nao foram alterados app, frontend de produto, backend, env remota, banco, feature flags ou deploy.

---

## 3. Como o root parametrico foi aplicado

Regra V2.1:

```text
Todo comando local do metodo deve rodar a partir de $repoRoot.
Quando precisar entrar no frontend, usar $frontendRoot = Join-Path $repoRoot "frontend".
```

Aplicacao:

- F0 do metodo base usa `$repoRoot = "<REPO_ROOT_DA_EXECUCAO>"` para branch no clone principal.
- F0 do metodo base usa `$sourceRepoRoot`, `$worktree` e depois `$repoRoot = $worktree` para worktree dedicada.
- Template de job define `<SOURCE_REPO_ROOT>`, `<WORKTREE_ROOT>` e `<REPO_ROOT_DA_EXECUCAO>`.
- Baseline tecnico usa `$repoRoot`, `$frontendRoot` e `$backup`.
- F2, F3 e F6 do template de job usam `$repoRoot`.
- Resultado final usa `$repoRoot` e `$frontendRoot` para build frio e Playwright.
- Handoff usa `$repoRoot` e `$frontendRoot` no sanity de retomada.

---

## 4. Como branch e worktree ficaram equivalentes operacionalmente

Branch dedicada:

- operador define `$repoRoot = "<REPO_ROOT_DA_EXECUCAO>"`
- exemplo de valor: clone principal
- branch esperada: `i18n/<JOB_NAME>-exec`
- todos os comandos seguintes rodam em `$repoRoot`

Worktree dedicada:

- operador define `$sourceRepoRoot` para o clone fonte
- `git worktree add -b $branch $worktree main`
- metodo define `$repoRoot = $worktree`
- todos os comandos seguintes rodam em `$repoRoot`

Equivalencia:

- as mesmas evidencias sao salvas em `reports/_backup_<JOB_NAME>/`
- o mesmo dirty write-set gate roda em `frontend`, `backend`, `shared`, `tools`, `scripts`
- o mesmo build frio roda em `$frontendRoot`
- o mesmo Playwright roda em `$frontendRoot`
- o mesmo append-only log fica no repo root escolhido

---

## 5. Trechos des-hardcoded

Foram removidos dos comandos operacionais:

- `Set-Location C:\winegod-app`
- `Set-Location C:\winegod-app\frontend`
- log de F0 que dizia `Branch/worktree: $branch em C:\winegod-app`
- resumo executivo que dizia que o operador gerava evidencias a partir de `C:\winegod-app`

Substituicoes principais:

- `Set-Location $repoRoot`
- `Set-Location $frontendRoot`
- `$frontendRoot = Join-Path $repoRoot "frontend"`
- `$backup = Join-Path $repoRoot "reports/_backup_<JOB_NAME>"`
- `Repo root: $repoRoot` nas entradas de log

---

## 6. Gaps que ainda sobraram

Gaps remanescentes, sem reabrir escopo:

- `<SOURCE_REPO_ROOT>` e `<WORKTREE_ROOT>` ainda sao preenchidos pelo operador no template.
- Ainda nao existe script unico que automatize a criacao de worktree e preflight.
- `tools/i18n_parity.mjs` continua precisando ser parametrizado para novo locale.
- smoke final ainda depende de `<SMOKE_SHARE_ID>` real publicado.

Esses gaps nao bloqueiam a V2.1 porque o objetivo desta rodada era corrigir a ambiguidade de root/worktree, nao automatizar o fluxo inteiro.

---

## 7. Verificacao

Verificacao documental executada:

- varredura por `Set-Location C:\winegod-app` nos documentos operacionais do metodo
- varredura por `C:\winegod-app\frontend` nos documentos operacionais do metodo
- confirmacao de que os comandos restantes usam `$repoRoot` ou `$frontendRoot`
- validacao ASCII do pacote V2.1
- append desta manutencao em `reports/i18n_execution_log.md`

---

## 8. Veredito final

`METODO V2.1 PRONTO PARA CONGELAR`

Justificativa:

```text
Branch dedicada e worktree dedicada agora sao equivalentes no metodo: ambas
convergem para $repoRoot, e todos os comandos relevantes derivam paths a partir
dele. A opcao de worktree deixou de ser apenas textual e passou a ser
operacional.
```
