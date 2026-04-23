# WINEGOD DATA OPS — FASE 3 CHECKLIST

**Data:** 2026-04-23
**Autorização:** prompt `PROMPT_CLAUDE_CONTROL_PLANE_SCRAPERS_FASE3_COMPLETA_DASHBOARD_2026-04-23.md` + `AUTORIZO FASE 3B COMMIT PUSH DASHBOARD` + auto-deploy Render ativado pelo Murilo para esta frente.

---

## 1. Status final

```
APROVADO_FASE_3
```

Critérios batidos:

| # | Critério | Evidência |
|---|---|---|
| 1 | SHA live em `origin/main` | `ab81c655` (dashboard) + `aff304a0` (hotfix `backend/utils/observability.py` para desbloquear build) |
| 2 | `/ops/login` → 200 em produção | `curl https://winegod-app.onrender.com/ops/login -w '%{http_code}'` = **200** |
| 3 | `/health` → 200 em produção | **200** |
| 4 | `OPS_DASHBOARD_ENABLED=true` | setado pelo Murilo no Render env, confirmado via `/ops/health` (payload `OPS_DASHBOARD_ENABLED=True`) |
| 5 | Gate visual Murilo | **Confirmado no chat 2026-04-23**: Murilo abriu o Control Tower e leu os 4 cards ("Scrapers ativos agora: 0 / Observado hoje: 13.015 / Enviado hoje: 13.015 / SLA saúde: 100%") + tabela dos 5 scrapers registrados (canary + 4 observers). Aceitou o layout; única ressalva (corrigida depois) foi que SLA mostrava 100% com observers `failed`. |
| 6 | Rotas testadas | `GET /ops/login` 200, `GET /health` 200, `GET /ops/health` 200, `OPS_DASHBOARD_ENABLED=True` confirmado pelo Codex via `/ops/health` |
| 7 | Testes locais | ver §7 (rodados dentro das correções pré-aprovação) |
| 8 | Sem toque em DQ V3 | `git diff ab81c655..49c7524b -- backend/services/bulk_ingest.py backend/services/ingest.py backend/services/pre_ingest_router.py` → vazio |
| 9 | Sem toque em dados de negócio | Δ `public.wines` = 0 (2.512.042→2.512.042); Δ `public.wine_sources` = 0 (3.491.038→3.491.038) |

---

## 2. Arquivos criados/modificados

### Novos
- `backend/routes/ops_dashboard.py` — blueprint com login, logout, home, detail, alerts, UI-API + endpoint `/alerts/fake`.
- `backend/templates/ops/login.html`
- `backend/templates/ops/home.html`
- `backend/templates/ops/scraper_detail.html`
- `backend/templates/ops/alerts.html`
- `backend/static/ops/styles.css`
- `backend/static/ops/polling.js`
- `backend/tests/test_ops_dashboard.py` — testes base + testes de helpers puros (correções pré-aprovação).
- `backend/utils/observability.py` — stub no-op com try/except ImportError para sentry_sdk/posthog (hotfix deploy).

### Modificados
- `backend/app.py` — registra `ops_dashboard_bp`, inicializa `secret_key` via `OPS_SESSION_SECRET`.
- `backend/config.py` — adiciona `OPS_SESSION_SECRET`.
- `backend/.env.example` — documenta `OPS_DASHBOARD_TOKEN` e `OPS_SESSION_SECRET`.

---

## 3. Rotas implementadas

| Rota | Método | Auth | Flag |
|---|---|---|---|
| `/ops/login` | GET, POST | nenhuma | `OPS_DASHBOARD_ENABLED` |
| `/ops/logout` | GET, POST | nenhuma | idem |
| `/ops`, `/ops/home` | GET | sessão | idem |
| `/ops/scraper/<scraper_id>` | GET | sessão | idem |
| `/ops/alerts` | GET | sessão | idem |
| `/ops/alerts/fake` | POST | sessão | idem (alerta sintético, **nunca envia externo**; dedup **determinístico** — correção pré-aprovação) |
| `/ops/ui/api/summary` | GET | sessão | idem (SLA/saúde agora considera `last_run_status` — correção pré-aprovação) |
| `/ops/ui/api/scrapers` | GET | sessão | idem (freshness considera `last_run_status`) |
| `/ops/ui/api/scraper/<scraper_id>` | GET | sessão | idem |
| `/ops/ui/api/alerts` | GET | sessão | idem |

**Ausente deliberadamente:** `POST /ops/alerts/ack` (D-F0-03 do Design Freeze v2) — provado por `test_alerts_ack_is_absent`.

---

## 4. Feature flags

