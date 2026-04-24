# WINEGOD - Discovery Production Path

Data: 2026-04-24
Branch: `data-ops/execucao-total-discovery-enrichment-producao-20260424`
Contrato: [docs/DISCOVERY_STORES_PROMOTION_CONTRACT.md](../docs/DISCOVERY_STORES_PROMOTION_CONTRACT.md)

## 1. O que foi entregue

Codigo:

- `sdk/plugs/discovery_stores/promotion.py` - `StorePromoter`
  (plan/apply idempotente, gates G1..G5, dedup dominio, legacy recipe
  detection)
- `sdk/plugs/discovery_stores/recipe_generator.py` - heuristica
  deterministica (JSON-LD, OpenGraph, preco por moeda, TLD fallback,
  paginacao, vintage, producer brand), sem LLM
- `scripts/data_ops_producers/promote_discovery_stores.py` - CLI
  `--plan-only` (default); `--apply` exige `DISCOVERY_PROMOTION_AUTHORIZED=1`
- `scripts/data_ops_producers/dedup_stores.py` - CLI batch 10k,
  dominio canonicalizado, similarity hits, report md+json

Testes:

- `sdk/plugs/discovery_stores/tests/test_promotion.py` (12 casos)
- `sdk/plugs/discovery_stores/tests/test_recipe_generator.py` (9 casos)
- `scripts/data_ops_producers/tests/test_dedup_stores.py` (10 casos)

## 2. Como rodar dry-runs

```powershell
python scripts/data_ops_producers/promote_discovery_stores.py --plan-only --limit 50
python scripts/data_ops_producers/dedup_stores.py --plan-only
python -m sdk.plugs.discovery_stores.runner --source agent_discovery --limit 10 --dry-run
powershell -File scripts/data_ops_scheduler/run_discovery_promotion_dryrun.ps1
powershell -File scripts/data_ops_scheduler/run_dedup_stores_dryrun.ps1
```

Artefatos gerados:

- `reports/data_ops_promotion_plans/<ts>_plan.json` + `<ts>_plan_summary.md`
- `reports/data_ops_dedup/stores_dedup_<ts>.md` + `.json`
- `reports/data_ops_recipe_candidates/<ts>_<domain>.json`

## 3. O que precisa autorizacao explicita para ativar

| Acao | Env var | Flag |
|---|---|---|
| apply promocao em `public.stores` + `public.store_recipes` | `DISCOVERY_PROMOTION_AUTHORIZED=1` | `--apply` |
| apply merge de duplicatas em `public.stores` | `DEDUP_STORES_AUTHORIZED=1` | `--apply` |

Nesta sessao **ambos estao bloqueados** mesmo com as envs setadas
(CLI raise explicito). O apply real vai ser implementado em sessao
futura com revisao manual do primeiro plan que o usuario quiser
disparar.

## 4. Criterios de sucesso operacional

- promote_discovery_stores produz plan estavel (`plan_hash` nao
  muda entre execucoes com mesmo input).
- dedup_stores produz report que cobre 100% das linhas de `public.stores`.
- recipe_generator emite `confidence >= 0.5` em >=70% dos dominios
  com JSON-LD Product.

## 5. Riscos conhecidos

- **Gates dependem de `sample_scrape`** que ainda nao e parte do
  pipeline discovery real. Todos os candidatos atuais sao skipped com
  `minimum_products_below_threshold` ate o pipeline scraper enriquecer
  os candidatos. Esse e o comportamento esperado nesta fase.
- **Dedup heuristico de similaridade** agrupa por 2nd-to-last label;
  dominios muito distintos no topo podem escapar. O report lista
  hits por score, operacao humana aprova o merge.
- **Promotion apply hardcoded-disabled**: mesmo com env+auth=True, o
  `apply()` exige `conn_factory` injetado. Adicionar pool de conexao
  esta fora do escopo desta sessao.

## 6. Rollback procedure

Como zero apply foi feito nesta sessao, rollback = remover commits
da branch + apagar `reports/data_ops_promotion_plans/`,
`reports/data_ops_dedup/`, `reports/data_ops_recipe_candidates/`.
Nenhum registro em `public.*` precisa ser revertido.

Se no futuro um `--apply` for executado:

1. lookup em `public.stores` pelo `promotion_plan_hash` na coluna
   `notas` JSON;
2. delete cascata em `public.store_recipes` e `public.stores` com esse
   hash;
3. registrar no runbook qual plan foi revertido e por que.
