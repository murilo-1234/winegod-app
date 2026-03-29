INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# FIX SCRAPERS — Melhorias de moeda, filtro e validacao nos 3 sistemas de scraping

## CONTEXTO

WineGod.ai tem 3 sistemas de scraping independentes que alimentam ~4.86M registros de precos em 50 paises. Uma auditoria encontrou problemas graves causados pela extracao:

- **1.19M registros com moeda errada** (scraper defaulta USD quando nao encontra moeda)
- **~100K registros de produtos nao-vinho** (scraper pega tudo da loja sem filtrar)
- **~22K registros com preco em centavos** (Magento retorna centavos, scraper grava direto)
- **~10K placeholders** (preco = 1.00, 99999 — scraper nao valida)
- **~80K URLs duplicadas** (scraper grava homepage como produto)

## OS 3 SISTEMAS

| Sistema | Localizacao | Arquivos a modificar |
|---------|------------|---------------------|
| **Codex** | `C:\natura-automation\winegod_codex\` | `scraper_tier1.py` (38KB), `tier2_service.py` (28KB) |
| **Admin** | `C:\natura-automation\winegod_admin\` | `scraper_tier1.py`, `scraper_tier2.py` |
| **Claude** | `C:\winegod\` | `CLAUDE.md`, `db\dedup.py` |

Todos gravam no mesmo banco local: `postgresql://postgres:XXXXXXXXX@localhost:5432/winegod_db`

Tabelas afetadas: `vinhos_{pais}_fontes` (50 tabelas) e `lojas_scraping` (64K lojas)

## SUA TAREFA

Criar uma biblioteca compartilhada `winegod_utils` e integrar nos 3 sistemas, implementando 7 melhorias.

---

## PASSO 0 — LER OS ARQUIVOS ANTES DE QUALQUER COISA

ANTES de escrever qualquer codigo, leia INTEIRAMENTE estes arquivos para entender a logica atual:

1. `C:\natura-automation\winegod_codex\scraper_tier1.py` — Tier 1 Codex (Shopify, WooCommerce, VTEX, Tiendanube)
2. `C:\natura-automation\winegod_codex\tier2_service.py` — Tier 2 Codex (Playwright + BeautifulSoup)
3. `C:\natura-automation\winegod_codex\utils_scraping.py` — Utilitarios Codex
4. `C:\natura-automation\winegod_codex\server.py` — Server/config Codex
5. `C:\natura-automation\winegod_admin\scraper_tier1.py` — Tier 1 Admin
6. `C:\natura-automation\winegod_admin\scraper_tier2.py` — Tier 2 Admin (Grok/DeepSeek)
7. `C:\winegod\db\dedup.py` — Normalizacao/hash (85 linhas)
8. `C:\winegod\CLAUDE.md` — Instrucoes do sistema Claude
9. `C:\winegod\config\settings.py` — Config global

Anote EXATAMENTE:
- Onde cada sistema extrai o preco (funcao, linha)
- Onde cada sistema define a moeda (funcao, linha)
- Onde cada sistema grava no banco (funcao, linha)
- Quais validacoes ja existem (se alguma)

---

## PASSO 1 — CRIAR BIBLIOTECA COMPARTILHADA

Criar `C:\winegod\utils\` com 4 modulos:

### 1.1 `C:\winegod\utils\currency.py`

```python
"""
Deteccao de moeda da loja via API/HTML.
Uma chamada por loja (nao por produto).
"""

# Mapeamento pais -> moeda (fallback quando API nao retorna)
MOEDA_POR_PAIS = {
    "ae": "AED", "ar": "ARS", "at": "EUR", "au": "AUD", "be": "EUR",
    "bg": "BGN", "br": "BRL", "ca": "CAD", "ch": "CHF", "cl": "CLP",
    "cn": "CNY", "co": "COP", "cz": "CZK", "de": "EUR", "dk": "DKK",
    "es": "EUR", "fi": "EUR", "fr": "EUR", "gb": "GBP", "ge": "GEL",
    "gr": "EUR", "hk": "HKD", "hr": "EUR", "hu": "HUF", "ie": "EUR",
    "il": "ILS", "in": "INR", "it": "EUR", "jp": "JPY", "kr": "KRW",
    "lu": "EUR", "md": "MDL", "mx": "MXN", "nl": "EUR", "no": "NOK",
    "nz": "NZD", "pe": "PEN", "ph": "PHP", "pl": "PLN", "pt": "EUR",
    "ro": "RON", "ru": "RUB", "se": "SEK", "sg": "SGD", "th": "THB",
    "tr": "TRY", "tw": "TWD", "us": "USD", "uy": "UYU", "za": "ZAR",
}