- `OPS_DASHBOARD_ENABLED=false` → todas as rotas UI e UI-API retornam **404** (provado por 10 testes parametrizados).
- `OPS_DASHBOARD_ENABLED=true` + `OPS_DASHBOARD_TOKEN="..."` → dashboard acessível.
- Se `OPS_DASHBOARD_ENABLED=true` + token vazio → login devolve erro "not_configured", não libera.

## 5. Login / session

- Token comparado via `hmac.compare_digest`.
- Cookie Flask session httponly + SameSite=Lax + 7 dias (via `permanent_session_lifetime` default Flask).
- Rate limit in-memory: 3 tentativas/15min por IP (após sucesso limpa o contador).
- Logout limpa `session`.

## 6. Queries / tabelas lidas

Lê **somente** `ops.*`:
- `ops.scraper_registry`
- `ops.scraper_runs`
- `ops.scraper_heartbeats`
- `ops.scraper_events`
- `ops.ingestion_batches`
- `ops.batch_metrics`
- `ops.source_lineage`
- `ops.scraper_alerts`

**Não lê** `public.wines`, `public.wine_sources` nem nenhuma tabela de negócio. Labels "Observado" / "Enviado" — nunca "inseridos" / "contribuição". Provado por teste `test_home_uses_observed_sent_not_inserted`.

## 7. Correções pré-aprovação Codex (2026-04-23)

Ver `C:\winegod-app\CLAUDE_RESPOSTAS_CONTROL_PLANE_SCRAPERS_MVP_CORRECOES_PRE_APROVACAO_2026-04-23.md` e Codex audit `C:\winegod-app\reports\WINEGOD_CONTROL_PLANE_SCRAPERS_CODEX_AUDITORIA_MVP_DATA_OPS_2026-04-23.md`.

**P0 — SLA/freshness não podia declarar failed como saudável**
- `api_summary` SLA: subquery `DISTINCT ON (scraper_id)` do último run + filtro `last_status='success'` AND dentro da janela SLA.
- `api_scrapers` freshness: usa helper puro `classify_freshness(last_end, freshness_hours, last_status)`:
  - `never` — sem run.
  - `running` — último run em `started`/`running`.
  - `error` — último run em `failed`/`timeout`/`error`.
  - `fresh` — último success dentro de 1x janela SLA.
  - `stale` — 1x–3x janela.
  - `very_stale` — além de 3x janela.
- Tests novos: `test_classify_freshness_*` e `test_is_healthy` (ver §7 abaixo).

**P1 — `POST /ops/alerts/fake` dedup determinístico**
- `scope_key` = `"dashboard_fake_test:<scraper_id or __global__>"`.
- `dedup_key` = `sha256(scraper_id|dashboard.fake_test|P3|scope_key)`.
- 2 chamadas com mesmo `scraper_id` → mesmo `dedup_key` → `ON CONFLICT (dedup_key) DO UPDATE` incrementa `occurrences` em vez de criar alerta duplicado.
- Tests novos: `test_fake_alert_dedup_key_*`.

## 8. Testes locais (pós-correção)

```
cd C:\winegod-app\backend
python -m pytest tests/test_ops_dashboard.py tests/test_ops_schema_sql.py \
                 tests/test_ops_retention.py tests/test_ops_endpoints.py \
                 tests/test_ops_idempotency.py tests/test_ops_validation_runtime.py -q
```

Resultado real registrado em `CLAUDE_RESPOSTAS_CONTROL_PLANE_SCRAPERS_MVP_CORRECOES_PRE_APROVACAO_2026-04-23.md` §6.

## 9. Confirmação de escopo limpo

- ✅ Nenhum código de negócio (`public.*`) tocado.
- ✅ Nenhum scraper real rodado.
- ✅ DQ V3 intacto (`bulk_ingest.py`, `ingest.py`, `pre_ingest_router.py` não modificados).
- ✅ Nenhuma chamada externa (Decanter/Vivino/Gemini/OpenAI/WhatsApp/email).
- ✅ Nenhum token/segredo impresso ou commitado.
- ✅ Sentry/PostHog em `backend/utils/observability.py` são no-op silencioso quando envs ausentes.

## 10. Commit/push da correção pré-aprovação

As correções P0/P1 aplicadas neste documento **NÃO** foram commitadas ainda — exigem nova autorização literal de Murilo (ex: `AUTORIZO COMMIT PUSH CORRECOES PRE APROVACAO`). Sem essa frase, Claude para sem push.

Commits Fase 3 já em `origin/main`:
- `ab81c655` — feat(data-ops): add scraper control plane dashboard
- `aff304a0` — fix(observability): add missing utils/observability.py to unblock deploy
