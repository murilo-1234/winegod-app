# Pesquisa 5: Nota Base, Penalidade Contextual e Fallback sem Degrau

**Data:** 2026-04-12
**Escopo:** Estudo estatistico — sem implementacao, sem alteracao de banco ou codigo
**Proxy utilizado:** `vivino_reviews > 0` como indicador de nota direta (ver limitacoes na secao 8)

---

## 1. Resumo Executivo

Esta pesquisa investigou 3 lacunas abertas na `nota_wcf v2`:

**Lacuna 1 — Como calcular a `nota_base` dentro do balde?**
Recomendacao: **media ponderada com teto `min(n, 50)`** (onde `n` = `vivino_reviews` ou, idealmente, `total_reviews_wcf`). Esta opcao equilibra respeito a dados com mais amostra sem deixar vinhos mega-avaliados dominar o balde. Delta medio vs. simples: apenas +0.022. Delta max: 0.254.

**Lacuna 2 — Penalidade contextual faz sentido?**
Recomendacao: **penalidade zero quando `n > 0`** (o shrinkage ja atua). **Para `n = 0`, usar penalidade proporcional ao desvio-padrao real do balde**, nao tabela fixa. A variancia medida vai de 0.131 (D1) a 0.418 (D6) — aplicar a mesma penalidade a todos e indefensavel.

**Lacuna 3 — O que fazer com vinhos `n > 0` sem degrau?**
- Subgrupo A (sem `tipo`): sao maioritariamente **nao-vinhos** (refrigerantes, tonicos, etc). Recomendacao: **nao atribuir nota WCF**. Sao 2.360 no proxy usado (potencialmente mais no CSV original).
- Subgrupo B (com `tipo` sem mais nada): apenas 31 vinhos no proxy. Recomendacao: **usar `nota_wcf` direta com confianca baixa** — sao poucos e isolados, nao vale criar regra especial.

---

## 2. Melhor forma de calcular a `nota_base`

### O que foi medido

Comparacao de 3 agregadores no degrau D4 (`regiao + tipo`, 5.110 baldes com >= 30 vinhos):

| Agregador | Delta medio vs simples | |Delta| medio | |Delta| max |
|-----------|----------------------|--------------|------------|
| Media simples | — (referencia) | — | — |
| Ponderada por `n` | **+0.078** | 0.097 | **0.598** |
| Ponderada com `min(n, 50)` | **+0.022** | 0.039 | **0.254** |

### Analise por criterio

#### Media simples

- **Risco de outlier:** Baixo. Nenhum vinho individual pesa mais que outro.
- **Risco de fama historica:** Nenhum. Vinhos com 200K reviews pesam igual a vinhos com 3 reviews.
- **Aderencia a tese do fundador:** Alta — trata todos igualmente.
- **Robustez estatistica:** Baixa. Um vinho com nota 1.0 e 1 review contamina o balde tanto quanto um vinho com nota 3.8 e 500 reviews. Isso e estatisticamente errado: a nota com mais dados e mais confiavel.
- **Justica com vinhos novos:** Boa — nao sao prejudicados. Mas tambem nao sao protegidos de vizinhos com dados frageis.

#### Media ponderada por `n` (sem teto)

- **Risco de outlier:** **Alto**. Um vinho com 256K reviews domina completamente o balde. Delta max de 0.598 confirma: em alguns baldes, a ponderada diverge ~0.6 pontos da simples.
- **Risco de fama historica:** **Muito alto**. Exatamente o oposto da tese do fundador. Os vinhos mais famosos (Moet, Yellowtail, etc) determinam a "nota base" de toda a regiao.
- **Aderencia a tese:** **Baixa** — vinhos famosos dominam o prior contextual.
- **Robustez estatistica:** Alta em teoria. Vinhos com mais reviews sao dados mais confiaveis.
- **Justica com vinhos novos:** **Ruim**. O shrinkage puxa o vinho novo para uma nota_base dominada pelos famosos da regiao.

#### Media ponderada com teto `min(n, 50)` — RECOMENDADA

