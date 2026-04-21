# WINEGOD_PRE_INGEST_ROUTER — Analise tecnica do fluxo bifurcado

Data: 2026-04-21
Projeto: winegod-app / bulk_ingest v2
Autor: Claude (analise pre-implementacao)

Destino: handoff pra Codex ou proximo executor. **Nao implementa nada** — e estudo + plano.

---

## 1. Contexto

O pipeline `bulk_ingest` esta tecnicamente pronto e em producao:

- Smoke endpoint OK (`https://winegod-app.onrender.com/api/ingest/bulk`).
- Dedup por tripla `(produtor_norm, nome_norm, safra)` + hash, corrigido na auditoria.
- `total_fontes = 0` em novos INSERTs (alinhado com `new_wines.py`).
- 16 testes (10 offline + 6 DB), runner com SKIP/FAIL/ABORT + modo strict.
- Piloto sintetico validou os 2 caminhos: `would_insert` e `would_update`.

Porem o **fluxo operacional real** ainda nao esta definido. A hipotese atual e que mandar item direto pro `bulk_ingest` sem classificacao previa tem risco operacional — especialmente quando a fonte e scraping/OCR/planilha com dados sujos.

Este documento analisa a alternativa: **fluxo bifurcado com uncertain como saida lateral nao-bloqueante**.

---

## 2. Fluxo proposto

```
Fonte real (scraper / OCR / planilha / parceiro)
        ↓
  Lista bruta de produtos
        ↓
  Filtro NOT_WINE forte deterministico
  (wine_filter + pre_ingest_filter)
        ↓
  Classificador de prontidao para ingestao
        ↓
  ──────────────────────────────────────────
  ↓                                        ↓
  READY                                    NEEDS_ENRICHMENT
  identidade suficiente                    incompleto / ambiguo
  para dedup seguro                        precisa completar / reclassificar
  ↓                                        ↓
  bulk_ingest/dedup                        enrichment Gemini/outra fonte
  valida, normaliza, deduplica             completa dados + reclassifica
  ↓                                        ↓
  insert/update seguro                     Segundo filtro NOT_WINE contextual
  Banco wines                              usando resultado enriquecido
                                            ↓
                                            Resultado:
                                            - enriched_wine_ready → bulk_ingest/dedup
                                            - enriched_not_wine  → descarta/loga
                                            - uncertain          → uncertain_review.csv
                                                                   (NAO bloqueia pipeline)
```

### Regra de revisao humana (importante)

- `uncertain_review.csv` e **saida lateral**. Nao e gate.
- Nenhum processo (dry-run, enrichment, apply, ingestao) depende de humano revisar esse arquivo.
- Casos uncertain sao **excluidos do lote automatico** ate que um processo futuro os reprocesse.
- O pipeline deve terminar com sucesso mesmo se `len(uncertain) > 0`.

### Por que bifurcar

Dedup do `bulk_ingest` se apoia em `(produtor_normalizado, nome_normalizado, safra)`. Se o produtor chega vazio ou o nome e generico ("Red Wine", "Sparkling", "House Blend 2022"), o dedup gera hash — mas o hash e ruido:

- Dois scrapings diferentes com "House Blend 2022" viram o mesmo wine.
- Wines legitimos com produtores diferentes colidem na tripla se o nome for generico demais.

O fluxo bifurcado resolve movendo a decisao pra **antes** do dedup: "este item tem identidade suficiente pra ser deduplicado?" Se nao tem, enrichment corrige antes; se corrigir nao for suficiente, vai pra uncertain. Em ambos os casos, o banco so recebe wines com identidade minima garantida.

Vantagem extra: **inverte a economia do Gemini**. Hoje enrichment e "embelezamento" aplicavel ao banco todo. No bifurcado, enrichment e cirurgico — so sobre os 10-30% incompletos, reduzindo custo.

---

## 3. Regras objetivas de classificacao

### 3.1 READY (todas as condicoes juntas, AND)

