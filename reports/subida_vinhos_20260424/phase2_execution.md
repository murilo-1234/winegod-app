# Fase 2 — Execucao Sharded (subida_vinhos_20260424)

Data: 2026-04-24 (atualizado 22:30 UTC apos rodada FR corretiva)
Branch: `data-ops/subida-local-render-3fases-20260424`
Prompts executados nesta fase:
- `SUBIDA_LOCAL_RENDER_FASE_2_EXECUCAO_SHARDED_20260424`
- `SUBIDA_LOCAL_RENDER_FASE_2_PILOTO_FR_CORRETIVO_20260424`
Plano mestre: `reports/WINEGOD_CODEX_PLANO_FINAL_EXECUCAO_3_FASES_SUBIDA_LOCAL_RENDER_2026-04-24.md`

## Status geral

```
FASE_2_PILOTO_FR_PASS + SHARD_FR_5K_ABORT
```

Nao seguir automaticamente para Fase 3. Nao retomar AE. Codex deve
emitir prompt corretivo de heterogeneidade por range (Tier1/FR) antes
de qualquer propagacao.

## 1. Sumario das 4 execucoes reais (run_manifest.jsonl)

| # | Shard | Pais | Range | N | Status | valid/recv | Inserts | Updates | Sources ins | Sources upd | Not_wine |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | tier1_global__ae__0000_smoke50 | ae | 1..42369 | 50 | **PASS** | 0.700 | 0 | 35 | 0 | 35 | 15 |
| 2 | tier1_global__ae__0000_pilot2k | ae | 1..42369 | 2000 | **ABORT** | 0.652 | 0 | 1304 | 1255 | 49 | 688 |
| 3 | tier1_global__fr__0000_pilot2k | fr | 1..53069 | 2000 | **PASS** | 0.892 | 1652 | 132 | 1672 | 112 | 48 |
| 4 | tier1_global__fr__0001_shard5k | fr | 53070..106138 | 5000 | **ABORT** | 0.682 | 3338 | 73 | 3364 | 47 | 1020 |
| | **TOTAIS** | | | 9050 | 2 PASS + 2 ABORT | 6534 valid | **4990** | **1544** | **6291** | **243** | 1771 |

Observacao: linhas com `status=ABORT` ainda tiveram `postcheck=PASS`
e persistiram dados no Render — o ABORT do plano e por gate
`valid/received < 0.70`, nao por falha de ingestao.

## 2. Precondicoes revalidadas (confirmadas antes de cada etapa)

- `phase1_execution.md`: `FASE_1_PASS_COM_RESSALVA_CONCORRENCIA` ✓
- `shards.csv`: 308 linhas, max expected_rows=49984, 0 > 50k ✓
- `audit_wines_pre_subida_20260424`: 2.513.197 rows ✓
- `audit_wine_sources_pre_subida_20260424`: 3.491.687 rows ✓
- `decisions.md`: BLOCKED_CONCURRENCY + mitigacao operacional registrados
- Writers bloqueantes: `WineGod Plug Reviews Vivino Backfill` (Em execucao),
  `WineGod Plug Reviews Vivino Incremental` (Pronto) — sem permissao para DISABLE

## 3. Smoke Tier1 AE 50 (`tier1_global__ae__0000_smoke50`)

| Campo | Valor |
|---|---|
| source | tier1_global |
| country | ae |
| source_table | vinhos_ae_fontes |
| range f.id | 1..42369 |
| expected_rows | 50 |
| artifact_sha256 | cfe6b620af250f81b571fcc98f59e43c586eefd124cbe69fca8f134941535fe9 |
| apply_run_id | plug_commerce_dq_v3_tier1_global_20260424_193327 |
| started_at → finished_at | 2026-04-24T19:33:21Z → 19:34:55Z |

