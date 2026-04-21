# WINEGOD_PRE_INGEST_ROUTER — Handoff Oficial

**Data**: 2026-04-21 (atualizado pos-apply pequeno + drain)
**Sessao Claude**: 2026-04-21_0825
**Projeto**: winegod-app
**Branch**: `i18n/onda-2` (mudancas nao commitadas)

Este documento e o **handoff completo** do trabalho feito na sessao em cima do pipeline `bulk_ingest` + seu roteador de entrada `pre_ingest_router`. Qualquer outra aba ou operador deve abrir **este arquivo primeiro**: ele diz onde estamos, o que ja foi decidido, o que rodou, o que falta, e como retomar.

---

## 1. Sumario executivo (TL;DR)

1. **bulk_ingest esta em producao** em `https://winegod-app.onrender.com/api/ingest/bulk`. Smoke validado (`overall_ok: true`). Commit `fa33bb24` em `origin/main`.
2. **Bugs corrigidos via auditoria**:
   - Duplicata por tripla normalizada com hash diferente → `_apply_batch` faz `UPDATE WHERE id=...` em vez de confiar em `ON CONFLICT(hash_dedup)`.
   - `total_fontes` inflava em reapply e arrancava com `1` mesmo sem `wine_sources` → agora `0` no INSERT, preservado no UPDATE, com merge dedup em `fontes`.
3. **Runner de testes** com modo `REQUIRE_DB_TESTS=1` estrito (`SKIP/FAIL/ABORT`). Breakdown: **16 com DB acessivel, 10 pass + 6 skip sem DB**. Total `test_bulk_ingest` cresceu para mais casos apos integracao DQ V3.
4. **Fluxo bifurcado implementado e executado**: `fonte real → filtro deterministico → classificador → {ready, needs_enrichment, not_wine, uncertain} → bulk_ingest so sobre ready`. `uncertain` e saida lateral nunca-bloqueante.
5. **Fase 1 (classificador)** ENTREGUE — `scripts/_ingest_classifier.py` + 30 testes offline.
6. **Fase 2 (router) + HARDENING** ENTREGUE — `scripts/pre_ingest_router.py` + 37 testes (sanitizacao de `--source`, `--out-dir` default ancorado em repo root, dir so criado apos validacao).
7. **Runbook** em `reports/WINEGOD_PRE_INGEST_ROUTER_RUNBOOK.md`, incluindo secao 11 para base legada.
8. **Ponte com base legada** ENTREGUE — `scripts/export_vinhos_brasil_to_router.py` read-only sobre `C:\natura-automation\vinhos_brasil\vinhos_brasil_db` (146k wines). Suporte a `--offset`, `"nacional"` em fontes conhecidas, `f.dados_extras` (extrai `loja`), campos comerciais explicitos (`url_original`, `loja`, `fonte_original`, `preco_fonte`, `mercado`). 35 testes offline.
9. **Fase 4 (Gemini) com guardrail factual** ENTREGUE — `scripts/enrich_needs.py` reutiliza `enrichment_v3.enrich_items_v3`, aplica segundo filtro pos-merge, reclassifica via `classify()`. **Guardrail `qa_conflict:country_hint_mismatch`** rejeita enriquecimento que contradiz URL/descricao/pais original. Suporte a `--from-raw` reprocessa sem gastar Gemini. 43 testes offline com mock.
10. **Piloto real vtex rodou ponta a ponta**:
    - Export: 500 items vtex → `reports/ingest_pipeline_inputs/20260421_113807_vinhos_brasil_vtex.jsonl`.
    - Router: `406 ready, 53 needs_enrichment, 40 rejected_notwine, 1 uncertain`.
    - Gemini real sobre os 53 needs: 53 wine, 48 post_ready, 5 post_uncertain, ~8594 tokens (Flash Lite).
    - Guardrail reprocessado via `--from-raw`: **Two Birds One Stone Carignan** detectado (URL `/vin-fr-`, Gemini dizia `pais=cl`) → **desceu de ready para uncertain**. Final: **47 enriched_ready**, 6 uncertain, 1 qa_conflict.
    - QA pre-apply: 0 blocker, 23 review (todos falsos-positivos de `Chateau X` Bordeaux), 24 ok.
    - **Apply pequeno autorizado e executado**: 44 inserted + 3 updated, errors=[], zero Two Birds, zero uncertain aplicado.
    - QA pos-apply: 0 violacoes de campos minimos, smoke de leitura 3/3 verde, `score_recalc_queue` drenada (pending=0).
11. **Mudancas DQ V3 (terceiros)** integradas ao codigo: `backend/services/bulk_ingest.py` e `backend/routes/ingest.py` ganharam suporte a `sources: [...]` → `wine_sources` + `run_id` + `ingestion_run_log` + `not_wine_rejections`. Migration 018 nao foi aplicada nesta sessao.
12. **Nenhum commit/push/deploy** disparado. Mudancas locais aguardam commit seletivo (4 perguntas pendentes no `CLAUDE_RESPOSTAS_2026-04-21_0825.md`).

---

## 2. Estado do repositorio

### 2.1 Git

- `origin/main` esta em `fa33bb24 Add audited bulk ingest pipeline` (bulk_ingest pre-auditoria).
- Branch local atual: `i18n/onda-2`.
- Mudancas **nao commitadas** criadas nesta sessao:

| Caminho | Tipo | Descricao |
|---|---|---|
| `backend/services/bulk_ingest.py` | **MODIFICADO** | Refatorado `_resolve_existing` (retorna `hash_to_id`), substituido `_UPSERT_SQL` por `_INSERT_SQL`+`_UPDATE_SQL`, `total_fontes=0` no INSERT. |
| `backend/tests/test_bulk_ingest.py` | **MODIFICADO** | Runner com `SKIP/FAIL/ABORT` + modo `REQUIRE_DB_TESTS=1`; `test_process_bulk_dedup_in_input` renomeado pra `test_db_process_bulk_dedup_in_input`; +3 testes de regressao. |
| `scripts/_ingest_classifier.py` | **NOVO** | Classificador deterministico puro (Fase 1). |
| `scripts/pre_ingest_router.py` | **NOVO** | Router operacional (Fase 2) com hardening. |
| `scripts/export_vinhos_brasil_to_router.py` | **NOVO** | Ponte read-only com `vinhos_brasil_db`. |
| `backend/tests/test_ingest_classifier.py` | **NOVO** | 30 testes offline do classifier. |
| `backend/tests/test_pre_ingest_router.py` | **NOVO** | 37 testes do router (parametrizados + CLI subprocess). |
| `reports/WINEGOD_PRE_INGEST_ROUTER_ANALISE.md` | **NOVO** | Analise tecnica do fluxo bifurcado. |
| `reports/WINEGOD_PRE_INGEST_ROUTER_RUNBOOK.md` | **NOVO** | Runbook operacional. |
| `reports/WINEGOD_PRE_INGEST_ROUTER_HANDOFF_OFICIAL.md` | **NOVO** | Este arquivo. |
| `reports/ingest_pipeline_inputs/20260421_113807_vinhos_brasil_vtex.jsonl` | **NOVO** | Smoke de 500 items vtex exportados. |
| `CLAUDE_RESPOSTAS_2026-04-21_0825.md` | **NOVO** | Arquivo de respostas desta sessao (historico cronologico). |

### 2.2 Producao (Render)

- Backend web service: `https://winegod-app.onrender.com`.
- Endpoint `/api/ingest/bulk` ativo. Env `BULK_INGEST_TOKEN` setado.
- Smoke (3 checks: 401 sem token, 400 payload invalido, 200 dry-run com 1 item) retornou `overall_ok: true`.
- **Deploy atual e o commit `fa33bb24`**: inclui o bulk_ingest corrigido **apenas ate o contrato do commit**. As correcoes extras desta sessao (legacy hash guard em `_resolve_existing`, `total_fontes=0`, runner strict) **NAO estao em producao** ate um novo push + Manual Deploy.

---

## 3. Cronologia detalhada da sessao

Ordem cronologica do que aconteceu (mais antigo primeiro), com evidencias e artefatos.

### 3.1 Auditoria do bulk_ingest — bug de duplicata

**Problema identificado**: `_resolve_existing()` detectava match por tripla normalizada `(produtor, nome, safra)`, mas `_apply_batch` usava `INSERT ... ON CONFLICT (hash_dedup)`. Se um wine legado estava no banco com `hash_dedup='legacyX'` e o payload novo gerava `hash='newY'`, o `ON CONFLICT` nao disparava — o INSERT sucedia criando duplicata, mesmo com dry-run indicando `would_update`.

**Correcao** em `backend/services/bulk_ingest.py`:
- `_resolve_existing(conn, batch)` agora retorna `(existing_hashes_set, hash_to_id_map)`.
- `_apply_batch` faz `UPDATE WHERE id = %s` com `COALESCE(wines.x, EXCLUDED.x)` quando ha match. `INSERT ... ON CONFLICT DO NOTHING RETURNING id` so no caso genuinamente novo (race-safe).
- `hash_dedup` existente nao-nulo **nunca** e sobrescrito. Se for `NULL/''`, completa.

**Teste de regressao**: `test_db_legacy_hash_does_not_create_duplicate` injeta wine com `legacy_hash`, manda payload com mesma tripla mas hash diferente, valida que COUNT nao cresce, id preservado, regiao mergeada.

### 3.2 Auditoria do bulk_ingest — bug semantico `total_fontes`

**Problema identificado**: `_UPSERT_SQL` original fazia `total_fontes = wines.total_fontes + 1` no UPDATE, e iniciava com `1` no INSERT. Dois defeitos:
1. Reapply do mesmo payload inflava o contador (sem nova fonte real).
2. Iniciava com `1` mesmo quando `bulk_ingest` nao cria linha em `wine_sources`.

**Evidencias consultadas**:
- `scripts/import_render_z.py:481-590` carrega `wines_clean.total_fontes` de origens comerciais (`wine_sources`).
- `backend/services/new_wines.py:387` (chat auto-create) insere com `total_fontes = 0`.
- `frontend/components/wine/WineCard.tsx` renderiza `total_fontes` como "loja/lojas".
- `reports/tail_base_summary_2026-04-10.md` documenta divergencia entre `wines.total_fontes` e `wine_sources_count_live`.

**Correcao**:
- UPDATE nao mexe em `total_fontes` (preserva valor existente).
- INSERT inicia com `total_fontes = 0` (alinhado com `new_wines.py`).
- `fontes` tem merge deduplicado: `wines.fontes || fontes_novas` so se `NOT @>`.

**Testes de regressao**:
- `test_db_reapply_does_not_inflate_total_fontes`: 4 ingestoes, final `total_fontes = 0` e `len(fontes) = 1`.
- `test_db_new_bulk_insert_starts_with_zero_fontes`: novo bulk nao conta como "1 loja".

### 3.3 Runner de testes — SKIP/FAIL/ABORT + strict

**Problema identificado**: `_db_available()` cacheava em runtime, `if not _db_available(): return` era contado como PASS (enganoso). `test_process_bulk_dedup_in_input` era tratado como offline mas chamava `process_bulk` (que consulta banco).

