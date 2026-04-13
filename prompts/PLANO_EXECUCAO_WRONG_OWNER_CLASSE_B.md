# Plano de Execucao — Wrong Owner Classe B (move_needed)

**Data**: 2026-04-09
**Status**: PROPOSTO (nao executado)
**Escopo**: Apenas Classe B — wine_sources apontando para actual_wine_id errado, cujo expected_wine_id (correto) NAO possui o link.

---

## 1. Numeros consolidados

| Metrica | Valor |
|---|---|
| Bruto (todas as fontes) | 5,773 |
| Deduplicado (por ws_id) | 4,201 |
| move_needed_safe | 4,158 |
| ambiguous (conflito de expected) | 43 |
| incomplete (pilot sem ws_id) | 606 |
| stale_or_already_fixed | 0 (requer verificacao no banco) |

### Fontes

| Fonte | Arquivos | Linhas brutas | Range owners | Tem ws_id |
|---|---|---|---|---|
| wo_move_needed (v1/v2) | 100 | 1,854 | 501-50500 | SIM |
| wo_hybrid_b | 127 | 2,882 | 52501-305046 | SIM |
| wo_sql_b (inclui gap) | 7 | 431 | 50501-52500 + 114501-144500 | SIM |
| candidates | 1 | 0 | - | SIM |
| pilot_candidates | 1 | 606 | - | **NAO** |

### Chave de deduplicacao

**ws_id** (PK de wine_sources).

Justificativa: cada ws_id e uma row unica no banco. A operacao de move e por row. Chave composta `(actual_wine_id, expected_wine_id, store_id, url)` seria errada porque perderia rows distintas que compartilham a mesma tupla logica mas sao fisicamente rows separadas.

### Cobertura de owner ranges

- v1/v2: owners 501-50500 (100 blocos, sem gaps)
- hybrid: owners 52501-305046 (127 blocos, sem gaps)
- sql: owners 50501-52500 (gap) + 114501-144500 (6 blocos)
- Gap 50501-52500: **COBERTO** pelo wo_sql_b_50501_52500.csv (77 linhas)
- Overlap hybrid-sql: owners 114501-144500 (30,000 owners, dedup por ws_id resolve)

### Divergencias de schema encontradas

| Fonte | Colunas different | Impacto |
|---|---|---|
| wo_move_needed | col order diferente, tem `pais` | Resolvido na normalizacao |
| wo_hybrid_b | `actual`/`expected`/`cid` em vez de nomes longos | Resolvido na normalizacao |
| pilot_candidates | **SEM ws_id** | 606 rows inutilizaveis sem lookup no banco |
| wo_move_needed | **store_id vazio** em 1,852/1,854 rows | Nao e bloqueio: store_id existe no banco, obtido via SELECT |

---

## 2. Classificacao dos 43 ambiguos

Todos os 43 ws_ids ambiguos compartilham o mesmo padrao: **URL e apenas o dominio da loja** (ex: `https://www.chicovalley.com.br`), sem path de produto. Isso fez com que multiplos owner ranges classificassem o mesmo ws_id com expected_wine_id diferentes.

Acao recomendada: **NAO MEXER**. Esses 43 sao genuinamente ambiguos e exigiriam prova manual do owner correto.

---

## 3. Os 606 pilot_candidates (incomplete)

Esses 606 registros vieram do piloto inicial e NAO possuem ws_id no CSV. Nenhum deles e coberto por outra fonte que tenha ws_id.

Para incorpora-los ao pipeline, seria necessario:
1. Fazer SELECT no Render por `(url, store_id, wine_id = actual_wine_id)` para descobrir o ws_id
2. Reclassificar com o ws_id preenchido

Acao recomendada: **deixar de lado nesta rodada**. Focar nos 4,158 safe. Os 606 podem ser resolvidos numa rodada futura com acesso ao banco.

---

## 4. Estrategia de execucao proposta

### Operacao: UPDATE (NAO DELETE+INSERT)

```sql
UPDATE wine_sources
SET wine_id = <expected_wine_id>
WHERE id = <ws_id>
  AND wine_id = <actual_wine_id>;  -- guard clause
```

**Justificativa**: UPDATE e preferivel a DELETE+INSERT porque:
- Preserva ws_id (PK), store_id, url, preco, moeda, disponivel, timestamps
- Nao precisa reconstruir a row
- Atomico e simples
- Guard clause `wine_id = actual_wine_id` garante que o UPDATE so acontece se o estado nao mudou

### Ordem: nao ha dilema INSERT-primeiro-ou-DELETE-primeiro

Com UPDATE, a operacao e atomica. Nao ha risco de perda de dados ou estado intermediario inconsistente.

Se o usuario preferir DELETE+INSERT:
- **INSERT primeiro** (no expected_wine_id), com SELECT para capturar todos os campos da row original
- Depois DELETE (do actual_wine_id)
- Guard: verificar que o INSERT foi bem-sucedido antes do DELETE
- SAVEPOINT entre INSERT e DELETE para rollback se algo falhar

