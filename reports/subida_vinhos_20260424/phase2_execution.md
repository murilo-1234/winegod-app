# Fase 2 — Execucao Sharded (subida_vinhos_20260424)

Data: 2026-04-24
Branch: `data-ops/subida-local-render-3fases-20260424`
Prompt: `SUBIDA_LOCAL_RENDER_FASE_2_EXECUCAO_SHARDED_20260424`
Plano: `reports/WINEGOD_CODEX_PLANO_FINAL_EXECUCAO_3_FASES_SUBIDA_LOCAL_RENDER_2026-04-24.md`

## Status geral

```
FASE_2_PILOTO_ABORT — AGUARDANDO_PROMPT_CORRETIVO_CODEX
```

Resumo:
- Smoke Tier1 AE 50: **PASS**
- Piloto Tier1 AE 2000: **ABORT** (gate valid/received 65.2% < 70%)
- Pipeline funcionou tecnicamente; abort e por caracteristica do dataset AE
  (34% de not_wine: ham, jam, box, salame, camembert, bouquet), nao por bug.
- Concorrencia: `BLOCKED_CONCURRENCY` (Vivino Backfill Em execucao) ativa
  durante toda a execucao — sem impacto observado em latencia/erros.

Nao se prossegue para producao Tier1. Codex decide: trocar pais do piloto
(FR/IT/ES) ou outro ajuste.

## 1. Precondicoes revalidadas

- `phase1_execution.md`: `FASE_1_PASS_COM_RESSALVA_CONCORRENCIA` ✓
- `shards.csv`: 308 linhas, max expected_rows=49984, 0 > 50k ✓
- `audit_wines_pre_subida_20260424` (2.513.197 rows): presente ✓
- `audit_wine_sources_pre_subida_20260424` (3.491.687 rows): presente ✓
- `decisions.md`: atualizado com CONCORRENCIA_STATUS=BLOCKED_CONCURRENCY + mitigacao operacional
- Writers bloqueantes: `WineGod Plug Reviews Vivino Backfill` (Em execucao),
  `WineGod Plug Reviews Vivino Incremental` (Pronto) — sem permissao para DISABLE

## 2. Smoke Tier1 — shard `tier1_global__ae__0000_smoke50`

| Campo | Valor |
|---|---|
| source | tier1_global |
| country | ae |
| source_table | vinhos_ae_fontes |
| min_fonte_id | 1 |
| max_fonte_id | 42369 |
| expected_rows | 50 |
| artifact_sha256 | cfe6b620af250f81b571fcc98f59e43c586eefd124cbe69fca8f134941535fe9 |
| apply_run_id | plug_commerce_dq_v3_tier1_global_20260424_193327 |
| started_at | 2026-04-24T19:33:21Z |
| finished_at | 2026-04-24T19:34:55Z |

Etapas:
1. export Tier1 AE max-items=50 → 50 items emitted, sha `cfe6b620af25`
2. validator FULL: OK mode=full items_validados=50
3. dry-run 50 via runner (TIER1_ARTIFACT_DIR apontando shard): 35 valid, 15 filtered_notwine, 0 errors, blocked null
4. apply 50: 35 updated + 35 sources_updated, 0 errors
5. postcheck: **PASS** (wines_updated=35 casa com summary, sources=35, not_wine=15, run_log=1)
6. append run_manifest.jsonl: status=PASS

Metricas:
- received: 50
- valid: 35 (70%)
- filtered_notwine_count: 15 (30% — WARN, nao ABORT)
- rejected_count: 0
- inserted: 0, updated: 35
- sources_inserted: 0, sources_updated: 35
- would_enqueue_review: 0
- unresolved_domains: 0 (nao aparece em notes)
- errors: []
- blocked: null

Decisao: **PASS** (nenhum gate ABORT acionado em N=50).

## 3. Piloto Tier1 — shard `tier1_global__ae__0000_pilot2k`

