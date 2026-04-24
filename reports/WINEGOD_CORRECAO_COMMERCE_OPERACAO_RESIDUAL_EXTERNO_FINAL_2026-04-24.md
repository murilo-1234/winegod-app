# WINEGOD - Correcao Commerce Operacao + Residual Externo Final

Data: 2026-04-24  
Executor: Claude Code (Opus 4.7 1M context)  
Prompt fonte: `prompts/PROMPT_CLAUDE_CORRECAO_COMMERCE_OPERACAO_RESIDUAL_EXTERNO_FINAL_2026-04-24.md`  
Branch: `data-ops/correcao-commerce-operacao-residual-externo-final-20260424`  
Base: `5dc824a0 docs(data-ops): pin 225f77d5 SHA in final commerce docs` (origin)  
Auditor final: **Codex admin**

## 1. Veredito final

```text
APROVADO_CORRECOES_OBRIGATORIAS_APLICADAS_E_PERSISTIDAS_EM_ARQUIVO
```

As 4 folgas locais que o Codex admin marcou como obrigatorias foram
reaplicadas e persistiram no working tree. O validator CLI foi endurecido
para full-scan (novo default) com teste que prova a deteccao de linha
invalida pos-janela e mismatch de `items_emitted`. Zero apply executado.
Zero canal paralelo criado.

## 2. Findings corrigidos (todos os 5)

### 2.1 Manifest `commerce_winegod_admin_legacy_mixed` (4.1)

Arquivo: `sdk/adapters/manifests/commerce_winegod_admin_legacy_mixed.yaml`.

Antes:
```yaml
registry_status: observed
```

Depois:
```yaml
registry_status: blocked_missing_source
status_reason: exige_LEGACY_MIXED_ALLOWED_FONTES_para_habilitar_allowlist_explicita
```

Agora o registry bate com o runtime real (dry-run retorna `blocked_missing_source`
enquanto `LEGACY_MIXED_ALLOWED_FONTES` nao for declarada).

### 2.2 Scheduler `run_all_plug_dryruns.ps1` (4.2)

Arquivo: `scripts/data_ops_scheduler/run_all_plug_dryruns.ps1`.

Removidos: `amazon_mirror`, `tier2_chat1..5`.
Adicionadas: `amazon_local_legacy_backfill`, `amazon_mirror_primary`,
`tier2_global_artifact`, `winegod_admin_legacy_mixed`.

Lista canonica final:

```text
winegod_admin_world
vinhos_brasil_legacy
amazon_local
amazon_local_legacy_backfill
amazon_mirror_primary
tier1_global
tier2_global_artifact
tier2_br
winegod_admin_legacy_mixed
```

Dry-run only. Continua usando `Invoke-Step` com `--dry-run`.

### 2.3 Contrato `TIER_COMMERCE_CONTRACT.md` (4.3)

Arquivo: `docs/TIER_COMMERCE_CONTRACT.md`.

Paths atualizados:

```
reports/data_ops_artifacts/amazon_mirror/<prefix>.jsonl
reports/data_ops_artifacts/tier1/<prefix>.jsonl
reports/data_ops_artifacts/tier2_global/<prefix>.jsonl
reports/data_ops_artifacts/tier2/br/<prefix>.jsonl
```

`tier2_chat1..5` documentados como historicos/DEPRECATED, nao como
particoes reais. Nao e mais "chat1..5 ou br".

### 2.4 README scheduler (4.4)

Arquivo: `scripts/data_ops_scheduler/README.md`.

Paths alinhados com 4.3 + nota historica explicita do colapso Tier2
(`tier2_global/` substituiu `tier2/chat1..5/`; `tier2/br/` separado por
filtro de pais real).

### 2.5 Validator CLI - full-scan real (4.5)

Arquivos:

- `sdk/plugs/commerce_dq_v3/artifact_contract.py` - nova funcao
  `validate_artifact_dir_full()` que:
  - le TODAS as linhas JSONL nao vazias (sem janela);
  - reprova qualquer linha invalida pos-janela;
  - compara `summary.items_emitted` com total real de linhas validas e
    reprova o contrato se divergir (`summary_items_emitted_mismatch=<X>_vs_<Y>`).
