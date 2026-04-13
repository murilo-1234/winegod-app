# Demanda 1 -- Claude Executor

## Papel

Voce e o executor desta etapa da auditoria pre-lancamento da cauda de vinhos fora da camada Vivino no WineGod.

Voce NAO esta administrando o projeto. Voce esta executando apenas a Etapa 1.

Nao reinterprete a estrategia. Nao proponha uma auditoria nova. Execute com rigor a etapa pedida.

---

## Objetivo da Etapa

Validar o snapshot live atual, reconciliar `vivino_db` versus Render, registrar contradicoes factuais com os documentos historicos e produzir os artefatos basicos que travam o contexto do projeto antes das etapas de features, candidatos e amostragem.

Ao final desta etapa, o projeto precisa ter:

1. um snapshot live oficial com data e queries;
2. uma reconciliacao oficial entre `vivino_db` e Render;
3. uma lista clara de fatos historicos que continuam validos;
4. uma lista clara de fatos historicos que NAO sao mais verdade live;
5. um parecer se o contexto esta estavel o suficiente para seguir para a etapa 2.

---

## Regras Fixas

- Snapshot live vence documentos historicos.
- `y2_results.vivino_id = wines.id do Render`, NAO o `vivino_id` real do Vivino.
- Nao escrever em producao.
- Nao aplicar alias.
- Nao importar canonicos.
- Nao fazer merge.
- Nao gerar amostras ainda.
- Nao construir ainda a tabela completa de features da cauda.

---

## Fatos de Referencia a Conferir

Use estes numeros apenas como referencia inicial. Eles precisam ser revalidados.

Render:

- `wines = 2.506.441`
- `wines com vivino_id = 1.727.058`
- `wines sem vivino_id = 779.383`
- `wine_aliases aprovados = 43`
- `wine_sources = 3.484.975`
- `stores = 19.889`
- `wines da cauda sem wine_sources = 8.071`

Local:

- `vivino_db.vivino_vinhos = 1.738.585`
- `vivino_ids presentes so no vivino_db e nao no Render = 11.527`
- `winegod_db.y2_results matched com vivino_id != null = 1.465.480`
- `winegod_db.y2_results matched com match_score >= 0.7 = 648.374`

Se alguma contagem divergir mais de `1%`, atualize o snapshot.
Se alguma contagem divergir mais de `5%`, pare e reporte drift relevante.

---

## Arquivos Obrigatorios a Ler Antes de Rodar

Leia estes arquivos:

1. `C:\winegod-app\reports\RESUMO_FASE0_DEDUP_2026-04-09.md`
2. `C:\winegod-app\reports\RELATORIO_SESSAO_DEDUP_2026-04-08.md`
3. `C:\winegod-app\reports\RUNBOOK_FASE2_REBUILD.md`
4. `C:\winegod-app\scripts\reconcile_vivino.py`
5. `C:\winegod-app\prompts\HANDOFF_AUDITORIA_LINHAGEM_LINKS_RENDER.md`
6. `C:\winegod-app\prompts\PROMPT_RECRIAR_WINE_SOURCES_FALTANTES.md`

Importante:

- trate `database/schema_atual.md` como historico, nao como fonte de verdade live;
- trate referencias a `~76.812 new sem source` como historicas, nao como verdade atual.

---

## Tarefas

### Tarefa A -- Revalidar snapshot live do Render

Voce deve rodar queries live e registrar:

- total de `wines`
- total de `wines` com `vivino_id`
- total de `wines` sem `vivino_id`
- total de `wine_aliases`
- total de `wine_aliases` aprovados
- total de `wine_sources`
- total de `stores`
- total de `wines` da cauda sem `wine_sources`
- total de `wines` da cauda com `wine_sources`

Tambem deve registrar:

- quantos `canonical_wine_id` distintos existem nos `43` aliases aprovados
- distribuicao por `source_type` e `review_status` em `wine_aliases`

### Tarefa B -- Revalidar snapshot local

Voce deve rodar queries locais e registrar:

- total de `vivino_vinhos` no `vivino_db`
- total de `y2_results` com `status = 'matched'` e `vivino_id IS NOT NULL`
- total de `y2_results` com `status = 'matched'` e `match_score >= 0.7`

### Tarefa C -- Reconciliar `vivino_db` vs Render

Voce deve reconciliar:

- `in_both`
- `only_vivino_db`
- `only_render`

Tambem deve produzir:

- amostra pequena e legivel de `only_vivino_db`
- confirmacao explicita se `only_render = 0` ou nao

### Tarefa D -- Registrar contradicoes factuais

Voce deve produzir uma lista objetiva de contradicoes entre:

- documentos historicos
- estado live atual

O foco principal e:

- numero atual de `wine_sources`
- numero atual de `stores`
- numero atual de `new sem source`
- qualquer documento que ainda esteja assumindo schema ou contagem antiga

### Tarefa E -- Criar o snapshot oficial da auditoria

Voce deve consolidar tudo em um report final que passe a ser a referencia oficial para a etapa 2.

---

## Queries Obrigatorias

Rode e salve o resultado destas consultas ou equivalentes funcionais:

### Render

```sql
SELECT COUNT(*) FROM wines;
SELECT COUNT(*) FROM wines WHERE vivino_id IS NOT NULL;
SELECT COUNT(*) FROM wines WHERE vivino_id IS NULL;
SELECT COUNT(*) FROM wine_aliases;
SELECT COUNT(*) FROM wine_aliases WHERE review_status = 'approved';
SELECT review_status, source_type, COUNT(*) FROM wine_aliases GROUP BY review_status, source_type ORDER BY review_status, source_type;
SELECT COUNT(*) FROM wine_sources;
SELECT COUNT(*) FROM stores;
SELECT COUNT(*) FROM wines w WHERE w.vivino_id IS NULL AND NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id);
SELECT COUNT(*) FROM wines w WHERE w.vivino_id IS NULL AND EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id);
SELECT COUNT(DISTINCT canonical_wine_id) FROM wine_aliases WHERE review_status = 'approved';
```

### Local `winegod_db`

```sql
SELECT COUNT(*) FROM y2_results WHERE status = 'matched' AND vivino_id IS NOT NULL;
SELECT COUNT(*) FROM y2_results WHERE status = 'matched' AND match_score >= 0.7 AND vivino_id IS NOT NULL;
```

### Local `vivino_db`

```sql
SELECT COUNT(*) FROM vivino_vinhos;
```

### Reconciliacao

Voce pode fazer via script Python ou SQL, mas precisa entregar:

- `in_both`
- `only_vivino_db`
- `only_render`

Se usar Python, deixe o script salvo em `scripts/`.

---

## Scripts

Se precisar criar script novo, crie:

- `C:\winegod-app\scripts\audit_tail_snapshot.py`

Objetivo do script:

- conectar ao Render
- conectar ao `winegod_db`
- conectar ao `vivino_db`
- rodar todas as contagens e reconciliacoes desta etapa
- salvar a saida em `reports/`
- ser idempotente

Se preferir ajustar `reconcile_vivino.py`, tudo bem, mas nao destrua o comportamento atual. Se fizer ajuste, explique o motivo.

---

## Artefatos Obrigatorios

Gere estes arquivos:

1. `C:\winegod-app\reports\tail_audit_snapshot_2026-04-10.md`
2. `C:\winegod-app\reports\tail_audit_reconciliation_2026-04-10.md`
3. `C:\winegod-app\reports\tail_audit_contradictions_2026-04-10.md`

Se criar script:

4. `C:\winegod-app\scripts\audit_tail_snapshot.py`

---

## Conteudo Esperado de Cada Artefato

### `tail_audit_snapshot_2026-04-10.md`

Deve conter:

- data exata
- queries ou referencia ao script usado
- contagens oficiais do Render
- contagens oficiais dos bancos locais
- comparacao com os numeros de referencia
- indicacao explicita de drift percentual
- veredito:
  - `snapshot estavel`
  ou
  - `snapshot com drift relevante`

### `tail_audit_reconciliation_2026-04-10.md`

Deve conter:

- total no Render com `vivino_id`
- total no `vivino_db`
- `in_both`
- `only_vivino_db`
- `only_render`
- amostra legivel de `only_vivino_db`
- conclusao operacional:
  - se existe de fato universo real de canonicos importaveis
  - se existe ou nao sujeira do tipo `vivino_id` no Render sem correspondencia no `vivino_db`

### `tail_audit_contradictions_2026-04-10.md`

Deve conter tabela com colunas:

- `tema`
- `documento_historico`
- `valor_historico`
- `valor_live`
- `status`
- `comentario`

Exemplos de temas:

- `wine_sources_total`
- `stores_total`
- `new_without_sources`
- `schema_live_assumptions`

---

## Criterios de Aceite

Esta etapa so esta pronta se:

1. Todas as contagens principais forem confirmadas com query ou script verificavel.
2. A reconciliacao `vivino_db vs Render` estiver fechada com numeros e amostra.
3. As contradicoes factuais estiverem explicitamente registradas.
4. Houver um arquivo unico de snapshot que o Codex possa tratar como base oficial da etapa 2.
5. Nenhuma escrita em producao tiver sido feita.

---

## O Que Voce Nao Pode Fazer

- Nao construir ainda a tabela completa de features dos `779.383`.
- Nao gerar candidatos.
- Nao estratificar.
- Nao montar a amostra de `120`, `600` ou `120 impacto`.
- Nao aplicar aliases.
- Nao importar canonicos.
- Nao assumir que numero historico continua valendo sem revalidar.
- Nao usar `database/schema_atual.md` como prova do estado live.

---

## Formato da Sua Resposta no Chat

Responda ao final com:

1. O que foi feito
2. Quais queries e scripts foram usados
3. Quais numeros foram confirmados
4. Quais contradicoes historico versus live foram encontradas
5. Quais arquivos foram gerados
6. Se a etapa esta pronta para aprovacao
7. Quais riscos ou bloqueios restaram para a etapa 2

Se voce encontrar uma contradicao factual importante entre docs e banco live, registre a contradicao com data exata e siga com o dado live.
