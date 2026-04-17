# Runbook: Automacao Incremental de Score — Estado Final

## Estado atual (2026-04-10)

### Ja aplicado no banco
- [x] Migration 005: colunas nota_wcf, nota_wcf_sample_size
- [x] Migration 006: tabela score_recalc_queue
- [x] Migration 007: funcao fn_enqueue_score_recalc (v1)
- [x] Migration 008: colunas attempts/last_error + indice dedup
- [x] Migration 009: funcao v2 (INSERT + UPDATE + ON CONFLICT) + trigger

### Indices de score em wines (estado real)

```
idx_wines_wg_score
  btree (winegod_score) WHERE (winegod_score IS NOT NULL)

idx_wines_score_type
  btree (winegod_score_type) WHERE (winegod_score_type != 'none')

idx_wines_pais_wgscore
  btree (pais_nome, winegod_score DESC) WHERE (winegod_score IS NOT NULL)
```

### Trigger ativo
```
trg_score_recalc  AFTER INSERT  FOR EACH ROW
trg_score_recalc  AFTER UPDATE  FOR EACH ROW
  -> fn_enqueue_score_recalc (v2, com ON CONFLICT dedup)
```

### Fila
```
score_recalc_queue: id, wine_id, reason, created_at, processed_at, attempts, last_error
  idx_recalc_pending        (created_at) WHERE processed_at IS NULL
  idx_recalc_pending_dedup  UNIQUE (wine_id) WHERE processed_at IS NULL
  idx_recalc_wine           (wine_id)
```

### Scores
- 10.983 vinhos com score real
- 0 pendentes na fila

---

## O que falta para producao

### Passo 1 — Push do branch de rollout

```bash
git push origin rollout/score-automation
```

Merge via PR no GitHub, ou push direto se for o fluxo do projeto.
O Render faz deploy automatico ao detectar push em main (se configurado).

### Passo 2 — Configurar Cron Jobs no Render

No dashboard do Render (https://dashboard.render.com), criar 2 **Cron Jobs**.

IMPORTANTE: Cron Jobs no Render sao servicos independentes. Eles clonama
o repo e executam o comando. Nao rodam dentro do web service do backend.

#### Cron Job 1: Fila (a cada 15 min)

| Campo | Valor |
|-------|-------|
| **Name** | `score-recalc-queue` |
| **Repository** | mesmo repo `winegod-app` |
| **Branch** | `main` |
| **Runtime** | Python 3 |
| **Root Directory** | _(vazio — raiz do repo)_ |
| **Build Command** | `pip install psycopg2-binary python-dotenv` |
| **Command** | `python scripts/cron_score_recalc.py` |
| **Schedule** | `*/15 * * * *` |

Env vars:
| Variavel | Valor |
|----------|-------|
| `DATABASE_URL` | URL **interna** do PostgreSQL no Render (comeca com `postgres://...` ou usar o env group) |

#### Cron Job 2: Sweep diario (4am UTC)

| Campo | Valor |
|-------|-------|
| **Name** | `score-recalc-sweep` |
| **Repository** | mesmo repo `winegod-app` |
| **Branch** | `main` |
| **Runtime** | Python 3 |
| **Root Directory** | _(vazio — raiz do repo)_ |
| **Build Command** | `pip install psycopg2-binary python-dotenv` |
| **Command** | `python scripts/cron_score_recalc.py --sweep` |
| **Schedule** | `0 4 * * *` |

Env vars: mesmas do Cron Job 1.

NOTA: Se o projeto usa um **Env Group** no Render, vincule o grupo ao cron job
em vez de copiar a DATABASE_URL manualmente.

NOTA: O script faz `sys.exit("ERROR: DATABASE_URL...")` se a env nao existir.
Se o cron falhar na primeira execucao, verifique se a env var foi configurada.

### Passo 3 — Validar primeiro run do cron

Depois que o Cron Job 1 executar pela primeira vez:

```sql
-- Verificar se houve alguma execucao
SELECT
    COUNT(*) FILTER (WHERE processed_at IS NOT NULL) AS processed,
    COUNT(*) FILTER (WHERE processed_at IS NULL AND attempts < 5) AS pending,
    COUNT(*) FILTER (WHERE processed_at IS NULL AND attempts >= 5) AS dead_lettered,
    COUNT(*) FILTER (WHERE last_error IS NOT NULL AND processed_at IS NULL) AS with_error
FROM score_recalc_queue;

-- Se houver erros
SELECT wine_id, reason, attempts, last_error, created_at
FROM score_recalc_queue
WHERE last_error IS NOT NULL AND processed_at IS NULL
ORDER BY created_at DESC LIMIT 10;

-- Sanidade dos scores
SELECT
    COUNT(*) FILTER (WHERE winegod_score IS NOT NULL) AS with_score,
    ROUND(AVG(winegod_score)::numeric, 2) AS avg_score,
    MIN(winegod_score) AS min_score,
    MAX(winegod_score) AS max_score
FROM wines
WHERE winegod_score IS NOT NULL;
```

---

## Testes de trigger (referencia — ja validados)

Todos os testes rodam dentro de transacao com ROLLBACK.
Usar um vinho com preco_min real (ex: id=588).

### Teste A — UPDATE sem mudanca real (nao deve enfileirar)

```sql
BEGIN;
SELECT COUNT(*) AS antes FROM score_recalc_queue WHERE processed_at IS NULL;
UPDATE wines SET preco_min = preco_min WHERE id = 588;
SELECT COUNT(*) AS depois FROM score_recalc_queue WHERE processed_at IS NULL;
-- depois == antes
ROLLBACK;
```

### Teste B — UPDATE com mudanca real + dedup

```sql
BEGIN;
UPDATE wines SET preco_min = preco_min + 0.01 WHERE id = 588;
SELECT wine_id, reason FROM score_recalc_queue WHERE wine_id = 588 AND processed_at IS NULL;
-- 1 row, reason='trigger_update'
UPDATE wines SET preco_min = preco_min + 0.01 WHERE id = 588;
SELECT COUNT(*) FROM score_recalc_queue WHERE wine_id = 588 AND processed_at IS NULL;
-- ainda 1 (dedup)
ROLLBACK;
```

### Teste C — INSERT de vinho novo

```sql
BEGIN;
INSERT INTO wines (nome, nome_normalizado, hash_dedup, pais_nome, preco_min, moeda)
VALUES ('__TESTE_TRIGGER__', '__teste_trigger__', '__test_hash_trigger__', 'Brasil', 50.00, 'BRL')
RETURNING id;
SELECT wine_id, reason FROM score_recalc_queue
WHERE processed_at IS NULL ORDER BY created_at DESC LIMIT 1;
-- reason='trigger_insert'
ROLLBACK;
```

---

## Resumo de acoes pendentes

| Acao | Tipo | Onde | Quem |
|------|------|------|------|
| Merge branch `rollout/score-automation` | Git | GitHub | Murilo |
| Verificar deploy backend no Render | Infra | Dashboard Render | Murilo |
| Verificar deploy frontend no Vercel | Infra | Dashboard Vercel | Murilo |
| Criar Cron Job 1 (fila) | Infra | Dashboard Render | Murilo |
| Criar Cron Job 2 (sweep) | Infra | Dashboard Render | Murilo |
| Validar primeiro run do cron | SQL | psql / pgAdmin | Murilo |