| Condicao | Justificativa |
|---|---|
| `nome` presente, normalizado, length >= 8 | evita "Red", "Blend", "House" solo |
| `produtor` presente, normalizado, length >= 3 | produtor + nome = identidade dedup |
| nome NAO consiste so de uva/cor/tipo generico | lista negra: `{"red","white","blanc","rose","blend","reserva","brut","cuvee","house"}` sozinhos ou combinados em <= 3 tokens |
| `pais` presente OU `regiao` presente OU `ean_gtin` presente | identidade geografica OU code comercial |
| `should_skip_wine(nome, produtor)` == `(False, None)` | filtro deterministico ja passou |
| nome NAO tem padrao tipico de item ambiguo | sem `magnum/jeroboam/balthazar` sozinhos sem outros tokens |

Item que satisfaz todas → `ready.jsonl` → bulk_ingest direto.

### 3.2 NEEDS_ENRICHMENT

Primeiro filtro passou (nao e NOT_WINE obvio) **mas** pelo menos uma condicao de READY falhou e e "consertavel" via enrichment:

- `produtor` ausente **mas** `nome` tem pista (uva + regiao explicita)
- `pais` E `regiao` ausentes **mas** `produtor` conhecido
- `nome` curto mas `ean_gtin` presente (Gemini resolve via EAN)
- `safra` ausente mas resto completo
- Descricao livre grande (> 100 chars) sem estruturacao

**Regra negativa**: se `nome` + `produtor` ambos vazios → **uncertain**, nao enrichment. Gemini sem ancora inventa.

### 3.3 NOT_WINE automatico

**Primeiro filtro deterministico** (ja existe em `scripts/pre_ingest_filter.py:63`):
- `wine_filter` hits (whisky/vodka/beer/sake/cachaca/etc)
- ABV fora 10-15%
- volume nao-padrao
- gramatura (gramas/kg)
- data com sufixo (20th, 21st)
- case+numero 2-96 (kit)

→ `rejected_notwine.jsonl` com razao. Nao vai pra lugar nenhum.

**Segundo filtro pos-enrichment** (novo, leve):
- Gemini retornou `kind != "wine"` (ja existe no prompt de `new_wines.py:70-118`)
- `confidence < 0.50`
- pais + classificacao consistentes com destilado (ex: pais=MX + classificacao="Tequila")

→ `rejected_notwine_post_enrichment.jsonl`. Separado do deterministico pra medir slip do primeiro filtro.

### 3.4 UNCERTAIN (saida lateral nao-bloqueante)

Qualquer uma dispara:
- Pos-enrichment com `0.50 <= confidence < 0.75`
- Gemini em conflito com input sem razao dominante (input: "fr", Gemini: "ar", sem evidencia)
- Pos-enrichment ainda sem produtor OU sem pais/regiao/ean
- Gemini retornou `kind: "unknown"`

→ `uncertain_review.csv` com colunas:

| coluna | tipo | descricao |
|---|---|---|
| id_fonte | str | chave do scraping original |
| nome_original | str | nome bruto |
| produtor_original | str | produtor bruto |
| nome_enriquecido | str | nome pos-Gemini (se houve) |
| produtor_enriquecido | str | idem produtor |
| pais_enriquecido | str | idem pais ISO |
| confidence | float | 0.0-1.0 |
| reasons | array[str] | lista de razoes ("produtor_vazio", "conflito_pais", etc) |
| source | str | origem (`gemini-2.5`, `manual`, etc) |
| timestamp | ISO datetime | quando foi classificado |

Pipeline continua sem esperar. Items uncertain nao entram no bulk_ingest dessa rodada. Proxima rodada (semanal, por ex.), humano pode revisar o CSV, corrigir, alimentar um `ready_manual.jsonl` de volta. Mas opcional. Pipeline e idempotente; nao reprocessar uncertain nao quebra nada.

---

## 4. Schema padronizado de enrichment (contrato de saida do Gemini)

| Campo | Tipo | Obrigatorio? | Observacao |
|---|---|---|---|
| `status` | enum | sim | `wine_ready` / `not_wine` / `uncertain` |
| `confidence` | float | sim | 0.0-1.0 |
| `nome` | str | condicional | presente se `status != not_wine` |
| `produtor` | str | condicional | presente se `status == wine_ready` |
| `safra` | str 4 digitos | nao | ISO 4-digit year |
| `pais` | str 2 chars | nao | ISO-2 uppercase |
| `regiao` | str | nao | |
| `tipo` | enum | nao | `tinto/branco/rose/espumante/fortificado/sobremesa` |
| `uvas` | array[str] | nao | |
| `descricao` | str | nao | |
| `reasons` | array[str] | sim | **array**, nao string unica — ex: `["produtor_vazio", "regiao_inferida"]` |
| `source` | str | sim | `gemini-2.5-flash-lite`, `manual`, etc |
| **adicionar** `raw_original` | dict | sim | payload bruto antes do enrichment — essencial pra rollback/auditoria |
| **adicionar** `enriched_at` | ISO datetime | sim | pra expirar cache |
| **adicionar** `ean_gtin` | str | nao | util se fonte tiver |

