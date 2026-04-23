# WINEGOD DATA OPS — FASE 2 CHECKLIST

**Data:** 2026-04-22
**Autorização:** `AUTORIZO FASE 2 RENDER CANARIO` (Murilo, 2026-04-22).
**Status geral:** `PARCIAL_AGUARDANDO_DEPLOY_RENDER` — migration aplicada no Render, aguardando Murilo configurar envs + Manual Deploy.

---

## 1. Autorização

- **Frase explícita recebida:** `AUTORIZO FASE 2 RENDER CANARIO` ✅
- Fase 1 Local aprovada pelo Codex: `WINEGOD_CONTROL_PLANE_SCRAPERS_CODEX_APROVACAO_FASE1_LOCAL_2026-04-22.md`.

---

## 2. Preflight local (passou)

```
python -m pytest sdk/tests -q
 → 75 passed in 1.26s

python -m pytest backend/tests/test_ops_schema_sql.py tests/test_ops_retention.py tests/test_ops_endpoints.py tests/test_ops_idempotency.py tests/test_ops_validation_runtime.py -q
 → 46 passed, 1 warning in 16.36s

python sdk/examples/canary_scraper.py --dry-run --items 100
 → [canary] dry-run OK: all payloads valid.
```

Veredito: ✅ **APROVADO**. Preflight verde; autorizado conectar ao Render.

---

## 3. Env check (sem expor valores)

| Var | Status local `.env` | Obs |
|---|---|---|
| `DATABASE_URL` | ✅ PRESENT (aponta para Render oregon-postgres) | usado nas migrations |
| `OPS_TOKEN` | ❌ MISSING | **ação Murilo: gerar e adicionar no Render** |
| `OPS_DASHBOARD_TOKEN` | ❌ MISSING | idem |
| `OPS_API_ENABLED` | ❌ MISSING | default Config=True, OK |
| `OPS_WRITE_ENABLED` | ❌ MISSING | default Config=True, OK |
| `OPS_CANARY_ENABLED` | ❌ MISSING | default Config=True, OK |
| `OPS_BASE_URL` | ❌ MISSING | **ação Murilo: informar URL do backend Render** |

---

## 4. Dry-run transacional da migration 023 no Render

- **Técnica usada:** script `scripts/fase2_migration_runner.py dry-run`:
  1. Lê `database/migrations/023_create_ops_schema.sql`.
  2. Remove `BEGIN;` inicial e `COMMIT;` final (para não aninhar transações).
  3. Abre transação própria com `autocommit=False`.
  4. Guard: aborta se `ops` já existir.
  5. Executa DDL completo.
  6. Conta tabelas → valida `= 14`.
  7. `ROLLBACK` explícito.
  8. Pós-rollback: confirma que schema `ops` **não** persistiu.

- **Resultado:**
  ```
  [dry-run] connecting to dpg-d6o56scr85hc73843p...
  [dry-run] executing 24504 chars of DDL...
  [dry-run] tables_in_ops_after_ddl=14
  [dry-run] tables=['batch_metrics', 'batch_metrics_hourly',
    'contract_validation_errors', 'dq_decisions', 'final_apply_results',
    'ingestion_batches', 'matching_decisions', 'scraper_alerts',
    'scraper_configs', 'scraper_events', 'scraper_heartbeats',
    'scraper_registry', 'scraper_runs', 'source_lineage']
  [dry-run] OK: 14 tables created and rolled back cleanly.
  ```

Veredito: ✅ **DRY-RUN APROVADO**. DDL aceito pelo Postgres 16 do Render, incluindo `ON DELETE SET NULL (run_id)` em `ops.scraper_events` (Postgres 15+ syntax).

---

## 5. Migration definitiva

- **Comando:** `python scripts/fase2_migration_runner.py apply`
- **Resultado:**
  ```
  [apply] connecting to dpg-d6o56scr85hc73843p...
  [apply] executing migration 023 (24521 chars)...
  [apply] tables_in_ops=14
  [apply]   - batch_metrics
  [apply]   - batch_metrics_hourly
  [apply]   - contract_validation_errors
  [apply]   - dq_decisions
  [apply]   - final_apply_results
  [apply]   - ingestion_batches
  [apply]   - matching_decisions
  [apply]   - scraper_alerts
  [apply]   - scraper_configs
  [apply]   - scraper_events
  [apply]   - scraper_heartbeats
  [apply]   - scraper_registry
  [apply]   - scraper_runs
  [apply]   - source_lineage
  [apply] OK: migration applied, 14 tables confirmed.
  ```

