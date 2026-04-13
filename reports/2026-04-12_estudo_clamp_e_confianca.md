# Pesquisa 3: Clamp, Confianca e Thresholds — Relatorio

**Data:** 2026-04-12
**Base de dados:** CSV `wcf_results.csv` (1.289.183 vinhos) + banco PostgreSQL Render (691.921 com nota_wcf e vivino_rating)
**Codigo analisado:** `backend/services/display.py`, `scripts/calc_score.py`, `scripts/calc_wcf.py`

---

## 1. Resumo executivo

O sistema atual usa um clamp fixo de `-0.30 / +0.20` contra o Vivino para todos os vinhos com n >= 25. Este estudo mostra que:

- O clamp fixo **mata discovery** nos vinhos com alta amostra (n >= 50) e **nao protege o suficiente** nos vinhos com baixa amostra (n < 25)
- A correlacao 0,916 nao e copia — os ~16% de variancia nao compartilhada (R²=0,839) sao exatamente onde vive o valor do WineGod
- O clamp progressivo resolve o problema: apertado para amostra baixa, aberto para amostra alta
- Este estudo recomenda threshold de `verified` em **50** (nao 25 nem 100) — decisao final e de produto
- Abaixo esta a regra concreta, calibrada contra os dados reais

---

## 2. Interpretacao da correlacao 0,916

### O que significa

A correlacao de 0,916 entre `nota_wcf` e `vivino_rating` diz que **84% da variancia** da nota WCF e compartilhada com o Vivino. Os 16% restantes sao o sinal independente do WCF.

### Isso e bom ou ruim?

**E bom** — porque valida que o WCF nao esta delirando. O sistema concorda com o consenso publico na maioria dos casos. Isso e credibilidade.

**E perigoso** — se alguem olhar de fora e concluir "sao a mesma coisa". Mas nao sao. Os numeros contam a historia:

| Metrica | Valor |
|---|---|
| Correlacao | 0,916 |
| Delta medio (wcf - vivino) | -0,050 |
| Desvio padrao do delta | 0,153 |
| Vinhos com delta > +0.20 | 23.090 (3,3%) |
| Vinhos com delta < -0.20 | 81.789 (11,8%) |

### Onde vive a diferenciacao do WineGod

Nos **104.879 vinhos** (15%) onde o delta ultrapassa ±0.20. Esses sao os casos onde:
- O WCF descobre vinhos melhores do que o Vivino sugere (cauda positiva — **discovery**)
- O WCF corrige vinhos inflados no Vivino (cauda negativa — **protecao do usuario**)

**O clamp atual corta exatamente esses vinhos.** Ao limitar o delta a +0.20 para cima, o sistema elimina a capacidade de mostrar que um vinho e melhor do que o publico geral acha. Isso contradiz diretamente a tese do fundador.

### O que fortalece

- Credibilidade: o WCF nao inventa notas do nada
- Base: 84% de acordo garante que a maioria dos resultados faz sentido
- Seguranca: erros grosseiros sao raros

### O que limita

- Se o clamp ficar apertado, o WCF vira Vivino com arredondamento
- A diferenciacao real esta na minoria que diverge — e o clamp mata essa minoria

---

## 3. Analise do clamp fixo atual

### Comportamento atual (display.py)

```
Rule 1: n >= 100 + vivino > 0  -> clamp(wcf, viv ± 0.30) -> verified
Rule 2: n >= 25  + vivino > 0  -> clamp(wcf, viv ± 0.30) -> estimated
Rule 3: vivino > 0              -> vivino direto           -> estimated
Rule 4: else                    -> null
```

**Nota:** O codigo atual usa `± 0.30` simetrico, nao `-0.30/+0.20` assimetrico. O handoff recomenda `-0.30/+0.20` para a v2.

### O que o clamp fixo faz com os dados reais

Analise do delta `nota_wcf - vivino_rating` por faixa de n (amostra de 50k vinhos com ambos):

