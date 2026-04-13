# Pesquisa 4 — Resultado: Cobertura da Cascata, Reforco dos Degraus Amplos e Uso de Uvas

Data: 2026-04-12

---

## 1. Resumo Executivo

A cascata com minimos por degrau (`2/10/3/10/3/10/5`) cobre apenas **42.9%** dos 596.290 candidatos com tipo. Os outros **57.1% (340.405 vinhos) ficam sem nota**.

A causa raiz nao e a cascata em si — e a **ausencia do campo `pais`**: 99.9% dos vinhos que ficam SEM_NOTA nao tem pais preenchido. Sem pais, os degraus D5 e D6 (que sao os mais eficazes) ficam inacessiveis, e o degrau D7 (vinicola+tipo) so salva quem tem uma vinicola com 5+ feeders — o que e raro para vinhos de loja sem historico Vivino.

Uvas (18.8% dos candidatos) funciona como **refinador de precisao**, nao como motor de cobertura. O delta mediano de nota quando uva e adicionada ao balde pais+tipo e de **0.160**, com p90 de **0.356**. Mas a cobertura do campo nos feeders e baixa (5.4%), o que limita a formacao de baldes pais+tipo+uva.

**A maior alavanca de cobertura nao esta na cascata — esta no preenchimento de `pais`.**

---

## 2. Diagnostico da Cobertura Atual

### Universo

| Bloco | Vinhos | % |
|-------|--------|---|
| Total na base | 2.506.441 | 100% |
| Com nota_wcf (feeders) | 1.727.054 | 68.9% |
| Sem nota_wcf (candidatos) | 779.387 | 31.1% |
| Candidatos com tipo | 596.290 | 76.5% dos candidatos |
| Candidatos sem tipo | 183.097 | 23.5% — excluidos da cascata |

### Campos disponiveis nos 596.290 candidatos com tipo

| Campo | Preenchido | % |
|-------|-----------|---|
| produtor_normalizado | 572.181 | 96.0% |
| produtor | 494.245 | 82.9% |
| teor_alcoolico | 445.098 | 74.6% |
| pais | 244.259 | 41.0% |
| safra | 201.540 | 33.8% |
| uvas | ~112.000 | ~18.8% |
| regiao | 107.712 | 18.1% |
| sub_regiao | 57.496 | 9.6% |
| volume_ml | 0 | 0% |

**Observacao critica**: `produtor_normalizado` (96%) e de longe o campo mais preenchido, mas o unico degrau que o usa e D7. `pais` (41%) e o gargalo — sem ele, D5 e D6 ficam inacessiveis.

---

## 3. Por que a Cascata Perdeu Cobertura

### 3.1 Distribuicao dos baldes (feeders com nota_wcf)

| Degrau | Baldes | Atingem minimo | %OK | p50 do balde |
|--------|--------|----------------|-----|-------------|
| D1: vinicola+sub_regiao+tipo (min=2) | 23.376 | 6.270 | 26.8% | 1 |
| D2: sub_regiao+tipo (min=10) | 4.333 | 599 | 13.8% | 1 |
| D3: vinicola+regiao+tipo (min=3) | 729.727 | 155.565 | 21.3% | 1 |
| D4: regiao+tipo (min=10) | 14.493 | 7.128 | 49.2% | 9 |
| D5: vinicola+pais+tipo (min=3) | 445.993 | 164.593 | 36.9% | 2 |
| D6: pais+tipo (min=10) | 371 | 313 | 84.4% | 234 |
| D7: vinicola+tipo (min=5) | 430.429 | 94.660 | 22.0% | 2 |

**Interpretacao**: Nos degraus estreitos (D1, D2, D3), a mediana do balde e **1 vinho**. Ou seja, a maioria dos baldes sequer existe com suporte suficiente. Os minimos estao cortando "no osso", nao "na gordura".

D6 (pais+tipo) e o unico degrau que funciona bem: 84.4% dos baldes atingem o minimo, com mediana de 234 vinhos por balde. E uma maquina de cobertura.

D7 (vinicola+tipo) tem 430K baldes, mas 78% deles tem menos de 5 feeders. O minimo de 5 elimina 3/4 dos baldes.

