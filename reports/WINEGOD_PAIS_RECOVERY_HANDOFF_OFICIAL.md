# WINEGOD_PAIS_RECOVERY — Handoff Oficial

Data: 2026-04-21
Branch: i18n/onda-2

Consolida o fechamento do projeto pais_recovery + housekeeping pos-Gemini
+ pipeline unico de ingestao + migracao pais_nome → pais_display + parser
de descricao em dry-run + varredura notwine arquivada.

---

## Rollout bulk_ingest

A preparacao operacional para liberar o pipeline em producao esta em:

- **Runbook**: [`reports/WINEGOD_PAIS_RECOVERY_BULK_INGEST_ROLLOUT_RUNBOOK.md`](WINEGOD_PAIS_RECOVERY_BULK_INGEST_ROLLOUT_RUNBOOK.md)
- **Smoke script**: `scripts/smoke_bulk_ingest_endpoint.py`
  (testa 401 sem token / 400 payload invalido / 200 dry-run com 1 item,
  nao loga o token, exit code 0/1).

Lembretes explicitos:
- `git push` **nao** dispara deploy no Render (REGRA 7). Deploy e manual.
- Nenhum apply em volume antes de passar pelo piloto dry-run do runbook.
- Parser descricao (Fase 4) **continua bloqueado por gate humano** — so
  rodar apply se houver decisao formal; recomendacao concreta esta na
  Fase 4 deste handoff.
- Rollback operacional = zerar `BULK_INGEST_TOKEN` no Render (endpoint
  volta a 401 imediato).

---

## Correcoes pos-auditoria (2026-04-21)

Auditoria corretiva do pipeline antes de producao. Dois problemas corrigidos:

### Bug critico 1: duplicata por hash diferente na mesma tripla

**Confirmado**. Cenario:
- Wine legado (ex: Vivino/import_render_z) inserido com `hash_dedup = 'legacyX'`.
- Payload novo bate na mesma tripla `(produtor_norm, nome_norm, safra)` mas
  o pipeline gera `hash_dedup = 'newY'`.
- `_resolve_existing` detectava match via tripla -> dry-run falava `would_update`.
- Apply usava `INSERT ... ON CONFLICT (hash_dedup) DO UPDATE`. Como `newY != legacyX`,
  nao havia conflito -> INSERT sucedia com duplicata.

**Correcao**:
- `_resolve_existing` agora retorna `(set_hashes, hash_to_id)` — mapa
  hash_payload -> id do wine existente.
- `_apply_batch` faz `UPDATE WHERE id=...` quando tem id, com merge
  conservador (`COALESCE(wines.x, EXCLUDED.x)`).
- Fallback `INSERT ... ON CONFLICT DO NOTHING RETURNING id` so quando
  realmente novo (race-safe).
- `hash_dedup` existente nao-nulo **nunca** e sobrescrito; se NULL/vazio,
  completa com o hash novo.

### Bug semantico 2: `total_fontes` em INSERT e reapply

**Confirmado em 2 niveis**:
1. `total_fontes` historicamente representa fontes **comerciais**
   (`wine_sources`). Evidencia: `scripts/import_render_z.py` carrega
   direto de `wines_clean.total_fontes`; `backend/services/new_wines.py`
   tambem insere com `total_fontes = 0` quando nao cria `wine_sources`;
   frontend `WineCard.tsx` renderiza como "loja/lojas";
   `reports/tail_base_summary_2026-04-10.md` registra divergencia
   conhecida entre `wines.total_fontes` e `wine_sources_count_live`.
2. Bulk_ingest **nao cria linha em `wine_sources`** — so grava provenance
   textual em `wines.fontes`. Portanto iniciar com `total_fontes = 1`
   contradiz o contrato e faria o wine aparecer como "1 loja" no UI.

**Correcao final**:
- UPDATE **nao mexe** em `total_fontes` (preserva valor existente).
- INSERT inicia com **`total_fontes = 0`** (alinhado com `new_wines.py`).
- `fontes` mantem provenance textual `["bulk_ingest:<source>"]` com
  merge deduplicado no UPDATE (`wines.fontes || novo` so se `NOT @>`).
