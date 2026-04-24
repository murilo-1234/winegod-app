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

## 2026-04-24 ~22:10 — Fase 2 piloto FR PASS + shard FR 5k ABORT

Prompt: SUBIDA_LOCAL_RENDER_FASE_2_PILOTO_FR_CORRETIVO_20260424

- Piloto Tier1 FR 2000 range 1..53069: PASS
  - valid=89.2% (1784/2000), 1652 wines NOVAS + 132 updates, 1672 sources novas
  - 48 not_wine (2.4%), 0 rejected, 0 unresolved, errors=[]
  - Postcheck PASS perfeito (counts batem)
  - Duracao 12min 57s
- Shard adicional FR 5000 range 53070..106138: ABORT
  - valid=68.2% (3411/5000) abaixo de 70% threshold
  - 3338 wines NOVAS + 73 updates + 3364 sources novas PERSISTIDAS em Render
  - 1020 not_wine (20.4%) vs 2.4% do piloto — ranges FR sao heterogeneos
  - Pipeline funcionou corretamente (rejected=0, errors=[], postcheck PASS)
  - Duracao 28min 56s (concorrencia Vivino ativa, sem erros observados)
- Delta Render nesta sessao corretiva:
  - +4990 wines NOVAS (1652 FR piloto + 3338 FR 5k)
  - +5036 wine_sources novas
  - +1068 not_wine_rejections
- Padrao tecnico: ranges diferentes do mesmo pais FR tem taxa de not_wine
  muito diferente. Sugestao: reclassificar gate valid/received por fonte
  conhecida, ou rodar amostragem random em vez de range sequencial.

## 2026-04-24 ~20:00 — Fase 2 piloto AE ABORT

- Smoke Tier1 AE 50: PASS (35 updates + 35 sources, postcheck PASS)
- Piloto Tier1 AE 2000: ABORT (valid/received=65.2% < 70% threshold)
  - rejected=0, errors=[], blocked=null, postcheck PASS
  - 1304 wines updates + 1255 wine_sources novas persistidas em Render
  - 688 not_wine_rejections corretas (ham/jam/box/salame/camembert)
  - Causa: dataset AE sujo, NAO bug do pipeline
- Escalonamento 5k/10k NAO iniciado (regra: piloto ABORT => stop)
- Concorrencia Vivino Backfill ativa durante teste — sem impacto observado
- Recomendacao: Codex emite prompt corretivo para piloto FR/IT (paises de
  vinho puro, not_wine esperado <15%)

## 2026-04-24 ~19:40 — Fase 2 autorizada com ressalva

Prompt: SUBIDA_LOCAL_RENDER_FASE_2_EXECUCAO_SHARDED_20260424
Decisao Codex: Fase 2 AUTORIZADA com ressalva de concorrencia ativa.

Estado de entrada:
- `FASE_1_PASS_COM_RESSALVA_CONCORRENCIA` (phase1_execution.md HEAD cb99b1ac)
- `CONCORRENCIA_STATUS=BLOCKED_CONCURRENCY`
- Writers bloqueantes ativos (permissao schtasks = Acesso negado):
  - `WineGod Plug Reviews Vivino Backfill`
  - `WineGod Plug Reviews Vivino Incremental`
- Snapshots audit presentes: audit_wines_pre_subida_20260424 (2.513.197 rows),
  audit_wine_sources_pre_subida_20260424 (3.491.687 rows)
- shards.csv: 308 linhas, max expected_rows=49984, 0 acima de 50k

Mitigacao operacional Fase 2 (por causa da concorrencia):
- cap inicial por apply = 5000 itens (nao 50000)
- cooldown 60s entre shards
- apply so sobe para 10000 apos 3 shards consecutivos PASS
- NAO sobe para 50000 enquanto BLOCKED_CONCURRENCY persistir
- gates rigidos: unresolved_domains > 10% = ABORT; postcheck != PASS = ABORT

Todos os artefatos da Fase 2 (phase2_execution.md, run_manifest.jsonl,
postchecks/, progress/) vao registrar CONCORRENCIA_STATUS=BLOCKED_CONCURRENCY.

## 2026-04-24 ~19:15 — Fase 1 finalizacao operacional

- `inventario_subida_vinhos.py` corrigido: TIER1_METHODS expandido (10 metodos),
  _scan_fontes_table substituida por SQL aggregates, score_recalc_queue query
  corrigida para `processed_at IS NULL`. Resultado: 308 shards, max 49984 rows.
- Snapshots criados no Render: `audit_wines_pre_subida_20260424` (2.513.197 rows)
  e `audit_wine_sources_pre_subida_20260424` (3.491.687 rows).
- Tentativa DISABLE schtasks Vivino Backfill + Incremental: ACESSO NEGADO.
  Status: BLOCKED_CONCURRENCY. Risco medio documentado.
- Preflight rerodado: snapshots OK, migration 021 FAIL nao-bloqueante.
- Status Fase 1: FASE_1_PASS_COM_RESSALVA_CONCORRENCIA.
  Aguarda decisao Codex sobre BLOCKED_CONCURRENCY antes de Fase 2.

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
