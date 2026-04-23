# HANDOFF — Scraper Amazon em produção (estado atual)

> **Para o Claude que recuperar esta sessão**: o scraper Amazon está rodando em 9 processos. Este documento descreve EXATAMENTE o que existe, como está rodando e como retomar sem quebrar nada. **NÃO é plano de evolução — é documentação do estado.** Atualizado em 2026-04-16 ~12:00.

---

## 0. Regra de ouro antes de encostar

1. O scraper NÃO mora neste repo. Mora em `C:\natura-automation\`. Regra 4 do `C:\winegod-app\CLAUDE.md`: este repo é o PRODUTO (chat+API), não o pipeline.
2. **9 processos Playwright estão ativos agora** (7 em v2, 2 em v1). Matar qualquer um = perder vinhos em memória que ainda não foram salvos no chunk atual.
3. Banco local: PostgreSQL 16 em `localhost:5432`, db `winegod_db`, user `postgres`, senha `postgres123`.
4. Binário psql: `C:\Program Files\PostgreSQL\16\bin\psql.exe`.
5. Python 3.12.10 + Playwright **1.58.0** + Chromium 145 + playwright-stealth 2.0.3.

---

## 1. O que mudou nesta sessão (v1 → v2)

### 1.1 Problema identificado

Fase 1.5 do scraper (queries enriquecidas: uvas, regiões, vinícolas) usava busca simples sem split de preço. A Amazon corta paginação em ~7 páginas (~400 itens), mas muitas queries populares (ex: "Cabernet Sauvignon wine") têm milhares de resultados. O scraper perdia a maioria silenciosamente.

### 1.2 Estudo empírico (filter_research.py)

Criamos `C:\natura-automation\amazon\filter_research.py` — script de pesquisa que testa 10 estratégias de quebra de busca em paralelo ao scraper (browser próprio, banco read-only).

**Resultado com "cabernet sauvignon wine" em US:**

| Estratégia | ASINs únicos | Novos vs baseline |
|---|---|---|
| Baseline (sem filtro) | 321 | — |
| **Split por preço (6 faixas)** | **632** | **+329 (2x)** |
| Sort=price-asc | 194 | +52 |
| Sort=price-desc | 193 | +52 |
| Sort=review-rank | 193 | +55 |
| Sort=date-desc | 194 | +55 |
| Rating ≥4★ | 325 | +78 |
| **União de tudo** | **796** | **+475 (2.48x)** |

Split por preço é o vencedor: 2x mais ASINs, 0.5% de repetição entre faixas. Resultado salvo em `C:\natura-automation\logs\filter_research_US_20260415_190140.json`.

### 1.3 Mudanças no código

**`C:\natura-automation\amazon\db_amazon.py`** — 2 funções novas:
- `iniciar_query_execucao(pais, template, query_text, parametros, fase)` → INSERT/UPDATE em `amazon_queries`, status `rodando`, retorna `id`
- `finalizar_query_execucao(query_id, status, paginas, itens, novos, dupes, tempo_s, erro)` → fecha com métricas

**`C:\natura-automation\amazon\orchestrator.py`** — 3 mudanças:
1. **3 flags CLI novas**: `--uvas-max N`, `--vinicolas-max N`, `--enrich-split-preco`
2. **Constantes novas (module-level)**:
   ```python
   ENRICH_UVAS_MAX = 40            # default historico (de UVAS = 150)
   ENRICH_VINICOLAS_MAX = 500      # default historico (de VINICOLAS_MUNDO = 87044)
   ENRICH_SPLIT_PRECO = False      # se True, enrich usa scrape_faixa_adaptativa
   ```
3. **Loop de enrich (Fase 1.5) reescrito** — cada query tagueada com template (`enrich_uva`, `enrich_regiao`, `enrich_vinicola`, `enrich_autocomplete` — com sufixo `_x_preco` se split ativo) e registra início+fim no banco com delta de novos/dupes/tempo.
4. Quando `--enrich-split-preco` está ligado: chama `scrape_faixa_adaptativa()` (mesma função de Fase 2 que divide recursivamente por preço) em vez de `paginar_faixa()` simples.

**Banco** — view nova:
```sql
CREATE OR REPLACE VIEW progresso_estrategias AS
SELECT pais_codigo, template,
  COUNT(*) FILTER (WHERE status='ok') AS queries_ok,
  COUNT(*) FILTER (WHERE status='erro') AS queries_erro,
  COUNT(*) FILTER (WHERE status='rodando') AS queries_rodando,
  COALESCE(SUM(vinhos_novos), 0) AS vinhos_novos_total,
  COALESCE(SUM(vinhos_duplicados), 0) AS vinhos_dupes_total,
  MAX(executado_em) AS ultima_execucao
