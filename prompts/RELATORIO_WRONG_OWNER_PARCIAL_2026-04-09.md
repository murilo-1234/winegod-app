# Relatorio Parcial — Wrong Owner Cleanup

**Data**: 2026-04-09 ~18:38 UTC-3
**Status**: Run final SQL ainda em execucao (`wrong_owner_sql_final.py`)

---

## 1. O que ja foi corrigido

O pipeline wrong_owner identifica `wine_sources` cujo `wine_id` aponta para o vinho errado (atribuidos por `check_exists_in_render` com produtores genericos). O cleanup deleta essas linhas para descontaminar a base.

### Deletes efetivados (Classe A)

| Fonte | Arquivos | Linhas deletadas |
|---|---|---|
| `wrong_owner_delete_only_executed` (piloto) | 1 | 4.191 |
| `wo_del_executed_*` (fase del, owners 501-50500) | 100 | 159.751 |
| **Total Classe A dedup** | **101** | **163.942** |

Esses 163.942 `wine_sources` foram deletados do Render com sucesso e possuem manifesto de revert.

### Deletes via fase hybrid (sem exec CSV separado)

A fase hybrid (owners 52501-242500) nao gera `wo_del_executed` — ela deleta diretamente e grava revert. Os reverts hybrid somam **85.771 linhas** adicionais deletadas.

### Total acumulado de deletes

| Componente | Linhas |
|---|---|
| Exec manifest (del + piloto) | 163.942 |
| Hybrid revert (deletes diretos) | 85.771 |
| SQL rev (overlap com hybrid, owners 114501-119500) | 1.650 |
| Pilot 100 revert | 100 |
| **Total revert manifest dedup** | **251.463** |

**~251k wine_sources deletados ate agora.**

---

## 2. Tranches e blocos presentes nos artefatos

### Fase "del" (step 500)
- Range: owners **501 a 50.500**
- 100 tranches continuas, sem gaps
- Cada tranche gera: `wo_del_candidates`, `wo_del_executed`, `wo_del_revert`, `wo_move_needed`

### Fase "hybrid" (step 2000)
- Range: owners **52.501 a 242.500** (95 tranches ate o momento)
- Sem gaps internos
- Cada tranche gera: `wo_hybrid_b`, `wo_hybrid_rev`
- Apenas 1 tranche gerou `wo_hybrid_c` (84501-86500)

### Fase "sql" (step 5000)
- Range: owners **114.501 a 144.500** (6 tranches)
- 1 tranche de revert (114501-119500)
- **Overlap intencional** com hybrid: mesmo range de owners processado por metodo SQL direto

### Fase inicial (piloto)
- `wrong_owner_delete_only_*`: 1 lote (~4.191 linhas)
- `wrong_owner_pilot_*`: 606 candidatos, 100 reverts
- `wrong_owner_ambiguous_candidates`: vazio (header only)
- `wrong_owner_move_needed_candidates`: vazio (header only)

---

## 3. Totais parciais A/B/C

| Classe | Descricao | Total dedup |
|---|---|---|
| **A** (delete) | wine_sources deletados | **~251.463** (via revert manifest) |
| **B** (move_needed) | ws_id precisa UPDATE wine_id | **3.669** |
| **C** (ambiguous) | requer revisao manual | **2** |

### Detalhamento Classe B por fonte

| Fonte | Rows bruto |
|---|---|
| `wo_move_needed_*` (del phase) | 1.854 |
| `wo_hybrid_b_*` (hybrid phase) | 2.368 |
| `wo_sql_b_*` (sql phase) | 354 |
| `wrong_owner_pilot_candidates` | 606 |
| **Total bruto** | **5.182** |
| **Dedup por ws_id** | **3.669** |

A diferenca bruto-dedup (1.513) vem do overlap entre fases (sql reprocesa owners ja cobertos pelo hybrid) e do piloto inicial incluido no move_needed.

---

## 4. Lacunas esperadas (run final ainda rodando)

O run final (`wrong_owner_sql_final.py`) esta cobrindo owners **119.501 a 305.046**.

### O que falta:

| Range de owners | Situacao |
|---|---|
| 242.501 — 305.046 | **Ainda em processamento** pelo run final |
| 50.501 — 52.500 | **Gap entre fase del e hybrid** — provavelmente coberto pelo run final SQL |

Quando o run terminar, esperamos:
- Novos `wo_hybrid_b_*` ate owners ~305.046
- Novos `wo_hybrid_rev_*` ate owners ~305.046
- Novos `wo_sql_b_*` ate owners ~305.046
- Possivelmente novos `wo_hybrid_c_*`

### Estimativa de incremento

- Faltam ~62.500 owners (242.501-305.046)
- Taxa media de B por tranche hybrid: ~25 linhas/2000 owners
- Incremento estimado B: ~780 linhas adicionais
- Incremento estimado deletes: ~56.000 linhas adicionais (rate ~900/tranche)

---

## 5. Riscos residuais

### 5.1 Classe B nao resolvida
Os 3.669 (e crescendo) `move_needed` representam wine_sources que apontam para o vinho errado **e** o vinho correto existe no Render. Precisam de `UPDATE wine_sources SET wine_id = expected WHERE ws_id = X`. Enquanto nao resolvidos, esses vinhos continuam com links incorretos.

### 5.2 Overlap sql/hybrid pode gerar conflito
O range 114.501-144.500 foi processado tanto pelo hybrid quanto pelo SQL. A dedup por ws_id resolve isso nos consolidados, mas **se ambos tentaram deletar o mesmo ws_id**, o segundo teria falhado silenciosamente (ON CONFLICT / row not found). Verificar apos run.

### 5.3 Gap 50.501-52.500
Esse range de 2.000 owners pode nao ter sido coberto por nenhuma fase. Verificar se o run final SQL o inclui.

### 5.4 Classe C minima
Apenas 2 casos ambiguos detectados. Isso e bom (poucas ambiguidades), mas pode significar que o detector de ambiguidade e conservador demais. Avaliar manualmente.

### 5.5 Not-wine vazados
Wine_sources deletados podem ter apontado para vinhos que nao sao vinhos (not_wine). Esses registros fake continuam na tabela `wines` mesmo apos o cleanup de sources. Investigacao separada necessaria.

### 5.6 Revert manifest como seguro
Os 251k reverts estao salvos localmente. Se qualquer delete foi incorreto, e possivel restaurar via INSERT usando os dados do revert manifest. **Manter esses arquivos intactos ate validacao completa.**

---

## 6. Artefatos gerados nesta consolidacao

| Arquivo | Linhas | Descricao |
|---|---|---|
| `scripts/wrong_owner_move_needed_consolidado_parcial.csv` | 3.669 | Classe B dedup |
| `scripts/wrong_owner_ambiguous_consolidado_parcial.csv` | 2 | Classe C dedup |
| `scripts/wrong_owner_revert_manifest_parcial.csv` | 251.463 | Todos os reverts dedup |
| `scripts/wrong_owner_exec_manifest_parcial.csv` | 163.942 | Deletes confirmados dedup |
| `scripts/wrong_owner_consolidation_stats_parcial.json` | - | Stats programaticas |
| `scripts/consolidar_wrong_owner_artifacts.py` | - | Script reutilizavel |

---

## 7. Proximo passo

Quando o run final terminar:
1. Rodar `python scripts/consolidar_wrong_owner_artifacts.py --suffix _final`
2. Comparar totais finais vs parciais
3. Atacar Classe B (UPDATE wine_id)
4. Investigar not_wine vazados

Ver: `prompts/PLANO_POS_RUN_CLASSE_B_E_NOT_WINE.md`