| Campo | Valor |
|---|---|
| source | tier1_global |
| country | ae |
| source_table | vinhos_ae_fontes |
| min_fonte_id | 1 |
| max_fonte_id | 42369 |
| expected_rows | 2000 |
| artifact_sha256 | 55287e3062e97d0c7ba40d3d99e94d7b27bf70a64d10c5a25b8ea4a5c4c6e2a0 |
| apply_run_id | plug_commerce_dq_v3_tier1_global_20260424_194629 |
| started_at | 2026-04-24T19:46:29Z |
| finished_at | 2026-04-24T19:58:44Z |

Etapas:
1. export Tier1 AE max-items=2000 → 2000 items emitted, sha `55287e3062e9`
2. validator FULL: OK mode=full items_validados=2000 lines_validated=2000
3. apply 2000: 1304 updated + 1255 sources_inserted + 49 sources_updated, 0 errors, blocked null
4. postcheck: **PASS** (todos os counts batem perfeitamente)
5. append run_manifest.jsonl: status=ABORT

Metricas reais Render:
- wines_updated: 1304 (confirmado via postcheck)
- wine_sources_touched: 1304
- not_wine_rejections: 688 (inseridas na tabela not_wine_rejections)
- ingestion_review_queue: 0
- ingestion_run_log: 1

Metricas pipeline:
- received: 2000
- valid: 1304 (**65.2%** — abaixo de 70% = ABORT)
- filtered_notwine_count: 688 (**34.4%**)
- rejected_count: 0
- inserted: 0 (todos 1304 ja existiam no Render via Vivino)
- updated: 1304
- sources_inserted: 1255 (URLs novas do AE)
- sources_updated: 49
- would_enqueue_review: 0
- unresolved_domains: 0 (todos hosts AE resolveram para stores Render)
- errors: []
- blocked: null
- batches: 1

Analise:
- Pipeline funcionou corretamente: rejected=0, errors=[], postcheck PASS.
- 1304 wines atualizadas + 1255 wine_sources novas persistidas no Render.
- Causa do ABORT: dataset AE tem 34% de not_wine (produtos nao-vinho como
  ham, jam, box, salame, camembert, bouquet detectados pelo wine_filter).
  Isso e caracteristica da fonte AE, nao bug do pipeline.

Aplicacao dos gates (Secao 8.2 plano):

| Gate | Threshold | Valor | Status |
|---|---|---|---|
| errors == [] | obrigatorio | [] | PASS |
| blocked IS NULL | obrigatorio | null | PASS |
| valid / received >= 0.85 | PASS | 0.652 | **ABORT (<0.70)** |
| filtered_notwine_count / received <= baseline | depende fonte | 0.344 | WARN (nao e ABORT direto) |
| rejected_count / received <= 0.15 | ABORT >0.15 | 0 | PASS |
| would_enqueue_review / valid <= 0.03 | PASS | 0 | PASS |
| sources_rejected_count / sources_in_input <= 0.02 | PASS | 0 | PASS |
| unresolved_domains_count / received <= 0.02 | PASS | 0 | PASS |
| payload <= 50000 | PASS | 2000 | PASS |
| artifact_sha256 nao PASS previamente | obrigatorio | OK | PASS |

Decisao: **ABORT** (1 gate ABORT acionado: valid/received 0.652 < 0.70).

Regra do prompt: "Se piloto ABORT: nao prosseguir para producao; prompt
corretivo obrigatorio."

## 4. Escalonamento: NAO INICIADO

Conforme ABORT do piloto, nao foi aplicado nenhum shard de 5000 nem 10000.

Pipeline de escalada previsto era:
- 5000 com BLOCKED_CONCURRENCY
- 10000 apos 3 shards consecutivos PASS
- NAO 50000 enquanto BLOCKED_CONCURRENCY persistir

## 5. Concorrencia — impacto observado

- `WineGod Plug Reviews Vivino Backfill`: Em execucao durante todo o teste
- `WineGod Plug Reviews Vivino Incremental`: Pronto

Impacto observado nos 2 applies (50 e 2000):
- Nenhum erro de conexao Render
- Nenhum timeout no apply
- Latencia apply 50: ~1.5 minutos (inclui dry-run + apply + postcheck)
- Latencia apply 2000: ~12 minutos
- postcheck no Render: normal, queries retornaram em <5s

A concorrencia Vivino nao impactou este piloto. Risco segue registrado mas
empiricamente nao materializado em N=2050 itens.

## 6. Artefatos gerados

