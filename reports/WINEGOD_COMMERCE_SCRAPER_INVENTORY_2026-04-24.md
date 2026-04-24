# WINEGOD - Commerce Scraper Inventory (Fase A)

Data: 2026-04-24  
Executor: Claude Code (Opus 4.7 1M context)  
Escopo: mapear scrapers commerce em `C:\natura-automation\` e tabelas em
`winegod_db` local, para fundamentar as fases B-F (exporters).

## 1. Scrapers identificados

| id | path | tier | estado | cadencia | grava em |
|---|---|---|---|---|---|
| Amazon espelho (ativo) | `C:\natura-automation\amazon\main.py` (orchestrator.py, query_executor.py) | commerce-amazon | **ATIVO no PC espelho** | on-demand (queries `amazon_queries`) | `public.amazon_queries`, `public.amazon_categorias`, `public.vinhos_{pais}_fontes` (fonte `amazon_playwright`/`amazon_scraper`/`amazon_scrapingdog`) |
| Amazon legacy (desativado) | mesma pasta `amazon\` (legado) + dados residuais em `vinhos_{pais}_fontes` com `fonte ILIKE 'amazon%'` | commerce-amazon | PAUSADO, dados historicos > 60k linhas | one-time backfill | historico no proprio `vinhos_{pais}_fontes` |
| Tier1 (Codex/Admin) | `C:\natura-automation\winegod_admin\scraper_tier1.py` (+ `winegod_codex\scraper_tier1.py`) | commerce-tier1 (APIs/sitemap deterministico) | **PAUSADO; volta ao lancar, cadencia semanal** | semanal | `public.vinhos_{pais}`, `public.vinhos_{pais}_fontes`, `public.lojas_scraping`, `public.scraping_execucoes` (tier=1) |
| Tier2 (Codex - 5 chats globais) | `C:\natura-automation\winegod_admin\scraper_tier2.py` + `winegod_codex\tier2_service.py` | commerce-tier2 (Playwright + IA Grok/DeepSeek) | **PAUSADO; volta ao lancar, semanal** | semanal | idem Tier1, com `tier=2` em `scraping_execucoes` |
| Tier2 BR (`vinhos_brasil\`) | `C:\natura-automation\vinhos_brasil\main.py` + `scraper_*.py` (woocommerce, vtex, shopify, magento, etc.) | commerce-tier2-br | **PAUSADO** | semanal | `vinhos_brasil_db`.`public.vinhos_brasil`, `.vinhos_brasil_fontes`, `.vinhos_brasil_execucoes` |

### Prompts Codex (onde moram)

Em `C:\natura-automation\` (root, top-level):

- `prompt_tier2_admin.md`
- `prompt_tier2_br.md`
- `prompt_tier2_chat1.md` - AU/DK/RO/ES/MD/PT (1610 lojas)
- `prompt_tier2_chat2.md` - KR/TR/AR/NL/PH/CL (1604 lojas)
- `prompt_tier2_chat3.md` - FR/JP/PL/US/AT/HK/LU/CA/TH/GR (1586 lojas)
- `prompt_tier2_chat4.md` - DE/CH/IN/IL/GB/CN (1601 lojas)
- `prompt_tier2_chat5.md` - TW/BE/NO/NZ/FI/SG/IE/HU/SE/RU (1586 lojas)

Esses chats **NAO tem particao disjunta reproduzivel** no DB (todos os
chats gravam em `vinhos_{pais}` com o mesmo schema via `scraper_tier2.py`).
Por isso o plug commerce colapsou em `tier2_global_artifact` unico.

### Dashboard

- `C:\natura-automation\winegod_codex_dashboard.bat` inicia
  `winegod_codex\server.py` na porta 5568 (FastAPI/Flask) com
  classificador de lojas Tier1/Tier2 e upload de prompts.
- Nao e scraper; e painel de controle.

## 2. Estrutura relevante de `C:\natura-automation\`

```
C:\natura-automation\
  .env, .env.local                    # creds Postgres local + providers IA
  backup_diario.bat                   # rclone sync dump winegod_db + zip source
                                      # (NAO inclui logs/checkpoints - Fase M)
  winegod_codex_dashboard.bat         # launcher dashboard
  amazon\
    main.py                           # CLI amazon (setup / generate / run)
    orchestrator.py
    query_executor.py
    query_generator.py
    db_amazon.py                      # cria amazon_queries/categorias/reviews
    utils_playwright.py
    config.py
  winegod_admin\
    scraper_tier1.py                  # Shopify/VTEX/WooCommerce HTTP deterministico
    scraper_tier2.py                  # Playwright + IA (Grok -> DeepSeek)
    db_scraping.py                    # cria lojas_scraping, vinhos_{pais}, vinhos_{pais}_fontes, scraping_execucoes
    pipeline_discovery.py             # discovery stores
    server.py                         # admin UI
  winegod_codex\
    scraper_tier1.py                  # equivalente, acesso WINEGOD_CODEX_DATABASE_URL
    tier2_service.py
    server.py                         # codex UI porta 5568
  vinhos_brasil\
    main.py                           # CLI tier2_br
    db_vinhos.py                      # cria vinhos_brasil/vinhos_brasil_fontes em vinhos_brasil_db
    scraper_woocommerce.py / ...      # ~25 scrapers por plataforma
    CLAUDE.md                         # doc mestre (status 146k vinhos BR)
  prompts Tier2 (listados acima)
  _amazon_run*.log                    # nao commitados, nao backupados (Fase M)
  _ct_scraper_progress.json           # nao backupado (Fase M)
