# WINEGOD_PRE_INGEST_ROUTER — Runbook operacional

Data: 2026-04-21
Projeto: winegod-app
Fase: roteamento determinístico antes do bulk_ingest.

Este runbook e pra operador rodar o `pre_ingest_router.py` sobre um
arquivo real e preparar a entrada do `ingest_via_bulk.py` (Fase 3).

---

## 1. Objetivo

Separar um lote bruto de produtos em 4 buckets antes do dedup/gravacao:

- **ready** — item com identidade suficiente (nome, produtor, geografia ou EAN). Pode ir direto pro `bulk_ingest` em dry-run.
- **needs_enrichment** — item com ancora util mas faltando campos. Entra em fila futura de enrichment Gemini (Fase 4+).
- **rejected_notwine** — bloqueado pelo filtro deterministico (`wine_filter` + regras procedurais). Descarta ou auditoria.
- **uncertain** — sem ancora util. Vai pra `uncertain_review.csv` como **saida lateral** (revisao humana opcional).

Garantias fortes do router:

- **Nao chama Gemini.**
- **Nao toca o banco.**
- **Nao faz HTTP.**
- **Nao grava nada em `wines`.**
- **Nao roda `--apply`.**
- **Uncertain e saida lateral, nao gate.** Pipeline termina com sucesso mesmo com `uncertain > 0`.

---

## 2. Fluxo

```
fonte real (scraper / OCR / planilha / parceiro)
        ↓
JSONL bruto (uma linha = um objeto JSON)
        ↓
python scripts/pre_ingest_router.py
        ↓
reports/ingest_pipeline/<timestamp>_<source>/
    ├─ ready.jsonl              → entrada do bulk_ingest
    ├─ needs_enrichment.jsonl   → espera enrichment (Fase 4+)
    ├─ rejected_notwine.jsonl   → descarte ou log
    ├─ uncertain_review.csv     → saida lateral p/ humano (nao bloqueia)
    └─ summary.md               → contadores + WARNING se uncertain > 20%
        ↓
python scripts/ingest_via_bulk.py (dry-run, so sobre ready.jsonl)
```

---

## 3. Pre-requisitos

### Input

- Arquivo **JSONL** (`.jsonl`).
- Cada linha e um **objeto JSON** (nao array, nao scalar).
- Linhas em branco sao ignoradas.
- UTF-8 recomendado.

### Campos aceitos no item

| Campo | Tipo | Obrigatorio? |
|---|---|---|
| `nome` | string | quase sempre (sem nome + sem EAN + sem produtor = uncertain) |
| `produtor` | string | nao, mas muito recomendado |
| `safra` | string de 4 digitos (1900-2099) | nao |
| `pais` | ISO-2 (`fr`, `ar`, ...) | nao — uma das ancoras geograficas |
| `regiao` | string | nao — ancora geografica alternativa |
| `sub_regiao` | string | nao — ancora geografica alternativa |
| `ean_gtin` | string | nao — ancora comercial alternativa |
| `uvas` | string ou lista | nao |
| `tipo` | enum tinto/branco/rose/espumante/fortificado/sobremesa | nao |
| `teor_alcoolico` | float 10-15 | nao |
| `volume_ml` | float | nao |
| `harmonizacao` | string | nao |
| `descricao` | string | nao — >= 100 chars conta como ancora |
| `preco_min`, `preco_max`, `moeda` | — | nao |
| `imagem_url` | string | nao |

Campos extras sao preservados nos JSONLs de saida (o bulk_ingest ignora desconhecidos).

### `--source` (importante — validado)

Aceita apenas `[A-Za-z0-9_.-]`. Rejeitado:
- vazio
- espaco
- `/`, `\`
- `..` (path traversal)
- acentos ou caracteres especiais (`:`, `@`, `*`, etc)

Exemplos validos: `scraping_real_20260421`, `vivino_batch_001`, `loja-x`, `source.v2`.

Exemplos que falham: `minha fonte`, `../escape`, `foo/bar`, `produção`, `x:y`.

---

## 4. Comando do router

```bash
python scripts/pre_ingest_router.py \
  --input caminho/arquivo_real.jsonl \
  --source scraping_real_20260421
