# WINEGOD - GO-LIVE COMMERCE + RESIDUAL EXTERNO + ARTIFACTS

Data: 2026-04-23 (continuado 2026-04-24 UTC)
Branch: `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`
Base: `54698a08` em `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`
Auditor final: **Codex admin**
Executor: Claude Code (Opus 4.7 1M context)
Prompt: `prompts/PROMPT_CLAUDE_EXECUCAO_TOTAL_RESIDUAL_EXTERNO_E_GO_LIVE_COMMERCE_2026-04-23.md`

## 1. Veredito final

```text
APROVADO_COM_GO_LIVE_LOCAL_ESCADA_E_RESIDUAL_EXTERNO_ISOLADO_COM_HARDENING
```

Atualizado em 2026-04-24 apos rodada corretiva dos 4 findings do Codex admin:

- **Tier2 colapsado**: `tier2_chat1..5` nao tinham particao disjunta reproduzivel - foram colapsados em um unico `tier2_global_artifact` + `tier2_br` (mantido separado porque tem filtro real por pais). Os 5 manifests dos chats permanecem registrados mas com `status_reason` explicito de colapso e deprecated.
- **Matching endurecido**: producer agora usa `normalize_host` + `_host_eligible` com boundary real. Aceita igualdade exata ou subdominio legitimo (`shop.amazon.com.br`). Rejeita falso positivo `mazon.com.br` vs `amazon.com.br` ou `malamazon.com.br` vs `amazon.com.br`. 12 testes novos em `scripts/data_ops_producers/tests/test_host_matching.py`.
- **Manifests alinhados**: `commerce_tier1_global`, `commerce_tier2_br` e `commerce_tier2_global_artifact` agora `registry_status: observed` com `status_reason` apontando para o diretorio do artefato. `tier2_chat1..5` permanecem `blocked_contract_missing` honesto.
- **Trilha Git atualizada** abaixo com SHAs reais desta rodada corretiva.

Todos os producers locais que podiam ser automatizados foram implementados e estao emitindo artefato padronizado que o validador aceita. As fontes com contrato cumprido saltaram de `blocked_*` para `observed` e passaram pela escada de apply controlado. O unico residual real e externo (PC espelho Amazon nao acessivel neste ambiente) permanece isolado e honesto: continua `blocked_external_host` enquanto o operador do PC espelho nao deposita JSONL + summary no diretorio local ja pronto para consumir.

## 2. Status por fonte (final)

| fonte | papel | estado final | entrada | apply nesta sessao |
| --- | --- | --- | --- | --- |
| `winegod_admin_world` | feed local | `observed` | exporter legacy `winegod_db` | nao reaplicado (ja gated 1000 em sessoes anteriores) |
| `vinhos_brasil_legacy` | feed local | `observed` | exporter legacy vinhos_brasil_db | nao reaplicado (gated 200 por BLOCKED_QUEUE_EXPLOSION) |
| `amazon_mirror_primary` | feed primario Amazon | `blocked_external_host` | artefato `reports/data_ops_artifacts/amazon_mirror/*.jsonl` (aguardando PC espelho) | residual externo |
| `amazon_local_legacy_backfill` | backfill historico Amazon | `observed` | exporter legacy + lineage=legacy_local | **escada 50/200/1000 COMPLETA** |
| `amazon_local` | observer/dryrun | `observed` | exporter legacy | congelado (nao promover como feed primario) |
| `tier1_global` | feed tier1 | `observed` | artefato `reports/data_ops_artifacts/tier1/*.jsonl` | **escada 50/200/500 COMPLETA** |
| `tier2_chat1..5` | DEPRECATED (sem particao disjunta real) | `blocked_contract_missing` | nenhum artefato consumido | colapsados em tier2_global_artifact |
| `tier2_global_artifact` | feed unico tier2 global | `observed` | artefato `reports/data_ops_artifacts/tier2_global/*.jsonl` | **apply 50 OK (dominio duro)**: 28 inserted + 16 updated + 6 notwine |
| `tier2_br` | feed tier2 (BR por filtro de pais real) | `observed` | artefato `reports/data_ops_artifacts/tier2/br/*.jsonl` | apply 50 OK (sessao anterior) |
| `winegod_admin_legacy_mixed` | salvamento legado Tier1/Tier2 misturado | `blocked_missing_source` | exige allowlist `LEGACY_MIXED_ALLOWED_FONTES` | nao executado |