Etapas:
1. export max-items=50 → 50 items
2. validator FULL: OK
3. dry-run 50: 35 valid, 15 filtered_notwine
4. apply 50: 0 inserted + 35 updated + 35 sources_updated
5. postcheck: **PASS** (1 run_log, 35 wines_updated, 35 sources touched, 15 not_wine)
6. manifest: **PASS**

Gates aplicados: errors=[], blocked=null, valid/received=70% (borderline, nao ABORT), rejected_count=0, unresolved_domains=0.

## 4. Piloto Tier1 AE 2000 (`tier1_global__ae__0000_pilot2k`)

| Campo | Valor |
|---|---|
| source | tier1_global |
| country | ae |
| source_table | vinhos_ae_fontes |
| range f.id | 1..42369 |
| expected_rows | 2000 |
| artifact_sha256 | 55287e3062e97d0c7ba40d3d99e94d7b27bf70a64d10c5a25b8ea4a5c4c6e2a0 |
| apply_run_id | plug_commerce_dq_v3_tier1_global_20260424_194629 |
| started_at → finished_at | 2026-04-24T19:46:29Z → 19:58:44Z (12m 15s) |

Metricas pipeline:
- received=2000, valid=1304 (**65.2%**), filtered_notwine=688 (34.4%)
- rejected=0, errors=[], blocked=null
- inserted=0, updated=1304 (todos ja existiam via Vivino)
- sources_inserted=1255, sources_updated=49

Postcheck (Render real vs summary):
- wines_new=0 ✓  wines_updated=1304 ✓  sources_touched=1304 ✓
- not_wine_rejections=688 ✓  review_queue=0 ✓  run_log=1 ✓
- status: **PASS** (counts batem perfeitamente)

Gates aplicados:
- valid/received=0.652 < 0.70 → **ABORT** (causa ABORT)
- filtered_notwine_ratio=0.344 (dataset AE sujo: ham/jam/salame/camembert/box)
- demais gates PASS

Decisao: **ABORT** — dataset AE nao representativo; Codex redirecionou para FR.

## 5. Piloto Tier1 FR 2000 (`tier1_global__fr__0000_pilot2k`)

| Campo | Valor |
|---|---|
| source | tier1_global |
| country | fr |
| source_table | vinhos_fr_fontes |
| range f.id | 1..53069 |
| expected_rows | 2000 |
| artifact_sha256 | 979faa13e2ef |
| apply_run_id | plug_commerce_dq_v3_tier1_global_20260424_212710 |
| started_at → finished_at | 2026-04-24T21:27:05Z → 21:40:02Z (12m 57s) |

Metricas pipeline:
- received=2000, valid=1784 (**89.2%**), filtered_notwine=48 (2.4%)
- rejected=0, errors=[], blocked=null
- **inserted=1652** (wines novas), updated=132
- sources_inserted=1672, sources_updated=112

Postcheck (Render real vs summary):
- wines_new=1652 ✓  wines_updated=132 ✓  sources_touched=1784 ✓
- not_wine_rejections=48 ✓  review_queue=0 ✓  run_log=1 ✓
- status: **PASS** (counts batem perfeitamente)

Gates aplicados:
- valid/received=0.892 >= 0.85 → **PASS**
- rejected_count/received=0, would_enqueue_review/valid=0, sources_rejected/sources=0,
  unresolved_domains/received=0, payload<=5000, sha sem PASS previo — **todos PASS**

Decisao: **PASS** — liberado para shard adicional de 5000 (regra corretiva Codex).

## 6. Shard Tier1 FR 5000 range 2 (`tier1_global__fr__0001_shard5k`)

| Campo | Valor |
|---|---|
| source | tier1_global |
| country | fr |
| source_table | vinhos_fr_fontes |
| range f.id | 53070..106138 |
| expected_rows | 5000 |
| artifact_sha256 | 6a39cc3cc14a |
| apply_run_id | plug_commerce_dq_v3_tier1_global_20260424_214152 |
| started_at → finished_at | 2026-04-24T21:41:48Z → 22:10:44Z (28m 56s) |

