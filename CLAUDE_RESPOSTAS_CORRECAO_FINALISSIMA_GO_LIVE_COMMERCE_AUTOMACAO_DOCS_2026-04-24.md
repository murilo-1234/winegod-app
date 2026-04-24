# CLAUDE RESPOSTAS - CORRECAO FINALISSIMA GO-LIVE COMMERCE - 2026-04-24

## Veredito da rodada

```text
CORRECAO_FINALISSIMA_PUBLICADA
```

## 1. Scheduler corrigido

`scripts/data_ops_scheduler/run_commerce_artifact_dryruns.ps1` reescrito para refletir a arquitetura canonica atual.

Antes rodava dry-run em 8 fontes, incluindo `tier2_chat1..5` deprecated. Agora roda apenas 4 fontes canonicas:

- `amazon_mirror_primary` (residual externo enquanto sem JSONL)
- `tier1_global`
- `tier2_global_artifact` (feed Tier2 UNICO; substitui os extintos `tier2_chat1..5`)
- `tier2_br` (Tier2 filtrado por pais real)

Comentarios do script atualizados explicando o colapso. `scripts/data_ops_scheduler/README.md` tambem atualizado para descrever a nova lista de fontes canonicas.

Smoke do scheduler pos-mudanca:

```
==> commerce artifact dry-run source=amazon_mirror_primary limit=20
==> commerce artifact dry-run source=tier1_global limit=20
==> commerce artifact dry-run source=tier2_global_artifact limit=20
==> commerce artifact dry-run source=tier2_br limit=20
==> commerce artifact dryruns done
```

## 2. O que foi limpo no relatorio

`reports/WINEGOD_GO_LIVE_COMMERCE_RESIDUAL_EXTERNO_E_ARTIFACTS_2026-04-23.md` reescrito para narrativa unica e coerente:

- Secao "Producer local novo" agora menciona matching por host endurecido + boundary real (em vez de substring antiga).
- Secao "Artefatos canonicos atuais" substituiu a lista antiga com `tier2/chat1..5`. Agora lista os 4 diretorios reais (`tier1/`, `tier2/br/`, `tier2_global/`, `amazon_mirror/`). Bloco explicito "Diretorios antigos removidos" documenta o colapso.
- Secao "Dry-runs executados" - listou as 4 fontes canonicas atuais (tier1_global, tier2_br, tier2_global_artifact, amazon_local_legacy_backfill) + `amazon_mirror_primary` como residual. Paragrafo explicito sobre tier2_chat1..5 nao serem mais executados.
- Nova sub-tabela de apply em tier2_global_artifact (50 items, 44 valid, 28 inserted + 16 updated, 0 errors).
- Secao "Automacao" reescrita para apontar o scheduler canonico atualizado (4 fontes) e adicionar comando de produce para `tier2_global_artifact`.
- Apendice de testes atualizado: 53 (sdk/plugs + scripts/data_ops_producers/tests) + 119 (sdk/tests sdk/adapters/tests).
- Secao Git expandida com `e91a22b3`, `00e726b8` e commit desta rodada.

## 3. O que foi limpo nos manifests

- `sdk/adapters/manifests/commerce_tier1_global.yaml`:
  - `entrypoint` atualizado de shadow wrapper para `python -m sdk.plugs.commerce_dq_v3.runner --source tier1_global --limit 50 --dry-run`
  - tag `pending:contract` removida; adicionada `lineage:primary`; `planned` removida
  - `notes` reescritas: descricao operacional do artefato + producer + matching endurecido
- `sdk/adapters/manifests/commerce_tier2_br.yaml`: mesmas mudancas, com comando e descricao equivalentes para tier2_br (pais=br, playwright_ia).
- `sdk/adapters/manifests/commerce_tier2_chat1..5.yaml` (deprecated): nao foram tocados nesta rodada porque ja explicavam colapso na sessao anterior (`status_reason: colapsado_em_tier2_global_artifact_por_falta_de_particao_disjunta_real` + notes DEPRECATED).
- `sdk/adapters/manifests/commerce_tier2_global_artifact.yaml` (novo, da sessao anterior): ja nasceu coerente com `lineage:primary`.

## 4. Trilha Git final

Commits desta branch `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`:

- `fbd80841 feat(data-ops): go-live commerce local ladder with tier producer`
- `4f2bab88 docs(data-ops): pin fbd80841 SHA in go-live docs`
- `e91a22b3 fix(data-ops): harden tier matching and collapse fake tier2 partitions`
- `00e726b8 docs(data-ops): pin e91a22b3 SHA in correction docs`
- `5b429f37 fix(data-ops): align scheduler/manifests with canonical tier2_global_artifact`
- commit SHA pin final (se necessario).

## 5. Testes/verificacoes

- `python -m pytest sdk/plugs scripts/data_ops_producers/tests -q` -> **53 passed**
- `python -m pytest sdk/tests sdk/adapters/tests -q` -> **119 passed**
- Scheduler `run_commerce_artifact_dryruns.ps1 -Limit 20` -> 4 fontes rodadas sem erro.
- Dry-run individual de `tier2_global_artifact` -> `state=observed`, `contract=ok`.

## 6. Commit final

- Branch: `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`
- Commit desta correcao finalissima: `5b429f37 fix(data-ops): align scheduler/manifests with canonical tier2_global_artifact`
- Remote: `origin/data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`

## 7. Arquivos a repassar ao Codex admin

```text
C:\winegod-app\reports\WINEGOD_GO_LIVE_COMMERCE_RESIDUAL_EXTERNO_E_ARTIFACTS_2026-04-23.md
C:\winegod-app\CLAUDE_RESPOSTAS_CORRECAO_FINALISSIMA_GO_LIVE_COMMERCE_AUTOMACAO_DOCS_2026-04-24.md
```
