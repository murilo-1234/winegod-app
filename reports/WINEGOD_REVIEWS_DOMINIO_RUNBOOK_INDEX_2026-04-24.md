# WINEGOD - Reviews - Runbook Index

Data: 2026-04-24
Tipo: indice de navegacao do dominio reviews
Status: ATIVO

## 1. Objetivo

Indice unico de todos os artefatos operacionais e decisorios do dominio
`reviews` hoje. Serve para que qualquer job futuro acesse rapidamente o
estado, o contrato, a rotina e as decisoes sem caca ao tesouro no repo.

## 2. Contrato e escopo

- [docs/PLUG_REVIEWS_SCORES_CONTRACT.md](../docs/PLUG_REVIEWS_SCORES_CONTRACT.md)
  contrato oficial do `plug_reviews_scores` (fonte canonica,
  idempotencia, atomicidade, modos, health check)
- [reports/WINEGOD_PLUG_REVIEWS_SCORES_AUDITORIA_FINAL_2026-04-23.md](WINEGOD_PLUG_REVIEWS_SCORES_AUDITORIA_FINAL_2026-04-23.md)
  matriz PASS/FAIL dos 4 criterios Codex (idempotencia, atomicidade,
  progresso de backfill, regra de confianca compartilhada)
- [reports/WINEGOD_VIVINO_REVIEWS_HANDOFF_FINAL_OPERACIONAL_2026-04-23.md](WINEGOD_VIVINO_REVIEWS_HANDOFF_FINAL_OPERACIONAL_2026-04-23.md)
  handoff final da implementacao do canal Vivino

## 3. Decisoes da fase atual

- [reports/WINEGOD_SINAIS_EXTERNOS_CT_DEC_WE_WS_HANDOFF_DECISAO_2026-04-23.md](WINEGOD_SINAIS_EXTERNOS_CT_DEC_WE_WS_HANDOFF_DECISAO_2026-04-23.md)
  decisao oficial de pausar CT / Decanter / WE / WS nesta fase
- [reports/WINEGOD_SINAIS_EXTERNOS_CT_DEC_WE_WS_ANALISE.md](WINEGOD_SINAIS_EXTERNOS_CT_DEC_WE_WS_ANALISE.md)
  inventario tecnico das 4 fontes externas
- [reports/WINEGOD_REVIEWS_DOMINIO_FONTES_PAUSADAS_DISCIPLINA_2026-04-24.md](WINEGOD_REVIEWS_DOMINIO_FONTES_PAUSADAS_DISCIPLINA_2026-04-24.md)
  disciplina operacional das fontes pausadas (o que esta travado e por que)

## 4. Operacao - tasks e wrappers

Wrappers instalaveis no Windows Task Scheduler:

- `scripts/data_ops_scheduler/install_vivino_reviews_tasks.ps1`
  instalador oficial (S4U, nao interativo; fallback InteractiveToken
  documentado)
- `scripts/data_ops_scheduler/run_vivino_reviews_backfill.ps1`
  backfill progressivo (cursor persistente por `id ASC`) -
  cadencia default: 15 min
- `scripts/data_ops_scheduler/run_vivino_reviews_incremental.ps1`
  sync incremental (topo recente por `atualizado_em DESC`) -
  cadencia default: 60 min
- `scripts/data_ops_scheduler/status_vivino_reviews_tasks.ps1`
  inspecao dos LastTaskResult + NextRun + checkpoint atual
- `scripts/data_ops_scheduler/run_vivino_reviews_health_check.ps1`
  snapshot read-only do dominio (state + summary + logs + status
  classificado)

Wrapper generico do plug (uso local/manual):

- `scripts/data_ops_scheduler/run_plug_reviews_scores_apply.ps1`
  entry point para `incremental_recent` ou `backfill_windowed`
- `scripts/data_ops_scheduler/run_reviews_scores_dryruns.ps1`
  dry-run das fontes nao-Vivino para manter staging fresco
- `scripts/data_ops_scheduler/run_all_plug_dryruns.ps1`
  dry-run global cobrindo commerce + reviews + discovery + enrichment

## 5. Codigo do plug

