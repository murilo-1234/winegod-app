# Fase 1 — Execucao (subida_vinhos_20260424)

Data: 2026-04-24
Branch: `data-ops/subida-local-render-3fases-20260424`
Plano: `reports/WINEGOD_CODEX_PLANO_FINAL_EXECUCAO_3_FASES_SUBIDA_LOCAL_RENDER_2026-04-24.md`

## Status geral

```
IMPLEMENTACAO_CONCLUIDA_VALIDACAO_OPERACIONAL_PARCIAL
```

Motivo do status (nao `FASE_1_PASS`):

- todo o codigo, wrappers, scripts e testes da Secao 6.1 estao
  implementados e commitados; 190 testes PASS.
- preflight foi executado contra DBs reais e gerou `preflight.md`;
  resultado traz 2 gates FAIL (migration 021 + snapshot audit).
- inventario foi executado em 2 chamadas: local com `--skip-render`
  completou OK; chamada completa caiu em `statement_timeout` na
  consulta Render (`canceling statement due to statement timeout`).
  `shards.csv` foi gerado com 0 linhas (elegibilidade local retornou
  zero — o inventario precisa de investigacao antes de shards reais).
- snapshots `audit_wines_pre_subida_20260424` e
  `audit_wine_sources_pre_subida_20260424` ainda NAO existem no Render.
- writers concorrentes (schtasks Vivino/backup) estao `Pronto` (ativos)
  — nao foram pausados.

Portanto nao e `PASS`: implementacao pronta, validacao operacional
parcial, artefatos finais ainda precisam ser regenerados com cobertura
real antes de abrir a Fase 2.

## 1. Escopo executado

Conforme Secao 6.1 do plano Codex:

| # | Item | Status |
|---|---|---|
| 1 | Sharding real nos 5 exporters | IMPLEMENTADO |
| 2 | Artifact apply explicito (TIER1_ARTIFACT_DIR/TIER2_/AMAZON_MIRROR_) | IMPLEMENTADO |
| 3 | Wrapper unico de shard | IMPLEMENTADO |
| 4 | Amazon legacy done marker gated | IMPLEMENTADO |
| 5 | Amazon mirror state journal pending/commit/abort | IMPLEMENTADO |
| 6 | Postcheck por run_id | IMPLEMENTADO |
| 7 | Inventario + shard plan | SCRIPTS IMPLEMENTADOS + EXECUCAO LOCAL OK + EXECUCAO RENDER FALHOU (timeout) + SHARDS.CSV VAZIO |
| 8 | Testes | 190 PASS / 0 FAIL |
| 9 | Preflight | EXECUTADO; 2 gates FAIL (migration 021, snapshot audit) |

9/9 entregas de codigo previstas na Fase 1 foram implementadas
(sharding, wrappers, scripts tooling, testes, docs).

A passagem operacional da Fase 1 continua INCOMPLETA:
- preflight tem 2 gates em FAIL (migration 021, snapshot audit);
- inventario Render nao foi coletado (statement_timeout);
- shards.csv esta vazio (0 linhas);
- concorrencia nao foi serializada (2 writers Render ativos).

Nenhuma dessas 4 pendencias e uma entrega de codigo; sao validacoes
operacionais que ficaram abertas. Portanto `FASE_1_PASS` nao se aplica.

## 2. Commits gerados (sem push)

Branch `data-ops/subida-local-render-3fases-20260424`, 6 commits
apos `0fa420d3`:

| Commit | Escopo |
|---|---|
| `d369a319` | fix: Amazon legacy done marker gated by env + manifest PASS |
| `a856265b` | feat: postcheck + manifest + hash tooling |
| `c932a464` | feat: Amazon mirror state journal pending/commit/abort |
| `15920a72` | feat: sharding real nos 5 exporters + wrapper apply_shard |
| `df622ee4` | feat: scripts de inventario + preflight + shards planner |
| `834d37ab` | docs: phase1_execution + phase1_tests + decisions log (versao anterior) |

Este documento substitui `834d37ab` em commit posterior.

## 3. Arquivos alterados / criados

