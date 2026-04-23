# WINEGOD DATA OPS — FASE 4 CHECKLIST

**Data:** 2026-04-23
**Status geral:** `APROVADO_FASE_4`

---

## 1. Fontes detectadas

| Fonte | Env / Path | Status |
|---|---|---|
| `DATABASE_URL` (Render DQ V3 + public.wines) | PRESENT | ✅ disponível |
| `DATABASE_URL_LOCAL_WINEGOD` / `WINEGOD_DB_URL` | MISSING | ❌ indisponível (run=failed documentado) |
| `DATABASE_URL_LOCAL_VIVINO` / `VIVINO_DB_URL` | MISSING | ❌ indisponível (run=failed documentado) |
| `decanter_collector_status.json` | `C:/natura-automation/winegod_v2/` | ✅ found |
| `winegod_v2` dir | `C:/natura-automation/winegod_v2` | ✅ found |

## 2. Adapters implementados (4)

| scraper_id | família | status apply | observação |
|---|---|---|---|
| `commerce_world_winegod_admin` | commerce | `failed` (source_unavailable) | env local ausente |
| `reviews_vivino_global` | review | `failed` (source_unavailable) | idem |
| `critics_decanter_persisted` | critic | `success` | JSON lido, 0 registros |
| `commerce_dq_v3_observer` | commerce | `success` | 11 runs, 6003 wines, 6547 sources, 354 not_wine, 0 queue |

## 3. Gates (todos verdes)

- **Gate A — 4 scrapers registrados** com `can_create_wine_sources=False` e `requires_dq_v3=False` ✅
- **Gate B — Runs com status correto** (2 success, 2 failed honesto) ✅
- **Gate C — items_final_inserted=0 em todos** ✅
- **Gate D — ops.* volumes**: registry 1→5, runs 1→5, batches 10→12, metrics 10→12, lineage 10→12 ✅
- **Gate E — Dados de negócio inalterados**: wines 2512042→2512042, wine_sources 3491038→3491038 ✅

## 4. Testes (28 verdes)

```
python -m pytest sdk/adapters/tests -q
 → 28 passed in 1.41s
```

## 5. DQ V3 observado read-only

Apenas SELECT. `bulk_ingest.py`, `ingest.py`, `pre_ingest_router.py` intactos.

## 6. Pendências

1. `DATABASE_URL_LOCAL_WINEGOD` e `DATABASE_URL_LOCAL_VIVINO` no `.env` quando quiser dados reais.
2. Dashboard Render Fase 3 ainda em auto-deploy.
3. Task Scheduler 1x/hora — não ativado (requer autorização separada).
