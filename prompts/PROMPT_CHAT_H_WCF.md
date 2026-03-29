# CHAT H — Calcular Nota WCF para 1.72M Vinhos

## CONTEXTO
WineGod.ai usa uma formula proprietaria chamada WCF (Weighted Collaborative Filtering) pra calcular a nota real de cada vinho. A nota WCF e diferente da media simples porque da mais peso pra avaliadores experientes.

O banco no Render tem 1.72M vinhos com `vivino_rating` (media simples) e `vivino_reviews` (quantidade). O banco LOCAL (vivino_db) tem 33M reviews individuais com dados dos reviewers.

## SUA TAREFA
Calcular `nota_wcf` pra todos os vinhos e gravar no banco do Render.

## CONEXOES

```
# Banco LOCAL — reviews individuais (33M reviews, 4.8M reviewers)
VIVINO_DATABASE_URL=postgresql://postgres:XXXXXXXXX@localhost:5432/vivino_db

# Banco RENDER — wines (1.72M vinhos, coluna nota_wcf a preencher)
DATABASE_URL=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod
```

psql local: `"C:\Program Files\PostgreSQL\16\bin\psql.exe"`

## ONDE CRIAR
`C:\winegod-app\scripts\calc_wcf.py`

## FORMULA WCF

Pesos por experiencia do reviewer:
- 1-10 reviews totais → peso 1.0x (Iniciante)
- 11-50 reviews → peso 1.5x (Regular)
- 51-200 reviews → peso 2.0x (Entusiasta)
- 201-500 reviews → peso 3.0x (Expert)
- 500+ reviews → peso 4.0x (Master)

Formula pra cada vinho:
```
WCF = SUM(rating_i * peso_i) / SUM(peso_i)
```

Onde rating_i e a nota que o reviewer i deu, e peso_i e o peso baseado na experiencia total do reviewer.

## PASSO 1 — ENTENDER O SCHEMA LOCAL

Primeiro, verificar as tabelas no vivino_db:
```sql
-- Estrutura da tabela de reviews
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'vivino_reviews' ORDER BY ordinal_position;

-- Estrutura da tabela de reviewers
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'vivino_reviewers' ORDER BY ordinal_position;

-- Estrutura da tabela de vinhos
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'vivino_vinhos' ORDER BY ordinal_position;

-- Amostra
SELECT * FROM vivino_reviews LIMIT 3;
SELECT * FROM vivino_reviewers LIMIT 3;
```

Identificar:
- Campo de rating na review (provavelmente `rating` ou `nota`)
- Campo que liga review ao vinho (provavelmente `wine_id` ou `vivino_id`)
- Campo que liga review ao reviewer
- Campo de total de reviews do reviewer (provavelmente `ratings_count` ou similar)

## PASSO 2 — CALCULAR WCF NO BANCO LOCAL

A query principal (rodar no vivino_db local):
```sql
-- Calcular WCF por vinho
-- ADAPTAR nomes dos campos conforme schema encontrado no Passo 1
SELECT
    r.wine_id,
    ROUND(
        SUM(r.rating * CASE
            WHEN rv.ratings_count <= 10 THEN 1.0
            WHEN rv.ratings_count <= 50 THEN 1.5
            WHEN rv.ratings_count <= 200 THEN 2.0
            WHEN rv.ratings_count <= 500 THEN 3.0
            ELSE 4.0
        END) /
        NULLIF(SUM(CASE
            WHEN rv.ratings_count <= 10 THEN 1.0
            WHEN rv.ratings_count <= 50 THEN 1.5
            WHEN rv.ratings_count <= 200 THEN 2.0
            WHEN rv.ratings_count <= 500 THEN 3.0
            ELSE 4.0
        END), 0)
    , 2) as nota_wcf,
    COUNT(*) as total_reviews_wcf
FROM vivino_reviews r
JOIN vivino_reviewers rv ON r.reviewer_id = rv.id
WHERE r.rating > 0
GROUP BY r.wine_id
```