### 3.2 Simulacao da cascata efetiva (exclusiva, com minimos)

| Degrau | Vinhos cobertos | % dos candidatos |
|--------|----------------|-----------------|
| D1 | 939 | 0.2% |
| D2 | 40.607 | 6.8% |
| D3 | 2.166 | 0.4% |
| D4 | 43.702 | 7.3% |
| D5 | 2.287 | 0.4% |
| **D6** | **156.597** | **26.3%** |
| D7 | 9.587 | 1.6% |
| **SEM_NOTA** | **340.405** | **57.1%** |
| **Total coberto** | **255.885** | **42.9%** |

**Degraus decorativos**: D1 (0.2%), D3 (0.4%), D5 (0.4%). Juntos cobrem 5.392 vinhos — **0.9%**. Poderiam ser removidos sem impacto significativo.

**Degraus que carregam a cascata**: D6 (26.3%), D4 (7.3%), D2 (6.8%).

**D7 e um fundo falso**: Apesar de 96% dos candidatos terem vinicola+tipo como campos, apenas 1.6% efetivamente encaixam em balde qualificado. A maioria das vinicolas do bloco candidato nao tem historico suficiente no pool de feeders.

### 3.3 Perfil dos 340.405 que ficam SEM NOTA

| Campo | Preenchido | % |
|-------|-----------|---|
| vinicola | 334.469 | 98.3% |
| uvas | 52.458 | 15.4% |
| sub_regiao | 5.171 | 1.5% |
| regiao | 1.609 | 0.5% |
| **pais** | **429** | **0.1%** |

**Causa raiz**: 99.9% nao tem `pais`. Se tivessem, D6 poderia absorver a maioria deles (desde que o balde pais+tipo exista e atinja o minimo — o que acontece para 84.4% dos baldes D6).

---

## 4. Como Fortalecer os Degraus Amplos

### 4.1 D6 (pais+tipo) — O carro-chefe

**Situacao atual**: 313 baldes qualificados, mediana 234 vinhos. Cobre 26.3% dos candidatos.

**Dispersao**: media stddev = 0.419, p50 = 0.429.

A dispersao de D6 e a mais alta entre os degraus amplos. Isso e esperado: "tinto da Italia" agrupa desde Chianti basico ate Barolo premium. Mesmo assim, como base contextual com shrinkage (k=20), o valor e defensavel — a nota final do candidato vai tender ao grupo, nao ser identica a ele.

**Como fortalecer**:
- **Preencher `pais`**: a maior alavanca. Se pais fosse preenchido para os 346K candidatos sem ele, D6 absorveria uma fatia enorme.
- **Usar uva como refinador dentro de D6**: Quando o candidato tem uva E o balde pais+tipo+uva tem suporte, usar a media mais refinada em vez da media ampla. Detalhe na secao 5.

### 4.2 D4 (regiao+tipo) — Importante mas limitado

**Situacao atual**: 7.128 baldes qualificados, mediana 9 vinhos. Cobre 7.3%.

**Dispersao**: media stddev = 0.379, p50 = 0.374. Mais preciso que D6.

**Limitacao**: `regiao` so esta preenchido para 18.1% dos candidatos. Nao tem como fortalecer sem preencher o campo.

### 4.3 D7 (vinicola+tipo) — Subutilizado

**Situacao atual**: 94.660 baldes qualificados com min=5. Cobre apenas 1.6%.

**Dispersao**: media stddev = 0.318, p50 = 0.286. **A menor dispersao dos 3 degraus amplos**. Faz sentido: vinhos da mesma vinicola tendem a ser similares em qualidade.

**Sensibilidade ao minimo**:

| Minimo | Baldes D7 | Candidatos match | media_sd | p50_sd |
|--------|-----------|-----------------|----------|--------|
| 5 | 94.660 | 18.493 | 0.318 | 0.286 |
| 3 | 164.815 | 28.010 | 0.296 | 0.258 |
| 2 | 241.887 | 42.207 | 0.264 | 0.225 |
| 1 | 430.429 | 60.565 | 0.148 | 0.040 |