- `scripts/data_ops_producers/validate_commerce_artifact.py` - CLI
  reescrito:
  - **default = full scan**;
  - flag opcional `--window <N>` para smoke rapido (nao substitui full);
  - `--item-limit` deprecated (mantido para compatibilidade);
  - saida inclui `mode=full|window=N` e `lines_validated=<n>` quando full.
- `scripts/data_ops_producers/tests/test_validate_commerce_artifact_full.py`
  (novo) - 6 testes cobrindo:
  - artefato 100% valido passa;
  - linha invalida na posicao 211 passa em janela=200 mas reprova em full
    (prova direta do finding do Codex admin);
  - `summary.items_emitted=999` com 10 items reais reprova;
  - summary SHA mismatch reprova;
  - `expected_family` divergente reprova;
  - artefato ausente retorna `artefato_ausente`.
- `reports/data_ops_artifacts/amazon_mirror/README.md` - instrucoes do PC
  espelho atualizadas para rodar FULL por default (sem `--item-limit`) e
  explicar `--window` como opcao de smoke rapido.
- `docs/RUNBOOK_COMMERCE_OPERACAO_RECORRENTE.md` - mesmo ajuste na secao
  "Residual externo Amazon".

O plug em dry-run continua usando janela curta (`item_limit=--limit`);
isso nao e validacao final, e apenas sample para observabilidade. A
validacao final do artefato antes de apply passa a ser o CLI full.

## 3. Arquivos alterados

### Modificados

- `sdk/adapters/manifests/commerce_winegod_admin_legacy_mixed.yaml`
- `scripts/data_ops_scheduler/run_all_plug_dryruns.ps1`
- `docs/TIER_COMMERCE_CONTRACT.md`
- `scripts/data_ops_scheduler/README.md`
- `sdk/plugs/commerce_dq_v3/artifact_contract.py`
- `scripts/data_ops_producers/validate_commerce_artifact.py`
- `reports/data_ops_artifacts/amazon_mirror/README.md`
- `docs/RUNBOOK_COMMERCE_OPERACAO_RECORRENTE.md`

### Criados

- `scripts/data_ops_producers/tests/test_validate_commerce_artifact_full.py`
- `reports/WINEGOD_CORRECAO_COMMERCE_OPERACAO_RESIDUAL_EXTERNO_FINAL_2026-04-24.md` (ESTE)
- `CLAUDE_RESPOSTAS_CORRECAO_COMMERCE_OPERACAO_RESIDUAL_EXTERNO_FINAL_2026-04-24.md`

## 4. Comandos rodados e resultados

### 4.1 Testes

```powershell
python -m pytest sdk/plugs/commerce_dq_v3 scripts/data_ops_producers/tests -q
# 33 passed in 2.06s  (27 antigos + 6 novos de full-scan)

python -m pytest sdk/adapters/tests -q
# 43 passed in 1.32s

python -m pytest sdk/tests -q
# 76 passed in 1.17s
```

**Total: 152 passed, 0 failed, 0 regressao.**

### 4.2 Validator CLI (modo FULL - novo default)

```powershell
python scripts/data_ops_producers/validate_commerce_artifact.py --artifact-dir reports/data_ops_artifacts/tier1 --expected-family tier1
# OK mode=full artifact=20260424_040740_tier1_global.jsonl items_validados=346 lines_validated=346 sha256=e71322a4fb38

python scripts/data_ops_producers/validate_commerce_artifact.py --artifact-dir reports/data_ops_artifacts/tier2_global --expected-family tier2
# OK mode=full artifact=20260424_040736_tier2_global_artifact.jsonl items_validados=176 lines_validated=176 sha256=493541ade1e4

python scripts/data_ops_producers/validate_commerce_artifact.py --artifact-dir reports/data_ops_artifacts/tier2/br --expected-family tier2
# OK mode=full artifact=20260424_040742_tier2_br.jsonl items_validados=200 lines_validated=200 sha256=e1795383591e

python scripts/data_ops_producers/validate_commerce_artifact.py --artifact-dir reports/data_ops_artifacts/amazon_mirror --expected-family amazon_mirror_primary
# FAIL mode=full reason=nenhum_artefato_jsonl_em=reports\data_ops_artifacts\amazon_mirror (exit=2, esperado ate PC espelho entregar)
```