```

### Flags opcionais

| Flag | Default | Efeito |
|---|---|---|
| `--out-dir <path>` | `<repo_root>/reports/ingest_pipeline` | diretorio base das saidas (ancorado no repo root quando omitido — nao depende de CWD) |
| `--timestamp YYYYMMDD_HHMMSS` | agora | timestamp explicito (util pra retomar ou reproduzir) |

### Exit codes

- `0` — processou, mesmo com `uncertain > 0`.
- `1` — erro real:
  - input nao existe
  - JSONL invalido
  - linha nao-objeto
  - `--source` invalido
  - erro de escrita

### Saida no stdout

JSON com contadores + `uncertain_pct`:

```json
{
  "out_dir": "C:/.../reports/ingest_pipeline/20260421_143502_scraping_real_20260421",
  "timestamp": "20260421_143502",
  "total": 500,
  "ready": 312,
  "needs_enrichment": 98,
  "rejected_notwine": 47,
  "uncertain": 43,
  "uncertain_pct": 8.6
}
```

Se `uncertain_pct > 20%`, stderr tem `[router] WARNING: uncertain_pct=X.XX% > 20% (nao bloqueante, veja summary.md)`.

---

## 5. Saidas

```
reports/ingest_pipeline/20260421_143502_scraping_real_20260421/
  ready.jsonl              ← compativel com ingest_via_bulk.py
  needs_enrichment.jsonl
  rejected_notwine.jsonl
  uncertain_review.csv     ← saida lateral
  summary.md               ← contadores + WARNING 20%
```

### JSONLs (ready / needs_enrichment / rejected_notwine)

Cada linha preserva os campos originais **e** adiciona metadados nao-destrutivos:

| Campo | Significado |
|---|---|
| `_router_status` | `ready` / `needs_enrichment` / `not_wine` / `uncertain` |
| `_router_reasons` | lista de strings auto-explicativas |
| `_router_source` | valor sanitizado de `--source` |
| `_router_index` | posicao do item no JSONL original (0-based) |

### `uncertain_review.csv`

Header fixo:

```
router_index,source,nome,produtor,safra,pais,regiao,sub_regiao,ean_gtin,reasons,raw_json
```

- `reasons` — separado por `;`.
- `raw_json` — item original serializado, **sem** os metadados `_router_*`.
- Arquivo CSV pra abrir no Excel/LibreOffice. Revisao humana e **opcional** — nunca bloqueia o pipeline.

### `summary.md`

Contem:
- input path / source / timestamp / output dir.
- Tabela de contadores com percentuais.
- `## WARNING` explicito quando `uncertain_pct > 20%`.
- Comando sugerido pra Fase 3 (`ingest_via_bulk.py` sem `--apply`).

---

## 6. Como interpretar cada bucket

### `ready.jsonl`

**O que e**: items que o dedup pode processar com seguranca.

**Criterios juntos (AND)**:
- nome normalizado >= 8 chars.
- produtor normalizado >= 3 chars.
- nome NAO e so termos genericos (`red`, `white`, `blend`, `reserva`, `brut`, `cuvee`, `house`, etc).
- pelo menos uma ancora geografica: `pais`, `regiao`, `sub_regiao` OU `ean_gtin`.

**O que fazer**: pode ir direto pro `ingest_via_bulk.py` em dry-run. Inspecao de amostra antes do apply pequeno continua obrigatoria (runbook do bulk_ingest, secao 4).

### `needs_enrichment.jsonl`

**O que e**: primeiro filtro passou, mas falta algum campo "consertavel" via enrichment.

**Ancoras tipicas**:
- nome forte (>=3 tokens nao-genericos) sem produtor.
- produtor presente, sem pais/regiao/ean.
- EAN presente com nome fraco.
- descricao longa (>=100 chars) com pistas.
- pista de uva no nome + faltando produtor ou geo.
- produtor conhecido compensando nome generico.

**O que fazer nesta fase**: **deixar esperando**. Fase 4 (enrichment Gemini) e rodada separada, com autorizacao explicita + custo controlado (REGRA 6). **Nao mandar direto pro bulk_ingest** — dedup gera ruido com item incompleto.

### `rejected_notwine.jsonl`

**O que e**: primeiro filtro deterministico bloqueou.