Metricas pipeline:
- received=5000, valid=3411 (**68.2%**), filtered_notwine=1020 (**20.4%**)
- rejected=0, errors=[], blocked=null
- **inserted=3338** (wines novas), updated=73
- sources_inserted=3364, sources_updated=47

Postcheck (Render real vs summary):
- wines_new=3338 ✓  wines_updated=73 ✓  sources_touched=3411 ✓
- not_wine_rejections=1020 ✓  review_queue=0 ✓  run_log=1 ✓
- status: **PASS** (counts batem perfeitamente)

Gates aplicados:
- valid/received=0.682 < 0.70 → **ABORT**
- filtered_notwine_ratio=0.204 (8x maior que no piloto FR range 1..53069)
- rejected=0, errors=[], postcheck=PASS — pipeline ok
- unresolved_domains=0, payload<=5000, sha sem PASS previo

Decisao: **ABORT** — nao propagar para 10k. Regra estrita: 1 shard adicional
pos-piloto deu ABORT => stop.

## 7. Escalonamento real executado

Sequencia efetivamente rodada:

```
Smoke AE 50     → PASS     (valid 70%, n limitado)
Piloto AE 2000  → ABORT    (valid 65.2%, AE sujo)
    [redirecionamento Codex para FR]
Piloto FR 2000  → PASS     (valid 89.2%, FR range 1 limpo)
Shard FR 5000   → ABORT    (valid 68.2%, FR range 2 sujo)
    [parada: regra estrita pos-piloto + 1 shard ABORT]
```

Caps respeitados:
- Piloto: 2000 (cap maximo do piloto)
- Shard pos-piloto: 5000 (cap BLOCKED_CONCURRENCY, nao subiu para 10k)
- Nunca excedeu 5000 com concorrencia ativa
- Cooldown 60s aplicado entre etapas

## 8. Artefatos gerados

### Artifacts JSONL + summaries
```
reports/data_ops_artifacts/shards_fase2/
├── tier1_ae_0000_smoke/
│   ├── 20260424_193208_tier1_global.jsonl (50)
│   └── 20260424_193208_tier1_global_summary.json
├── tier1_ae_0000_pilot2k/
│   ├── 20260424_193527_tier1_global.jsonl (2000)
│   └── 20260424_193527_tier1_global_summary.json
├── tier1_fr_0000_pilot2k/
│   ├── 20260424_212626_tier1_global.jsonl (2000)
│   └── 20260424_212626_tier1_global_summary.json
└── tier1_fr_0001_shard5k/
    ├── 20260424_214127_tier1_global.jsonl (5000)
    └── 20260424_214127_tier1_global_summary.json
```

### Runner summaries
```
reports/data_ops_plugs_staging/
├── 20260424_193236_commerce_tier1_global_summary.md  (AE smoke dry-run)
├── 20260424_193327_commerce_tier1_global_summary.md  (AE smoke apply)
├── 20260424_194629_commerce_tier1_global_summary.md  (AE pilot apply)
├── 20260424_212710_commerce_tier1_global_summary.md  (FR pilot apply)
└── 20260424_214152_commerce_tier1_global_summary.md  (FR 5k apply)
```

### Postchecks
```
reports/subida_vinhos_20260424/postchecks/
├── tier1_ae_0000_smoke50.json      (PASS)
├── tier1_ae_0000_pilot2k.json       (PASS)
├── tier1_fr_0000_pilot2k.json       (PASS)
└── tier1_fr_0001_shard5k.json       (PASS)
```

### Progress
```
reports/subida_vinhos_20260424/progress/
├── tier1_fr_0000_pilot2k_start.txt  2026-04-24T21:27:05Z
├── tier1_fr_0000_pilot2k_end.txt    2026-04-24T21:40:02Z
├── tier1_fr_0001_shard5k_start.txt  2026-04-24T21:41:48Z
└── tier1_fr_0001_shard5k_end.txt    2026-04-24T22:10:44Z
```

