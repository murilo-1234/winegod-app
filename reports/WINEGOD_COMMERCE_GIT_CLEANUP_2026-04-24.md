# WINEGOD - Commerce Git Cleanup (Fase L)

Data: 2026-04-24  
Escopo: analise nao-destrutiva de branches commerce consolidadas.  
Modo: **diagnostico apenas**. Zero `git branch -D`, zero push force,
zero delete remoto executado automaticamente.

## 1. Branches de commerce desta sequencia

Em ordem cronologica:

| branch | base | merge/integra em | status | seguro deletar? |
|---|---|---|---|---|
| `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423` | `main` | `main` (f7b13d60 entrou) | ancorada no historico | **Nao** - referenciada nos handoffs |
| `data-ops/execucao-total-commerce-operacao-residual-externo-final-20260424` | `f7b13d60` | substituida por correcao-commerce | ancestor de correcao | Sim *apos* correcoes pushed |
| `data-ops/correcao-commerce-operacao-residual-externo-final-20260424` | `5dc824a0` | substituida por correcao-minima | ancestor de correcao-minima | Sim *apos* correcao-minima pushed |
| `data-ops/correcao-minima-commerce-readme-validator-20260424` | `31a6ac5f` | (aberta) base desta rodada | aberta | **Nao** - PR pendente |
| `data-ops/execucao-total-commerce-fechamento-final-20260424` (local) | `ab39d816` | (aberta) esta rodada | local ahead (commit nao pushed ainda) | **Nao** |

## 2. Branches nao-commerce ahead (contaminacao por acidente de checkout)

| branch | commit extra | motivo | recomendacao |
|---|---|---|---|
| `data-ops/execucao-total-reviews-dominio-final-20260424` | `1c081730 feat(data-ops): commerce runbook + amazon_mirror README + artifact validator CLI` | commit commerce acidental em sessao anterior | `git reset --keep HEAD~1` se operador quiser limpar (nao-destrutivo no working tree) |
| `data-ops/execucao-total-nao-commerce-reviews-discovery-enrichment-20260424` | `b2ea90c1 fix(data-ops): reapply commerce finding fixes + harden validator full scan` | idem | idem |
| `data-ops/execucao-total-discovery-enrichment-producao-20260424` | `0ec288c8 docs(commerce): scraper inventory mapping (Fase A)` | commit da fase A desta rodada (sera movido) | sera consolidado via cherry-pick |

Nenhuma dessas branches foi pushed com os commits acidentais, entao o
remote permanece limpo. O usuario pode limpar localmente sem risco para
collaborators.

## 3. Branches `gone` (upstream deletado)

- `dq-v3-pr-a-clean` - upstream `origin/dq-v3-pr-a-clean: gone`
- `dq-v3-pr-b-clean` - upstream `origin/dq-v3-pr-b-clean: gone`

Seguras para deletar local:

```powershell
git branch -D dq-v3-pr-a-clean
git branch -D dq-v3-pr-b-clean
```

**Nao executado nesta rodada por precaucao** (`-D` e destrutivo).

## 4. Branches consolidadas em `origin/main`

Lista de `git branch -r --merged origin/main`:

- origin/codex/h4-closeout
- origin/hotfix/wcf-score-worker-fanout-20260422_162025
- origin/i18n/h4-exec
- origin/i18n/onda-2
- origin/pais-recovery-bulk-ingest
- origin/rollout/score-automation

Essas **foram integradas em main** no ponto do fetch. Candidatas a
`git push origin --delete <branch>` **apos confirmacao do usuario**.
Nao sao commerce e nao fazem parte do escopo desta rodada - documentadas
aqui so para visibilidade.

## 5. Comandos sugeridos (opt-in do operador)

### 5.1 Limpar branches `gone`

```powershell
git branch -D dq-v3-pr-a-clean
git branch -D dq-v3-pr-b-clean
```

### 5.2 Limpar branches commerce ancestor (apos PRs mergearem)

```powershell
# Depois que correcao-minima-commerce-readme-validator-20260424 for mergeada:
git branch -D data-ops/execucao-total-commerce-operacao-residual-externo-final-20260424
git branch -D data-ops/correcao-commerce-operacao-residual-externo-final-20260424
# E eventualmente:
git branch -D data-ops/correcao-minima-commerce-readme-validator-20260424
```

### 5.3 Limpar contaminacao de branches de reviews/discovery/enrichment

(apos cherry-pick para branch commerce definitiva)

```powershell
git checkout data-ops/execucao-total-reviews-dominio-final-20260424
git reset --keep HEAD~1  # remove 1c081730 (commit commerce acidental)
git checkout data-ops/execucao-total-nao-commerce-reviews-discovery-enrichment-20260424
git reset --keep HEAD~1  # remove b2ea90c1
git checkout data-ops/execucao-total-discovery-enrichment-producao-20260424
git reset --keep HEAD~1  # remove 0ec288c8
```

**ALERTA**: `reset --keep` (nao `--hard`) preserva o working tree. Ainda
e uma operacao destrutiva de historico; operador decide.

## 6. O que NAO fazer (reforco)

- Nao `git push --force` em nenhuma dessas branches.
- Nao `git branch -D` em branches ativas ou nao-mergidas (ex:
  `data-ops/correcao-minima-commerce-readme-validator-20260424`).
- Nao deletar `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`
  - ela e referenciada pelos handoffs historicos (`f7b13d60` marca o
  go-live aprovado).
- Nao `rebase -i` em branches pushed.

## 7. Proximo passo recomendado

Concentrar a auditoria e merge em **uma unica branch ativa de commerce**:
`data-ops/execucao-total-commerce-fechamento-final-20260424`. As branches
ancestor podem ser deletadas de forma incremental apos o usuario
confirmar que foram mergidas ou descartadas.
