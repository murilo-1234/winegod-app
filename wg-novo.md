# WG-NOVO — Guia do PC Scraper

PC principal (origem): **clubemac**, IP **192.168.1.2** (Wi-Fi)

## Repos para clonar (todos privados, GitHub murilo-1234)

| Repo | Clone | O que tem |
|---|---|---|
| `winegod-app` | `git clone https://github.com/murilo-1234/winegod-app.git` | Produto (chat + API) + 170 scripts de pipeline |
| `natura-automation` | `git clone https://github.com/murilo-1234/natura-client-automation.git` | Projeto Natura + **76 scripts WineGod misturados** |
| `winegod` | `git clone https://github.com/murilo-1234/winegod.git` | Repo de dados (quase vazio, so scaffolding) |

**IMPORTANTE:** Os scripts de scraping do WineGod estao em 2 repos diferentes:
- `winegod-app/scripts/` — 154 scripts (matching, dedup, classificacao, import, audit)
- `winegod-app/wine_classifier/` — 16 scripts (classificacao via browser com LLMs)
- `natura-automation/` — 76 scripts WineGod (scrapers tier1/tier2, codex, testes de score)

O repo `winegod/` (dados) tem so 17 arquivos Python basicos (utils, config). Nao tem scripts de execucao.

---

## Setup no PC novo

### 1. Instalar

- Python 3.11+
- PostgreSQL 16 (local, user `postgres`, password `postgres123`, database `winegod_db`)
- Git
- Google Chrome + Microsoft Edge (para wine_classifier)
- Node.js 18+ (so se for rodar o frontend)

### 2. Clonar os repos

```bash
cd C:\
git clone https://github.com/murilo-1234/winegod-app.git
git clone https://github.com/murilo-1234/natura-client-automation.git natura-automation
```

### 3. Copiar o .env (do PC principal, NAO esta no git)

Copiar `C:\winegod-app\backend\.env` do clubemac para o mesmo caminho no PC novo.
Contem: ANTHROPIC_API_KEY, GEMINI_API_KEY, DATABASE_URL, FLASK_ENV, FLASK_PORT.

### 4. Instalar dependencias Python

```bash
cd C:\winegod-app
pip install -r requirements.txt
```

### 5. Sincronizar dia a dia

```bash
cd C:\winegod-app && git pull
cd C:\natura-automation && git pull
```

---

## Onde esta cada coisa

### winegod-app/scripts/ (154 scripts)

| Categoria | Scripts | O que fazem |
|---|---|---|
| **Classificacao API** | `pipeline_y2.py`, `pipeline_y2_async.py` | Dashboard Flask com Gemini Flash, 50-200 workers |
| **Matching Vivino** | `match_vivino_1.py` a `_15.py`, `match_vivino.py` | Matching de 3.96M vinhos, shardado por faixa |
| **Dedup** | `dedup_crossref.py`, `dedup_group_1.py` a `_10.py` | Dedup 3 niveis (exato, fuzzy, produtor) |
| **Trigram** | `trgm_batch.py`, `trgm_fast.py` | Matching via pg_trgm no PostgreSQL |
| **Import/Export** | `import_vivino_local.py`, `import_stores.py`, `import_render_z.py` | Mover dados entre local e Render |
| **Score/WCF** | `calc_score.py`, `calc_score_incremental.py`, `calc_wcf_*.py` | Calcular WineGod Score e nota WCF |
| **Cron** | `cron_score_recalc.py` | Recalculo de score (15min fila + 4am sweep) |
| **Limpeza** | `clean_wines.py`, `fix_wines_clean_*.py`, `fix_prices*.py` | Normalizar nomes, encoding, precos |
| **Wrong Owner** | `wrong_owner_*.py` (15 scripts) | Remover vinhos com produtor errado |
| **Aliases** | `find_alias_candidates.py`, `generate_aliases.py` | Dedup manual e aliases |
| **Lotes Codex** | `gerar_lotes_codex.py`, `salvar_respostas_codex.py` | Gerar e salvar lotes para classificacao |
| **Audit** | `audit_*.py`, `analyze_baco_responses.py` | Auditorias de dados e respostas |
| **Testes** | `teste_*.py`, `test_*.py`, `validate_*.py` | Testes pontuais e validacao |

### winegod-app/wine_classifier/ (16 scripts)

| Script | O que faz |
|---|---|
| `run_chrome.py` | 8 abas: 4 ChatGPT + 4 Gemini Rapido |
| `run_edge.py` | 5 abas Claude Opus |
| `run_mistral.py` | 5 abas Mistral Le Chat |
| `setup_chrome.py`, `setup_edge.py`, `setup_mistral.py` | Login nos browsers |
| `drivers/` (8 arquivos) | Drivers: chatgpt, claude, mistral, gemini, grok, qwen, glm, base |

### natura-automation/ (76 scripts WineGod)

| Categoria | Scripts | O que fazem |
|---|---|---|
| **Scrapers tier1** | `_rodar_tier1_todos.py`, `_rodar_tier1_paralelo.py` | Scraping de lojas de vinho |
| **Scrapers tier2** | `_run_tier2_chat*.py` (15+) | Classificacao via chat (paises especificos) |
| **Codex** | `_codex_*.py` (7 scripts) | Amazon scraper, importar/classificar blocos |
| **Testes score** | `_test_ct_score_precision_r*.py` (7 versoes) | Calibracao de score |
| **Testes LLM** | `_test_*modelos*.py`, `_test_gemini_*.py`, `_test_grok_*.py` | Comparacao de IAs |
| **Vivino testes** | `_test_vivino_ct_*.py` (6 scripts) | Testes de matching Vivino |
| **Salvar lotes** | `_save_lote*.py`, `_add_tier*.py` | Salvar resultados no banco |
| **Scraper paises** | `_scraper_AR_*.py`, `_scraper_ct.py`, `_scraper_tier2_br_ar.py` | Scrapers especificos |

---

## Banco de dados

| Banco | Onde | Uso |
|---|---|---|
| **winegod** (Render) | `DATABASE_URL` no `.env` | Producao. 1.72M vinhos, 57K lojas. Acessado via internet. |
| **winegod_db** (local) | `localhost:5432` | Trabalho local. Matching, dedup, classificacao. |

---

## BAT files (atalhos para rodar)

```
winegod-app/scripts/PIPELINE_Y2.bat         -> pipeline_y2.py (dashboard porta 8050)
winegod-app/scripts/PIPELINE_Y2_ASYNC.bat    -> pipeline_y2_async.py (200 async)
winegod-app/scripts/run_mistral_classifier.bat -> mistral_classifier.py
winegod-app/wine_classifier/run_chrome.bat   -> run_chrome.py (8 abas)
winegod-app/wine_classifier/run_edge.bat     -> run_edge.py (5 abas Claude)
winegod-app/wine_classifier/run_mistral.bat  -> run_mistral.py (5 abas Mistral)
```

---

## Credenciais

Tudo no arquivo `winegod-app/backend/.env` (NAO esta no git).
Scripts carregam automaticamente via `import _env` (modulo em `scripts/_env.py`).
