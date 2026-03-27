# CHAT C — Banco de Dados (Schema + Migracoes do WineGod)

## O QUE E O WINEGOD
WineGod.ai e uma IA sommelier global que ranqueia vinhos por custo-beneficio usando uma formula proprietaria (WineGod Score). O banco PostgreSQL no Render ja tem 1.72M vinhos importados do Vivino. Falta adicionar campos novos para o score e documentar o schema.

## SUA TAREFA
1. Documentar o schema atual do banco no Render (6 tabelas, campos, tipos, volumes)
2. Adicionar 6 campos novos na tabela `wines` (para o WineGod Score)
3. Habilitar extensao `pg_trgm` para busca fuzzy
4. Criar indices para performance
5. Gerar documentacao completa do schema

## CONEXAO COM O BANCO

```
# Banco WineGod no Render (PRODUCAO — cuidado!)
DATABASE_URL=postgresql://winegod_user:PASSWORD@dpg-XXXXX.oregon-postgres.render.com/winegod
```

Usar psql ou qualquer cliente PostgreSQL. O banco tem PostgreSQL 16.

## ONDE SALVAR ARQUIVOS
Diretorio: `C:\winegod-app\database\`

```
C:\winegod-app\database\
  schema_atual.md            ← Documentacao do schema atual (antes das mudancas)
  schema_completo.md         ← Documentacao do schema com campos novos
  migrations/
    001_add_winegod_score.sql  ← SQL para adicionar 6 campos novos
    002_add_trgm_index.sql     ← SQL para habilitar pg_trgm + indices
    003_add_performance_indexes.sql ← Indices extras para performance
  rollback/
    001_rollback.sql           ← SQL para desfazer a migracao 001
    002_rollback.sql           ← SQL para desfazer a migracao 002
```

## PASSO 1 — DOCUMENTAR SCHEMA ATUAL

Conectar ao banco e extrair informacao de TODAS as 6 tabelas:

```sql
-- Listar todas as tabelas
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';

-- Para cada tabela: campos, tipos, constraints
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'wines' AND table_schema = 'public'
ORDER BY ordinal_position;

-- Contar registros de cada tabela
SELECT 'wines' as tabela, count(*) FROM wines
UNION ALL SELECT 'wine_sources', count(*) FROM wine_sources
UNION ALL SELECT 'wine_scores', count(*) FROM wine_scores
UNION ALL SELECT 'stores', count(*) FROM stores
UNION ALL SELECT 'store_recipes', count(*) FROM store_recipes
UNION ALL SELECT 'executions', count(*) FROM executions;

-- Indices existentes
SELECT indexname, tablename, indexdef
FROM pg_indexes WHERE schemaname = 'public';

-- Tamanho do banco e tabelas
SELECT pg_size_pretty(pg_database_size('winegod'));
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;
```

Salvar resultado em `schema_atual.md` com formato claro.

## PASSO 2 — ADICIONAR 6 CAMPOS NOVOS

Estes campos sao essenciais para o WineGod Score (formula proprietaria).

### Migracao 001_add_winegod_score.sql

```sql
-- WineGod Score — campos novos na tabela wines
-- Executar com cuidado: tabela tem 1.72M registros

-- 1. Score final (custo-beneficio) — escala 0 a 5, 2 casas decimais
ALTER TABLE wines ADD COLUMN IF NOT EXISTS winegod_score DECIMAL(3,2);

-- 2. Tipo do score: se a nota e verificada (100+ reviews) ou estimada (0-99)
-- 'verified' = nota WCF pura (100+ reviews)
-- 'estimated' = nota estimada por IA (0-99 reviews)
-- 'none' = sem dados suficientes
ALTER TABLE wines ADD COLUMN IF NOT EXISTS winegod_score_type VARCHAR(20) DEFAULT 'none';

-- 3. Componentes do score (quais termos proprietarios ativaram)
-- Exemplo: {"paridade": true, "legado": true, "capilaridade": false, "avaliacoes": true}
ALTER TABLE wines ADD COLUMN IF NOT EXISTS winegod_score_components JSONB DEFAULT '{}';

-- 4. Nota WCF (Weighted Collaborative Filtering) — qualidade pura, sem preco
-- Escala 0 a 5. Esta e a "nota do vinho", diferente do "score" (custo-beneficio)
ALTER TABLE wines ADD COLUMN IF NOT EXISTS nota_wcf DECIMAL(3,2);