### Exporters (patch sharding)
- `sdk/plugs/commerce_dq_v3/artifact_exporters/base.py` (+ `MAX_SHARD_ITEMS=50000`, `shard_spec` no summary)
- `sdk/plugs/commerce_dq_v3/artifact_exporters/tier1_global.py`
- `sdk/plugs/commerce_dq_v3/artifact_exporters/tier2_global.py`
- `sdk/plugs/commerce_dq_v3/artifact_exporters/tier2_br.py`
- `sdk/plugs/commerce_dq_v3/artifact_exporters/amazon_legacy.py`
- `sdk/plugs/commerce_dq_v3/artifact_exporters/amazon_mirror.py` (+ state journal)

### CLIs (flags novas)
- `scripts/data_ops_producers/export_tier1_global.py`
- `scripts/data_ops_producers/export_tier2_global.py`
- `scripts/data_ops_producers/export_tier2_br.py`
- `scripts/data_ops_producers/export_amazon_legacy.py`
- `scripts/data_ops_producers/export_amazon_mirror.py`

### Wrappers
- `scripts/data_ops_scheduler/run_commerce_apply_shard.ps1` (novo)
- `scripts/data_ops_scheduler/run_commerce_apply_amazon_legacy.ps1` (alterado)
- `scripts/data_ops_scheduler/remove_amazon_legacy_done_marker.ps1` (novo)

### Scripts tooling
- `scripts/data_ops_producers/postcheck_run_id.py` (novo)
- `scripts/data_ops_producers/append_run_manifest.py` (novo)
- `scripts/data_ops_producers/hash_artifact.py` (novo)
- `scripts/data_ops_producers/amazon_mirror_state.py` (novo — status/commit/abort)
- `scripts/data_ops_producers/inventario_subida_vinhos.py` (novo)
- `scripts/data_ops_producers/preflight_subida_vinhos.py` (novo)

### Testes (novos)
- `sdk/plugs/commerce_dq_v3/artifact_exporters/tests/test_sharding.py` (12 testes)
- `sdk/plugs/commerce_dq_v3/artifact_exporters/tests/test_amazon_mirror_state_journal.py` (4 testes)
- `scripts/data_ops_producers/tests/test_postcheck_tooling.py` (9 testes)
- `scripts/data_ops_producers/tests/test_inventario_shards.py` (8 testes)
- `scripts/data_ops_scheduler/tests/__init__.py`
- `scripts/data_ops_scheduler/tests/test_amazon_legacy_marker.py` (4 testes)
- `scripts/data_ops_scheduler/tests/test_apply_shard_wrapper.py` (9 testes)

### Artefatos da campanha
- `reports/subida_vinhos_20260424/decisions.md`
- `reports/subida_vinhos_20260424/run_manifest.jsonl` (vazio, pronto para appends)
- `reports/subida_vinhos_20260424/postchecks/` (vazio)
- `reports/subida_vinhos_20260424/progress/` (vazio)
- `reports/subida_vinhos_20260424/quarantine/` (vazio)
- `reports/subida_vinhos_20260424/preflight.md` (REAL, gerado pelo script)
- `reports/subida_vinhos_20260424/inventory.json` (REAL, incompleto — Render timeout)
- `reports/subida_vinhos_20260424/inventory_summary.txt` (REAL)
- `reports/subida_vinhos_20260424/shards.csv` (REAL, 0 linhas — alvo de investigacao)

## 4. Preflight real

Executado em `2026-04-24T16:00:03Z`. Saida em `preflight.md`.

Resumo:

- branch: `data-ops/subida-local-render-3fases-20260424` HEAD `834d37ab`
- DSNs mascarados confirmados:
  - winegod_local: `postgres://***:***@localhost/winegod_db`
  - render: `postgres://***:***@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod`
- Schema Render:
  - migration 018 (`ingestion_run_log`): OK
  - migration 019 (`not_wine_rejections`): OK
  - migration 020 (`ingestion_review_queue`): OK
  - migration 021 (`wcf_pipeline_control`): FALTA
- Counts baseline Render:
  - `wines` = 2.513.197
  - `wine_sources` = 3.491.687
  - `stores` = 19.889
  - `ingestion_review_queue` pending = 10
  - db_size_pretty = 8.426 MB (~8.4 GB de 15 GB)
- Snapshots pre-campanha:
  - `audit_wines_pre_subida_20260424`: FALTA CRIAR
  - `audit_wine_sources_pre_subida_20260424`: FALTA (nao listado pelo script atual; pendencia real)
- Concorrencia detectada (schtasks status `Pronto`):
  - `\BackupVivino08h`
  - `\BackupVivino14h`
  - `\BackupVivino22h`
  - `\WineGod Plug Reviews Vivino Backfill`
  - `\WineGod Plug Reviews Vivino Incremental`

