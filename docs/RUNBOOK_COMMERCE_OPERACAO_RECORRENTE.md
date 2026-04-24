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
- Scraper inventory (Fase A da rodada 2026-04-24): `reports/WINEGOD_COMMERCE_SCRAPER_INVENTORY_2026-04-24.md`

## 11. Exporters locais (artifact_exporters)

Cada exporter le `winegod_db` em modo read-only e gera JSONL +
`<prefix>_summary.json` no diretorio destino. Sem exception, nao
escreve em `winegod_db` nem em producao.

| exporter | modulo | CLI | output |
|---|---|---|---|
| Amazon legacy (one-time backfill) | `sdk/plugs/commerce_dq_v3/artifact_exporters/amazon_legacy.py` | `scripts/data_ops_producers/export_amazon_legacy.py` | `reports/data_ops_artifacts/amazon_local_legacy_backfill/` |
| Amazon mirror primary | `sdk/plugs/commerce_dq_v3/artifact_exporters/amazon_mirror.py` | `scripts/data_ops_producers/export_amazon_mirror.py` | `reports/data_ops_artifacts/amazon_mirror/` |
| Tier1 global | `sdk/plugs/commerce_dq_v3/artifact_exporters/tier1_global.py` | `scripts/data_ops_producers/export_tier1_global.py` | `reports/data_ops_artifacts/tier1/` |
| Tier2 global | `sdk/plugs/commerce_dq_v3/artifact_exporters/tier2_global.py` | `scripts/data_ops_producers/export_tier2_global.py` | `reports/data_ops_artifacts/tier2_global/` |
| Tier2 BR | `sdk/plugs/commerce_dq_v3/artifact_exporters/tier2_br.py` | `scripts/data_ops_producers/export_tier2_br.py` | `reports/data_ops_artifacts/tier2/br/` |

Cada exporter respeita REGRA 5 (batches de 10.000 linhas). Amazon
mirror suporta modo incremental via state em
`reports/data_ops_export_state/amazon_mirror.json`.

## 12. Fluxos de operacao por exporter

### 12.1 Amazon mirror primary (diario)

1. PC espelho grava no `winegod_db` local (scraper ativo).
2. `backup_diario.bat` as 04:00 faz `pg_dump` + rclone pra
   `gdrive:winegod-backups/`.
3. Neste host (winegod-app), rodar exporter:
   ```powershell
   python scripts\data_ops_producers\export_amazon_mirror.py --mode incremental --max-items 50000
   ```
   (Ou `--mode full` no primeiro run, sem state.)
4. Validar:
   ```powershell
   python scripts\data_ops_producers\validate_commerce_artifact.py `
     --artifact-dir reports\data_ops_artifacts\amazon_mirror `
     --expected-family amazon_mirror_primary
   ```
5. Se OK, apply em escada via
   `scripts\data_ops_scheduler\run_commerce_apply_amazon_mirror.ps1`
   (exige env `COMMERCE_APPLY_AUTHORIZED_AMAZON_MIRROR=1`).

### 12.2 Amazon legacy backfill (one-time)

1. Confirmar que amazon_mirror primary ja esta operacional.
2. Exporter:
   ```powershell
   python scripts\data_ops_producers\export_amazon_legacy.py --max-items 50000
   ```
3. Validar (mesmo CLI, `--expected-family amazon_local_legacy_backfill`).
4. Apply em escada (gated por `COMMERCE_APPLY_AUTHORIZED_AMAZON_LEGACY=1`).
5. Apos sucesso, state `amazon_legacy_backfill_done.json` impede
   re-execucao.

### 12.3 Tier1 / Tier2 global / Tier2 BR (semanal)

Quando o scraper Codex Tier1/Tier2 voltar a rodar (pos-lancamento):

1. Scraper Codex grava em `winegod_db`.
2. Exporters correspondentes:
   ```powershell
   python scripts\data_ops_producers\export_tier1_global.py --max-items 50000
   python scripts\data_ops_producers\export_tier2_global.py --max-items 50000
   python scripts\data_ops_producers\export_tier2_br.py --max-items 10000
   ```
3. Validar cada um com `validate_commerce_artifact.py`.
4. Apply em escada via wrappers gated.

Enquanto scraper nao rodar, exporters retornam
`reason=no_producer_<familia>` (exit=2) - comportamento esperado,
nao e erro.

## 13. Rollback / incidentes

### 13.1 Identificacao de apply ruim

- checar `ingestion_review_queue` > 5% do valid no `plug_commerce_dq_v3`:
  BLOCKED_QUEUE_EXPLOSION ativo; parar escada imediatamente.
- comparar `not_wine_rejections` antes/depois do apply: crescimento > 2x
  o baseline = revisar artefato.
