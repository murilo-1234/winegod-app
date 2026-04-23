# WINEGOD MULTILINGUE - METODO V2 RESULTADO CORRETIVO

Data: 2026-04-23
Status: concluido
Escopo: correcao cirurgica do pacote do metodo oficial

---

## 1. Resumo do que foi corrigido

Esta rodada V2 corrigiu os 4 gaps materiais apontados na auditoria:

- F0 agora exige branch dedicada ou worktree dedicada e bloqueia tracked modified + untracked no write-set de producao.
- O metodo deixou de depender obrigatoriamente de `C:\winegod-app-h4-closeout`.
- O gate final de ativacao passou a exigir prova do frontend publicado e smoke de share prefixado real.
- `reports/i18n_execution_log.md` virou artefato obrigatorio append-only em todo novo job.

Nao houve mudanca em app, env remoto, banco, feature flags ou deploy.

---

## 2. Arquivos editados

- `docs/metodo-linguas/WINEGOD_MULTILINGUE_METODO_BASE_OFICIAL.md`
- `docs/metodo-linguas/WINEGOD_MULTILINGUE_TEMPLATE_JOB_NOVO_LOCALE.md`
- `docs/metodo-linguas/WINEGOD_MULTILINGUE_TEMPLATE_DECISIONS_NOVO_LOCALE.md`
- `docs/metodo-linguas/WINEGOD_MULTILINGUE_TEMPLATE_RESULTADO_NOVO_LOCALE.md`
- `docs/metodo-linguas/WINEGOD_MULTILINGUE_TEMPLATE_HANDOFF_FINAL_NOVO_LOCALE.md`
- `docs/metodo-linguas/WINEGOD_MULTILINGUE_METODO_GAPS_E_PENDENCIAS.md`
- `docs/metodo-linguas/WINEGOD_MULTILINGUE_METODO_RESUMO_EXECUTIVO.md`
- `reports/WINEGOD_MULTILINGUE_METODO_RESULTADO_DA_CONSTRUCAO.md`
- `reports/i18n_execution_log.md`
- `reports/WINEGOD_MULTILINGUE_METODO_V2_RESULTADO_CORRETIVO.md`

---

## 3. Como a F0 mudou

Antes:

- F0 falava em branch/worktree limpa, mas o comando real bloqueava apenas untracked.
- tracked modified no write-set de producao podia passar.
- branch dedicada nao era gate operacional forte.

Agora:

- abordagem oficial default: branch dedicada `i18n/<JOB_NAME>-exec`
- alternativa oficial: worktree dedicada criada a partir de `main`
- proibido rodar locale job direto em `main`
- F0 grava `git_status_initial.txt`, `git_branch_initial.txt`, `untracked_production_initial.txt` e `dirty_production_initial.txt`
- F0 aborta se `frontend/`, `backend/`, `shared/`, `tools/` ou `scripts/` tiverem tracked modified ou untracked
- F0 orienta o que fazer se o repo estiver sujo: commit separado, worktree dedicada ou remocao apenas de artefato descartavel verificado
- F0 adiciona entrada inicial em `reports/i18n_execution_log.md`

---

## 4. Como a dependencia de `winegod-app-h4-closeout` foi resolvida

Antes:

- o metodo base listava arquivos de `C:\winegod-app-h4-closeout\reports\...` como documentos obrigatorios
- isso tornava o metodo fragil para um operador com clone limpo apenas de `C:\winegod-app`

Agora:

- o metodo V2 declara explicitamente que e autocontido em `C:\winegod-app`
- os documentos obrigatorios sao locais ao repo principal
- `reports/i18n_execution_log.md` do repo principal entrou como fonte local obrigatoria
- `C:\winegod-app-h4-closeout\reports\*` ficou classificado apenas como referencia historica opcional
- as licoes permanentes do fechamento total foram preservadas no metodo, sem exigir a worktree historica

---

## 5. Como o gate final de ativacao foi endurecido

Antes:

- o metodo aceitava `node tools/enabled_locales_check.mjs` com override local de `NEXT_PUBLIC_ENABLED_LOCALES` como prova forte
- isso provava a lista esperada contra o backend dinamico, mas nao provava que o frontend publicado recebeu o novo build-time env

Agora:

- `enabled_locales_check` virou pre-check, nao gate final
- o resultado precisa registrar id/URL/timestamp do redeploy frontend ou evidencia equivalente
- o smoke final consulta o backend publicado em `<API_BASE>/api/config/enabled-locales`
- o smoke final valida rotas prefixadas publicadas `/<LOCALE_SHORT>/...`
- o smoke final exige `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>` com share id real publico
- se a rota share prefixada der 404/5xx, o gate falha
- se a rota share prefixada redirecionar para `/c/<SMOKE_SHARE_ID>` sem prefixo, o gate falha porque isso sugere frontend publicado tratando o locale como desligado

Racional:

```text
NEXT_PUBLIC_ENABLED_LOCALES e build-time. Backend dinamico verde nao garante
que o frontend Vercel publicado foi reconstruido com o novo locale.
```

---

## 6. Como o append-only log passou a ser obrigatorio

Antes:

- `reports/i18n_execution_log.md` era historicamente importante, mas nao era artefato obrigatorio em todo novo job de locale

Agora:

- o metodo base lista o log como fonte local obrigatoria e evidencia obrigatoria
- o template de job inclui append em F0
- o template de resultado tem secao propria de append-only log
- o handoff final manda abrir o log para retomar o job
- rollback tambem exige append no log

Momentos minimos de append:

- F0 aprovado ou abortado
- gate estrutural/editorial concluido
- decisions O1/O2/O3 preenchidas
- ativacao/canary iniciada ou explicitamente nao executada
- smoke final aprovado/falhou
- fechamento/handoff emitido

---

## 7. Gaps que ainda sobraram

Gaps remanescentes, ja isolados em `WINEGOD_MULTILINGUE_METODO_GAPS_E_PENDENCIAS.md`:

- `tools/i18n_parity.mjs` ainda precisa ser parametrizado para novo locale
- smoke PowerShell atual ainda nao e script generico oficial
- ativacao remota ainda depende de acesso operacional ou dashboard Vercel
- legal local continua dependendo de decisao humana
- CJK/RTL continuam exigindo plano extra
- share smoke depende de `<SMOKE_SHARE_ID>` real publicado

Esses gaps nao bloqueiam o congelamento do metodo V2, porque estao explicitamente documentados e nao sao mais tratados como automacao inexistente.

---

## 8. Verificacao

Verificacao documental executada nesta rodada:

- leitura dos 11 arquivos obrigatorios do prompt corretivo
- patches limitados a documentacao do metodo
- nenhum arquivo de app/frontend/backend/shared alterado
- nenhuma env remota alterada
- nenhum deploy executado
- append em `reports/i18n_execution_log.md` executado como parte do fechamento desta manutencao
- documentos do pacote V2 validados como ASCII puro (`ASCII_OK`)

---

## 9. Veredito final

`METODO V2 PRONTO PARA CONGELAR`

Justificativa:

```text
Os 4 gaps materiais foram corrigidos de forma explicita. A V2 ficou mais
segura operacionalmente sem reabrir o projeto inteiro, e o pacote agora e
autocontido, auditavel, Windows-first e com gate final forte para frontend
publicado.
```