Gates preflight:

- dsn_local_presente: PASS
- dsn_render_presente: PASS
- migration_018_ok: PASS
- migration_019_ok: PASS
- migration_020_ok: PASS
- migration_021_ok: FAIL
- snapshot_audit_presente: FAIL

Resultado: 5 PASS, 2 FAIL.

## 5. Inventario real

Executado em `2026-04-24T16:02:19Z` em 2 chamadas.

### 5.1 Chamada completa (local + Render)

- conexao local: OK
- shards calculados por source: OK (looping concluido)
- conexao Render: iniciada
- query Render (`SELECT COUNT(*) FROM public.wines`): `QueryCanceled: canceling statement due to statement timeout`
- exit code: 1

### 5.2 Chamada `--skip-render`

- conexao local: OK
- inventory.json: gerado
- inventory_summary.txt: gerado
- shards.csv: gerado com 0 linhas (so header)
- exit code: 0

### 5.3 Dados coletados (inventory_summary.txt)

```
lojas_scraping_total = 86.089
wines_clean_total    = 3.962.334
tier1_eligible       = 0
tier2_global_elig    = 0
tier2_br_eligible    = 0
amazon_legacy        = 0
amazon_mirror        = 0
local_hosts_distinct = 0
vinhos_tables        = 50
```

Render na chamada `--skip-render`:
- wines_total = None
- wine_sources_total = None
- stores_total = None
- db_size_pretty = None
- queue_pending = None

Gates inventario (chamada --skip-render):
- db_size_below_12gb: NAO_AVALIADO (valor Render = None; dado real
  nao foi coletado porque a chamada completa caiu em
  statement_timeout e a chamada --skip-render nao consulta Render)
- queue_below_100k: NAO_AVALIADO (mesmo motivo)
- stores_diff_below_20pct: NAO_AVALIADO (Render data ausente; diff
  nao calculavel)

Nota: o preflight real coletou `db_size_pretty = 8426 MB` e
`ingestion_review_queue_pending = 10`, mas esses numeros vem de uma
execucao independente do inventario e nao sao suficientes para
declarar PASS dos gates deste bloco — o inventario propriamente dito
continua sem coleta Render para ser auditavel.

### 5.4 Leitura tecnica dos dados

- 86k lojas em `lojas_scraping`, 3.96M em `wines_clean`, 50 tabelas
  `vinhos_<cc>` — dados existem localmente.
- Todas as 5 contagens de elegibilidade retornam 0, incluindo
  `local_hosts_distinct = 0`. Isso sinaliza que a query de host distinct
  entre `lojas_scraping` e `vinhos_<cc>_fontes` nao esta casando — ou a
  coluna `host_normalizado` / esquema esperado pelo script nao bate com
  o schema real do `winegod_db`.
- Com `shards.csv` vazio, a Fase 2 nao tem shard real para apply. Nao
  faz sentido declarar PASS.

## 6. Snapshots pre-campanha

Para rollback medio viavel (Secao 9 do plano), dois snapshots sao
necessarios no Render:

- `audit_wines_pre_subida_20260424` — lista inicial de IDs e
  `ingestion_run_id` pre-campanha para computar "IDs novos" por
  diferenca pos-apply.
- `audit_wine_sources_pre_subida_20260424` — mesmo papel para
  `wine_sources`, permitindo rollback fino por `wine_id`.

Ambos sao PENDENCIA REAL. Nenhum dos dois existe hoje no Render.

Criacao proposta (a ser disparada pelo proximo passo tecnico):

```sql
CREATE TABLE IF NOT EXISTS audit_wines_pre_subida_20260424 AS
  SELECT id, ingestion_run_id, created_at FROM wines;
CREATE INDEX IF NOT EXISTS idx_audit_wines_pre_id
  ON audit_wines_pre_subida_20260424(id);

CREATE TABLE IF NOT EXISTS audit_wine_sources_pre_subida_20260424 AS
  SELECT id, wine_id, ingestion_run_id FROM wine_sources;
CREATE INDEX IF NOT EXISTS idx_audit_wine_sources_pre_id
  ON audit_wine_sources_pre_subida_20260424(id);
```

REGRA 2 (CLAUDE.md) nao e violada: cria tabelas auxiliares, nao
altera/deleta existentes.

## 7. Concorrencia — estado operacional atual