- se runner retornou `errors > 0` persistentes, quarantena.

### 13.2 Quarentenar `run_id`

Um `run_id` quarentenado NAO deve ser reaplicado. Passos:

1. Renomear o artefato de `<prefix>.jsonl` para
   `<prefix>.jsonl.quarantined` (mantem historico auditavel).
2. Renomear summary equivalente.
3. Adicionar nota em
   `reports/data_ops_export_state/<exporter>.json` com
   `last_run_id_quarantined=<run_id>` e `reason=<motivo>`.
4. Proximo run do exporter incremental comeca de novo a partir do
   `last_captured_at` anterior ao run quarentenado (state fica
   inalterado se o run falhou antes de `save_state`).

### 13.3 Reverter efeitos no Render

Canal unico exige reverter via DQ V3 (nao por SQL direto). Se
necessario:

1. identificar `ingestion_run_id` pelo `plug_commerce_dq_v3` log.
2. usar rotina de rollback do DQ V3 (ver handoff
   `reports/WINEGOD_DQ_V3_HANDOFF_FINAL_ENCERRAMENTO_C10_2026-04-22.md`).
3. reverter em batches (10.000 linhas por vez, REGRA 5).
4. confirmar `wines` + `wine_sources` saneados antes de re-aplicar.

## 14. Thresholds de alerta

| Metrica | Warning | Failed |
|---|---|---|
| `ingestion_review_queue` / valid | > 3% | > 5% (BLOCKED_QUEUE_EXPLOSION) |
| `not_wine_rejections` (novo batch) | 1.5x baseline | 2x baseline |
| `errors` por batch | >= 1 | >= 3 |
| `unresolved_domains` no bundle | 10% do valid | 25% |
| tamanho `reports/data_ops_artifacts/` | > 2 GB | > 5 GB |
| exporter state `last_run` age | > 72h (warning p/ mirror) | > 7 dias (mirror) |

Disk e age sao observadas por `sdk/plugs/commerce_dq_v3/health.py`.

## 15. Incident response

Se validator FULL reprovar em producao semanal Tier1/Tier2:

1. NAO promover nenhum apply.
2. Notas do validator apontam falha exata. Categorias:
   - `summary_sha256_nao_confere` -> regerar artefato (producer travou);
   - `items_emitted_mismatch` -> summary foi escrito pre-dedup ou fora
     de sync; regerar summary ou o artefato inteiro;
   - `pipeline_family` divergente -> exporter chamou com family errado.
3. Se necessario, desabilitar temporariamente o wrapper de apply
   removendo env `COMMERCE_APPLY_AUTHORIZED_<FAMILIA>`.
4. Reexecutar exporter + validator. Apply so apos FULL ok.

## 16. Dependencias externas

- `WINEGOD_DATABASE_URL` (env, aponta para `postgresql://.../winegod_db`)
  - sem ela, todos os exporters retornam `reason=dsn_missing:...`.
- PC espelho (pc_espelho): roda o scraper Amazon principal; entrega
  `winegod_db` via dump rclone em `gdrive:winegod-backups/`.
- rclone configurado em `C:\natura-automation\` para sync gdrive.
- Postgres local (PostgreSQL 16+) para restaurar dump se necessario.
- Repo `winegod-app` (este) com `python -m pytest` + validator CLI.

Se o dump estiver disponivel mas nao foi restaurado, Criar banco
temporario `winegod_db_snapshot` e apontar `WINEGOD_DATABASE_URL` pra
ele antes dos exporters rodarem. Nao sobrescrever o `winegod_db` vivo.

## 17. Retencao + rotacao

Regras (ver `sdk/plugs/commerce_dq_v3/retention.py` +
`scripts/data_ops_producers/rotate_commerce_artifacts.py`):

- JSONL em `reports/data_ops_artifacts/*/`: manter ultimos 30 dias
  ou 10 arquivos (o que for menor).
- Summaries: mesmo tratamento.
- Arquivos com > 7 dias: comprimir (gzip) antes de deletar.
- Rotation roda em `--plan-only` por default; `--apply` exige env
  `COMMERCE_ROTATION_AUTHORIZED=1`.

Disk monitor (health):

- > 2 GB: warning.
- > 5 GB: failed.

## 18. Health recorrente

Wrapper:

```powershell
powershell -File scripts\data_ops_scheduler\run_commerce_health_check.ps1
```

Exit:

- 0 = ok (todos observed, disk < 2 GB, exporters recentes).
- 2 = warning (artefato velho, fonte sem JSONL, disk 2-5 GB).
- 3 = failed (contrato invalido, disk > 5 GB).

Snapshot em `reports/WINEGOD_COMMERCE_HEALTH_LATEST.md` (atualizado
por `--write-md`).
