# HANDOFF — Amazon Scraper: como funciona (PC principal → PC espelho)

> **Para o Claude do PC espelho**: este documento descreve EXATAMENTE como o scraper Amazon do WineGod funciona no PC principal do Murilo, em 2026-04-10. Foi escrito porque você (Claude no espelho) procurou e achou só o modelo antigo de ScrapingDog. Esse modelo está **DESATIVADO**. O scraper real e ativo é outro, em outro repositório, com Playwright. Leia tudo antes de mexer.

---

## TL;DR

- O scraper Amazon do WineGod **NÃO está no repo `winegod-app`**. Está no repo `natura-automation`, em `C:\natura-automation\amazon\`.
- Existem **dois modelos** no histórico:
  - `amazon_scraper` → ScrapingDog API (`amazon/query_executor.py`) — **DESATIVADO**. O próprio arquivo diz isso na linha 2: `"O sistema Amazon agora usa amazon/orchestrator.py com Playwright."`
  - `amazon_playwright` → Playwright + Chromium headless (`amazon/orchestrator.py`) — **ATIVO**. É este que está rodando hoje.
- O dashboard do PC principal roda em `http://localhost:5568/` (PID variável, processo `python C:\natura-automation\winegod_codex\server.py`).
- O dashboard tem 2 abas: **Geral** (Tier 1/2/3 das lojas normais) e **Amazon**.
- O scraper Amazon é disparado por `POST /api/run/amazon` ou `POST /api/run/amazon/<CODE>` (ex: `/api/run/amazon/BR`).
- Estado em 2026-04-10: **50.558 vinhos** Amazon em **18 marketplaces** (29.308 via Playwright + 21.250 legados via ScrapingDog).

---

## 1. Onde estão os arquivos (CAMINHOS COMPLETOS)