- `sdk/plugs/reviews_scores/runner.py` - ponto de entrada CLI
- `sdk/plugs/reviews_scores/writer.py` - UPSERT atomico por batch,
  idempotencia forte, rollback por batch
- `sdk/plugs/reviews_scores/exporters.py` - leitura das fontes (vivino
  canonico aplica; demais sao dry-run)
- `sdk/plugs/reviews_scores/checkpoint.py` - estado persistente em
  `reports/data_ops_plugs_state/<source>.json`
- `sdk/plugs/reviews_scores/confidence.py` - wrapper fino que importa
  `scripts/wcf_confidence.py::confianca` (fonte unica)
- `sdk/plugs/reviews_scores/schemas.py` - mapas de fonte / sinal /
  responsabilidade de apply
- `sdk/plugs/reviews_scores/health.py` - health check observacional
  (read-only)
- `sdk/plugs/reviews_scores/manifest.yaml` - manifest do plug no painel

## 6. Adapters observers - dominio reviews

Adapters read-only que alimentam a plataforma central com telemetria:

- `sdk/adapters/catalog_vivino_updates_observer.py`
- `sdk/adapters/reviewers_vivino_observer.py`
- `sdk/adapters/vivino_reviews_observer.py`
- `sdk/adapters/cellartracker_observer.py`
- `sdk/adapters/decanter_persisted_observer.py`
- `sdk/adapters/wine_enthusiast_observer.py`
- `sdk/adapters/winesearcher_observer.py`

Manifests correspondentes em `sdk/adapters/manifests/*.yaml` com `family`
entre {`review`, `community_rating`, `critic`, `market`, `catalog_identity`,
`reviewer`} e tag `plug:reviews_scores`.

## 7. Staging e state

- `reports/data_ops_plugs_staging/` - JSONL + summary Markdown por run
  (gerado a cada execucao do runner)
- `reports/data_ops_plugs_state/vivino_wines_to_ratings.json` - cursor
  persistente do backfill
- `reports/data_ops_plugs_state/vivino_wines_to_ratings.BACKFILL_DONE` -
  sentinela gravada pelo wrapper quando `items=0` no ultimo run
- `reports/data_ops_scheduler/vivino_reviews_backfill/*.log` - log das
  rodadas do Task Scheduler (backfill)
- `reports/data_ops_scheduler/vivino_reviews_incremental/*.log` - idem
  (incremental)

## 8. Testes

Local: `C:\winegod-app\sdk\plugs\reviews_scores\tests\`

- `test_runner.py` - contrato dos exporters + backfill_windowed
  rejeitado para fontes nao-Vivino + confianca compartilhada
- `test_writer.py` - idempotencia forte, atomicidade por lote (commit
  apos ambos os execute_values, rollback no update falho), guard
  textual do SQL
- `test_health.py` - classificacao ok / warning / failed / sentinela
- `test_manifests_coverage.py` - safety net: plug_reviews_scores existe
  como dono, todos os manifests linkam via tag, fontes pausadas ficam
  observed, ninguem aponta para wine_sources

Global: `python -m pytest sdk/plugs sdk/tests sdk/adapters/tests -q`

## 9. Como interpretar o estado hoje

Comando:

```powershell
.\scripts\data_ops_scheduler\run_vivino_reviews_health_check.ps1 -Format md
```

Saida esperada na fase normal:

- status `ok` enquanto o backfill progride com cursor atualizado;
- status `ok_backfill_done` quando a sentinela `.BACKFILL_DONE`
  aparecer e o operador rodar `install_vivino_reviews_tasks.ps1
  -CheckBackfillDone` para desabilitar a task;
- status `warning` se o cursor ficar mais de 3h sem atualizar sem
  sentinela (ajustavel via `-StallHours`);
- status `failed` se o ultimo run do scheduler saiu com exit code !=0
  ou se a ultima apply reportou erros.

## 10. Veredito do indice

```
dominio_reviews = CONTRATO_TRAVADO + APPLY_VIVA + FONTES_EXTERNAS_PAUSADAS
plataforma_central = NAO_PRECISA_CONHECER_SEGUNDO_CAMINHO
proxima_revisao = SO_APOS_NOVO_OBJETIVO_DE_PRODUTO
```
