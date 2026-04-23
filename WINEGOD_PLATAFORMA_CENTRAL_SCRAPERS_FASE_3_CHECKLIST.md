# WINEGOD DATA OPS — FASE 3 CHECKLIST

**Data:** 2026-04-23
**Autorização:** prompt `PROMPT_CLAUDE_CONTROL_PLANE_SCRAPERS_FASE3_COMPLETA_DASHBOARD_2026-04-23.md` + autorizações explícitas Murilo (AUTORIZO FASE 3B COMMIT PUSH DASHBOARD + auto-deploy Render).

---

## 1. Status final

**Em execução:** Fase 3A implementada + testes + commit/push sendo feito. Gate Render segue.

---

## 2. Arquivos criados/modificados

### Novos
- `backend/routes/ops_dashboard.py` — blueprint com login, logout, home, detail, alerts, UI-API + endpoint /alerts/fake.
- `backend/templates/ops/login.html`
- `backend/templates/ops/home.html`
- `backend/templates/ops/scraper_detail.html`
- `backend/templates/ops/alerts.html`
- `backend/static/ops/styles.css`
- `backend/static/ops/polling.js`
- `backend/tests/test_ops_dashboard.py` — 19 testes.

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
| `/ops/alerts/fake` | POST | sessão | idem (alerta sintético, **nunca envia externo**) |
| `/ops/ui/api/summary` | GET | sessão | idem |
| `/ops/ui/api/scrapers` | GET | sessão | idem |
| `/ops/ui/api/scraper/<scraper_id>` | GET | sessão | idem |
| `/ops/ui/api/alerts` | GET | sessão | idem |

**Ausente deliberadamente:** `POST /ops/alerts/ack` (D-F0-03 do Design Freeze v2) — confirmado por teste `test_alerts_ack_is_absent`.

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

## 7. Testes locais

```
python -m pytest backend/tests/test_ops_dashboard.py tests/test_ops_endpoints.py tests/test_ops_idempotency.py tests/test_ops_validation_runtime.py -q
 → 49 passed, 1 warning in 25.15s
```

Cobre:
- `OPS_DASHBOARD_ENABLED=false` → 404 em todas UI e UI-API (10 paths).
- Login page renderiza.
- Token inválido → 401.
- Token vazio → 401.
- Token válido → 302 redirect.
- Detail com 10 seções nomeadas `1.`–`10.`.
- Labels "Observado" / "Enviado" presentes; "inseridos"/"contribuição" ausentes.
- Alerts renderiza vazio sem erro.
- `POST /ops/alerts/ack` → 404.
- Endpoints legados `/ops/health`, `/ops/scrapers`, `/ops/runs` respondendo.
- Logout limpa sessão.
- UI-API exige sessão (401).
- Rate limit após 3 tentativas.

## 8. Confirmação de escopo limpo

- ✅ Nenhum código de negócio (`public.*`) tocado.
- ✅ Nenhum scraper real rodado.
- ✅ DQ V3 intacto (`bulk_ingest.py`, `ingest.py`, `pre_ingest_router.py` não modificados).
- ✅ Nenhuma chamada externa (Decanter/Vivino/Gemini/OpenAI/WhatsApp/email).
- ✅ Nenhum token/segredo impresso ou commitado.
- ✅ Sentry/PostHog preservados em `backend/app.py` (mudanças do Murilo).

## 9. Próximos passos (Fase 3B → 3C)

Já pré-autorizado:
1. **Commit + push** com mensagem `feat(data-ops): add scraper control plane dashboard`.
2. Render auto-deploy ativo (Murilo ativou pra Fase 3) → deploy automático.
3. Murilo verificar `OPS_DASHBOARD_ENABLED=true`, `OPS_DASHBOARD_TOKEN=<token>`, `OPS_SESSION_SECRET=<chave>` no Render Environment Variables.
4. Após deploy live, health check + smoke HTTP automáticos.
5. Gate visual Murilo paralelo.
