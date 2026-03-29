INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# CHAT PRICES — Correcao de Precos e Moedas (4.58M registros)

## CONTEXTO

WineGod.ai tem 4.17M vinhos scraped de 50 paises. Os precos estao nas tabelas `vinhos_{pais}_fontes` no banco local (4.58M registros com preco). Dois problemas foram detectados:

1. **~20 paises com moeda errada** — marcados como USD quando deveria ser moeda local (DKK, PLN, SEK, etc.)
2. **~6 paises com precos gigantes** — erro de parse decimal ("15990" em vez de "159.90")

## CREDENCIAIS

```
WINEGOD_LOCAL_URL=postgresql://postgres:XXXXXXXXX@localhost:5432/winegod_db
```

## SUA TAREFA

Criar e rodar um script que corrige precos e moedas em 3 passes, usando tecnicas estatisticas comprovadas.

## PASSO 0 — INSTALAR DEPENDENCIAS

```bash
pip install price-parser
```

## PASSO 1 — DIAGNOSTICO (antes de corrigir qualquer coisa)

Gerar relatorio completo ANTES de qualquer alteracao:

```python
# Para CADA pais (50 tabelas vinhos_{pais}_fontes):
# 1. Contar registros com preco > 0
# 2. Moedas presentes (distribuicao)
# 3. Mediana, Q1, Q3, IQR
# 4. Min, Max
# 5. Percentil 99
# 6. Quantidade de outliers (preco > Q3 + 1.5*IQR)
# 7. Benford's Law: distribuicao do primeiro digito (deve ser ~30% "1", ~17% "2", etc.)

# Salvar diagnostico em arquivo JSON para referencia
```

## PASSO 2 — CORRIGIR MOEDAS ERRADAS

Mapeamento pais → moeda correta:

```python
MOEDA_CORRETA = {
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

# Faixas de preco aceitaveis por moeda (vinho mais barato e mais caro razoavel)
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
```

**Logica de correcao de moeda:**

Para cada pais com moeda marcada como USD mas que deveria ser outra:
1. Calcular mediana do preco atual (em "USD")
2. Converter essa mediana para a moeda local real
3. Se o valor convertido faz sentido na faixa do pais → a moeda ja esta certa (realmente USD, loja internacional)
4. Se o valor SEM conversao faz sentido na faixa da moeda local → moeda errada, corrigir
5. Validar com amostra de 20 registros antes de aplicar UPDATE

```sql
-- Exemplo: DK marcado como USD, mediana 1645
-- 1645 USD = improvavel para vinho medio dinamarques
-- 1645 DKK = ~230 USD = faz sentido
-- Conclusao: moeda errada, UPDATE para DKK
UPDATE vinhos_dk_fontes SET moeda = 'DKK' WHERE moeda = 'USD';
```

## PASSO 3 — CORRIGIR PRECOS GIGANTES (IQR Method)

Para CADA pais+moeda (apos correcao de moeda):

```python
import numpy as np

def corrigir_precos_pais(cur, pais, moeda_correta):
    tabela = f"vinhos_{pais}_fontes"

    # 1. Buscar todos os precos
    cur.execute(f"SELECT id, preco FROM {tabela} WHERE preco > 0 AND moeda = %s", (moeda_correta,))
    rows = cur.fetchall()
    precos = [r[1] for r in rows]

    if len(precos) < 10:
        return 0

    # 2. Calcular IQR
    q1 = np.percentile(precos, 25)
    q3 = np.percentile(precos, 75)
    iqr = q3 - q1
    upper_fence = q3 + 3.0 * iqr  # Usar 3x IQR (mais permissivo que 1.5x para vinhos de luxo)

    faixa_min, faixa_max = FAIXA_PRECO.get(moeda_correta, (1, 100000))

    # 3. Identificar outliers
    outliers = [(r[0], r[1]) for r in rows if r[1] > upper_fence and r[1] > faixa_max]

    # 4. Para cada outlier, tentar corrigir
    corrigidos = 0
    for id_reg, preco in outliers:
        # Tentar dividir por 100
        p100 = preco / 100
        if faixa_min <= p100 <= faixa_max:
            cur.execute(f"UPDATE {tabela} SET preco = %s WHERE id = %s", (p100, id_reg))
            corrigidos += 1
            continue

        # Tentar dividir por 1000
        p1000 = preco / 1000
        if faixa_min <= p1000 <= faixa_max:
            cur.execute(f"UPDATE {tabela} SET preco = %s WHERE id = %s", (p1000, id_reg))
            corrigidos += 1
            continue

        # Nao conseguiu corrigir — marcar como suspeito (preco negativo = flag)
        # NAO deletar, NAO usar
        cur.execute(f"UPDATE {tabela} SET preco = -1 WHERE id = %s", (id_reg,))

    return corrigidos
```

