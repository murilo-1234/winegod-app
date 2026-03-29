INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# CHAT L+N — WineGod Score + Paridade + Micro-Ajustes + Nota Estimada

## CONTEXTO

WineGod.ai e uma IA sommelier com 1.72M vinhos no banco. Cada vinho ja tem:
- `nota_wcf` — nota ponderada (Weighted Collaborative Filtering), calculada a partir de 33M reviews
- `vivino_rating` — nota original do Vivino (media simples)
- `vivino_reviews` — quantidade de reviews
- `preco_min`, `preco_max`, `moeda` — precos de lojas
- `confianca_nota` — "verified" (100+ reviews) ou "estimated"
- `winegod_score_type` — "verified" ou "estimated"

Agora precisamos calcular o **WineGod Score** (score final de custo-beneficio) e os **micro-ajustes**.

## FORMULA DO WINEGOD SCORE

### Passo 1: 4 Micro-Ajustes (somam ate +0.05 max)

1. **Avaliacoes** = +0.00 (fixo, reservado para uso futuro)
2. **Paridade** = +0.02 se o vinho tem preco em 3+ paises diferentes (moedas diferentes)
3. **Legado** = +0.02 se o vinho tem 500+ reviews E nota_wcf >= 4.0
4. **Capilaridade** = +0.01 se o vinho esta disponivel em 5+ lojas (wine_sources)

Total micro-ajustes = soma dos 4, **teto maximo +0.05** (nunca ultrapassa).

### Passo 2: Nota Ajustada

```
nota_ajustada = nota_wcf + total_micro_ajustes
```

Teto: 5.00 (nunca ultrapassa)

### Passo 3: WineGod Score (custo-beneficio)

```
Se tem preco (preco_min > 0):
    preco_normalizado = preco_min / mediana_preco_global
    winegod_score = nota_ajustada / preco_normalizado

Se NAO tem preco:
    winegod_score = nota_ajustada (score = nota, sem ajuste de preco)
```

- `mediana_preco_global`: mediana de `preco_min` de TODOS os vinhos com preco > 0, convertido para USD
- Escala: 0-5, 2 casas decimais
- Se score > 5.00, limitar a 5.00

### Passo 4: Classificacao

- `winegod_score_type` = "verified" se vivino_reviews >= 100
- `winegod_score_type` = "estimated" se vivino_reviews < 100

### Passo 5: Componentes (JSON)

Salvar em `winegod_score_components` (campo JSONB):
```json
{
    "nota_wcf": 4.35,
    "micro_ajustes": {
        "avaliacoes": 0.00,
        "paridade": 0.02,
        "legado": 0.02,
        "capilaridade": 0.00,
        "total": 0.04
    },
    "nota_ajustada": 4.39,
    "preco_min_usd": 25.50,
    "mediana_global_usd": 18.00,
    "preco_normalizado": 1.42,
    "score": 3.09
}
```

## CREDENCIAIS

```
# Banco WineGod no Render
DATABASE_URL=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod
```

## DADOS DISPONIVEIS NO BANCO

Tabela `wines`:
- `id`, `nome`, `produtor`, `safra`, `tipo`
- `pais_nome`, `regiao`, `sub_regiao`
- `vivino_rating`, `vivino_reviews`
- `preco_min`, `preco_max`, `moeda`
- `nota_wcf` (ja preenchido — 1.29M com reviews, ~445K estimados por regiao)
- `confianca_nota` ("verified" ou "estimated")
- `winegod_score` (VAZIO — voce vai preencher)
- `winegod_score_type` (VAZIO — voce vai preencher)
- `winegod_score_components` (VAZIO, JSONB — voce vai preencher)

Tabela `wine_sources`:
- `wine_id`, `store_id`, `preco`, `moeda`, `url`
- Usar para contar lojas por vinho (capilaridade)

Tabela `stores`:
- `id`, `nome`, `dominio`, `pais`
- Usar para contar paises por vinho (paridade)

## CONVERSAO DE MOEDAS PARA USD

Para normalizar precos, usar taxas fixas aproximadas (nao precisa de API):
```python
TAXAS_USD = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "BRL": 0.18,
    "ARS": 0.001, "CLP": 0.001, "MXN": 0.058, "COP": 0.00025,
    "AUD": 0.65, "NZD": 0.60, "CAD": 0.74, "CHF": 1.12,
    "JPY": 0.0067, "KRW": 0.00075, "CNY": 0.14, "HKD": 0.13,
    "SGD": 0.75, "TWD": 0.031, "THB": 0.028, "INR": 0.012,
    "ZAR": 0.055, "SEK": 0.096, "NOK": 0.093, "DKK": 0.145,
    "PLN": 0.25, "CZK": 0.043, "HUF": 0.0027, "RON": 0.22,
    "TRY": 0.031, "ILS": 0.28, "AED": 0.27, "RUB": 0.011,
    "GEL": 0.37, "HRK": 0.14, "BGN": 0.55, "PEN": 0.27,
    "UYU": 0.024, "PHP": 0.018, "MDL": 0.056,
}
```

