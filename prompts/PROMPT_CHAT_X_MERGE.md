INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# CHAT X_MERGE — Juntar 10 tabelas de dedup em wines_unique

## CONTEXTO

A Fase X (deduplicacao) rodou em 10 abas paralelas. Cada aba processou um grupo de paises e salvou resultado em `wines_unique_g1` ate `wines_unique_g10` e `dedup_quarantine_g1` ate `dedup_quarantine_g10`.

Este prompt junta tudo na tabela final `wines_unique` e `dedup_quarantine`.

## CREDENCIAIS

```
WINEGOD_LOCAL_URL=postgresql://postgres:XXXXXXXXX@localhost:5432/winegod_db
```

## O QUE FAZER

Criar script `scripts/merge_dedup_groups.py` que:

### 1. Verificar que todas as 10 tabelas existem

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name LIKE 'wines_unique_g%'
ORDER BY table_name;
-- Deve retornar 10 tabelas (g1 a g10)
```

Se alguma falta, avisar qual e parar.

### 2. Mostrar contagens de cada grupo

```sql
SELECT 'g1' as grupo, COUNT(*) FROM wines_unique_g1
UNION ALL SELECT 'g2', COUNT(*) FROM wines_unique_g2
...
UNION ALL SELECT 'g10', COUNT(*) FROM wines_unique_g10;
```

### 3. Criar tabela final wines_unique

```sql
CREATE TABLE wines_unique AS
SELECT * FROM wines_unique_g1
UNION ALL SELECT * FROM wines_unique_g2
UNION ALL SELECT * FROM wines_unique_g3
UNION ALL SELECT * FROM wines_unique_g4
UNION ALL SELECT * FROM wines_unique_g5
UNION ALL SELECT * FROM wines_unique_g6
UNION ALL SELECT * FROM wines_unique_g7
UNION ALL SELECT * FROM wines_unique_g8
UNION ALL SELECT * FROM wines_unique_g9
UNION ALL SELECT * FROM wines_unique_g10;

-- Resetar IDs sequenciais
ALTER TABLE wines_unique ADD COLUMN new_id SERIAL;
ALTER TABLE wines_unique DROP COLUMN id;
ALTER TABLE wines_unique RENAME COLUMN new_id TO id;
ALTER TABLE wines_unique ADD PRIMARY KEY (id);

-- Indices
CREATE INDEX idx_wu_nome ON wines_unique (nome_normalizado);
CREATE INDEX idx_wu_produtor ON wines_unique (produtor_normalizado) WHERE produtor_normalizado IS NOT NULL;
CREATE INDEX idx_wu_hash ON wines_unique (hash_dedup) WHERE hash_dedup IS NOT NULL;
CREATE INDEX idx_wu_pais ON wines_unique (pais_tabela);
CREATE INDEX idx_wu_ean ON wines_unique (ean_gtin) WHERE ean_gtin IS NOT NULL;
CREATE INDEX idx_wu_match ON wines_unique (match_type);
```

### 4. Criar tabela final dedup_quarantine

```sql
CREATE TABLE dedup_quarantine AS
SELECT * FROM dedup_quarantine_g1
UNION ALL SELECT * FROM dedup_quarantine_g2
... (mesma logica)
UNION ALL SELECT * FROM dedup_quarantine_g10;
```

### 5. Rodar auditoria basica

```sql
-- Total
SELECT COUNT(*) as total_unicos FROM wines_unique;
SELECT COUNT(*) as total_quarentena FROM dedup_quarantine;

-- Por tipo de match
SELECT match_type, COUNT(*), ROUND(AVG(match_probability)::numeric, 2) as prob_media
FROM wines_unique GROUP BY match_type ORDER BY COUNT(*) DESC;

-- Por pais
SELECT pais_tabela, COUNT(*) FROM wines_unique GROUP BY pais_tabela ORDER BY COUNT(*) DESC;

-- Distribuicao de copias
SELECT total_copias, COUNT(*) FROM wines_unique GROUP BY total_copias ORDER BY total_copias DESC LIMIT 15;

-- Grupos muito grandes (suspeitos)
SELECT id, nome_limpo, total_copias, match_type FROM wines_unique WHERE total_copias > 50 ORDER BY total_copias DESC LIMIT 20;

-- Amostra de 20 merges deterministicos
SELECT nome_limpo, produtor, safra, total_copias, match_type FROM wines_unique WHERE match_type = 'deterministic' ORDER BY RANDOM() LIMIT 20;

-- Amostra de 20 merges Splink
SELECT nome_limpo, produtor, safra, total_copias, match_type, match_probability FROM wines_unique WHERE match_type = 'splink_high' ORDER BY RANDOM() LIMIT 20;

-- Quarentena — amostras
SELECT nome_a, nome_b, match_probability, motivo FROM dedup_quarantine ORDER BY RANDOM() LIMIT 20;
```

### 6. Drop tabelas temporarias (so se auditoria OK)

```sql
DROP TABLE IF EXISTS wines_unique_g1, wines_unique_g2, wines_unique_g3, wines_unique_g4, wines_unique_g5;
DROP TABLE IF EXISTS wines_unique_g6, wines_unique_g7, wines_unique_g8, wines_unique_g9, wines_unique_g10;
DROP TABLE IF EXISTS dedup_quarantine_g1, dedup_quarantine_g2, dedup_quarantine_g3, dedup_quarantine_g4, dedup_quarantine_g5;
DROP TABLE IF EXISTS dedup_quarantine_g6, dedup_quarantine_g7, dedup_quarantine_g8, dedup_quarantine_g9, dedup_quarantine_g10;
```

### 7. Imprimir relatorio final

```
=== MERGE CONCLUIDO ===
Total vinhos unicos: X
Total quarentena: X
Por match_type: deterministico X | splink_high X | splink_medium X
Taxa de dedup global: de 3,955,624 para X (Y% reducao)
Grupos >50 copias: X (verificar se sao suspeitos)
```

## O QUE NAO FAZER

- **NAO modificar wines_clean** — so ler as tabelas _g
- **NAO conectar ao banco Render** — tudo local
- **NAO fazer git commit/push**
- **NAO dropar tabelas temporarias se a auditoria mostrar problemas** — avisar o CTO

## ENTREGAVEL

- Tabela `wines_unique` populada com todos os vinhos unicos de todos os 10 grupos
- Tabela `dedup_quarantine` com todos os pares incertos
- Relatorio impresso no terminal
- Script `scripts/merge_dedup_groups.py`