```

## 3. Tabelas relevantes em `winegod_db` local

Total de tabelas no schema `public`: **175**.

### 3.1 Amazon

| tabela | linhas | escopo | usada por |
|---|---:|---|---|
| `amazon_queries` | 16.609 | queries geradas para buscar vinhos na Amazon por pais/template | Amazon scraper (ativo) |
| `amazon_categorias` | 18 | checkpoint de scraping por node_id | Amazon scraper (ativo) |
| `amazon_reviews` | 0 | reservada para reviews Amazon (nao usada) | - |

Dados Amazon produto vivem nos proprios `vinhos_{pais}_fontes`
com `fonte ILIKE 'amazon%%'`. Totais por fonte:

| coluna `fonte` | escopo | comentario |
|---|---|---|
| `amazon_playwright` | feed ativo do espelho | scraper atual |
| `amazon_scraper` | feed espelho historico (legado) | primeira versao do scraper |
| `amazon_scrapingdog` | scraper via ScrapingDog API | alternativa |
| `amazon` | feed inicial simples | legado puro |

Total: **~64.8k** linhas em `vinhos_*_fontes` com `fonte ILIKE 'amazon%%'`.
Top paises: JP (24.587), BR (15.787), DE (7.036), NL (4.305), US (3.726),
IE (2.833), MX (1.813), GB (945), AU (577), IT (570), FR (491), etc.

### 3.2 Tier1 / Tier2 / Tier2 BR

| tabela | linhas | papel |
|---|---:|---|
| `vinhos_{pais}` (49 paises, ex: `vinhos_us`, `vinhos_br`) | ~4.98 M total | vinhos unificados pos-dedup |
| `vinhos_{pais}_fontes` (49) | ~5.81 M total | relacao vinho-loja-preco com coluna `fonte` (plataforma) |
| `lojas_scraping` | 86.089 | cadastro lojas + `metodo_recomendado` (tier) |
| `scraping_execucoes` | 1.108 | log por pais + `tier` + status |

Top paises por volume de `vinhos_{pais}`:
US 848k, BR 254k, GB 232k, IT 216k, DE 215k, AU 201k, CA 119k, ES 125k, MX 133k, AR 134k, etc.

### 3.3 Classificacao Tier1 vs Tier2 (lojas_scraping.metodo_recomendado)

| metodo | count | tier |
|---|---:|---|
| `url_morta` | 44.769 | inativo |
| `playwright_ia` | 18.786 | Tier2 |
| `sitemap_html` | 8.048 | Tier1 |
| `api_woocommerce` | 6.473 | Tier1 |
| `api_shopify` | 4.988 | Tier1 |
| NULL | 2.328 | indefinido |
| `sitemap_jsonld` | 448 | Tier1 |
| `nao_scrapeavel` | 151 | inativo |
| `api_vtex` | 84 | Tier1 |
| outros sitemap_* | 14 | Tier1 |

Regra deste projeto (confirmada no producer `build_commerce_artifact.py`):

- Tier1 = `api_shopify` + `api_woocommerce` + `api_vtex` + `sitemap_html` + `sitemap_jsonld`
- Tier2 = `playwright_ia`
- Tier2 BR = `playwright_ia` AND `pais_codigo='BR'`

### 3.4 Top paises por plataforma (sample fontes)

Top `fonte` em `vinhos_us_fontes`: shopify (778k), woocommerce (161k), codex_light (12k), amazon_playwright (3.3k), grok (817), opus (478).

Top `fonte` em `vinhos_br_fontes`: vtex (71k), woocommerce (32k), magento (27k), codex_light (19k), shopify (15k), dooca (14k), loja_integrada (13k), nuvemshop (11k).

### 3.5 Outras tabelas observadas (fora do escopo commerce)

Tabelas `ct_*`, `decanter_*`, `exec_*`, `flash_*`, `match_results_*`
pertencem ao dominio reviews/enrichment/discovery. Nao sao fonte de
exporter commerce.

## 4. Fluxo arquitetural

```
[scrapers em C:\natura-automation\]
  amazon\main.py ---------> public.vinhos_{pais}_fontes (fonte=amazon_playwright)
  winegod_admin\scraper_tier1.py -> public.vinhos_{pais}(_fontes) (tier=1)
  winegod_admin\scraper_tier2.py -> public.vinhos_{pais}(_fontes) (tier=2 playwright_ia)
  vinhos_brasil\main.py -----> vinhos_brasil_db.public.vinhos_brasil(_fontes)
                                  |
                                  v
                           [PC espelho winegod_db local]
                                  |
                              (rclone 04:00)
                                  v
                   gdrive:winegod-backups/backup_winegod_db_YYYYMMDD.dump
                                  |
                           [este repo winegod-app]
                                  |
                    [Fase B-F: 5 exporters]
                                  v
             reports/data_ops_artifacts/
               amazon_mirror/          (amazon_mirror_primary)
               amazon_local_legacy_backfill/ (NOVO nesta rodada)
               tier1/                  (tier1)
               tier2_global/           (tier2)
               tier2/br/               (tier2)
                                  v
                sdk/plugs/commerce_dq_v3/runner.py (via artefatos)
                                  v
                    Render: public.wines + public.wine_sources
