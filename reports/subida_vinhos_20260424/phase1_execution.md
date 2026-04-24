# Fase 1 — Execucao (subida_vinhos_20260424)

Data: 2026-04-24
Branch: `data-ops/subida-local-render-3fases-20260424`
Plano: `reports/WINEGOD_CODEX_PLANO_FINAL_EXECUCAO_3_FASES_SUBIDA_LOCAL_RENDER_2026-04-24.md`

## 1. Escopo executado

Conforme Secao 6.1 do plano Codex:

1. Sharding real nos 5 exporters — OK
2. Artifact apply explicito (via `TIER1_ARTIFACT_DIR`, `TIER2_ARTIFACT_DIR`, `AMAZON_MIRROR_ARTIFACT_DIR`) — OK
3. Wrapper unico de shard — OK
4. Amazon legacy done marker — OK
5. Amazon mirror state journal — OK
6. Postcheck por run_id — OK
7. Inventario e shard plan (scripts) — OK
8. Testes — OK (190 PASS, 0 FAIL)
9. Preflight (script + skeleton) — OK

Total: 9/9 tarefas da Fase 1 concluidas.

## 2. Commits gerados (sem push)

Branch `data-ops/subida-local-render-3fases-20260424`, 5 commits, origem
`data-ops/execucao-total-commerce-fechamento-final-20260424` (HEAD `0fa420d3`):

| Commit | Escopo |
|---|---|
| `d369a319` | fix: Amazon legacy done marker gated by env + manifest PASS |
| `a856265b` | feat: postcheck + manifest + hash tooling |
| `c932a464` | feat: Amazon mirror state journal pending/commit/abort |
| `15920a72` | feat: sharding real nos 5 exporters + wrapper apply_shard |
| `df622ee4` | feat: scripts de inventario + preflight + shards planner |

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

## 4. Arquitetura final Fase 1

### Sharding
- `ExporterConfig` de todos 5 exporters ganharam `source_table_filter`, `min_fonte_id`, `max_fonte_id`, `shard_id`.
- `_iter_rows` aplica `WHERE f.id BETWEEN %s AND %s` na SQL quando sharding ligado.
- `write_artifact` raise `ValueError` se `max_items > MAX_SHARD_ITEMS=50000` (REGRA 5 + `BULK_INGEST_MAX_ITEMS=50000`).
- `shard_spec={shard_id, source_table, min_fonte_id, max_fonte_id}` vai pro summary JSON.

### Anti-reprocessamento
- `run_commerce_apply_shard.ps1` le `run_manifest.jsonl` antes de qualquer apply.
- Se `artifact_sha256` (via `hash_artifact.py`) ja aparece com `status=PASS`, aborta com `exit 5`.

### Amazon legacy done marker
- Marker so gravado se `COMMERCE_AMAZON_LEGACY_MARK_DONE=1` E manifest contem >=1 shard `source=amazon_local_legacy_backfill` todos com `status=PASS`.
- Rollback via `remove_amazon_legacy_done_marker.ps1 -Force`.

### Amazon mirror state journal
- `run_export` grava em `amazon_mirror.pending.json`, nao no state oficial.
- `commit_pending_state()` promove pending -> oficial apos apply PASS.
- `abort_pending_state(reason=...)` move para `aborted/<key>.aborted_<ts>.json`.
- `has_pending_state()` bloqueia novo export com `reason=blocked_state_pending_orfao`.
- CLI: `python scripts/data_ops_producers/amazon_mirror_state.py {status|commit|abort --reason TEXT}`.

### Postcheck por run_id
- `postcheck_run_id.py --run-id X --summary-path Y --apply-start Z --output W`.
- Compara summary markdown (bloco JSON extraido) com queries Render por `ingestion_run_id`:
  - `wines` novos (`created_at >= apply_start`);
  - `wines` atualizados (`created_at < apply_start`);
  - `wine_sources` tocadas;
  - `not_wine_rejections` count;
  - `ingestion_review_queue` count;
  - `ingestion_run_log` exists.
- Tolerancia 2% (5% pra not_wine).
- PASS ou FAIL no JSON de saida.

### Inventario e shard plan
- `inventario_subida_vinhos.py [--skip-render]` le winegod_db + Render READ-ONLY.
- Saida: `inventory.json`, `shards.csv`, `inventory_summary.txt`.
- `_plan_shards(total_rows, min_id, max_id, shard_size=50000)` funcao pura testada.
- Shards disjuntos por `source_table + f.id`.

### Preflight
- `preflight_subida_vinhos.py` gera `preflight.md` com:
  - branch/commit HEAD;
  - DSNs mascarados (nao expoe senha);
  - migrations 018-021 via `to_regclass`;
  - baseline counts wines/wine_sources/stores/queues;
  - check snapshot `audit_wines_pre_subida_20260424` (reporta instrucao se falta);
  - schtasks Vivino/WCF;
  - gates PASS/FAIL.