### Manifest
```
reports/subida_vinhos_20260424/run_manifest.jsonl
  linha 1: AE smoke50 PASS
  linha 2: AE pilot2k ABORT
  linha 3: FR pilot2k PASS
  linha 4: FR shard5k ABORT
```

## 9. Impacto Render observado — contas consolidadas

Somas diretas dos 4 registros do `run_manifest.jsonl`:

| Metrica | AE smoke50 | AE pilot2k | FR pilot2k | FR shard5k | **TOTAL** |
|---|---:|---:|---:|---:|---:|
| received | 50 | 2000 | 2000 | 5000 | **9050** |
| valid | 35 | 1304 | 1784 | 3411 | **6534** |
| inserted (wines novas) | 0 | 0 | 1652 | 3338 | **4990** |
| updated (wines existentes tocadas) | 35 | 1304 | 132 | 73 | **1544** |
| sources_inserted (wine_sources novas) | 0 | 1255 | 1672 | 3364 | **6291** |
| sources_updated (wine_sources tocadas) | 35 | 49 | 112 | 47 | **243** |
| filtered_notwine_count | 15 | 688 | 48 | 1020 | **1771** |
| rejected_count | 0 | 0 | 0 | 0 | **0** |
| unresolved_domains | 0 | 0 | 0 | 0 | **0** |

Delta consolidado no Render pos-Fase 2:
- **+4990 wines** (INSERTs reais; todos vinhos previamente ausentes)
- **1544 wines** tocadas por UPDATE (nao-destrutivo — atualizam `ingestion_run_id`)
- **+6291 wine_sources** novas (URLs de lojas Tier1 persistidas)
- **243 wine_sources** atualizadas (preco/moeda/ingestion_run_id atualizados)
- **+1771 not_wine_rejections** (tabela auxiliar de telemetria de filtro)
- **0 deletes** (REGRA 2 respeitada)
- **0 unresolved_domains** em todos os shards — mitigacao stores_diff confirmada

## 10. Concorrencia observada

- `BLOCKED_CONCURRENCY` permaneceu ativo durante toda a Fase 2
- `WineGod Plug Reviews Vivino Backfill`: Em execucao
- `WineGod Plug Reviews Vivino Incremental`: Pronto

Impacto empirico medido nos 4 applies:
- 0 erros de conexao Render em nenhum dos 5 runs (smoke + pilot + pilot + shard + dry-run)
- 0 BLOCKED_QUEUE_EXPLOSION
- Latencia apply por 1k items: ~6min (AE pilot 2k em 12m 15s; FR pilot 2k em 12m 57s; FR 5k em 28m 56s)
- Latencia postcheck Render: <5s em todos os casos

Risco teorico nao materializou em N=9050 items. Seguro manter
BLOCKED_CONCURRENCY enquanto Codex nao autorizar outro caminho.

## 11. Descoberta tecnica principal — heterogeneidade intra-pais por range

Pipeline comportou-se **identicamente** em todos os shards (rejected=0,
errors=[], blocked=null, postcheck=PASS). O que varia e a composicao
da FONTE por faixa de `f.id`:

| Pais | Range f.id | N | filtered_notwine_ratio | valid_ratio | Gate |
|---|---|---|---|---|---|
| AE | 1..42369 | 2000 | 34.4% | 65.2% | ABORT |
| FR | 1..53069 | 2000 | 2.4% | 89.2% | PASS |
| FR | 53070..106138 | 5000 | 20.4% | 68.2% | ABORT |