CUIDADO: 33M reviews. Essa query pode demorar 5-30 minutos. Pode ser necessario:
- Criar indice temporario: `CREATE INDEX IF NOT EXISTS idx_reviews_wine ON vivino_reviews(wine_id);`
- Rodar em lotes por wine_id range

## PASSO 3 — EXPORTAR RESULTADOS

Salvar resultados em CSV ou tabela temporaria:
```sql
-- Criar tabela temporaria com resultado
CREATE TABLE IF NOT EXISTS wcf_calculado AS
SELECT wine_id, nota_wcf, total_reviews_wcf
FROM (query do Passo 2);
```

Ou exportar pra CSV:
```sql
COPY (query do Passo 2) TO 'C:/winegod-app/scripts/wcf_results.csv' WITH CSV HEADER;
```

## PASSO 4 — ATUALIZAR BANCO NO RENDER

Script Python que:
1. Le os resultados do WCF (CSV ou tabela local)
2. Conecta no Render
3. Faz UPDATE em lotes de 1000:
```sql
UPDATE wines SET nota_wcf = %s, confianca_nota = %s
WHERE vivino_id = %s
```

Para confianca_nota:
- 100+ reviews → 1.0
- 50-99 → 0.8
- 25-49 → 0.6
- 10-24 → 0.4
- 1-9 → 0.2

Para winegod_score_type:
- 100+ reviews → 'verified'
- 1-99 reviews → 'estimated'
- 0 reviews → 'none'

## PASSO 5 — VINHOS SEM REVIEWS (Nota Estimada basica)

Para vinhos com 0 reviews no Vivino, calcular nota estimada basica:
1. Calcular media da uva+regiao:
```sql
SELECT regiao, AVG(nota_wcf) as media_regiao
FROM wines
WHERE nota_wcf IS NOT NULL AND regiao IS NOT NULL
GROUP BY regiao
```
2. Para vinhos sem review: nota_wcf = media da regiao, confianca_nota = 0.1, score_type = 'estimated'

## O QUE NAO FAZER
- NAO alterar o schema (campos ja existem)
- NAO modificar codigo do backend Flask
- NAO fazer git commit/push
- NAO deletar dados existentes
- NAO rodar queries sem LIMIT primeiro pra testar

## COMO VERIFICAR

```sql
-- No Render: verificar que nota_wcf foi populada
SELECT count(*) FROM wines WHERE nota_wcf IS NOT NULL;
-- Deve ser proximo de 1.72M

-- Distribuicao das notas
SELECT
  CASE
    WHEN nota_wcf >= 4.5 THEN '4.5+'
    WHEN nota_wcf >= 4.0 THEN '4.0-4.49'
    WHEN nota_wcf >= 3.5 THEN '3.5-3.99'
    WHEN nota_wcf >= 3.0 THEN '3.0-3.49'
    ELSE '<3.0'
  END as faixa,
  count(*) as total
FROM wines WHERE nota_wcf IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- Diferenca entre WCF e media simples
SELECT
  ROUND(AVG(nota_wcf - vivino_rating), 3) as diff_media,
  ROUND(MIN(nota_wcf - vivino_rating), 3) as diff_min,
  ROUND(MAX(nota_wcf - vivino_rating), 3) as diff_max
FROM wines
WHERE nota_wcf IS NOT NULL AND vivino_rating IS NOT NULL;
-- WCF tipicamente e 0.05-0.15 MENOR que media simples (experts sao mais criticos)
```

## ENTREGAVEL
1. Script `C:\winegod-app\scripts\calc_wcf.py`
2. Coluna `nota_wcf` populada pra ~1.72M vinhos no Render
3. Coluna `confianca_nota` populada
4. Coluna `winegod_score_type` atualizada (verified/estimated/none)
5. Relatorio: distribuicao das notas, diferenca WCF vs media simples
