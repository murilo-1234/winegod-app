# HANDOFF — Problema P7: Estudo Aprofundado de Scores e Notas

## Quem é você neste chat
Você é um data scientist sênior investigando o sistema de scoring do WineGod.ai. Sua missão é **fazer um estudo estatístico profundo** das discrepâncias entre vivino_rating, nota_wcf e winegod_score. NÃO implemente nada — entregue o estudo completo com dados, gráficos conceituais e recomendações.

---

## O que é o WineGod.ai

WineGod.ai é uma IA sommelier. O usuário conversa com "Baco" (deus do vinho) via chat web. Baco responde sobre vinhos, dá notas, recomenda.

### Stack relevante
- **Banco**: PostgreSQL 16 no Render (~1.72M vinhos)
- **Backend**: Python 3.11, Flask (`C:\winegod-app\backend\`)
- **Pipeline de dados**: repo separado em `C:\winegod\`

---

## OS 3 CAMPOS DE NOTA NO BANCO

A tabela `wines` tem 3 campos de nota diferentes:

### 1. `vivino_rating` (DECIMAL)
- Nota ORIGINAL do Vivino (0-5)
- Nunca modificada pelo nosso sistema
- Fonte: scraping direto do Vivino
- Exemplo: Pena Vermelha Reserva = 3.90

### 2. `nota_wcf` (DECIMAL 3,2)
- "Weighted Collaborative Filtering" — nota recalculada
- Gerada no repo `winegod` via algoritmo WCF → exportada em `wcf_results.csv`
- Importada pelo script `C:\winegod-app\scripts\calc_wcf.py`
- Match feito por `vivino_id`
- Exemplo: Pena Vermelha Reserva = 3.71 (0.19 MENOR que o Vivino!)

### 3. `winegod_score` (DECIMAL 3,2)
- Score de CUSTO-BENEFÍCIO (não é nota de qualidade)
- Calculado pelo script `C:\winegod-app\scripts\calc_score.py`
- Fórmula: `nota_ajustada / (preço_usd / mediana_global_usd)`
- Cap em 5.00
- Se preço=NULL: winegod_score = nota_ajustada (= nota_wcf + micro_ajustes)

### Campos auxiliares:
- `winegod_score_type` — "verified" (100+ reviews), "estimated" (1-99), "none" (0)
- `winegod_score_components` — JSONB com detalhes do cálculo
- `confianca_nota` — 0.2 a 1.0 baseado em número de reviews
- `vivino_reviews` — número de reviews no Vivino

---

## O PROBLEMA REPORTADO

O dono do produto testou vinhos reais e viu discrepâncias:
> "Vi vinhos de 4.0 no Vivino que nosso sistema tá dando 4.2 — é muita discrepância"

---

## DADOS CONCRETOS QUE JÁ COLETAMOS

### Cordero con Piel de Lobo (TODOS os dados):

| Variante | ID | Vivino | WCF | WG Score | Preço USD | Reviews |
|----------|-----|--------|-----|----------|-----------|---------|
| Gran Malbec | 1721546 | 4.00 | 4.10 | 4.10 | None | 53 |
| Malbec | 963879 | 3.80 | 3.93 | **5.00** | $9.08 | 69869 |
| Chardonnay | 1164637 | 3.90 | 3.89 | **5.00** | $9.08 | 4262 |
| Rosé | 1294949 | 3.80 | 3.92 | **5.00** | $9.08 | 2921 |
| Merlot | 1603321 | 3.80 | 3.78 | **2.83** | $58.49 | 228 |
| Bonarda | 1599399 | 3.80 | 3.86 | **2.60** | $64.99 | 1843 |
| CS | 1152637 | 3.80 | 3.76 | **5.00** | $12.43 | 13531 |
| Torrontés-Chard | 1377919 | 3.80 | 3.84 | 3.84 | None | 280 |
| Demi Sec | 1439086 | 3.80 | 3.77 | 3.77 | None | 286 |
| Blend Blancas | 1492148 | 3.90 | 3.94 | **5.00** | $9.17 | 1321 |

**Components do Gran Malbec:**
```json
{
  "nota_wcf": 4.1,
  "micro_ajustes": {"total": 0.0, "legado": 0.0, "paridade": 0.0, "avaliacoes": 0.0, "capilaridade": 0.0},
  "nota_ajustada": 4.1,
  "preco_min_usd": null,
  "mediana_global_usd": 43.84,
  "preco_normalizado": null,
  "score": 4.1
}
```

**Components do Malbec regular (score 5.00):**
```json
{
  "nota_wcf": 3.93,
  "micro_ajustes": {"total": 0.0},
  "nota_ajustada": 3.93,
  "preco_min_usd": 9.08,
  "mediana_global_usd": 43.84,
  "preco_normalizado": 0.2071,
  "score": 5.0
}
```
Cálculo: 3.93 / 0.2071 = 18.97 → cap em 5.00

**Components do Merlot (score 2.83):**
```json
{
  "nota_wcf": 3.78,
  "nota_ajustada": 3.78,
  "preco_min_usd": 58.49,
  "preco_normalizado": 1.3342,
  "score": 2.83
}
```
Cálculo: 3.78 / 1.3342 = 2.83

### Pena Vermelha (TODOS os dados):

| Variante | ID | Vivino | WCF | WG Score | Preço | Reviews |
|----------|-----|--------|-----|----------|-------|---------|
| Branco | 1500419 | 3.90 | 3.89 | 3.89 | None | 486 |
| Rosé | 1487176 | 3.90 | 3.75 | 3.75 | None | 93 |
| Reserva Tinto | 1287027 | 3.90 | **3.71** | **3.71** | None | 141 |
| Tinto | 1225955 | 3.70 | 3.75 | 3.75 | None | 1486 |
| Colheita Selec. | 1488220 | 3.50 | 3.39 | 3.39 | None | 138 |

**O Reserva Tinto PERDEU 0.19 pontos** (3.90 → 3.71). É muito.
Nenhum Pena Vermelha tem preço no banco, então score = nota_wcf.
Nenhum micro-ajuste foi aplicado (todos 0).

### Outros exemplos de discrepância:

| Vinho | Vivino | WCF | Delta WCF | WG Score | Delta Score |
|-------|--------|-----|-----------|----------|-------------|
| Krug Vintage | 4.60 | 4.88 | +0.28 | 4.90 | +0.30 |
| Dom Ruinart Rosé | 4.50 | 4.58 | +0.08 | 4.60 | +0.10 |
| D.Eugenio Crianza | 3.60 | 3.65 | +0.05 | 3.65 | +0.05 |
| Amaral | 4.00 | 4.04 | +0.04 | 4.04 | +0.04 |
| Chaski Petit Verdot | 4.10 | 4.26 | +0.16 | 5.00 | +0.90 |
| Piedra Seca CS | 4.10 | 4.22 | +0.12 | 4.67 | +0.57 |

---

## A FÓRMULA DO SCORE (arquivo: `C:\winegod-app\scripts\calc_score.py`)

```python
# Micro-ajustes (max +0.05)
m_paridade = 0.02 if vinhos em 3+ países else 0
m_legado = 0.02 if reviews >= 500 AND wcf >= 4.0 else 0
m_capilaridade = 0.01 if vinho em 5+ lojas else 0
micro_total = min(m_paridade + m_legado + m_capilaridade, 0.05)

nota_ajustada = min(wcf + micro_total, 5.00)

# Custo-benefício
if preço disponível:
    preco_norm = preco_usd / mediana_global_usd  # mediana = $43.84
    score = min(nota_ajustada / preco_norm, 5.00)
else:
    score = nota_ajustada
```

**Problemas identificados:**
1. Vinhos baratos ($9) → preco_norm ~0.21 → score ~19 → cap 5.00
2. Vinhos caros ($65) → preco_norm ~1.48 → score = wcf/1.48 → nota REDUZIDA
3. A oscilação é de 2.4 pontos (5.0 vs 2.6) para vinhos de qualidade similar (~3.8)
4. Quando preço=NULL, score = nota_wcf (sem ajuste)

## A IMPORTAÇÃO DO WCF (arquivo: `C:\winegod-app\scripts\calc_wcf.py`)

```python
# Lê wcf_results.csv (gerado no repo winegod)
# Cada linha: nota_wcf, total_reviews_wcf, vinho_id
# Faz UPDATE wines SET nota_wcf = X WHERE vivino_id = Y
```

O cálculo real do WCF acontece no repo `C:\winegod\`. Você precisa encontrar:
- O script que gera `wcf_results.csv`
- A fórmula WCF usada
- Por que alguns vinhos sobem (Krug +0.28) e outros descem (Pena Vermelha -0.19)

---

## O QUE BACO MOSTRA AO USUÁRIO

O system prompt (`C:\winegod-app\backend\prompts\baco_system.py`) diz:
- Quando usuário pergunta "qual a nota?" → mostrar NOTA (vivino_rating ou nota_wcf)
- Quando pergunta "custo-benefício?" → mostrar winegod_score
- Nota verificada (100+ reviews): "4.18 estrelas"
- Nota estimada (0-99): "~3.85 estrelas" (com til)

**Evidências de teste:**
- Foto Pena Vermelha: Baco disse "3.9 estrelas" → usou vivino_rating (CORRETO)
- Foto She's Always: Baco disse "~3.96" → provavelmente nota_wcf

---

## O QUE VOCÊ DEVE INVESTIGAR

### Parte 1: Estudo estatístico da discrepância WCF vs Vivino
1. Qual a distribuição do delta (nota_wcf - vivino_rating) para TODOS os vinhos?
2. Quantos vinhos têm delta > 0.10? > 0.20? > 0.50?
3. Quantos vinhos têm delta < -0.10? < -0.20?
4. Há correlação entre delta e número de reviews?
5. Há correlação entre delta e faixa de preço?
6. Quais vinhos têm as maiores discrepâncias?
7. Como o WCF é calculado no repo `winegod`? A fórmula faz sentido?

### Parte 2: Estudo do winegod_score (custo-benefício)
1. Distribuição do winegod_score — quantos vinhos têm score 5.00? (provavelmente muitos vinhos baratos)
2. A fórmula nota/preço faz sentido? Ou deveria ser log(preço)?
3. A mediana de $43.84 é boa? Ou deveria ser por mercado/país?
4. O cap de 5.00 esconde vinhos excepcionais baratos (todos parecem 5.00)
5. A oscilação de 2.4 pontos é aceitável?

### Parte 3: O que Baco deve mostrar
1. Baco deveria mostrar vivino_rating puro (o que o usuário vê no Vivino)?
2. Ou nota_wcf (nossa nota recalculada)?
3. Como apresentar o winegod_score sem confundir com nota de qualidade?
4. Precisa de label claro ("Nota: X | Custo-benefício: Y")?

---

## QUERIES SQL PARA COMEÇAR

```sql
-- Distribuição do delta WCF vs Vivino
SELECT
  ROUND((nota_wcf - vivino_rating)::numeric, 1) as delta_bucket,
  COUNT(*) as qtd
FROM wines
WHERE nota_wcf IS NOT NULL AND vivino_rating IS NOT NULL AND vivino_rating > 0
GROUP BY delta_bucket
ORDER BY delta_bucket;

-- Top 20 maiores inflações (WCF > Vivino)
SELECT nome, vivino_rating, nota_wcf, (nota_wcf - vivino_rating) as delta,
       vivino_reviews, pais_nome
FROM wines
WHERE nota_wcf IS NOT NULL AND vivino_rating > 0
ORDER BY (nota_wcf - vivino_rating) DESC
LIMIT 20;

-- Top 20 maiores deflações (WCF < Vivino)
SELECT nome, vivino_rating, nota_wcf, (nota_wcf - vivino_rating) as delta,
       vivino_reviews, pais_nome
FROM wines
WHERE nota_wcf IS NOT NULL AND vivino_rating > 0
ORDER BY (nota_wcf - vivino_rating) ASC
LIMIT 20;

-- Distribuição do winegod_score
SELECT
  CASE
    WHEN winegod_score >= 4.9 THEN '5.0 (cap)'
    WHEN winegod_score >= 4.0 THEN '4.0-4.9'
    WHEN winegod_score >= 3.0 THEN '3.0-3.9'
    WHEN winegod_score >= 2.0 THEN '2.0-2.9'
    ELSE '<2.0'
  END as faixa,
  COUNT(*)
FROM wines WHERE winegod_score IS NOT NULL
GROUP BY faixa ORDER BY faixa;

-- Quantos vinhos com score 5.00 (baratos demais)
SELECT COUNT(*) FROM wines WHERE winegod_score = 5.00;
```

---

## ARQUIVOS QUE VOCÊ PRECISA LER

- `C:\winegod-app\scripts\calc_score.py` — fórmula completa do score
- `C:\winegod-app\scripts\calc_wcf.py` — como importa o WCF
- `C:\winegod-app\backend\prompts\baco_system.py` — como Baco apresenta notas
- `C:\winegod-app\backend\tools\search.py` — quais campos são retornados na busca
- `C:\winegod\` — procurar o gerador do wcf_results.csv (a fórmula WCF real)

---

## O QUE VOCÊ DEVE ENTREGAR

1. **Estudo estatístico** — distribuição dos deltas, outliers, correlações
2. **Diagnóstico da fórmula WCF** — por que infla/defla, se faz sentido
3. **Diagnóstico da fórmula custo-benefício** — problema do cap 5.00, oscilação brutal
4. **Proposta de ajustes** com prós/contras:
   - Cap máximo de delta WCF vs Vivino?
   - Mudar fórmula custo-benefício (log, raiz quadrada)?
   - Mediana por mercado em vez de global?
   - Separar claramente nota vs score na interface?
5. **Simulações** — como os ajustes propostos mudariam os exemplos concretos acima

---

## REGRAS

- NÃO implemente nada. Só estudo e proposta.
- NÃO faça commit ou push.
- NÃO delete dados do banco.
- Pode rodar queries SELECT à vontade.
- Use caminhos completos ao mencionar arquivos.
- Respostas em português, simples e diretas.
- O usuário NÃO é programador.