```

## 5. Gaps identificados

1. **Contrato contra schema real**: `vinhos_{pais}_fontes` usa coluna
   `fonte` para plataforma (ex: `woocommerce`, `amazon_playwright`), nao
   e equivalente a `pipeline_family`. O exporter precisa mapear.
2. **Campo `captured_at`**: `vinhos_{pais}` tem `descoberto_em` +
   `atualizado_em`; `_fontes` tem `descoberto_em` + `atualizado_em`. Usar
   `COALESCE(f.atualizado_em, f.descoberto_em, v.atualizado_em, v.descoberto_em)`.
3. **`store_name` / `store_domain`**: vem via JOIN com `lojas_scraping`
   (host normalizado), como ja faz `build_commerce_artifact.py`. Reaproveitar.
4. **Amazon legacy separado do mirror**: unica diferencia entre `fonte`
   `amazon_playwright` (mirror ativo) e `amazon_scraper`/`amazon`/
   `amazon_scrapingdog` (legados). Filtro por `fonte` explicito.
5. **Tier2 BR existe em dois bancos**: `winegod_db` (legacy mixed) e
   `vinhos_brasil_db` (padrao). Para esta rodada: Tier2 BR e consumido
   via `winegod_db`.`vinhos_br_fontes` com filtro `fonte` = plataformas
   Tier2 (fonte ILIKE playwright% ou tier=2), ou via
   `lojas_scraping.metodo_recomendado=playwright_ia`.
6. **Amazon reviews vazio**: `amazon_reviews` esta com 0 linhas; nao
   afeta escopo commerce (reviews sao outra frente).
7. **`vinhos_brasil_db` separado**: o repo mesmo ja expoe
   `VINHOS_BRASIL_DATABASE_URL` via `scripts/export_vinhos_brasil_to_router.py`
   usado pelo exporter existente `export_vinhos_brasil_legacy_to_dq`. Esta
   rodada NAO duplica esse canal; ele ja e consumido pelo plug. O novo
   `tier2_br` exporter consome o `winegod_db`.`vinhos_br_fontes` com
   criterio Tier2 real, nao o `vinhos_brasil_db` paralelo.
8. **Amazon mirror ativo maximo descoberto_em em us**: `2026-04-08 13:45 UTC`
   - ja tem tempo parado; usuario confirmou que volta a rodar antes do
   lancamento. Exporter incremental usa state file para nao duplicar.

## 6. Bancos envolvidos

| banco | DSN env var | papel | acesso |
|---|---|---|---|
| `winegod_db` (localhost:5432) | `WINEGOD_DATABASE_URL` (tambem `WINEGOD_CODEX_DATABASE_URL`) | dados de scraping Tier1/Tier2/Amazon | **READ-ONLY nesta rodada** |
| `vinhos_brasil_db` (localhost:5432) | `VINHOS_BRASIL_DATABASE_URL` | dados `vinhos_brasil\` | READ-ONLY via exporter existente |
| `winegod` (Render) | `DATABASE_URL` | banco de producao | NAO TOCADO nesta rodada |

## 7. Resumo executivo

- 5 scrapers identificados (1 Amazon espelho ativo + 1 Amazon legacy
  pausado + 1 Tier1 pausado + 1 Tier2 Codex pausado + 1 Tier2 BR
  pausado).
- Dados de todos ja estao no `winegod_db` local (alem do
  `vinhos_brasil_db` para Tier2 BR). Os exporters das fases B-F leem
  esse banco em read-only e geram JSONL canonico para o plug.
- Nenhum scraper precisa ser "reconstruido" por este repo. Quando os
  Tier1/Tier2 voltarem a rodar (semanal pos-lancamento), os exporters
  desta rodada ja estao prontos para consumir.

## 8. Nao localizados / zona cinza

- Nenhum scraper "nao_localizado". Todos os 5 foram encontrados com
  path + linha.
- `amazon_reviews` (tabela existe com 0 linhas) - provavelmente
  reservada para scraper Amazon reviews futuro. Fora do escopo commerce.
