# Decisions log — Campanha subida_vinhos_20260424

ULTIMA no topo. Cada entrada registra decisao tecnica tomada durante Fase 1/2/3.

---

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