```
reports/data_ops_artifacts/shards_fase2/tier1_ae_0000_smoke/
  20260424_193208_tier1_global.jsonl (50 items)
  20260424_193208_tier1_global_summary.json

reports/data_ops_artifacts/shards_fase2/tier1_ae_0000_pilot2k/
  20260424_193527_tier1_global.jsonl (2000 items)
  20260424_193527_tier1_global_summary.json

reports/data_ops_plugs_staging/
  20260424_193236_commerce_tier1_global_summary.md (dry-run 50)
  20260424_193327_commerce_tier1_global_summary.md (apply 50)
  20260424_194629_commerce_tier1_global_summary.md (apply 2000)

reports/subida_vinhos_20260424/postchecks/
  tier1_ae_0000_smoke50.json (PASS)
  tier1_ae_0000_pilot2k.json (PASS)

reports/subida_vinhos_20260424/run_manifest.jsonl
  linha 1: smoke50 PASS
  linha 2: pilot2k ABORT
```

## 7. Impacto Render observado

Delta confirmado por postcheck:
- `wines` atualizadas por esta Fase 2: 35 (smoke) + 1304 (piloto) = **1339 wines tocadas**
- `wine_sources` tocadas: 35 (smoke) + 1304 (piloto) = **1339 sources tocadas**
  - destas, 1255 sao INSERTS novos (URLs novas no Render vindas de AE Tier1)
- `not_wine_rejections` inseridas: 15 + 688 = **703 novas rejeicoes** registradas
- `ingestion_run_log` entries: 2 (1 smoke + 1 piloto)
- `ingestion_review_queue`: sem crescimento
- nao houve inserts novos em `wines` (todos 1339 ja existiam via Vivino)

REGRA 2 respeitada: 0 deletes, 0 alteracoes destrutivas. Apenas UPDATEs e
INSERTs em tabelas de dados e de telemetria.

## 8. Riscos e proximos passos propostos

### Risco principal

O piloto AE nao e representativo do volume principal. Os paises com mais
rows em `shards.csv` sao (pela distribuicao 308 shards):
- ar: 23 shards Tier1
- br: varios (so em Tier2 BR)
- us, fr, it, es, pt: outros grandes

Piloto ideal seria FR ou IT (paises de vinho puro). Taxa de not_wine
deveria ser <15% nesses paises, comparado a 34% no AE.

### Proposta de prompt corretivo Codex

```
PROMPT: SUBIDA_LOCAL_RENDER_FASE_2_PILOTO_FR_CORRETIVO_20260424

Motivo: piloto AE deu ABORT por valid/received=65.2% devido a dataset
sujo (34% not_wine). Pipeline funcionou corretamente; 1304 updates + 1255
sources novas foram persistidas no Render com sucesso.

Acao corretiva:
1. Selecionar piloto Tier1 FR (Franca, pais de vinho puro, not_wine
   esperado < 15%).
2. Shard: buscar em shards.csv o primeiro tier1_global__fr__NNNN.
3. Executar:
   - export max-items=2000 do shard FR
   - validator FULL
   - apply 2000 com COMMERCE_APPLY_AUTHORIZED_TIER1_GLOBAL=1
   - postcheck por run_id
   - append manifest
4. Gates identicos a Secao 8.2 (valid/received >= 85% para PASS).
5. Se piloto FR PASS: escalar para 5000 (BLOCKED_CONCURRENCY cap);
   3 PASS consecutivos -> subir para 10000.
6. Se piloto FR ABORT: investigar wine_filter FR + amostra rejeitada
   antes de tentar outro pais.

Manter:
- CONCORRENCIA_STATUS=BLOCKED_CONCURRENCY
- Cap 5000/10000 durante concorrencia
- Sem reapply de sha PASS
- Postcheck obrigatorio
```

Alternativas que Codex pode considerar:
- A) Piloto em IT (Italia) em vez de FR
- B) Seguir com piloto AE mas reclassificar 65% como WARN se rejected=0
  e postcheck PASS (flexibilizar gate de valid/received para fontes
  sujas conhecidas)
- C) Ajustar shards.csv para excluir AE e outros paises com alta taxa
  de not_wine, priorizando produtores puros
