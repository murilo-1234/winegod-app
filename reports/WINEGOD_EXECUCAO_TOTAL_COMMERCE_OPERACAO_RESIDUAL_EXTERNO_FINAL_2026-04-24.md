# WINEGOD - Execucao Total Commerce: Operacao + Residual Externo + Fechamento Final

Data: 2026-04-24  
Executor: Claude Code (Opus 4.7 1M context)  
Prompt fonte: `prompts/PROMPT_CLAUDE_EXECUCAO_TOTAL_COMMERCE_OPERACAO_RESIDUAL_EXTERNO_FINAL_2026-04-24.md`  
Branch: `data-ops/execucao-total-commerce-operacao-residual-externo-final-20260424`  
Base: `f7b13d60 docs(data-ops): finalize go-live audit docs`  
Auditor final: **Codex admin**

## 1. Veredito final

```text
COMMERCE_LOCAL_OPERACIONAL_CONFIRMADO + RESIDUAL_EXTERNO_AMAZON_MINIMIZADO + RUNBOOK_ENTREGUE + 4_PROPOSTAS_DE_ENDURECIMENTO_REVERTIDAS_EXTERNAMENTE
```

O estado operacional canonico continua intacto. As 4 fontes canonicas por
artefato passam no dry-run. O residual externo `amazon_mirror_primary`
continua isolado e agora tem contrato local + validator CLI + README
in-place prontos para o dia em que o JSONL do PC espelho aparecer.

Foram identificadas 4 folgas locais e propostas correcoes em arquivos
existentes, mas essas edicoes foram **revertidas externamente** durante a
sessao (hook/linter/editor/usuario). Registrei as propostas aqui para o
Codex admin decidir se deve reaplicar.

## 2. Fontes commerce - estado final confirmado

| Fonte | Papel | Estado | Evidencia |
|---|---|---|---|
| `winegod_admin_world` | feed local observed (winegod_db) | observed | exporter legacy (sem alteracao nesta sessao) |
| `vinhos_brasil_legacy` | feed local observed (vinhos_brasil_db) | observed | exporter legacy (sem alteracao nesta sessao) |
| `amazon_mirror_primary` | feed Amazon oficial (artefato PC espelho) | **blocked_external_host honesto** | dry-run 2026-04-24T05:20:48 + validator CLI FAIL artefato_ausente (esperado) |
| `amazon_local_legacy_backfill` | backfill controlado Amazon | observed | dry-run 2026-04-24T05:20:32 |
| `amazon_local` | observer legado (diagnostico) | observed | sem alteracao |
| `tier1_global` | feed Tier1 via artefato | **observed** | dry-run 2026-04-24T05:20:54 (contract=ok, sha256=e71322a4fb38) |
| `tier2_global_artifact` | feed Tier2 UNICO global via artefato | **observed** | dry-run 2026-04-24T05:21:03 (contract=ok, sha256=493541ade1e4) |
| `tier2_br` | Tier2 BR por filtro real de pais | **observed** | dry-run 2026-04-24T05:21:12 (contract=ok, sha256=e1795383591e) |
| `winegod_admin_legacy_mixed` | historico misturado (allowlist explicita) | **blocked_missing_source honesto** | dry-run 2026-04-24T05:20:26 (runtime); manifest `registry_status: observed` segue inconsistente com o runtime (ver secao 5) |
| `tier2_chat1..5` | DEPRECATED (colapsados em tier2_global_artifact) | blocked_contract_missing | nao executado; historico preservado |

Canal unico preservado: todas as fontes sobem por
`plug_commerce_dq_v3 -> DQ V3 -> public.wines + public.wine_sources`.
Zero writer paralelo. Zero novo plug.

## 3. O que foi confirmado como operacional

