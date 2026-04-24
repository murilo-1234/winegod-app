# WINEGOD - EXECUCAO TOTAL - FINALIZACAO COMMERCE DQ V3 (Amazon + Tier1 + Tier2)

Data: 2026-04-23
Branch: `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`
Base: `dd756093` em `data-ops/integracao-restantes-scrapers-total-20260423`
Auditor final: **Codex admin**
Executor: Claude Code (Opus 4.7 1M context)
Prompt: `prompts/PROMPT_CLAUDE_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md`

## 17.1 Veredito

```text
APROVADO_PARCIAL_COM_RESIDUAL_EXTERNO_MINIMO
```

Todos os caminhos tecnicos foram implementados localmente e testados em dry-run. O unico residual e irreduzivel e externo: entregar no diretorio local do repo o(s) artefato(s) JSONL que o PC espelho (Amazon) e os chats Codex (Tier2) devem emitir. Enquanto o artefato nao chega, os exporters retornam `blocked_external_host`/`blocked_contract_missing` de forma honesta — sem fingir apply, sem canal paralelo. Nada do que foi feito rompe o contrato unico: `plug_commerce_dq_v3 -> DQ V3 -> public.wines + public.wine_sources`.

## 17.2 Fontes e papel final

| fonte | papel final | entra pelo DQ V3 | estado final | ordem |
| --- | --- | --- | --- | --- |
| `winegod_admin_world` | feed local ja validado | sim | `observed` (apply escada ja aplicado em sessao anterior) | 1 |
| `vinhos_brasil_legacy` | feed local ja validado | sim | `observed` (apply 50 OK; 200 gated) | 2 |
| `amazon_mirror_primary` | **feed recorrente oficial Amazon** | sim (via artefato JSONL) | `blocked_external_host` enquanto JSONL + summary nao chegam; manifest registra `registry_status: blocked_external_host` explicito; passa a `observed` apenas quando o contrato for cumprido | 3 |
| `amazon_local_legacy_backfill` | backfill historico Amazon, lineage=`legacy_local` | sim | `observed` (smoke com 10 items, 7 valid / 3 not_wine) | 4 |
| `amazon_local` | observer/dry-run, **congelado como feed primario** | sim | `observed` (preservado, nao promover como feed principal) | - |
| `tier1_global` | feed futuro via artefato padronizado | sim (via artefato JSONL) | `blocked_contract_missing` ate artefato + summary chegarem e validarem contrato | 5 |
| `tier2_chat1..5` + `tier2_br` | feeds futuros via artefato padronizado | sim (via artefato JSONL) | `blocked_contract_missing` ate artefato + summary chegarem e validarem contrato | 6 |
| `winegod_admin_legacy_mixed` | salvamento honesto do legado misturado, lineage=`legacy_mixed` | sim | **`blocked_missing_source` por default** (sem allowlist); so vira `observed` quando `LEGACY_MIXED_ALLOWED_FONTES` for declarado explicitamente | - |

## 17.3 O que foi realmente implementado

### Exporters novos (em `sdk/plugs/commerce_dq_v3/exporters.py`)

- `export_amazon_mirror_primary_to_dq` - loader de JSONL padronizado do espelho; hash SHA256 por artefato; lineage=`primary`.
- `export_amazon_local_legacy_backfill_to_dq` - mesma leitura do `amazon_local` mas com `_source_pipeline='amazon_local_legacy_backfill'` e `_source_lineage='legacy_local'`.
- `export_tier1_global_to_dq` - loader de JSONL padronizado Tier1 a partir de `reports/data_ops_artifacts/tier1/`. Sem artefato = `blocked_contract_missing` explicito.
- `export_tier2_from_artifact` - mesma ideia para `tier2_chat1..5` e `tier2_br`, por chat, em `reports/data_ops_artifacts/tier2/<chat>/`.
- `export_winegod_admin_legacy_mixed_to_dq` - salvamento honesto do legado Tier1/Tier2 misturado com `_source_lineage='legacy_mixed'`. **Default: `blocked_missing_source`** porque o schema atual nao tem FK que prove Tier1 vs Tier2 por vinho. So libera items quando a variavel `LEGACY_MIXED_ALLOWED_FONTES=fonte1,fonte2,...` for declarada explicitamente (allowlist). Isso garante que o exporter nao sobrepoe `winegod_admin_world`.
- Stubs antigos (`export_amazon_mirror_to_dq_stub`, `export_tier1_global_to_dq_stub`, `export_tier2_to_dq_stub`) mantidos para compatibilidade com schedulers antigos e como fallback honesto quando o artefato nao existe.

### Runner atualizado (`sdk/plugs/commerce_dq_v3/runner.py`)

- Tier2 agora tenta primeiro consumir artefato padronizado (`export_tier2_from_artifact`); se nao houver artefato, cai no stub `blocked_contract_missing`. Comportamento observavel honesto preservado.

### Contrato de artefato (novo doc)

