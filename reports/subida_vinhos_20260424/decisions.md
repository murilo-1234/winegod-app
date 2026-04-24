# Decisions log — Campanha subida_vinhos_20260424

ULTIMA no topo. Cada entrada registra decisao tecnica tomada durante Fase 1/2/3.

---

## 2026-04-24 ~16:00 Fase 1 — preflight + inventario executados

- `python scripts/data_ops_producers/preflight_subida_vinhos.py`:
  - exit=0, gerou `preflight.md`
  - gates: dsn PASS, migrations 018/019/020 PASS, migration 021 FAIL,
    snapshot audit FAIL
  - concorrencia: 5 schtasks detectadas `Pronto`; 2 relevantes para
    Render (`WineGod Plug Reviews Vivino Backfill` e `Incremental`)
- `python scripts/data_ops_producers/inventario_subida_vinhos.py`:
  - exit=1, falhou em `_collect_render` com `statement_timeout` no
    `SELECT COUNT(*) FROM public.wines`
- `python scripts/data_ops_producers/inventario_subida_vinhos.py --skip-render`:
  - exit=0, gerou `inventory.json`, `inventory_summary.txt`, `shards.csv`
  - 5 sources retornaram `eligible=0` e `local_hosts_distinct=0`
  - `shards.csv` ficou com 0 linhas (so header)
- Status Fase 1: `IMPLEMENTACAO_CONCLUIDA_VALIDACAO_OPERACIONAL_PARCIAL`.
  Nao autoriza Fase 2 ate:
  - `_collect_local` ser corrigido para gerar shards > 0;
  - statement_timeout ser ajustado para coleta Render;
  - snapshots `audit_wines_pre_subida_20260424` e
    `audit_wine_sources_pre_subida_20260424` serem criados;
  - schtasks Vivino Backfill/Incremental serem desabilitadas.

## 2026-04-24 Fase 1 — setup inicial

- Branch `data-ops/subida-local-render-3fases-20260424` criada a partir de
  `data-ops/execucao-total-commerce-fechamento-final-20260424` (HEAD 0fa420d3).
- Estrutura `reports/subida_vinhos_20260424/` + subdirs criada:
  - postchecks/
  - progress/
  - quarantine/
- Plano de fases conforme `reports/WINEGOD_CODEX_PLANO_FINAL_EXECUCAO_3_FASES_*`.
- Rails confirmados:
  - commerce apply NAO chama Gemini/enrichment_v3 (teste `test_sharding.py`);
  - zero alteracao em backend/services/bulk_ingest.py, new_wines.py, enrichment_v3.py;
  - zero `git reset --hard`, `git push --force`, merge em main;
  - zero apply em producao ate Fase 2 autorizada.