**Razoes tipicas** (em `_router_reasons`):
- `wine_filter=whisky` / `vodka` / `cerveja` / `cachaca` / etc (400+ regex).
- `abv_fora_10_15=X%`
- `volume_nao_padrao=X`
- `gramatura=Xg`
- `data_evento=Xth`
- `case_kit=...`

**O que fazer**: descartar ou logar. Se encontrar padroes novos (ex: licor X que passou), propagar pra `wine_filter.py` E `pre_ingest_filter.py` (regra de propagacao).

### `uncertain_review.csv`

**O que e**: nao foi possivel decidir automatico sem risco de Gemini inventar.

**Razoes tipicas** (em `reasons`):
- `uncertain:nome_e_produtor_vazios`
- `uncertain:nome_curto_sem_ean_sem_produtor`
- `uncertain:nome_generico_sem_produtor_sem_ean`
- `uncertain:sem_ancora_util`

**O que fazer**: **NAO bloquear o pipeline por causa disso**. Revisao humana e opcional — operador pode abrir no Excel, corrigir items, e alimentar um `ready_manual.jsonl` de volta numa proxima rodada. Mas pipeline automatico termina com sucesso mesmo se `uncertain > 0`.

**Soft warning** apenas se `uncertain_pct > 20%`: sinal de que o primeiro filtro ou o input estao degradados. Investigar a fonte antes de escalar volume.

---

## 7. Como rodar Fase 3 (dry-run do `ready.jsonl`)

Apos o router rodar sem erro:

```bash
python scripts/ingest_via_bulk.py \
  --input reports/ingest_pipeline/<timestamp>_<source>/ready.jsonl \
  --source <source>
```

**Nao adicionar `--apply`.** Dry-run e default da CLI.

O `ingest_via_bulk.py` le `DATABASE_URL` do `.env` e detecta `would_insert` / `would_update` contra o banco de producao **sem gravar**.

### Contadores a validar no output

- `received` = numero de linhas do `ready.jsonl`.
- `valid` = filtrado pelo `should_skip_wine` (deve ser ~100% porque o router ja filtrou).
- `would_insert` / `would_update` = decisao de dedup.
- `errors` = `[]` sempre.

---

## 8. Criterios para seguir

| Criterio | Meta | Se nao atender |
|---|---|---|
| `ready > 0` | ao menos um item util | investigar input; provavelmente todos caem em `needs_enrichment` ou `uncertain` |
| `rejected_notwine` plausivel | taxa compativel com a fonte | se >> esperado, inspecionar amostra — primeiro filtro pode estar agressivo demais |
| `uncertain_pct <= 20%` | soft gate | acima de 20% e warning — inspecionar `uncertain_review.csv` antes de escalar |
| `needs_enrichment` plausivel | % esperavel de items precisando Gemini | se muito alto, revisar fonte (scraping sujo) |
| dry-run do `ready.jsonl` sem `errors` | `errors: []` | investigar antes de qualquer apply |
| amostra de `would_insert` inspecionada | 10+ items legitimos | bloquear apply se encontrar item poluido |
| amostra de `would_update` inspecionada | tripla casa corretamente com banco | bloquear se match errado |

**So apos todos os criterios verdes**, solicitar autorizacao explicita do usuario pro apply pequeno (runbook do bulk_ingest, secao 5).

---

## 9. O que NAO fazer