1. **Scheduler canonico** `scripts/data_ops_scheduler/run_commerce_artifact_dryruns.ps1` roda os 4 dry-runs das fontes por artefato em sequencia e consome automaticamente o JSONL mais recente em cada diretorio. Exit 0 em todos.
2. **Producer local** `scripts/data_ops_producers/build_commerce_artifact.py` gera JSONL + `<prefix>_summary.json` no contrato, com matching por host endurecido.
3. **Artefatos atuais validados pelo CLI novo**:
   - `reports/data_ops_artifacts/tier1/20260424_040740_tier1_global.jsonl` (346 items, sha256=e71322a4fb38...)
   - `reports/data_ops_artifacts/tier2_global/20260424_040736_tier2_global_artifact.jsonl` (176 items, sha256=493541ade1e4...)
   - `reports/data_ops_artifacts/tier2/br/20260424_040742_tier2_br.jsonl` (200+ items, sha256=e1795383591e...)
4. **Contrato endurecido** em `sdk/plugs/commerce_dq_v3/artifact_contract.py` valida 13 campos por item + 8 de summary + SHA256 match + pipeline_family match.
5. **Precedencia preservada**: `amazon_mirror > amazon_local_legacy_backfill`.
6. **Winegod admin legacy mixed** continua bloqueado por default (exige `LEGACY_MIXED_ALLOWED_FONTES`).
7. **Testes automatizados**:
   - `sdk/plugs/commerce_dq_v3 + scripts/data_ops_producers/tests`: 27 passed
   - `sdk/adapters/tests`: 43 passed
   - `sdk/tests`: 76 passed
   - **Total: 146 passed, 0 failed, 0 regressao.**

## 4. O que foi entregue nesta execucao (arquivos novos)

### 4.1 `scripts/data_ops_producers/validate_commerce_artifact.py` (novo)

CLI local que reaproveita `validate_artifact_dir` para validar qualquer
artefato (amazon_mirror, tier1, tier2*) contra o contrato sem rodar o plug
nem escrever no banco. Exit codes:

- 0 = contrato OK.
- 1 = contrato invalido.
- 2 = artefato ausente.

Uso previsto: operador do PC espelho valida seu JSONL antes de deixar o
arquivo no diretorio alvo.

### 4.2 `reports/data_ops_artifacts/amazon_mirror/README.md` (novo)

Guia in-place com o contrato completo, checklist antes da entrega, comando
de validacao local, plano de apply em escada e lista do que NAO fazer.
Tudo no diretorio que o operador do PC espelho vai abrir.

### 4.3 `docs/RUNBOOK_COMMERCE_OPERACAO_RECORRENTE.md` (novo)

Runbook operacional consolidado: fontes canonicas, cadencia recorrente,
producers, scheduler, apply em escada, gates e metricas de controle,
criterios de promocao/recuo/bloqueio, ordem de monitoramento, testes e
lista do que NAO fazer. Aponta para `docs/TIER_COMMERCE_CONTRACT.md` e
para o README in-place do amazon_mirror.

## 5. Folgas locais identificadas (propostas revertidas externamente)

Durante a execucao identifiquei 4 inconsistencias locais e apliquei
propostas de fix em arquivos existentes. Essas edicoes foram revertidas
externamente (hook/linter/editor/usuario) e acabaram nao persistindo no
working tree. Registro aqui para o Codex admin decidir.

### 5.1 `sdk/adapters/manifests/commerce_winegod_admin_legacy_mixed.yaml`

- **Inconsistencia**: `registry_status: observed` enquanto o exporter
  retorna `blocked_missing_source` por default (sem
  `LEGACY_MIXED_ALLOWED_FONTES` declarada).
- **Proposta**: trocar para `registry_status: blocked_missing_source` +
  `status_reason: exige_LEGACY_MIXED_ALLOWED_FONTES_para_habilitar_allowlist_explicita`.
- **Estado atual pos-reversao**: manifest continua `observed`. Runtime
  real continua `blocked_missing_source`. Divergencia segue no registry.

### 5.2 `scripts/data_ops_scheduler/run_all_plug_dryruns.ps1`

- **Inconsistencia**: lista `amazon_mirror` (stub substituido por
  `amazon_mirror_primary`) e `tier2_chat1..5` (DEPRECATED). Nao lista
  as fontes canonicas (`amazon_mirror_primary`,
  `amazon_local_legacy_backfill`, `tier2_global_artifact`,
  `winegod_admin_legacy_mixed`).