**Correcao em `backend/tests/test_bulk_ingest.py`**:
- Introduzido `class _Skip(Exception)` e `class DBUnavailable(Exception)`.
- `_skip_if_no_db()` levanta `_Skip` em modo default, `DBUnavailable` com `REQUIRE_DB_TESTS=1`.
- Runner custom agora conta `passed/skipped/failed`. Output: `"X passed, Y skipped, Z failed (strict mode)"`.
- `test_process_bulk_dedup_in_input` renomeado pra `test_db_process_bulk_dedup_in_input` (DB-dependent).

**Exit codes validados nos 4 paths**:

| DB ok? | `REQUIRE_DB_TESTS=1`? | Saida | Exit |
|---|---|---|---|
| Sim | Nao | `16 passed, 0 skipped, 0 failed` | 0 |
| Sim | Sim | `16 passed, 0 skipped, 0 failed (strict mode)` | 0 |
| Nao | Nao | `10 passed, 6 skipped, 0 failed` | 0 |
| Nao | Sim | `ABORTADO: modo strict exige DB` | 1 |

### 3.4 Documentos atualizados apos auditoria

- `reports/WINEGOD_PAIS_RECOVERY_HANDOFF_OFICIAL.md` — secao "Correcoes pos-auditoria" adicionada; breakdown dos testes atualizado de "13 originais + 3 regressao" para "10 offline + 6 DB" com nota de `REQUIRE_DB_TESTS=1`.
- `reports/WINEGOD_PAIS_RECOVERY_BULK_INGEST_ROLLOUT_RUNBOOK.md` — secao 2 passou a documentar os 2 modos (default e strict).

---

### 3.5 Piloto real vtex (ponta a ponta)

**Export**:
```
python scripts/export_vinhos_brasil_to_router.py --fonte vtex --limit 500
```
Saida: `reports/ingest_pipeline_inputs/20260421_113807_vinhos_brasil_vtex.jsonl`
500 items, 89% com produtor, 66% com EAN, 88% ready-like.

**Router**: 406 ready + 53 needs_enrichment + 40 rejected_notwine + 1 uncertain.

**Fase 4 Gemini real** (53 items autorizados):
```
python scripts/enrich_needs.py --input ...needs_enrichment.jsonl --source ... --limit 53 --confirm-gemini
```
Resultado: 53 wine (0 not_wine/spirit/unknown), ~8594 tokens Flash Lite (custo baixo), 48 post_ready, 5 post_uncertain.

**Alucinacao detectada por terceiro (Codex)**: `Two Birds One Stone Carignan` (URL `/vin-fr-` + descricao "Vin de France") virou ready com Gemini dizendo `pais=cl, regiao=Valle del Maule`.

**Guardrail factual implementado** em `scripts/enrich_needs.py`:
- `_extract_country_hint_from_url` — padrao WorldWine `/vin-XX-` com mapa conservador.
- `_extract_country_hint_from_text` — evidencia textual forte (Vin de France, Languedoc, Bordeaux, Rioja, Toscana, etc).
- `_collect_source_hints` — ordem `pais` original > URL > descricao/regiao/nome.
- `_detect_country_conflict` — retorna `{gemini_pais, source_hint_pais, source_hint_reason}`.
- Em `classify_post_enrichment`, se conflito: bucket `enriched_uncertain`, razoes `qa_conflict:country_hint_mismatch; gemini_pais=...; source_hint_pais=...; source_hint_reason=...`. NAO faz merge do pais conflitante.
- Novo contador `qa_conflicts` no summary.

**Reprocessamento com guardrail via `--from-raw`** (zero novo custo Gemini):
```
python scripts/enrich_needs.py --input ...needs_enrichment.jsonl --source vinhos_brasil_vtex_20260421_113807_guarded --limit 53 --from-raw ...raw_gemini_response.jsonl
```
Resultado: 47 post_ready (Two Birds saiu), 6 post_uncertain, 1 qa_conflict.

**QA pre-apply** (`scripts/_audit_enriched_ready.py`): 0 blocker, 23 review (todos falsos-positivos `Chateau X = Domaine X` Bordeaux legitimo), 24 ok. Relatorio em `reports/WINEGOD_PRE_INGEST_ENRICHED_READY_QA_20260421.md` + CSV detalhado.

---

### 3.6 Apply pequeno e pos-apply

**Apply autorizado e executado**:
```
python scripts/ingest_via_bulk.py \
  --input reports/ingest_pipeline_enriched/20260421_120957_vinhos_brasil_vtex_20260421_113807_guarded/enriched_ready.jsonl \
  --source vinhos_brasil_vtex_20260421_113807_guarded_qa \
  --apply
```
Resultado: `received=47, valid=47, inserted=44, updated=3, errors=[]`.

**Checklist SQL pos-apply**:
- 47 wines com `fontes @> '["bulk_ingest:vinhos_brasil_vtex_20260421_113807_guarded_qa"]'`.
- 0 wines com sources nao-autorizados (`_guarded`, `_enriched`).
- Two Birds com source QA: 0 (guardrail funcionou).
- Uncertain com source QA: 0/6.
- Amostra 5: todos franceses, regioes coerentes, `pais=fr`.

**QA de estabilidade** (relatorio em `reports/WINEGOD_PRE_INGEST_POST_APPLY_QA_20260421.md`):
- 0/47 violacoes de campos minimos.
- Smoke de leitura via `services.wine_search.find_wines` retornou 3/3 wines do lote com `pais_display="França"` e `display_note` calculado.