Interpretacao tecnica:
- **Nao e bug do pipeline** (postcheck PASS em todos, inserts persistidos).
- **Nao e problema do gate** (gate 70% e razoavel; foi acionado corretamente).
- **E caracteristica do dataset** (`vinhos_{cc}_fontes` foi scrapado ao longo do tempo; ranges diferentes de `f.id` correspondem a campanhas de scraping diferentes, com composicoes heterogeneas de produto — ranges antigos limpos, ranges novos incluindo mais lixo).

Implicacao: shardar sequencialmente por `f.id` garante determinismo e
anti-duplicacao, mas nao garante homogeneidade estatistica. Para
propagacao em escala e necessario ou (a) aceitar a heterogeneidade
via ajuste de gate, (b) resharding por granularidade menor, (c)
amostragem que exponha o perfil da fonte antes de escalar.

## 12. Status final da Fase 2

```
FASE_2_PILOTO_FR_PASS + SHARD_FR_5K_ABORT
```

Nao autorizado:
- abrir Fase 3
- retomar AE
- propagar Tier1 producao
- subir para 10k ou 50k

Autorizado em proximo prompt corretivo:
- ajuste de gate operacional (WARN vs ABORT quando pipeline OK mas not_wine alto)
- resharding menor de Tier1 FR ranges > 53069
- amostragem preliminar antes de apply em ranges nao-visitados

## 13. Proximo passo proposto ao Codex

```
PROMPT: SUBIDA_LOCAL_RENDER_FASE_2_HETEROGENEIDADE_RANGE_TIER1_FR_20260424

Estado de entrada:
- FASE_2_PILOTO_FR_PASS + SHARD_FR_5K_ABORT
- Piloto FR (range 1..53069): PASS (not_wine 2.4%, valid 89.2%)
- Shard FR (range 53070..106138): ABORT (not_wine 20.4%, valid 68.2%)
- Pipeline funciona identicamente em ambos; heterogeneidade e da fonte.

Objetivo:
Decidir estrategia contra heterogeneidade intra-pais antes de propagar
Tier1 para producao. Sem escalar, sem retomar AE, sem Fase 3.

Execucao obrigatoria (antes de qualquer apply novo):

1. Rodar amostragem de perfil em 3 ranges adicionais FR do shards.csv
   em modo EXPORT-ONLY (sem apply):
   - tier1_global__fr__0002 (range 106139..159205), N=500 sample
   - tier1_global__fr__0005 (meio), N=500
   - tier1_global__fr__NNNN (ultimo), N=500
   Medir filtered_notwine_ratio projetado (via validator + pre_ingest_filter
   dry-run) sem inserir no Render.

2. Produzir `reports/subida_vinhos_20260424/fr_range_profile.md` com:
   - tabela ranges vs not_wine_ratio esperado
   - decisao: quais ranges aceitaveis (not_wine < 15%) vs quais precisam
     resharding ou tratamento especial

3. Baseado no profile, escolher UMA de 3 estrategias:
   A. Gate operacional flexivel: valid/received <70% vira WARN quando
      rejected=0, errors=[], blocked=null, postcheck=PASS, delta_render>0.
      Documentar o ajuste em decisions.md.
   B. Reshardar Tier1 FR em sub-shards de 10k com profile antes do apply.
   C. Filtro dinamico de range: excluir ranges com not_wine projetado > 15%.

4. Aplicar apenas 1 shard adicional em FR range ainda nao apresentado,
   tamanho <= 5000, com estrategia escolhida em (3) aplicada. Registrar
   como evidencia de eficacia da estrategia.

5. Se esse shard passar, responder FASE_2_RETORNOU_AO_TRILHO_HETEROGENEIDADE.
   Se nao passar, parar e propor PROMPT de engenharia de dataset.

Regras absolutas:
- sem Gemini, sem items_final_inserted, sem reapply de sha PASS
- sem delete destrutivo, validator FULL antes de apply, postcheck por run_id
- cap <=5000 com BLOCKED_CONCURRENCY
- nenhum shard > 50000
- sem gate humano
```