FROM amazon_queries GROUP BY pais_codigo, template;
```

### 1.4 Filosofia de estratégias (decisão do usuário)

**Todas as estratégias que trouxerem qualquer vinho serão executadas em todos os países.** Não é competição — é soma. O estudo serve para definir ORDEM de execução e eliminar só o que traz zero. Sempre buscar NOVAS formas para somar à pilha.

Destino final: todo este trabalho vira um **app autônomo** que o usuário vai criar para rodar independente do Claude.

---

## 2. Processos rodando agora (2026-04-16 ~12:00)

| País | Versão | PID | Início | Log | Status |
|---|---|---|---|---|---|
| US | **v2** | 13372 | 15-abr 21:46 | `relaunch_20260415/US_v2.log` | Regiões 1.333/2.580 (51%) |
| NL | **v2** | 14156 | 16-abr 11:39 | `relaunch_20260416/NL_v2.log` | Uvas (início) |
| CA | **v2** | 10008 | 16-abr 11:39 | `relaunch_20260416/CA_v2.log` | Uvas (início) |
| DE | **v2** | 14308 | 16-abr 11:39 | `relaunch_20260416/DE_v2.log` | Uvas (início) |
| AU | **v2** | 15880 | 16-abr 11:39 | `relaunch_20260416/AU_v2.log` | Uvas (início) |
| IT | **v2** | 15376 | 16-abr 11:39 | `relaunch_20260416/IT_v2.log` | Uvas (início) |
| JP | **v2** | 14560 | 16-abr 11:39 | `relaunch_20260416/JP_v2.log` | Uvas (início) |
| BR | v1 | 8912 | 15-abr 03:19 | `relaunch_20260415/BR.log` | Terminando (dedup stalls) |
| MX | v1 | 5400 | 15-abr 03:19 | `relaunch_20260415/MX.log` | Terminando (dedup stalls) |

**Quando BR e MX terminarem v1, relançar em v2** com:
```bash
cd C:\natura-automation
nohup python -u amazon/orchestrator.py --pais BR --fase A \
  --uvas-max 150 --vinicolas-max 2000 --enrich-split-preco \
  > logs/relaunch_20260416/BR_v2.log 2>&1 &
```

**Como verificar se continuam vivos:**
```bash
tasklist | grep python
# Esperar 9 linhas. Se cair abaixo, ver quem morreu.
```

**Como ver o que cada um está fazendo agora:**
```bash
tail -n 20 C:/natura-automation/logs/relaunch_20260416/<PAIS>_v2.log
# ou para v1:
tail -n 20 C:/natura-automation/logs/relaunch_20260415/<PAIS>.log
```

---

## 3. Tracking — como ver progresso por estratégia

```bash
PGPASSWORD=postgres123 "C:/Program Files/PostgreSQL/16/bin/psql.exe" \
  -h localhost -U postgres -d winegod_db -c \
  "SELECT * FROM progresso_estrategias ORDER BY pais_codigo, template;"
