# Runbook operacional - Commerce (DQ V3)

Objetivo: operar recorrentemente o commerce sem reabrir arquitetura nem
criar canal paralelo. Canal unico: `plug_commerce_dq_v3 -> DQ V3 ->
public.wines + public.wine_sources`.

## 1. Fontes canonicas

| Fonte | Papel | Estado esperado |
|---|---|---|
| `winegod_admin_world` | feed local observed (winegod_db) | observed |
| `vinhos_brasil_legacy` | feed local observed (vinhos_brasil_db) | observed |
| `amazon_mirror_primary` | feed Amazon oficial (PC espelho -> JSONL) | observed / blocked_external_host |
| `amazon_local_legacy_backfill` | backfill controlado do historico Amazon | observed (lotes controlados) |
| `amazon_local` | observer legado (diagnostico, nao feed principal) | observed |
| `tier1_global` | Tier1 APIs/sitemap via artefato | observed |
| `tier2_global_artifact` | Tier2 UNICO global via artefato | observed |
| `tier2_br` | Tier2 Brasil por filtro real de pais | observed |
| `winegod_admin_legacy_mixed` | historico Tier1/Tier2 misturado, allowlist | blocked_missing_source (por default) |
| `tier2_chat1..5` | DEPRECATED (colapsados em tier2_global_artifact) | blocked_contract_missing (historico) |

Stub legado preservado: `amazon_mirror` (substituido por `amazon_mirror_primary`).

## 2. Cadencia recorrente

### 2.1 Producao de artefatos (semanal)

```powershell
# Tier1 - APIs/sitemap/HTTP deterministico
python scripts\data_ops_producers\build_commerce_artifact.py `
  --pipeline-family tier1 `
  --source-label tier1_global `
  --output-dir reports\data_ops_artifacts\tier1 `
  --tier-filter api_shopify,api_woocommerce,api_vtex,sitemap_html,sitemap_jsonld `
  --limit 2000

# Tier2 global - Playwright + IA
python scripts\data_ops_producers\build_commerce_artifact.py `
  --pipeline-family tier2 `
  --source-label tier2_global_artifact `
  --output-dir reports\data_ops_artifacts\tier2_global `
  --tier-filter playwright_ia `
  --limit 2000

# Tier2 BR - Playwright + IA + filtro pais
python scripts\data_ops_producers\build_commerce_artifact.py `
  --pipeline-family tier2 `
  --source-label tier2_br `
  --output-dir reports\data_ops_artifacts\tier2\br `
  --tier-filter playwright_ia `
  --pais-codigo br `
  --limit 500
```

### 2.2 Dry-run canonico (diario)

```powershell
# Fontes por artefato (inclui amazon_mirror_primary - blocked ate JSONL chegar)
powershell -File scripts\data_ops_scheduler\run_commerce_artifact_dryruns.ps1

# Fontes locais sem artefato (winegod_admin_world / vinhos_brasil_legacy / amazon_local)
powershell -File scripts\data_ops_scheduler\run_commerce_dryruns.ps1
```

### 2.3 Apply em escada (manual)

Sempre passar por todos os degraus:

```text
dry-run -> apply 50 -> apply 200 -> apply 1000 -> lotes maiores se metricas OK
```

```powershell
python -m sdk.plugs.commerce_dq_v3.runner --source <fonte> --limit 50 --apply
python -m sdk.plugs.commerce_dq_v3.runner --source <fonte> --limit 200 --apply
python -m sdk.plugs.commerce_dq_v3.runner --source <fonte> --limit 1000 --apply
```

Parar a escada se qualquer gate abaixo piorar claramente.

## 3. Gates e metricas

Metricas observadas a cada apply:

- `received` / `valid` / `filtered_notwine`
- `inserted` / `updated` (em `public.wines`)
- `sources_inserted` / `sources_updated` (em `public.wine_sources`)
- `enqueue_review` (cap <5% do valid; acima disso gate `BLOCKED_QUEUE_EXPLOSION` dispara)
- `errors`
- lineage: `run_id` + `source` + `state`

Gates de parada (recuo obrigatorio):

1. `enqueue_review > 5% * valid` em qualquer degrau -> parar, investigar queue.
2. `not_wine_rejections` subindo mais de 2x o baseline da fonte -> parar.
3. `errors > 0` sem padrao claro -> parar.
4. `sources_inserted` 0 em fonte que historicamente gerava sources -> investigar `public.stores`.