- **Nao rodar `--apply` sem autorizacao explicita do usuario nesta conversa.** Sempre dry-run primeiro.
- **Nao jogar `needs_enrichment.jsonl` direto no `ingest_via_bulk.py`.** Esses items faltam ancora de dedup; vao para Fase 4 (Gemini), nao para o bulk.
- **Nao usar `uncertain_review.csv` como gate.** Pipeline continua sem esperar. Revisao humana e backlog opcional.
- **Nao chamar Gemini nesta fase.** Router e deterministico e puro (REGRA 6).
- **Nao criar migration, tabela nova, fila no banco** pra suportar esse fluxo. Arquivos JSONL bastam ate volume/retomabilidade justificarem.
- **Nao confiar que `rejected_notwine.jsonl` esta 100% correto.** Se inspecao amostral encontrar vinho valido la, ajustar `wine_filter.py` (nao "corrigir" o CSV).
- **Nao usar `--source` com espaco, acento, `..`, `/` ou `\`.** Router aborta com `source_invalido`. Use `[A-Za-z0-9_.-]`.

---

## 10. Rollback / limpeza

Todas as saidas sao **arquivos auditaveis** em `reports/ingest_pipeline/<ts>_<source>/`. Nao ha estado persistido fora disso — o router nao toca o banco.

### Casos

- **Smoke / teste**: pode apagar o diretorio inteiro quando terminar.
  ```bash
  rm -rf reports/ingest_pipeline/<ts>_<source>/
  ```

- **Lote real**: **manter o diretorio ate o fechamento do ciclo** (dry-run + apply + validacao SQL pos-apply). Serve de trilha de auditoria pra qualquer pergunta tipo "esse wine veio de que lote?".

- **Lote real ja aplicado**: pode arquivar mas nao deletar. Sugestao: mover pra `reports/ingest_pipeline/_archived/<YYYY-MM>/`.

- **Rollback de apply (se o bulk_ingest foi aplicado com dados ruins)**: a rotina e do runbook do bulk_ingest (`WINEGOD_PAIS_RECOVERY_BULK_INGEST_ROLLOUT_RUNBOOK.md`, secao 6). Tipicamente:
  ```sql
  DELETE FROM wines
  WHERE fontes @> '["bulk_ingest:<source>"]'::jsonb
    AND descoberto_em > NOW() - INTERVAL '2 hours'
    AND total_fontes = 0;
  ```
  O `<source>` a usar e o mesmo validado no router.

### Nao rodar o router no mesmo lote sem necessidade

Cada execucao cria um novo diretorio com timestamp. Re-rodar o mesmo input duplica artefatos no disco mas nao polui nada externo. Se precisar reproduzir um resultado especifico, passe `--timestamp YYYYMMDD_HHMMSS` explicito.

---

## 11. Fonte legado `vinhos_brasil_db` / scrapers antigos

Contexto: existe uma base **local** em `C:\natura-automation\vinhos_brasil\`
(`vinhos_brasil_db`) com ~146k wines e ~165k linhas em
`vinhos_brasil_fontes`, vinda dos scrapers antigos (vtex, magento,
mercadolivre, evino, loja_integrada, dooca, tray, mistral, sonoma,
shopify, woocommerce, wine_com_br, nuvemshop, videiras, tenda, amazon,
vtex_io, nacional, generico, html, vivino_br).

A ponte oficial entre essa base e o pipeline novo e:
`scripts/export_vinhos_brasil_to_router.py`. Ele e **somente leitura**
(`SET TRANSACTION READ ONLY`), nao imprime DSN/secrets, e emite um
JSONL compativel com `pre_ingest_router.py`.

### Fluxo ponta a ponta (legado -> producao)

```
vinhos_brasil_db (local)
       ↓ export_vinhos_brasil_to_router.py
reports/ingest_pipeline_inputs/<ts>_vinhos_brasil_<fonte|all>.jsonl
       ↓ pre_ingest_router.py
reports/ingest_pipeline/<ts>_<source>/
  ├─ ready.jsonl              → ingest_via_bulk.py (dry-run)
  ├─ needs_enrichment.jsonl   → Fase 4 Gemini (enrich_needs.py)
  ├─ rejected_notwine.jsonl   → log / descarte
  └─ uncertain_review.csv     → saida lateral (nao bloqueia)
```

### Comandos

```bash
# 1) Export — ex: 500 items do scraper vtex
python scripts/export_vinhos_brasil_to_router.py \
  --fonte vtex \
  --limit 500

# com paginacao:
python scripts/export_vinhos_brasil_to_router.py \
  --fonte vtex --limit 500 --offset 500

# 2) Router sobre o JSONL exportado (ajustar o caminho do step anterior)
python scripts/pre_ingest_router.py \
  --input reports/ingest_pipeline_inputs/<arquivo_exportado>.jsonl \
  --source vinhos_brasil_vtex_<timestamp>

# 3) Dry-run do bulk_ingest — SO sobre ready.jsonl
python scripts/ingest_via_bulk.py \
  --input reports/ingest_pipeline/<router_out>/ready.jsonl \
  --source vinhos_brasil_vtex_<timestamp>