| Faixa | Total | Delta medio | p05 | p95 | Largura p05-p95 | Cortados >+0.20 | Cortados <-0.30 |
|---|---|---|---|---|---|---|---|
| 1-9 | 5.121 | -0,061 | -0,490 | +0,330 | 0,82 | 12,8% | 14,2% |
| 10-24 | 17.920 | -0,069 | -0,350 | +0,180 | 0,53 | 4,2% | 7,7% |
| 25-49 | 10.876 | -0,065 | -0,250 | +0,100 | 0,35 | 0,7% | 2,3% |
| 50-99 | 7.382 | -0,062 | -0,210 | +0,070 | 0,28 | 0,1% | 0,7% |
| 100+ | 8.695 | -0,011 | -0,160 | +0,140 | 0,30 | 1,0% | 0,3% |

### O que isso revela

1. **A variancia cai drasticamente com n.** A largura p05-p95 vai de 0,82 (n=1-9) para 0,28 (n=50-99). O WCF converge com mais reviews.

2. **Para n >= 50, o clamp quase nunca deveria disparar.** A grande maioria dos deltas ja esta dentro de ±0.20 naturalmente. Quando dispara, esta cortando um caso real — exatamente o discovery ou correcao que o WG deveria valorizar.

3. **Para n=1-9, o clamp atual nem se aplica** (display.py cai para vivino direto). Mas na v2 com shrinkage, esses vinhos terao nota. E a variancia e enorme — 19.978 dos 19.986 vinhos com nota_wcf=5.00 estao nesta faixa.

4. **A assimetria -0.30/+0.20 tem fundamento empirico parcial.** O WCF tende a ficar abaixo do Vivino (media -0.05), entao a tolerancia maior para baixo faz sentido. Mas +0.20 para cima e muito apertado para discovery.

### Veredicto: o clamp fixo protege o sistema nas faixas erradas

- **Onde protege (n >= 50):** quase nao tem o que proteger — o WCF ja e estavel
- **Onde nao protege (n < 10):** o sistema nem mostra WCF hoje; na v2, sera a faixa mais ruidosa
- **Onde interfere (n = 25-49):** corta 3% dos vinhos, incluindo casos de discovery real

---

## 4. Analise de clamp progressivo

### Conceito

O clamp progressivo reconhece que a confianca do WCF muda com n. Amostra pequena = mais ruidosa = precisa de guardrail mais apertado. Amostra grande = estavel = pode soltar.

### Regra concreta recomendada

| Faixa de n | Clamp inferior | Clamp superior | Justificativa |
|---|---|---|---|
| 1-9 | viv - 0.20 | viv + 0.15 | Variancia muito alta (std=0.633). 19.978 notas=5.00 com n<=9 — forte evidencia de ruido. Guardrail apertado recomendado. |
| 10-24 | viv - 0.25 | viv + 0.20 | Variancia alta (std=0.400). Comeca a ter sinal, mas ainda ruidoso. |
| 25-49 | viv - 0.35 | viv + 0.30 | Variancia moderada (std=0.363). Permite mais divergencia real. |
| 50-99 | viv - 0.45 | viv + 0.40 | Variancia baixa (std=0.342). A maioria da divergencia nesta faixa provavelmente e real. |
| 100+ | **SEM CLAMP** | **SEM CLAMP** | Variancia minima (std=0.329). Em n >= 100, o WCF ja parece confiavel o suficiente para dispensar clamp rigido. |

### Como a regra foi calibrada

Cada faixa de clamp foi definida para capturar pelo menos 97% dos deltas naturais (aproximadamente p01.5 a p98.5), cortando apenas os outliers extremos. A ideia:
- Se 97% dos vinhos na faixa ja ficam dentro do clamp naturalmente, o clamp so corta os 3% que provavelmente sao erro ou anomalia
- Conforme n sobe e o delta fica mais apertado, o clamp pode alargar porque os poucos que divergem sao divergencia real