```

**Estado do tracking em 2026-04-16 ~12:00:**

| País | Template | Queries OK | Novos | Dupes |
|---|---|---|---|---|
| AU | enrich_uva_x_preco | 3 | 2 | 178 |
| IT | enrich_uva_x_preco | 1 | 0 | 66 |
| NL | enrich_uva_x_preco | 8 | 0 | 12 |
| US | enrich_uva_x_preco | 150 ✅ | 377 | 652 |
| US | enrich_regiao_x_preco | 1.333 (rodando) | 2.484 | 5.207 |

Tracking só existe para processos v2. Processos v1 (BR, MX) e execuções anteriores não registram.

---

## 4. Arquitetura (sem inventar — descrevendo o que está em disco)

### 4.1 Código
```
C:\natura-automation\amazon\
  orchestrator.py       ~1.100 linhas — pipeline (Fase A + B + C), agora com flags v2
  utils_playwright.py   1.129 linhas — browser, extração, bloqueio, 14 campos Fase B
  config.py               347 linhas — MARKETPLACES, UVAS(150), REGIOES(250), PRODUTORES(175), WINE_KEYWORDS
  autocomplete.py         160 linhas — Amazon Autocomplete API (grátis, sem auth)
  regioes_mundo.py      2.588 linhas — 2.580 regiões vinícolas (inglês/original, do Vivino)
  vinicolas_mundo.py   87.044 linhas — 87K vinícolas ordenadas por popularidade (Vivino, 100+ ratings)
  filter_research.py      250 linhas — NOVO: estudo empírico de estratégias de quebra de busca
  category_discovery.py   191 linhas — descobre node "Wine" automaticamente
  query_generator.py      194 linhas — gerador legado (referência)
  query_executor.py       312 linhas — _UVAS_CONHECIDAS
  db_amazon.py            ~410 linhas — get_connection, criar_tabelas, iniciar/finalizar_query_execucao, tracking
  main.py                 220 linhas

C:\natura-automation\winegod_codex\
  db_scraping.py          — criar_tabelas_vinhos, upsert_vinhos_batch (LOTE_UPSERT)
  utils_scraping.py       — eh_vinho, inferir_pais, inferir_tipo_vinho, gerar_hash_dedup, normalizar_texto
  classifier.py, scraper_tier1.py, tier2_service.py, server.py, templates/, cache/
```

### 4.2 Banco (tabelas que importam)

Por país (18): `vinhos_<xx>` + `vinhos_<xx>_fontes`. Schema igual ao handoff anterior.

Tabelas de suporte:
- `amazon_categorias` (20 linhas — node_ids descobertos)
- `amazon_queries` (**ativa desde v2** — tracking de cada query executada: template, status, métricas)
- `amazon_reviews` (0 — Fase C nunca rodou)
- `progresso_estrategias` (VIEW — resumo por país × template)

### 4.3 Contagem atual (2026-04-16 ~12:00)

```
IE 65.211 · NL 38.303 · CA 32.139 · US 21.353 · PL 17.735 · DE 16.471
MX 16.140 · IT 11.432 · BR 10.979 · BE 10.603 · AU 10.293
SG 6.656 · JP 5.948 · FR 2.976 · AE 2.635 · GB 2.566 · SE 2.156 · ES 1.885
Total ~273K linhas (era ~245K em 15-abr 13:35)
```

---

## 5. Como o scraper extrai vinhos — v1 vs v2

### v1 (comportamento original, sem flags)

Fase 1.5 roda `paginar_faixa()` simples por keyword. Amazon corta em ~7pgs (~400 itens). Queries populares (uvas comuns, regiões grandes) perdem a maioria dos resultados. Cobertura: UVAS[:40] + REGIOES_MUNDO (2.580) + VINICOLAS_MUNDO[:500] + autocomplete.

### v2 (com `--uvas-max 150 --vinicolas-max 2000 --enrich-split-preco`)

Fase 1.5 roda `scrape_faixa_adaptativa()` — mesma função de Fase 2 que detecta se Amazon declara >700 resultados e divide recursivamente por faixa de preço até `SPLIT_FLOOR=5`. Cada query é registrada em `amazon_queries` com template, métricas e tempo.

Cobertura v2: UVAS[:150] (todas) + REGIOES_MUNDO (2.580) + VINICOLAS_MUNDO[:2000] + autocomplete.

**Execução v2 por país (estimativa):**
- Uvas: ~150 queries × split → ~2-4h
- Regiões: ~2.580 queries × split → ~2-3 dias
- Vinícolas: ~2.000 queries × split → ~1-2 dias
- Total: ~3-5 dias por país

### Fases A, B, C (inalteradas)

- **Fase A**: discovery (cat × keyword → enrich → keyword sem cat → catch-all). V2 só muda o enrich.
- **Fase B**: enriquecimento individual — visita `/dp/<asin>`, extrai 14 campos. Roda com `--fase B`.
- **Fase C**: reviews (nunca rodou em produção). Tabela `amazon_reviews` vazia.

---

## 6. Constantes e comportamentos críticos

```python
# orchestrator.py
FONTE                 = "amazon_playwright"
BROWSER_RESTART_PAGES = 500       # restart browser inteiro a cada 500 pgs (libera RAM)
SAVE_CHUNK_PAGES      = 10        # flush no banco a cada 10 pgs
MAX_PAGES_POR_FAIXA   = 150       # cap duro anti-loop
DEDUP_STALL_PAGES     = 5         # para se 5 pgs seguidas com <3% novos
DEDUP_STALL_RATIO     = 0.03
SPLIT_FLOOR           = 5         # abaixo deste delta, não divide mais