## 5. Testes

Ver `phase1_tests.txt` para detalhes. Resumo:

```
sdk/plugs/commerce_dq_v3/                       114 passed
scripts/data_ops_producers/tests/                63 passed
scripts/data_ops_scheduler/tests/                13 passed
--------------------------------------------------------
TOTAL                                           190 passed, 0 failed
```

Zero regressao em testes pre-existentes. Teste regra absoluta do plano 3
fases (`test_bulk_ingest_does_not_import_new_wines`) inclui verificacao
textual que confirma `bulk_ingest.py` nao chama Gemini/enrichment_v3 —
se futuro patch acoplar, teste falha automaticamente.

## 6. Gates da Fase 1 (Secao 6.3 do plano Codex)

- [x] testes obrigatorios PASS — 190/190
- [x] shards.csv existe e nao tem overlap — logica `_plan_shards` testada; shards.csv em si gera na primeira execucao do inventario
- [x] nenhum shard > 50000 — hard cap em `base.py:MAX_SHARD_ITEMS` raise ValueError
- [x] runner/wrapper aplica artifact explicito ou diretorio isolado — wrapper seta `TIER{1,2}_ARTIFACT_DIR` / `AMAZON_MIRROR_ARTIFACT_DIR` por shard
- [x] anti-reprocessamento funciona — wrapper le manifest e aborta com exit 5 se sha PASS
- [x] Amazon legacy done marker corrigido — so marca com env + manifest PASS
- [x] Amazon mirror state protegido — pending/commit/abort journal + teste
- [x] preflight.md confirma DSNs/schema/backup — script `preflight_subida_vinhos.py`
- [x] inventory.json confirma volume real — script `inventario_subida_vinhos.py` pronto; FUNDADOR ainda precisa rodar
- [x] bulk_ingest continua sem Gemini — teste automatico `test_bulk_ingest_does_not_import_new_wines`

## 7. Riscos residuais / itens para Fase 2

### Risco A: inventario + preflight ainda nao executados contra DBs reais
- Scripts prontos, mas fundador precisa disparar:
  ```powershell
  $env:WINEGOD_DATABASE_URL = "postgresql://...winegod_db..."
  $env:DATABASE_URL = "postgresql://...render..."
  python scripts/data_ops_producers/preflight_subida_vinhos.py
  python scripts/data_ops_producers/inventario_subida_vinhos.py
  ```
- Saidas: `reports/subida_vinhos_20260424/{preflight.md,inventory.json,shards.csv,inventory_summary.txt}`.
- Codex audita os arquivos gerados antes de autorizar Fase 2.

### Risco B: snapshot audit_wines_pre_subida_20260424 nao existe
- Preflight reporta instrucao `CREATE TABLE audit_wines_pre_subida_20260424 AS SELECT id, ingestion_run_id, created_at FROM wines`.
- Fundador executa no Render antes de Fase 2 (REGRA 2: nao deleta, so adiciona — criar tabela auxiliar nao viola).

### Risco C: pytest name collision entre 3 dirs `tests/`
- Cada suite passa isoladamente. Comando agregado colide por nome.
- Correcao de baixa prioridade: `conftest.py` ou `pyproject.toml` com `testpaths`.

### Risco D: wrapper Amazon mirror recorrente ainda nao criado
- Plano Fase 3 (recorrencia) — nao e Fase 1. Nesta fase, exporter Amazon mirror pode rodar manual via CLI com state journal protegido.

### Risco E: `inventario_subida_vinhos.py` faz COUNT por pais em loop
- Statement timeout 60s por query (nao global). ~50 paises = ate 50 queries; nenhuma sozinha excede.
- Falha silenciosa em 1 tabela retorna 0 — acompanhar via `inventory_summary.txt`.

## 8. Proximo passo

Fundador executa:

```powershell
# 1. Preflight
python scripts/data_ops_producers/preflight_subida_vinhos.py

# 2. Snapshot audit (se preflight reportou instrucao)
# psql $DATABASE_URL -c "CREATE TABLE audit_wines_pre_subida_20260424 AS SELECT id, ingestion_run_id, created_at FROM wines;"

# 3. Inventario
python scripts/data_ops_producers/inventario_subida_vinhos.py
```

Codex audita `preflight.md` e `inventory.json`.

Se tudo OK: Codex emite prompt `SUBIDA_LOCAL_RENDER_FASE_2_EXECUCAO_SHARDED_20260424`
e Claude Code executa Fase 2 (smoke 50 dry-run -> piloto Tier1 2000 -> producao por shards).

Se FAIL em algum gate de preflight/inventario: Codex emite prompt corretivo na
propria Fase 1.
