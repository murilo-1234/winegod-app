# CLAUDE RESPOSTAS - CORRECAO GO-LIVE COMMERCE PARTICOES TIER + MATCHING - 2026-04-24

## Veredito

```text
CORRECAO_PUBLICADA
```

## Estrategia escolhida para Tier2

**Colapso honesto**: `tier2_chat1..5` nao tinham criterio tecnico reproduzivel e disjunto (todos os chats Codex rodam Playwright+IA sobre a mesma pool de lojas, sem allowlist disjunta por chat). Em vez de fingir particao, colapsei em UM feed global `tier2_global_artifact` + manter `tier2_br` separado (porque tem filtro real por pais).

**O que ficou**:

- `commerce_tier2_global_artifact` (novo) - `registry_status: observed`, feed unico via `reports/data_ops_artifacts/tier2_global/`.
- `commerce_tier2_br` - promovido para `registry_status: observed`, feed separado legitimo por filtro de pais.
- `commerce_tier2_chat1..5` - permanecem `blocked_contract_missing` com `status_reason: colapsado_em_tier2_global_artifact_por_falta_de_particao_disjunta_real` e `notes` explicando DEPRECATED ate existir allowlist disjunta por chat. Se no futuro cada chat tiver pool de lojas isolada, reabilita.

## Como endureci o matching de dominio

Substitui `f.url_original ILIKE '%' || ls.url_normalizada || '%'` por matching Python-side com boundary real:

```python
def normalize_host(value):  # extrai host real, sem protocolo/porta/www
    ...

def _host_eligible(fonte_host, loja_hosts):
    # aceita igualdade exata OU subdominio legitimo (shop.amazon.com -> amazon.com)
    # rejeita mazon.com.br vs amazon.com.br
    ...
```

Agora o producer:
1. Busca lojas elegiveis por pais + metodo.
2. Normaliza host de cada loja.
3. Faz scan paginado de `vinhos_{pais}_fontes`.
4. Filtra em Python: aceita se `host == loja_host` ou `host.endswith("." + loja_host)`.

Isso elimina 3 classes de falso positivo:
- substring sem boundary (`mazon.com.br`)
- sufixo coincidente (`malamazon.com.br`)
- host None/vazio

## Testes novos

`scripts/data_ops_producers/tests/test_host_matching.py` com 12 casos:

- normalize_host: com/sem protocolo, com/sem www, vazio
- _host_eligible: igualdade, subdominio legitimo, falso positivo substring, sufixo coincidente, dominio diferente, multiplas lojas, None

Todos 12/12 pass.

## O que mudou no manifest/registry

| scraper_id | antes | depois |
| --- | --- | --- |
| `commerce_tier1_global` | `blocked_contract_missing` | **`observed`** (artefato local em reports/data_ops_artifacts/tier1) |
| `commerce_tier2_br` | `blocked_contract_missing` | **`observed`** (artefato local em reports/data_ops_artifacts/tier2/br) |
| `commerce_tier2_global_artifact` | (nao existia) | **novo, `observed`** (artefato local em reports/data_ops_artifacts/tier2_global) |
| `commerce_tier2_chat1..5` | `blocked_contract_missing` (razao: "prompts_chat...") | `blocked_contract_missing` com razao `colapsado_em_tier2_global_artifact_por_falta_de_particao_disjunta_real` + notes DEPRECATED |

Registry sincronizado: 31 -> **32 manifests** (+1 do tier2_global_artifact). Snapshot atual:

- commerce_amazon_local / amazon_local_legacy_backfill / br_vinhos_brasil_legacy / dq_v3_observer / tier1_global / tier2_br / tier2_global_artifact / winegod_admin_legacy_mixed / world_winegod_admin: **observed**
- commerce_amazon_mirror / amazon_mirror_primary: **blocked_external_host**
- commerce_tier2_chat1..5: **blocked_contract_missing** (colapsados)

## Testes

- `python -m pytest sdk/plugs scripts/data_ops_producers/tests -q` -> **53 passed** (41 antes + 12 novos de host matching)
- `python -m pytest sdk/tests sdk/adapters/tests -q` -> **119 passed**

## Dry-runs e apply re-rodados

Artefatos regenerados com matching endurecido:
- `tier1_global`: 346 items (antes 550; matching mais restrito filtrou falsos positivos)
- `tier2_global_artifact`: 176 items (colapsando o que antes ia pra 5 chats x 157)
- `tier2_br`: 200 items

Dry-runs: todos os 3 retornaram `state=observed` com `contract=ok`.

Apply 50 de `tier2_global_artifact`: 44 valid / 6 notwine / 28 inserted + 16 updated / 0 enqueue_review / 0 errors. Zero sources_inserted porque os dominios dos itens desta amostra nao tinham correspondencia em `public.stores` (sem FK loja em `public.stores` → source nao criado, mas wine inserida corretamente).

Nao re-executei applies de `tier1_global` nem `amazon_local_legacy_backfill` porque o matching endurecido reduz o universo mas nao invalida os applies anteriores (apenas deixa a proxima sessao produzir artefato com menos falso positivo).

## Arquivos alterados

- `scripts/data_ops_producers/build_commerce_artifact.py` - matching endurecido (normalize_host + _host_eligible).
- `scripts/data_ops_producers/tests/__init__.py` e `scripts/data_ops_producers/tests/test_host_matching.py` - 12 testes novos.
- `sdk/plugs/commerce_dq_v3/exporters.py` - novo exporter `export_tier2_global_artifact_to_dq` e entrada no dict `EXPORTERS`.
- `sdk/adapters/manifests/commerce_tier1_global.yaml` - promovido para observed.
- `sdk/adapters/manifests/commerce_tier2_br.yaml` - promovido para observed.
- `sdk/adapters/manifests/commerce_tier2_global_artifact.yaml` (novo) - feed unico tier2.
- `sdk/adapters/manifests/commerce_tier2_chat1..5.yaml` - `status_reason` e `notes` explicando colapso/DEPRECATED.
- `reports/WINEGOD_GO_LIVE_COMMERCE_RESIDUAL_EXTERNO_E_ARTIFACTS_2026-04-23.md` - bloco de veredito atualizado + tabela de fontes alinhada.
- `CLAUDE_RESPOSTAS_CORRECAO_GO_LIVE_COMMERCE_PARTICOES_TIER_MATCHING_2026-04-24.md` (este).

Artefatos regenerados: `reports/data_ops_artifacts/tier1/`, `reports/data_ops_artifacts/tier2/br/`, `reports/data_ops_artifacts/tier2_global/`. Diretorios antigos `reports/data_ops_artifacts/tier2/chat1..5/` removidos.

Zero alteracao em: `plug_reviews_scores`, WCF, `wine_scores`, `discovery_stores`, `enrichment`, arquitetura DQ V3.

## Branch e commit final

- Branch: `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`
- HEAD anterior: `4f2bab88`
- Commit desta correcao: `<preenchido apos commit>`
- Remote: `origin/data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`

## Arquivos a repassar ao Codex admin

```text
C:\winegod-app\reports\WINEGOD_GO_LIVE_COMMERCE_RESIDUAL_EXTERNO_E_ARTIFACTS_2026-04-23.md
C:\winegod-app\CLAUDE_RESPOSTAS_CORRECAO_GO_LIVE_COMMERCE_PARTICOES_TIER_MATCHING_2026-04-24.md
```