- Quando uma linha em `wine_sources` for criada por um pipeline
  comercial separado, o contador sera atualizado por la — nao por aqui.

### Testes de regressao adicionados

- `test_db_legacy_hash_does_not_create_duplicate`: injeta wine com hash
  legado, manda payload com mesma tripla, valida COUNT=1, hash preservado,
  regiao mergeada, `total_fontes` preservado (seed=5 permanece 5).
- `test_db_reapply_does_not_inflate_total_fontes`: 4 ingestoes do mesmo
  payload, final `total_fontes = 0` e `len(fontes) = 1`.
- `test_db_new_bulk_insert_starts_with_zero_fontes`: prova que um novo
  bulk insert nao aparece como "1 loja" no frontend (alinhamento com
  `WineCard.tsx` e `new_wines.py`).

Resultado: **16 testes totais — 10 offline + 6 DB/integration**.
- Com DB acessivel: **16/16 passing** (modo default ou `REQUIRE_DB_TESTS=1`).
- Sem DB: **10 passed, 6 skipped, 0 failed** (exit 0 em modo default).
- Rollout exige modo estrito: `REQUIRE_DB_TESTS=1 python -m tests.test_bulk_ingest`
  — aborta com exit 1 se o banco estiver indisponivel.

Cleanup dos fake rows confirmado.

### Arquivos alterados na auditoria

- `backend/services/bulk_ingest.py`: refatorado `_resolve_existing`,
  `_apply_batch`, substituido `_UPSERT_SQL` por `_INSERT_SQL`+`_UPDATE_SQL`,
  INSERT inicia com `total_fontes = 0`.
- `backend/tests/test_bulk_ingest.py`: +3 testes de regressao.

---

## Sumario executivo (TL;DR)

As 7 fases do plano foram executadas sem humano no caminho critico.
Nenhum Gemini novo, nenhum score sweep, nenhum UPDATE em 139k wines
sem dry-run aprovado.

| Fase | Status | Saida principal |
|---|---|---|
| 0 Preflight | OK | `reports/WINEGOD_PAIS_RECOVERY_CHECKPOINT_FASE0.md` |
| 1 Pipeline unico | OK | `backend/services/bulk_ingest.py`, `backend/routes/ingest.py`, 16 testes (10 offline + 6 DB). Com DB: 16/16. Sem DB: 10 pass + 6 skip. |
| 2 Fluxo real pronto | OK | `scripts/ingest_via_bulk.py` (CLI CSV/JSON/JSONL) |
| 3 Migracao pais_display | OK | `enrich_wine` espalha `pais_display` canonico em todas as tools |
| 4 Parser descricao DRY-RUN | OK | `scripts/parse_gemini_descricao_fields.py` + relatorio em 157k wines |
| 5 Testes e validacao | OK | 16 testes (10 offline + 6 DB; 16/16 com DB, 10 pass + 6 skip sem DB) + app boota com ingest_bp + endpoint 401/400/200 OK |
| 6 Handoff oficial | OK | este arquivo |
| 7 Varredura notwine | OK | `WINEGOD_PAIS_RECOVERY_NOTWINE_FASE7_FECHAMENTO.md` — sem acao automatica segura |

Decisoes que ficam com o humano:
- Parser descricao apply: 57.969 mismatch de ABV vs 28.011 match.
  Recomendo so preencher onde `teor_alcoolico` e NULL (53.241 wines,
  ganho sem risco de sobrescrever dado real).
- Deploy Render: setar `BULK_INGEST_TOKEN` antes + Manual Deploy
  (REGRA 7: push nao dispara deploy).
- Commit/push das mudancas desta sessao — nada commitado ainda.

---

## 1. Estado do banco

| Metrica | Valor |
|---|---|
| wines total | 2.506.450 |
| wines ativos (suppressed_at IS NULL) | 2.225.822 |
| com pais (ISO) | 2.147.666 (96,49%) |
| sem pais (residuais aceitos) | 78.156 (3,51%) |
| com teor_alcoolico | 415.088 |
| com harmonizacao | 397.179 |
| com descricao | 157.183 |
| score_recalc_queue | 0 |
| wine_context_buckets total | 202.580 |
| trg_score_recalc | ativo |