- **Proposta**: substituir a lista por fontes canonicas alinhadas com o
  plano mestre final.
- **Estado atual pos-reversao**: arquivo volta a listar stubs/deprecated.
  O scheduler canonico reduzido (`run_commerce_artifact_dryruns.ps1`)
  continua ok e nao e afetado.

### 5.3 `docs/TIER_COMMERCE_CONTRACT.md`

- **Inconsistencia**: documenta caminho `tier2/<chat>/` com chat1..5 como
  valores validos (obsoleto pos-colapso).
- **Proposta**: documentar `tier2_global/` como feed UNICO + `tier2/br/`
  separado por pais, com nota explicita sobre a extincao.
- **Estado atual pos-reversao**: doc continua apontando para o caminho
  antigo. Contradiz o que o exporter real (`tier2_global_artifact`) ja
  consome.

### 5.4 `scripts/data_ops_scheduler/README.md`

- **Inconsistencia**: diretorios esperados apontavam `tier2/<chat>/`
  (obsoleto).
- **Proposta**: listar `tier2_global/` + `tier2/br/` com nota historica.
- **Estado atual pos-reversao**: README continua apontando para o path
  antigo.

## 6. Residual externo real que sobrou

Um so: `amazon_mirror_primary` depende do operador do PC espelho depositar:

```text
reports/data_ops_artifacts/amazon_mirror/<prefix>.jsonl
reports/data_ops_artifacts/amazon_mirror/<prefix>_summary.json
```

Contrato local pronto. Scheduler canonico pronto para consumir o mais
recente assim que aparecer. Validator CLI disponivel para o operador
verificar antes de entregar. README in-place com checklist passo-a-passo.
Nao ha outro residual externo.

## 7. Comandos/testes/smokes executados

### 7.1 Testes automatizados

```powershell
python -m pytest sdk/plugs/commerce_dq_v3 scripts/data_ops_producers/tests -q
# 27 passed in 1.11s

python -m pytest sdk/adapters/tests -q
# 43 passed in 1.00s

python -m pytest sdk/tests -q
# 76 passed in 1.34s
```

Total: **146 passed, 0 failed, 0 regressao.**

### 7.2 Validator CLI (artefatos atuais)

```powershell
python scripts/data_ops_producers/validate_commerce_artifact.py `
  --artifact-dir reports/data_ops_artifacts/tier1 `
  --expected-family tier1 --item-limit 200
# OK artifact=20260424_040740_tier1_global.jsonl items_validados=200 sha256=e71322a4fb38

python scripts/data_ops_producers/validate_commerce_artifact.py `
  --artifact-dir reports/data_ops_artifacts/tier2_global `
  --expected-family tier2 --item-limit 200
# OK artifact=20260424_040736_tier2_global_artifact.jsonl items_validados=176 sha256=493541ade1e4

python scripts/data_ops_producers/validate_commerce_artifact.py `
  --artifact-dir reports/data_ops_artifacts/tier2/br `
  --expected-family tier2 --item-limit 200
# OK artifact=20260424_040742_tier2_br.jsonl items_validados=200 sha256=e1795383591e

python scripts/data_ops_producers/validate_commerce_artifact.py `
  --artifact-dir reports/data_ops_artifacts/amazon_mirror `
  --expected-family amazon_mirror_primary --item-limit 200
# FAIL reason=nenhum_artefato_jsonl_em=... (exit=2, esperado ate PC espelho entregar)
```

### 7.3 Dry-runs manuais

Rodados um a um via `python -m sdk.plugs.commerce_dq_v3.runner --source <x> --limit 10 --dry-run`:

| Fonte | exit | state | notes |
|---|---:|---|---|
| `tier1_global` | 0 | observed | items_exported=10; contract=ok |
| `tier2_global_artifact` | 0 | observed | items_exported=10; contract=ok |
| `tier2_br` | 0 | observed | items_exported=10; contract=ok |
| `amazon_mirror_primary` | 0 | blocked_external_host | nenhum_artefato_jsonl; host_externo_pc_espelho |
| `amazon_local_legacy_backfill` | 0 | observed | items_exported=10; lineage=legacy_local |
| `winegod_admin_legacy_mixed` | 0 | blocked_missing_source | declare_LEGACY_MIXED_ALLOWED_FONTES_para_habilitar_allowlist |