# Flags v2 (configuraveis via CLI, defaults abaixo)
ENRICH_UVAS_MAX       = 40        # --uvas-max (v2 usa 150)
ENRICH_VINICOLAS_MAX  = 500       # --vinicolas-max (v2 usa 2000)
ENRICH_SPLIT_PRECO    = False     # --enrich-split-preco (v2 liga)
```

### Anti-bot tiers (em `utils_playwright.AdaptiveDelay`)
| Tier | Marketplaces | Delay base | Rotação contexto |
|---|---|---|---|
| Normal | BR US MX CA JP NL SE IE SG BE AU DE IT ES | 0.3s | 500 pgs |
| Sensitive | GB | 3.0s | 50 pgs |
| Ultra | FR PL AE | 6.0s | 15 pgs |

### Preço teto por moeda (`PRECO_TETO`)
```
BRL 20.000 · USD 5.000 · EUR 5.000 · GBP 4.000
JPY 750.000 · CAD 7.000 · AUD 8.000 · MXN 100.000
PLN 20.000 · SEK 55.000 · SGD 7.000 · AED 20.000
```

---

## 7. Problemas conhecidos

1. **IT/ES layout `_c2Itd`** — SERP discovery sem preço. Preço só vem na Fase B.
2. **DE/FR/GB** — ~35-48% dos cards sem preço no SERP. Fase B resolve.
3. **Contaminação parcial em IT** — BLACKLIST não cobre "cavatappi", "bicchieri", "cantinetta".
4. **Fase B trava em marketplaces sensíveis** — PL: 0/899 (captcha imediato). MX: 8%.
5. **Fase C (reviews)** — código pronto, nunca rodou em produção.
6. **Regiões: 2.580 vs 2.765** — arquivo `regioes_mundo.py` (Vivino) tem 2.580; fonte PT antiga tinha 2.765. Diferença de ~185 regiões perdidas na migração. Decidido: não corrigir agora, possível fazer merge depois.
7. **Vinícolas: 2.000 de 87.044** — v2 usa top 2.000 (por popularidade Vivino). Teste em ondas planejado (2K→5K→10K) mas não executado ainda. Depende do ROI em JP/US.

---

## 8. Estratégias de busca testadas empiricamente

Resultado do estudo `filter_research.py` (US, "cabernet sauvignon wine"):

| Estratégia | Implementada? | Ganho vs baseline |
|---|---|---|
| **Split por preço** | ✅ v2 (enrich_*_x_preco) | +329 ASINs (2x) |
| Sort=review-rank | ❌ Não ainda | +55 ASINs |
| Sort=date-desc | ❌ Não ainda | +55 ASINs |
| Sort=price-asc | ❌ Não ainda | +52 ASINs |
| Sort=price-desc | ❌ Não ainda | +52 ASINs |
| Rating ≥4★ filter | ❌ Não ainda | +78 ASINs |
| Discovery pages (bestseller/new/movers/wished) | ❌ Não ainda | +49 ASINs |
| Combo price+sort | ❌ Descartado | Menor que split puro |

**Mindset**: todas as que trouxerem >0 vinhos serão implementadas. Ordem segue eficiência. Estudo é contínuo — sempre pensar em novas formas.

---

## 9. Se o scraper cair — como retomar

### 9.1 Diagnóstico rápido
```bash
# 1. Processos vivos?
tasklist | grep python