> **IMPORTANTE — PC ESPELHO**: se você não tem `C:\natura-automation\` no PC espelho, o sync (Syncthing ou o que for) não trouxe a pasta. **Pede pro Murilo sincronizar a pasta `C:\natura-automation\` inteira antes de continuar.** Sem ela você não tem o scraper.

### Repositório separado: `C:\natura-automation\`

```
C:\natura-automation\
├── amazon\                       <- O SCRAPER AMAZON (este é o foco)
│   ├── __init__.py               (vazio)
│   ├── orchestrator.py           (711 linhas) — PIPELINE PRINCIPAL ATIVA
│   ├── config.py                 (347 linhas) — marketplaces, queries, uvas, regiões, produtores
│   ├── utils_playwright.py       (414 linhas) — browser, anti-bloqueio, parsing de preço
│   ├── db_amazon.py              (376 linhas) — schema PostgreSQL (amazon_queries, amazon_categorias, amazon_reviews)
│   ├── category_discovery.py     (191 linhas) — descobre node_ids de categorias de vinho
│   ├── query_executor.py         (312 linhas) — DESATIVADO (era o ScrapingDog antigo)
│   ├── query_generator.py        (194 linhas) — gera ~25K queries texto (modelo antigo)
│   └── main.py                   (220 linhas) — entry point antigo (modelo ScrapingDog)
│
├── winegod_codex\                <- DASHBOARD + serviços compartilhados
│   ├── server.py                 — Flask, porta 5568
│   ├── db_scraping.py            — upsert_vinhos_batch, criar_tabelas_vinhos (USADO PELO ORCHESTRATOR)
│   ├── utils_scraping.py         — eh_vinho, normalizar_texto, inferir_pais, gerar_hash_dedup, etc.
│   ├── scraper_tier1.py
│   ├── tier2_service.py
│   ├── classifier.py
│   ├── cache\
│   ├── run_logs\
│   └── templates\
│
├── _amazon_run.log               (logs de execução amazon)
├── _amazon_run_jp.log
├── _amazon_run_usjp.log
├── _codex_amazon_scraper.py
└── (vários _aba*.json e _prompt_amazon_playwright_*.md de handoffs anteriores)
```

### Repo `C:\winegod\` (referenciado pelo orchestrator)

`amazon/orchestrator.py:69` faz `sys.path.insert(0, "C:\\winegod")` e importa `is_wine` e `normalize_wine_name` de `utils.py`. Se `C:\winegod\` não existir no espelho, ele cai no fallback local (linhas 71-74) e segue funcionando — mas com filtragem menos boa.

### Banco de dados

PostgreSQL local. Variável de ambiente lida em `amazon/db_amazon.py:16`:

```python
DATABASE_URL = (
    os.environ.get("WINEGOD_CODEX_DATABASE_URL")
    or os.environ.get("WINEGOD_DATABASE_URL")
    or "postgresql://postgres:postgres123@localhost:5432/winegod_db"
)
```

> **Atenção**: o banco do scraper é `winegod_db` LOCAL, **não** é o `winegod` do Render que está em `C:\winegod-app\CLAUDE.md`. São dois bancos diferentes. O Render é o do produto/chat, o local é o do pipeline de coleta.

---

## 2. Por que o modelo antigo (ScrapingDog) confunde

`amazon/query_executor.py` linha 1-6 diz textualmente:

```python
"""
Amazon Wine Scraper — Executor de queries (DESATIVADO).
O sistema Amazon agora usa amazon/orchestrator.py com Playwright.
As funcoes de parsing (_parse_rating, _parse_reviews, etc.) sao mantidas
pois o novo crawler as importa.
"""
```

E no `config.py:9-10` ainda existe:

```python
SCRAPINGDOG_API_KEY_ENV = "SCRAPINGDOG_API_KEY"
SCRAPINGDOG_DEFAULT_KEY = "69d30c37c9f188ef33b70e95"
```

> **TODO de segurança**: essa chave está hardcoded em texto puro no repositório. Tem que sair pro `.env` o quanto antes. Não foi feito ainda — fica como tarefa pendente.

O orchestrator novo (`orchestrator.py`) **não importa** SCRAPINGDOG_DEFAULT_KEY. Ele só usa `MARKETPLACES` do config. Os vinhos legados na tabela `vinhos_<pais>_fontes` com `fonte = 'amazon_scraper'` foram coletados pelo modelo antigo e ainda existem no banco — não foram migrados, ficam lá conviventes.

**Resumo de fontes no banco:**

| `fonte`             | Origem                                  | Status                          |
|---------------------|-----------------------------------------|---------------------------------|
| `amazon_scraper`    | `query_executor.py` via ScrapingDog API | LEGADO. Não roda mais.          |
| `amazon_playwright` | `orchestrator.py` via Playwright local  | **ATIVO**. Constante `FONTE` na linha 77 do orchestrator. |

Estado atual em 2026-04-10 (do `GET /api/amazon/status`):

| País | Total | Playwright | Antigo |
|------|------:|-----------:|-------:|
| JP   | 16.034 |     1.636 | 14.398 |
| BR   | 11.136 |     5.467 |  5.669 |
| DE   |  6.925 |     6.885 |     40 |
| NL   |  3.986 |     3.986 |      0 |
| US   |  3.562 |     3.233 |    329 |
| IE   |  2.633 |     2.321 |    312 |
| MX   |  1.775 |     1.775 |      0 |
| GB   |    901 |       901 |      0 |
| AU   |    550 |       160 |    390 |
| FR   |    437 |       437 |      0 |
| IT   |    501 |       501 |      0 |
| BE   |    403 |       384 |     19 |
| PL   |    465 |       465 |      0 |
| SE   |    394 |       394 |      0 |
| CA   |    206 |       206 |      0 |
| ES   |    203 |       203 |      0 |
| SG   |    201 |       201 |      0 |
| AE   |    246 |       153 |     93 |
| **TOTAL** | **50.558** | **29.308** | **21.250** |

JP é o caso mais óbvio onde a migração para Playwright ainda não terminou (só 10% migrado). O resto está majoritariamente Playwright.

---

## 3. O dashboard (`localhost:5568`)

### Como subir

```cmd
python C:\natura-automation\winegod_codex\server.py
```

(O Murilo deixa rodando manualmente. Não tem auto-start.)

### Como verificar se está rodando

```bash
curl -s http://localhost:5568/api/amazon/status
```

Se voltar JSON com `totals`, `por_pais`, `campos_por_pais`, `vinhos_por_fonte` — está OK.

### Endpoints relevantes (Amazon)

| Método | URL | O que faz |
|--------|-----|-----------|
| `GET`  | `/`                          | Dashboard HTML (aba Geral + aba Amazon) |
| `GET`  | `/api/status`                | Status geral (Tier 1/2/3) |
| `GET`  | `/api/amazon/status`         | Status só Amazon (totals, por país, campos preenchidos, fontes) |
| `POST` | `/api/run/amazon`            | Roda o orchestrator pra TODOS os países |
| `POST` | `/api/run/amazon/<CODE>`     | Roda só pra um país (ex: `BR`) |
| `POST` | `/api/run/amazon-generate`   | Gera queries (modelo antigo, raramente usado) |
| `GET`  | `/api/amazon/categorias`     | Lista de `amazon_categorias` (com `?pais=BR` opcional) |
| `GET`  | `/api/amazon/reviews/<asin>` | Reviews de um ASIN específico |
| `GET`  | `/api/amazon/checkpoint`     | Checkpoints de paginação por categoria |
| `POST` | `/api/stop/amazon`           | Mata o processo Amazon ativo |

O dispatcher do botão "Rodar Todos os Paises" no dashboard cai em `server.py:999-1015`:

```python
SCRIPT_AMAZON = os.path.join(ROOT, "amazon", "orchestrator.py")

@app.route("/api/run/amazon", methods=["POST"])
@app.route("/api/run/amazon/<code>", methods=["POST"])
def api_run_amazon(code=None):
    cmd_args = []
    if code:
        cmd_args = ["--pais", code.upper()]
    args = [PYTHON_EXE, "-u", SCRIPT_AMAZON] + cmd_args
    key = f"amazon:{(code or 'ALL').upper()}"
    label = f"Amazon {(code or 'ALL').upper()}"
    if has_active("amazon"):
        return jsonify({"ok": False, "msg": "Ja existe processo Amazon ativo"})
    start_proc(key, label, args)
    return jsonify({"ok": True, "msg": f"Iniciando Amazon {(code or 'ALL').upper()}..."})
```

Note que o subprocess é lançado pelo Python do dashboard com `-u` (unbuffered) pra os logs aparecerem em tempo real.

---

## 4. Arquitetura do scraper (3 fases)

`orchestrator.py:673-694` é o `run_pipeline`:

```python
def run_pipeline(paises=None, fases=None):
    inicio = time.time()
    criar_tabelas()
    if not gate_0(): return  # gate de sanidade
    rate_limiter = AdaptiveDelay()
    paises_lista = paises or ORDEM_PAISES   # 18 países
    fases_lista = fases or ["A", "B", "C"]
    with sync_playwright() as pw:
        if "A" in fases_lista:
            for pais in paises_lista:
                fase_a_pais(pw, pais, rate_limiter)
        if "B" in fases_lista:
            for pais in paises_lista:
                fase_b_pais(pw, pais, rate_limiter)
        if "C" in fases_lista:
            for pais in [p for p in paises_lista if p in PAISES_FASE_C]:
                fase_c_pais(pw, pais, rate_limiter)