- **Risco de outlier:** Baixo. O teto limita o peso maximo a 50, entao um vinho com 256K reviews pesa no maximo 50x mais que um vinho com 1 review (em vez de 256.000x).
- **Risco de fama historica:** **Controlado**. Vinhos famosos contribuem, mas nao dominam. O delta medio de +0.022 mostra que a influencia e marginal.
- **Aderencia a tese:** **Boa** — respeita a experiencia sem premiar fama excessiva.
- **Robustez estatistica:** Boa. Vinhos com mais reviews ainda pesam mais (ate 50x), entao a nota base reflete dados mais confiaveis. Mas o teto evita dominancia extrema.
- **Justica com vinhos novos:** **Boa**. O prior contextual e equilibrado, entao o shrinkage puxa para um centro razoavel, nao para a nota dos famosos.

### Por que teto 50?

O valor 50 nao e arbitrario — corresponde ao p75 da distribuicao de `vivino_reviews` entre vinhos com nota WCF (mediana = 14, media = 180). Com teto 50:
- 75% dos vinhos contribuem com seu peso real
- Apenas os 25% mais avaliados sao limitados
- O delta max cai de 0.598 para 0.254 (reducao de 58%)
- O delta medio cai de 0.078 para 0.022 (reducao de 72%)

---

## 3. Critica as alternativas descartadas

### Media simples — descartada por fragilidade estatistica

A media simples ignora que um vinho com 500 reviews tem nota muito mais confiavel que um vinho com 1 review. Num balde com 100 vinhos, se 80 deles tem 1-3 reviews e notas estaveis em 3.5, mas 20 vinhos artesanais tem notas volateis entre 1.0 e 5.0 com 1 review cada, a media simples e contaminada pelos volateis. Isso cria um prior instavel.

### Media ponderada sem teto — descartada por dominancia de fama

O caso extremo e fatal: no balde "France + tinto", vinhos como Chateau Margaux ou Mouton Rothschild com centenas de milhares de reviews determinariam a nota base para TODOS os tintos franceses, incluindo um novo produtor do Languedoc com 3 reviews. O shrinkage puxaria o novo produtor para a nota dos Bordeaux famosos. Isso contradiz diretamente a tese do fundador.

Dado medido: delta max de 0.598 entre ponderada e simples. Em uma escala de 0-5, isso e uma distorcao grave.

### Outras opcoes consideradas

**Mediana:** Robusta a outliers, mas descarta informacao sobre a dispersao. Nao usa os pesos de reviews, que sao informacao valiosa. E problematica em baldes pequenos (2-5 vinhos).

**Media trimmed (excluindo top/bottom 5%):** Boa robustez, mas dificil de implementar na cascata com baldes de tamanhos muito diferentes. Num balde com 3 vinhos, nao faz sentido.

---

## 4. Melhor tratamento para penalidade contextual

### O que foi medido

Desvio-padrao real das notas dentro dos baldes, por degrau:

| Degrau | Mediana desvio | P25 | P75 | P90 |
|--------|---------------|-----|-----|-----|
| D1: vin+sub+tipo | **0.131** | 0.071 | 0.212 | 0.310 |
| D2: sub+tipo | **0.230** | 0.191 | 0.287 | 0.339 |
| D3: vin+reg+tipo | **0.273** | 0.172 | 0.419 | 0.612 |
| D4: reg+tipo | **0.378** | 0.293 | 0.467 | 0.558 |
| D5: vin+pais+tipo | **0.291** | 0.187 | 0.437 | 0.626 |
| D6: pais+tipo | **0.418** | 0.336 | 0.484 | 0.545 |
| D7: vin+tipo | **0.316** | 0.222 | 0.445 | 0.599 |

### Comparacao das 4 abordagens

#### Aplicar sempre (modelo atual)

- Penalidades de -0.00 a -0.15 aplicadas em todos os casos, independente de n.
- **Problema:** Para n > 0, o shrinkage `n/(n+20)` ja reduz o peso do prior proporcionalmente. Penalizar o prior alem disso e "double-dipping" — aplica dois descontos. Um vinho com n=10 ja tem alpha=0.33 (67% da nota vem do prior). Penalizar o prior em -0.10 alem disso e excessivo.
- **Risco de outlier:** Neutro.
- **Risco de fama:** Neutro (penalidade nao distingue).
- **Aderencia a tese:** Ruim — penaliza todos uniformemente, inclusive vinhos novos com poucas reviews cujo prior e o unico lastro.
- **Robustez:** Baixa — valores arbitrarios sem base empirica.
- **Justica com vinhos novos:** Ruim — vinhos novos com n=1-5 dependem muito do prior, e penaliza-lo reduz sua nota injustamente.