**Drain da `score_recalc_queue`**:
```
python scripts/drain_score_queue.py
# [drain] FILA ZERADA. Concluido em 2s (0 rodadas).
```
`pending = 0`. Os 2816 na tabela sao historico processado (`processed_at IS NOT NULL`). Amostra de 5 wines do lote QA apos drain: todos com `winegod_score` contextual calculado (3.15 a 3.66).

---

### 3.7 Integracao DQ V3 (mudancas externas no bulk_ingest)

Apos o fluxo principal da sessao, `backend/services/bulk_ingest.py` e `backend/routes/ingest.py` foram expandidos (por um patch externo/Codex) com DQ V3 Escopo 1+2:

- Campo `sources: [{store_id, url, preco, moeda, disponivel, external_id}]` aceito por item. Apos resolver `wine_id`, grava/atualiza `wine_sources` com `ON CONFLICT (wine_id, store_id, url) DO UPDATE`.
- Parametro `run_id` opcional no CLI/endpoint. Marca `wines.ingestion_run_id` e `wine_sources.ingestion_run_id`, persiste stats em `ingestion_run_log`.
- NOT_WINE rejections persistidas em `not_wine_rejections`.
- Todas operacoes de tracking degradam graciosamente se migration 018 nao estiver aplicada (checa `information_schema` e pula).
- Testes novos em `backend/tests/test_bulk_ingest.py`: `_validate_source`, `sources` mixed rejected/valid, contadores `sources_in_input/would_insert_sources/sources_inserted`, etc.

**Migration 018 (`database/migrations/018_ingestion_guardrail.sql`) NAO FOI APLICADA** nesta sessao. Tracking de `sources`/`run_id` fica inerte no banco atual ate a migration rodar.

---

### 3.5 Validacao operacional do endpoint em producao

- Executado smoke de producao contra `https://winegod-app.onrender.com/api/ingest/bulk`.
- `overall_ok: true`, `no_token_401=401`, `bad_payload_400=400`, `dry_run_200=200` com `received=1, valid=1, would_insert=1`.
- Commit `fa33bb24` confirmado em `origin/main`. URL canonica em `DEPLOY.md:47-105`.

### 3.6 Piloto dry-run sintetico (validacao do pipeline)

Gerado arquivo sintetico de 265 items (150 reais do banco + 100 ficticios + 10 not_wine + 5 invalidos) e rodado via `scripts/ingest_via_bulk.py` (sem `--apply`):
- `received=265`, `valid=250 (94.3%)`, `would_insert=102`, `would_update=148`, `filtered_notwine=10`, `rejected=5`.
- 10/10 `would_update` amostrados bateram por tripla com `id` unico casado.
- 10/10 `would_insert` eram os ficticios com marker `PilotoSint20260421`.
- Arquivo **removido apos validacao** pra evitar apply acidental.

### 3.7 Analise tecnica do fluxo bifurcado

Criado `reports/WINEGOD_PRE_INGEST_ROUTER_ANALISE.md` com 12 secoes:
- Contexto, fluxo proposto, regras objetivas dos 4 status, schema de enrichment, onde mora, persistencia (arquivos vs tabela), plano em 7 fases, riscos, estado atual, discordancias, handoff pro Codex, decisoes pendentes.

Decisoes do gate humano (aplicadas):
- `nome_vazio_ou_curto` nao vira NOT_WINE automatico quando ha EAN/produtor (cai em uncertain/needs_enrichment).
- `Sparkling` sozinho tratado como nao-ingestivel (ja esta em `wine_filter.py`).
- `has_strong_name = 3+ tokens significativos` aprovado.
- Lista curta de 16 uvas em `_NON_GENERIC_EXAMPLES` aprovada.
- Tokens curtos (<=2) ignorados aprovado.
- Termos genericos PT-BR (`tinto`, `branco`, `rosado`) incluidos.
- `uncertain_pct > 20%` gera warning visivel mas nao bloqueia.
- `uncertain_review` e CSV.
- Revisao humana e saida lateral, nunca gate.

### 3.8 Fase 1 — classificador deterministico

**Arquivo**: `scripts/_ingest_classifier.py`

Contrato: `classify(item: dict) -> tuple[str, list[str]]` com `status ∈ {ready, needs_enrichment, not_wine, uncertain}`.

Pureza: sem banco, sem HTTP, sem Gemini, sem side effects.

Regras implementadas:
1. **NOT_WINE** via `pre_ingest_filter.should_skip_wine`, exceto `nome_vazio_ou_curto` (cai em uncertain).
2. **READY** (AND): nome >= 8, produtor >= 3, nome nao-generico, pelo menos uma ancora geo (`pais`/`regiao`/`sub_regiao`/`ean_gtin`).
3. **UNCERTAIN** duro: nome+produtor+EAN vazios; nome curto sem EAN/produtor; nome generico sem produtor nem EAN.
4. **NEEDS_ENRICHMENT** com ancoras: nome forte sem produtor; produtor sem geo; EAN com nome fraco; descricao >=100; pista de uva/regiao; produtor compensando nome generico.
5. Fallback: UNCERTAIN.

`GENERIC_TERMS` (20 termos): `red/white/blanc/blanco/bianco/rouge/rosso/rose/rosé/blend/reserva/reserve/brut/cuvee/cuvée/house/wine/vino/vin/wein/sparkling/tinto/branco/rosado`.

**Testes**: 30 em `backend/tests/test_ingest_classifier.py`. Cobrem 5 READY + 7 NEEDS + 8 NOT_WINE + 6 UNCERTAIN + 4 edges. Rodam tanto com runner custom quanto pytest.

### 3.9 Fase 2 — router + hardening

**Arquivo**: `scripts/pre_ingest_router.py`

CLI: `--input <file.jsonl>`, `--source <nome>`, `--out-dir`, `--timestamp`.