**Nota**: Os "candidatos match" sao contagens independentes (nao exclusivas com a cascata). Na cascata real, D7 so pega os que nao encaixaram em D1-D6. A coluna mostra o potencial isolado.

**Analise**: Baixar de min=5 para min=2 mais que triplica o numero de candidatos elegives (18K → 42K) e a dispersao *diminui* (media_sd 0.318 → 0.264). Isso e contraintuitivo ate entender que os baldes com 2-4 feeders tendem a ser vinicolas boutique de nicho — mais coesas que vinicolas gigantes com dezenas de vinhos distintos.

Baixar para min=1 e arriscado: um unico feeder nao e um "grupo" — e um ponto individual. A stddev cai para 0.040 (quase zero) porque nao ha variacao com n=1, o que nao significa precisao — significa falta de informacao.

---

## 5. Como `uvas` Poderia Ajudar

### 5.1 Cobertura de uvas

| Bloco | Tem uvas | % |
|-------|---------|---|
| Feeders (1.727K com nota_wcf) | 92.480 | 5.4% |
| Candidatos (779K sem nota_wcf) | 146.512 | 18.8% |
| Candidatos SEM_NOTA (340K) | 52.458 | 15.4% |

**Problema central**: So 5.4% dos feeders tem uvas. Isso limita severamente a formacao de baldes com uva como eixo.

### 5.2 Efeito refinador

Teste: para baldes pais+tipo com min>=10 (os "baldes D6"), qual o delta quando se refina por uva?

**1.518 pares validos** (pais+tipo+uva com n>=5 vs pais+tipo com n>=10):

| Metrica | Valor |
|---------|-------|
| Media do delta absoluto | 0.182 |
| p50 | 0.160 |
| p75 | 0.251 |
| p90 | 0.356 |
| Max | 0.750 |

**Interpretacao**: A uva muda a nota esperada em ~0.16 na mediana. Em 10% dos casos, a diferenca passa de 0.35. Para referencia, o clamp da pesquisa 3 era da mesma ordem de grandeza.

**Exemplos extremos**: Nebbiolo na Italia (nota media +0.39 vs media IT tinto), Tinta del Pais na Espanha (+0.75 vs media ES tinto). A uva carrega informacao real de qualidade.

### 5.3 Resposta as 4 perguntas especificas sobre uvas

**Quanto aumenta cobertura?**
Quase nada. Uvas tem cobertura suficiente nos feeders para formar baldes uteis, mas isso so funciona onde ja existe pais+tipo. Nao resolve o problema dos 340K sem pais. E desses 340K, apenas 52K (15%) sequer tem uvas.

**Quanto melhora precisao?**
Significativamente para quem se encaixa. Delta mediano de 0.16 e p90 de 0.36 demonstra que a uva carrega sinal real.

**Mantem suporte minimo defensavel?**
Parcialmente. Dos 1.518 pares pais+tipo+uva com n>=5, o suporte e razoavel. Mas se exigir n>=10 no balde refinado, o numero de pares cai drasticamente (porque so 5.4% dos feeders tem uvas).

**Onde entra como refinador e onde nao?**
- **Entra**: Como ajuste opcional dentro de D4 (regiao+tipo) ou D6 (pais+tipo), QUANDO o candidato tem uvas E existe balde refinado com suporte suficiente. Nesse caso, usa-se a media do balde refinado em vez da media ampla.
- **Nao entra**: Como eixo central ou degrau independente. Nao ha massa critica nos feeders.
- **Nao entra**: Nos degraus estreitos (D1-D3, D5) — la ja tem contexto suficiente, uva nao agrega.

### 5.4 Qualidade dos dados de uvas

O campo `uvas` (jsonb array) esta limpo na maioria dos registros (amostra: `["Cabernet Sauvignon"]`, `["Nebbiolo", "Pinot Noir"]`). Mas ha artefatos de parsing em alguns registros (aspas e colchetes residuais nos nomes). Uma limpeza pontual seria necessaria antes de usar em producao.

---

## 6. Opcoes de Desenho com Trade-offs