- `docs/TIER_COMMERCE_CONTRACT.md` define:
  - diretorios padrao por familia;
  - campos minimos por item (13 campos);
  - summary por execucao (`run_id`, `artifact_sha256`, etc);
  - precedencia `mirror_primary > local_legacy_backfill` e `tier_artifact > legacy_mixed`;
  - regras de verificacao antes de apply.

### Manifests novos (3 entradas no registry)

- `sdk/adapters/manifests/commerce_amazon_mirror_primary.yaml` - `registry_status: blocked_external_host` (aguardando JSONL; nao da falso verde)
- `sdk/adapters/manifests/commerce_amazon_local_legacy_backfill.yaml` - `registry_status: observed`
- `sdk/adapters/manifests/commerce_winegod_admin_legacy_mixed.yaml` - `registry_status: observed` no manifest; comportamento default do exporter e `blocked_missing_source` ate allowlist ser declarada

Apos `sync_registry_from_manifests.py --apply`, `ops.scraper_registry` passou de 29 para 32 entradas.

Apos a rodada de hardening e esta correcao minima, status real registrado em `ops.scraper_registry`:

- `commerce_amazon_mirror`: `blocked_external_host`
- `commerce_amazon_mirror_primary`: `blocked_external_host` (aguardando JSONL + summary.json)
- `commerce_amazon_local`: `observed`
- `commerce_amazon_local_legacy_backfill`: `observed`
- `commerce_winegod_admin_legacy_mixed`: `observed` no manifest, mas comportamento por default em runtime e `blocked_missing_source` (sem allowlist)

### Shadow wrappers novos

- `scripts/data_ops_shadow/run_commerce_amazon_mirror_primary_shadow.ps1`
- `scripts/data_ops_shadow/run_commerce_amazon_local_legacy_backfill_shadow.ps1`
- `scripts/data_ops_shadow/run_commerce_winegod_admin_legacy_mixed_shadow.ps1`

### Scheduler dedicado novo

- `scripts/data_ops_scheduler/run_commerce_artifact_dryruns.ps1` roda dry-run de:
  - `amazon_mirror_primary`
  - `tier1_global`
  - `tier2_chat1..5`, `tier2_br`

### Docs atualizados

- `scripts/data_ops_scheduler/README.md` atualizado com novo scheduler + secao "Artefatos padronizados de commerce".

## 17.4 O que foi realmente aplicado na base final

Nada. Esta sessao NAO executou apply produtivo em `public.wines`/`public.wine_sources`.

Delta observado:

- `public.wines`: (nao medido com precisao - timeout 120s; ultima leitura estavel=2512787 da sessao anterior)
- `public.wine_sources`: 3491567 (inalterado por este executor)
- `public.wine_scores`: 530 → 169520 (+168990 por processo paralelo de Murilo rodando `vivino_wines_to_ratings` apply massivo; NAO executado por este executor; assinatura `fonte='vivino'`)
- `public.not_wine_rejections`: 546 (inalterado)
- `public.ingestion_review_queue`: 10 (inalterado)
- `ops.scraper_runs`: 138 → 188 (+50 de smokes + observers refresh desta sessao; nenhum apply commerce)
- `ops.ingestion_batches`: 143 → 193 (+50)
- `ops.scraper_registry`: 29 → 32 (+3 manifests novos: amazon_mirror_primary, amazon_local_legacy_backfill, winegod_admin_legacy_mixed)

## 17.5 Escada de lotes executada

| fonte | dry-run | 50 | 200 | 1000 | 5000 | motivo |
| --- | --- | --- | --- | --- | --- | --- |
| `winegod_admin_world` | - | - | - | - | - | ja aplicado em sessao anterior |
| `vinhos_brasil_legacy` | - | - | - | - | - | apply 50 ja OK; 200 gated (BLOCKED_QUEUE_EXPLOSION) em sessao anterior |
| `amazon_mirror_primary` | limit=20 (`blocked_external_host`) | - | - | - | - | aguardando artefato JSONL do PC espelho |
| `amazon_local_legacy_backfill` | limit=10 (`observed`, 7 valid/3 notwine) | - | - | - | - | nao promovido; so apos espelho operar |
| `amazon_local` | - | - | - | - | - | congelado; observer continua |
| `tier1_global` | limit=20 (`blocked_contract_missing`) | - | - | - | - | aguardando artefato JSONL Tier1 |
| `tier2_chat1..5` + `tier2_br` | limit=20 cada (`blocked_contract_missing`) | - | - | - | - | aguardando artefato JSONL Tier2 |
| `winegod_admin_legacy_mixed` | limit=10 `blocked_missing_source` (default sem allowlist) | - | - | - | - | nao promovido; allowlist opcional via `LEGACY_MIXED_ALLOWED_FONTES` |

Dry-run de cada scheduler novo executado com sucesso:

- `run_commerce_artifact_dryruns.ps1 -Limit 20` -> 8 fontes rodadas sem erro.

## 17.6 Evidencia de seguranca