Veredito: ✅ **MIGRATION APLICADA** no banco `winegod` do Render. 14 tabelas `ops.*` criadas.

**Rollback disponível** (caso necessário) via `023_create_ops_schema.rollback.sql` — `DROP SCHEMA ops CASCADE`. Válido enquanto só houver dados do canário.

---

## 6. Snapshot pré-canário (dados de negócio no Render)

Coletados antes de qualquer canário `--apply`:

```sql
SELECT count(*) FROM public.wines;          -- wines_count_before = 2512042
SELECT count(*) FROM public.wine_sources;   -- wine_sources_count_before = 3491038
```

Estes números serão comparados **após** o canário no Gate 8.

---

## 7. Deploy manual Render — BLOQUEIO atual

**Código da Fase 1 ainda NÃO está no Render.** Status git:

- Branch atual: `i18n/h4-exec`.
- Arquivos modificados não-commitados: ~60 (incluindo `backend/app.py`, `backend/config.py`, `backend/routes/ops.py` e SDK completo).
- Último commit: `a7442506 fix(i18n): normalize es-419 and fr-FR locale quality...`

**Ação manual Murilo (CRÍTICA):**

1. **Decidir branch** — commit da Fase 1 vai na branch atual (`i18n/h4-exec`) ou em nova branch (`ops/fase1`) com PR para main?
2. **Commit + push** do bloco Fase 1 (arquivos novos + modificados relacionados a `ops.*` apenas).
3. **No dashboard do Render**, Environment Variables do backend `winegod-app`:
   - Adicionar `OPS_TOKEN` com um token forte (32+ chars random, ex: `python -c "import secrets; print(secrets.token_urlsafe(36))"`).
   - Adicionar `OPS_DASHBOARD_TOKEN` (outro token forte).
   - Opcionalmente confirmar `OPS_API_ENABLED=true`, `OPS_WRITE_ENABLED=true`, `OPS_CANARY_ENABLED=true` (defaults seguros do Config se ausentes).
4. **Manual Deploy** do backend no Render (aba "Manual Deploy" → "Deploy latest commit").
5. **Informar URL** do backend Render (ex: `https://winegod-app.onrender.com`) para o canário.

**REGRA 7 do CLAUDE.md:** deploy no Render NÃO é automático. `git push` **não** dispara deploy. Murilo precisa clicar no dashboard.

**Status:** ⏸ **AGUARDANDO AÇÃO MANUAL**.

---

## 8. Health check — PENDENTE

Depois do Manual Deploy confirmado:

```bash
curl https://<RENDER_URL>/ops/health
```

Esperado:
```json
{ "ok": true, "db": "ok", "schema": "ops", "version": "0.1.0", "flags": {...} }
```

**Status:** ⏸ **AGUARDANDO DEPLOY**.

---

## 9. Canário `--apply` — PENDENTE

Depois do health check:

```powershell
$env:OPS_BASE_URL="<RENDER_URL>"
$env:OPS_TOKEN="<TOKEN>"  # mesmo valor configurado no Render
python sdk/examples/canary_scraper.py --apply --items 100
```

**Status:** ⏸ **AGUARDANDO DEPLOY E TOKEN**.

---

## 10. Gates SQL (Gate 1–8) — PENDENTES

Serão executados após canário `--apply`. Queries prontas no prompt Fase 2 §9.

---

## 11. Decisão

**Status atual:** `BLOQUEADO_AGUARDANDO_DEPLOY_RENDER`

Migration aplicada OK, 14 tabelas confirmadas. **Não posso avançar para canário `--apply`** enquanto:
1. Murilo não gerar `OPS_TOKEN` + colocar no Render.
2. Murilo não fazer commit + push + Manual Deploy.
3. Murilo não informar URL do backend Render.

Este checklist será **atualizado** com os resultados dos passos 7–11 quando Murilo sinalizar prontidão.

---

## Arquivos tocados nesta parte da Fase 2

- `C:\winegod-app\scripts\fase2_migration_runner.py` (novo — runner de migration controlado)
- `C:\winegod-app\WINEGOD_PLATAFORMA_CENTRAL_SCRAPERS_FASE_2_CHECKLIST.md` (este, novo)
- **Banco Render:** schema `ops.*` + 14 tabelas criadas.