### Opcao A — Conservadora (manter cascata, ajustar minimos)

**Mudancas**:
- Baixar D7 de min=5 para **min=3**
- Manter todos os outros degraus intactos
- Nao usar uvas

**Cobertura estimada**: ~44-45% (ganho de ~2 pontos percentuais vs 42.9%)

**Trade-offs**:
- (+) Nenhum risco novo
- (+) Facil de implementar
- (-) Nao resolve o problema dos 340K sem pais
- (-) Ganho marginal

### Opcao B — Intermediaria (ajustar D7 + uva como refinador opcional)

**Mudancas**:
- Baixar D7 de min=5 para **min=2**
- Adicionar **sub-refinamento por uva** nos degraus D4 e D6:
  - Se candidato tem uvas E balde (regiao/pais)+tipo+uva tem n>=5, usar media refinada
  - Senao, usar media ampla normal
  - Marcar `confianca_nota` levemente acima quando uva refinou
- Remover D1, D3, D5 (decorativos) para simplificar

**Cascata simplificada**:
1. `sub_regiao + tipo` (min=10)
2. `regiao + tipo` (min=10)
3. `pais + tipo` (min=10) — com sub-refinamento por uva quando possivel
4. `vinicola + tipo` (min=2)
5. sem nota

**Cobertura estimada**: ~45-46%

**Trade-offs**:
- (+) Cascata mais simples (4 degraus vs 7)
- (+) Precisao melhor onde uva existe
- (+) D7 com min=2 e defensavel (sd 0.264 vs 0.318 com min=5)
- (-) Ainda nao resolve os 340K sem pais
- (-) Uva melhora poucos casos (5.4% dos feeders)

### Opcao C — Abrangente (Opcao B + preenchimento de pais)

**Mudancas**: Tudo da Opcao B, mais:
- **Pipeline para preencher `pais`** nos candidatos que nao o tem:
  - Extrair de `regiao` (quando mapeavel, ex: "Mendoza" → AR)
  - Extrair de `produtor_normalizado` (muitas vinicolas sao associaveis a um pais)
  - Extrair de `nome` (heuristicas por idioma ou termos como "Reserva", "Crianza", etc.)
  - Extrair de `sub_regiao` (quando existir)
- Marcar `pais_inferido = true` para distinguir de pais original

**Cobertura estimada**: 60-70%+ (dependendo da taxa de sucesso do preenchimento de pais)

**Trade-offs**:
- (+) Resolve a causa raiz real da baixa cobertura
- (+) D6 (84% dos baldes qualificados) finalmente funciona em escala
- (+) Escalavel — cada vinho que ganha pais ganha nota
- (-) Requer pipeline de inferencia de pais (trabalho extra, risco de erro)
- (-) Pais inferido incorreto → nota contextual errada
- (-) Precisa de validacao e taxa de acerto medida antes de confiar

---

## 7. Recomendacao Final

**Implementar Opcao B agora, preparar Opcao C como proxima frente.**

Justificativa:
1. A Opcao B e de baixo risco e traz ganhos imediatos (cascata mais limpa, D7 mais eficaz, uva como bonus de precisao).
2. A Opcao C e onde esta o ganho real, mas requer pesquisa propria sobre inferencia de `pais`.
3. Nao faz sentido investir em otimizar a cascata quando o gargalo e um campo faltante.

**Sobre uvas**: Usar como refinador opcional, nunca como eixo. Entrar apenas nos degraus D4 e D6, apenas quando o balde refinado tem suporte. Nao criar degrau novo para uva.

**Sobre D7 minimo**: Recomendo min=2 (nao 3, nao 1). A dispersao com min=2 (sd=0.264) e menor que D4 e D6, e triplica a cobertura isolada do degrau. Min=1 nao e grupo — e um unico ponto.

**Sobre degraus decorativos (D1, D3, D5)**: Podem ser removidos. Juntos cobrem 0.9% e complicam a cascata sem beneficio mensuravel. A simplificacao para 4 degraus facilita manutencao e explicacao.

---

## 8. O que Ainda Nao Foi Provado