# 2. Detalhes (PIDs + linha de comando)
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Select-Object ProcessId, CommandLine | Format-Table -AutoSize -Wrap"

# 3. Último heartbeat de cada país
for p in US NL CA DE AU IT JP BR MX; do
  echo "=== $p ==="
  # Procura log v2 primeiro, depois v1
  f="C:/natura-automation/logs/relaunch_20260416/${p}_v2.log"
  [ ! -f "$f" ] && f="C:/natura-automation/logs/relaunch_20260415/${p}.log"
  [ ! -f "$f" ] && f="C:/natura-automation/logs/relaunch_20260415/${p}_v2.log"
  tail -n 3 "$f" 2>/dev/null || echo "sem log"
done

# 4. Banco acessível?
PGPASSWORD=postgres123 "C:/Program Files/PostgreSQL/16/bin/psql.exe" -h localhost -U postgres -d winegod_db -c "\dt" | head -5
```

### 9.2 Contagem atual por país
```bash
PGPASSWORD=postgres123 "C:/Program Files/PostgreSQL/16/bin/psql.exe" -h localhost -U postgres -d winegod_db -t -A -F"|" -c "
SELECT 'AE',COUNT(*) FROM vinhos_ae UNION ALL SELECT 'AU',COUNT(*) FROM vinhos_au
UNION ALL SELECT 'BE',COUNT(*) FROM vinhos_be UNION ALL SELECT 'BR',COUNT(*) FROM vinhos_br
UNION ALL SELECT 'CA',COUNT(*) FROM vinhos_ca UNION ALL SELECT 'DE',COUNT(*) FROM vinhos_de
UNION ALL SELECT 'ES',COUNT(*) FROM vinhos_es UNION ALL SELECT 'FR',COUNT(*) FROM vinhos_fr
UNION ALL SELECT 'GB',COUNT(*) FROM vinhos_gb UNION ALL SELECT 'IE',COUNT(*) FROM vinhos_ie
UNION ALL SELECT 'IT',COUNT(*) FROM vinhos_it UNION ALL SELECT 'JP',COUNT(*) FROM vinhos_jp
UNION ALL SELECT 'MX',COUNT(*) FROM vinhos_mx UNION ALL SELECT 'NL',COUNT(*) FROM vinhos_nl
UNION ALL SELECT 'PL',COUNT(*) FROM vinhos_pl UNION ALL SELECT 'SE',COUNT(*) FROM vinhos_se
UNION ALL SELECT 'SG',COUNT(*) FROM vinhos_sg UNION ALL SELECT 'US',COUNT(*) FROM vinhos_us
ORDER BY 1;"
```

### 9.3 Progresso de tracking (só v2)
```bash
PGPASSWORD=postgres123 "C:/Program Files/PostgreSQL/16/bin/psql.exe" -h localhost -U postgres -d winegod_db -c "
SELECT * FROM progresso_estrategias ORDER BY pais_codigo, template;"
```

### 9.4 Relançar 1 país v2
```bash
cd C:\natura-automation
DIA=$(date +%Y%m%d)
mkdir -p logs/relaunch_$DIA
nohup python -u amazon/orchestrator.py --pais BR --fase A \
  --uvas-max 150 --vinicolas-max 2000 --enrich-split-preco \
  > logs/relaunch_$DIA/BR_v2.log 2>&1 &
