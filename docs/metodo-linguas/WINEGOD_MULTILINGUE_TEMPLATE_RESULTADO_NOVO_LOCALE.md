# WINEGOD MULTILINGUE - TEMPLATE RESULTADO NOVO LOCALE

Status: template
Uso: copiar para `reports/WINEGOD_<JOB_NAME>_RESULTADO.md` ao final do job.

---

## 1. Resumo

- Data:
- Job: `<JOB_NAME>`
- Locale: `<LOCALE>`
- Status final: `FECHADO` | `FECHADO COM RESIDUAIS` | `PRONTO SEM ATIVACAO` | `BLOQUEADO`
- Branch:
- Repo root de execucao:
- Modo de execucao: `BRANCH_NO_CLONE_PRINCIPAL` | `WORKTREE_DEDICADA`
- Commit(s):
- Operador:

Resumo em 5 linhas:

```text
<preencher>
```

---

## 2. Escopo executado

### Incluido

- [ ] Estrutura de locale
- [ ] `frontend/messages/<LOCALE>.json`
- [ ] Routing/middleware/fallback
- [ ] Legal
- [ ] Age gate
- [ ] QA deterministic/visual
- [ ] Activation/canary
- [ ] Smoke prod
- [ ] Docs finais

### Fora de escopo

- [ ] Deploy
- [ ] Env remoto
- [ ] Feature flags reais
- [ ] Revisao juridica local
- [ ] Humano nativo

Explicacao:

```text
<preencher>
```

---

## 3. Arquivos alterados

### Codigo/config

```text
<listar>
```

### Mensagens

```text
frontend/messages/<LOCALE>.json
```

### Legal

```text
<listar ou N/A>
```

### QA

```text
<listar>
```

### Docs

```text
<listar>
```

---

## 4. Evidencias obrigatorias

### 4.1 Git inicial e final

Inicial:

```text
<colar resumo de reports/_backup_<JOB_NAME>/git_status_initial.txt>
```

Final:

```text
<colar git status --short final ou resumir>
```

Branch/worktree/root:

```text
<informar branch i18n/<JOB_NAME>-exec, repo root usado e se era clone principal ou worktree dedicada>
```

Dirty production write-set inicial:

```text
<colar reports/_backup_<JOB_NAME>/dirty_production_initial.txt; esperado vazio>
```

### 4.2 Parity

Comando:

```powershell
node tools/i18n_parity.mjs
```

Resultado:

```text
<colar saida resumida>
```

Veredito: `OK` | `FALHOU`

### 4.3 Build frio

Comando:

```powershell
$repoRoot = "<REPO_ROOT_DA_EXECUCAO>"
$frontendRoot = Join-Path $repoRoot "frontend"
Set-Location $frontendRoot
Remove-Item -LiteralPath ".next" -Recurse -Force -ErrorAction SilentlyContinue
npm run build
```

Resultado:

```text
<colar saida resumida>
```

Veredito: `OK` | `FALHOU`

### 4.4 Playwright i18n

Comando:

```powershell
$repoRoot = "<REPO_ROOT_DA_EXECUCAO>"
$frontendRoot = Join-Path $repoRoot "frontend"
Set-Location $frontendRoot
npx playwright test tests/i18n/ --project=desktop-chromium
```

Resultado:

```text
<colar saida resumida>
```

Veredito: `OK` | `FALHOU` | `NAO EXECUTADO`

### 4.5 Enabled locales check pre-ativacao

Comando:

```powershell
$env:NEXT_PUBLIC_ENABLED_LOCALES='<lista>'
node tools/enabled_locales_check.mjs
```

Resultado:

```text
<colar saida>
```

Veredito: `OK` | `FALHOU` | `NAO APLICAVEL`

Observacao obrigatoria:

```text
Este check e apenas pre-check static/dynamic com lista esperada local. Ele nao prova sozinho que o frontend publicado recebeu o novo NEXT_PUBLIC_ENABLED_LOCALES.
```

### 4.6 Prova de frontend publicado

Preencher quando houve ativacao:

- Vercel deploy id/URL:
- Horario do deploy:
- Evidencia de `NEXT_PUBLIC_ENABLED_LOCALES` atualizado:
- Header/prova de resposta publicada, se coletado:

Veredito: `OK` | `FALHOU` | `NAO APLICAVEL`

### 4.7 Smoke de producao

Base URL:

```text
<PROD_URL>
```

Resultado por rota:

| Rota | Status | Observacao |
|---|---:|---|
| `/` |  |  |
| `/ajuda` |  |  |
| `/plano` |  |  |
| `/conta` |  |  |
| `/favoritos` |  |  |
| `/privacy` |  |  |
| `/terms` |  |  |
| `/data-deletion` |  |  |
| `/<LOCALE_SHORT>/ajuda` |  |  |
| `/<LOCALE_SHORT>/age-verify` |  |  |
| `/<LOCALE_SHORT>/privacy` |  |  |
| `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>` |  |  |

Veredito: `OK` | `FALHOU` | `NAO EXECUTADO`

Regra:

```text
O smoke de share prefixado precisa usar um id real publico. Nao vale usar id sintetico. Se a rota 301/302 para `/c/<SMOKE_SHARE_ID>` sem prefixo de locale, o gate falha porque o frontend publicado pode estar tratando `<LOCALE>` como desligado.
```

### 4.8 Append-only log

Fonte:

```text
reports/i18n_execution_log.md
```

Entradas adicionadas:

| Momento | Linha/Data | Resumo |
|---|---|---|
| F0 |  |  |
| Gate estrutural/editorial |  |  |
| Decisions |  |  |
| Ativacao/canary |  |  |
| Smoke final |  |  |
| Fechamento |  |  |

Veredito: `OK` | `FALHOU`

---

## 5. Review editorial

Artefatos:

- `reports/WINEGOD_<JOB_NAME>_REVIEW_CLAUDE.md`
- `reports/WINEGOD_<JOB_NAME>_REVIEW_CODEX.md`
- `reports/WINEGOD_<JOB_NAME>_REVIEW_CONSOLIDADO.md`

Resumo:

| Severidade | Quantidade inicial | Corrigidos | Aceitos |
|---|---:|---:|---:|
| S1 |  |  |  |
| S2 |  |  |  |
| S3 |  |  |  |
| S4 |  |  |  |

Veredito editorial final:

```text
<PASSA | PASSA COM AJUSTES | NAO PASSA>
```

---

## 6. Decisions

Fonte:

```text
reports/WINEGOD_<JOB_NAME>_DECISIONS.md
```

Resumo:

- O1:
- O2:
- O3:
- O4:
- O5:

---

## 7. Ativacao

- `feature_flags.enabled_locales`: `ALTERADO` | `NAO ALTERADO`
- `NEXT_PUBLIC_ENABLED_LOCALES`: `ALTERADO` | `NAO ALTERADO`
- Redeploy Vercel: `EXECUTADO` | `NAO EXECUTADO`
- Frontend publicado provado: `SIM` | `NAO` | `NAO APLICAVEL`
- Share prefixado provado: `SIM` | `NAO` | `NAO APLICAVEL`
- Render: `EXECUTADO` | `NAO EXECUTADO` | `NAO APLICAVEL`
- Canary: `FECHADO` | `COMPRIMIDO` | `GRADUAL` | `NAO ATIVADO`

Detalhes:

```text
<preencher>
```

---

## 8. Residuais aceitos

| ID | Residual | Risco | Racional | Dono |
|---|---|---|---|---|
| R1 |  |  |  |  |

---

## 9. Pendencias humanas residuais

| ID | Pendencia | Bloqueia? | Dono | Proxima acao |
|---|---|---|---|---|
| H1 |  |  |  |  |

---

## 10. Veredito final

Escolher uma:

- [ ] `<LOCALE>` esta fechado e ativo em producao.
- [ ] `<LOCALE>` esta pronto, mas nao foi ativado por decisao operacional.
- [ ] `<LOCALE>` esta parcialmente pronto e bloqueado por pendencia humana.
- [ ] `<LOCALE>` nao passou nos gates do metodo.

Justificativa:

```text
<preencher>
```
