# Plano Pos-Run — Classe B e Not-Wine

**Contexto**: O run final do wrong_owner (`wrong_owner_sql_final.py`) esta limpando wine_sources com owner errado. Quando terminar, restam duas frentes abertas: Classe B (move_needed) e not_wine vazados.

---

## Ordem recomendada

```
1. Trilha 1 — Consolidar resultado final         [~10 min, so CSV local]
2. Trilha 2 — Atacar Classe B                     [~30 min, banco]
3. Trilha 3 — Investigar not_wine vazados          [variavel, banco]
```

Trilha 1 e pre-requisito de 2 e 3. Trilhas 2 e 3 sao independentes entre si.

---

## Trilha 1 — Consolidar resultado final do wrong_owner

### Dependencia: run final terminar
### Requer banco: NAO (so CSVs locais)

### Passos

1. **Confirmar que o run terminou**
   - Verificar que o processo `wrong_owner_sql_final.py` nao esta mais rodando
   - Verificar o ultimo arquivo gerado (timestamp recente, sem truncamento)

2. **Rodar consolidacao final**
   ```bash
   python scripts/consolidar_wrong_owner_artifacts.py --suffix _final
   ```

3. **Comparar com parcial**
   - Diff de totais: B final vs B parcial (espera-se ~780 linhas a mais)
   - Diff de revert: espera-se ~56k linhas a mais
   - Verificar se surgiram novos C (ambiguous)

4. **Verificar gaps**
   - O script reporta gaps de ranges. Se houver gap 50501-52500, documentar.
   - Se houver outros gaps, avaliar se sao intencionais ou falha

5. **Artefatos finais esperados**
   - `wrong_owner_move_needed_consolidado_final.csv`
   - `wrong_owner_ambiguous_consolidado_final.csv`
   - `wrong_owner_revert_manifest_final.csv`
   - `wrong_owner_exec_manifest_final.csv`
   - `wrong_owner_consolidation_stats_final.json`

---

## Trilha 2 — Atacar Classe B (move_needed)

### Dependencia: Trilha 1 concluida
### Requer banco: SIM (UPDATE no Render)

### O que e Classe B

Sao `wine_sources` que apontam para `actual_wine_id` (errado) mas cujo `expected_wine_id` (correto) existe no Render. A correcao e um UPDATE simples:

```sql
UPDATE wine_sources
SET wine_id = <expected_wine_id>
WHERE id = <ws_id>
  AND wine_id = <actual_wine_id>;  -- guard clause
```

### Estrategia

1. **Piloto de 50 linhas**
   - Pegar as primeiras 50 do consolidado final
   - Executar UPDATE com guard clause e SAVEPOINT
   - Validar que o wine_source agora aponta pro vinho certo
   - Gerar revert CSV (ws_id, old_wine_id, new_wine_id)

2. **Batch incremental**
   - Processar em batches de 500
   - Cada batch: BEGIN, SAVEPOINT, UPDATE, validacao, RELEASE/ROLLBACK
   - Timeout por statement: 30s
   - Gerar `wo_b_executed_{range}.csv` e `wo_b_revert_{range}.csv`

3. **Validacao pos-batch**
   ```sql
   -- Quantos B ainda restam?
   SELECT COUNT(*) FROM wine_sources ws
   WHERE ws.id IN (SELECT ws_id::int FROM ... consolidado)
     AND ws.wine_id != expected_wine_id;
   ```

4. **Riscos especificos**
   - Se `expected_wine_id` foi deletado do Render entre a deteccao e o UPDATE, o UPDATE vai criar FK invalida. **Guard**: verificar que expected existe antes do UPDATE.
   - Se o ws_id ja foi deletado (por overlap com Classe A), o UPDATE nao faz nada. OK.
   - Race condition com o chat se o run ainda estiver ativo. **Nao iniciar Trilha 2 antes da Trilha 1.**

### Script sugerido

```
scripts/wrong_owner_fix_class_b.py
```

Entradas:
- `wrong_owner_move_needed_consolidado_final.csv`
- `DATABASE_URL` do .env

Saidas:
- `wo_b_executed_{batch}.csv`
- `wo_b_revert_{batch}.csv`
- Log de erros

### O que depende so de CSV (pre-banco)
- Analise de distribuicao de B por pais/store
- Verificacao de duplicatas (mesmo ws_id com expected diferente)
- Contagem de expected_wine_id unicos vs actual_wine_id unicos
- Priorizacao: quais B afetam mais vinhos

---

## Trilha 3 — Investigar not_wine vazados

### Dependencia: nenhuma (pode rodar em paralelo com Trilha 2)
### Requer banco: SIM (SELECT no Render)

### O que e not_wine

Sao registros na tabela `wines` que nao sao vinhos reais (kits, copos, acessorios, gift cards, etc.) que entraram via scraping e nao foram filtrados. O wrong_owner cleanup remove os sources deles, mas os registros em `wines` continuam.

### Passos de investigacao

1. **Identificar wines sem nenhum source apos cleanup**
   ```sql
   SELECT w.id, w.nome, w.hash_dedup
   FROM wines w
   WHERE w.vivino_id IS NULL
     AND NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)
   ORDER BY w.id
   LIMIT 1000;
   ```

2. **Classificar por padrao no nome**
   - Regex para detectar: `kit`, `pack`, `copo`, `glass`, `gift`, `decanter`, `abridor`, `saca-rolhas`, `acessorio`, `box`
   - Gerar `not_wine_candidates.csv`

3. **Decidir acao**
   - Opcao A: Marcar com flag (`is_not_wine = true`) — requer nova coluna
   - Opcao B: Deletar registros — destrutivo, requer backup
   - Opcao C: Ignorar por agora — nao afetam chat se nao tem sources
   - **Recomendacao**: Opcao C no curto prazo. Sem sources, esses wines nao aparecem em buscas do Baco. Limpar depois com calma.

4. **Quantificar impacto**
   - Quantos wines novos sem source existem pos-cleanup?
   - Quantos desses tem nome suspeito?
   - Quantos tem `winegod_score` calculado (contaminacao do score)?

### O que depende so de CSV (pre-banco)
- Analise dos nomes nos revert manifests (wines que perderam sources)
- Pattern matching local para not_wine nos candidatos de delete
- Estimar escala do problema antes de tocar no banco

---

## Resumo de dependencias

```
                    +-----------+
                    | Run final |
                    | terminar  |
                    +-----+-----+
                          |
                    +-----v-----+
                    | Trilha 1  |  (so CSV)
                    | Consolidar|
                    +-----+-----+
                          |
                +---------+---------+
                |                   |
          +-----v-----+     +------v------+
          | Trilha 2  |     | Trilha 3    |
          | Classe B  |     | not_wine    |
          | (banco)   |     | (banco)     |
          +-----------+     +-------------+
```

## Checklist pre-execucao

- [ ] Run final `wrong_owner_sql_final.py` terminou
- [ ] Consolidacao final rodada com `--suffix _final`
- [ ] Totais finais revisados e aprovados
- [ ] Gap 50501-52500 investigado
- [ ] Backup do revert manifest em local seguro
- [ ] Piloto Classe B executado e validado
- [ ] Batch Classe B executado
- [ ] Investigacao not_wine concluida