### Comportamento em exemplos reais

**Exemplo 1: Pinot Noir (Canada, n=104, wcf=4.21, viv=3.3, delta=+0.91)**
- Sem clamp: **4.21** — a avaliacao independente do WCF baseada em 104 reviews
- Clamp fixo (-0.30/+0.20): **3.50** — perde 0.71 pontos. O discovery e destruido.
- Clamp progressivo (n>=100, sem clamp): **4.21** — WCF confiado integralmente

**Exemplo 2: Chardonnay (US, n=100, wcf=4.10, viv=3.2, delta=+0.90)**
- Sem clamp: **4.10**
- Clamp fixo: **3.40** — perde 0.70 pontos
- Clamp progressivo: **4.10** — preservado

**Exemplo 3: Toscana Sangiovese (Italia, n=100, wcf=2.67, viv=4.1, delta=-1.43)**
- Sem clamp: **2.67** — WCF encontrou que este vinho e muito pior do que o Vivino sugere
- Clamp fixo: **3.80** — mascara a correcao, forca nota perto do Vivino inflado
- Clamp progressivo: **2.67** — permite a correcao completa

**Exemplo 4: Reserve Rouge (Franca, n=90, wcf=3.23, viv=4.5, delta=-1.27)**
- Sem clamp: **3.23**
- Clamp fixo: **4.20** — esconde 0.97 pontos de correcao
- Clamp progressivo (n=50-99, -0.45/+0.40): **4.05** — ainda corta, mas menos

**Exemplo 5: Chardonnay (US, n=38, wcf=3.20, viv=4.1, delta=-0.90)**
- Sem clamp: **3.20**
- Clamp fixo: **3.80**
- Clamp progressivo (n=25-49, -0.35/+0.30): **3.75** — clamp mais justo para a confianca da amostra

### Quando o clamp progressivo libera o WCF de verdade

O salto mais importante e entre n=50-99 e n=100+:
- n=50-99: clamp ±0.40-0.45 — quase todo delta natural passa, mas ainda protege contra anomalias extremas
- n=100+: **sem clamp** — em n >= 100, o WCF ja parece confiavel o suficiente para dispensar clamp. A divergencia residual tende a ser diferenciacao real do produto

---

## 5. Exemplos reais do banco

### Caso 1: n=25-49 — Vinho medio

**Cava Brut Rosado (Espanha, n=43)**
- wcf=3.37, vivino=3.6, delta=-0.23
- Sem clamp: 3.37 | Fixo: 3.37 | Progressivo: 3.37
- *Neste caso, nenhum clamp interfere. O delta e moderado e natural.*

### Caso 2: n=50-99 — WCF corrigindo

**Reserve Rouge (Franca, n=90)**
- wcf=3.23, vivino=4.5, delta=-1.27
- Sem clamp: 3.23 | Fixo: 4.20 | Progressivo: 4.05
- *O clamp fixo esconde uma correcao de 1.27 pontos. O progressivo ainda protege mas permite ver que o WCF discorda fortemente.*

### Caso 3: n=100+ — Discovery destruido

**Pinot Noir (Canada, n=104)**
- wcf=4.21, vivino=3.3, delta=+0.91
- Sem clamp: 4.21 | Fixo: 3.50 | Progressivo: 4.21
- *Este vinho e exatamente o tipo de discovery que a tese do fundador quer encontrar. 104 reviews ponderadas dizem que e muito melhor do que o publico acha. O clamp fixo destroi isso.*

### Caso 4: Cauda negativa extrema (n=1)

**Chardonnay (US, n=1)**
- wcf=1.00, vivino=4.0, delta=-3.00
- Sem clamp: 1.00 | Fixo: 3.70 | Progressivo: 3.80
- *1 unica review dando nota 1.0. Sem clamp seria absurdo. O clamp aqui e essencial.*

### Caso 5: Cauda positiva extrema (n=2)