---

## 5. Onde mora no codigo

**Script operacional**, nao servico HTTP:

- `scripts/pre_ingest_router.py` — CLI que le JSONL de entrada, classifica, escreve 4 arquivos de saida.

Razoes pra script:
- rollout e batch, nao streaming — nao precisa estar no backend Flask.
- e fluxo de operador (roda quando chega scraping novo), nao endpoint.
- fica com os outros CLIs (`ingest_via_bulk.py`, `smoke_bulk_ingest_endpoint.py`).
- testavel offline puro (so lista-lista, sem HTTP).

Promover pra `backend/services/pre_ingest_router.py` + rota HTTP que enfileira **so quando virar rotina automatizada**. YAGNI ate la.

---

## 6. Persistencia — arquivos JSONL, nao tabela

Comecar com arquivos em `reports/ingest_pipeline/`:

```
reports/ingest_pipeline/
  2026-04-21_1400_source_vivino/
    ready.jsonl
    needs_enrichment.jsonl
    rejected_notwine.jsonl
    uncertain_review.csv
    summary.md    ← contadores + warnings
```

Motivos:
- Zero migracao de schema (REGRA 2).
- Auditavel: cada subdiretorio e um snapshot com data + fonte.
- `git log` / rclone / backup simples.
- Se um batch "perde", voce le o JSONL, nao SQL.
- Quando volume justificar (milhoes/semana ou filas paralelas), migrar pra tabela `ingest_candidates` + `status enum`. Nao e agora.

Unica excecao justificavel hoje: se enrichment precisar ser **retomavel a meio do lote** (Gemini batch API demora 20min → processo cai). Ai sim, tabela com `status/attempts/last_error`. Pro lote sincrono atual, arquivo basta.

---

## 7. Plano incremental (fases)

Gate humano entre fases. Fase 4 precisa autorizacao explicita (REGRA 6 — Gemini nao roda sem OK).

| Fase | Objetivo | Saida | Apply? |
|---|---|---|---|
| 0 | Auditoria (este documento) | `WINEGOD_PRE_INGEST_ROUTER_ANALISE.md` | nao |
| 1 | Classificador deterministico de prontidao | `scripts/_ingest_classifier.py` + testes offline | nao |
| 2 | Router: le JSONL, gera os 4 arquivos | `scripts/pre_ingest_router.py` + smoke com input fake | nao |
| 3 | Dry-run real dos `ready` via `ingest_via_bulk.py` | relatorio contadores | nao |
| 4 | Consumir `needs_enrichment`, chamar Gemini (OFFLINE ainda — so gera arquivos) | `scripts/enrich_needs.py` + `enriched.jsonl` | nao |
| 5 | Segundo filtro + gerador `uncertain_review.csv` | funcao + teste offline | nao |
| 6 | bulk_ingest dos `enriched_ready` re-roteados p/ `ready.jsonl` | dry-run + apply pequeno com autorizacao | **sim, pequeno** |
| 7 | Automacao (cron/trigger) | CronCreate/trigger | pipeline completo |

### Caminho critico curto (70% do valor)

Fases 1-3 resolvem o essencial **sem Gemini**:

1. `is_ready()` / `why_not_ready()` em `scripts/_ingest_classifier.py` + testes offline.
2. `scripts/pre_ingest_router.py` que le JSONL e gera 4 arquivos.
3. Rodar `ingest_via_bulk.py` so sobre `ready.jsonl`.

Zero Gemini, zero codigo novo no backend, zero migration. Fases 4-6 depois, quando tiver lote real que justifique custo.

---

## 8. Riscos de mandar incompleto pro bulk_ingest hoje

Ordenados por impacto:

| Risco | Exemplo | Dano |
|---|---|---|
| Duplicata por identidade fraca | "Red Wine / Sin Producer / 2022" x 2 scrapings diferentes → hash igual → update errado | wine A do scraping X ganha `fontes` do scraping Y; semantica podre |
| Colisao de triplas genericas | "Reserve / Vinicola XYZ" + "Reserve / Vinicola XYZ" com produtos diferentes | um ofusca o outro; UPDATE merge_conservador pega pais errado |
| Wine generico poluindo busca | 1000 items "House White" indexados → chat "vinho branco bom" pega | Baco recomenda lixo, quebra R6 |
| Score nonsense | Wine sem pais/regiao nao bate balde contextual → `pais_display=None` | UX quebra; chat passa null pra template |
| Not_wine que passou | Gin tonica com nome "Wine & Dine Set" passa wine_filter | mancha 2,2M wines reais |
| Rollback caro | 2000 items ruins misturados com 500 bons no mesmo source | `DELETE WHERE fontes @> ...` apaga tudo |

Com bifurcacao: todos caem em `needs_enrichment` ou `uncertain`, **antes** de tocarem no banco.

---

## 9. Estado atual — o que existe vs o que falta

| Componente | Arquivo | Status | Observacao |
|---|---|---|---|
| Filtro NOT_WINE deterministico | `scripts/wine_filter.py` | **pronto** | 400+ regex multilingua |
| Filtro procedural (ABV, volume, kit) | `scripts/pre_ingest_filter.py` | **pronto** | 6 regras consolidadas 2026-04-15 |
| Bulk ingest final | `backend/services/bulk_ingest.py` | **pronto** | auditado, 16 testes, total_fontes=0 |
| Endpoint HTTP ingest | `backend/routes/ingest.py` | **pronto** | 401/400/200 validado em prod |
| CLI ingest dry-run | `scripts/ingest_via_bulk.py` | **pronto** | dry-run default |
| Smoke endpoint | `scripts/smoke_bulk_ingest_endpoint.py` | **pronto** | 3 checks, exit 0/1 |
| Classifier READY/NEEDS/NOT/UNCERTAIN | — | **falta** | Fase 1 |
| Router (gera 4 arquivos) | `scripts/pre_ingest_router.py` | **falta** | Fase 2 |
| Enrichment de incompletos | `scripts/pais_enrichment_gemini*.py` | **parcial** | serve pra `pais`, nao pro contrato `wine_ready/not_wine/uncertain`; precisa wrapper |
| Prompt de enrichment estruturado | `backend/services/new_wines.py:70-118` | **parcial** | pro chat sincrono; reusar schema pro batch |
| Segundo filtro NOT_WINE pos-enrichment | — | **falta** | Fase 5 |
| Gerador `uncertain_review.csv` | — | **falta** | Fase 5 |
| Tabela `ingest_candidates` / fila DB | — | **nao necessario agora** | arquivos JSONL bastam |
| Testes offline classifier | `backend/tests/test_pre_ingest_router.py` (hipotetico) | **falta** | junto com Fase 1 |
| Runbook fluxo bifurcado | `WINEGOD_PRE_INGEST_ROUTER_RUNBOOK.md` | **falta** | depois Fase 2 |

---

## 10. Ressalvas e discordancias

1. **Uncertain nao bloqueia producao**: correto. Mas em **rollout inicial** eu manteria soft gate: se `len(uncertain) / len(total) > 20%`, emitir warning visivel ao operador (nao bloquear). Se primeiro filtro ou enrichment estiver muito ruim, operador quer saber antes do loop 10×.

2. **`scripts/` vs `backend/services/`**: correto enquanto fluxo e manual/batch. Se virar automatico (Fase 7), promover pra servico + tabela. YAGNI ate la.

3. **Segundo filtro pos-enrichment como camada nova**: eu **nao** criaria ainda. Comecaria reusando `should_skip_wine()` com payload enriquecido. So extrair lambda nova se encontrar slip real nao coberto. YAGNI.

4. **Tabela `ingest_candidates` agora**: nao. Arquivos bastam. Promover quando volume justificar OU enrichment precisar ser retomavel a meio do batch.

---

## 11. Handoff pro Codex

Pra quem continuar:

**Objetivo**: implementar Fase 1 (classificador) + Fase 2 (router) sem tocar em Gemini, sem migration, sem apply em volume.