**Hardening aplicado nesta sessao** (3 itens):

1. **Sanitizacao de `--source`** via `_validate_source()`: so `[A-Za-z0-9_.-]`; rejeita `..`, `/`, `\`, whitespace, acentos. Erros informativos (`source_invalido: path_traversal`, `contem_barra`, `contem_espaco`, `so_aceita_...`).

2. **Default `--out-dir` ancorado em repo root**: `_REPO_ROOT / reports/ingest_pipeline`. Independente de CWD.

3. **Diretorio so criado apos validacao**: ordem `_validate_source → _read_jsonl → mkdir`. Erro de input/source nao vaza dir vazio.

**Saidas** em `reports/ingest_pipeline/<timestamp>_<source>/`:
- `ready.jsonl` — compativel com `ingest_via_bulk.py`
- `needs_enrichment.jsonl`
- `rejected_notwine.jsonl`
- `uncertain_review.csv` (header: `router_index,source,nome,produtor,safra,pais,regiao,sub_regiao,ean_gtin,reasons,raw_json`)
- `summary.md` com contadores + WARNING se `uncertain_pct > 20%`

**Metadados** (preservados, nao destrutivos):
- `_router_status`, `_router_reasons`, `_router_source`, `_router_index`

**Exit codes**: 0 sempre que processou (mesmo com uncertain > 0); 1 em erros reais.

**Testes**: 37 em `backend/tests/test_pre_ingest_router.py`. Cobertura:
- Roteamento pros 4 buckets
- 5 arquivos criados
- Metadados e compat com `ingest_via_bulk.py`
- CSV com header correto e `raw_json` sem metadados
- summary.md com contadores e WARNING
- Linhas em branco ignoradas
- 5 tipos de erro de input (inexistente, JSONL invalido, linha nao-objeto, source invalido, source vazio)
- CLI via subprocess (exit 0 e exit 1)
- **Parametrizados**: 12 variantes de source sanitizacao (8 invalidos + 1 controle + 5 validos)
- Anchoring de `--out-dir` com `monkeypatch.chdir`
- 3 testes "erro nao cria dir"

**Resultado combinado Fase 1 + Fase 2**: `pytest backend/tests/test_ingest_classifier.py backend/tests/test_pre_ingest_router.py -q` → **67 passed in 5.89s**.

### 3.10 Runbook operacional do router

**Arquivo**: `reports/WINEGOD_PRE_INGEST_ROUTER_RUNBOOK.md`

10 secoes cobrindo:
1. Objetivo
2. Fluxo (diagrama ASCII)
3. Pre-requisitos (formato JSONL, campos aceitos, regras `--source`)
4. Comando + flags + exit codes + JSON stdout
5. Estrutura das saidas + metadados
6. Interpretacao dos 4 buckets
7. Como rodar Fase 3 (dry-run sem `--apply`)
8. Criterios go/no-go
9. O que NAO fazer (7 itens)
10. Rollback/limpeza (smoke pode apagar, lote real mantem ate fechamento)

### 3.11 Ponte com base legada vinhos_brasil_db

**Arquivo**: `scripts/export_vinhos_brasil_to_router.py`

Contexto: o Codex auditou `C:\natura-automation\vinhos_brasil\` e encontrou base `vinhos_brasil_db` com 146.591 wines + 165.146 linhas em `vinhos_brasil_fontes`. Fontes reais: `vtex, magento, loja_integrada, dooca, tray, mercadolivre, woocommerce, shopify, mistral, sonoma, wine_com_br, evino, nuvemshop, videiras, tenda, amazon, vivino_br, vtex_io, generico, html`.

Contrato do exportador:
- Import via `sys.path.insert(0, r"C:\natura-automation\vinhos_brasil")` + `from db_vinhos import get_connection`.
- **Somente leitura**: `SET TRANSACTION READ ONLY` na transacao.
- **Nao imprime DSN**: mensagens de erro so mostram classe da excecao.
- LEFT JOIN LATERAL com `vinhos_brasil_fontes` (1 linha representativa por wine).
- Com `--fonte X`, filtra E exige `EXISTS` em `vinhos_brasil_fontes`.

Flags:
- `--limit N` (default 500, >500 exige `--allow-large`)
- `--fonte` (filtro opcional por scraper)
- `--out PATH`
- `--min-quality ready_like` (filtra no SQL: nome>=8, produtor>=3, ancora geo)
- `--allow-large`

Campos exportados: `nome, produtor, safra (str YYYY), tipo, pais (ISO-2 lower), regiao, sub_regiao, uvas (JSON), ean_gtin, imagem_url, harmonizacao, descricao, preco_min, preco_max, moeda`.

Metadados de linhagem: `_origem_vinho_id, _source_dataset=vinhos_brasil_db, _source_table=vinhos_brasil, _source_scraper, _fonte_original (URL), _preco_fonte, _mercado`.

Normalizacoes:
- `safra INTEGER` → string `"YYYY"` compativel.
- `pais` → ISO-2 lowercase.
- `uvas JSONB` → string JSON de lista.
- `preco_*` → float.
- Chaves `None` removidas.

### 3.12 Smoke do exportador em vtex

```bash
python scripts/export_vinhos_brasil_to_router.py --fonte vtex --limit 500
```

Saida:
```json
{
  "out_path": "C:/winegod-app/reports/ingest_pipeline_inputs/20260421_113807_vinhos_brasil_vtex.jsonl",
  "fonte_filter": "vtex",
  "min_quality": null,
  "limit_requested": 500,
  "total_written": 500,
  "with_produtor": 447,
  "with_pais": 197,
  "with_ean": 330,
  "ready_like_estimate": 440,
  "next_step_cmd": "python scripts/pre_ingest_router.py --input C:/winegod-app/reports/ingest_pipeline_inputs/20260421_113807_vinhos_brasil_vtex.jsonl --source vinhos_brasil_vtex_20260421_113807"
}
```

Leitura:
- 500 items exportados num unico JSONL.
- 89,4% com produtor, 39,4% com pais ISO, 66% com EAN.
- Estimativa client-side: ~88% viram `ready` no router (consistente com piloto manual anterior 406/500 aprovados).

### 3.13 Fase 4 entregue — Gemini + guardrail factual

`scripts/enrich_needs.py` implementado reutilizando `backend/services/enrichment_v3.enrich_items_v3` + `to_auto_create_enriched` (sem integracao Gemini paralela). Detalhes do guardrail, do `--from-raw` e dos 43 testes estao nas secoes **3.5** e **3.6**.

---

## 4. Estado das fases do plano

| Fase | Objetivo | Status | Artefato |
|---|---|---|---|
| **0** | Auditoria do fluxo linear | OK | `reports/WINEGOD_PRE_INGEST_ROUTER_ANALISE.md` |
| **1** | Classificador deterministico | OK | `scripts/_ingest_classifier.py` + 30 testes |
| **2** | Router operacional + hardening | OK | `scripts/pre_ingest_router.py` + 37 testes + runbook |
| **2.5** | Ponte com base legada | OK | `scripts/export_vinhos_brasil_to_router.py` + 35 testes + smoke 500 vtex |
| **3** | Dry-run real via `ingest_via_bulk.py` | OK | `scripts/ingest_via_bulk.py` rodado 2x (apos Gemini e apos guardrail) |
| **4** | Gemini em `needs_enrichment.jsonl` | OK | `scripts/enrich_needs.py` + 43 testes + guardrail factual + `--from-raw` |
| **5** | 2o filtro pos-enrichment + uncertain_review | OK | integrado no proprio `enrich_needs.py` (`classify_post_enrichment` + `_detect_country_conflict`) |
| **6** | `bulk_ingest` do `enriched_ready` | OK | apply pequeno autorizado: 44 inserted + 3 updated, source `vinhos_brasil_vtex_20260421_113807_guarded_qa` |
| **7** | Automacao (cron/trigger) | nao iniciado | fora de escopo desta sessao |

---

## 5. Contadores de teste consolidados

```bash
# Todos os testes do pipeline novo (classifier + router) — sem dependencia de DB
python -m pytest backend/tests/test_ingest_classifier.py backend/tests/test_pre_ingest_router.py -q
# 67 passed in 5.89s  (30 + 37)