```

### 9.5 Relançar todos v2 em lote
```bash
cd C:\natura-automation
DIA=$(date +%Y%m%d)
mkdir -p logs/relaunch_$DIA
for p in US BR DE MX NL CA AU IT JP; do
  nohup python -u amazon/orchestrator.py --pais $p --fase A \
    --uvas-max 150 --vinicolas-max 2000 --enrich-split-preco \
    > logs/relaunch_$DIA/${p}_v2.log 2>&1 &
  sleep 3
done
# NAO rodar FR/PL/AE junto (ultra-tier). Rodar isoladamente.
```

### 9.6 Matar gentilmente um processo (sem /F)
```bash
# Usa PowerShell porque bash no MSYS converte /PID em path
powershell -NoProfile -Command "Stop-Process -Id <PID>"
```

---

## 10. Arquivos de log importantes

| Caminho | Conteúdo |
|---|---|
| `C:\natura-automation\logs\relaunch_20260415\<PAIS>.log` | v1 — Fase A original (15-abr) |
| `C:\natura-automation\logs\relaunch_20260415\US_v2.log` | US v2 — primeiro país com tracking+split |
| `C:\natura-automation\logs\relaunch_20260416\<PAIS>_v2.log` | v2 — NL, CA, DE, AU, IT, JP (16-abr) |
| `C:\natura-automation\logs\filter_research_US_20260415_190140.json` | Resultado do estudo de filtros |
| `C:\natura-automation\logs\filter_research_run.log` | Log da execução do estudo |

Log saudável:
```
[2026-04-16 11:35:48] [US] [1-5000] 0 resultados, pulando
[2026-04-16 02:16:24] [US] [1-5000] pg 5: 10 asins, 6 novos
[2026-04-16 02:16:24] [US] [1-5000] chunk save final: 3 salvos (total na faixa: 3)
```

Se aparecer `Bloqueio: pagina_vazia` várias vezes seguidas = captcha (normal, recupera sozinho em 30-90s). Se aparecer `_object` = bug antigo do Playwright 1.40 (não deveria acontecer em 1.58).

---

## 11. O que NÃO fazer

1. **Não** `git add .` / `git add -A` — listar arquivos explicitamente (Regra 1 do CLAUDE.md).
2. **Não** deletar colunas existentes em `vinhos_<xx>` — só adicionar (Regra 2).
3. **Não** criar scrapers/enrichment neste repo `winegod-app` — é o repo do PRODUTO (Regra 4).
4. **Não** matar processos sem motivo — deixar terminar naturalmente.
5. **Não** subir versão do Playwright sem motivo — 1.58.0 corrigiu bug crítico.
6. **Não** mexer no orchestrator.py com processos v1 rodando — eles já carregaram o arquivo antigo na memória, mas edições podem confundir debugging. Processos v2 carregaram a versão atual.
7. **Não** rodar FR+PL+AE junto com outros (ultra-tier, delay 6s).
8. **Não** eliminar uma estratégia que traz qualquer resultado — filosofia é somar todas.

---

## 12. Checklist de continuidade (para o Claude que assumir)

- [ ] Ler este arquivo inteiro antes de agir.
- [ ] `tasklist | grep python` — confirmar quantos processos estão vivos.
- [ ] Verificar PIDs com PowerShell (seção 9.1) — confirmar quais países v1 vs v2.
- [ ] `tail` nos logs — ver timestamp do último heartbeat (deve ser <5min atrás).
- [ ] Contagem no banco (seção 9.2) — comparar com tabela da seção 4.3.
- [ ] Tracking v2 (seção 9.3) — ver quantas queries ok/erro/rodando por país.
- [ ] Se BR ou MX terminaram v1 → relançar em v2 (seção 9.4).
- [ ] Se algum país parou de escrever log por >10min mas Python ainda vivo → provavelmente captcha. Considerar kill e relançar.
- [ ] **Perguntar ao usuário antes de qualquer commit, qualquer kill, qualquer relançamento em lote.**

---

## 13. v3 — Mudanças implementadas (2026-04-17)

### 13.1 Problema detectado em v2

Análise dos logs de US v2 revelou perda massiva:
- **154 queries na "zona morta"** (400-700 declarados, sem split — threshold era 700)
- **141 sub-faixas saturadas** (range ≤$5 com >400 declarados — SPLIT_FLOOR era 5)
- **Perda estimada em US: ~50.000-200.000 vinhos** (Amazon inflaciona, real ~30-50%)
- Mesmo padrão em CA (200 sub-faixas), NL (534), AU (73)
- DE/IT/JP sem perda (moedas EUR/JPY distribuem melhor)

### 13.2 Três correções aplicadas

| Camada | Antes (v2) | Depois (v3) | Efeito |
|---|---|---|---|
| Threshold de split | 700 | **400** | Elimina zona morta |
| SPLIT_FLOOR | 5 | **1** | Divide até $1 de granularidade |
| Sort rotation | não existia | **4 sorts em faixas saturadas** | Quando range ≤ SPLIT_FLOOR e declarados >400, roda mesma faixa 4x com sorts diferentes (default, price-asc, review-rank, date-desc) |

### 13.3 Resultado medido (primeiras 5h de v3)

- **NL**: 44.712 → 55.340 (+10.628)
- **CA**: 33.393 → 39.893 (+6.500)
- **Taxa de novidade em sort rotation: 57%** (mais da metade dos ASINs são novos)
- **Cobertura estimada: ~75-85%** do catálogo (era ~40-60% em v2)

### 13.4 Processos relançados em v3

| País | Relançou v3? | Log |
|---|---|---|
| US | ✅ | `relaunch_20260417/US_v3.log` |
| CA | ✅ | `relaunch_20260417/CA_v3.log` |
| NL | ✅ | `relaunch_20260417/NL_v3.log` |
| AU | ✅ | `relaunch_20260417/AU_v3.log` |
| BR | ✅ | `relaunch_20260417/BR_v3.log` |
| DE | ❌ (0 perda em v2) | — |
| IT | ��� (0 perda em v2, v2 rodando) | — |
| JP | ❌ (0 perda em v2) | — |
| MX | v1 terminando, relançar v3 | — |

### 13.5 Código alterado

- `C:\natura-automation\amazon\orchestrator.py`:
  - `SPLIT_FLOOR = 1` (era 5)
  - `scrape_faixa_adaptativa()`: threshold 400 (era 700), sort rotation quando faixa ≤ SPLIT_FLOOR e >400 declarados
  - `paginar_faixa()`: aceita parâmetro `sort=` para sort rotation

---

## 14. v4 — PLANO PARA COBRIR OS ~15-25% RESTANTES (NÃO executar sem aprovação)

### 14.1 Problema residual

Mesmo com v3 (split $1 + sort rotation 4x), faixas de $1 densas (ex: $9-$10 em CA) ainda declaram 1.001+ resultados. 4 sorts × ~400 = ~1.600 máximo. Se o catálogo real for maior, vinhos escapam.

### 14.2 Variáveis adicionais para segmentação (a implementar em v4)

| Variável | Parâmetro Amazon | Como segmentar | Impacto estimado |
|---|---|---|---|
| **Tipo de vinho** | `p_n_feature_browse-bin:XXX` | Red / White / Rosé / Sparkling / Dessert / Fortified (6 splits) | Alto — cada tipo tem catálogo próprio |
| **Rating** | `p_72:XXXX` | 4+★, 3+★, 2+★, 1+★, sem rating (5 variações) | Médio — Amazon reordena resultados por rating |
| **Marca/brand** | `p_89:NOME` | Top 50-100 brands extraídas da sidebar da Amazon | Alto — vinícolas populares concentram volume |
| **Tamanho garrafa** | `p_n_size_browse-vebin:XXX` | 375ml / 750ml / 1.5L / 3L / box | Baixo-médio — separa formatos |
| **Prime** | `p_85:2470955011` | Prime vs não-Prime (2 splits) | Médio — divide catálogo ~50/50 |
| **Vendedor** | `p_6:ATVPDKIKX0DER` | Amazon vs third-party (2 splits) | Médio — catálogos diferentes |
| **Safra/vintage** | via keyword | Adicionar "2020", "2021", "2022" na query | Baixo — poucos vinhos marcam safra no título |
| **País de origem** | via keyword | Adicionar "france wine", "italy wine" dentro de faixa de preço | Médio — cross-referencia com regiões |
| **Desconto** | `p_n_pct-off-with-tax:25-` | 10%+, 25%+, 50%+ off | Baixo — subset dos mesmos vinhos |
| **Subscribe & Save** | `p_n_subscribe_with_discount:1` | S&S vs não-S&S | Baixo — poucos vinhos em S&S |

### 14.3 Estratégia de implementação v4

**Prioridade 1 — Tipo de vinho (maior impacto)**:
- Descobrir IDs de `p_n_feature_browse-bin` por marketplace (navegar na sidebar, extrair)
- Quando faixa $1 + sort rotation ainda satura: subdividir por tipo (6 tipos × 4 sorts × ~400 = ~9.600 máximo)
- Cobertura estimada: 90-95%

**Prioridade 2 — Brand split**:
- Extrair top 50 brands da sidebar de cada marketplace
- Para queries genéricas saturadas: `&rh=p_89:CaymuS` etc
- Pega vinhos de produtores que se perdem no meio de queries genéricas

**Prioridade 3 — Prime + Vendedor**:
- Split binário (2x): Prime/não-Prime ou Amazon/third-party
- Baixo custo (2 queries extras), dobra cobertura em faixas densas

**Prioridade 4 — Rating**:
- 4+★ vs sem filtro já testado no filter_research (ganho: +78 ASINs)
- Pode empilhar com tipo + preço

### 14.4 Abordagem

Mesma filosofia: testar empiricamente com `filter_research.py` antes de implementar. Cada variável nova = novo estudo medindo ASINs únicos vs baseline. Só implementa se trouxer >0 vinhos. Ordem segue ROI medido.

### 14.5 Nota sobre IDs de filtro

Os IDs de `p_n_feature_browse-bin`, `p_72`, `p_85` etc **variam por marketplace**. US tem um ID para "Red Wine", DE tem outro. O software autônomo precisa:
1. Navegar na página de busca de cada marketplace
2. Extrair IDs da sidebar/filtros (seletores: `#s-refinements a`, `[data-component-type="s-refinements"] a`)
3. Mapear: marketplace → filtro → ID
4. Armazenar no banco (tabela nova: `amazon_filtros_marketplace`)