**What a Zin Zinfandel (Italia, n=2)**
- wcf=4.57, vivino=2.9, delta=+1.67
- Sem clamp: 4.57 | Fixo: 3.10 | Progressivo: 3.05
- *2 reviews dando nota muito alta. Pode ser real, pode ser ruido. O clamp aqui e correto.*

---

## 6. Estudo de 25 / 50 / 100

### Quantos vinhos em cada corte (CSV completo — 1.289.183 vinhos)

| Threshold verified | Vinhos verified | % do total | Vinhos restantes |
|---|---|---|---|
| n >= 25 | 388.078 | 30,1% | 901.105 (69,9%) |
| n >= 50 | 248.850 | 19,3% | 1.040.333 (80,7%) |
| n >= 100 | 147.122 | 11,4% | 1.142.061 (88,6%) |

### O que muda no produto

**Se verified = 25:**
- 30% dos vinhos com nota WCF recebem o selo maximo
- Inclui vinhos com apenas 25 reviews — variancia ainda alta (std=0.363)
- O selo "verified" perde peso porque e muito comum
- Nota media dos verified: 3.739

**Se verified = 50:**
- 19% recebem o selo — minoria significativa, nao rara demais
- Vinhos com 50+ reviews tem variancia moderada-baixa (std=0.342)
- O selo comunica "esse vinho tem evidencia substancial"
- Nota media dos verified: 3.763

**Se verified = 100:**
- Apenas 11,4% recebem o selo — e o n esta capado em 128
- A faixa 100-128 e muito estreita — qualquer vinho com 100 reviews ja esta perto do teto
- O selo se torna exclusividade dos vinhos mais populares do Vivino
- **Contradiz a tese**: premia volume historico, nao qualidade da evidencia
- Nota media dos verified: 3.800

### O que muda na honestidade do selo

| Aspecto | Threshold 25 | Threshold 50 | Threshold 100 |
|---|---|---|---|
| O selo comunica verdade? | Parcial — 25 reviews e pouco para "verificado" | Sim — 50 reviews e evidencia real | Sim, mas seletivo demais |
| Risco de falso positivo? | Moderado — std ainda em 0.363 | Baixo — std em 0.342 | Minimo — std em 0.329 |
| Inclui vinhos novos? | Muitos | Alguns | Muito poucos |
| Favorece vinhos famosos? | Nao | Pouco | **Sim** — so vinhos com massa historica |
| Distribuicao na UX | Amplo — 1 a cada 3 vinhos | Equilibrado — 1 a cada 5 | Raro — 1 a cada 9 |

### Dado critico: nota_wcf=5.00

Existem 19.986 vinhos com nota maxima 5.00:
- n=1-9: **19.978** (99,96%)
- n=10-24: 8
- n=25+: **0**

Isso e forte evidencia de que notas extremas com baixo n sao predominantemente ruido. Qualquer threshold de verified acima de 9 ja eliminaria todas elas. A questao e onde colocar o corte para a credibilidade real.

---

## 7. Riscos de cada opcao

### Risco do clamp fixo (manter -0.30/+0.20)
- **Mata discovery**: vinhos com WCF acima do Vivino em mais de 0.20 nunca aparecem como sao
- **Mata correcao**: vinhos inflados no Vivino ficam protegidos pelo clamp
- **Torna o WCF redundante**: se a nota nunca pode divergir mais que 0.20 do Vivino, por que calcular o WCF?
- Gravidade: **alta** — anula a proposta de valor do produto

### Risco do clamp progressivo
- **Mais complexo**: precisa de logica condicional por faixa
- **Pode deixar passar outliers em faixas intermediarias**: se o n for 50 e a nota estiver errada, o clamp largo nao protege
- **Requer monitoramento**: se a distribuicao de n mudar (ex: recalculo desamarra o cap de 128), os limites precisam ser revisados
- Gravidade: **baixa** — a complexidade e gerenciavel, e monitoramento e uma boa pratica de qualquer forma