## ARQUIVOS A CRIAR

### 1. scripts/calc_score.py (NOVO)

Script principal. Estrutura:

```python
#!/usr/bin/env python3
"""Calcula WineGod Score para todos os vinhos no Render."""

import psycopg2
import psycopg2.extras
import json
import os
import time
from statistics import median

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://winegod_user:...")

TAXAS_USD = { ... }  # tabela acima

def converter_para_usd(preco, moeda):
    taxa = TAXAS_USD.get(moeda, None)
    if taxa is None or preco is None or preco <= 0:
        return None
    return round(preco * taxa, 2)

def main():
    conn = psycopg2.connect(DATABASE_URL)

    # 1. Calcular mediana global de precos em USD
    print("Calculando mediana global de precos...")
    # SELECT preco_min, moeda FROM wines WHERE preco_min > 0
    # Converter cada um para USD, calcular mediana

    # 2. Para cada vinho, calcular micro-ajustes
    print("Calculando micro-ajustes...")
    # Paridade: contar paises distintos das lojas que vendem o vinho
    #   SELECT wine_id, COUNT(DISTINCT s.pais) as n_paises
    #   FROM wine_sources ws JOIN stores s ON ws.store_id = s.id
    #   GROUP BY wine_id

    # Capilaridade: contar lojas que vendem o vinho
    #   SELECT wine_id, COUNT(*) as n_lojas
    #   FROM wine_sources GROUP BY wine_id

    # Legado: vivino_reviews >= 500 AND nota_wcf >= 4.0
    #   Ja esta na tabela wines

    # 3. Calcular score para cada vinho
    # 4. UPDATE em batches de 1000

    conn.close()

if __name__ == "__main__":
    main()
```

**Performance:**
- Buscar micro-ajustes em batch (1 query para paridade, 1 para capilaridade)
- Armazenar em dicts: `paridade[wine_id] = n_paises`, `capilaridade[wine_id] = n_lojas`
- Processar vinhos em lotes de 5000 (SELECT com LIMIT/OFFSET)
- UPDATE com executemany em batches de 1000
- Imprimir progresso: `[50000/1720000] 2.9% — 45 scores/sec`
- Tempo estimado: 20-40 min para 1.72M vinhos

### 2. scripts/score_report.py (NOVO — opcional)

Relatorio apos calculo:
- Distribuicao de scores (0-1, 1-2, 2-3, 3-4, 4-5)
- Top 10 vinhos por score
- Top 10 vinhos por nota_ajustada
- Media de score por pais
- Quantos verified vs estimated
- Quantos com vs sem preco

## O QUE NAO FAZER

- **NAO modificar nenhum arquivo do backend ou frontend** — so scripts/
- **NAO modificar app.py, baco.py, tools/**, ou qualquer arquivo existente
- **NAO deletar ou recalcular nota_wcf** — ja esta pronto, so ler
- **NAO fazer git commit/push** — avisar quando terminar
- **NAO usar APIs de cambio** — usar taxas fixas do dicionario acima

## COMO TESTAR

1. Testar com 100 vinhos:
```bash
cd scripts
python -c "
from calc_score import *
# Testar logica com 1 vinho
"
```

2. Verificar no banco apos rodar:
```sql
SELECT COUNT(*) FROM wines WHERE winegod_score IS NOT NULL;
SELECT AVG(winegod_score), MIN(winegod_score), MAX(winegod_score) FROM wines WHERE winegod_score IS NOT NULL;
SELECT winegod_score_components FROM wines WHERE winegod_score IS NOT NULL LIMIT 3;
```

3. Rodar completo:
```bash
cd scripts && python calc_score.py
```

## ENTREGAVEL

- `scripts/calc_score.py` — script de calculo (pronto pra rodar)
- `scripts/score_report.py` — relatorio (opcional)
- 1.72M vinhos com `winegod_score`, `winegod_score_type`, `winegod_score_components` preenchidos no banco Render

## REGRA DE COMMIT

Commitar APENAS os arquivos que VOCE criou/modificou nesta sessao. NUNCA incluir arquivos de outros chats. Fazer `git pull` antes de `git push` para nao conflitar com outros chats que rodam em paralelo.