def get_currency_shopify(base_url, session=None):
    """
    Shopify: GET /meta.json -> {"currency": "DKK"}
    Alternativa: GET /products.json?limit=1 e ler campo "currency" se existir
    Retorna string da moeda ou None se falhar.
    """
    # Implementar: tentar /meta.json primeiro, depois /cart.json (tem "currency")
    pass

def get_currency_woocommerce(base_url, session=None):
    """
    WooCommerce: GET /wp-json/wc/v3/data/currencies/current -> {"code": "PLN"}
    Alternativa: parsear <meta property="og:price:currency"> do HTML
    Retorna string da moeda ou None.
    """
    pass

def get_currency_vtex(product_json):
    """
    VTEX: o JSON do produto JA contem "currencyCode": "BRL"
    So precisa ler o campo.
    """
    pass

def get_currency_for_store(base_url, plataforma, pais_codigo, session=None):
    """
    Funcao principal: tenta detectar moeda via API da plataforma.
    Se falhar, usa fallback pais -> moeda.
    NUNCA retorna USD como default (a menos que pais = 'us').
    """
    # 1. Tentar via API da plataforma
    # 2. Se falhar, usar MOEDA_POR_PAIS[pais_codigo]
    # 3. Se pais desconhecido, retornar None (nao USD!)
    pass
```

### 1.2 `C:\winegod\utils\wine_filter.py`

```python
"""
Filtro para separar vinhos de nao-vinhos.
Roda ANTES do insert no banco.
"""
import re

# Produtos que NUNCA sao vinho
NON_WINE_KEYWORDS = re.compile(
    r'\b(whisky|whiskey|vodka|gin(?!\s*\w*ger)|rum\b|tequila|cognac|bourbon|'
    r'beer|cerveja|birra|bier|'
    r'gift\s*card|gutschein|carte\s*cadeau|tarjeta\s*regalo|voucher|'
    r'cheese|queijo|fromage|formaggio|'
    r'chocolate|coffee|cafe\s|espresso|'
    r'ketchup|mayonnaise|mustard|vinegar|olive\s*oil|'
    r'soap|shampoo|candle|perfume|cream|lotion|'
    r't-shirt|camiseta|shirt|jeans|bra\b|panties|lingerie|'
    r'flower|flor\b|bouquet|'
    r'volleyball|basketball|soccer|dumbbell|'
    r'pet\s*food|dog\s*food|cat\s*food|'
    r'chicken|frango|beef|pork|fish\b|shrimp|'
    r'toothpaste|mouthwash|razor|detergent|'
    r'toilet\s*paper|paper\s*towel|'
    r'espresso\s*machine|coffee\s*machine|grinder)\b',
    re.IGNORECASE
)

# Sufixos que indicam embalagem (manter o vinho, remover sufixo)
GIFT_SUFFIX = re.compile(
    r'\s*[-–—]?\s*(gift\s*(box|boxed|set|tin|bag|pack|wrapped|packaging))\s*$',
    re.IGNORECASE
)

def is_wine(nome):
    """Retorna True se o produto provavelmente e vinho."""
    if not nome or len(nome.strip()) < 3:
        return False
    return not NON_WINE_KEYWORDS.search(nome)

def clean_gift_suffix(nome):
    """Remove 'Gift Box', 'Gift Set' etc do nome, mantendo o vinho."""
    return GIFT_SUFFIX.sub('', nome).strip()
```

### 1.3 `C:\winegod\utils\price_validator.py`

```python
"""
Validacao de precos antes de gravar no banco.
"""

FAIXA_PRECO = {
    "USD": (2, 50000), "EUR": (2, 50000), "GBP": (2, 40000),
    "BRL": (10, 100000), "ARS": (500, 5000000), "CLP": (1000, 10000000),
    "MXN": (30, 500000), "COP": (5000, 50000000), "PEN": (10, 50000),
    "UYU": (50, 500000), "AUD": (3, 50000), "NZD": (3, 50000),
    "CAD": (3, 50000), "CHF": (2, 50000), "JPY": (200, 5000000),
    "KRW": (2000, 50000000), "CNY": (10, 500000), "HKD": (10, 500000),
    "SGD": (3, 50000), "TWD": (50, 500000), "THB": (50, 500000),
    "INR": (100, 5000000), "ZAR": (20, 500000), "SEK": (20, 500000),
    "NOK": (20, 500000), "DKK": (20, 500000), "PLN": (5, 100000),
    "CZK": (20, 500000), "HUF": (200, 5000000), "RON": (5, 100000),
    "TRY": (10, 500000), "ILS": (10, 100000), "AED": (5, 200000),
    "BGN": (3, 100000), "GEL": (3, 50000), "MDL": (10, 100000),
    "PHP": (50, 500000), "RUB": (50, 5000000),
}

