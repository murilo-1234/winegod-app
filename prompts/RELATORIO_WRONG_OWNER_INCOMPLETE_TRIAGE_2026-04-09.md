# Relatório — Triage dos 606 Incomplete (Classe B wrong_owner)

**Data**: 2026-04-09
**Escopo**: READ-ONLY — nenhum dado foi alterado no banco
**Status**: CONCLUÍDO

---

## 1. Resumo executivo

Dos 606 casos `incomplete` da Classe B (pilot_candidates sem ws_id), a triage canônica no estado atual do banco revelou:

| Classe | Total | % |
|---|---|---|
| **stale_or_already_fixed** | **567** | 93.6% |
| **recoverable_safe** | **39** | 6.4% |
| ambiguous | 0 | 0% |
| unresolved_incomplete | 0 | 0% |
| errors | 0 | 0% |

**93.6% dos incomplete já estavam resolvidos** — a grande maioria pela Classe A (delete do link errado quando o expected já possuía o link correto) e 36 pela Classe B safe (com actual/expected invertidos no pilot).

---

## 2. Fonte dos 606 incomplete

**Arquivo**: `C:\winegod-app\scripts\wrong_owner_move_needed_incomplete.csv`

Já existia. Gerado pela consolidação original da Classe B (`consolidar_classe_b_completo.py`).

### Schema

| Coluna | Populated | Observação |
|---|---|---|
| ws_id | **0** (todos vazios) | PROBLEMA CENTRAL — nenhum ws_id no pilot |
| actual_wine_id | 606 | 471 únicos |
| expected_wine_id | 606 | 217 únicos |
| store_id | 606 | 261 únicos |
| url | 606 | 606 únicos (todos distintos) |
| clean_id | 606 | 539 únicos |
| origem_csv | 606 | Todos "pilot_candidates" |
| owner_range | 606 | Todos "pilot" |
| classificacao | 606 | Todos "incomplete" |
| motivo | 606 | Todos "pilot_candidate_sem_ws_id_nao_coberto" |

**Todos os 606 tinham dados suficientes** (url, store_id, actual_wine_id) para tentar recuperar o ws_id no banco via SELECT canônico.

---

## 3. Detalhamento dos stale (567)

### 3a. already_on_expected_owner: 527 (87.0%)

A row com `(url, store_id)` já foi encontrada no `expected_wine_id`. Isso significa que o link correto já existe no owner correto. Cenário mais provável: a Classe A deletou o link duplicado no actual, e o link no expected já existia antes (era justamente a prova de que o caso era Classe A no bloco original).

**Ação necessária**: nenhuma. Estado correto.

### 3b. B_safe_overlap_inverted: 36 (5.9%)

Esses 36 ws_ids apareciam tanto no pilot_candidates quanto no CSV safe executado (`wrong_owner_move_needed_safe.csv`). Descoberta: o pilot_candidates tinha `actual` e `expected` **invertidos** para todos os 36 (35 perfeitamente invertidos, 1 com padrão misto mas igualmente já corrigido).

Prova: o DB wine_id atual de todos os 36 coincide com o `expected_wine_id` do safe executado (e com o `actual_wine_id` do pilot_candidates).

**Ação necessária**: nenhuma. A Classe B safe já os corrigiu na direção correta.

### 3c. moved_to_third_owner: 4 (0.7%)

A row com `(url, store_id)` não está mais no actual nem no expected. Existe em um terceiro wine_id. O estado mudou por outro processo.

Casos:
- ws actual=31250 expected=1220062 → agora em wine=1537330
- ws actual=130369 expected=1295767 → agora em wine=995433
- ws actual=2015639 expected=353155 → agora em wine=45784
- ws actual=2092648 expected=1540053 → agora em wine=345922

**Ação necessária**: nenhuma nesta rodada. Se desejado, investigar em rodada futura.

---

## 4. Detalhamento dos recoverable_safe (39)

### Critérios de classificação (todos devem ser verdadeiros)

1. Exatamente 1 row candidata em `wine_sources` com `(url, store_id, wine_id = actual_wine_id)`
2. `expected_wine_id` existe na tabela `wines`
3. Nenhuma row com `(url, store_id, wine_id = expected_wine_id)` existe (não criaria duplicata)
4. O `ws_id` recuperado é único e inequívoco

### Verificações de sanidade realizadas (TODAS passaram)

- [x] Nenhum actual == expected (0 no-ops)
- [x] Todos os 39 ws_ids existem no DB e apontam para actual_wine_id
- [x] Todos os expected_wine_ids existem na tabela wines
- [x] Nenhuma duplicata seria criada no expected
- [x] Nenhum overlap com os 43 ambiguous da Classe B original
- [x] Todos os 39 ws_ids são únicos

### Estatísticas dos 39 safe