**IMPORTANTE:** Antes de rodar o UPDATE em cada pais:
1. Mostrar 10 exemplos de outliers e o que seria o preco corrigido
2. Mostrar quantos seriam afetados
3. Aplicar automaticamente (nao pedir confirmacao)

## PASSO 4 — VALIDACAO (Benford's Law)

Apos todas as correcoes, validar com Benford's Law:

```python
from collections import Counter

def benford_check(precos):
    """Verifica se distribuicao do primeiro digito segue Benford's Law."""
    first_digits = [str(int(p))[0] for p in precos if p > 0]
    total = len(first_digits)
    dist = Counter(first_digits)

    # Distribuicao esperada por Benford
    benford = {'1': 0.301, '2': 0.176, '3': 0.125, '4': 0.097,
               '5': 0.079, '6': 0.067, '7': 0.058, '8': 0.051, '9': 0.046}

    desvio_total = 0
    for d in '123456789':
        real = dist.get(d, 0) / total
        esperado = benford[d]
        desvio = abs(real - esperado)
        desvio_total += desvio

    # Desvio total < 0.15 = OK, > 0.15 = suspeito
    return desvio_total, desvio_total < 0.15
```

Rodar Benford para cada pais ANTES e DEPOIS da correcao. Se o desvio melhorou (diminuiu), a correcao foi boa.

## PASSO 5 — RELATORIO FINAL

Imprimir:

```
=== RELATORIO DE CORRECAO DE PRECOS ===

MOEDAS CORRIGIDAS:
  DK: USD → DKK (120,420 registros)
  PL: USD → PLN (64,974 registros)
  ...

PRECOS CORRIGIDOS (IQR):
  BR: 1,234 outliers corrigidos (div/100: 890, div/1000: 344)
  FR: 567 outliers corrigidos
  ...

PRECOS SUSPEITOS (nao corrigiveis):
  GR: 89 marcados como -1
  ...

BENFORD'S LAW (antes → depois):
  BR: 0.23 → 0.08 (MELHOROU)
  FR: 0.19 → 0.06 (MELHOROU)
  ...

TOTAL:
  Moedas corrigidas: X paises, Y registros
  Precos corrigidos: Z registros
  Precos suspeitos: W registros
  Benford passou: N/50 paises
```

## ARQUIVO A CRIAR

### scripts/fix_prices.py (NOVO)

Script completo com os 5 passos acima. Salvar diagnostico em `scripts/prices_diagnostic.json` e relatorio final em `scripts/prices_report.txt`.

## O QUE NAO FAZER

- **NAO deletar registros** — marcar suspeitos como preco = -1
- **NAO modificar tabelas que nao sejam _fontes** — vinhos_{pais} e wines_clean ficam intactos
- **NAO conectar ao banco Render** — tudo local
- **NAO fazer git commit/push** — avisar quando terminar
- **NAO corrigir precos que ja estao na faixa aceitavel** — so outliers

## COMO TESTAR

```bash
# Testar com 1 pais primeiro
cd scripts && python fix_prices.py --pais br --dry-run
# Se ok, rodar tudo
cd scripts && python fix_prices.py
```

## ENTREGAVEL

- `scripts/fix_prices.py`
- `scripts/prices_diagnostic.json` — diagnostico pre-correcao
- `scripts/prices_report.txt` — relatorio pos-correcao
- Precos corrigidos nas 50 tabelas `vinhos_{pais}_fontes`

## REGRA DE COMMIT

Commitar APENAS os arquivos que VOCE criou/modificou nesta sessao. Fazer `git pull` antes de `git push`.