# Placeholders conhecidos
PLACEHOLDER_VALUES = {0, 0.01, 0.99, 1.00, 9999, 99999, 99999.99, 999999}

def is_valid_price(preco, moeda):
    """
    Retorna True se o preco e valido para a moeda.
    Rejeita: None, 0, negativos, placeholders, fora da faixa.
    """
    if preco is None or preco <= 0:
        return False
    if preco in PLACEHOLDER_VALUES:
        return False
    faixa = FAIXA_PRECO.get(moeda)
    if faixa:
        minimo, maximo = faixa
        if preco > maximo:
            return False
    return True

def fix_centavos_magento(preco, moeda, plataforma):
    """
    Magento retorna precos em centavos (9081 = 90.81).
    Se plataforma = magento E preco > faixa_max, divide por 100.
    """
    if plataforma and 'magento' in plataforma.lower():
        faixa = FAIXA_PRECO.get(moeda, (1, 100000))
        if preco > faixa[1]:
            return preco / 100
    return preco

def is_valid_url(url):
    """
    Rejeita URLs que nao sao paginas de produto.
    """
    if not url:
        return False
    bad_patterns = ['/cart', '/checkout', '/login', '/account', '/search',
                    'javascript:', 'mailto:', '#']
    url_lower = url.lower()
    for pattern in bad_patterns:
        if pattern in url_lower:
            return False
    return True
```

### 1.4 `C:\winegod\utils\normalize.py`

```python
"""
Normalizacao de nomes de vinho.
Pipeline: unescape HTML -> remover volume -> remover preco -> limpar.
"""
import html
import re
import unicodedata

# Volume patterns
VOLUME_PATTERN = re.compile(
    r'\s*[-–—]?\s*\(?\s*\d+(?:[.,]\d+)?\s*'
    r'(?:ml|cl|l|lt|ltr|litre|liter|litro|oz|fl\.?\s*oz)\s*\)?\s*',
    re.IGNORECASE
)

# Price patterns em qualquer moeda
PRICE_PATTERN = re.compile(
    r'(?:R\$|€|\$|£|¥|₩|kr|zł|Kč|Ft|lei|₺|₽|₪|AED|BRL|EUR|USD|GBP)\s*'
    r'\d+[.,]?\d*(?:\s*(?:por|per|each|unidade|unit))?',
    re.IGNORECASE
)

# Alcohol percentage
ALCOHOL_PATTERN = re.compile(
    r'\s*[-–—]?\s*\d+[.,]?\d*\s*%\s*(?:vol|alc|abv)?\s*\.?\s*',
    re.IGNORECASE
)

def normalize_wine_name(nome):
    """
    Pipeline completo de normalizacao:
    1. HTML unescape
    2. Remove volume (750ml, 75cl, 1.5L)
    3. Remove preco (R$89,00)
    4. Remove teor alcoolico (13.5% vol)
    5. Limpa espacos e pontuacao trailing
    """
    if not nome:
        return nome

    # 1. HTML entities
    nome = html.unescape(nome)

    # 2. Volume
    nome = VOLUME_PATTERN.sub(' ', nome)

    # 3. Preco
    nome = PRICE_PATTERN.sub(' ', nome)

    # 4. Alcool
    nome = ALCOHOL_PATTERN.sub(' ', nome)

    # 5. Limpar
    nome = re.sub(r'\s+', ' ', nome).strip()
    nome = nome.strip('-–— .,;:')

    return nome


def normalize_for_search(nome):
    """
    Normalizacao para busca/dedup.
    MANTEM caracteres nao-latinos (japones, russo, coreano, etc).
    Remove apenas acentos combinantes (diacriticos).
    """
    if not nome:
        return nome

    nome = nome.lower().strip()

    # Remove acentos combinantes (e -> e) mas MANTEM kanji, cirillico, etc
    nome = unicodedata.normalize('NFKD', nome)
    nome = ''.join(c for c in nome if not unicodedata.combining(c))

    # Remove pontuacao mas MANTEM letras de qualquer script + numeros + espacos
    # \w em Python com Unicode flag inclui letras de todos os scripts
    nome = re.sub(r'[^\w\s]', '', nome, flags=re.UNICODE)

    # Normaliza espacos
    nome = re.sub(r'\s+', ' ', nome).strip()

    return nome