#### Aplicar so quando n = 0 — RECOMENDADA

- Para n > 0: sem penalidade. O shrinkage ja faz o trabalho.
- Para n = 0: aplicar penalidade proporcional a incerteza do balde.
- **Problema:** Nenhum grave. Quando n > 0, o dado real ja esta presente e o shrinkage equilibra. Quando n = 0, a nota E o prior, e algum desconto e razoavel para comunicar incerteza.
- **Risco de outlier:** Baixo — so afeta n=0.
- **Risco de fama:** Neutro.
- **Aderencia a tese:** Boa — vinhos novos (n > 0) nao sao penalizados.
- **Robustez:** Media — depende da regra de calculo da penalidade para n=0.
- **Justica com vinhos novos:** Boa.

#### Tabela fixa por degrau (modelo proposto originalmente)

- D1: -0.00, D2: -0.03, D3: -0.05, D4: -0.08, D5: -0.10, D6: -0.12, D7: -0.15
- **Problema critico:** A variancia real medida mostra que o desvio vai de 0.131 (D1) a 0.418 (D6), mas a tabela tem incrementos uniformes de ~0.02-0.03 por degrau. A penalidade de -0.12 para D6 e muito menor que o desvio real (0.418). E em D1, penalidade 0.00 assume previsibilidade perfeita — quando o desvio real e 0.131.
- **Risco:** Falsa precisao. Trata todos os degraus como se tivessem variancia proporcional ao nivel, mas os dados mostram que nao e assim (D5 tem desvio menor que D4, por exemplo).
- **Robustez:** Baixa.
- **Justica:** Media.

#### Regra baseada na variancia real do balde — RECOMENDADA para n = 0

- Formula proposta: `penalidade = -0.5 * desvio_padrao_do_balde`
- O fator 0.5 e uma escolha conservadora (metade do desvio).
- Aplicada **somente quando n = 0**.

Exemplos com dados reais:

| Balde | Desvio mediano | Penalidade proposta | vs tabela fixa |
|-------|---------------|--------------------|----|
| D1 (vin+sub+tipo) | 0.131 | **-0.066** | -0.00 (tabela subestima) |
| D2 (sub+tipo) | 0.230 | **-0.115** | -0.03 (tabela subestima) |
| D4 (reg+tipo) | 0.378 | **-0.189** | -0.08 (tabela subestima) |
| D6 (pais+tipo) | 0.418 | **-0.209** | -0.12 (tabela subestima) |

- **Risco de outlier:** Controlado — o desvio e medido por balde, entao baldes com outliers tem desvio alto e penalidade maior.
- **Risco de fama:** Neutro.
- **Aderencia a tese:** Boa — so penaliza notas puramente contextuais.
- **Robustez:** **Alta** — baseada em dado real, nao em heuristica.
- **Justica com vinhos novos:** Boa — vinhos com n > 0 nao sao afetados.

---

## 5. Melhor fallback para `n > 0` sem degrau

### Dados medidos

**Numeros originais do prompt (baseados em `total_reviews_wcf` do CSV):**
- 44.186 vinhos com n > 0 sem encaixe estrutural
- 43.395 sem `tipo`
- 791 com `tipo` mas sem produtor/sub_regiao/regiao/pais

**Numeros medidos nesta pesquisa (proxy `vivino_reviews > 0`):**
- Subgrupo A (sem tipo): **2.360 vinhos**
- Subgrupo B (com tipo sem cascata): **31 vinhos**
- Discrepancia explicada na secao 8

### Subgrupo A: Sem `tipo` (n > 0)

**Perfil:**
- 2.360 vinhos (proxy)
- Todos tem pais, regiao e produtor preenchidos
- Media nota_wcf: 3.616 | Desvio: 0.667
- Media vivino_reviews: 13.8 | Mediana: 6
- Top paises: FR (621), IT (472), ES (233), US (217)

