# WINEGOD MULTILINGUE - TEMPLATE HANDOFF FINAL NOVO LOCALE

Status: template
Uso: copiar para `reports/WINEGOD_<JOB_NAME>_HANDOFF_FINAL.md`.

---

## 1. Estado atual

- Data:
- Job: `<JOB_NAME>`
- Locale: `<LOCALE>`
- Status: `ATIVO` | `PRONTO SEM ATIVAR` | `BLOQUEADO` | `ROLLBACK`
- Ambiente: `local` | `preview` | `producao`
- Branch:
- Repo root de execucao:
- Modo de execucao: `BRANCH_NO_CLONE_PRINCIPAL` | `WORKTREE_DEDICADA`
- Commit(s):

Resumo:

```text
<preencher>
```

---

## 2. O que esta pronto

- [ ] UI em `<LOCALE>`
- [ ] routing/prefix `/<LOCALE_SHORT>`
- [ ] fallback chain `<FALLBACK_CHAIN>`
- [ ] legal
- [ ] age gate
- [ ] QA determinista
- [ ] QA visual
- [ ] canary
- [ ] smoke prod
- [ ] append-only log atualizado

Detalhes:

```text
<preencher>
```

---

## 3. O que nao esta pronto

Listar apenas pendencias reais.

| Item | Tipo | Bloqueia producao? | Dono |
|---|---|---|---|
|  |  |  |  |

---

## 4. Decisoes vigentes

Fonte: `reports/WINEGOD_<JOB_NAME>_DECISIONS.md`

- O1 legal:
- O2 OG image:
- O3 OG alt/static:
- O4 revisao humana:
- O5 canary:
- O6 env/deploy:

---

## 5. Validacoes executadas

| Gate | Status | Evidencia |
|---|---|---|
| Preflight branch/worktree dedicada |  |  |
| Dirty production write-set vazio |  |  |
| Parity |  |  |
| Build frio |  |  |
| Playwright i18n |  |  |
| Review editorial |  |  |
| Legal/age gate |  |  |
| Enabled locales pre-check |  |  |
| Frontend publicado com novo env |  |  |
| Share prefixado `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>` |  |  |
| Smoke prod |  |  |
| Append-only log |  |  |

---

## 6. Como retomar

Se o proximo operador precisar continuar:

1. Abrir este handoff.
2. Abrir `reports/WINEGOD_<JOB_NAME>_RESULTADO.md`.
3. Abrir `reports/i18n_execution_log.md` e localizar as entradas de `<JOB_NAME>`.
4. Conferir `git status --short`.
5. Conferir decisions O1/O2/O3/O4/O5.
6. Se `<LOCALE>` nao esta ativo, retomar a partir da primeira pendencia marcada como bloqueante.
7. Se `<LOCALE>` esta ativo, rodar smoke antes de qualquer nova mudanca.

Comandos de sanity:

```powershell
$repoRoot = "<REPO_ROOT_DA_EXECUCAO>"
$frontendRoot = Join-Path $repoRoot "frontend"

Set-Location $repoRoot
git status --short
node tools/i18n_parity.mjs

Set-Location $frontendRoot
Remove-Item -LiteralPath ".next" -Recurse -Force -ErrorAction SilentlyContinue
npm run build
Set-Location $repoRoot
```

---

## 7. Rollback

Rollback dinamico:

```text
Remover <LOCALE> de feature_flags.enabled_locales.
```

Rollback frontend:

```text
Remover <LOCALE> de NEXT_PUBLIC_ENABLED_LOCALES no Vercel e redeployar.
```

Smoke apos rollback:

```powershell
$env:NEXT_PUBLIC_ENABLED_LOCALES='<lista_sem_LOCALE>'
node tools/enabled_locales_check.mjs
Remove-Item Env:\NEXT_PUBLIC_ENABLED_LOCALES -ErrorAction SilentlyContinue
```

Registro obrigatorio:

```text
Adicionar uma entrada append-only em reports/i18n_execution_log.md com data, motivo, lista final de enabled_locales e resultado do smoke apos rollback.
```

Referencias:

- `docs/RUNBOOK_I18N_ROLLBACK.md`
- `tools/enabled_locales_check.mjs`
- `reports/i18n_execution_log.md`

---

## 8. Residuais aceitos

| ID | Residual | Risco | Como monitorar | Revisitar quando |
|---|---|---|---|---|
|  |  |  |  |  |

---

## 9. Trabalho futuro opcional

Nao bloquear o estado atual por estes itens, salvo se marcado como bloqueante acima.

- [ ] revisao nativa humana
- [ ] revisao juridica local
- [ ] OG localizado
- [ ] polimento editorial S3
- [ ] ampliacao de snapshots mobile
- [ ] observabilidade por locale

---

## 10. O que nao falta

Marcar para evitar retrabalho:

- [ ] nao falta criar JSON
- [ ] nao falta parity
- [ ] nao falta legal
- [ ] nao falta enabled locales
- [ ] nao falta deploy
- [ ] nao falta smoke
- [ ] nao falta handoff
- [ ] nao falta append-only log

Notas:

```text
<preencher>
```

---

## 11. Veredito do handoff

```text
<preencher uma frase objetiva: o que esta entregue, o que falta, se alguem pode retomar sem memoria do chat.>
```
