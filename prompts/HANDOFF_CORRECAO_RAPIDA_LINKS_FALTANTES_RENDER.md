# Handoff - Correcao Rapida dos Links Faltantes no Render

## Missao

Voce vai executar uma correcao tatica e focada para recriar os `wine_sources` faltantes dos vinhos novos de scraping que ja existem no Render mas estao sem qualquer link.

Este documento NAO substitui a auditoria completa em `prompts/HANDOFF_AUDITORIA_LINHAGEM_LINKS_RENDER.md`.

Use este handoff apenas quando o objetivo for:

1. recuperar rapidamente os links faltantes dos vinhos novos sem source
2. evitar reusar a logica defeituosa da Fase 2
3. operar com o caminho mais direto e com menos superficie de erro

Nao use este handoff como unica correcao global se ainda houver muitos `wine_sources` ligados ao vinho errado. Nesse caso, a auditoria completa continua obrigatoria.

---

## Escopo

Este handoff cobre apenas:

- `wines` do Render onde `vivino_id IS NULL`
- e que nao possuem nenhum registro em `wine_sources`

Ele nao cobre, por si so:

- remocao de `wine_sources` errados
- reavaliacao de `check_exists_in_render`
- reconciliacao completa de `wrong_wine_association`

---

## Fatos de Referencia

Segundo `prompts/JULGAMENTO_HANDOFF_CODEX.md`:

- contagem mais recente de vinhos novos sem source: `76,812`
- classificacao reportada:
  - `A = 74,520`
  - `B = 9`
  - `C = 2,084`
  - `D = 199`

Interprete esses numeros como referencia operacional atual, nao como verdade eterna.

---

## Regra Absoluta

- Nao alterar `scripts/import_render_z.py`
- Nao usar `check_exists_in_render` nesta correcao
- Nao usar `wines_clean.fontes`
- Nao inferir link por nome de vinho
- Usar apenas:
  - `wines.hash_dedup`
  - `wines_clean.hash_dedup`
  - `wines_clean.pais_tabela`
  - `wines_clean.id_original`
  - `vinhos_XX_fontes`
  - `stores.dominio`
- Fazer `INSERT INTO wine_sources ... ON CONFLICT DO NOTHING`
- Processar em batches pequenos e com transacao segura

---

## Ideia Central

Para esta correcao, ignore completamente a logica historica da Fase 2.

O caminho certo e:

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

Sem:

- workers
- `check_exists_in_render`
- `hash_to_fontes`
- replay da Fase 2

---

## Pre-condicoes

Antes de rodar a correcao:

1. Confirmar quantos `wines` novos estao sem source no Render
2. Confirmar quantos deles resolvem por `hash_dedup -> wines_clean`
3. Confirmar quantos deles tem ao menos uma fonte local
4. Confirmar quantos dominios dessas fontes existem em `stores`

Se os numeros divergirem brutalmente dos valores de referencia, pare e revalide a base antes de inserir.

---

## Queries Base

### 1. Vinhos novos sem qualquer source no Render

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

### 2. Resolver no LOCAL por hash

```sql
SELECT
    wc.id AS clean_id,
    wc.hash_dedup,
    wc.pais_tabela,
    wc.id_original
FROM wines_clean wc
WHERE wc.hash_dedup = %s;
```

### 3. Buscar fontes reais

Exemplo para `br`:

```sql
SELECT url_original, preco, moeda
FROM vinhos_br_fontes
WHERE vinho_id = %s
  AND url_original IS NOT NULL;
```

### 4. Resolver loja no Render

```sql
SELECT id
FROM stores
WHERE dominio = %s;
```

---

## Algoritmo Recomendado

### Passo 1

Buscar no Render todos os `wines` novos sem source.

Cada linha minima:

```text
render_wine_id
hash_dedup
nome
```

### Passo 2

Para cada `hash_dedup`, buscar `wines_clean`.

Regras:

- se encontrar exatamente 1 linha: seguir
- se encontrar varias linhas: unir as fontes de todas
- se nao encontrar: registrar em `unresolved_hash.csv`

Nota:

- segundo a auditoria empirica mais recente, no snapshot atual o padrao dominante parece ser `1 hash_dedup -> 1 clean_id`
- ainda assim, o script deve continuar defensivo e unir fontes se aparecer mais de uma linha

### Passo 3

Para cada linha local resolvida:

- ler `pais_tabela`
- ler `id_original`
- consultar a tabela `vinhos_{pais}_fontes`

### Passo 4

Para cada `url_original`:

- normalizar dominio exatamente como no script:

```python
netloc = urlparse(url).netloc
dominio = netloc.replace('www.', '') if netloc else None
```

- buscar `store_id` em `stores`

### Passo 5

Se existir `store_id`, montar a tripla esperada:

```text
wine_id
store_id
url
```

Guardar tambem:

```text
preco
moeda
```

### Passo 6

Inserir em `wine_sources` com:

```sql
INSERT INTO wine_sources (
    wine_id,
    store_id,
    url,
    preco,
    moeda,
    disponivel,
    descoberto_em,
    atualizado_em
)
VALUES (...)
ON CONFLICT (wine_id, store_id, url) DO NOTHING;
```

Observacao:

- se o banco exigir a versao com indice parcial `WHERE url IS NOT NULL`, use a mesma forma que ja esta no projeto

---

## Implementacao Recomendada

Criar um script novo e separado, por exemplo:

```text
scripts/recriar_wine_sources_faltantes.py
```

Principios:

- usar `psycopg2`
- sem workers
- batch de `200` a `500`
- `SAVEPOINT` por batch ou por vinho
- commit frequente
- logar progresso

Configuracao recomendada para a conexao Render:

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

Estimativa:

- nao assumir tempo fixo sem medir
- rodar primeiro um piloto de `500` wines
- medir tempo real do piloto
- extrapolar antes da execucao completa

Campos minimos de log:

```text
processados
hash_resolvidos
sem_hash_local
sem_fonte_local
sem_store
links_tentados
links_inseridos
duplicatas_ignoradas
erros
```

---

## O Que Registrar em Arquivos

No minimo:

1. `artifacts/missing_wines_input.csv`
2. `artifacts/resolved_hashes.csv`
3. `artifacts/unresolved_hash.csv`
4. `artifacts/missing_store_domains.csv`
5. `artifacts/wine_sources_to_insert.csv`
6. `artifacts/quick_fix_summary.md`

---

## O Que Nao Fazer

1. Nao usar `check_exists_in_render`
2. Nao usar produtor/nome como heuristica de dono do link
3. Nao reconstruir `wine_id` por similaridade textual
4. Nao tentar corrigir links errados no mesmo script sem auditoria previa
5. Nao carregar `5.6M` fontes sem filtro se puder evitar
6. Nao depender de `rowcount` sozinho para medir sucesso

---

## Validacao

Ao final, provar pelo menos:

1. quantos `wines` novos sem source existiam antes
2. quantos continuam sem source depois
3. quantos `wine_sources` foram inseridos
4. quantos casos ficaram sem resolver por:
   - hash ausente
   - fonte ausente
   - store ausente

Queries minimas:

### Antes e depois

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

### Quantos `wine_sources` por `wines` novos

```sql
SELECT COUNT(*)
FROM wine_sources ws
JOIN wines w ON w.id = ws.wine_id
WHERE w.vivino_id IS NULL;
```

---

## Limite Deste Handoff

Se ao final ainda existirem muitos `wine_sources` ligados ao vinho errado, este handoff nao resolve isso.

Nesse caso, o proximo passo nao e insistir neste script. O proximo passo e voltar para:

- `prompts/HANDOFF_AUDITORIA_LINHAGEM_LINKS_RENDER.md`
- `prompts/JULGAMENTO_HANDOFF_CODEX.md`

e executar a reconciliacao completa de `wrong_wine_association`.