### Revert lossless

Para cada ws_id processado, gerar CSV de revert com:
```
ws_id, old_wine_id (actual), new_wine_id (expected)
```

Revert e um UPDATE inverso:
```sql
UPDATE wine_sources
SET wine_id = <old_wine_id>
WHERE id = <ws_id>
  AND wine_id = <new_wine_id>;
```

### Checks obrigatorios antes de cada operacao

1. **expected_wine_id existe**: `SELECT 1 FROM wines WHERE id = <expected_wine_id>`
   - Se nao existe, SKIP (wine pode ter sido deletado)
2. **ws_id ainda aponta para actual**: `SELECT wine_id FROM wine_sources WHERE id = <ws_id>`
   - Se wine_id != actual, SKIP (ja foi corrigido ou mudou)
3. **Nao criar duplicata**: `SELECT 1 FROM wine_sources WHERE wine_id = <expected_wine_id> AND url = <url> AND store_id = <store_id>`
   - Se ja existe, SKIP (outro processo ja inseriu o link correto — pode ter virado Classe A)
4. **store_id valido**: obtido do SELECT do check 2

### Batching

- SAVEPOINT antes de cada batch
- Timeout por statement: 30s
- Log de cada operacao: ws_id, resultado (ok/skipped/error), motivo

---

## 5. Recomendacao de piloto

### Tamanho: **100 casos**

Justificativa:
- Pequeno o suficiente para revisao manual pos-execucao
- Grande o suficiente para detectar padroes (erros sistematicos, edge cases)
- Similar ao piloto da Classe A (que usou 100 casos com sucesso)

### Selecao dos 100

Criterios:
1. Pegar dos safe (nao ambiguous)
2. Priorizar rows COM store_id no CSV (hybrid/sql) para facilitar validacao pos-execucao
3. Misturar fontes: ~40 de hybrid, ~40 de move_needed, ~20 de sql
4. Evitar mesmos actual_wine_id ou expected_wine_id repetidos no piloto (diversidade)

### Validacao pos-piloto

```sql
-- Verificar que os 100 ws_ids agora apontam para expected
SELECT ws.id, ws.wine_id, ws.url, ws.store_id
FROM wine_sources ws
WHERE ws.id IN (<lista de 100 ws_ids>);

-- Verificar que nenhum wine ficou com 0 sources
SELECT w.id, w.nome
FROM wines w
WHERE w.id IN (<lista de 100 actual_wine_ids>)
  AND NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id);
```

---

## 6. Risco operacional residual

| Risco | Probabilidade | Impacto | Mitigacao |
|---|---|---|---|
| expected_wine_id deletado entre deteccao e execucao | Baixa | Medio (FK invalida) | Check 1: SELECT antes do UPDATE |
| ws_id ja corrigido por outro processo | Baixa | Nulo (guard clause ignora) | Check 2: guard `wine_id = actual` |
| Duplicata de (url, store_id) no expected | Media | Baixo (link duplicado) | Check 3: ON CONFLICT ou SELECT antes |
| store_id ausente no CSV (1,628 rows v1/v2) | Certa | Nulo (UPDATE preserva store_id) | UPDATE nao precisa de store_id |
| Pilot candidates sem ws_id | Certa | Medio (606 rows nao processaveis) | Excluidas desta rodada |
| Ambiguos com URL domain-only | Certa | Nulo (excluidos) | 43 rows excluidas |

### Risco global

**BAIXO**. Os 4,158 safe sao operacoes simples de UPDATE com guard clause. O revert e determinístico. Nenhum dado e perdido.

---

## 7. Artefatos desta rodada

| Arquivo | Conteudo | Linhas |
|---|---|---|
| `scripts/wrong_owner_move_needed_consolidado_final.csv` | Consolidado dedup completo | 4,201 |
| `scripts/wrong_owner_move_needed_safe.csv` | Casos seguros para execucao | 4,158 |
| `scripts/wrong_owner_move_needed_ambiguous.csv` | Ambiguos + incompletos | 649 |
| `scripts/wrong_owner_move_needed_stale.csv` | Stale (vazio, requer banco) | 0 |
| `scripts/wrong_owner_classe_b_stats.json` | Stats completas em JSON | 1 |
| `scripts/consolidar_classe_b_completo.py` | Script de consolidacao | 1 |
| `prompts/PLANO_EXECUCAO_WRONG_OWNER_CLASSE_B.md` | Este documento | 1 |

---

## 8. Proximos passos (nao executar agora)

1. **Piloto de 100**: executar UPDATE com guard clause nos primeiros 100 safe
2. **Validacao pos-piloto**: verificar resultado e confirmar revert funcional
3. **Batch completo**: processar os 4,158 safe em batches de 500
4. **Resolver incompletos**: lookup dos 606 pilot candidates no banco
5. **Resolver ambiguos**: investigacao manual dos 43 domain-only URLs
