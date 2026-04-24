# CLAUDE RESPOSTAS - GO-LIVE COMMERCE + RESIDUAL EXTERNO + ARTIFACTS

## Veredito

```text
APROVADO_COM_GO_LIVE_LOCAL_ESCADA_E_RESIDUAL_EXTERNO_ISOLADO
```

## Resumo executivo

Implementado producer local de artefato commerce padronizado com evidencia tecnica real de tier (cruzando `lojas_scraping.metodo_recomendado` com `vinhos_*_fontes.url_original`). Tier1 e todas as 6 particoes Tier2 agora emitem JSONL + summary validados pelo contrato. Escada de apply controlada executada para `amazon_local_legacy_backfill`, `tier1_global` e `tier2_br`. Amazon mirror continua `blocked_external_host` honesto por dependencia externa. Zero canal paralelo, zero violacao de contrato.

## O que foi fechado de ponta a ponta

- **Producer local**: `scripts/data_ops_producers/build_commerce_artifact.py` - parametrizado, respeita contrato, filtra items incompletos.
- **Artefatos**: 8 JSONLs novos (tier1 + 6 tier2 + backfill disponivel), todos com summary + sha256 match.
- **Apply escada**:
  - `amazon_local_legacy_backfill`: 50/200/1000 completos. 471 wines updated + 226 sources updated. Zero inserted (so atualiza lineage). Zero errors.
  - `tier1_global`: 50/200/500 completos. 370 wines inserted + 205 wines updated + 108 sources inserted + 148 sources updated.
  - `tier2_br`: apply 50 OK. 12 wines inserted + 4 updated + 12 sources inserted.
- **Dry-runs saudaveis**: `tier2_chat1..5` e `tier2_br` todos em `observed` (escada maior liberada para proxima sessao).
- **Registry**: 3 manifests commerce novos + 3 shadows novos + 1 scheduler dedicado ja estavam na sessao anterior; nada regressou.

## O que ainda depende de externo

**Um unico residual real**: `amazon_mirror_primary` continua `blocked_external_host` enquanto o operador do PC espelho nao depositar JSONL + summary em `reports/data_ops_artifacts/amazon_mirror/` no contrato `docs/TIER_COMMERCE_CONTRACT.md`. Quando aparecer, o scheduler `run_commerce_artifact_dryruns.ps1` consome automaticamente o mais recente.

Nao ha outro residual externo.

## Testes

- `python -m pytest sdk/plugs -q` -> **41 passed**
- `python -m pytest sdk/tests sdk/adapters/tests -q` -> **119 passed**

## Smokes

- `run_commerce_artifact_dryruns.ps1 -Limit 50` -> 7/8 `observed` + 1 `blocked_external_host` (mirror, esperado)
- Dry-runs individuais antes de cada apply -> 100% coerente com os applies

## Applies

| fonte | escada | wines_inserted | wines_updated | sources_inserted | sources_updated | errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| amazon_local_legacy_backfill | 50+200+1000 | 0 | 471 | 0 | 226 | 0 |
| tier1_global | 50+200+500 | 370 | 205 | 108 | 148 | 0 |
| tier2_br | 50 | 12 | 4 | 12 | 4 | 0 |

Totais desta sessao:
- `public.wines`: +382 inserted + 680 updated
- `public.wine_sources`: +120 inserted + 378 updated
- `public.not_wine_rejections`: +219
- `public.ingestion_review_queue`: 0 delta (saudavel)

## Arquivos alterados

- `scripts/data_ops_producers/build_commerce_artifact.py` (novo)
- `reports/data_ops_artifacts/amazon_mirror/` (diretorio novo, vazio aguardando PC espelho)
- `reports/data_ops_artifacts/tier1/*.jsonl` + `*_summary.json`
- `reports/data_ops_artifacts/tier2/{br,chat1..5}/*.jsonl` + `*_summary.json`
- `reports/WINEGOD_GO_LIVE_COMMERCE_RESIDUAL_EXTERNO_E_ARTIFACTS_2026-04-23.md` (novo)
- `CLAUDE_RESPOSTAS_GO_LIVE_COMMERCE_RESIDUAL_EXTERNO_E_ARTIFACTS_2026-04-23.md` (este)

Zero alteracao em: `plug_reviews_scores`, WCF, `public.wine_scores`, `discovery_stores`, `enrichment`, arquitetura de plugs, validator `artifact_contract.py`, manifests existentes, outros schedulers.

## Branch e commit final

- Branch: `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`
- HEAD anterior: `54698a08`
- Commit desta sessao: `fbd80841 feat(data-ops): go-live commerce local ladder with tier producer`
- Remote: `origin/data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`

## Caminhos dos 2 arquivos a repassar ao Codex admin

```text
C:\winegod-app\reports\WINEGOD_GO_LIVE_COMMERCE_RESIDUAL_EXTERNO_E_ARTIFACTS_2026-04-23.md
C:\winegod-app\CLAUDE_RESPOSTAS_GO_LIVE_COMMERCE_RESIDUAL_EXTERNO_E_ARTIFACTS_2026-04-23.md
```