```

Argumentos CLI (`main()`, linhas 697-707):

```bash
python amazon/orchestrator.py                       # tudo: 3 fases x 18 países
python amazon/orchestrator.py --pais BR             # só BR, todas fases
python amazon/orchestrator.py --pais BR US DE       # múltiplos países
python amazon/orchestrator.py --fase A              # só Fase A
python amazon/orchestrator.py --pais BR --fase A    # combinado
```

### Fase A — Catálogo (a "garimpo")

`fase_a_pais()`, linhas 412-465.

**Estratégia**: pesquisa pela palavra "wine" no idioma local + split adaptativo por faixa de preço, porque a Amazon corta toda busca em ~700 produtos visíveis.

Keyword por idioma (`WINE_KEYWORD`, linha 87):

```python
WINE_KEYWORD = {
    "en": "wine", "pt": "vinho", "es": "vino", "fr": "vin",
    "de": "wein", "it": "vino", "nl": "wijn", "pl": "wino",
    "sv": "vin", "ja": "wine", "ar": "wine",
}
```

Tetos de preço por moeda (linha 94):

```python
PRECO_TETO = {
    "BRL": 6000, "USD": 1000, "EUR": 1000, "GBP": 800,
    "JPY": 150000, "CAD": 1400, "AUD": 1600, "MXN": 20000,
    "PLN": 4000, "SEK": 11000, "SGD": 1400, "AED": 4000,
}
```

#### O coração: split adaptativo por preço

`scrape_faixa_adaptativa()`, linhas 317-406. Pseudo-código:

```
def scrape_faixa(lo, hi):
    ir até /s?k=wine&low-price={lo}&high-price={hi}
    ler "X resultados" do topo da página (ler_total_resultados)
    se total <= 700:
        paginar tudo até a próxima página sumir (paginar_faixa)
        salvar
    senão:
        se hi - lo <= 10:
            paginar o que der (faixa estreita)
        senão:
            mid = (lo + hi) // 2
            scrape_faixa(lo, mid)    ← recursão
            scrape_faixa(mid, hi)    ← recursão
```

A leitura de "X resultados" está em `ler_total_resultados()` (linhas 116-129):

```python
def ler_total_resultados(page):
    el = page.query_selector(".a-section span[dir=auto], .s-desktop-toolbar .a-spacing-small span")
    if not el: return None
    txt = el.inner_text().strip()
    is_over = "mais" in txt.lower() or "over" in txt.lower() or "+" in txt
    m = re.search(r"([\d.,]+)\+?\s*(?:resultado|result)", txt, re.I)
    if not m: return None
    num = int(re.sub(r"[^\d]", "", m.group(1)))
    if is_over:
        return num + 1  # "mais de 4.000" -> 4001 (acima do limite)
    return num
```

Depois do split adaptativo, `fase_a_pais` ainda faz um **catch-all** sem filtro de preço (linhas 441-456) pra pegar produtos que não tinham preço listado e por isso ficaram fora dos filtros.

#### Paginação

`paginar_faixa()`, linhas 262-311. Itera `&page=1`, `&page=2`, ... até `s-pagination-next.s-pagination-disabled` aparecer ou a página vir vazia. Detectado por `fim_de_paginacao()` em `utils_playwright.py:210`.

Restart do browser a cada 500 páginas (`BROWSER_RESTART_PAGES = 500`, linha 78) pra liberar memória, com `gc.collect()`.

#### Extração da página de resultados (`extrair_items_pagina`, linhas 213-256)

Para cada `[data-asin]` na SERP da Amazon:

```python
for el in page.query_selector_all("[data-asin]"):
    asin = el.get_attribute("data-asin") or ""
    if len(asin) != 10: continue                            # ASIN sempre 10 chars
    title_el = el.query_selector("h2 a span, h2 span")
    if not title_el: continue
    title = title_el.inner_text().strip()
    if len(title) < 8: continue

    price_el = el.query_selector(".a-price .a-offscreen")   # preço atual
    price_float = parsear_preco(...)
    old_el = el.query_selector(".a-price[data-a-strike] .a-offscreen, .a-text-price .a-offscreen")  # preço riscado
    rating_el = el.query_selector(".a-icon-alt")            # "4,5 de 5 estrelas"
    stars = parse_rating(...)

    # nº de reviews: busca pelo "(123)" no parent .a-row do rating
    row_text = rating_el.evaluate("el => (el.closest('.a-row') || {}).textContent || ''")
    m = re.search(r"\(([\d.,]+)\)", row_text)
    reviews_int = int(re.sub(r"[^\d]", "", m.group(1))) if m else None

    img_el = el.query_selector("img.s-image")
    is_prime = bool(el.query_selector("[aria-label*='Prime']"))
    is_sponsored = bool(el.query_selector("[data-component-type*=sp-], .s-label-popover-default"))
    is_best_seller = "best seller" in all_text.lower() or "mais vendido" in all_text.lower()
    is_amazon_choice = "amazon" in all_text.lower() and "choice" in all_text.lower()