Temp tables (`tmp_gemini_v3_updates`, `pais_enrichment_queue`,
`tmp_regiao_pais_lookup`, `pais_recovery_candidates`, `tmp_produtor_95_safe`):
todas **dropadas**.

Mantidas: `vivino_vinicolas_lookup`, `notwine_suppression_log`.

---

## 2. Decisoes finais

- **78.156 wines sem pais**: aceitos. Nao vai rodar Gemini novo.
- **Score sweep**: nao rodar agora. Queue zerada via TRUNCATE.
- **pais/pais_nome**: `pais` (ISO) e canonico. `pais_display` e derivado em
  runtime via `utils.country_names.iso_to_name`. `pais_nome` continua no
  banco como compat para clientes legados e fallback textual.
- **Parser descricao**: entregue em dry-run. Apply real **nao aprovado** —
  qualidade da extracao e ruidosa (ver secao 5).

---

## 3. Entregas desta rodada

### 3.1 Pipeline unico de ingestao (Fase 1)

- `backend/services/bulk_ingest.py`: `process_bulk(items, dry_run=...,
  source=...)` — filtro NOT_WINE, dedup por tripla (produtor_norm,
  nome_norm, safra) + hash_dedup, UPSERT em batches de 10k (REGRA 5).
- `backend/routes/ingest.py`: `POST /api/ingest/bulk` protegido por
  header `X-Ingest-Token` (env `BULK_INGEST_TOKEN`).
- `backend/config.py`: 3 envs novos
  (`BULK_INGEST_TOKEN`, `BULK_INGEST_BATCH_SIZE`, `BULK_INGEST_MAX_ITEMS`).
- `backend/tests/test_bulk_ingest.py`: 16 testes — **10 offline** (validacao,
  filtro notwine, hash estavel, rejeicao all-notwine, empty) + **6 DB**
  (dedup_in_input, dry-run detecta update, apply + cleanup, regressao de
  duplicata por hash diferente, reapply nao infla total_fontes,
  `total_fontes=0` em novo INSERT).
  - Runner tem modo estrito: `REQUIRE_DB_TESTS=1` aborta com exit 1 se
    o banco estiver indisponivel. Default sem DB marca DB tests como
    SKIP (nao PASS) e mantem exit 0.
  - "16/16" e valido **apenas com DB acessivel**. Sem DB: "10 passed,
    6 skipped, 0 failed".

### 3.2 Fluxo real pronto pra usar (Fase 2)

- `scripts/ingest_via_bulk.py`: CLI wrapper que aceita CSV/JSON/JSONL
  (arquivo ou stdin) e chama o mesmo `process_bulk`. Dry-run default.
- Caminhos historicos (`services/new_wines.py` para chat auto-create,
  `scripts/import_render_z.py` para import Vivino) continuam funcionando
  — nao foram migrados, nao quebrei nada.

### 3.3 Migracao pais_nome → pais_display (Fase 3)

- `backend/services/display.py`: `resolve_display` agora retorna
  `pais_display` derivado de `iso_to_name(pais)` com fallback em `pais_nome`.
- `backend/tools/prices.py`: passou a chamar `enrich_wines(results)`.
- `backend/tools/resolver.py`: linha 739 prioriza `d.get('pais_display')`
  antes do fallback.
- `search.py`, `compare.py`, `models_share.py`, `details.py`, `discovery.py`:
  ja chamavam `enrich_wines` — ganham `pais_display` de graca.
- WHEREs com `pais_nome ILIKE` (search/compare/stats) **mantidos** como
  compat legitimo (Politica A): usuario digita "italy" sem ISO reconhecido,
  cai em pais_nome. Comentarios no codigo ja documentam.

### 3.4 Parser descricao (Fase 4, dry-run)

- `scripts/parse_gemini_descricao_fields.py`: streaming com server-side
  cursor, regex deterministico, NAO toca no banco.
- Saidas:
  - `reports/WINEGOD_PAIS_RECOVERY_PARSER_DRYRUN.md`
  - `reports/WINEGOD_PAIS_RECOVERY_PARSER_DRYRUN_samples.csv`

