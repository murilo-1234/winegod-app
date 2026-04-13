# Relatorio Final Wrong_Owner — 2026-04-09

## Resumo executivo

Cleanup de wine_sources com owner errado no Render.
Causa raiz: `check_exists_in_render` no `import_render_z.py` redirecionava links para wines com produtores genericos.

**Frente encerrada operacionalmente.** Restam apenas 43 casos ambiguos que requerem investigacao manual.

## Numeros finais consolidados

### Classe A (delete_only_safe) — CONCLUIDA

| Metrica | Valor |
|---|---|
| ws_id unicos deletados | **266,274** |
| Consolidacao final | 265,524 |
| Gap 50501-52500 (fechado depois) | +750 |
| Revert manifest | 265,524 linhas (consolidacao) + reverts do gap |
| Erros | 0 |
| Skipped | 0 |

Nota: a consolidacao final reportou 265,524. O gap de 2,000 owners na faixa 50501-52500 foi processado separadamente e adicionou 750 deletes, totalizando **266,274**.

### Classe B (move_needed) — CONCLUIDA

| Metrica | Valor |
|---|---|
| **Total executado** | **4,197 updates** |
| Classe B safe principal | 4,158 (100 piloto + 4,058 batches) |
| Incomplete recoverable_safe | 39 (25 piloto + 14 restante) |
| Erros | 0 |
| Skipped | 0 |

### Classe B — Incomplete (606 casos triados)

| Classe | Total | Acao |
|---|---|---|
| stale_or_already_fixed | 567 | Nenhuma — ja resolvidos |
| recoverable_safe | 39 | Executados (incluidos nos 4,197 acima) |
| ambiguous | 0 | — |
| unresolved | 0 | — |

Detalhamento dos 567 stale:
- 527 — link ja existia no expected_wine_id (resolvidos pela Classe A)
- 36 — ja corrigidos pela Classe B safe (pilot_candidates tinha actual/expected invertidos)
- 4 — row migrou para terceiro owner

### Classe B — Ambiguos globais — BLOQUEADO

| Metrica | Valor |
|---|---|
| Total | **43** |

Todos os 43 ws_ids ambiguos compartilham o mesmo padrao: URL e apenas o dominio da loja (ex: `https://www.chicovalley.com.br`), sem path de produto. Multiplos owner ranges classificaram o mesmo ws_id com expected_wine_id diferentes.

**Acao**: requer investigacao manual. Nao executavel automaticamente.

### Classe C (ambiguo legado) — ENCERRADO

| Metrica | Valor |
|---|---|
| Total | **2** |

Casos com 2+ owners errados e owner correto ausente. Encerrados como irrecuperaveis automaticamente.

---

## Totais globais da frente wrong_owner

| Operacao | Total |
|---|---|
| **Deletes (Classe A)** | **266,274** |
| **Updates (Classe B)** | **4,197** |
| **Total de wine_sources corrigidos** | **270,471** |
| Stale/already_fixed (incomplete) | 567 |
| Ambiguous (bloqueado) | 43 + 2 = 45 |
| **Backlog remanescente executavel** | **0** |

---

## Cobertura por metodo

| Metodo | Faixa owners | Blocos | ws_ids deletados |
|---|---|---|---|
| Piloto 100 | 1-500 | 1 | 100 |
| v1/v2 (bloco a bloco) | 501-50500 | 100 | 159,751 |
| Hybrid (batch + SQL classify) | 52501-300500 | 124 | 99,832* |
| SQL (DELETE RETURNING) | 114501-119500 | 1 | 1,650 |
| SQL final (low yield stop) | 119501-144500 | 5 | 0 |
| Gap 50501-52500 | 50501-52500 | 1 | 750 |

*Hybrid inclui overlap com SQL na faixa 114501-144500.

---

## Gaps e overlaps

### Gap: owners 50501-52500 — FECHADO

- v1/v2 termina em 50500
- hybrid comeca em 52501
- **Fechado**: 750 deletes executados nessa faixa

### Overlap: owners 114501-144500

- Processado tanto pelo hybrid quanto pelo SQL
- SQL encontrou 0 Classe A (confirmando que hybrid ja havia limpado)
- Sem duplicacao de deletes

---

## Decisoes tecnicas tomadas

1. **Nunca usar check_exists_in_render** para redistribuir links
2. **Owner canonico** sempre via linhagem local: y2_results.vivino_id -> wines_clean -> pais_tabela + id_original -> vinhos_XX_fontes
3. **Classe A = delete_only_safe**: owner correto ja possui o link, apenas remover copias erradas
4. **Classe B = move_needed**: UPDATE de wine_id com guard clause atomica
5. **Chave composta (url, store_id)** para classificacao e validacao
6. **Revert lossless** via CSV com snapshot completo de cada linha alterada
7. **Incomplete**: triagem canonica READ-ONLY antes de qualquer execucao, detectou 36 casos com inversao pilot
8. **ws_id** como identidade fisica da row em wine_sources para toda operacao