```

### 1.5 `C:\winegod\utils\__init__.py`

```python
from .currency import get_currency_for_store, MOEDA_POR_PAIS
from .wine_filter import is_wine, clean_gift_suffix
from .price_validator import is_valid_price, fix_centavos_magento, is_valid_url
from .normalize import normalize_wine_name, normalize_for_search
```

---

## PASSO 2 — INTEGRAR NO CODEX (scraper_tier1.py)

Apos ler o arquivo `C:\natura-automation\winegod_codex\scraper_tier1.py` inteiro:

1. Adicionar import no topo:
```python
import sys
sys.path.insert(0, 'C:\\winegod')
from utils import get_currency_for_store, is_wine, is_valid_price, fix_centavos_magento, is_valid_url, normalize_wine_name, MOEDA_POR_PAIS
```

2. Encontrar onde o scraper **define a moeda** para cada loja e substituir a logica:
   - ANTES: provavelmente assume USD ou pega do campo sem fallback
   - DEPOIS: chamar `get_currency_for_store(url, plataforma, pais)` ANTES de iterar produtos

3. Encontrar onde o scraper **grava cada produto** no banco e adicionar validacoes:
   - Checar `is_wine(nome)` — se False, pular o produto
   - Checar `is_valid_price(preco, moeda)` — se False, pular
   - Checar `is_valid_url(url)` — se False, pular
   - Aplicar `fix_centavos_magento(preco, moeda, plataforma)`
   - Aplicar `normalize_wine_name(nome)` no nome antes de gravar

4. **NAO alterar** a estrutura do scraper, o fluxo de paginacao, ou a logica de retry. Apenas adicionar validacoes pontuais.

---

## PASSO 3 — INTEGRAR NO CODEX (tier2_service.py)

Mesmo processo para `C:\natura-automation\winegod_codex\tier2_service.py`:

1. Adicionar imports (mesmo do Passo 2)
2. Encontrar onde extrai preco/moeda do HTML parseado
3. Adicionar as mesmas validacoes (is_wine, is_valid_price, is_valid_url)
4. Aplicar normalize_wine_name no nome extraido
5. Para Tier 2, a moeda provavelmente vem do HTML ou da classificacao da loja — garantir que usa `get_currency_for_store` como fallback

---

## PASSO 4 — INTEGRAR NO ADMIN (scraper_tier1.py)

Mesmo processo para `C:\natura-automation\winegod_admin\scraper_tier1.py`:

1. Adicionar imports
2. Encontrar extracao de preco/moeda
3. Adicionar validacoes
4. Aplicar normalizacao

---

## PASSO 5 — INTEGRAR NO ADMIN (scraper_tier2.py)

Mesmo processo para `C:\natura-automation\winegod_admin\scraper_tier2.py`:

1. Adicionar imports
2. Este arquivo usa Grok/DeepSeek para extrair — a IA pode retornar moeda errada
3. Validar moeda retornada pela IA contra `MOEDA_POR_PAIS[pais]`
4. Adicionar is_wine, is_valid_price, is_valid_url

---

## PASSO 6 — ATUALIZAR DEDUP.PY (Unicode fix)

Arquivo: `C:\winegod\db\dedup.py`

**PROBLEMA ATUAL** (linha 17):
```python
texto = re.sub(r'[^a-z0-9\s]', '', texto)
```
Isso destroi TODOS os caracteres nao-latinos (japones, russo, coreano, arabe, etc).

**CORRECAO:**
```python
# ANTES: texto = re.sub(r'[^a-z0-9\s]', '', texto)
# DEPOIS: manter caracteres Unicode, remover apenas pontuacao
texto = re.sub(r'[^\w\s]', '', texto, flags=re.UNICODE)
```

**IMPORTANTE:** Essa mudanca altera os hashes de vinhos com nomes nao-latinos. Nao e urgente para esta sessao — pode ser feita separadamente com um script de re-hash. Se decidir fazer agora, rode um script que recalcula hashes e faz merge de duplicatas.

---

## PASSO 7 — ATUALIZAR CLAUDE.MD

Adicionar ao `C:\winegod\CLAUDE.md` na secao de regras:

```markdown
## Regras de Extracao de Precos