```

Cada produto passa por `validar_produto()` (`utils_playwright.py:354`) que faz validação de tamanho de título, presença de ASIN e sanity-check de preço por moeda (`PRECO_LIMITES`).

#### Conversão produto → vinho (`item_to_vinho`, linhas 135-207)

Filtros antes de aceitar:

1. `eh_acessorio(nome)` — blacklist em `utils_playwright.py:322` (saca-rolha, decanter, taça, vinagre, suco de uva, "wine bag", etc.)
2. `eh_vinho(nome, None, None)` — vem de `winegod_codex.utils_scraping`
3. `is_wine(nome)` — vem de `C:\winegod\utils.py` (com fallback `lambda: True` se não existir)

Inferências:
- `safra` via `extrair_safra(nome)`
- `tipo` (red/white/rose/sparkling/etc.) via `inferir_tipo_vinho(nome)`
- `pais_inf` via `inferir_pais(nome)` (procura região/produtor no nome) — se não conseguir, usa o país do marketplace
- `produtor` via `extrair_produtor_titulo(nome)` — heurística que pega as palavras antes do primeiro marcador (uva/tipo/safra/volume) — `utils_playwright.py:258`
- `is_natural` via `detectar_natural()` (palavras "organic", "biodynamic", "vinho natural", "sin sulfitos", etc.)
- `is_bundle, bundle_qty` via `detectar_bundle()` (regex `(\d+)\s*x\s*(\d+)\s*ml`, `\d+ garrafas`, "kit/pack/caixa de \d+", etc.)
- `volume_ml`: regex no nome, fallback 750ml
- `preco_por_litro`: se bundle, divide preço por bundle_qty primeiro
- `uva_detectada`: matching contra `_UVAS_CONHECIDAS` (importado de `query_executor.py:41` ou fallback local)
- `hash_dedup` via `gerar_hash_dedup(nome, produtor, safra)`

Salva via `upsert_vinhos_batch(vinhos, FONTE='amazon_playwright', pais)` em lotes de tamanho `LOTE_UPSERT`.

### Fase B — Detalhes da página individual

`fase_b_pais()`, linhas 471-565.

Pega vinhos do banco (`vinhos_<pais>` JOIN `<pais>_fontes`) onde `fonte IN ('amazon_scraper', 'amazon_playwright')`, prioriza os sem `vinicola_nome` ou sem `rating_medio`, e visita `https://www.amazon.<domain>/dp/<asin>` pra cada um.

Extrações da página de produto (linhas 519-541):

| Campo no banco        | Seletor / fonte                                                                |
|-----------------------|--------------------------------------------------------------------------------|
| `vinicola_nome`       | `#bylineInfo` (limpa "Visite a loja", "Brand:", "Marca:")                      |
| `descricao`           | `#feature-bullets li span` (concatenado, max 2000 chars)                       |
| `teor_alcoolico`      | regex `(\d+[.,]?\d*)\s*%` em linhas com "alcohol/alcool/teor/alkohol"          |
| `regiao_nome`         | linhas com "origin/origem/herkunft/origine"                                    |
| `ean_gtin`            | regex `(\d{8,14})` em linhas com "ean/gtin/barcode"                            |
| `dados_extras.category` | `#wayfinding-breadcrumbs a` (joined com " > ")                              |
| `dados_extras.merchant` | `#merchant-info`                                                            |

Update no banco com `COALESCE(%s, {tbl}.{key})` pra não sobrescrever valor existente, e `dados_extras` é mesclado com `||` jsonb.

### Fase C — Reviews

`fase_c_pais()`, linhas 571-646. Roda APENAS em `PAISES_FASE_C = ["BR","US","DE","FR","IT","GB"]` (linha 84).

Pega vinhos com `total_ratings >= 10` que ainda não têm reviews salvos em `amazon_reviews`. Visita `https://www.amazon.<domain>/product-reviews/<asin>/?pageNumber={1..5}` (max 5 páginas por produto) e extrai cada `[data-hook="review"]`:

| Campo                  | Seletor                                                |
|------------------------|--------------------------------------------------------|
| `review_id`            | `id` attribute                                         |
| `autor`                | `.a-profile-name`                                      |
| `rating` (1-5)         | `i.review-rating .a-icon-alt`                          |
| `titulo`               | `[data-hook=review-title] span`                        |
| `texto`                | `[data-hook=review-body] span`                         |
| `compra_verificada`    | qualquer `<span>` com "verifi"                         |
| `votos_util`           | `[data-hook=helpful-vote-statement]` (regex `(\d+)`)   |

Insert em `amazon_reviews` com `ON CONFLICT DO NOTHING`. Para se a página tiver < 8 reviews (sinal de fim).

> **Estado em 2026-04-10**: Fase C nunca rodou. `total_reviews: 0` em todos os países.

---

## 5. Anti-bloqueio (`utils_playwright.py`)

### Browser

```python
def criar_browser(playwright_instance):
    return playwright_instance.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
```

Headless Chromium com flag de stealth. Sem proxy.

### Contexto

User-Agent + viewport aleatórios por contexto (constantes `USER_AGENTS` e `VIEWPORTS` no topo do arquivo). Locale do país.

### Stealth plugin

```python
def criar_pagina(ctx):
    page = ctx.new_page()
    try:
        from playwright_stealth import Stealth
        Stealth().apply_stealth_sync(page)
    except Exception:
        logger.warning("playwright-stealth nao disponivel, continuando sem stealth")
    return page
```

> **Dependência**: precisa do pacote `playwright-stealth` instalado. Se não tiver, ele warna mas continua. **No PC espelho, instale**: `pip install playwright-stealth`.

### Cookies (GDPR)

```python
COOKIE_ACCEPT_SELECTORS = [
    "#sp-cc-accept",
    'input[name="accept"]',
    '[data-action-type="DISMISS"]',
    "#consent-page .a-button-inner button",
]
```

