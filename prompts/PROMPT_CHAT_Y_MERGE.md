INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar.

# CHAT Y_MERGE — Juntar 8 tabelas de match Vivino

## CONTEXTO

A Fase Y rodou em 8 abas paralelas. Cada aba processou um grupo de paises e criou `match_results_y{1-8}` no banco local. Agora precisa unificar.

## CREDENCIAL

```
Banco local: postgresql://postgres:postgres123@localhost:5432/winegod_db
```

## O QUE FAZER

Criar script `scripts/merge_match_results_y.py` que:

### 1. Verificar as 8 tabelas

```sql
SELECT 'y1' as grp, count(*) FROM match_results_y1
UNION ALL SELECT 'y2', count(*) FROM match_results_y2
UNION ALL SELECT 'y3', count(*) FROM match_results_y3
UNION ALL SELECT 'y4', count(*) FROM match_results_y4
UNION ALL SELECT 'y5', count(*) FROM match_results_y5
UNION ALL SELECT 'y6', count(*) FROM match_results_y6
UNION ALL SELECT 'y7', count(*) FROM match_results_y7
UNION ALL SELECT 'y8', count(*) FROM match_results_y8;
```

O total deve ser ~2,942,304.

### 2. Criar tabela unificada

```sql
DROP TABLE IF EXISTS match_results_y;
CREATE TABLE match_results_y AS
SELECT unique_id, vivino_id, match_score, match_strategy, match_level, loja_nome, vivino_nome
FROM match_results_y1
UNION ALL SELECT unique_id, vivino_id, match_score, match_strategy, match_level, loja_nome, vivino_nome FROM match_results_y2
UNION ALL SELECT unique_id, vivino_id, match_score, match_strategy, match_level, loja_nome, vivino_nome FROM match_results_y3
UNION ALL SELECT unique_id, vivino_id, match_score, match_strategy, match_level, loja_nome, vivino_nome FROM match_results_y4
UNION ALL SELECT unique_id, vivino_id, match_score, match_strategy, match_level, loja_nome, vivino_nome FROM match_results_y5
UNION ALL SELECT unique_id, vivino_id, match_score, match_strategy, match_level, loja_nome, vivino_nome FROM match_results_y6
UNION ALL SELECT unique_id, vivino_id, match_score, match_strategy, match_level, loja_nome, vivino_nome FROM match_results_y7
UNION ALL SELECT unique_id, vivino_id, match_score, match_strategy, match_level, loja_nome, vivino_nome FROM match_results_y8;

CREATE INDEX idx_mry_uid ON match_results_y (unique_id);
CREATE INDEX idx_mry_vid ON match_results_y (vivino_id);
CREATE INDEX idx_mry_level ON match_results_y (match_level);
```

### 3. Auditoria

```sql
-- Total
SELECT count(*) as total,
       count(DISTINCT unique_id) as unique_ids
FROM match_results_y;
-- unique_ids deve = total (sem duplicatas)

-- Distribuicao
SELECT match_level, count(*),
       round(100.0 * count(*) / sum(count(*)) OVER(), 1) as pct,
       round(avg(match_score)::numeric, 3) as score_medio
FROM match_results_y GROUP BY match_level ORDER BY count(*) DESC;

-- Match rate
SELECT
    count(*) FILTER (WHERE match_level IN ('high', 'medium')) as match_hm,
    count(*) FILTER (WHERE match_level = 'low') as match_low,
    count(*) FILTER (WHERE match_level = 'no_match') as sem_match,
    round(100.0 * count(*) FILTER (WHERE match_level IN ('high', 'medium')) / count(*), 1) as taxa_hm
FROM match_results_y;

-- Estrategia
SELECT match_strategy, count(*)
FROM match_results_y GROUP BY match_strategy ORDER BY count(*) DESC;

-- Vivinos mais matchados
SELECT vivino_id, count(*) as lojas, min(vivino_nome) as nome
FROM match_results_y WHERE vivino_id IS NOT NULL
GROUP BY vivino_id ORDER BY lojas DESC LIMIT 20;

-- Amostras
SELECT loja_nome, vivino_nome, match_score, match_strategy
FROM match_results_y WHERE match_level = 'high' ORDER BY match_score DESC LIMIT 10;

SELECT loja_nome, vivino_nome, match_score, match_strategy
FROM match_results_y WHERE match_level = 'no_match' ORDER BY random() LIMIT 10;
```

### 4. Drop temporarias (so se tudo OK)

```sql
DROP TABLE IF EXISTS match_results_y1, match_results_y2, match_results_y3,
    match_results_y4, match_results_y5, match_results_y6, match_results_y7,
    match_results_y8;
```

## ENTREGAVEL

Imprimir relatorio completo. NAO commit/push.