# Testes do bulk_ingest (misto offline + DB)
cd backend && REQUIRE_DB_TESTS=1 python -m tests.test_bulk_ingest
# 16 passed, 0 skipped, 0 failed (strict mode)   ← com DB
# 10 passed, 6 skipped, 0 failed                 ← sem DB
```

---

## 6. Arquivos e paths importantes

### 6.1 Codigo

| Arquivo | Proposito |
|---|---|
| `backend/services/bulk_ingest.py` | Pipeline final de gravacao (auditado nesta sessao, nao commitado) |
| `backend/routes/ingest.py` | Endpoint HTTP `POST /api/ingest/bulk` com `X-Ingest-Token` |
| `backend/services/new_wines.py` | Chat auto-create (referencia de prompt Gemini, nao modificado) |
| `scripts/ingest_via_bulk.py` | CLI consumidor de JSONL → bulk_ingest (dry-run default) |
| `scripts/smoke_bulk_ingest_endpoint.py` | Smoke 401/400/200 do endpoint |
| `scripts/wine_filter.py` | 400+ regex NOT_WINE multilingua |
| `scripts/pre_ingest_filter.py` | 6 regras procedurais (ABV, volume, kit, data) |
| `scripts/_ingest_classifier.py` | **NOVO**: classificador deterministico |
| `scripts/pre_ingest_router.py` | **NOVO**: router operacional |
| `scripts/export_vinhos_brasil_to_router.py` | **NOVO**: ponte legado → router |

### 6.2 Testes

| Arquivo | Testes | Obs |
|---|---|---|
| `backend/tests/test_bulk_ingest.py` | 16+ (10 offline + 6 DB base, mais DQ V3) | `REQUIRE_DB_TESTS=1` ativa strict |
| `backend/tests/test_ingest_classifier.py` | 30 offline | Fase 1 |
| `backend/tests/test_pre_ingest_router.py` | 37 (parametrizados) | Fase 2 + hardening |
| `backend/tests/test_export_vinhos_brasil_to_router.py` | 35 offline | Ponte legado |
| `backend/tests/test_enrich_needs.py` | 43 offline com mock Gemini | Fase 4 + guardrail |

### 6.3 Documentacao

| Arquivo | Proposito |
|---|---|
| `reports/WINEGOD_PAIS_RECOVERY_HANDOFF_OFICIAL.md` | Handoff do bulk_ingest (existia antes, atualizado com pos-auditoria) |
| `reports/WINEGOD_PAIS_RECOVERY_BULK_INGEST_ROLLOUT_RUNBOOK.md` | Runbook do bulk_ingest em producao |
| `reports/WINEGOD_PRE_INGEST_ROUTER_ANALISE.md` | Analise tecnica do fluxo bifurcado |
| `reports/WINEGOD_PRE_INGEST_ROUTER_RUNBOOK.md` | Runbook operacional do router (inclui secao 11 para base legada) |
| `reports/WINEGOD_PRE_INGEST_ROUTER_HANDOFF_OFICIAL.md` | ESTE arquivo |
| `reports/WINEGOD_PRE_INGEST_ENRICHED_READY_QA_20260421.md` + `.csv` | QA pre-apply dos 47 guarded |
| `reports/WINEGOD_PRE_INGEST_POST_APPLY_QA_20260421.md` | QA pos-apply + drain |
| `CLAUDE_RESPOSTAS_2026-04-21_0825.md` | Historico cronologico de respostas da sessao (nao commitar) |

### 6.4 Dados gerados nesta sessao

| Arquivo | O que e | Pode apagar? |
|---|---|---|
| `reports/ingest_pipeline_inputs/20260421_113807_vinhos_brasil_vtex.jsonl` | 500 items exportados do vtex | Sim apos apply; lote real manter |
| `reports/ingest_pipeline/20260421_114405_vinhos_brasil_vtex_20260421_113807/` | Saida do router (ready/needs/notwine/uncertain/summary) | Manter como trilha de auditoria |
| `reports/ingest_pipeline_enriched/20260421_115754_.../` | Gemini real (pre-guardrail) | Manter como raw audit |
| `reports/ingest_pipeline_enriched/20260421_120957_..._guarded/` | **Lote aplicado** (47 enriched_ready + 6 uncertain + raw) | **Manter** ate fechamento |

### 6.5 Base externa

| Path | Conteudo |
|---|---|
| `C:\natura-automation\vinhos_brasil\db_vinhos.py` | `get_connection()` + schema de 3 tabelas |
| `vinhos_brasil_db` (DATABASE_URL via env `VINHOS_CATALOGO_DATABASE_URL` ou `VINHOS_BRASIL_DATABASE_URL`) | 146.591 wines + 165.146 linhas em `vinhos_brasil_fontes` |

---

## 7. Como retomar — cenarios operacionais

### Cenario A — Novo lote ponta a ponta (outra fonte ou offset)

```bash
cd C:\winegod-app