## 4. Residual externo Amazon

Ponto de entrega: `reports/data_ops_artifacts/amazon_mirror/`.

O operador do PC espelho deposita:

- `<YYYYMMDD_HHMMSS>_<run_id>.jsonl`
- `<YYYYMMDD_HHMMSS>_<run_id>_summary.json`

Contrato completo + checklist em
`reports/data_ops_artifacts/amazon_mirror/README.md`.

Validacao local em modo FULL (default; le o JSONL inteiro + confere
`summary.items_emitted` contra as linhas reais; nao escreve no banco):

```powershell
python scripts\data_ops_producers\validate_commerce_artifact.py `
  --artifact-dir reports\data_ops_artifacts\amazon_mirror `
  --expected-family amazon_mirror_primary
```

Smoke rapido com janela (opcional, nao substitui o full):

```powershell
python scripts\data_ops_producers\validate_commerce_artifact.py `
  --artifact-dir reports\data_ops_artifacts\amazon_mirror `
  --expected-family amazon_mirror_primary `
  --window 50
```

Sem JSONL: `amazon_mirror_primary` continua `blocked_external_host` honesto.
Nao tentar substituir a fonte primaria com `amazon_local`; este ultimo
segue congelado como legado/observer.

## 5. Criterios de promocao por lote

Um lote so promove para o proximo degrau se:

- zero `enqueue_review` abaixo do cap;
- zero crescimento anormal de `not_wine_rejections`;
- zero `errors`;
- lineage `run_id` unico (nao re-aplicar mesmo artefato).

Se qualquer criterio falhar, parar. Investigar. Corrigir na origem ou
retirar o lote. Nao promover.

## 6. Criterios de recuo/bloqueio

Recuo imediato se:

- `BLOCKED_QUEUE_EXPLOSION` disparado.
- crescimento anormal de `not_wine` (>2x baseline).
- duplicatas internas explodindo (>20% do valid).
- dominios `unresolved` crescendo sem match em `public.stores`.

Bloqueio permanente (mover manifest para `blocked_*`):

- artefato invalido persistente (contrato quebra em 2+ rodadas).
- fonte que mistura familias sem prova de lineage.
- criacao de canal paralelo (zero tolerancia).

## 7. Monitoramento continuo

Ordem de checagem recomendada (diario ou por rodada):

1. Logs do scheduler: `reports/data_ops_scheduler/*.log`.
2. Dashboard / observers: `scripts/data_ops_scheduler/run_all_observers.ps1`.
3. `ops.scraper_runs` + `ops.ingestion_batches` (telemetria).
4. `public.ingestion_review_queue` (cap de 5%).
5. `public.not_wine_rejections` (baseline por fonte).

## 8. Testes automatizados

Pacote consolidado:

```powershell
python -m pytest sdk\plugs scripts\data_ops_producers\tests -q
python -m pytest sdk\tests sdk\adapters\tests -q
```

Esperado: 0 falhas, 0 regressao. Se algum teste quebrar, parar e
investigar antes de qualquer apply novo.

## 9. O que NAO fazer

- nao criar writer paralelo de commerce.
- nao criar outro plug de subida de lojas fora do DQ V3.
- nao misturar discovery ou enrichment no fluxo commerce.
- nao usar `amazon_local` como feed primario novo.
- nao reabrir `tier2_chat1..5` sem particao disjunta comprovavel.
- nao escrever direto em `public.wines` / `public.wine_sources`.
- nao reutilizar `run_id` entre execucoes.

## 10. Contatos e referencias

- Contrato de artefato: `docs/TIER_COMMERCE_CONTRACT.md`
- Handoff DQ V3 (fonte de verdade historica): `reports/WINEGOD_DQ_V3_HANDOFF_FINAL_ENCERRAMENTO_C10_2026-04-22.md`
- Go-live 2026-04-23/24: `reports/WINEGOD_GO_LIVE_COMMERCE_RESIDUAL_EXTERNO_E_ARTIFACTS_2026-04-23.md`
- Plano mestre final: `reports/WINEGOD_CODEX_PLANO_MESTRE_FINAL_TOTAL_2026-04-24.md`
- README operador PC espelho: `reports/data_ops_artifacts/amazon_mirror/README.md`
