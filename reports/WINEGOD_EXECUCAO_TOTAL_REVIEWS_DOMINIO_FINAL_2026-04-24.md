# WINEGOD - Execucao Total Reviews - Dominio Final

Data: 2026-04-24
Branch: `data-ops/execucao-total-reviews-dominio-final-20260424`
Repositorio: `C:\winegod-app`
Auditor esperado: **Codex admin**

## 1. Veredito final

`APROVADO PARA AUDITORIA`

```
dominio_reviews = VIVO + FORTIFICADO + AUDITAVEL
apply_oficial = vivino_wines_to_ratings (inalterado)
fontes_externas = OBSERVED (pausa preservada)
drift = BLOQUEADO_POR_TESTE
```

Tudo que era implementavel localmente nesta fase foi entregue. O canal
Vivino nao foi reescrito; foi observado, endurecido por safety net e
documentado para operacao continua. Nenhuma fonte externa subiu. Nenhum
writer paralelo foi criado.

## 2. Mapa das fontes de reviews e estado final

| Fonte                              | Manifest                                            | Status operacional                                        |
|------------------------------------|-----------------------------------------------------|-----------------------------------------------------------|
| `vivino_wines_to_ratings`          | `sdk/plugs/reviews_scores/manifest.yaml`            | **APPLY OFICIAL** - Task Scheduler S4U (backfill+incremental), last_id 1.941.423 / 35 runs |
| `vivino_reviews_to_scores_reviews` | (per-review, via exporter)                           | staging-only; runner bloqueia apply em wine_scores (per-review source) |
| `reviews_vivino_global`            | `sdk/adapters/manifests/reviews_vivino_global.yaml` | observer READ-ONLY; telemetria `ops.*` sem PII             |
| `reviews_vivino_partition_a/b/c`   | `sdk/adapters/manifests/reviews_vivino_partition_*` | `blocked_contract_missing` / `blocked_external_host` explicitos |
| `reviewers_vivino_global`          | `sdk/adapters/manifests/reviewers_vivino_global.yaml` | observer READ-ONLY; agregados anonimos                    |
| `catalog_vivino_updates`           | `sdk/adapters/manifests/catalog_vivino_updates.yaml` | observer READ-ONLY de identidade/catalogo                 |
| `scores_cellartracker`             | `sdk/adapters/manifests/scores_cellartracker.yaml`  | **PAUSED**: `observed`, sem apply, sem WCF                |
| `critics_decanter_persisted`       | `sdk/adapters/manifests/critics_decanter_persisted.yaml` | **PAUSED**: `observed`, sem apply, sem WCF            |
| `critics_wine_enthusiast`          | `sdk/adapters/manifests/critics_wine_enthusiast.yaml` | **PAUSED**: `observed`, sem apply, sem WCF              |
| `market_winesearcher`              | `sdk/adapters/manifests/market_winesearcher.yaml`   | **PAUSED**: `observed`, sem apply, sem WCF                |

## 3. Apply oficial confirmado

Fluxo canonico (inalterado, auditado na rodada anterior):

```
vivino_db (snapshot local)
  -> export_vivino_wines_to_ratings(mode=backfill_windowed | incremental_recent)
  -> plug.reviews_scores.writer.apply_bundle (atomico por batch, idempotente)
  -> public.wine_scores (UPSERT por (wine_id, fonte))
  -> public.wines.vivino_rating / vivino_reviews (UPDATE guarded IS DISTINCT FROM)
  -> trg_score_recalc
  -> score_recalc_queue
  -> pipeline WCF existente
```

Confirmacoes objetivas do estado atual (health check real):

```json
{
  "status": "ok",
  "state": {
    "last_id": 1941423,
    "runs": 35,
    "updated_at": "2026-04-24T05:17:08.069719Z",
    "mode": "backfill_windowed"
  },
  "backfill_log": { "exit": 0 },
  "incremental_log": { "exit": 0 }
}
```

- `wine_scores_changed` cai para 0 em rerun identico (guard `IS DISTINCT FROM`).
- `wines_rating_updated` reflete apenas mudancas reais.
- UPDATE de `wines` entra no MESMO commit do UPSERT de `wine_scores` (rollback
  por lote testado).

## 4. Disciplina das fontes pausadas (Fase C)

As 4 fontes externas continuam em `registry_status: observed`, sem apply
no Render, sem WCF, sem mistura com base local do Vivino. Um teste
dedicado trava drift silencioso:

- `sdk/plugs/reviews_scores/tests/test_manifests_coverage.py`
  - `test_paused_sources_stay_observed_not_applied`
  - `test_review_manifests_never_declare_commerce_outputs`

Documento operacional novo consolidando disciplina:

- `reports/WINEGOD_REVIEWS_DOMINIO_FONTES_PAUSADAS_DISCIPLINA_2026-04-24.md`

## 5. O que foi corrigido nesta execucao