-- 5. Nome normalizado para deduplicacao e busca
-- Lowercase, sem acentos, sem pontuacao, espacos unicos
-- Se ja existe a coluna (verificar), nao recriar
ALTER TABLE wines ADD COLUMN IF NOT EXISTS nome_normalizado TEXT;

-- 6. Confianca da nota (0.0 a 1.0)
-- 1.0 = nota verificada com muitos reviews
-- 0.5 = nota estimada com alguns dados
-- 0.1 = nota estimada com poucos dados
ALTER TABLE wines ADD COLUMN IF NOT EXISTS confianca_nota DECIMAL(3,2);

-- Comentarios para documentacao
COMMENT ON COLUMN wines.winegod_score IS 'WineGod Score: custo-beneficio, escala 0-5';
COMMENT ON COLUMN wines.winegod_score_type IS 'verified (100+ reviews), estimated (0-99), none';
COMMENT ON COLUMN wines.winegod_score_components IS 'Termos proprietarios: paridade, legado, capilaridade, avaliacoes';
COMMENT ON COLUMN wines.nota_wcf IS 'Nota WCF: qualidade pura sem preco, escala 0-5';
COMMENT ON COLUMN wines.nome_normalizado IS 'Nome normalizado para dedup e busca fuzzy';
COMMENT ON COLUMN wines.confianca_nota IS 'Confianca da nota: 0.0 (nenhuma) a 1.0 (total)';
```

### Migracao 002_add_trgm_index.sql

```sql
-- Habilitar pg_trgm para busca fuzzy
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Indice trigram no nome normalizado (para busca fuzzy)
-- IMPORTANTE: so criar se nome_normalizado estiver populado
-- Se a coluna existir mas estiver vazia, o indice nao ajuda ate popular
CREATE INDEX IF NOT EXISTS idx_wines_nome_trgm
ON wines USING gin (nome_normalizado gin_trgm_ops);

-- Indice trigram no nome original tambem (fallback)
CREATE INDEX IF NOT EXISTS idx_wines_nome_original_trgm
ON wines USING gin (nome gin_trgm_ops);

-- Configurar threshold de similaridade
-- 0.3 e bom para vinhos (nomes longos, muita variacao)
-- Pode ajustar depois
ALTER DATABASE winegod SET pg_trgm.similarity_threshold = 0.3;
```

### Migracao 003_add_performance_indexes.sql

```sql
-- Indices para queries frequentes do chat

-- Busca por pais + rating (ranking por pais)
CREATE INDEX IF NOT EXISTS idx_wines_pais_rating
ON wines (pais, vivino_rating DESC NULLS LAST);

-- Busca por tipo (tinto, branco, etc) + rating
CREATE INDEX IF NOT EXISTS idx_wines_tipo_rating
ON wines (tipo, vivino_rating DESC NULLS LAST);

-- Busca por regiao
CREATE INDEX IF NOT EXISTS idx_wines_regiao
ON wines (regiao) WHERE regiao IS NOT NULL;

-- Busca por faixa de preco
CREATE INDEX IF NOT EXISTS idx_wines_preco_min
ON wines (preco_min) WHERE preco_min IS NOT NULL;

-- Busca por winegod_score (quando estiver populado)
CREATE INDEX IF NOT EXISTS idx_wines_wg_score
ON wines (winegod_score DESC NULLS LAST) WHERE winegod_score IS NOT NULL;

-- Busca por score_type
CREATE INDEX IF NOT EXISTS idx_wines_score_type
ON wines (winegod_score_type) WHERE winegod_score_type != 'none';

-- Indice composto para ranking custo-beneficio por pais
CREATE INDEX IF NOT EXISTS idx_wines_pais_wgscore
ON wines (pais, winegod_score DESC NULLS LAST) WHERE winegod_score IS NOT NULL;

-- Vivino ID para cross-reference
CREATE INDEX IF NOT EXISTS idx_wines_vivino_id
ON wines (vivino_id) WHERE vivino_id IS NOT NULL;
```

## PASSO 3 — EXECUTAR AS MIGRACOES

IMPORTANTE: executar UMA POR VEZ, verificando resultado entre cada uma.

1. Rodar 001 → verificar que os 6 campos foram adicionados
2. Rodar 002 → verificar que pg_trgm esta habilitado
3. Rodar 003 → verificar que indices foram criados

Apos cada migracao, rodar:
```sql
-- Verificar campos adicionados
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'wines' AND column_name IN ('winegod_score', 'winegod_score_type', 'winegod_score_components', 'nota_wcf', 'nome_normalizado', 'confianca_nota');