### 4.3 Scheduler canonico

```powershell
powershell -File scripts/data_ops_scheduler/run_commerce_artifact_dryruns.ps1 -Limit 10
# ==> commerce artifact dry-run source=amazon_mirror_primary limit=10  -> blocked_external_host
# ==> commerce artifact dry-run source=tier1_global limit=10           -> observed
# ==> commerce artifact dry-run source=tier2_global_artifact limit=10  -> observed
# ==> commerce artifact dry-run source=tier2_br limit=10               -> observed
# ==> commerce artifact dryruns done
```

### 4.4 Scheduler completo

```powershell
powershell -File scripts/data_ops_scheduler/run_all_plug_dryruns.ps1 -CommerceLimit 10 -ReviewsLimit 5 -DiscoveryLimit 5 -EnrichmentLimit 5
```

Commerce (9 fontes canonicas):

| Fonte | state |
|---|---|
| winegod_admin_world | observed |
| vinhos_brasil_legacy | observed |
| amazon_local | observed |
| amazon_local_legacy_backfill | observed |
| amazon_mirror_primary | blocked_external_host |
| tier1_global | observed |
| tier2_global_artifact | observed |
| tier2_br | observed |
| winegod_admin_legacy_mixed | blocked_missing_source |

Reviews/discovery/enrichment rodaram dry-run sem erro (escopo respeitado,
nao alterei codigo dessas frentes).

## 5. Confirmacao de zero apply

- Nenhum comando com `--apply` foi executado.
- Nenhuma escrita direta em `public.wines` / `public.wine_sources`.
- Nenhuma chamada a Gemini pago.
- Zero `git reset --hard`, `git push --force`, merge em main, ou deploy Render/Vercel.
- Zero writer paralelo.
- Zero mudanca em plug/runner/exporter commerce (so endurecimento do validador
  via nova funcao nao-destrutiva).

## 6. Estado final de Amazon mirror

- Fonte `amazon_mirror_primary` continua `blocked_external_host` honesto
  enquanto o JSONL + summary do PC espelho nao aparecerem em
  `reports/data_ops_artifacts/amazon_mirror/`.
- Validator CLI em modo FULL confirma `FAIL reason=nenhum_artefato_jsonl_em=...`
  (exit=2), comportamento esperado.
- Scheduler local ja esta pronto para consumir automaticamente o JSONL
  mais recente assim que aparecer.
- README in-place + runbook referenciam o modo FULL como checagem final
  antes de plugar.

## 7. Branch / commit / push

- Branch: `data-ops/correcao-commerce-operacao-residual-externo-final-20260424`.
- Base: `5dc824a0` (HEAD do remote `origin/data-ops/execucao-total-commerce-operacao-residual-externo-final-20260424`).
- Commit final corretivo: a ser pinado logo apos push.
- Push: sera feito para `origin` com a mesma branch.

## 8. Nota sobre a branch local de reviews

A branch local `data-ops/execucao-total-reviews-dominio-final-20260424`
segue tendo o commit duplicado `1c081730 feat(data-ops): commerce runbook
+ amazon_mirror README + artifact validator CLI` (efeito colateral da
sessao anterior por acidente de checkout). O Codex admin deve decidir
se limpa essa branch local antes de qualquer push futuro dela. Nao fiz
`git reset --hard` nesta sessao por regra do CLAUDE.md.

Se o Codex admin quiser limpar: `git checkout <branch-reviews> && git reset --keep HEAD~1`
(keep preserva working tree; alternativa nao-destrutiva ao reset --hard).

## 9. Bloqueios externos remanescentes

Um unico bloqueio externo legitimo: PC espelho Amazon precisa depositar
JSONL + summary em `reports/data_ops_artifacts/amazon_mirror/`. Nenhum
outro bloqueio. Tudo do lado local esta endurecido e pronto para consumir.

## Apendice - Arquivo a repassar para o Codex admin

```text
C:\winegod-app\reports\WINEGOD_CORRECAO_COMMERCE_OPERACAO_RESIDUAL_EXTERNO_FINAL_2026-04-24.md
C:\winegod-app\CLAUDE_RESPOSTAS_CORRECAO_COMMERCE_OPERACAO_RESIDUAL_EXTERNO_FINAL_2026-04-24.md
```