Com base no preflight, classifico cada writer em 2 eixos separados:

- `scheduler_status`: estado reportado pelo `schtasks /Query`
- `blocking_relevance`: se bloqueia (ou nao) a Fase 2 de commerce apply

| Writer | scheduler_status | blocking_relevance | Destino Render? |
|---|---|---|---|
| `\BackupVivino08h` | Pronto | NOT_APPLICABLE | Nao (dump local) |
| `\BackupVivino14h` | Pronto | NOT_APPLICABLE | Nao (dump local) |
| `\BackupVivino22h` | Pronto | NOT_APPLICABLE | Nao (dump local) |
| `\WineGod Plug Reviews Vivino Backfill` | Pronto | BLOCKING_NOT_PAUSED | Sim (escreve `wines`, `wine_scores`, queues) |
| `\WineGod Plug Reviews Vivino Incremental` | Pronto | BLOCKING_NOT_PAUSED | Sim (idem) |

Resultado consolidado para Fase 2:

```
CONCORRENCIA_STATUS = BLOCKING_NOT_PAUSED
WRITERS_BLOQUEANTES_ATIVOS = [
  WineGod Plug Reviews Vivino Backfill,
  WineGod Plug Reviews Vivino Incremental
]
WRITERS_NAO_APLICAVEIS = [
  BackupVivino08h, BackupVivino14h, BackupVivino22h
]
```

`scheduler_status = Pronto` dos jobs `BackupVivino*` nao vira PASS de
concorrencia automaticamente — eles nao entram no calculo porque nao
escrevem no Render. Por isso a coluna separada `blocking_relevance`.

Acao tecnica do proximo passo: desabilitar schtasks dos 2 writers
ativos antes do primeiro apply de Fase 2; reabilitar apos fechamento
de Fase 2 ou no fechamento de Fase 3. Se ambiente/permissao nao
permitir, registrar `BLOCKED_CONCURRENCY` no manifesto/decisoes.

## 8. Testes

Ver `phase1_tests.txt` para detalhes. Resumo:

```
sdk/plugs/commerce_dq_v3/                       114 passed
scripts/data_ops_producers/tests/                63 passed
scripts/data_ops_scheduler/tests/                13 passed
--------------------------------------------------------
TOTAL                                           190 passed, 0 failed
```

Zero regressao em testes pre-existentes. Teste `test_bulk_ingest_
does_not_import_new_wines` inclui verificacao textual que confirma
`bulk_ingest.py` nao chama Gemini/enrichment_v3 — se futuro patch
acoplar, teste falha automaticamente.

## 9. Gates da Fase 1 (Secao 6.3 do plano Codex)

Estado real (evidencia ou pendencia):

| Gate | Evidencia | Status |
|---|---|---|
| testes obrigatorios PASS | 190/190 em 3 suites | PASS |
| shards.csv existe e nao tem overlap | `shards.csv` existe mas 0 linhas | INCOMPLETO (arquivo vazio; overlap trivial) |
| nenhum shard > 50000 | `MAX_SHARD_ITEMS=50000` raise em `write_artifact` | PASS (enforce em codigo) |
| runner/wrapper aplica artifact explicito ou diretorio isolado | wrapper seta `TIER{1,2}_ARTIFACT_DIR` / `AMAZON_MIRROR_ARTIFACT_DIR` | PASS (enforce em codigo) |
| anti-reprocessamento funciona | wrapper le manifest e aborta exit 5 se sha PASS | PASS (enforce em codigo + teste) |
| Amazon legacy done marker corrigido | env + manifest PASS enforcado | PASS (enforce em codigo + teste) |
| Amazon mirror state protegido | pending/commit/abort + teste | PASS (enforce em codigo + teste) |
| preflight.md confirma DSNs/schema/backup | preflight gerado; migration 021 FAIL + snapshot audit FAIL | INCOMPLETO (2 gates preflight em FAIL) |
| inventory.json confirma volume real | inventory gerado; chamada completa falhou (Render timeout); elegibilidade local = 0 em todas as 5 sources; gates `db_size_below_12gb`, `queue_below_100k`, `stores_diff_below_20pct` marcados `NAO_AVALIADO` por valor Render None | INCOMPLETO (Render nao coletado; shards vazio) |
| bulk_ingest continua sem Gemini | teste `test_bulk_ingest_does_not_import_new_wines` PASS | PASS |

Resumo:

- 7 gates PASS por evidencia em codigo + teste.
- 3 gates INCOMPLETOS (preflight parcial, inventory parcial, shards vazio).

Portanto nao ha justificativa tecnica para declarar `FASE_1_PASS`.

## 10. Riscos residuais

### R1. migration 021 (wcf_pipeline_control) ausente no Render
Indica que a migration nao foi aplicada. Nao bloqueia Fase 2
diretamente (commerce apply nao usa wcf_pipeline_control), mas
impede confirmar concorrencia de lote WCF ativo. Proximo passo
tecnico: checar se a migration existe em `database/migrations/020_*`
e comparar com Render; aplicar se for o caso (fora desta Fase 1).

### R2. Snapshots `audit_*` nao criados
Sem eles, nao ha rollback medio viavel na Fase 2. Proximo passo
tecnico: executar os CREATE TABLE da Secao 6 antes do primeiro apply
Fase 2.

### R3. Inventario Render: statement_timeout
Query `SELECT COUNT(*) FROM public.wines` abortou em timeout. O
script usa `statement_timeout = 60000`. Em Render Basic, com 2.5M
linhas e ingestao ativa, esse count pode passar de 60s. Proximo
passo tecnico: aumentar o timeout para 180000 no script (ou
particionar a consulta), rerun `inventario_subida_vinhos.py`.

### R4. Shards.csv vazio
5 sources retornando 0 elegivel sugere descasamento entre o query
de elegibilidade e o schema real do `winegod_db`. Proximo passo
tecnico: inspecionar `lojas_scraping.host_normalizado` vs
`vinhos_<cc>_fontes.url_original` e ajustar a query do
`_collect_local`, OU usar heuristica diferente (normalize_host de
cada URL). Sem shards, Fase 2 nao tem o que aplicar.

### R5. Concorrencia nao serializada
Writers `WineGod Plug Reviews Vivino Backfill` e `Incremental`
ativos. Proximo passo tecnico: desabilitar via `schtasks /Change
/DISABLE` antes do primeiro apply Fase 2.

### R6. pytest name collision entre 3 dirs `tests/`
Cada suite passa isolada; comando agregado colide. Baixa prioridade.
Futuro: `conftest.py` ou `pyproject.toml` com `testpaths`.

### R7. wrapper Amazon mirror recorrente e Fase 3
Nao entra nesta fase. Nesta fase, exporter Amazon mirror pode rodar
manual via CLI com state journal protegido.

## 11. Proximo passo tecnico

Sem gate humano de passagem. Proximo passo e encadeado:

1. Corrigir `_collect_local` em `inventario_subida_vinhos.py` para
   fazer as 5 contagens de elegibilidade retornarem valor real.
   Sem isso, `shards.csv` fica vazio e nao ha apply possivel.
   Escopo: diagnostico + fix + rerun; atualizar este relatorio.

2. Aumentar `statement_timeout` em `_collect_render` para 180000ms
   (ou particionar por tabela). Rerun inventario completo.

3. Executar snapshots pre-campanha no Render:
   - `audit_wines_pre_subida_20260424`
   - `audit_wine_sources_pre_subida_20260424`
   Se ambiente nao permitir CREATE, registrar `BLOCKED_ENV`.

4. Desabilitar schtasks `WineGod Plug Reviews Vivino Backfill` e
   `WineGod Plug Reviews Vivino Incremental` via `schtasks /Change
   /DISABLE`. Se ambiente nao permitir, registrar
   `BLOCKED_CONCURRENCY`.

5. Rerun preflight + inventario; conferir:
   - migration 021 status (pode continuar FALTA sem bloquear);
   - snapshots audit_* presentes;
   - shards.csv com N linhas reais, nenhuma excedendo 50k;
   - inventory.json com counts Render reais.

6. Atualizar este `phase1_execution.md` para
   `IMPLEMENTACAO_CONCLUIDA_VALIDACAO_OPERACIONAL_COMPLETA` ou, se
   todos os gates ficarem PASS, `FASE_1_PASS`.

7. Somente apos `FASE_1_PASS`, Codex emite prompt
   `SUBIDA_LOCAL_RENDER_FASE_2_EXECUCAO_SHARDED_20260424`.

Se algum passo encontrar `BLOCKED_ENV` ou `BLOCKED_CONCURRENCY`,
registrar no `decisions.md` com evidencia e aguardar prompt Codex
corretivo dentro da Fase 1, sem bloquear no humano.