-- Verificar extensao
SELECT * FROM pg_extension WHERE extname = 'pg_trgm';

-- Verificar indices
SELECT indexname FROM pg_indexes WHERE tablename = 'wines' ORDER BY indexname;

-- Verificar tamanho do banco apos mudancas
SELECT pg_size_pretty(pg_database_size('winegod'));
```

## PASSO 4 — POPULAR nome_normalizado

A coluna `nome_normalizado` precisa ser populada para a busca funcionar.

```sql
-- Popular nome_normalizado para todos os vinhos
-- Remove acentos, lowercase, remove pontuacao extra
UPDATE wines
SET nome_normalizado = lower(
    translate(
        nome,
        'ÀÁÂÃÄÅàáâãäåÈÉÊËèéêëÌÍÎÏìíîïÒÓÔÕÖòóôõöÙÚÛÜùúûüÇçÑñ',
        'AAAAAAaaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuCcNn'
    )
)
WHERE nome_normalizado IS NULL;
```

CUIDADO: isso vai atualizar 1.72M registros. Pode demorar 2-5 minutos. Rodar em lote se preferir:

```sql
-- Versao em lotes de 50K (mais seguro)
UPDATE wines
SET nome_normalizado = lower(
    translate(
        nome,
        'ÀÁÂÃÄÅàáâãäåÈÉÊËèéêëÌÍÎÏìíîïÒÓÔÕÖòóôõöÙÚÛÜùúûüÇçÑñ',
        'AAAAAAaaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuCcNn'
    )
)
WHERE nome_normalizado IS NULL
AND id IN (SELECT id FROM wines WHERE nome_normalizado IS NULL LIMIT 50000);

-- Repetir ate WHERE nao achar mais (retorna 0 rows)
```

## PASSO 5 — DOCUMENTAR SCHEMA COMPLETO

Gerar `schema_completo.md` com:
- Todas as tabelas e campos (incluindo os novos)
- Tipos de dados
- Constraints (PK, FK, UNIQUE, NOT NULL)
- Indices
- Volumes (count de cada tabela)
- Tamanho em disco
- Exemplo de 3 registros da tabela wines (SELECT * FROM wines LIMIT 3)

## O QUE NAO FAZER
- NAO deletar dados existentes
- NAO alterar colunas existentes (so adicionar novas)
- NAO importar lojas ou dados novos (isso e outra tarefa)
- NAO rodar queries pesadas sem LIMIT
- NAO tocar em nada fora de `C:\winegod-app\database\`
- NAO fazer git init, commit ou push
- NAO alterar variaveis de ambiente no Render

## COMO VERIFICAR SUCESSO

Apos tudo:
```sql
-- 6 campos novos existem
SELECT count(*) FROM information_schema.columns
WHERE table_name = 'wines'
AND column_name IN ('winegod_score','winegod_score_type','winegod_score_components','nota_wcf','nome_normalizado','confianca_nota');
-- Deve retornar 6

-- pg_trgm funciona
SELECT similarity('cabernet sauvignon', 'cabernt sauvignion');
-- Deve retornar um numero entre 0 e 1

-- Busca fuzzy funciona
SELECT nome, similarity(nome_normalizado, 'cabernet sauvignon') as sim
FROM wines
WHERE nome_normalizado % 'cabernet sauvignon'
ORDER BY sim DESC
LIMIT 5;
-- Deve retornar vinhos parecidos

-- nome_normalizado populado
SELECT count(*) FROM wines WHERE nome_normalizado IS NOT NULL;
-- Deve ser igual ao total de wines (~1.72M)
```

## ENTREGAVEL
1. Arquivo `schema_atual.md` com schema ANTES das mudancas
2. Arquivo `schema_completo.md` com schema DEPOIS das mudancas
3. 3 arquivos de migracao SQL (executados com sucesso)
4. 3 arquivos de rollback SQL (caso precise desfazer)
5. Coluna nome_normalizado populada em todos os 1.72M vinhos
6. Extensao pg_trgm habilitada e funcional
7. Indices criados