1. **Taxa de acerto da inferencia de pais**: Nao sabemos quantos candidatos sem pais poderiam ter o pais inferido corretamente a partir de regiao, produtor ou nome. Isso precisa de pesquisa propria.

2. **Cobertura de uvas nos candidatos apos preenchimento de pais**: Se pais for preenchido, o cruzamento pais+tipo+uva nos candidatos pode ficar mais rico. Nao medimos isso.

3. **Efeito cascata efetivo com Opcao B**: A simulacao de cobertura da Opcao B e estimada, nao computada exatamente. Uma simulacao completa da cascata simplificada com min=2 em D7 e necessaria para confirmar.

4. **Qualidade real dos baldes com min=2 em D7**: A dispersao baixa (0.264) sugere coesao, mas nao verificamos se esses baldes "pequenos" geram notas contextuais que fazem sentido em casos concretos (ex: uma vinicola com 2 feeders cujas notas sao 4.5 e 2.0 — media 3.25 com sd alto nesse par especifico).

5. **Limpeza do campo uvas**: Artefatos de parsing (colchetes/aspas residuais) existem. Nao medimos a taxa nem o impacto na formacao de baldes.

6. **Impacto de `safra`**: 33.8% dos candidatos tem safra. Nao investigamos se a safra carrega sinal de qualidade dentro de um balde (ex: safras antigas de vinicolas premium tem nota diferente?). Nao e prioridade — teor, volume e safra nao parecem carregar informacao de qualidade comparavel a pais/regiao/tipo/uva.

---

## Anexo: Dados Brutos

### A. Sensibilidade D7

| Minimo | Baldes | Candidatos (isolado) | media_sd | p50_sd |
|--------|--------|---------------------|----------|--------|
| 5 | 94.660 | 18.493 | 0.318 | 0.286 |
| 3 | 164.815 | 28.010 | 0.296 | 0.258 |
| 2 | 241.887 | 42.207 | 0.264 | 0.225 |
| 1 | 430.429 | 60.565 | 0.148 | 0.040 |

### B. Dispersao dos baldes amplos (feeders, com minimos)

| Degrau | Baldes | media_nota | media_sd | p50_sd | p75_sd | p90_sd | max_sd |
|--------|--------|-----------|----------|--------|--------|--------|--------|
| D4 regiao+tipo | 7.128 | 3.726 | 0.379 | 0.374 | 0.450 | 0.526 | 1.021 |
| D6 pais+tipo | 313 | 3.638 | 0.419 | 0.429 | 0.466 | 0.509 | 0.674 |
| D7 vinicola+tipo | 94.660 | 3.714 | 0.318 | 0.286 | 0.403 | 0.540 | 1.560 |

### C. Top 15 uvas nos feeders

| Uva | n | avg_wcf | sd |
|-----|---|---------|-----|
| Pinot Noir | 12.101 | 3.965 | 0.332 |
| Chardonnay | 11.728 | 3.901 | 0.372 |
| Cabernet Sauvignon | 7.920 | 3.870 | 0.442 |
| Sauvignon Blanc | 5.055 | 3.740 | 0.338 |
| Merlot | 4.833 | 3.722 | 0.403 |
| Riesling | 4.351 | 3.891 | 0.303 |
| Syrah | 3.575 | 3.899 | 0.337 |
| Grenache | 2.362 | 3.898 | 0.303 |
| Sangiovese | 2.187 | 3.886 | 0.331 |
| Cabernet Franc | 2.137 | 3.892 | 0.321 |
| Shiraz | 2.077 | 3.833 | 0.375 |
| Nebbiolo | 1.919 | 4.048 | 0.287 |
| Malbec | 1.852 | 3.786 | 0.328 |
| Tempranillo | 1.327 | 3.782 | 0.384 |
| Chenin Blanc | 1.286 | 3.865 | 0.311 |

### D. Delta refinador pais+tipo+uva

| Metrica | Valor |
|---------|-------|
| Pares validos | 1.518 |
| Media delta abs | 0.182 |
| p50 | 0.160 |
| p75 | 0.251 |
| p90 | 0.356 |
| Max | 0.750 |