Isso precisa ser feito **uma vez por marketplace** (IDs são estáveis).

---

## 15. Próximos passos operacionais (NÃO executar sem aprovação)

1. **Monitorar v3** — US, CA, NL, AU, BR em andamento. Medir ganho vs v2.
2. **MX**: quando terminar v1, relançar em v3.
3. **Países não rodando**: FR, PL, AE (ultra-tier — rodar isolados), GB (sensitive), SE, ES, IE, SG, BE.
4. **Ondas de vinícolas** — subir de 2.000 para 5.000, depois 10.000. Depende do ROI medido.
5. **v4** — implementar variáveis adicionais (seção 14) quando v3 estabilizar.
6. **App autônomo** — todo o tracking/CLI/view/formato validado é base para software independente. Doc: `FORMATO_VALIDADO_SCRAPER_AMAZON_V3.md`.

---

## 16. Referências cruzadas

- `C:\winegod-app\CLAUDE.md` — regras do repo do produto (Regras R1-R13 + REGRAS 0-4 pro Claude).
- `C:\winegod-app\prompts\HANDOFF_SCRAPER_AMAZON_SESSAO_2.md` — handoff da sessão anterior (evolução histórica: como chegamos em 64.688 → 245K).
- `C:\winegod-app\prompts\PLANO_SCRAPER_AMAZON_SISTEMA_AUTONOMO.md` — plano de evolução (observabilidade, supervisor, API). **Não executar sem aprovação explícita do usuário.**
- `C:\Users\User\.claude\projects\C--winegod-app\memory\` — memórias persistentes (rollout plan, strategy mindset, autonomous app goal).
