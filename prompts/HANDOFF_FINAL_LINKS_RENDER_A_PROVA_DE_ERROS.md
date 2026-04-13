# Handoff Final - Links de Loja no Render

## Objetivo

Este e o documento final e preferencial para qualquer IA, chat ou engenheiro que precise:

1. auditar a linhagem correta dos links de loja
2. explicar a causa raiz do problema atual
3. corrigir os `wine_sources` faltantes com o menor risco possivel
4. evitar repetir os erros da Fase 2 historica

Este documento consolida:

- `prompts/HANDOFF_AUDITORIA_LINHAGEM_LINKS_RENDER.md`
- `prompts/HANDOFF_CORRECAO_RAPIDA_LINKS_FALTANTES_RENDER.md`
- `prompts/JULGAMENTO_HANDOFF_CODEX.md`

Use este documento como ponto de partida. So recorra aos outros quando precisar de detalhe adicional.

---

## Estado Atual de Referencia

Data de referencia: `2026-04-06`

Estado observado no Render:

```text
wines total:        2,506,441
wines vivino:       1,727,058
wines novos:          779,383
stores:                19,881
wine_sources:       3,659,501
```

Segundo a auditoria empirica mais recente registrada em `prompts/JULGAMENTO_HANDOFF_CODEX.md`:

- vinhos novos sem source: `76,812`
- classificacao reportada:
  - `A = 74,520`
  - `B = 9`
  - `C = 2,084`
  - `D = 199`
- links errados observados:
  - `84,654` fontes excedentes em `17,314` wines receptores

Interpretacao operacional:

- o problema principal atual nao e falta de `store`
- o problema principal atual nao e falta estrutural de fonte
- o problema dominante apontado pela auditoria empirica e o ramo `check_exists_in_render`
- rollback de batch continua relevante, mas como causa secundaria e contextual

---

## Verdades Que Devem Guiar Todo Trabalho

1. Todo vinho de scraping nasceu de uma URL de loja
2. A fonte de verdade dos links e `vinhos_XX_fontes`
3. `wines_clean.id` nunca deve ser tratado como `vinhos_XX.id`
4. A ponte correta e sempre `wines_clean.pais_tabela + wines_clean.id_original`
5. Para `matched`, o owner final no Render vem de `y2_results.vivino_id`
6. Para `new`, o owner correto para correcao tatica deve ser resolvido por `hash_dedup`
7. O ramo `check_exists_in_render` deve ser reproduzido apenas para diagnostico e prova de causa raiz
8. O Render nao e fonte de verdade dos links; ele e o estado auditado

---

## Causa Raiz Operacional Mais Provavel

Segundo `prompts/JULGAMENTO_HANDOFF_CODEX.md`, duas causas atuaram em conjunto.

### Causa 1 - dominante

`check_exists_in_render` com produtores genericos redireciona fontes para o vinho errado.

Sinais empiricos reportados:

- `84,654` fontes excedentes em `17,314` wines receptores
- proporcao quase `1:1` com os `76,812` wines novos sem source
- produtores genericos recorrentes: `espumante`, `langhe`, `barbera`, `il`, `barolo`
- crescimento temporal da taxa de erro ao longo das rodadas principais

### Causa 2 - secundaria, mas real

Rollback do batch inteiro na Fase 2.

Esse mecanismo:

- perde sources bons junto com linhas ruins
- subconta perdas no log
- explica melhor o estado atual quando combinado com:
  - vinho ja inserido em rodada anterior
  - `DELETE` de sources entre rodadas
  - falha posterior ao recriar os links

---

## Decisao de Arquitetura

### Para auditoria

Use reconstrucao canonica completa.

### Para correcao tatica dos links faltantes

NAO use:

- `check_exists_in_render`
- replay da Fase 2
- `hash_to_fontes`
- workers

Use apenas:

```text
Render wines sem source
  -> hash_dedup
  -> LOCAL wines_clean
  -> (pais_tabela, id_original)
  -> LOCAL vinhos_XX_fontes
  -> dominio da URL
  -> Render stores
  -> INSERT wine_sources
```

---

## Modo 1 - Auditoria Completa

Escolha este modo se o objetivo for qualquer um destes:

- provar causa raiz
- medir `A/B/C/D`
- detectar `wrong_wine_association`
- produzir artefatos de reconciliacao

### Passos minimos

1. Validar conexoes e totais
2. Extrair universo `new` e `matched` do LOCAL
3. Construir a linhagem canonica por `hash_dedup` ou `vivino_id`
4. Streamar apenas fontes locais relevantes
5. Resolver `store_id` por dominio
6. Comparar esperado vs observado
7. Gerar:
   - `missing_wine_sources.csv`
   - `wrong_wine_sources.csv`
   - `audit_summary.md`

### Regra especial

O ramo `check_exists_in_render` deve ser:

- reproduzido para diagnostico
- comparado com os links errados
- explicitamente proibido como mecanismo de correcao tatica

---

## Modo 2 - Correcao Rapida dos Links Faltantes

Escolha este modo apenas se:

- o objetivo imediato e restaurar os links faltantes dos vinhos novos sem source
- e voce aceita que a limpeza de links errados pode vir em etapa separada

### Query performatica de entrada

```sql
SELECT
    w.id,
    w.hash_dedup,
    w.nome
FROM wines w
WHERE w.vivino_id IS NULL
  AND NOT EXISTS (
      SELECT 1
      FROM wine_sources ws
      WHERE ws.wine_id = w.id
  )
ORDER BY w.id;
```

### Regras obrigatorias

1. Resolver owner local apenas por `hash_dedup`
2. Buscar fontes reais em `vinhos_XX_fontes`
3. Resolver loja apenas por `stores.dominio`
4. Inserir com `ON CONFLICT DO NOTHING`
5. Processar em batch pequeno
6. Usar `SAVEPOINT`
7. Sem workers

### Implementacao recomendada

Script novo:

```text
scripts/recriar_wine_sources_faltantes.py
```

Conexao Render recomendada:

```python
psycopg2.connect(
    RENDER_DB,
    options='-c statement_timeout=120000',
    keepalives=1,
    keepalives_idle=30,
    keepalives_interval=10,
    keepalives_count=5,
)
```

### Estrategia de tempo

Nao assumir estimativa fixa.

Procedimento:

1. rodar piloto com `500` wines
2. medir tempo real
3. extrapolar
4. ajustar batch se necessario

---

## Queries Obrigatorias de Validacao

### 1. Quantos wines novos continuam sem source

```sql
SELECT COUNT(*)
FROM wines w
WHERE w.vivino_id IS NULL
  AND NOT EXISTS (
      SELECT 1
      FROM wine_sources ws
      WHERE ws.wine_id = w.id
  );
```

### 2. Quantos `wine_sources` existem para wines novos

```sql
SELECT COUNT(*)
FROM wine_sources ws
JOIN wines w ON w.id = ws.wine_id
WHERE w.vivino_id IS NULL;
```

### 3. Quantos URLs estao ligados a mais de um wine

```sql
SELECT url, COUNT(DISTINCT wine_id) AS wines
FROM wine_sources
GROUP BY url
HAVING COUNT(DISTINCT wine_id) > 1
ORDER BY wines DESC, url;
```

---

## O Que Nao Fazer

1. Nao usar `wines_clean.fontes`
2. Nao usar `wines.vivino_id` para resolver `matched`
3. Nao usar `check_exists_in_render` para recriar links faltantes
4. Nao depender de `LEFT JOIN + GROUP BY + HAVING COUNT = 0` onde `NOT EXISTS` resolver melhor
5. Nao confiar em `rowcount` sozinho com `ON CONFLICT`
6. Nao misturar, no mesmo script tatico, correcao de links faltantes com reconciliacao de links errados
7. Nao ignorar que produtores genericos podem redirecionar fontes para o wine errado

---

## Entregavel Final Esperado

Ao final, qualquer IA que use este documento deve conseguir responder:

1. quais links estao faltando
2. quais links estao errados
3. qual mecanismo historico gerou o problema
4. qual e a forma segura de recriar os links faltantes
5. quando a correcao tatica basta e quando e obrigatorio voltar para a auditoria completa

Se a resposta final nao separar claramente:

- auditoria
- correcao tatica
- reconciliacao de links errados

entao o trabalho ainda nao esta a prova de erros.

