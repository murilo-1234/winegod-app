# Runbook: Ativacao da Automacao Incremental de Score

## Pre-requisito
A limpeza massiva de scores legados em `wines` precisa estar CONCLUIDA.
Os indices dropados precisam ter sido recriados pelo outro chat.

---

## Passo 1 — Verificar que a limpeza terminou

```sql
-- Deve retornar 0 (ou o numero de scores reais gravados)
SELECT COUNT(*) FROM wines WHERE winegod_score IS NOT NULL;

-- Verificar que indices de score existem de novo
SELECT indexname FROM pg_indexes WHERE tablename = 'wines' AND indexname LIKE '%score%';
```

Se os indices `idx_wines_wg_score`, `idx_wines_score_type`, `idx_wines_pais_wgscore`
nao existirem, recria-los com a definicao exata que foi dropada:

```sql
CREATE INDEX idx_wines_wg_score
    ON wines (winegod_score DESC NULLS LAST)
    WHERE winegod_score IS NOT NULL;

CREATE INDEX idx_wines_score_type
    ON wines (winegod_score_type)
    WHERE winegod_score_type != 'none';

CREATE INDEX idx_wines_pais_wgscore
    ON wines (pais, winegod_score DESC NULLS LAST)
    WHERE winegod_score IS NOT NULL;
```

---

## Passo 2 — Aplicar migration 008 (endurecer fila)

```sql
-- Rodar no banco via psql ou pgAdmin:
\i database/migrations/008_harden_score_recalc_queue.sql
```

Ou colar diretamente:

```sql
ALTER TABLE score_recalc_queue ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE score_recalc_queue ADD COLUMN IF NOT EXISTS last_error TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_recalc_pending_dedup
    ON score_recalc_queue (wine_id) WHERE processed_at IS NULL;
```

Validacao:

```sql
-- Deve mostrar: id, wine_id, reason, created_at, processed_at, attempts, last_error
SELECT column_name FROM information_schema.columns
WHERE table_name = 'score_recalc_queue' ORDER BY ordinal_position;

-- Deve mostrar idx_recalc_pending_dedup
SELECT indexname FROM pg_indexes WHERE tablename = 'score_recalc_queue';
```

---

## Passo 3 — Aplicar migration 009 (trigger v2)

```sql
\i database/migrations/009_score_recalc_trigger_v2.sql
```

Validacao:

```sql
-- Deve mostrar trg_score_recalc com event_manipulation = INSERT e UPDATE
SELECT trigger_name, event_manipulation
FROM information_schema.triggers
WHERE trigger_name = 'trg_score_recalc';

-- Deve retornar a funcao com TG_OP = 'INSERT' e ON CONFLICT
SELECT prosrc FROM pg_proc WHERE proname = 'fn_enqueue_score_recalc';
```

---

## Passo 4 — Teste controlado de enqueue

Todos os testes rodam dentro de transacao com ROLLBACK.
Nenhum dado real e alterado.

IMPORTANTE: Escolher um vinho que tenha preco_min real (nao NULL).
Para encontrar um ID valido:

```sql
SELECT id, nome, preco_min, moeda FROM wines
WHERE preco_min > 0 AND moeda IS NOT NULL ORDER BY id LIMIT 1;
```

Usar o ID retornado nos testes A e B abaixo (ex: 588).

### Teste A — UPDATE sem mudanca real (nao deve enfileirar)

```sql
BEGIN;

-- Gravar contagem inicial da fila
SELECT COUNT(*) AS antes FROM score_recalc_queue WHERE processed_at IS NULL;

-- UPDATE que NAO muda valor (preco_min = preco_min)
UPDATE wines SET preco_min = preco_min WHERE id = 588;

-- Deve ser igual a contagem anterior (trigger nao dispara)
SELECT COUNT(*) AS depois FROM score_recalc_queue WHERE processed_at IS NULL;

ROLLBACK;
```

### Teste B — UPDATE com mudanca real (deve enfileirar 1x, com dedup)

```sql
BEGIN;

-- Mudar preco de verdade
UPDATE wines SET preco_min = preco_min + 0.01 WHERE id = 588;

-- Deve ter 1 entrada pendente
SELECT wine_id, reason FROM score_recalc_queue
WHERE wine_id = 588 AND processed_at IS NULL;
-- Esperado: 1 row, reason='trigger_update'

-- Mudar de novo (testar dedup)
UPDATE wines SET preco_min = preco_min + 0.01 WHERE id = 588;

-- Deve continuar com apenas 1 entrada (dedup via unique index)
SELECT COUNT(*) FROM score_recalc_queue
WHERE wine_id = 588 AND processed_at IS NULL;
-- Esperado: 1

ROLLBACK;
```

### Teste C — INSERT de vinho novo (deve enfileirar)

IMPORTANTE: wines tem colunas NOT NULL: nome, nome_normalizado, hash_dedup.

