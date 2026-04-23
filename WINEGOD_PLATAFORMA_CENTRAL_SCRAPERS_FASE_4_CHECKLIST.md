# WINEGOD DATA OPS — FASE 4 CHECKLIST

**Data:** 2026-04-23
**Status geral (revisado após auditoria Codex):**

```
APROVADO_PARCIAL_INFRA_OBSERVERS
```

**Trilha escolhida:** Trilha B (fontes locais indisponíveis). Escopo MVP **reduzido formalmente** para "infra de observers + 1 fonte real (DQ V3) + 1 fonte persistida (Decanter JSON)". As 2 fontes locais (`winegod_admin` + `vivino_reviews`) **saem do MVP** e reentram quando Murilo configurar `DATABASE_URL_LOCAL_WINEGOD` / `DATABASE_URL_LOCAL_VIVINO`.

---

## 0. Por que Trilha B

A Fase 4 original exigia 3 fontes reais + DQ V3. No apply:

- `commerce_dq_v3_observer` → **success**, 12.915 itens observados (1 de 1 esperado).
- `critics_decanter_persisted` → **success**, 0 registros (arquivo local `decanter_collector_status.json` está zerado, mas o adapter leu).
- `commerce_world_winegod_admin` → **failed honesto**, `DATABASE_URL_LOCAL_WINEGOD` ausente.
- `reviews_vivino_global` → **failed honesto**, `DATABASE_URL_LOCAL_VIVINO` ausente.

Codex apontou (`WINEGOD_CONTROL_PLANE_SCRAPERS_CODEX_AUDITORIA_MVP_DATA_OPS_2026-04-23.md` §3 P0): chamar isso de "MVP completo" é enganoso. Por isso **mudamos o status para parcial** e deixamos explícito que MVP operacional completo depende de configurar as 2 envs locais.

Murilo foi informado e aceitou o MVP parcial para fechar auditoria com Codex.

## 1. Fontes detectadas

| Fonte | Env / Path | Status | Trilha |
|---|---|---|---|
| `DATABASE_URL` (Render DQ V3 + public.wines) | PRESENT | ✅ disponível | dentro do MVP |
| `decanter_collector_status.json` | `C:/natura-automation/winegod_v2/` | ✅ found (0 registros no apply) | dentro do MVP |
| `winegod_v2` dir | `C:/natura-automation/winegod_v2` | ✅ found | dentro do MVP |
| `DATABASE_URL_LOCAL_WINEGOD` / `WINEGOD_DB_URL` | MISSING | ❌ | **fora do MVP (Trilha B)** |
| `DATABASE_URL_LOCAL_VIVINO` / `VIVINO_DB_URL` | MISSING | ❌ | **fora do MVP (Trilha B)** |

## 2. Adapters implementados (4) — status honesto

| scraper_id | família | status apply | dentro do MVP? |
|---|---|---|---|
| `commerce_dq_v3_observer` | commerce | `success`, 12.915 itens | ✅ sim |
| `critics_decanter_persisted` | critic | `success`, 0 registros (fonte lida, estado atual vazio) | ✅ sim |
| `commerce_world_winegod_admin` | commerce | `failed` (`source_unavailable`, env local missing) | ❌ fora — readmite quando `DATABASE_URL_LOCAL_WINEGOD` configurado |
| `reviews_vivino_global` | review | `failed` (`source_unavailable`, env local missing) | ❌ fora — readmite quando `DATABASE_URL_LOCAL_VIVINO` configurado |

O dashboard continua mostrando os 4 adapters registrados, mas agora:
- SLA/saúde **NÃO** conta failed como saudável (ver correção `api_summary` em `ops_dashboard.py`).
- Coluna "Freshness" mostra `error` (não `fresh`) para os 2 failed — correção pré-aprovação Codex.

## 3. Gates (revisados)

| Gate | Regra | Status |
|---|---|---|
| A | 4 scrapers registrados com `can_create_wine_sources=False` e `requires_dq_v3=False` | ✅ |
| B | Runs com status correto (sem maquiagem; failed aparece como failed) | ✅ |
| C | `items_final_inserted = 0` em todos | ✅ |
| D | Volumes `ops.*` — registry 1→5, runs 1→5, batches 10→12, metrics 10→12, lineage 10→12 | ✅ |
| E | Dados de negócio inalterados — wines 2.512.042 → 2.512.042; wine_sources 3.491.038 → 3.491.038 | ✅ |
| F | Dashboard não declara SLA 100% com failed aparecendo | ✅ (após correção P0 pré-aprovação — ver §7) |
| G | 3 fontes reais success (original) | ⚠️ **PARCIAL — Trilha B** (2 success + 2 bloqueadas por env missing) |

## 4. Testes

Rodados dentro da rodada de correções pré-aprovação. Resultado real em `CLAUDE_RESPOSTAS_CONTROL_PLANE_SCRAPERS_MVP_CORRECOES_PRE_APROVACAO_2026-04-23.md` §6.

```
python -m pytest sdk/adapters/tests -q
```

## 5. DQ V3 observado read-only

Apenas SELECT. `bulk_ingest.py`, `ingest.py`, `pre_ingest_router.py` intactos.

```
git diff ab81c655..HEAD -- backend/services/bulk_ingest.py backend/services/ingest.py backend/services/pre_ingest_router.py
```
→ vazio.

## 6. Dados de negócio

| Tabela | Pré | Pós | Δ |
|---|---|---|---|
| `public.wines` | 2.512.042 | 2.512.042 | **0** |
| `public.wine_sources` | 3.491.038 | 3.491.038 | **0** |

## 7. Correções pré-aprovação aplicadas na infra Fase 4

Ver `CLAUDE_RESPOSTAS_CONTROL_PLANE_SCRAPERS_MVP_CORRECOES_PRE_APROVACAO_2026-04-23.md`.

- **Dashboard SLA/saúde**: deixou de contar failed/timeout como saudável. `api_summary` com filtro `last_status='success'` AND janela SLA. `api_scrapers` com helper `classify_freshness` que retorna `error` para failed/timeout/error.
- **`/ops/alerts/fake` dedup determinístico**: scope_key agora é `dashboard_fake_test:<scraper_id or __global__>`.
- **Checklist Fase 3**: finalizado como `APROVADO_FASE_3` (gate visual Murilo confirmado).

## 8. Pendências para readmitir as 2 fontes Trilha B

1. Murilo preencher em `backend/.env` (ou equivalente Render):
   - `DATABASE_URL_LOCAL_WINEGOD=...`
   - `DATABASE_URL_LOCAL_VIVINO=...`
2. Rerodar `python sdk/adapters/run_all_observers.py --apply` para os 2 adapters failed.
3. Validar que `ops.scraper_runs` para esses 2 adapters passa a ter `status='success'` com `items_extracted>0`.
4. Atualizar este checklist para `APROVADO_FASE_4_COMPLETO` apenas se os 4 adapters tiverem pelo menos 1 run success com lineage registrada.

## 9. Confirmação de escopo limpo

- ✅ Nenhum código de negócio tocado.
- ✅ Nenhuma chamada externa paga/paywall.
- ✅ Nenhum token/segredo em plaintext.
- ✅ Vivino adapter com `PII_FORBIDDEN_KEYS` enforced (testado).
- ✅ Decanter adapter sem imports HTTP (testado).

## 10. Commit/push

Commits Fase 4 já em `origin/main`:
- `49c7524b` — feat(data-ops): add read-only source observers

Correções pré-aprovação deste documento **não** commitadas — exigem autorização literal nova.