---

## Artefatos de revert — Classe B (CRITICOS)

Estes sao os 4 CSVs de revert que permitem reverter QUALQUER update da Classe B:

| Arquivo | Linhas | Escopo |
|---|---|---|
| `scripts/wrong_owner_move_needed_pilot_100_revert.csv` | 100 | Piloto inicial Classe B safe |
| `scripts/wrong_owner_move_needed_batch_all_revert.csv` | 4,058 | Batches Classe B safe |
| `scripts/wrong_owner_move_needed_incomplete_pilot_25_revert.csv` | 25 | Piloto incomplete |
| `scripts/wrong_owner_move_needed_incomplete_restante_14_revert.csv` | 14 | Restante incomplete |
| **Total** | **4,197** | **Toda a Classe B** |

Schema de cada revert CSV:
```
ws_id, old_wine_id, new_wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em
```

Instrucao de revert (por linha):
```sql
UPDATE wine_sources
SET wine_id = <old_wine_id>
WHERE id = <ws_id>
  AND wine_id = <new_wine_id>;
```

---

## Artefatos de revert — Classe A

| Arquivo | Linhas |
|---|---|
| `scripts/wrong_owner_revert_manifest_final.csv` | 265,524 |
| Reverts do gap 50501-52500 | +750 |

---

## Outros artefatos consolidados

### CSVs de classificacao
- `wrong_owner_move_needed_consolidado_final.csv` — 4,201 linhas (Classe B bruto dedup)
- `wrong_owner_move_needed_safe.csv` — 4,158 linhas (Classe B safe)
- `wrong_owner_move_needed_ambiguous.csv` — 43 linhas (ambiguos globais)
- `wrong_owner_move_needed_incomplete.csv` — 606 linhas (incomplete original)
- `wrong_owner_move_needed_incomplete_input_audit.csv` — 606 linhas (triagem completa)
- `wrong_owner_move_needed_incomplete_recoverable_safe.csv` — 39 linhas
- `wrong_owner_move_needed_incomplete_stale.csv` — 567 linhas
- `wrong_owner_move_needed_incomplete_stats.json` — stats da triagem

### Scripts
- `consolidar_wrong_owner_artifacts.py` — consolidacao Classe A
- `consolidar_classe_b_completo.py` — consolidacao Classe B
- `wrong_owner_batch_v2.py` — cleanup v1/v2
- `wrong_owner_hybrid_autopilot.py` — cleanup hybrid
- `wrong_owner_sql_final.py` — cleanup SQL
- `triage_incomplete_readonly.py` — triagem READ-ONLY dos incomplete
- `triage_incomplete_correct_overlap.py` — correcao dos 36 overlap
- `wrong_owner_incomplete_pilot_25.py` — piloto incomplete
- `wrong_owner_incomplete_restante_14.py` — restante incomplete

### Relatorios
- `prompts/RELATORIO_WRONG_OWNER_FINAL_2026-04-09.md` — este documento
- `prompts/RELATORIO_WRONG_OWNER_INCOMPLETE_TRIAGE_2026-04-09.md` — triagem dos 606 incomplete
- `prompts/PLANO_EXECUCAO_WRONG_OWNER_CLASSE_B.md` — plano original Classe B
- `prompts/PLANO_POS_RUN_CLASSE_B_E_NOT_WINE.md` — plano pos-run

---

## Estado Final da Frente wrong_owner

### CONCLUIDO

| Trilha | Operacao | Total | Status |
|---|---|---|---|
| Classe A | DELETE de links duplicados | 266,274 | CONCLUIDA |
| Classe B safe | UPDATE de wine_id | 4,158 | CONCLUIDA |
| Classe B incomplete → recoverable | UPDATE de wine_id | 39 | CONCLUIDA |
| Classe B incomplete → stale | Nenhuma (ja resolvidos) | 567 | ENCERRADO |
| Classe C (ambiguo legado) | Nenhuma (irrecuperavel) | 2 | ENCERRADO |

### BLOQUEADO (requer acao manual)

| Trilha | Total | Motivo |
|---|---|---|
| Classe B ambiguous | 43 | URLs domain-only, multiplos expected conflitantes |

### Encerramento

A frente wrong_owner esta **operacionalmente encerrada**. Todas as correcoes automatizaveis foram executadas com sucesso. Zero erros, zero skips nas execucoes finais. Todos os reverts sao lossless e deterministicos.

Os 43 ambiguos restantes nao sao executaveis automaticamente — cada um requer prova manual de qual e o expected_wine_id correto. Recomendacao: tratar como backlog de baixa prioridade, pois o impacto de 43 links com owner errado e negligivel frente aos 270,471 ja corrigidos.