### 7.4 Scheduler canonico

```powershell
powershell -File scripts/data_ops_scheduler/run_commerce_artifact_dryruns.ps1 -Limit 10
# ==> commerce artifact dry-run source=amazon_mirror_primary limit=10  -> blocked_external_host
# ==> commerce artifact dry-run source=tier1_global limit=10           -> observed
# ==> commerce artifact dry-run source=tier2_global_artifact limit=10  -> observed
# ==> commerce artifact dry-run source=tier2_br limit=10               -> observed
# ==> commerce artifact dryruns done
```

4 dry-runs, 3 observed + 1 blocked_external_host honesto. Zero erro.

## 8. Resultados e metricas relevantes

- Zero apply executado nesta sessao (so dry-run, conforme intencao do prompt: confirmar operacao local recorrente sem tocar no banco).
- Zero regressao em testes.
- Zero criacao de canal paralelo.
- Zero mudanca em dominio reviews, discovery ou enrichment (escopo respeitado).
- Zero escrita direta em `public.wines` / `public.wine_sources`.
- Zero Gemini pago, zero chamada paga externa.
- Zero `git reset --hard`, `git push --force`, merge em main, ou deploy Render/Vercel.

## 9. Arquivos alterados

### Criados (persistem no working tree)

- `docs/RUNBOOK_COMMERCE_OPERACAO_RECORRENTE.md`
- `scripts/data_ops_producers/validate_commerce_artifact.py`
- `reports/data_ops_artifacts/amazon_mirror/README.md`
- `reports/WINEGOD_EXECUCAO_TOTAL_COMMERCE_OPERACAO_RESIDUAL_EXTERNO_FINAL_2026-04-24.md` (ESTE)
- `CLAUDE_RESPOSTAS_EXECUCAO_TOTAL_COMMERCE_OPERACAO_RESIDUAL_EXTERNO_FINAL_2026-04-24.md` (resposta Codex)

### Modificados e revertidos externamente (nao persistem)

Ver secao 5 para detalhe das 4 folgas identificadas. Propostas registradas
no relatorio mas nao persistidas em arquivo:

- `docs/TIER_COMMERCE_CONTRACT.md` (proposta: alinhar paths Tier2)
- `sdk/adapters/manifests/commerce_winegod_admin_legacy_mixed.yaml` (proposta: status honesto)
- `scripts/data_ops_scheduler/run_all_plug_dryruns.ps1` (proposta: fontes canonicas)
- `scripts/data_ops_scheduler/README.md` (proposta: paths atualizados)

## 10. Commits e branch

- Base: `f7b13d60 docs(data-ops): finalize go-live audit docs`.
- Branch desta execucao: `data-ops/execucao-total-commerce-operacao-residual-externo-final-20260424`.
- Commit: a ser pinado logo abaixo do push.

## 11. Bloqueios externos remanescentes

Um unico bloqueio externo legitimo:

- **PC espelho Amazon**: precisa depositar JSONL + summary em
  `reports/data_ops_artifacts/amazon_mirror/` conforme
  `reports/data_ops_artifacts/amazon_mirror/README.md`.
- Enquanto nao aparecer, `amazon_mirror_primary` continua
  `blocked_external_host` honesto. O scheduler local ja consome
  automaticamente o mais recente assim que os dois arquivos aparecerem.

Nenhum outro bloqueio externo relevante.

## Apendice - Arquivo a repassar para o Codex admin

```text
C:\winegod-app\reports\WINEGOD_EXECUCAO_TOTAL_COMMERCE_OPERACAO_RESIDUAL_EXTERNO_FINAL_2026-04-24.md
C:\winegod-app\CLAUDE_RESPOSTAS_EXECUCAO_TOTAL_COMMERCE_OPERACAO_RESIDUAL_EXTERNO_FINAL_2026-04-24.md
```