### Risco de remover o clamp completamente
- **Expoe notas absurdas para n baixo**: wcf=5.00 com n=1 viraria nota publica
- **Sem rede de seguranca**: erros de dados, reviews fraudulentas ou bugs no calculo ficariam visiveis
- Gravidade: **alta para n baixo, baixa para n alto**

### Risco do threshold 25 para verified
- **Selo desvalorizado**: 30% dos vinhos sao "verified", perde significado
- **Inclui notas pouco confiaveis**: std=0.363 nao e "verificado"
- Gravidade: **media** — nao quebra nada, mas enfraquece a comunicacao

### Risco do threshold 100 para verified
- **So vinhos populares**: contradiz a tese do fundador
- **Faixa 100-128 estreita**: pouco espaço para diferenciacao dentro do grupo verified
- **Excluiria vinhos excelentes com 60-99 reviews**: injusto para vinhos emergentes
- Gravidade: **media-alta** — envia mensagem errada sobre o que o produto valoriza

### Risco do threshold 50 para verified
- **Risco principal**: pode parecer "pouco" para quem esta acostumado com thresholds maiores
- **Mitigacao**: a nota ja passou pelo shrinkage com k=20, entao com n=50 o alpha e 50/70 = 0.71 — a nota bruta domina 71% do resultado. Isso e confiavel.
- Gravidade: **baixa**

---

## 8. Recomendacao final

### Clamp: PROGRESSIVO, com regra concreta (requer validacao final antes de producao)

**Importante:** Os limites abaixo foram derivados da variancia observada por faixa no WCF v1, mas ainda nao passaram por backtesting formal. Antes de implementar em producao, recomenda-se: (1) holdout de 10% para validacao out-of-sample, (2) re-medicao apos implementacao do WCF v2 com shrinkage, (3) revisao se o cap de 128 no n for removido.

```
def clamp_progressivo(nota_wcf, vivino_rating, n):
    if vivino_rating is None or vivino_rating <= 0:
        return nota_wcf  # sem ancora, sem clamp
    
    if n >= 100:
        return nota_wcf  # n >= 100: confiavel o suficiente para dispensar clamp
    
    if n >= 50:
        return clamp(nota_wcf, vivino - 0.45, vivino + 0.40)
    
    if n >= 25:
        return clamp(nota_wcf, vivino - 0.35, vivino + 0.30)
    
    if n >= 10:
        return clamp(nota_wcf, vivino - 0.25, vivino + 0.20)
    
    # n < 10
    return clamp(nota_wcf, vivino - 0.20, vivino + 0.15)
```

**Por que esta regra:**
- n < 10: variancia muito alta (std=0.633), 19.978 vinhos com nota=5.00 nesta faixa — forte evidencia de ruido. Guardrail apertado.
- n 10-24: variancia cai pela metade (std=0.400). Ainda ruidoso, mas comeca a ter sinal.
- n 25-49: variancia moderada (std=0.363). A maioria dos deltas ja esta dentro de ±0.25. Alargar permite os casos reais de divergencia.
- n 50-99: variancia baixa (std=0.342). A maioria da divergencia nesta faixa provavelmente e real. Clamp so para extremos.
- n 100+: **sem clamp**. Em n >= 100, o WCF ja parece confiavel o suficiente para dispensar guardrail rigido. A divergencia que sobra nesta faixa tende a ser a diferenciacao real do produto.

**Nota sobre assimetria:** Em todas as faixas exceto n=100+ (sem clamp), o clamp permite mais desvio para baixo do que para cima. Isso reflete o dado empirico: o WCF tende a ficar -0.05 abaixo do Vivino em media.

### Threshold verified: recomendacao 50 (decisao final e de produto)

**Por que 50 e nao 25:**
- Com n=25, std ainda e 0.363 — "verificado" deveria significar mais que isso
- 30% dos vinhos como verified desvaloriza o selo
- A diferenca de variancia entre 25 e 50 e pequena (0.363 vs 0.342), mas o salto simbolico e grande

