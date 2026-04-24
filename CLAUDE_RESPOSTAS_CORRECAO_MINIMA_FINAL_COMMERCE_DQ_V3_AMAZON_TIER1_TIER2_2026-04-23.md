# CLAUDE RESPOSTAS - CORRECAO MINIMA FINAL COMMERCE DQ V3 - 2026-04-23

## Veredito desta rodada

```text
CORRECAO_MINIMA_PUBLICADA
```

## O que foi corrigido em cada um dos 3 pontos

### Ponto 1 - `safra` e `preco` podem ser null

**Problema:** o validador em `sdk/plugs/commerce_dq_v3/artifact_contract.py` tratava todos os 13 campos obrigatorios como nao-vazios, mas o contrato em `docs/TIER_COMMERCE_CONTRACT.md` explicita que `safra` e `preco` **podem vir com valor null**.

**Correcao:** adicionado conjunto `ITEM_NULLABLE_FIELDS = {"safra", "preco"}` e a funcao `validate_items` foi reescrita para distinguir:
- campo ausente (chave nao esta no dict) -> falha
- campo presente com valor `None` / `""`:
  - se campo em `ITEM_NULLABLE_FIELDS` -> OK
  - senao -> falha

Os 11 campos nao-nullable continuam rejeitando null (incluindo `moeda`, `country`, `store_domain`, etc.). Apenas `safra` e `preco` passam a aceitar null.

**Testes adicionados (5 novos, todos passam):**
- `test_safra_null_is_accepted` - artefato com `safra=null` aprovado.
- `test_preco_null_is_accepted` - artefato com `preco=null` aprovado.
- `test_missing_safra_key_fails` - artefato sem a chave `safra` reprovado.
- `test_missing_preco_key_fails` - artefato sem a chave `preco` reprovado.
- `test_non_nullable_null_fails` - artefato com `moeda=null` reprovado (prova que a permissao de null ficou escopada).

Contrato documental (`docs/TIER_COMMERCE_CONTRACT.md`) **nao foi alterado** - o codigo foi ajustado para obedecer ao contrato atual, nao ao contrario.

### Ponto 2 - relatorio principal alinhado ao estado corrigido

Alteracoes em `reports/WINEGOD_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md`:

- Tabela **17.2 Fontes e papel final**:
  - `amazon_mirror_primary`: descricao atualizada para refletir `blocked_external_host` atual + transicao para `observed` apenas quando JSONL + summary validados chegarem.
  - `tier1_global` e `tier2_*`: mencionam agora validacao do summary + JSONL.
  - `winegod_admin_legacy_mixed`: **removida a alegacao falsa de `observed (items=10)`**; agora diz explicitamente `blocked_missing_source` por default e so `observed` via `LEGACY_MIXED_ALLOWED_FONTES`.
- Secao **17.3 O que foi realmente implementado / Manifests novos**:
  - `commerce_amazon_mirror_primary.yaml` marcado `registry_status: blocked_external_host`.
  - `winegod_admin_legacy_mixed.yaml` explicitado que o manifest e `observed` mas o runtime default e `blocked_missing_source`.
  - Adicionado bloco "apos a rodada de hardening e esta correcao minima, status real registrado em `ops.scraper_registry`" com snapshot real.
- Bullet de `export_winegod_admin_legacy_mixed_to_dq` reescrito: deixa explicito que o default e `blocked_missing_source` e so libera items com allowlist declarada.
- Tabela **17.5 Escada** e **17.7 Metricas de controle**: linha `winegod_admin_legacy_mixed` atualizada de `observed 10/7/3` para `blocked_missing_source (default sem allowlist)`.
- **Apendice A - Testes** reescrito com os numeros reais do pacote corrigido:
  - `test_artifact_contract.py` -> 13 passed (antes 8)
  - `sdk/plugs -q` -> 41 passed (antes 36)
  - `sdk/tests sdk/adapters/tests -q` -> 119 passed
  - Smokes dry-run confirmando comportamento corrigido.

### Ponto 3 - trilha Git ate o HEAD publicado

Tanto `reports/WINEGOD_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md::17.9` quanto `CLAUDE_RESPOSTAS_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md` listam agora:

- `fcfd866c feat(data-ops): finalize commerce routing for amazon tier1 and tier2`
- `5b6e3875 docs(data-ops): pin fcfd866c SHA in final commerce report`
- `c81072dd fix(data-ops): harden commerce artifact contract and legacy routing`
- `85b38c0a docs(data-ops): pin c81072dd SHA in correction docs`
- commit final desta correcao minima (preenchido apos push; ver abaixo).

## Arquivos alterados nesta rodada

- `sdk/plugs/commerce_dq_v3/artifact_contract.py` - adicionado `ITEM_NULLABLE_FIELDS` e refatorada `validate_items`.
- `sdk/plugs/commerce_dq_v3/tests/test_artifact_contract.py` - 5 testes novos.
- `reports/WINEGOD_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md` - alinhamento com codigo atual.
- `CLAUDE_RESPOSTAS_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md` - trilha Git atualizada.
- `CLAUDE_RESPOSTAS_CORRECAO_MINIMA_FINAL_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md` - este arquivo.

Zero alteracao em: `plug_reviews_scores`, WCF, `public.wine_scores`, `discovery_stores`, `enrichment`, arquitetura commerce, exporters/runner, fluxo `amazon_mirror_primary` vs `amazon_local_legacy_backfill`.

## Testes rodados

Comando: `python -m pytest`.

- `python -m pytest sdk/plugs/commerce_dq_v3/tests/test_artifact_contract.py -q` -> **13 passed** (antes 8)
- `python -m pytest sdk/plugs -q` -> **41 passed** (antes 36)
- `python -m pytest sdk/tests sdk/adapters/tests -q` -> **119 passed**

## Smokes rodados

- `python -m sdk.plugs.commerce_dq_v3.runner --source winegod_admin_legacy_mixed --limit 10 --dry-run` -> `state=blocked_missing_source` (default sem allowlist). Notes: `sem_prova_de_legado_misturado_no_schema_atual`, `nenhum_fk_entre_vinhos_e_scraping_execucoes.tier`, `declare_LEGACY_MIXED_ALLOWED_FONTES_para_habilitar_allowlist`, `por_padrao_bloqueado_para_nao_sobrepor_winegod_admin_world`.
- `python -m sdk.plugs.commerce_dq_v3.runner --source amazon_mirror_primary --limit 10 --dry-run` -> `state=blocked_external_host`. Notes: `nenhum_artefato_jsonl_em=C:\winegod-app\reports\data_ops_artifacts\amazon_mirror`, `host_externo_pc_espelho`, `entregar_jsonl_em=reports/data_ops_artifacts/amazon_mirror/`.

Zero apply produtivo; zero escrita em `public.wines`/`public.wine_sources`.

## Branch e commits finais

- Branch: `data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`
- HEAD anterior: `85b38c0a`
- Commit desta correcao minima: `0f75ba37 fix(data-ops): accept null safra/preco per contract and align final report`
- Remote: `origin/data-ops/finalizacao-commerce-dqv3-amazon-tier1-tier2-20260423`

## Arquivos a repassar ao Codex admin

```text
C:\winegod-app\reports\WINEGOD_EXECUCAO_TOTAL_FINALIZACAO_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md
C:\winegod-app\CLAUDE_RESPOSTAS_CORRECAO_MINIMA_FINAL_COMMERCE_DQ_V3_AMAZON_TIER1_TIER2_2026-04-23.md
```