1. NUNCA usar USD como moeda default. Usar `utils.currency.get_currency_for_store()` ou fallback `MOEDA_POR_PAIS[pais]`.
2. SEMPRE validar preco com `utils.price_validator.is_valid_price()` antes de gravar.
3. SEMPRE filtrar nao-vinhos com `utils.wine_filter.is_wine()` antes de gravar.
4. SEMPRE normalizar nome com `utils.normalize.normalize_wine_name()` antes de gravar.
5. Para Magento: aplicar `fix_centavos_magento()` no preco.
6. Rejeitar URLs invalidas com `is_valid_url()`.
```

---

## COMO TESTAR

```bash
# 1. Testar a biblioteca isolada
cd C:\winegod
python -c "
from utils import is_wine, is_valid_price, normalize_wine_name, MOEDA_POR_PAIS
print(is_wine('Chateau Margaux 2015'))  # True
print(is_wine('Ketchup Heinz 500g'))   # False
print(is_valid_price(29.90, 'EUR'))     # True
print(is_valid_price(1.00, 'EUR'))      # False (placeholder)
print(is_valid_price(99999, 'BRL'))     # False (placeholder)
print(normalize_wine_name('Vinho Tinto 750mlR\$89,00'))  # 'Vinho Tinto'
print(MOEDA_POR_PAIS['dk'])  # DKK
"

# 2. Testar Codex Tier 1 com dry-run em 1 pais
# (depende de como o Codex roda — verificar no server.py)

# 3. Testar Admin Tier 1 com 1 loja
```

---

## O QUE NAO FAZER

- **NAO alterar a estrutura dos scrapers** — apenas adicionar validacoes pontuais
- **NAO alterar tabelas do banco** — gravar nos mesmos campos que ja existem
- **NAO rodar scraping real** durante a implementacao — so testar funcoes isoladas
- **NAO alterar o hash de dedup** sem um plano de migracao (Passo 6 e opcional)
- **NAO deletar dados existentes**
- **NAO fazer git commit/push sem perguntar**

## ENTREGAVEL

1. `C:\winegod\utils\currency.py` — deteccao de moeda
2. `C:\winegod\utils\wine_filter.py` — filtro nao-vinho
3. `C:\winegod\utils\price_validator.py` — validacao de preco
4. `C:\winegod\utils\normalize.py` — normalizacao de nome
5. `C:\winegod\utils\__init__.py` — exports
6. Codex `scraper_tier1.py` modificado (com imports + validacoes)
7. Codex `tier2_service.py` modificado
8. Admin `scraper_tier1.py` modificado
9. Admin `scraper_tier2.py` modificado
10. `C:\winegod\CLAUDE.md` atualizado com regras de extracao

## DADOS DA AUDITORIA (para referencia)

### Moedas erradas encontradas (1.19M registros corrigidos):
31 paises tinham moeda marcada como USD quando deveria ser local. Os piores: DK (126K), HK (106K), PH (97K), IE (83K), BE (70K). Causa: scraper Tier 1 nao lia moeda da API.

### Produtos nao-vinho encontrados (~100K):
- StarQuik (IN): 20,866 — supermercado (frango, peixe, detergente)
- Rustans (PH): 17,918 — loja de departamento
- ShopSuki (PH): 14,791 — mercearia geral
- Cerqular (HK): 13,553 — moda/roupas
- Ever (PH): 17,525 — supermercado
- The Sip Shop (US): 5,849 — equipamento esportivo
- Ionion Market (GR): 5,742 — mercearia
- Tipsy.in (IN): 404 — lingerie (a cor "wine" confundiu o scraper)

### Precos em centavos (22K):
- garrafeiranacional.com (BR/PT): 18,925 — centimos EUR via Magento API
- vinhosevinhos.com (BR): 3,252 — centavos BRL via Magento
- trivino.com.br: 10, peterlongo: 18, domoexpress: 22

### Placeholders (10K):
- Suecia: 8,188 com preco = 1.00
- Franca: 622, Grecia: 280, US: 206, Holanda: 204
- Brasil: 97 com preco >= 99999 (interfood.com.br)

### URLs duplicadas (80K):
- BR: 18,238 extras (7.1%) — nicovinhos.com.br com 120 duplicatas da homepage
- NZ: 7,595 (7.1%), IT: 10,449 (6.5%), CA: 6,517 (6.5%)

### Distribuicao por fonte (como o scraper marca a origem):
- Tier 1 grava na coluna `fonte`: shopify, woocommerce, vtex, vtex_io, magento, nuvemshop, tray, dooca, loja_integrada, wix
- Tier 2 grava: opus, grok, deepseek, codex_bs4

### Tipo da coluna preco:
TODAS as 50 tabelas usam `real` (float 4 bytes) — pode causar erros de arredondamento. NAO corrigir agora (mudanca de schema).