| Métrica | Valor |
|---|---|
| ws_ids únicos | 39 |
| actual_wine_id únicos | 37 |
| expected_wine_id únicos | 29 |
| store_id únicos | 20 |
| URLs únicos | 39 |

### Risco identificado: inversão pilot

36 dos 606 originais tinham actual/expected invertidos no pilot_candidates. Embora esses 36 tenham sido removidos (já corrigidos pela B safe), **não há garantia de que os 39 remanescentes também não sofrem de inversão**. Diferença: para os 36, a cross-referência com o safe CSV permitiu detectar a inversão. Para os 39, não existe cross-referência.

**Mitigação recomendada**: piloto pequeno (25 casos) com verificação manual pós-execução.

---

## 5. Artefatos gerados

| Arquivo | Linhas | Descrição |
|---|---|---|
| `scripts/wrong_owner_move_needed_incomplete_input_audit.csv` | 606 | Audit completo com triage_class e triage_reason |
| `scripts/wrong_owner_move_needed_incomplete_recoverable_safe.csv` | 39 | Casos recuperáveis com ws_id |
| `scripts/wrong_owner_move_needed_incomplete_ambiguous.csv` | 0 | Nenhum ambíguo |
| `scripts/wrong_owner_move_needed_incomplete_stale.csv` | 567 | Já corrigidos ou removidos |
| `scripts/wrong_owner_move_needed_incomplete_unresolved.csv` | 0 | Nenhum irrecuperável |
| `scripts/wrong_owner_move_needed_incomplete_stats.json` | 1 | Stats + metadados da correção |
| `scripts/triage_incomplete_readonly.py` | 1 | Script de triage READ-ONLY |
| `scripts/triage_incomplete_correct_overlap.py` | 1 | Correção dos 36 overlap |
| `prompts/RELATORIO_WRONG_OWNER_INCOMPLETE_TRIAGE_2026-04-09.md` | 1 | Este relatório |

---

## 6. Proposta da próxima execução

### 6a. Escala

- 39 casos recoverable_safe
- Escala pequena o suficiente para execução cuidadosa

### 6b. Recomendação: piloto de 25

**Justificativa**:
- São apenas 39 casos no total
- Risco de inversão pilot (detectado em 36 dos 606 originais)
- Piloto de 25 permite verificação manual caso a caso antes de fechar os 14 restantes
- Se piloto OK → executar os 14 restantes imediatamente

### 6c. Estratégia de execução

```sql
UPDATE wine_sources
SET wine_id = <expected_wine_id>
WHERE id = <ws_id>
  AND wine_id = <actual_wine_id>;  -- guard clause
```

### 6d. Checks obrigatórios antes de cada UPDATE

1. `expected_wine_id` existe: `SELECT 1 FROM wines WHERE id = <expected>`
2. `ws_id` ainda aponta para actual: `SELECT wine_id FROM wine_sources WHERE id = <ws_id>`
3. Não criar duplicata: `SELECT 1 FROM wine_sources WHERE wine_id = <expected> AND url = <url> AND store_id = <store_id>`

### 6e. Revert lossless

Para cada ws_id processado, gerar CSV:
```
ws_id, old_wine_id (actual), new_wine_id (expected), url, store_id
```

Revert:
```sql
UPDATE wine_sources
SET wine_id = <old_wine_id>
WHERE id = <ws_id>
  AND wine_id = <new_wine_id>;
```

### 6f. Risco residual real

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Inversão actual/expected (como nos 36) | Baixa-média | Piloto de 25 + verificação manual |
| expected deletado entre triage e execução | Muito baixa | Check 1 antes do UPDATE |
| ws_id já corrigido por outro processo | Baixa | Guard clause `wine_id = actual` |
| Duplicata no expected | Nula (verificado) | Check 3 antes do UPDATE |

### 6g. O que sobra depois

| Classe | Total | Ação |
|---|---|---|
| stale_or_already_fixed | 567 | Nenhuma — encerrados |
| recoverable_safe (se piloto OK) | 0 | Todos executados |
| ambiguous (original Classe B) | 43 | Investigação manual futura |
| unresolved | 0 | Nenhum |

---

## 7. Números finais consolidados (wrong_owner completo)

| Trilha | Status | Total |
|---|---|---|
| Classe A (delete_only_safe) | ✅ CONCLUÍDA | 265,524 deletes |
| Classe B safe (move_needed) | ✅ CONCLUÍDA | 4,158 updates |
| Classe B incomplete → stale | ✅ ENCERRADOS | 567 (já resolvidos) |
| Classe B incomplete → recoverable | ⏳ PROPOSTO | 39 (piloto de 25 + 14) |
| Classe B ambiguous | 🔒 BLOQUEADO | 43 (investigação manual) |

**Total wrong_owner processado**: 265,524 + 4,158 + 567 = **270,249**
**Backlog remanescente**: 39 recoverable + 43 ambiguous = **82 casos**
