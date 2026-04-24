# WINEGOD - Correcao Minima Commerce README + Validator

Data: 2026-04-24  
Executor: Claude Code (Opus 4.7 1M context)  
Prompt fonte: `prompts/PROMPT_CLAUDE_CORRECAO_MINIMA_COMMERCE_README_VALIDATOR_2026-04-24.md`  
Branch: `data-ops/correcao-minima-commerce-readme-validator-20260424`  
Base: `31a6ac5f docs(data-ops): pin 6a682089 SHA in corrective commerce docs` (origin)  
Auditor final: **Codex admin**

## 1. Veredito final

```text
APROVADO_RESIDUO_DOCUMENTAL_E_VALIDATOR_TIPADO_FECHADOS
```

As 2 folgas residuais apontadas pela nova auditoria Codex admin foram
resolvidas e persistem em arquivo real:

1. `scripts/data_ops_scheduler/README.md` nao aponta mais
   `tier2/<chat>/` como path esperado.
2. `validate_artifact_dir_full()` rejeita `summary.items_emitted`
   nao-inteiro (string, float, bool) com nota explicita.

156 testes passam (37 commerce+producers + 43 adapters + 76 sdk).
Zero apply executado.

## 2. Findings corrigidos

### 2.1 README scheduler (Finding 1)

Arquivo: `scripts/data_ops_scheduler/README.md`.

Antes:

```
reports/data_ops_artifacts/amazon_mirror/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier1/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier2/<chat>/<timestamp>_<run_id>.jsonl
```

Depois:

```
reports/data_ops_artifacts/amazon_mirror/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier1/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier2_global/<timestamp>_<run_id>.jsonl
reports/data_ops_artifacts/tier2/br/<timestamp>_<run_id>.jsonl
```

+ nota explicita:

> `tier2_global/` e o feed Tier2 global unico; `tier2/br/` e o Tier2 Brasil
> por filtro real de pais. `tier2/chat1..5/` e historico/deprecated e nao
> deve ser usado (colapsados em `tier2_global_artifact` por falta de
> particao disjunta reproduzivel entre chats Codex).

Corrigida tambem a frase sobre `run_commerce_artifact_dryruns.ps1`:
agora diferencia estado por tipo de fonte:

- `amazon_mirror_primary` sem artefato -> `blocked_external_host` honesto.
- Tier1/Tier2 sem artefato -> `blocked_contract_missing` honesto.

### 2.2 Validator full rejeita `items_emitted` nao-inteiro (Finding 2)

Arquivo: `sdk/plugs/commerce_dq_v3/artifact_contract.py`.

Antes:

```python
declared = summary_data.get("items_emitted") if summary_data else None
if isinstance(declared, int) and declared != non_empty_lines:
    items_emitted_errors.append(...mismatch...)
```

Problema: `items_emitted="200"` (string) nao caia no `isinstance(int)` e
passava silenciosamente. O contrato operacional espera contador numerico.

Depois:

```python
declared = summary_data.get("items_emitted") if summary_data else None
if declared is None:
    pass  # validate_summary ja reporta summary_faltando=...
elif isinstance(declared, bool) or not isinstance(declared, int):
    items_emitted_errors.append(f"summary_items_emitted_not_int={declared!r}")
elif declared != non_empty_lines:
    items_emitted_errors.append(f"summary_items_emitted_mismatch={declared}_vs_{non_empty_lines}")
```

Notar o cuidado com `bool` (subclasse de `int` em Python mas invalido
como contador).

Novos testes em
`scripts/data_ops_producers/tests/test_validate_commerce_artifact_full.py`:

- `test_full_rejeita_items_emitted_string` - string `"10"` reprova.
- `test_full_rejeita_items_emitted_float` - `5.0` reprova.
- `test_full_rejeita_items_emitted_bool` - `True` reprova (subclasse `int`).
- `test_window_ignora_type_check_de_items_emitted` - modo janela
  (usado pelo runner em dry-run) nao faz essa checagem; garante
  nao-regressao do runner.

Docstring de `validate_artifact_dir_full()` atualizada para documentar
o novo comportamento.

