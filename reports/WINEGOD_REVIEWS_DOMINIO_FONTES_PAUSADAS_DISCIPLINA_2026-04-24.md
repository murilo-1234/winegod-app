# WINEGOD - Reviews - Disciplina das fontes pausadas nesta fase

Data: 2026-04-24
Tipo: consolidacao operacional / Fase C do prompt EXECUCAO_TOTAL_REVIEWS
Status: SEMANTICO_FECHADO_NESTA_FASE

## 1. Objetivo

Deixar explicito, em um so lugar, qual e o estado operacional e o limite
semantico das 4 fontes externas de sinais de review neste instante. Esta
consolidacao nao autoriza execucao, upload, nem mudanca de contrato.

A decisao de pausar essas fontes e da fase atual. Ela ja esta registrada em:

- [WINEGOD_SINAIS_EXTERNOS_CT_DEC_WE_WS_HANDOFF_DECISAO_2026-04-23.md](WINEGOD_SINAIS_EXTERNOS_CT_DEC_WE_WS_HANDOFF_DECISAO_2026-04-23.md)

Este documento e um complemento operacional: mostra como essa decisao esta
materializada no repositorio (manifests, adapters, wrappers), explica por
que nada neste prompt reabre o tema, e lista o que um proximo job deve
respeitar.

## 2. Fontes pausadas nesta fase

| Fonte | Manifest | Adapter observer | Wrapper shadow |
|---|---|---|---|
| CellarTracker | `sdk/adapters/manifests/scores_cellartracker.yaml` | `sdk/adapters/cellartracker_observer.py` | `scripts/data_ops_shadow/run_scores_cellartracker_shadow.ps1` |
| Decanter | `sdk/adapters/manifests/critics_decanter_persisted.yaml` | `sdk/adapters/decanter_persisted_observer.py` | `scripts/data_ops_shadow/run_critics_decanter_persisted_shadow.ps1` |
| Wine Enthusiast | `sdk/adapters/manifests/critics_wine_enthusiast.yaml` | `sdk/adapters/wine_enthusiast_observer.py` | `scripts/data_ops_shadow/run_critics_wine_enthusiast_shadow.ps1` |
| Wine-Searcher | `sdk/adapters/manifests/market_winesearcher.yaml` | `sdk/adapters/winesearcher_observer.py` | `scripts/data_ops_shadow/run_market_winesearcher_shadow.ps1` |

## 3. Estado materializado no repositorio

### 3.1 Manifests

Todos os 4 manifests acima declaram, nesta fase:

- `registry_status: observed`
- `outputs: [ops]`
- `can_create_wine_sources: false`
- `requires_dq_v3: false`
- `requires_matching: false`
- `tags` contem `plug:reviews_scores`

### 3.2 Adapters observers

Cada adapter roda em modo READ-ONLY contra o banco local
`WINEGOD_DATABASE_URL`. Nao abre conexao com API externa. Nao grava na base
principal. Produz apenas telemetria via `ops.*`.

### 3.3 Wrappers shadow

Cada wrapper shadow chama o adapter em modo dry-run, captura log local em
`reports/data_ops_shadow/` e opcionalmente envia telemetria para
`ops.scraper_runs`. Nenhum deles abre apply no Render.

### 3.4 Plug `plug_reviews_scores`

O runner do plug rejeita `--mode backfill_windowed` para qualquer source
nao-Vivino (vide `BACKFILL_SUPPORTED_SOURCES = {"vivino_wines_to_ratings"}`
em `sdk/plugs/reviews_scores/runner.py`). O writer `apply_bundle` continua
nao escrevendo para essas fontes porque os itens nao carregam `vivino_id`
para resolver `public.wines`; o campo `unmatched` seria 100% delas.

## 4. Salvaguardas de teste

Foram consolidados dois testes de cobertura (`test_manifests_coverage.py`)
que travam drift silencioso:

- `test_paused_sources_stay_observed_not_applied` falha se alguem mudar
  `registry_status` para algo diferente de `observed` nestas 4 fontes;
- `test_review_manifests_never_declare_commerce_outputs` falha se alguma
  dessas fontes (ou qualquer manifest do dominio reviews) comecar a declarar
  `public.wine_sources` no bloco `outputs`.

## 5. O que este prompt NAO muda

Nada nesta execucao:

- promove qualquer das 4 fontes para apply;
- adiciona exporter delas ao caminho canonico;
- altera a formula de confianca;
- mistura esses sinais na base local do Vivino;
- tenta mover o WCF para absorver esses sinais.

A logica de producao continua sendo: o canal Vivino e o unico apply oficial,
documentado em `docs/PLUG_REVIEWS_SCORES_CONTRACT.md`.

## 6. Proximo job - o que assumir

Se um proximo trabalho tocar essas 4 fontes:

1. assumir que elas continuam em `observed`;
2. justificar qualquer mudanca de status como um **novo contrato**, com PR
   proprio e atualizacao explicita do `registry_status`;
3. nao juntar os dados delas com `vivino_vinhos`;
4. nao reutilizar a fonte `vivino_wines_to_ratings` para novos sinais;
5. respeitar a disciplina de PII e anti-vazamento semantico ja documentada
   no handoff de decisao.

## 7. Ponteiros obrigatorios

- [WINEGOD_SINAIS_EXTERNOS_CT_DEC_WE_WS_HANDOFF_DECISAO_2026-04-23.md](WINEGOD_SINAIS_EXTERNOS_CT_DEC_WE_WS_HANDOFF_DECISAO_2026-04-23.md)
- [WINEGOD_SINAIS_EXTERNOS_CT_DEC_WE_WS_ANALISE.md](WINEGOD_SINAIS_EXTERNOS_CT_DEC_WE_WS_ANALISE.md)
- [PLUG_REVIEWS_SCORES_CONTRACT.md](../docs/PLUG_REVIEWS_SCORES_CONTRACT.md)

## 8. Veredito desta consolidacao

```
disciplina_fontes_externas_reviews = PRESERVADA
drift_de_status = BLOQUEADO_POR_TESTE
apply_no_render = NAO_EXISTE_NESTA_FASE_POR_DECISAO
review_bruto = NAO_SOBE
```