## 3. O que passou a produzir artefato real nesta sessao

### Producer local novo

- `scripts/data_ops_producers/build_commerce_artifact.py`
  - Producer parametrizado: `--pipeline-family`, `--source-label`, `--output-dir`, `--tier-filter`, `--pais-codigo`, `--limit`.
  - **Evidencia tecnica de tier real**: cruza `lojas_scraping.metodo_recomendado` (`api_shopify`/`api_woocommerce`/`api_vtex`/`sitemap_*` vs `playwright_ia`) com `vinhos_{pais}_fontes.url_original`. Alinha com `scraper_tier1.py` (APIs/sitemap) vs `scraper_tier2.py` (Playwright+IA).
  - **Matching por host endurecido**: `normalize_host` + `_host_eligible` Python-side aceitam igualdade exata ou subdominio legitimo (`shop.amazon.com.br` bate com `amazon.com.br`) e rejeitam falso positivo `mazon.com.br` vs `amazon.com.br`. 12 testes em `scripts/data_ops_producers/tests/test_host_matching.py`.
  - Grava JSONL + `<prefix>_summary.json` no contrato `docs/TIER_COMMERCE_CONTRACT.md`.
  - Filtra automaticamente items com `nome`/`produtor`/`store_domain` vazios (respeita obrigatoriedade do contrato).

### Artefatos canonicos atuais (todos com `contract=ok` no validator)

- `reports/data_ops_artifacts/tier1/*.jsonl` + `*_summary.json` - Tier1 global (APIs/sitemap)
- `reports/data_ops_artifacts/tier2/br/*.jsonl` + `*_summary.json` - Tier2 Brasil (playwright_ia + pais=br)
- `reports/data_ops_artifacts/tier2_global/*.jsonl` + `*_summary.json` - Tier2 global (feed unico que substituiu os extintos `tier2_chat1..5`)
- `reports/data_ops_artifacts/amazon_mirror/` (vazio; aguardando JSONL do PC espelho)

**Diretorios antigos removidos** nesta rodada corretiva: `reports/data_ops_artifacts/tier2/chat1..5/` nao existem mais (colapsados em `tier2_global`).

## 4. O que ainda ficou externo (residual real e isolado)

- `amazon_mirror_primary`: precisa que o operador do PC espelho deposite JSONL + summary em `reports/data_ops_artifacts/amazon_mirror/` no contrato (ver `docs/TIER_COMMERCE_CONTRACT.md`). Assim que aparecer, o scheduler `run_commerce_artifact_dryruns.ps1` consome automaticamente o mais recente.

Nao ha outro residual externo. Todos os Tier1 e Tier2 passaram a produzir artefato local valido.

## 5. Dry-runs executados

Todos os dry-runs das fontes canonicas com artefato retornaram `state=observed`:

- `tier1_global` -> observed (com matching por host endurecido)
- `tier2_br` -> observed
- `tier2_global_artifact` (novo feed unico Tier2) -> observed
- `amazon_local_legacy_backfill` dry-runs 50/200/1000 -> observed em cada degrau
- `amazon_mirror_primary` -> `blocked_external_host` honesto (sem JSONL do PC espelho)

`tier2_chat1..5` NAO sao mais executados: foram colapsados em `tier2_global_artifact` por nao terem particao disjunta reproduzivel. Permanecem no registry apenas como historico `blocked_contract_missing` deprecated.

## 6. Applies executados (escada controlada)

### `amazon_local_legacy_backfill`

| step | received | valid | filtered_notwine | inserted | updated | sources_inserted | sources_updated | enqueue_review | errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 50 | 40 | 10 | 0 | 40 | 0 | 16 | 0 | 0 |
| 200 | 200 | 159 | 40 | 0 | 159 | 0 | 78 | 0 | 0 |
| 1000 | 343 | 272 | 68 | 0 | 272 | 0 | 132 | 0 | 0 |

Todos `inserted=0` porque sao linhas ja existentes em `public.wines` (backfill de lineage), so atualiza com marcador legacy_local. Escada completa sem gate disparado.

### `tier1_global`