# Sem --apply. Inspecionar amostras antes de qualquer apply.
```

### Contratos mantidos pelo exportador

- `nome`, `produtor`, `safra` (string YYYY), `tipo`, `pais` (ISO-2 lower),
  `regiao`, `sub_regiao`, `uvas` (JSON string), `ean_gtin`, `imagem_url`,
  `harmonizacao`, `descricao`, `preco_min`, `preco_max`, `moeda`.
- Campos de origem comercial (nao-underscore, entram no payload e
  sao preservados pelo router; `bulk_ingest` ignora desconhecidos):
  - `url_original` — URL da pagina do produto na loja.
  - `loja` — nome humano da loja/seller, extraido de `dados_extras`.
  - `fonte_original` — nome do scraper (vtex, magento, ...).
  - `preco_fonte` — preco registrado na linha `vinhos_brasil_fontes`.
  - `mercado` — geralmente `br`.
- Metadata de linhagem (underscore, tecnica):
  - `_origem_vinho_id`, `_source_dataset = vinhos_brasil_db`,
    `_source_table = vinhos_brasil`, `_source_scraper`, `_mercado`,
    `_preco_fonte`, `_fonte_original` (**alias historico**: recebe a URL
    da loja, nao o nome do scraper — novo codigo deve usar
    `url_original`).

### Interpretacao das saidas do router aplicada a este fluxo

- `ready.jsonl` → vai pro **dry-run** do `ingest_via_bulk.py`. Apply
  pequeno so com **autorizacao humana explicita** (runbook do bulk_ingest,
  secao 5).
- `needs_enrichment.jsonl` → vai pra **Fase 4 Gemini** via
  `scripts/enrich_needs.py` (consumidor dedicado). Nao mandar direto
  pro `bulk_ingest` — item incompleto polui dedup.
- `rejected_notwine.jsonl` → descarta. Se inspecao encontrar vinho real
  bloqueado por engano, ajustar `wine_filter.py` + `pre_ingest_filter.py`
  (regra de propagacao de NOT_WINE).
- `uncertain_review.csv` → **saida lateral, nunca bloqueia**. Revisao
  humana e opcional; pipeline termina OK mesmo com `uncertain > 0`.
- Apply pequeno com `--apply` so **apos autorizacao humana explicita**.

### Regras de seguranca do exportador

- **Read-only** na base legada: `SET TRANSACTION READ ONLY`.
- `--limit` default 500. Acima exige `--allow-large`.
- `--offset` default 0. Permite paginar lotes grandes sem recarregar.
- `--fonte` valida contra lista conhecida; fora da lista = warning, nao erro.
- Nao loga `DATABASE_URL`, `VINHOS_CATALOGO_DATABASE_URL`, credenciais.
- Mensagens de erro so mostram classe da excecao.

---

## Referencias

- Codigo: `scripts/pre_ingest_router.py`, `scripts/_ingest_classifier.py`,
  `scripts/export_vinhos_brasil_to_router.py`, `scripts/enrich_needs.py` (Fase 4).
- Filtros: `scripts/pre_ingest_filter.py`, `scripts/wine_filter.py`.
- Bulk ingest (Fase 3+): `backend/services/bulk_ingest.py`, `scripts/ingest_via_bulk.py`.
- Testes: `backend/tests/test_ingest_classifier.py` (30), `backend/tests/test_pre_ingest_router.py` (37), `backend/tests/test_export_vinhos_brasil_to_router.py` (35).
- Base legada: `C:\natura-automation\vinhos_brasil\db_vinhos.py`.
- Analise do fluxo bifurcado: `reports/WINEGOD_PRE_INGEST_ROUTER_ANALISE.md`.
- Handoff oficial do pre-ingest router: `reports/WINEGOD_PRE_INGEST_ROUTER_HANDOFF_OFICIAL.md`.
- Rollout do bulk_ingest: `reports/WINEGOD_PAIS_RECOVERY_BULK_INGEST_ROLLOUT_RUNBOOK.md`.
- Handoff do bulk_ingest: `reports/WINEGOD_PAIS_RECOVERY_HANDOFF_OFICIAL.md`.