Nao havia bug. As melhorias foram de endurecimento / observabilidade /
documentacao. Tudo dentro do write scope prioritario do prompt.

### 5.1 Codigo

- `sdk/plugs/reviews_scores/health.py` **[NOVO]**
  Modulo read-only que produz um snapshot auditavel do dominio
  (checkpoint + sentinela + ultimos summaries + ultimos logs do scheduler).
  Classifica em `ok` / `ok_backfill_done` / `warning` / `failed`.
  Exit code `0 | 2 | 3`. Sem side effects de DB.

### 5.2 Wrappers operacionais

- `scripts/data_ops_scheduler/run_vivino_reviews_health_check.ps1` **[NOVO]**
  wrapper .ps1 para o health check, pronto para Task Scheduler e uso
  manual. Resolucao robusta de python (mesmo padrao dos wrappers S4U).

### 5.3 Tests (safety net)

- `sdk/plugs/reviews_scores/tests/test_health.py` **[NOVO]** (6 casos)
  fresh cursor -> `ok`; stale sem sentinela -> `warning`;
  exit !=0 no ultimo run -> `failed`; sentinela presente ->
  `ok_backfill_done`; missing state -> `failed`; render MD contem status.
- `sdk/plugs/reviews_scores/tests/test_manifests_coverage.py` **[NOVO]** (4 casos)
  plug e dono, todos os manifests do dominio usam tag
  `plug:reviews_scores`, fontes pausadas ficam `observed`, nenhum manifest
  do dominio declara `public.wine_sources` em `outputs`.

### 5.4 Documentacao

- `docs/PLUG_REVIEWS_SCORES_CONTRACT.md` **[ATUALIZADO]**
  nova secao `Health check` + lista dos wrappers reais (incluindo
  install/status/health), alinhada ao Task Scheduler S4U.
- `scripts/data_ops_scheduler/README.md` **[ATUALIZADO]**
  lista dos wrappers reais do canal Vivino + health check.
- `reports/WINEGOD_REVIEWS_DOMINIO_RUNBOOK_INDEX_2026-04-24.md` **[NOVO]**
  indice unico de contrato, decisoes, operacao, codigo, adapters,
  staging/state, testes.
- `reports/WINEGOD_REVIEWS_DOMINIO_FONTES_PAUSADAS_DISCIPLINA_2026-04-24.md` **[NOVO]**
  consolida a disciplina operacional das 4 fontes pausadas.

## 6. Comandos / testes / smokes executados

### 6.1 Suite completa

```bash
python -m pytest sdk/plugs/reviews_scores -q
# -> 32 passed em 0.90s

python -m pytest sdk/plugs sdk/tests sdk/adapters/tests -q
# -> 170 passed em 1.87s
```

Baseline anterior: 22 + 147. Agora: 32 (plug) + 170 (SDK). +10 testes novos
(6 health + 4 manifests coverage).

### 6.2 Dry-run smoke do canal Vivino

```bash
python -m sdk.plugs.reviews_scores.runner \
  --source vivino_wines_to_ratings --limit 5 --dry-run
```

Summary gerado:

```
reports/data_ops_plugs_staging/20260424_051955_vivino_wines_to_ratings_summary.md
  mode: incremental_recent
  items: 5
  max_id=6900332
```

### 6.3 Dry-run smoke de fonte pausada (CellarTracker)

```bash
python -m sdk.plugs.reviews_scores.runner \
  --source cellartracker_to_scores_reviews --limit 3 --dry-run
```

Summary gerado com 3 items em staging. Apply (caso testado manualmente)
retorna 100% unmatched porque a fonte nao carrega `vivino_id` - exatamente
a fronteira de seguranca que mantem essas fontes fora do Render nesta fase.

### 6.4 Health check real do dominio

```bash
python -m sdk.plugs.reviews_scores.health --stdout md \
  --write-md reports/WINEGOD_REVIEWS_HEALTH_LATEST.md
```

Status retornado: `ok` (cursor fresco, ultimo backfill exit 0,
ultimo incremental exit 0, sem sentinela de fim - backfill segue
varrendo a base).

## 7. Metricas relevantes observadas no momento da execucao

- Checkpoint atual: `last_id = 1.941.423`, `runs = 35`, modo `backfill_windowed`.
- Ultimo backfill real: 50 `wine_scores_changed` em 10.000 processados;
  `matched = 9.950`, `unmatched = 50`. `batches_committed = 1`.
- Ultimo incremental: 9.943 upserts, 0 changes, 0 updates -
  idempotencia forte confirmada em re-run do topo.
- Nenhum erro acumulado em `errors[]` dos summaries recentes.

## 8. Arquivos alterados / criados

Criados:

- `sdk/plugs/reviews_scores/health.py`
- `sdk/plugs/reviews_scores/tests/test_health.py`
- `sdk/plugs/reviews_scores/tests/test_manifests_coverage.py`
- `scripts/data_ops_scheduler/run_vivino_reviews_health_check.ps1`
- `reports/WINEGOD_REVIEWS_DOMINIO_RUNBOOK_INDEX_2026-04-24.md`
- `reports/WINEGOD_REVIEWS_DOMINIO_FONTES_PAUSADAS_DISCIPLINA_2026-04-24.md`
- `reports/WINEGOD_EXECUCAO_TOTAL_REVIEWS_DOMINIO_FINAL_2026-04-24.md` (este)
- `reports/WINEGOD_REVIEWS_HEALTH_LATEST.md` (saida do health, reexecutavel)
- `CLAUDE_RESPOSTAS_EXECUCAO_TOTAL_REVIEWS_DOMINIO_FINAL_2026-04-24.md` (resposta Codex)

Atualizados:

- `docs/PLUG_REVIEWS_SCORES_CONTRACT.md`
- `scripts/data_ops_scheduler/README.md`

NAO alterados (respeitando scope):

- `sdk/plugs/reviews_scores/runner.py`
- `sdk/plugs/reviews_scores/writer.py`
- `sdk/plugs/reviews_scores/exporters.py`
- `sdk/plugs/reviews_scores/checkpoint.py`
- `sdk/plugs/reviews_scores/confidence.py`
- `sdk/plugs/reviews_scores/schemas.py`
- `sdk/plugs/reviews_scores/manifest.yaml`
- Scripts/wrappers de backfill/incremental/install/status do Task Scheduler
- Nenhum manifest de adapter (dominio reviews nem commerce)
- Nenhum arquivo do dominio commerce_dq_v3

## 9. Residual externo / de produto / de contrato

Residuais reais nesta fase:

1. **Backfill ainda varrendo** a base Vivino (`last_id = 1.941.423` /
   total estimado ~1.72M `public.wines` matched ou mais se considerar
   `vivino_vinhos`). NAO e bug. O proprio contrato descreve que o modo
   `backfill_windowed` avanca uma janela por execucao. Quando a sentinela
   `.BACKFILL_DONE` aparecer, o operador deve rodar
   `install_vivino_reviews_tasks.ps1 -CheckBackfillDone` para desabilitar
   a task e manter so o incremental. Nao exige acao neste commit.

2. **Fontes externas CT/Decanter/WE/WS** continuam em pausa consciente
   por ausencia de uso de produto aprovado. Reabrir esse tema exige
   novo contrato + decisao de produto. Fora do escopo desta execucao.

3. **Branch nao mergeada**: esta execucao criou a branch
   `data-ops/execucao-total-reviews-dominio-final-20260424` a partir do
   estado da branch anterior (`data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`).
   O commit inclui APENAS os arquivos citados em §8 (criados + atualizados).
   Nenhuma outra mudanca pendente do commerce foi arrastada.
   - SHA do commit: `23a6d87d`
   - Push: `origin/data-ops/execucao-total-reviews-dominio-final-20260424`

4. **Deploy Render**: nada neste pacote muda o Render. O canal Vivino roda
   localmente (Task Scheduler S4U no `este_pc`), escrevendo diretamente no
   Postgres do Render via `DATABASE_URL`. O `git push` desta branch nao
   dispara deploy de backend web (regra 7 do CLAUDE.md).

## 10. Criterios do prompt - checklist

- [x] Fase A: estado do dominio reconfirmado (checkpoint fresco, logs exit 0,
  32 testes verdes).
- [x] Fase B: canal Vivino oficial preservado; endurecimento apenas
  observacional (health + manifests coverage); nenhum writer paralelo; nenhum
  review bruto no Render.
- [x] Fase C: disciplina das 4 fontes pausadas explicitada em doc proprio
  (`WINEGOD_REVIEWS_DOMINIO_FONTES_PAUSADAS_DISCIPLINA_2026-04-24.md`);
  drift travado por teste.
- [x] Fase D: scraper Vivino reviews visivel na plataforma central
  (manifest do plug + tags `plug:reviews_scores` em todos os adapters do
  dominio + logs em `reports/data_ops_scheduler/...`).
- [x] Fase E: 170/170 testes SDK verdes; dry-run smoke Vivino 5 items
  OK; dry-run CT 3 items OK; health check real OK.
- [x] Entregaveis: este relatorio + `CLAUDE_RESPOSTAS_*` + runbook index
  + disciplina fontes pausadas. Branch com commit/push.

## 11. Criterio de encerramento

Nesta fase esta encerrado:

- implementacao local relevante: 100% entregue;
- canal Vivino: preservado e fortalecido;
- fontes externas pausadas: semanticamente limpas, com teste de drift;
- codigo + docs + scheduler + manifests: coerentes entre si;
- branch: commit + push;
- auditoria Codex admin: pacote consolidado neste arquivo.

---

Arquivo a repassar para o Codex admin:

```
C:\winegod-app\reports\WINEGOD_EXECUCAO_TOTAL_REVIEWS_DOMINIO_FINAL_2026-04-24.md
```