`aceitar_cookies()` clica no primeiro que encontrar.

### Detecção de bloqueio

`pagina_bloqueada()` retorna o tipo de bloqueio ou None:

```python
def pagina_bloqueada(page):
    content = page.content()
    url = page.url
    if "captcha" in content.lower() or "/errors/validateCaptcha" in url:
        return "captcha"
    if len(content) < 5000:
        return "pagina_vazia"
    if "/ap/signin" in url:
        return "redirect_login"
    if "Service Unavailable" in content:
        return "503"
    if "Sorry, we just need to make sure" in content:
        return "dog_page"
    return None
```

### Recuperação

`lidar_com_bloqueio()`, max 3 tentativas:

| Tipo            | Recovery                                               |
|-----------------|--------------------------------------------------------|
| `captcha`       | sleep 60-90s + recria contexto (novo UA/viewport)      |
| `503` / `dog_page` / `pagina_vazia` | sleep linear 30s × tentativa             |
| `redirect_login`| fecha browser inteiro, sleep 10s, recria browser+contexto+page |

### Rate limiting adaptativo (`AdaptiveDelay`)

`utils_playwright.py:180-204`:

```python
class AdaptiveDelay:
    def __init__(self):
        self.delay_base = 0.3   # começa em 0.3s entre páginas
        self.delay_min = 0.2
        self.delay_max = 10.0
        self.paginas_limpas = 0

    def esperar(self):
        delay = self.delay_base + random.uniform(0, 0.3)
        time.sleep(delay)

    def sucesso(self):
        self.paginas_limpas += 1
        if self.paginas_limpas > 20 and self.delay_base > self.delay_min:
            self.delay_base = max(self.delay_min, self.delay_base * 0.9)  # acelera 10%

    def bloqueio(self):
        self.paginas_limpas = 0
        self.delay_base = min(self.delay_max, self.delay_base * 2.0)  # dobra

    def novo_pais(self):
        self.delay_base = 0.5
        self.paginas_limpas = 0
```

A cada bloqueio dobra o delay. A cada 20 páginas limpas acelera 10%. Reset a cada novo país.

---

## 6. Parsing de preço (locale-aware)

`parsear_preco()` em `utils_playwright.py:227-252`. Importante porque cada país tem formato diferente:

```python
MOEDAS_SEM_CENTAVOS = {"JPY"}

def parsear_preco(preco_texto, pais_codigo, moeda):
    limpo = re.sub(r"[^\d.,]", "", str(preco_texto).strip())

    if moeda in MOEDAS_SEM_CENTAVOS:
        return float(re.sub(r"[^\d]", "", limpo))   # JPY: só dígitos

    decimal_tipo = MARKETPLACES.get(pais_codigo, {}).get("decimal", "ponto")

    if decimal_tipo == "virgula":   # EUR/BRL: 1.234,56
        if "," in limpo:
            limpo = limpo.replace(".", "").replace(",", ".")
        else:
            partes = limpo.split(".")
            if len(partes) == 2 and len(partes[1]) == 3:
                limpo = limpo.replace(".", "")  # "1.000" -> "1000" (separador de milhar)
    else:  # USD/GBP/JPY: 1,234.56
        limpo = limpo.replace(",", "")

    return float(limpo)
```

Configuração em `MARKETPLACES` (`config.py:15`):

| País | domain   | lang | moeda | decimal  |
|------|----------|------|-------|----------|
| US   | com      | en   | USD   | ponto    |
| BR   | com.br   | pt   | BRL   | virgula  |
| MX   | com.mx   | es   | MXN   | virgula  |
| CA   | ca       | en   | CAD   | ponto    |
| DE   | de       | de   | EUR   | virgula  |
| FR   | fr       | fr   | EUR   | virgula  |
| IT   | it       | it   | EUR   | virgula  |
| ES   | es       | es   | EUR   | virgula  |
| GB   | co.uk    | en   | GBP   | ponto    |
| NL   | nl       | nl   | EUR   | virgula  |
| PL   | pl       | pl   | PLN   | virgula  |
| SE   | se       | sv   | SEK   | virgula  |
| BE   | com.be   | fr   | EUR   | virgula  |
| IE   | ie       | en   | EUR   | ponto    |
| AU   | com.au   | en   | AUD   | ponto    |
| JP   | co.jp    | ja   | JPY   | ponto    |
| SG   | sg       | en   | SGD   | ponto    |
| AE   | ae       | en   | AED   | ponto    |

**Não inclui SA (Arábia Saudita), IN (Índia) e TR (Turquia)**: removidos por restrições de venda de álcool.

> **Bug provável** (em 2026-04-10): qualidade de extração de DE mostra **99% de produtor mas só 5% de preço**. Investigar `parsear_preco` no caminho alemão. Pode ser um padrão `1.234,56 €` que algum branch trata mal.

---

## 7. Validação e sanity check (`gate_0`)

`orchestrator.py:652-667`. Roda antes de qualquer scraping pra garantir que as funções básicas funcionam:

```python
def gate_0():
    erros = []
    # Parsing de preço com 4 formatos
    for txt, p, m, exp in [
        ("R$ 1.000,50","BR","BRL",1000.5),
        ("12,99","DE","EUR",12.99),
        ("$1,234.56","US","USD",1234.56),
        ("3500","JP","JPY",3500.0),
    ]:
        r = parsear_preco(txt, p, m)
        if r is None or abs(r - exp) > 0.01:
            erros.append(f"PRECO: ({txt})={r}")

    # Detecção de bundle
    for nome, eb, eq in [("Kit 6 garrafas",True,6),("Merlot 750ml",False,1)]:
        ib, q, _ = detectar_bundle(nome)
        if ib != eb or q != eq:
            erros.append(f"BUNDLE: {nome}")

    # Blacklist
    if eh_acessorio("Cabernet Sauvignon"): erros.append("BLACKLIST falso+")
    if not eh_acessorio("Saca-rolha"): erros.append("BLACKLIST falso-")

    # Extração de produtor
    if not extrair_produtor_titulo("Casillero del Diablo Cabernet Sauvignon 2022"):
        erros.append("PRODUTOR")

    if erros:
        for e in erros: logger.error(f"GATE 0: {e}")
        return False
    return True
```

Se `gate_0()` falhar, o pipeline aborta antes de gastar 1 request.

---

## 8. Schema do banco (essencial)

`amazon/db_amazon.py`. Três tabelas próprias do Amazon (criadas por `criar_tabelas()`):

### `amazon_queries` (legado, do modelo ScrapingDog)

```sql
CREATE TABLE IF NOT EXISTS amazon_queries (
    id SERIAL PRIMARY KEY,
    pais_codigo VARCHAR(5) NOT NULL,
    template VARCHAR(30) NOT NULL,
    query_text TEXT NOT NULL,
    parametros JSONB,
    fase VARCHAR(1) DEFAULT 'A',
    status VARCHAR(30) DEFAULT 'pendente',
    paginas_buscadas INTEGER DEFAULT 0,
    itens_encontrados INTEGER DEFAULT 0,
    vinhos_novos INTEGER DEFAULT 0,
    vinhos_duplicados INTEGER DEFAULT 0,
    creditos_usados INTEGER DEFAULT 0,
    tempo_s REAL,
    erro TEXT,
    criado_em TIMESTAMP DEFAULT NOW(),
    executado_em TIMESTAMP,
    ultima_pagina INTEGER DEFAULT 0,
    node_id TEXT,
    tipo_query VARCHAR(20) DEFAULT 'texto',
    UNIQUE(pais_codigo, template, query_text)
);
```

> O dashboard ainda lê dela em `server.py:668` pra cards de "creditos" (legado de quando ScrapingDog cobrava).

### `amazon_categorias` (novo, usado pelo orchestrator)

```sql
CREATE TABLE IF NOT EXISTS amazon_categorias (
    id SERIAL PRIMARY KEY,
    pais_codigo VARCHAR(5) NOT NULL,
    node_id TEXT NOT NULL,
    nome TEXT,
    nome_pai TEXT,
    total_declarado INTEGER,
    total_extraido INTEGER DEFAULT 0,
    ultima_pagina_processada INTEGER DEFAULT 0,
    paginas_descobertas INTEGER,
    status TEXT DEFAULT 'pendente',
    ultimo_scraping TIMESTAMP,
    UNIQUE(pais_codigo, node_id)
);
```

Usada pra checkpoint de paginação por categoria. Funções `salvar_checkpoint()` / `obter_checkpoint()` em `utils_playwright.py:377-397`.

### `amazon_reviews` (Fase C)

```sql
CREATE TABLE IF NOT EXISTS amazon_reviews (
    id SERIAL PRIMARY KEY,
    asin VARCHAR(10) NOT NULL,
    pais_codigo VARCHAR(5) NOT NULL,
    vinho_id INTEGER,
    review_id TEXT,
    autor TEXT,
    autor_pais TEXT,
    rating INTEGER,
    titulo TEXT,
    texto TEXT,
    data_review TIMESTAMP,
    compra_verificada BOOLEAN,
    votos_util INTEGER,
    formato TEXT,
    coletado_em TIMESTAMP DEFAULT NOW()
);
```

### `vinhos_<pais>` e `vinhos_<pais>_fontes` (compartilhadas)

Os vinhos em si vão pras tabelas `vinhos_br`, `vinhos_us`, `vinhos_de`, etc. (uma por país). Compartilhadas com Tier1/Tier2/Tier3 do dashboard. Criadas por `winegod_codex.db_scraping.criar_tabelas_vinhos(pais)`. Insert via `upsert_vinhos_batch(vinhos, FONTE, pais)`.

> **NÃO é o banco do Render** (`winegod` em `dpg-XXXXX.oregon-postgres.render.com`). É o banco LOCAL `winegod_db` em `localhost:5432`. O scraper alimenta o banco local; o produto chat.winegod.ai usa o do Render. A migração local→Render é uma etapa separada que não está documentada aqui.

---

## 9. Como rodar no PC espelho (passo a passo)

Assumindo que o Murilo sincronizou `C:\natura-automation\` inteiro pro espelho:

### 9.1. Instalar dependências Python

```bash
cd C:\natura-automation
pip install -r requirements.txt   # se existir; senão:
pip install playwright playwright-stealth psycopg2-binary requests beautifulsoup4 python-dotenv flask
python -m playwright install chromium
```

### 9.2. Subir PostgreSQL local (se ainda não tem)

O banco esperado é `winegod_db` em `localhost:5432` com user `postgres` / senha `postgres123` (default em `db_amazon.py:19`). Se for diferente, exporta `WINEGOD_CODEX_DATABASE_URL` ou `WINEGOD_DATABASE_URL`.

> **Opção alternativa**: apontar pro mesmo banco do PC principal via rede. Aí os dois PCs alimentam a mesma base. Se não tem rede entre eles, cada um tem seu banco local.

### 9.3. Criar tabelas

A primeira execução do orchestrator chama `criar_tabelas()` automaticamente. Mas você pode forçar:

```bash
cd C:\natura-automation
python -c "from amazon.db_amazon import criar_tabelas; criar_tabelas()"
```

### 9.4. Subir o dashboard

```bash
python C:\natura-automation\winegod_codex\server.py
```

Vai escutar em `http://localhost:5568/`. Abrir no browser, clicar na aba **Amazon** pra ver o estado.