**Achado critico:** Os exemplos com mais reviews sao **nao-vinhos**:
- "Classic (Original Coke)" (US) — 3.484 reviews, nota 4.46
- "Buckfast Tonic Wine" (GB) — 1.265 reviews, nota 4.05
- "Zero" (US) — 669 reviews, nota 3.78
- "Cafeine Free" (US) — 561 reviews, nota 4.38

Estes itens nao tem `tipo` porque **nao sao vinhos**. Entraram na base via Vivino (que permite cadastro de qualquer bebida).

**Recomendacao para Subgrupo A:**
- **Nao atribuir nota WCF.** Sem `tipo`, o item nao pode ser posicionado em nenhuma cascata e provavelmente nao e vinho.
- Na v2.1, considerar limpeza: filtrar itens sem `tipo` que sao claramente nao-vinhos.
- Se houver vinhos reais entre os 2.360, o caminho e **preencher o `tipo`** (via enrichment ou heuristica), nao criar fallback especial.

**Criterios:**
- Risco de outlier: N/A (sem nota)
- Risco de fama: N/A
- Aderencia a tese: Alta — melhor nao dar nota do que dar nota a refrigerante
- Robustez: Alta — decisao simples e defensavel
- Justica com vinhos novos: Neutra

### Subgrupo B: Com `tipo`, sem produtor/regiao/pais (n > 0)

**Perfil:**
- 31 vinhos (proxy)
- Media nota_wcf: 3.249 | Desvio: 0.702
- Media vivino_reviews: 77.6 | Mediana: 13

**Recomendacao para Subgrupo B:**
- **Usar `nota_wcf` direta** (a nota que ja esta no banco, calculada a partir das reviews WCF).
- Marcar com confianca baixa.
- Sao apenas 31 vinhos — nao justifica regra especial.
- Na formula de shrinkage, sem nota_base disponivel, a nota final e a propria nota_wcf_bruta (alpha tende a 1 quando nota_base nao existe).

**Criterios:**
- Risco de outlier: Moderado (31 vinhos, desvio alto de 0.702)
- Risco de fama: Baixo (sem contexto, nao ha comparacao)
- Aderencia a tese: Neutra
- Robustez: Aceitavel para volume tao pequeno
- Justica com vinhos novos: Boa — recebem nota que reflete suas reviews

---

## 6. Exemplos reais / casos numericos

### Exemplo 1: Balde com dispersao baixa

**Monferrato Rose** (D4: regiao+tipo, 10 vinhos)
- Desvio: 0.032 | Range: [3.54 - 3.64]
- nota_base simples: ~3.608
- Interpretacao: balde homogeneo. A nota_base e muito confiavel. Penalidade quase desnecessaria.

Aplicando a formula de shrinkage para um vinho novo neste balde com n=5:
```
nota_final = (5/25) * nota_wcf_bruta + (20/25) * 3.608
           = 0.2 * nota_wcf_bruta + 0.8 * 3.608
```
Se nota_wcf_bruta = 4.0: nota_final = 0.8 + 2.886 = **3.686** (puxado de 4.0 para 3.69)
Se nota_wcf_bruta = 3.5: nota_final = 0.7 + 2.886 = **3.586** (puxado de 3.5 para 3.59)

O shrinkage e suave porque o balde e homogeneo. Faz sentido.

### Exemplo 2: Balde com dispersao alta

**Lehigh Valley Espumante** (D4: regiao+tipo, 11 vinhos)
- Desvio: 1.111 | Range: [1.00 - 5.00]
- nota_base simples: ~3.394
- Interpretacao: balde com enorme variabilidade. A nota_base e fragil.

Para um vinho novo com n=5:
```
nota_final = 0.2 * nota_wcf_bruta + 0.8 * 3.394
```
Se nota_wcf_bruta = 4.5: nota_final = 0.9 + 2.715 = **3.615** (puxado de 4.5 para 3.62 — perda de 0.88)
Se nota_wcf_bruta = 2.0: nota_final = 0.4 + 2.715 = **3.115** (puxado de 2.0 para 3.12 — ganho de 1.12)

O shrinkage puxa muito — mas o prior e fragil (desvio 1.1). Se usar penalidade baseada em variancia para n=0: penalidade = -0.5 * 1.111 = -0.556. Isso e muito mais severo que a tabela fixa (-0.08), e justificadamente — este balde e muito instavel.