| step | received | valid | filtered_notwine | inserted | updated | sources_inserted | sources_updated | enqueue_review | errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 50 | 35 | 15 | 35 | 0 | 35 | 0 | 0 | 0 |
| 200 | 200 | 154 | 19 | 118 | 36 | 65 | 35 | 0 | 0 |
| 500 | 500 | 386 | 49 | 217 | 169 | 8 | 113 | 0 | 0 |

Escada 50 -> 200 -> 500 completa. Zero enqueue_review em todos os degraus (gate abaixo de 5% cap).

### `tier2_br`

| step | received | valid | filtered_notwine | inserted | updated | sources_inserted | sources_updated | enqueue_review | errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 50 (apply) | 50 | 16 | 18 | 12 | 4 | 12 | 4 | 0 | 0 |

Apply 50 OK. Escada maior pode ser liberada na proxima sessao depois de validar o artefato tier2_br novamente.

### `tier2_global_artifact` (novo feed unico Tier2)

| step | received | valid | filtered_notwine | inserted | updated | sources_inserted | sources_updated | enqueue_review | errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 50 (apply) | 50 | 44 | 6 | 28 | 16 | 0 | 0 | 0 | 0 |

Apply 50 OK depois do matching endurecido. Zero sources porque os dominios desta amostra nao tinham correspondencia em `public.stores`, o que e aceitavel: os vinhos entraram sem source; o gate de sources rejeitados nao disparou porque nao houve sources invalidas, apenas ausentes.

## 7. Metricas de controle (deltas observados no banco)

Baseline antes dos applies desta sessao -> final:

| Objeto | Antes | Depois | Delta |
| --- | ---: | ---: | ---: |
| `public.wine_sources` | 3491567 | 3491687 | **+120** (35+65+8+12 = 120 tier1+tier2_br sources_inserted; `amazon_local_legacy_backfill` nao criou sources novos, e `tier2_global_artifact` nao inseriu sources nesta amostra) |
| `public.not_wine_rejections` | 546 | 771 | +225 (10+40+68 = 118 legacy + 15+19+49 = 83 tier1 + 18 tier2_br + 6 tier2_global_artifact = 225) |
| `public.ingestion_review_queue` | 10 | 10 | 0 (zero explosao, gate saudavel) |
| `ops.scraper_runs` | 210 | 220 | +10 (dryruns + applies) |
| `ops.ingestion_batches` | 215 | 225 | +10 |

Contagem `public.wines` nao foi medida no final por timeout de 120s em `COUNT(*)` - o volume impede COUNT rapido. Mas os applies reportam explicitamente:
- tier1_global: 35 + 118 + 217 = **370 wines inserted**
- tier2_br: **12 wines inserted**
- tier2_global_artifact: **28 wines inserted**
- amazon_local_legacy_backfill: 0 inserted (backfill/update)
- Total inserted estimado: **410 wines novos**

## 8. Evidencias de seguranca

- Canal unico preservado: tudo via `plug_commerce_dq_v3 -> process_bulk -> public.wines + public.wine_sources`. Zero escrita direta. Zero novo plug.
- Contrato validado em codigo para toda fonte por artefato (13 campos por item + 8 no summary + SHA256 match + pipeline_family match).
- Producer filtra items incompletos automaticamente (respeita contract).
- Gate `enqueue_review` funcionando: nenhum apply desta sessao disparou `BLOCKED_QUEUE_EXPLOSION`.
- `amazon_local_legacy_backfill` separado de `amazon_mirror_primary` (precedencia `mirror > local_backfill` preservada no codigo e no contrato).
- `winegod_admin_legacy_mixed` continua `blocked_missing_source` (sem allowlist declarada).
- `amazon_mirror_primary` continua `blocked_external_host` honesto (sem artefato do espelho).
- Zero Gemini pago, zero review bruto, zero PII em `ops.*`, zero `vivino_rating`/`vivino_reviews` sobrescrito por este executor.
- Zero `git reset --hard`, zero force push, zero merge em main, zero deploy Render/Vercel.

## 9. Automacao instalada

Operacional:

- `scripts/data_ops_scheduler/run_commerce_artifact_dryruns.ps1` - scheduler canonico atualizado nesta rodada finalissima. Roda dry-run apenas das 4 fontes operacionais de artefato:
  - `amazon_mirror_primary` (residual externo enquanto sem JSONL)
  - `tier1_global`
  - `tier2_global_artifact` (feed unico Tier2; substitui os extintos `tier2_chat1..5`)
  - `tier2_br`
- `scripts/data_ops_scheduler/run_all_observers.ps1` - refresh do dashboard.
- `scripts/data_ops_producers/build_commerce_artifact.py` - producer generico parametrizado com matching por host endurecido.

Operacao recorrente sugerida (via Task Scheduler local):

1. Produzir artefatos (semanal):
   ```powershell
   python scripts/data_ops_producers/build_commerce_artifact.py --pipeline-family tier1 --source-label tier1_global --output-dir reports/data_ops_artifacts/tier1 --tier-filter api_shopify,api_woocommerce,api_vtex,sitemap_html,sitemap_jsonld --limit 2000
   python scripts/data_ops_producers/build_commerce_artifact.py --pipeline-family tier2 --source-label tier2_global_artifact --output-dir reports/data_ops_artifacts/tier2_global --tier-filter playwright_ia --limit 2000
   python scripts/data_ops_producers/build_commerce_artifact.py --pipeline-family tier2 --source-label tier2_br --output-dir reports/data_ops_artifacts/tier2/br --tier-filter playwright_ia --pais-codigo br --limit 500
   ```
2. Validar e dry-run (diario):
   ```powershell
   powershell -File scripts/data_ops_scheduler/run_commerce_artifact_dryruns.ps1
   ```
3. Apply controlado (manual ou agendado com threshold):
   ```powershell
   python -m sdk.plugs.commerce_dq_v3.runner --source tier1_global --limit 1000 --apply
   python -m sdk.plugs.commerce_dq_v3.runner --source tier2_global_artifact --limit 1000 --apply
   ```

## 10. Testes

Pacote consolidado apos rodada finalissima:

- `python -m pytest sdk/plugs scripts/data_ops_producers/tests -q` -> **53 passed** (41 contract + 12 host matching)
- `python -m pytest sdk/tests sdk/adapters/tests -q` -> **119 passed**

Zero falhas. Zero regressao.

## 11. Git

- Branch: `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`
- HEAD anterior: `54698a08`
- Commit do go-live inicial: `fbd80841 feat(data-ops): go-live commerce local ladder with tier producer`
- Commit SHA pin go-live: `4f2bab88 docs(data-ops): pin fbd80841 SHA in go-live docs`
- Commit da correcao de particoes/matching: `e91a22b3 fix(data-ops): harden tier matching and collapse fake tier2 partitions`
- Commit SHA pin correcao: `00e726b8 docs(data-ops): pin e91a22b3 SHA in correction docs`
- Commit da rodada finalissima (scheduler canonico + cleanup manifests + relatorio coerente): `5b429f37 fix(data-ops): align scheduler/manifests with canonical tier2_global_artifact`
- Commit SHA pin final: `217176db docs(data-ops): pin 5b429f37 SHA in final docs`
- Remote: `origin/data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`

## 12. O que o Codex admin deve auditar

1. `scripts/data_ops_producers/build_commerce_artifact.py` - producer local honesto com evidencia tecnica de tier.
2. Artefatos em `reports/data_ops_artifacts/tier1/` e `reports/data_ops_artifacts/tier2/*/` - cada JSONL com summary + sha256 match.
3. Escada de apply: `amazon_local_legacy_backfill` 50/200/1000 + `tier1_global` 50/200/500 + `tier2_br` 50. Todos saudaveis.
4. Nao regressao em `winegod_admin_legacy_mixed` (continua `blocked_missing_source`).
5. Nao regressao em `amazon_mirror_primary` (continua `blocked_external_host` honesto).
6. Zero canal paralelo criado.

## Apendice - Arquivo a repassar para o Codex admin

```text
C:\winegod-app\reports\WINEGOD_GO_LIVE_COMMERCE_RESIDUAL_EXTERNO_E_ARTIFACTS_2026-04-23.md
C:\winegod-app\CLAUDE_RESPOSTAS_CORRECAO_FINALISSIMA_GO_LIVE_COMMERCE_AUTOMACAO_DOCS_2026-04-24.md
```