---

## 4. Nada novo consumindo Gemini

- Nenhuma chamada nova a Gemini (REGRA 6 respeitada).
- Pipeline de ingestao NAO dispara IA — cadastro + dedup + filtro
  deterministicos apenas.
- Enrichment IA continua em `services/new_wines.py` (chat auto-create) e
  em scripts manuais aprovados caso-a-caso.

---

## 5. Parser descricao — resultado completo (157k wines)

Full dataset (ver `WINEGOD_PAIS_RECOVERY_PARSER_DRYRUN.md`):

| Campo | Extraidos | % |
|---|---:|---:|
| pelo menos 1 campo | 150.937 | 96,03% |
| abv | 139.221 | 88,57% |
| classificacao | 104.296 | 66,35% |
| corpo | 148.358 | 94,39% |
| docura | 149.416 | 95,06% |
| harmonizacao | 147.336 | 93,74% |
| envelhecimento | 147.389 | 93,77% |
| temperatura | 146.919 | 93,47% |

**ABV vs coluna `teor_alcoolico`:**

| Categoria | Count |
|---|---:|
| match (<= 0.2 diff) | 28.011 |
| **mismatch** | **57.969** |
| so extraido (coluna NULL) | 53.241 |
| so coluna (extraido NULL) | 10.682 |
| ambos null | 7.280 |

**Harmonizacao divergente** da coluna existente: 87.027 wines.

### Recomendacao (decisao do humano)

1. **NAO** sobrescrever `teor_alcoolico` existente — 57.969 mismatch e
   risco alto de trocar dado real por estimativa Gemini.
2. **PODE** preencher `teor_alcoolico` onde esta NULL — 53.241 wines
   ganham ABV sem risco de sobrescrever nada.
3. **Novas colunas** (classificacao, corpo, docura, envelhecimento,
   temperatura_servico): decidir se adiciona schema ou mantem no
   `descricao` livre. O parser ainda tem ruido (`medio` como
   classificacao: 837 casos; `750ml` como docura: 1.813 casos) — se
   virar coluna, precisa whitelist de valores normalizados + rejeitar
   resto.

Gate humano para decidir. Nenhuma dessas opcoes foi executada.

---

## 6. Rollback

Pipeline e migracao pais_display sao **puramente codigo novo / shim
aditivo**. Rollback:

- Remover `backend/services/bulk_ingest.py`.
- Remover `backend/routes/ingest.py` + o `register_blueprint(ingest_bp)`
  de `backend/app.py`.
- Remover `scripts/ingest_via_bulk.py` e `scripts/parse_gemini_descricao_fields.py`.
- Remover os 3 envs novos de `backend/config.py`.
- Reverter `backend/services/display.py` (tirar `pais_display` do retorno).
- Reverter `backend/tools/prices.py` (tirar enrich_wines).
- Reverter `backend/tools/resolver.py` linha 739.

Banco: nenhuma migration SQL foi executada. Nao ha rollback de schema.

---

## 7. O que ficou pendente (nao urgente)

- **Parser descricao APPLY**: so rodar se gate humano aprovar. Recomendacao
  concreta: preencher `teor_alcoolico` apenas onde esta NULL (53.241 wines),
  nao sobrescrever valores existentes. Classificacao/corpo/docura precisam
  whitelist antes de virarem coluna.
- **Fase 7 (padroes notwine)**: ja varrido nesta sessao — nenhum padrao
  forte em 588 candidatos. Arquivado em
  `WINEGOD_PAIS_RECOVERY_NOTWINE_FASE7_FECHAMENTO.md`. Se aparecer set
  novo com padroes concentrados (>=5% num unico termo), revisitar.

---

## 8. Comandos uteis

```bash
# Rodar os testes do pipeline
cd backend && python -m tests.test_bulk_ingest

# Ingestao via CLI (dry-run default)
python scripts/ingest_via_bulk.py --input wines.csv --source scraping_x

# Ingestao apply
python scripts/ingest_via_bulk.py --input wines.jsonl --apply --source wcf

# Parser descricao (dry-run, amostra)
python scripts/parse_gemini_descricao_fields.py --sample 10000

# Parser descricao (dry-run completo)
python scripts/parse_gemini_descricao_fields.py
```