# 1. Export (exemplo: evino)
python scripts/export_vinhos_brasil_to_router.py --fonte evino --limit 500
# (ou --fonte vtex --limit 500 --offset 500 pra paginar o vtex)

# 2. Router
python scripts/pre_ingest_router.py \
  --input reports/ingest_pipeline_inputs/<arquivo>.jsonl \
  --source vinhos_brasil_<fonte>_<timestamp>

# 3. Enrichment Gemini dos needs_enrichment (com --confirm-gemini explicito)
python scripts/enrich_needs.py \
  --input reports/ingest_pipeline/<router_out>/needs_enrichment.jsonl \
  --source vinhos_brasil_<fonte>_<timestamp> \
  --limit <N> \
  --confirm-gemini

# 4. Se encontrar alucinacoes, reprocessar com guardrails (sem novo custo Gemini)
python scripts/enrich_needs.py \
  --input ...needs_enrichment.jsonl \
  --source vinhos_brasil_<fonte>_<timestamp>_guarded \
  --limit <N> \
  --from-raw reports/ingest_pipeline_enriched/<out>/raw_gemini_response.jsonl

# 5. QA pre-apply (0 blocker obrigatorio)
python scripts/_audit_enriched_ready.py \
  --input reports/ingest_pipeline_enriched/<guarded_out>/enriched_ready.jsonl \
  --md reports/WINEGOD_PRE_INGEST_ENRICHED_READY_QA_<date>.md \
  --csv reports/WINEGOD_PRE_INGEST_ENRICHED_READY_QA_<date>.csv

# 6. Dry-run do bulk_ingest
python scripts/ingest_via_bulk.py \
  --input reports/ingest_pipeline_enriched/<guarded_out>/enriched_ready.jsonl \
  --source vinhos_brasil_<fonte>_<timestamp>_guarded_qa

# 7. Apply pequeno (apenas com autorizacao humana explicita)
python scripts/ingest_via_bulk.py --input ... --source ..._guarded_qa --apply