**Entregas minimas da rodada Codex**:

1. `scripts/_ingest_classifier.py` com:
   - `def classify(item: dict) -> tuple[str, list[str]]` retornando `(status, reasons)` onde status ∈ `{"ready", "needs_enrichment", "not_wine", "uncertain"}`.
   - Funcoes auxiliares puras (`is_generic_name`, `has_identity`, etc).
   - Nenhuma chamada a banco nem HTTP.

2. `backend/tests/test_ingest_classifier.py` com:
   - Casos ready (positivos).
   - Casos needs_enrichment (nome generico + produtor, produtor vazio + nome forte, etc).
   - Casos not_wine (delegando pra `pre_ingest_filter.should_skip_wine`).
   - Casos uncertain (nome+produtor vazios).
   - >= 20 testes, todos offline.

3. `scripts/pre_ingest_router.py` com:
   - Le JSONL de input (path via `--input`).
   - Gera em `reports/ingest_pipeline/<timestamp>_<source>/`:
     - `ready.jsonl`
     - `needs_enrichment.jsonl`
     - `rejected_notwine.jsonl`
     - `uncertain_review.csv`
     - `summary.md` com contadores + warning se uncertain_pct > 20%.
   - Exit 0 sempre, mesmo com uncertain > 0.

4. `reports/WINEGOD_PRE_INGEST_ROUTER_RUNBOOK.md` explicando:
   - Como rodar.
   - Como interpretar os 4 arquivos.
   - Como escalar pra Fase 3 (alimentar `ready.jsonl` pro `ingest_via_bulk.py`).

**Fora do escopo desta rodada Codex**:
- Chamar Gemini.
- Criar tabela no banco.
- Rodar `--apply`.
- Automacao via cron.
- Segundo filtro pos-enrichment (Fase 5).

**Arquivos de contexto que o Codex deve ler antes**:
- `backend/services/bulk_ingest.py` (entender contrato do UPSERT e dedup)
- `scripts/pre_ingest_filter.py` (filtro deterministico ja existente)
- `scripts/wine_filter.py` (regex base)
- `scripts/ingest_via_bulk.py` (CLI que vai consumir `ready.jsonl`)
- `backend/services/new_wines.py:70-118` (prompt de enrichment atual pro chat sincrono — reusar schema)
- `reports/WINEGOD_PAIS_RECOVERY_HANDOFF_OFICIAL.md` (historico + regras)
- `reports/WINEGOD_PAIS_RECOVERY_BULK_INGEST_ROLLOUT_RUNBOOK.md` (rollout do bulk_ingest que o router alimenta)

**Regras que o Codex deve respeitar**:
- REGRA 1: nao commitar sem autorizacao; nao usar `git add .`.
- REGRA 2: nao alterar banco (esta rodada nao precisa).
- REGRA 5: se algum SQL acessorio aparecer, batches de 10k.
- REGRA 6: zero Gemini nesta rodada.
- REGRA 7: deploy Render e manual; nao assumir automatico.
- REGRA 8: arquivos novos de handoff/plano com prefixo `WINEGOD_PRE_INGEST_ROUTER_*`.
- Feedback "fases pequenas auditadas": entregar Fase 1 inteira, rodar testes, **parar e aguardar** antes de Fase 2.
- Feedback "NOT_WINE propagation": se descobrir padrao novo, vai pros 2 arquivos (`wine_filter.py` + `pre_ingest_filter.py`).

---

## 12. Decisoes pendentes do usuario (antes do Codex comecar)

1. Confirmar as listas negras de nomes genericos (item 3.1). Proposta: `{"red","white","blanc","rose","blend","reserva","brut","cuvee","house"}`. Aceita? Quer adicionar/remover?
2. Thresholds de confidence: 0.75 (ready), 0.50-0.75 (uncertain), <0.50 (not_wine). Aceita?
3. Soft warning se `uncertain_pct > 20%`: aceita como policy?
4. Formato final de `uncertain_review`: CSV (proposto) ou JSONL? Argumentacao: CSV pra humano abrir no Excel; JSONL pra reimportar se quiser.

Essas 4 decisoes fecham a especificacao. Depois disso o Codex tem input suficiente pra executar Fase 1 sem ambiguidade.