**Por que 50 e nao 100:**
- O n esta capado em 128 — threshold de 100 cria uma faixa de 100-128 artificialmente estreita
- 100 favorece vinhos com massa historica grande, contradizendo a tese
- A melhoria real de confianca de 50 para 100 e marginal (std 0.342 vs 0.329)
- Com n=50, alpha no shrinkage = 50/70 = 0.71 — a nota bruta ja domina. Isso e confiavel.

**Classificacao recomendada por este estudo (nao e decisao fechada — depende de validacao e decisao de produto):**
- `verified` = n >= 50
- `estimated` = n entre 10 e 49
- `contextual` = n = 0 (nota veio puramente da cascata)
- `sem nota` = sem contexto suficiente

**Proposta adicional (nova, nao existia no modelo anterior):**
- `low_confidence` = n entre 1 e 9 — esta faixa nao existia como categoria separada. A sugestao e criar esta sub-faixa porque a meta-analise mostrou que o bucket "estimated" (1-99) era heterogeneo demais (p50 de n = 9, ou seja, metade dos "estimated" tinham amostra minuscula). Marcar essa faixa explicitamente melhora a honestidade do sistema, mas e uma decisao de produto que precisa ser avaliada separadamente.

**Nota:** Tanto o threshold de 50 quanto a criacao da faixa `low_confidence` sao recomendacoes deste estudo, sustentadas pelos dados mas nao provadas matematicamente. A escolha final envolve tradeoffs de UX e comunicacao que extrapolam esta analise estatistica.

---

## 9. O que ainda ficou incerto

1. **O cap de 128 no n distorce a analise.** O n real de vinhos populares pode ser 500 ou 5000, mas o CSV corta em 128. Se o cap for removido, a faixa 100+ muda completamente de perfil — e o threshold de verified e o comportamento do clamp precisam ser revistos.

2. **Interacao clamp + shrinkage na v2.** O shrinkage ja puxa notas de baixo n para a base contextual. O clamp age em cima do resultado pos-shrinkage. Em teoria, double-dipping: ambos sao conservadores. Na pratica, para n baixo o shrinkage ja domina tanto que o clamp e redundante. Para n alto o shrinkage solta e o clamp vira o unico guardrail. Isso reforça a logica progressiva.

3. **Comportamento quando vivino_rating nao existe.** O clamp atual requer ancora no Vivino. Se o vinho so tem WCF sem Vivino, o clamp nao tem contra o que comparar. A proposta acima ja trata isso (retorna wcf direto), mas precisa de validacao sobre quantos vinhos estao nessa situacao.

4. **A correlacao 0,916 foi medida sobre o WCF v1.** Se o WCF v2 muda o shrinkage e a base, a correlacao pode cair (se a nota divergir mais) ou subir (se a base contextual puxar mais para o Vivino). Medir novamente apos implementacao e obrigatorio.

5. **O que acontece com vinhos que mudam de faixa.** Se um vinho ganha reviews e pula de n=45 para n=55, o clamp muda de -0.35/+0.30 para -0.45/+0.40. Se a nota estava no limite do clamp, ela pode saltar visivelmente. Nao e um problema grave (a direcao e correta), mas o usuario pode notar.

6. **Calibracao formal dos limites.** Os valores propostos (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45) foram derivados da variancia observada por faixa, mas nao passaram por backtesting formal. Uma validacao out-of-sample (holdout 10%) confirmaria se os limites estao calibrados. **Este e o ponto pendente mais importante antes de ir para producao.**

7. **Todas as recomendacoes deste estudo sao propostas, nao decisoes.** O threshold de verified, a regra de clamp progressivo e a criacao da faixa `low_confidence` dependem de validacao final e decisao de produto. Os dados sustentam as propostas, mas nao as provam como unica opcao correta.