# 8. Pos-apply: SQL checklist + drain
python scripts/drain_score_queue.py
```

### Cenario B — Aplicar migration 018 (DQ V3 wine_sources/run_id)

Migration pendente: `database/migrations/018_ingestion_guardrail.sql`. Enquanto nao rodar, `sources`/`run_id` sao aceitos no payload mas o tracking degrada graciosamente.

Quando autorizado:
- Aplicar migration no banco Render (batch 10k se houver ALTER TABLE grande — REGRA 5).
- Verificar `information_schema` pra confirmar colunas criadas.
- Rodar suite com DB em modo strict e confirmar que testes de `sources` passam com persistencia real.

```bash
python scripts/export_vinhos_brasil_to_router.py --fonte evino --limit 500
python scripts/export_vinhos_brasil_to_router.py --fonte mistral --limit 500
python scripts/export_vinhos_brasil_to_router.py --fonte mercadolivre --limit 500
# etc
```

Cada execucao gera novo arquivo em `reports/ingest_pipeline_inputs/`. Rodar router em cada um separadamente pra comparar taxa de `ready / needs / not_wine / uncertain` por scraper.

### Cenario D — Commit + push seletivo das mudancas desta sessao

**Requer autorizacao explicita do usuario** (REGRA 1). 22 arquivos propostos (7 scripts novos, 4 testes novos, 5 backend modificados, 6 docs novos). Lista completa em `CLAUDE_RESPOSTAS_2026-04-21_0825.md`.

- NAO usar `git add .` — ha muitos arquivos de outras sessoes/workspaces nao relacionados.
- Adicionar arquivo-a-arquivo.
- NAO commitar `reports/ingest_pipeline*/` (dados), `CLAUDE_RESPOSTAS_*.md` (historico), nem arquivos de outras sessoes (chat.py, baco.py, wine_filter.py, frontend/*, prompts/* etc).
- Antes do `git commit`: rodar `python -m pytest backend/tests/test_ingest_classifier.py backend/tests/test_pre_ingest_router.py backend/tests/test_enrich_needs.py backend/tests/test_export_vinhos_brasil_to_router.py -q` e `cd backend && REQUIRE_DB_TESTS=1 python -m tests.test_bulk_ingest`.
- Apos push + merge em `main`, disparar Manual Deploy no Render (REGRA 7) pra que `bulk_ingest` (com fix de duplicata + `total_fontes=0` + integracao DQ V3) chegue em producao.

### Cenario E — Aplicar outro lote do mesmo source

Se quiser aplicar outro slice do vtex (offset diferente), use o mesmo template do Cenario A mudando apenas `--offset` no export. Gate humano obrigatorio antes de cada `--apply`.

---

## 8. Decisoes pendentes (acao humana necessaria)

1. **Commit seletivo** das mudancas desta sessao — 4 perguntas pendentes no topo do `CLAUDE_RESPOSTAS_2026-04-21_0825.md`: (a) lista de arquivos OK? (b) incluir migration `018_ingestion_guardrail.sql`? (c) 1 commit unico ou 3? (d) mensagem de commit aprovada?
2. **Aplicar migration 018** para ativar `wine_sources`/`run_id`/`ingestion_run_log`/`not_wine_rejections` no banco de producao.
3. **Proximo lote**: outra fonte (evino/mistral/mercadolivre/wine_com_br) ou offset maior do vtex.
4. **Parser descricao apply** (pendente de sessao anterior — 53k wines sem `teor_alcoolico` que podem ser preenchidos sem sobrescrever): autoriza?

---

## 9. Regras aplicaveis permanentes

Do projeto (`CLAUDE.md`):
- **REGRA 1**: sem commit/push sem autorizacao; nunca `git add .`.
- **REGRA 2**: zero UPDATE/DELETE no banco alem dos testes isolados.
- **REGRA 5**: Render tem pouca memoria; batches de 10k (BULK_INGEST_BATCH_SIZE).
- **REGRA 6**: Gemini exige autorizacao explicita + custo controlado.
- **REGRA 7**: deploy no Render e manual (nao ha CI/CD automatico).
- **REGRA 8**: nomes de handoff/runbook/decisoes usam prefixo `WINEGOD_<SUBPROJETO>_*`. Este arquivo segue.

Da memoria do usuario:
- Fases pequenas auditadas com gate humano entre elas.
- NOT_WINE patterns novos vao pros 2 arquivos (`wine_filter.py` E `pre_ingest_filter.py`).
- Respostas acumuladas em `CLAUDE_RESPOSTAS_<timestamp>.md` por sessao.
- `pais` ISO e canonico; `pais_display` via `utils.country_names.iso_to_name`.
- Nao logar tokens/secrets/DATABASE_URL.

---

## 10. Apendice — comandos de verificacao rapida

```bash
cd C:\winegod-app

# Verificar que o exportador compila
python -m py_compile scripts/export_vinhos_brasil_to_router.py

# Verificar que o pipeline novo compila
python -m py_compile scripts/_ingest_classifier.py scripts/pre_ingest_router.py \
  scripts/enrich_needs.py scripts/export_vinhos_brasil_to_router.py \
  scripts/_audit_enriched_ready.py

# Rodar toda a suite do pipeline novo (sem DB)
python -m pytest backend/tests/test_ingest_classifier.py \
  backend/tests/test_pre_ingest_router.py \
  backend/tests/test_enrich_needs.py \
  backend/tests/test_export_vinhos_brasil_to_router.py -q
# Esperado: 145 passed

# Rodar bulk_ingest strict (exige DB acessivel)
cd backend && REQUIRE_DB_TESTS=1 python -m tests.test_bulk_ingest

# Smoke do endpoint em producao (exige BULK_INGEST_TOKEN no terminal, sem logar)
python scripts/smoke_bulk_ingest_endpoint.py --base-url https://winegod-app.onrender.com
# Esperado: overall_ok: true

# Verificar status da score_recalc_queue
python scripts/drain_score_queue.py status
# Esperado: fila pendente: 0

# Verificar wines do lote aplicado
python - <<'EOF'
import os, psycopg2
from urllib.parse import urlparse
from dotenv import load_dotenv
load_dotenv('backend/.env')
u = urlparse(os.environ['DATABASE_URL'])
conn = psycopg2.connect(host=u.hostname, port=u.port, database=u.path[1:],
                        user=u.username, password=u.password)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM wines WHERE fontes @> jsonb_build_array('bulk_ingest:vinhos_brasil_vtex_20260421_113807_guarded_qa')")
print('lote_qa_applied:', cur.fetchone()[0])  # esperado: 47
conn.close()
EOF
```

---

## 11. Historico em uma linha

`bulk_ingest auditado (duplicata + total_fontes) → runner strict → fluxo bifurcado desenhado → classifier Fase 1 (30 testes) → router Fase 2 + hardening (37 testes) → runbook → exportador vinhos_brasil_db Fase 2.5 (35 testes) → Fase 4 Gemini com guardrail factual (43 testes, qa_conflict:country_hint_mismatch) → piloto vtex ponta a ponta (500→47 ready apos guardrail, Two Birds detectado) → QA pre-apply (0 blocker) → apply pequeno autorizado (44 insert + 3 update) → QA pos-apply (0 violacoes de campos minimos, smoke de leitura 3/3) → queue drenada (pending=0) → mudancas DQ V3 integradas (wine_sources/run_id, migration 018 nao aplicada) → **commit seletivo pendente**`.