Modo janela (`validate_artifact_dir()`) **nao** foi alterado: o runner em
dry-run continua podendo consumir JSONL com `items_emitted` nao-inteiro
sem quebrar. Apenas o modo full (CLI operacional antes de plugar)
endureceu.

## 3. Arquivos alterados

### Modificados

- `scripts/data_ops_scheduler/README.md` - paths + nota Tier2 + estado
  honesto por tipo de fonte.
- `sdk/plugs/commerce_dq_v3/artifact_contract.py` - checagem de tipo em
  `items_emitted` + docstring atualizada.
- `scripts/data_ops_producers/tests/test_validate_commerce_artifact_full.py`
  - helper `_UNSET` sentinel + `Any` import; 4 testes novos.

### Criados

- `reports/WINEGOD_CORRECAO_MINIMA_COMMERCE_README_VALIDATOR_2026-04-24.md` (ESTE)
- `CLAUDE_RESPOSTAS_CORRECAO_MINIMA_COMMERCE_README_VALIDATOR_2026-04-24.md`

## 4. Comandos rodados e resultados

### 4.1 Testes

```powershell
python -m pytest sdk/plugs/commerce_dq_v3 scripts/data_ops_producers/tests -q
# 37 passed in 1.98s  (33 antigos + 4 novos de items_emitted tipado)

python -m pytest sdk/adapters/tests -q
# 43 passed in 1.32s

python -m pytest sdk/tests -q
# 76 passed in 1.43s
```

**Total: 156 passed, 0 failed, 0 regressao.**

### 4.2 Validator CLI (modo FULL)

```
tier1         -> OK mode=full items_validados=346 lines_validated=346 sha256=e71322a4fb38
tier2_global  -> OK mode=full items_validados=176 lines_validated=176 sha256=493541ade1e4
tier2/br      -> OK mode=full items_validados=200 lines_validated=200 sha256=e1795383591e
amazon_mirror -> FAIL reason=nenhum_artefato_jsonl_em=... (exit=2, esperado)
```

### 4.3 Scheduler canonico

```
run_commerce_artifact_dryruns.ps1 -Limit 10:
  amazon_mirror_primary -> blocked_external_host
  tier1_global          -> observed
  tier2_global_artifact -> observed
  tier2_br              -> observed
```

### 4.4 Scheduler completo

```
run_all_plug_dryruns.ps1 -CommerceLimit 10 -ReviewsLimit 5 -DiscoveryLimit 5 -EnrichmentLimit 5:
  9 commerce (7 observed + 2 blocked honestos)
  5 reviews
  1 discovery
  1 enrichment
  Zero erro
```

States commerce:

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

## 5. Confirmacao de zero apply

- Nenhum comando com `--apply` executado.
- Nenhuma escrita direta em `public.wines` / `public.wine_sources`.
- Nenhuma chamada Gemini pago.
- Zero `git reset --hard`, `git push --force`, merge em main, ou deploy.
- Zero writer paralelo.
- Zero mudanca em reviews/discovery/enrichment.

## 6. Branch / commit / push

- Branch: `data-ops/correcao-minima-commerce-readme-validator-20260424`.
- Base: `31a6ac5f` (HEAD do remote
  `origin/data-ops/correcao-commerce-operacao-residual-externo-final-20260424`).
- Commit corretivo final: `7d617434 fix(data-ops): commerce README tier2 paths + validator full rejeita items_emitted nao-int`.
- Remote: push para `origin/data-ops/correcao-minima-commerce-readme-validator-20260424`.

## 7. Residual externo Amazon mirror

Continua um unico bloqueio externo legitimo: PC espelho precisa depositar
JSONL + summary em `reports/data_ops_artifacts/amazon_mirror/`. Validator
em modo full confirma `FAIL reason=nenhum_artefato_jsonl_em=...` (exit=2,
comportamento esperado). Scheduler local ja pronto para consumir
automaticamente o mais recente quando aparecer.

## Apendice - Arquivo a repassar para o Codex admin

```text
C:\winegod-app\reports\WINEGOD_CORRECAO_MINIMA_COMMERCE_README_VALIDATOR_2026-04-24.md
C:\winegod-app\CLAUDE_RESPOSTAS_CORRECAO_MINIMA_COMMERCE_README_VALIDATOR_2026-04-24.md
```
