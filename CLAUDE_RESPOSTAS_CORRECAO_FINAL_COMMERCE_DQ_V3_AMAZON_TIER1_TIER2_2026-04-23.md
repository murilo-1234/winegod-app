# CLAUDE RESPOSTAS - CORRECAO FINAL COMMERCE DQ V3 - 2026-04-23

## Veredito desta rodada

```text
CORRECAO_PUBLICADA
```

## Findings do Codex admin e como foram corrigidos

### Finding 1 - `winegod_admin_legacy_mixed` amplo demais

**Como ficou:** o exporter agora retorna `blocked_missing_source` por padrao. O filtro antigo "todo nao-Amazon" foi removido.

**Criterio final:** o schema atual do `winegod_db` nao oferece FK limpa que prove legado Tier1/Tier2 (a coluna `tier` existe em `scraping_execucoes` mas nao ha rastreio direto fonte->execucao->tier em cada vinho). Em vez de inventar um filtro amplo, o exporter agora exige allowlist explicita via variavel de ambiente:

```
LEGACY_MIXED_ALLOWED_FONTES=fonte1,fonte2,fonte3
```

Se a allowlist nao estiver declarada, estado = `blocked_missing_source` com `notes` explicando o motivo. Se estiver, so passa itens cuja `fonte` estiver na allowlist (e nao `amazon*`). Isso nao sobrepoe mais `winegod_admin_world`.

**Codigo:** `sdk/plugs/commerce_dq_v3/exporters.py::export_winegod_admin_legacy_mixed_to_dq` + helper `_legacy_mixed_allowed_fontes()`.

**Smoke validado (default):** `state=blocked_missing_source`, notes=`sem_prova_de_legado_misturado_no_schema_atual`, `nenhum_fk_entre_vinhos_e_scraping_execucoes.tier`, `declare_LEGACY_MIXED_ALLOWED_FONTES_para_habilitar_allowlist`, `por_padrao_bloqueado_para_nao_sobrepor_winegod_admin_world`.

### Finding 2 - contrato de artefato fraco no codigo

**Como ficou:** novo modulo `sdk/plugs/commerce_dq_v3/artifact_contract.py` com validacao rigorosa:

- localiza JSONL mais recente (`pick_latest_jsonl`);
- localiza summary correspondente `<prefix>_summary.json`;
- valida 13 campos obrigatorios por item;
- valida 8 campos obrigatorios no summary;
- recalcula SHA256 do JSONL e compara com `summary.artifact_sha256`;
- valida que `pipeline_family` dos items e do summary bate com o esperado.

Qualquer falha retorna `ContractValidation(ok=False, reason, notes=[...])`; os exporters convertem isso em `blocked_external_host` (artefato ausente) ou `blocked_contract_missing` (contrato invalido), com `notes` explicando o motivo especifico.

**Codigo aplicado em:** `export_amazon_mirror_primary_to_dq`, `_export_tier_from_artifact` (usado por `tier1_global` e `tier2_*`).

**Testes novos (8 casos):** `sdk/plugs/commerce_dq_v3/tests/test_artifact_contract.py` cobre: artefato valido, JSONL sem campo obrigatorio, summary ausente, SHA mismatch, `pipeline_family` errado no item, `pipeline_family` errado no summary, diretorio sem JSONL. Todos passam.

### Finding 3 - manifest do Amazon mirror primary

**Como ficou:** `sdk/adapters/manifests/commerce_amazon_mirror_primary.yaml` ajustado para refletir o estado real atual:

```yaml
registry_status: blocked_external_host
status_reason: aguardando_jsonl_no_diretorio_reports/data_ops_artifacts/amazon_mirror/
```

Apos `sync_registry_from_manifests.py --apply`, `ops.scraper_registry` mostra:

```
commerce_amazon_mirror_primary | blocked_external_host
commerce_amazon_mirror         | blocked_external_host
commerce_amazon_local          | observed
commerce_amazon_local_legacy_backfill | observed
```

O dashboard nao da mais falso verde. Quando o PC espelho entregar JSONL valido, o manifest sobe para `observed` num commit futuro (fica explicito como transicao de status).

### Finding 4 - trilha Git final

**Como ficou:** as secoes Git em:

- `reports/WINEGOD_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md::17.9`
- `CLAUDE_RESPOSTAS_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md`

listam explicitamente:
- `fcfd866c feat(data-ops): finalize commerce routing for amazon tier1 and tier2`
- `5b6e3875 docs(data-ops): pin fcfd866c SHA in final commerce report`
- commit fix desta rodada (SHA sera cravado ao final via commit+amend+re-commit para evitar loop de hash)

## Arquivos que mudaram nesta rodada corretiva

- `sdk/plugs/commerce_dq_v3/artifact_contract.py` (novo) - validator canonico
- `sdk/plugs/commerce_dq_v3/exporters.py` (atualizado) - usa validator + restringe legacy_mixed
- `sdk/plugs/commerce_dq_v3/tests/test_artifact_contract.py` (novo) - 8 testes
- `sdk/adapters/manifests/commerce_amazon_mirror_primary.yaml` (atualizado) - `registry_status: blocked_external_host`
- `reports/WINEGOD_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md` (atualizado)
- `CLAUDE_RESPOSTAS_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md` (atualizado)
- `CLAUDE_RESPOSTAS_CORRECAO_FINAL_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md` (este arquivo - novo)

Nao houve alteracao em:
- `plug_reviews_scores` ou qualquer modulo de reviews
- Writer/WCF/wine_scores
- Outros plugs (`discovery_stores`, `enrichment`)
- `backend/`

## Testes rodados

Comando usado: `python -m pytest`.

- `python -m pytest sdk/plugs/commerce_dq_v3/tests/test_artifact_contract.py -q` -> **8 passed**
- `python -m pytest sdk/plugs -q` -> **36 passed** (antes eram 28; +8 novos do contrato)
- `python -m pytest sdk/tests sdk/adapters/tests -q` -> **119 passed**

Smokes dry-run desta rodada:
- `python -m sdk.plugs.commerce_dq_v3.runner --source winegod_admin_legacy_mixed --limit 10 --dry-run` -> `blocked_missing_source` (default sem allowlist)
- `python -m sdk.plugs.commerce_dq_v3.runner --source amazon_mirror_primary --limit 10 --dry-run` -> `blocked_external_host` (sem JSONL entregue ainda)

Zero apply produtivo. Zero escrita em `public.wines`/`public.wine_sources`.

## Branch e commits para auditoria

- Branch: `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`
- HEAD previo: `5b6e3875`
- Commit fix desta rodada: `<preenchido apos commit>`
- Remote: `origin/data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`

## Arquivo a repassar para o Codex admin

```text
C:\winegod-app\reports\WINEGOD_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md
C:\winegod-app\CLAUDE_RESPOSTAS_CORRECAO_FINAL_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md
```