### 9.5. Rodar o scraper

**Opção A — pelo dashboard**: clica em "Rodar Todos os Paises" ou em "Rodar" na linha de um país específico.

**Opção B — pela CLI** (recomendada se for rodar 1 país por vez no espelho pra dividir carga):

```bash
cd C:\natura-automation
python amazon/orchestrator.py --pais BR             # só BR, todas as fases
python amazon/orchestrator.py --pais BR --fase A    # só Fase A do BR (catálogo)
python amazon/orchestrator.py --pais JP --fase A    # JP precisa rodar Playwright
python amazon/orchestrator.py --pais US DE --fase B # Fase B (detalhes) só pra US e DE
```

Logs vão pra stdout (e o dashboard captura se foi disparado por ele).

### 9.6. Sugestão de divisão entre os 2 PCs

Em 2026-04-10 o estado mostra o que falta:

- **JP** está só 10% migrado (1.636 Playwright vs 14.398 ScrapingDog) → roda Fase A no espelho enquanto o principal faz outra coisa.
- **Fase C nunca rodou** em nenhum país → tem espaço óbvio pro espelho rodar Fase C dos 6 países (`BR US DE FR IT GB`).
- **`descricao` quase 0% em quase todos** → Fase B basicamente não rodou. Espelho pode rodar Fase B em paralelo.

> Mas: se os 2 PCs apontarem pro mesmo banco, isso funciona naturalmente porque o Fase B prioriza vinhos sem `vinicola_nome`/`rating_medio` e o Fase C ignora ASINs que já estão em `amazon_reviews`. Sem sobreposição de trabalho. Se forem bancos separados, cada PC vê os vinhos do seu próprio banco.

---

## 10. Cuidados / pontos de atenção

1. **`SCRAPINGDOG_DEFAULT_KEY` está hardcoded em `amazon/config.py:10`**. Vazamento. Mover pro `.env` é tarefa pendente — não foi feita. Antes de comitar `natura-automation`, sanitizar.
2. **Não roda Fase A em paralelo pro mesmo país nos 2 PCs.** Eles vão duplicar requests pra Amazon e aumentar chance de bloqueio. Coordene por país.
3. **`playwright_stealth` é opcional mas IMPORTANTE.** Sem ele, dobra a taxa de bloqueio. Instale.
4. **`C:\winegod` é referenciado** por `orchestrator.py:69`. Se não existir no espelho, fallback funciona mas filtragem de "is_wine" fica permissiva demais.
5. **Restart de browser a cada 500 páginas é necessário** — sem ele, Chromium come 4-8 GB de RAM.
6. **AE (Emirados) e SA/IN/TR** — SA, IN, TR foram removidos por restrição legal. Se tentar adicionar, vai dar 0 resultados ou bloqueio diferente. Não tente.
7. **JPY é a única moeda sem centavos.** Se adicionar nova moeda asiática (KRW, IDR), tem que adicionar em `MOEDAS_SEM_CENTAVOS` em `utils_playwright.py:224`.
8. **`dados_extras_fonte`** (jsonb) é onde fica `{plataforma:"amazon", modelo:"amazon_playwright", loja:"Amazon BR"}` — não confunda com `dados_extras` (que é onde fica `asin`, `is_prime`, `compras_recentes`, etc.).
9. **Bug DE preço (5%)**: pendente. Provável regressão no `parsear_preco` quando o preço alemão vem em formato `1.234,56 €`.

---

## 11. Arquivos a sincronizar do PC principal pro espelho

Caso o sync ainda não tenha trazido tudo:

```
C:\natura-automation\amazon\__init__.py
C:\natura-automation\amazon\orchestrator.py        ← PRINCIPAL
C:\natura-automation\amazon\config.py              ← marketplaces, queries
C:\natura-automation\amazon\utils_playwright.py    ← anti-bloqueio
C:\natura-automation\amazon\db_amazon.py           ← schema
C:\natura-automation\amazon\category_discovery.py
C:\natura-automation\amazon\query_executor.py      ← LEGADO mas importado
C:\natura-automation\amazon\query_generator.py     ← LEGADO
C:\natura-automation\amazon\main.py                ← LEGADO

C:\natura-automation\winegod_codex\server.py       ← DASHBOARD
C:\natura-automation\winegod_codex\db_scraping.py  ← upsert_vinhos_batch
C:\natura-automation\winegod_codex\utils_scraping.py ← eh_vinho, etc.
```

E se a Fase A precisar de filtragem mais rigorosa de "is_wine":

```
C:\winegod\utils.py   ← define is_wine() e normalize_wine_name()
```

---

## 12. Verificação rápida no PC espelho

Cole isso no terminal do espelho pra confirmar que tudo bate com o principal:

```bash
# 1. Os arquivos existem?
ls C:\natura-automation\amazon\orchestrator.py
ls C:\natura-automation\amazon\utils_playwright.py
ls C:\natura-automation\winegod_codex\server.py

# 2. Quantas linhas?
wc -l C:\natura-automation\amazon\orchestrator.py    # esperado: 711
wc -l C:\natura-automation\amazon\utils_playwright.py # esperado: 414
wc -l C:\natura-automation\amazon\config.py           # esperado: 347

# 3. O Playwright está ok?
python -c "from playwright.sync_api import sync_playwright; print('OK')"
python -c "from playwright_stealth import Stealth; print('stealth OK')"

# 4. O banco responde?
python -c "from amazon.db_amazon import get_connection; \
           c = get_connection().__enter__(); \
           cur = c.cursor(); \
           cur.execute('SELECT COUNT(*) FROM amazon_categorias'); \
           print(cur.fetchone())"

# 5. Smoke test do orchestrator (gate_0 + 1 país, 1 fase, vai parar rápido)
cd C:\natura-automation
python amazon/orchestrator.py --pais AE --fase A
```

`AE` é bom pro smoke test porque tem só ~250 vinhos no total — fecha rápido.

---

## 13. Quem é quem (resumo de papéis)

| Arquivo | Papel | Status |
|---------|-------|--------|
| `amazon/orchestrator.py` | **Pipeline principal**. Fase A (catálogo via split adaptativo de preço), Fase B (detalhes), Fase C (reviews). | **ATIVO** |
| `amazon/utils_playwright.py` | Browser, anti-bloqueio, parser de preço locale-aware, validação de produto, blacklist de acessórios. | **ATIVO** |
| `amazon/config.py` | 18 marketplaces, ~25K templates de query (modelo antigo), tetos de preço, uvas, regiões, produtores. | Parcialmente usado |
| `amazon/db_amazon.py` | Schema PostgreSQL: `amazon_queries`, `amazon_categorias`, `amazon_reviews`. | **ATIVO** |
| `amazon/category_discovery.py` | Descobre node_ids de categorias de vinho na Amazon (usado uma vez por país). | **ATIVO** |
| `amazon/query_executor.py` | **Modelo antigo via ScrapingDog API**. Mantido só porque alguns helpers (`_UVAS_CONHECIDAS`, `parse_rating`, `parse_reviews`) ainda são importados. | **DESATIVADO** |
| `amazon/query_generator.py` | Gera queries texto pro modelo antigo. | **DESATIVADO** |
| `amazon/main.py` | Entry point antigo. | **DESATIVADO** |
| `winegod_codex/server.py` | Dashboard Flask em `:5568`. Dispara o orchestrator como subprocess. | **ATIVO** |
| `winegod_codex/db_scraping.py` | Funções compartilhadas: `criar_tabelas_vinhos(pais)`, `upsert_vinhos_batch(vinhos, fonte, pais)`. | **ATIVO** |
| `winegod_codex/utils_scraping.py` | Helpers de inferência (país, tipo, safra, hash dedup, normalização). | **ATIVO** |

---

## 14. Se você (Claude espelho) só achou o `query_executor.py` (ScrapingDog)

Significa um destes:

1. **A pasta `C:\natura-automation\` não foi sincronizada.** Pede pro Murilo confirmar o sync.
2. **A pasta foi sincronizada mas só parcialmente** — orchestrator.py não veio. Lista `C:\natura-automation\amazon\` e veja o que tem.
3. **Você procurou só pelo padrão "amazon scraper" e caiu no nome `amazon_scraper`** que é a string `FONTE` do modelo antigo. O nome do modelo novo é `amazon_playwright`. Procure por isso, ou por `orchestrator.py`, ou por `scrape_faixa_adaptativa`.

Comandos pra confirmar no espelho:

```bash
# Procurar TODO arquivo Python que mencione Playwright + Amazon
grep -r "amazon_playwright" C:\natura-automation\ 2>/dev/null
grep -r "scrape_faixa_adaptativa" C:\natura-automation\ 2>/dev/null
grep -r "FONTE = \"amazon_playwright\"" C:\natura-automation\ 2>/dev/null

# Se nada vier, a pasta não está sincronizada.
```

---

## 15. Cheat sheet pro Claude espelho

- **Quero ver o status atual** → `curl http://localhost:5568/api/amazon/status | jq`
- **Quero rodar tudo** → `python C:\natura-automation\amazon\orchestrator.py`
- **Quero rodar 1 país** → `python C:\natura-automation\amazon\orchestrator.py --pais BR`
- **Quero rodar só Fase B (detalhes) em US** → `python C:\natura-automation\amazon\orchestrator.py --pais US --fase B`
- **Quero parar** → Ctrl+C no terminal, ou `POST http://localhost:5568/api/stop/amazon`
- **Quero ver os logs** → aba Amazon do dashboard, ou `C:\natura-automation\_amazon_run*.log`
- **Quero entender por que um vinho não foi salvo** → procura no log por `"sem_asin"`, `"titulo_muito_curto"`, `"acessorio"`, ou rastreia em `validar_produto` / `eh_vinho` / `eh_acessorio`
- **Quero adicionar um país** → adiciona em `config.py:MARKETPLACES` + `config.py:PRECO_TETO` + `orchestrator.py:ORDEM_PAISES` + (se necessário) `WINE_KEYWORD` + (se nova moeda) `MOEDAS_SEM_CENTAVOS` em `utils_playwright.py`
- **Quero adicionar uma uva nova** → `config.py:UVAS` (não usado pelo orchestrator novo, é só pro modelo antigo) E `query_executor.py:_UVAS_CONHECIDAS` (esse é o que o orchestrator importa)

---

**Documento gerado em 2026-04-10 por Claude Opus 4.6 (1M context) no PC principal do Murilo, depois de inspecionar diretamente: o processo PID 30872 na porta 5568, o código de `C:\natura-automation\amazon\orchestrator.py`, `utils_playwright.py`, `config.py`, `db_amazon.py`, `query_executor.py`, e a resposta JSON do endpoint `/api/amazon/status`.**