- Zero novo plug de commerce criado. Canal unico `plug_commerce_dq_v3` preservado.
- Zero escrita direta em `public.wines`/`public.wine_sources` por este executor nesta sessao.
- Zero uso de `import_render_z.py`.
- Zero perda de dado legado por exclusao: `amazon_local` permanece observavel; `winegod_admin_legacy_mixed` criado para salvar Tier1/Tier2 historico sem mentir lineage.
- Zero mistura de origem sem prova: manifests marcam `_source_lineage` como `primary`, `legacy_local` ou `legacy_mixed` explicitamente.
- Zero force push, zero reset, zero merge em main.
- Zero secrets no log; `.env` nao foi commitado.
- Precedencia `mirror_primary > local_legacy_backfill` gravada no contrato `docs/TIER_COMMERCE_CONTRACT.md` e no manifest.
- Registry coerente: 32 entradas; as 3 novas refletem estado honesto no pacote atual (`blocked_external_host` para `amazon_mirror_primary`, `observed` para `amazon_local_legacy_backfill`, `observed` no manifest / `blocked_missing_source` em runtime para `winegod_admin_legacy_mixed`), todas com tags `plug:commerce_dq_v3`.

## 17.7 Metricas de controle

Dry-runs desta sessao (pequenos; sem apply):

| fonte | limit | state | received | valid | filtered_notwine | would_insert | would_update | review_queue |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `amazon_mirror_primary` | 20 | blocked_external_host | 0 | 0 | 0 | 0 | 0 | 0 |
| `tier1_global` | 20 | blocked_contract_missing | 0 | 0 | 0 | 0 | 0 | 0 |
| `tier2_chat1..5`, `tier2_br` | 20 cada | blocked_contract_missing | 0 | 0 | 0 | 0 | 0 | 0 |
| `amazon_local_legacy_backfill` | 10 | observed | 10 | 7 | 3 | - | - | - |
| `winegod_admin_legacy_mixed` | 10 | blocked_missing_source (default sem allowlist) | 0 | 0 | 0 | 0 | 0 | 0 |

Nenhum delta de `orphan_sources` por este executor; nenhuma explosao de `duplicates_in_input` ou `not_wine_rejections`.

## 17.8 O que ficou residual

Residual real e externo:

- PC espelho precisa entregar JSONL em `reports/data_ops_artifacts/amazon_mirror/` (formato: `docs/TIER_COMMERCE_CONTRACT.md`).
- Chats Codex Tier1 precisam entregar JSONL em `reports/data_ops_artifacts/tier1/`.
- Chats Codex Tier2 precisam entregar JSONL em `reports/data_ops_artifacts/tier2/<chat>/`.
- Assim que qualquer um desses artefatos existir, o scheduler `run_commerce_artifact_dryruns.ps1` pega automaticamente o mais recente (`mtime DESC`) e roda dry-run; apply controlado em escada `50->200->1000->5000` pode ser liberado depois da comparacao de overlap entre mirror e local.

Residual bloqueado por politica ja conhecida:

- deploy manual Render (CLAUDE.md R7) - nao disparado.
- PR/merge em main - nao solicitado.
- Gemini pago - nao disparado (CLAUDE.md R6).

## 17.9 Git

- Branch: `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`
- Base: `dd756093` em `data-ops/integracao-restantes-scrapers-total-20260423`
- Commits desta sessao (ordem cronologica):
  - `fcfd866c feat(data-ops): finalize commerce routing for amazon tier1 and tier2`
  - `5b6e3875 docs(data-ops): pin fcfd866c SHA in final commerce report`
  - `c81072dd fix(data-ops): harden commerce artifact contract and legacy routing` - hardening dos 4 findings anteriores do Codex (contrato no codigo + legacy_mixed restrito + manifest blocked + git trail)
  - `85b38c0a docs(data-ops): pin c81072dd SHA in correction docs`
  - `0f75ba37 fix(data-ops): accept null safra/preco per contract and align final report` - correcao minima final: validador aceita `safra=null` e `preco=null` conforme contrato, +5 testes, relatorio principal alinhado ao codigo atual
  - `559d962d docs(data-ops): pin 0f75ba37 SHA in minimal correction docs`
- Push remoto: `origin/data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`
- Diff resumido: 3 manifests novos + 3 shadows novos + 1 scheduler novo + 1 contrato novo + validator novo (artifact_contract.py) + 8 testes novos + exporters/runner atualizados + README atualizado + 2 relatorios + 1 CLAUDE_RESPOSTAS correcao.

## Apendice A - Testes (pacote atual corrigido)

- `python -m pytest sdk/plugs/commerce_dq_v3/tests/test_artifact_contract.py -q` -> **13 passed** (8 do hardening inicial + 5 desta correcao minima cobrindo nullability de `safra`/`preco`)
- `python -m pytest sdk/plugs -q` -> **41 passed** (antes 36 na rodada anterior; +5 novos testes)
- `python -m pytest sdk/tests sdk/adapters/tests -q` -> **119 passed**

Smokes dry-run confirmando comportamento corrigido:

- `winegod_admin_legacy_mixed --dry-run` -> `blocked_missing_source` (allowlist vazia)
- `amazon_mirror_primary --dry-run` -> `blocked_external_host` (sem JSONL + summary)

## Apendice B - Arquivo a repassar para o Codex admin

```text
C:\winegod-app\reports\WINEGOD_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md
```