```sql
BEGIN;

-- Inserir vinho de teste com preco (incluir colunas NOT NULL)
INSERT INTO wines (nome, nome_normalizado, hash_dedup, pais_nome, preco_min, moeda)
VALUES ('__TESTE_TRIGGER__', '__teste_trigger__', '__test_hash_trigger__', 'Brasil', 50.00, 'BRL')
RETURNING id;
-- Anotar o ID retornado (ex: 3360694)

-- Deve ter 1 entrada com reason='trigger_insert'
SELECT wine_id, reason FROM score_recalc_queue
WHERE processed_at IS NULL ORDER BY created_at DESC LIMIT 1;

ROLLBACK;
```

Se todos os 3 testes passarem, o trigger esta funcionando corretamente.
O ROLLBACK garante que nenhum dado foi alterado.

---

## Passo 5 — Rodar worker manualmente uma vez

```bash
# No terminal do Render (ou local com DATABASE_URL configurado)
cd /opt/render/project/src   # ou C:\winegod-app local

# Enfileirar alguns vinhos manualmente para teste
python -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(\"\"\"
    INSERT INTO score_recalc_queue (wine_id, reason)
    SELECT id, 'manual_test' FROM wines
    WHERE preco_min > 0 AND moeda IS NOT NULL
      AND (nota_wcf IS NOT NULL OR vivino_rating > 0)
    ORDER BY id LIMIT 10
    ON CONFLICT (wine_id) WHERE processed_at IS NULL DO NOTHING
\"\"\")
conn.commit()
print(f'Enqueued {cur.rowcount}')
conn.close()
"

# Rodar worker com batch pequeno
python scripts/calc_score_incremental.py --batch 10 --max-time 60

# Verificar resultados
python -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM score_recalc_queue WHERE processed_at IS NOT NULL')
print(f'Processed: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM score_recalc_queue WHERE processed_at IS NULL')
print(f'Pending: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM score_recalc_queue WHERE last_error IS NOT NULL')
print(f'With errors: {cur.fetchone()[0]}')
conn.close()
"
```

---

## Passo 6 — Configurar Cron Jobs no Render

No dashboard do Render, criar 2 Cron Jobs:

### Cron Job 1: Fila (a cada 15 min)
- **Name:** score-recalc-queue
- **Command:** `python scripts/cron_score_recalc.py`
- **Schedule:** `*/15 * * * *`
- **Environment:** mesmo `DATABASE_URL` do backend

### Cron Job 2: Sweep diario (4am UTC)
- **Name:** score-recalc-sweep
- **Command:** `python scripts/cron_score_recalc.py --sweep`
- **Schedule:** `0 4 * * *`
- **Environment:** mesmo `DATABASE_URL` do backend

Ambos precisam:
- Runtime: Python 3.11
- Build: `pip install psycopg2-binary`
- Env var: `DATABASE_URL` (mesmo valor do backend)

---

## Passo 7 — Verificacoes pos-ativacao

Depois de 1 hora com o cron rodando:

```sql
-- Itens processados vs pendentes vs com erro
SELECT
    COUNT(*) FILTER (WHERE processed_at IS NOT NULL) AS processed,
    COUNT(*) FILTER (WHERE processed_at IS NULL AND attempts < 5) AS pending,
    COUNT(*) FILTER (WHERE processed_at IS NULL AND attempts >= 5) AS dead_lettered,
    COUNT(*) FILTER (WHERE last_error IS NOT NULL AND processed_at IS NULL) AS with_error
FROM score_recalc_queue;

-- Ultimos erros (se houver)
SELECT wine_id, reason, attempts, last_error, created_at
FROM score_recalc_queue
WHERE last_error IS NOT NULL AND processed_at IS NULL
ORDER BY created_at DESC LIMIT 10;

-- Sanidade dos scores recem-calculados
SELECT
    COUNT(*) FILTER (WHERE winegod_score IS NOT NULL) AS with_score,
    ROUND(AVG(winegod_score)::numeric, 2) AS avg_score,
    MIN(winegod_score) AS min_score,
    MAX(winegod_score) AS max_score
FROM wines
WHERE winegod_score IS NOT NULL;
```

---

## Resumo de passos que exigem acao manual

| Passo | Tipo | Onde |
|-------|------|------|
| 1 | Verificacao SQL | psql / pgAdmin |
| 2 | Migration SQL | psql / pgAdmin |
| 3 | Migration SQL | psql / pgAdmin |
| 4 | Teste SQL | psql / pgAdmin |
| 5 | Teste CLI | Terminal Render ou local |
| 6 | Config infra | Dashboard Render |
| 7 | Verificacao SQL | psql / pgAdmin |

Nao ha deploy do backend necessario para a automacao funcionar.
Os cron jobs sao processos separados no Render.