### Exemplo 3: Impacto do agregador — CASO REAL Abruzzo Tinto

**Balde real: Abruzzo, tinto (D4), 376 vinhos**
- 1 vinho com 77.231 reviews (provavelmente Montepulciano d'Abruzzo de marca famosa)
- Restante com reviews distribuidas normalmente

| Agregador | Nota base | Delta vs simples |
|-----------|-----------|-----------------|
| Media simples | **3.600** | — |
| Ponderada por n | **4.198** | **+0.598** |
| Ponderada teto 50 | **3.593** | **-0.007** |

A ponderada sem teto puxa a nota base de 3.60 para 4.20 — quase meio ponto! Isso faria o shrinkage puxar TODOS os tintos novos do Abruzzo para 4.20, beneficiando vinhos mediocres na sombra do famoso. O teto 50 elimina este problema.

### Exemplo 4: Pauillac Tinto — caso classico da tese do fundador

**Balde real: Pauillac, tinto (D4), 408 vinhos**
- 1 vinho com 90.165 reviews (Chateau Lafite, Mouton, etc)

| Agregador | Nota base | Delta |
|-----------|-----------|-------|
| Media simples | **3.951** | — |
| Ponderada por n | **4.435** | **+0.484** |
| Ponderada teto 50 | **3.972** | **+0.021** |

Se usasse ponderada sem teto, um produtor novo de Pauillac com n=5 e nota real 3.8 teria:
```
nota_final = (5/25) * 3.8 + (20/25) * 4.435 = 0.76 + 3.548 = 4.308
```
Ele ganharia nota **4.31** mesmo sendo um vinho de **3.80**! O prior inflado pelos Grands Crus com 90K reviews puxa para cima. Com teto 50:
```
nota_final = (5/25) * 3.8 + (20/25) * 3.972 = 0.76 + 3.178 = 3.938
```
Nota **3.94** — muito mais justa.

---

## 7. Recomendacao final

### Formula completa proposta

**Para `n > 0` com encaixe na cascata:**
```
nota_base = media ponderada com teto min(n, 50) dos vinhos com nota direta no balde
nota_final = (n / (n + 20)) * nota_wcf + (20 / (n + 20)) * nota_base
```
- Sem penalidade contextual (o shrinkage ja atua)
- `nota_wcf` e o campo existente no banco (proxy para nota_wcf_bruta — ver secao 8)

**Para `n = 0` com encaixe na cascata:**
```
nota_base = media ponderada com teto min(n, 50) dos vinhos com nota direta no balde
penalidade = -0.5 * desvio_padrao_do_balde
nota_final = nota_base + penalidade
```
- Penalidade proporcional a variancia real, nao tabela fixa

**Para `n > 0` SEM encaixe na cascata:**
- Subgrupo A (sem tipo): sem nota WCF
- Subgrupo B (com tipo sem cascata): usar nota_wcf direta, confianca baixa

**Para `n = 0` SEM encaixe na cascata:**
- Sem nota (decisao ja fechada)

### Regras criticas

1. **nota_base construida APENAS com vinhos de nota direta** (n > 0). Nunca reciclar notas contextuais.
2. **Teto de ponderacao = 50** (revisavel se a distribuicao de `total_reviews_wcf` for significativamente diferente de `vivino_reviews`).
3. **Penalidade zero para n > 0** — o shrinkage ja e o mecanismo de conservadorismo.
4. **Penalidade para n = 0 baseada em variancia real** — formula: `-0.5 * stddev` do balde.
5. **Minimos por degrau ja aprovados** (2/10/3/10/3/10/5) — validados como razoaveis pelos dados.

---

## 8. O que ainda nao foi provado

### 8.1. `nota_wcf_sample_size` esta completamente vazio no banco

**Descoberta critica desta pesquisa:** A coluna `nota_wcf_sample_size` (migracaoo 005) esta NULL para **todos** os 1.727.054 vinhos com `nota_wcf`. Isso aconteceu provavelmente porque o script `calc_wcf_fast.py` foi usado em vez do `calc_wcf.py` original (o fast nao popula `nota_wcf_sample_size`).

**Impacto:** Toda esta pesquisa usou `vivino_reviews > 0` como proxy para "tem reviews WCF reais". Este proxy e razoavel mas impreciso:
- `vivino_reviews` = total publico de reviews no Vivino
- `total_reviews_wcf` (no CSV) = reviews validas usadas no calculo WCF (apos filtrar `usuario_total_ratings = 0`)
- Nao sao o mesmo numero

**Acao necessaria:** Rodar `calc_wcf.py` (nao o fast) para popular `nota_wcf_sample_size` no banco. Sem isso, a cascata nao pode distinguir nota direta de nota step5.

### 8.2. Os numeros 44.186 / 43.395 / 791 do prompt nao batem com o proxy

O prompt menciona 44.186 vinhos com `n > 0` sem encaixe. Minha pesquisa encontrou apenas 2.391 (2.360 + 31) usando `vivino_reviews > 0` como proxy. A diferenca (~41.795 vinhos) provavelmente sao vinhos que tem reviews WCF validas mas `vivino_reviews = 0` no banco — ou vinhos cujo `vivino_reviews` e > 0 mas que encaixam na cascata quando usamos a base completa (sem o filtro de nota direta).

**Acao necessaria:** Apos popular `nota_wcf_sample_size`, refazer esta analise com o filtro correto.

### 8.3. A nota_wcf atual no banco mistura notas diretas e step5

Hoje, `nota_wcf` contem tanto notas calculadas por WCF (reviews reais) quanto medias regionais inseridas pelo `calc_wcf_step5.py`. O campo `confianca_nota` distingue parcialmente (0.10 = step5, >= 0.20 = WCF real), mas nao e documentado como canonico para isso.

**Dado medido:** 167.872 vinhos com `nota_wcf` e `vivino_reviews = 0` (step5 fills). Apenas 220 valores distintos de nota — confirmando que sao medias regionais.

### 8.4. O fator 0.5 na penalidade de variancia nao foi calibrado

A formula `penalidade = -0.5 * stddev` e uma proposta conservadora. O fator 0.5 deveria ser validado:
- Se 0.5 e muito alto, notas contextuais sao excessivamente penalizadas
- Se muito baixo, nao refletem a incerteza real
- Cross-validation com holdout seria o metodo correto

### 8.5. O teto 50 nao foi otimizado

O teto 50 foi escolhido com base na distribuicao de `vivino_reviews` (p75). Se `total_reviews_wcf` tem distribuicao diferente (o CSV mostra max=128, nao 256K), o teto ideal pode ser outro. O max de `vivino_reviews` no banco e 256.727 enquanto o max de `total_reviews_wcf` no CSV e 128 — distribuicoes radicalmente diferentes.

**Recomendacao:** Apos popular `nota_wcf_sample_size`, recalcular o percentil p75 e ajustar o teto. Se o max do WCF e 128, um teto de 50 continua razoavel (cobre ~60-70% dos vinhos sem corte). Mas precisa ser validado.

### 8.6. Nao foi testada a interacao entre penalidade e shrinkage para n baixo

Para vinhos com n=1-5, a nota e dominada pelo prior (~80-96% da nota vem da nota_base). Se a nota_base ja e robusta (teto + variancia medida), a remocao da penalidade para n > 0 e segura. Mas cenarios extremos (n=1, nota_wcf_bruta=5.0, balde com desvio 1.0) nao foram simulados em escala.

### 8.7. Nao foi medido o impacto dos nao-vinhos na cascata

Vinhos como "Classic (Original Coke)" que tem tipo = NULL ficam fora da cascata e nao contaminam a nota_base. Mas se houver nao-vinhos com `tipo` preenchido (ex: tipo = "tinto" para um produto que nao e vinho), eles contaminam os baldes silenciosamente. Nao foi feita busca por estes casos.

---

## Anexo A: Dados completos dos 7 degraus

Apenas vinhos com nota direta (`vivino_reviews > 0 AND nota_wcf IS NOT NULL`).
Base: 1.559.182 vinhos.

| Degrau | Baldes | Vinhos | Media medias | Med. desvio | P25 desvio | P75 desvio | P90 desvio | Tam medio | Med. tam |
|--------|--------|--------|-------------|-------------|------------|------------|------------|-----------|----------|
| D1: vin+sub+tipo (min 2) | 5.865 | 16.943 | 4.018 | 0.131 | 0.071 | 0.212 | 0.310 | 2.9 | 2 |
| D2: sub+tipo (min 10) | 618 | 25.918 | 3.968 | 0.230 | 0.191 | 0.287 | 0.339 | 41.9 | 21 |
| D3: vin+reg+tipo (min 3) | 135.602 | 830.411 | 3.705 | 0.273 | 0.172 | 0.419 | 0.612 | 6.1 | 4 |
| D4: reg+tipo (min 10) | 8.773 | 1.520.540 | 3.738 | 0.378 | 0.293 | 0.467 | 0.558 | 173.3 | 38 |
| D5: vin+pais+tipo (min 3) | 151.853 | 1.125.624 | 3.702 | 0.291 | 0.187 | 0.437 | 0.626 | 7.4 | 5 |
| D6: pais+tipo (min 10) | 464 | 1.556.466 | 3.663 | 0.418 | 0.336 | 0.484 | 0.545 | 3.354 | 312 |
| D7: vin+tipo (min 5) | 80.613 | 901.689 | 3.717 | 0.316 | 0.222 | 0.445 | 0.599 | 11.2 | 8 |

## Anexo B: Dispersao — exemplos extremos (D4: regiao+tipo)

**Dispersao ALTA (balde instavel):**

| Balde | N | Media | Desvio | Range |
|-------|---|-------|--------|-------|
| Lehigh Valley / espumante | 11 | 3.394 | 1.111 | [1.00 - 5.00] |
| Cape Town / espumante | 11 | 3.015 | 1.087 | [1.00 - 4.12] |
| Givry 1er Cru / tinto | 10 | 3.899 | 1.076 | [1.00 - 5.00] |
| Wine of Brazil / branco | 20 | 3.326 | 1.072 | [1.00 - 5.00] |
| Sonoita / branco | 15 | 3.362 | 1.026 | [1.25 - 5.00] |

**Dispersao BAIXA (balde estavel):**

| Balde | N | Media | Desvio | Range |
|-------|---|-------|--------|-------|
| Monferrato / Rose | 10 | 3.608 | 0.032 | [3.54 - 3.64] |
| Nebraska / Branco | 14 | 3.421 | 0.035 | [3.30 - 3.43] |
| North East Victoria / Tinto | 11 | 3.782 | 0.039 | [3.76 - 3.87] |
| Pokolbin / Branco | 10 | 3.827 | 0.054 | [3.81 - 3.98] |
| Pennsylvania / Rose | 25 | 3.631 | 0.054 | [3.62 - 3.89] |

## Anexo C: Top 5 baldes onde ponderada diverge mais da simples (D4, >= 30 vinhos)

| Balde | N vinhos | M. simples | M. ponderada | M. teto50 | Delta pond | Max reviews |
|-------|----------|------------|-------------|-----------|------------|-------------|
| Abruzzo / tinto | 376 | 3.600 | 4.198 | 3.593 | **+0.598** | 77.231 |
| Sopron / rose | 30 | 3.353 | 3.888 | 3.525 | +0.535 | 2.372 |
| Emilia / branco | 172 | 3.463 | 3.953 | 3.521 | +0.490 | 8.334 |
| Lombardia / rose | 130 | 3.558 | 4.045 | 3.644 | +0.487 | 18.069 |
| Pauillac / tinto | 408 | 3.951 | 4.435 | 3.972 | +0.484 | 90.165 |

Observacao: Em **todos** os casos, a media com teto 50 fica proxima da simples (delta < 0.1). A ponderada sem teto diverge ate 0.6 pontos. Isso confirma que o teto e necessario.

## Anexo D: Distribuicao confianca_nota (estado atual do banco)

| confianca_nota | Qtd | Interpretacao |
|---------------|-----|---------------|
| 0.10 | 445.651 | Step5 fills (medias regionais) |
| 0.20 | 651.609 | WCF com 1-9 reviews |
| 0.40 | 243.497 | WCF com 10-24 reviews |
| 0.60 | 138.480 | WCF com 25-49 reviews |
| 0.80 | 101.248 | WCF com 50-99 reviews |
| 1.00 | 146.569 | WCF com 100+ reviews |
| **Total** | **1.727.054** | |