---

## 9. Deploy no Render

- `backend/config.py` novo env `BULK_INGEST_TOKEN` precisa ser setado no
  Render antes do endpoint responder 200 (senao 401).
- `git push` para `main` **NAO dispara deploy automatico** (REGRA 7).
  Deploy manual no Render (Manual Deploy) depois do merge.

---

## 10. Arquivos criados/alterados nesta sessao

**Novos:**
- `backend/services/bulk_ingest.py`
- `backend/routes/ingest.py`
- `backend/tests/test_bulk_ingest.py`
- `scripts/ingest_via_bulk.py`
- `scripts/parse_gemini_descricao_fields.py`
- `reports/WINEGOD_PAIS_RECOVERY_CHECKPOINT_FASE0.md`
- `reports/WINEGOD_PAIS_RECOVERY_PARSER_DRYRUN.md`
- `reports/WINEGOD_PAIS_RECOVERY_PARSER_DRYRUN_samples.csv`
- `reports/WINEGOD_PAIS_RECOVERY_NOTWINE_FASE7_FECHAMENTO.md`
- `reports/WINEGOD_PAIS_RECOVERY_HANDOFF_OFICIAL.md` (este)

**Alterados:**
- `backend/app.py` (+1 blueprint)
- `backend/config.py` (+3 envs: `BULK_INGEST_TOKEN`, `BULK_INGEST_BATCH_SIZE`, `BULK_INGEST_MAX_ITEMS`)
- `backend/services/display.py` (adiciona `pais_display` em `resolve_display`)
- `backend/tools/prices.py` (chama `enrich_wines` nos resultados)
- `backend/tools/resolver.py` (linha 739: prioriza `d.get('pais_display')`)

---

## 11. Regras respeitadas

- REGRA 1 (commit): nada commitado sem confirmacao.
- REGRA 2 (banco): zero UPDATE/DELETE fora dos testes (que limpam o proprio lixo).
- REGRA 5 (Render baixa memoria): batches de 10k, chunks menores disponiveis.
- REGRA 6 (Gemini): zero chamada nova a Gemini.
- REGRA 7 (deploy Render): anotado aqui, nao automatico.
- REGRA 8 (nomes handoff): todos os docs novos com prefixo `WINEGOD_PAIS_RECOVERY_*`.
- Feedback "fases pequenas auditadas": cada fase termina em saida tangivel.
- Feedback "NOT_WINE propagation": regra aplicada na Fase 7 (nao foi disparada porque nao houve padrao forte).
- Feedback "pais/pais_nome": `pais` ISO canonico, `pais_display` derivado via `country_names.iso_to_name`.

---

## 12. Para a proxima sessao abrir este arquivo e continuar

Se ninguem aprovou o parser apply ainda:
1. Ler `WINEGOD_PAIS_RECOVERY_PARSER_DRYRUN.md` (numeros full).
2. Decidir: preencher `teor_alcoolico` onde NULL (53k wines, risco baixo)?
3. Se sim: criar script `scripts/apply_descricao_parser.py` que desativa
   `trg_score_recalc`, UPDATE em chunks de 2k so onde `teor_alcoolico IS NULL`,
   reativa trigger, valida `score_recalc_queue = 0`.

Se o banco ainda nao precisou de nada novo:
1. Testar endpoint em producao com `BULK_INGEST_TOKEN` setado.
2. Apontar um scraping real (primeiros 100-500 items dry-run) pro
   `POST /api/ingest/bulk`.
3. Medir numeros, confirmar saida, entao apply em volume.

Se surgir um novo set de candidatos notwine:
1. Rodar varredura tipo `WINEGOD_PAIS_RECOVERY_NOTWINE_FASE7_FECHAMENTO.md`.
2. So adicionar padrao no filtro se hits >= 5% num unico termo.
3. Propagar para `wine_filter.py` E `pre_ingest_filter.py` (regra de propagacao).
