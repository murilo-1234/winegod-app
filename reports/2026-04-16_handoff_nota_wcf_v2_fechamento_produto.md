# Handoff Final de Produto: `nota_wcf v2`, Cascata B e Fallback dos 309K

**Data:** 2026-04-16  
**Status:** definicao de produto consolidada; implementacao ainda nao feita  
**Objetivo:** deixar um unico documento capaz de reabrir esta frente em um novo chat sem depender da conversa anterior

---

## 1. O que este handoff e

Este documento consolida:
- o estado historico da frente `nota_wcf v2`
- as alternativas antigas consideradas
- o que foi medido nas pesquisas
- o que foi fechado como decisao de produto
- como interpretar o problema dos `309.616` vinhos com gap de reviews
- qual logica provisoria foi aceita para esses vinhos ate o scraping completo

Este documento **nao e** um plano de execucao.

Ele tambem **nao substitui** os docs-fonte; ele os organiza, corrige ambiguidades e registra o que foi fechado depois deles.

---

## 2. Resumo executivo

O projeto saiu da ideia antiga de "`nota_wcf` so vale quando ha sample suficiente" para uma arquitetura mais madura:
- a `nota_wcf` continua sendo a base tecnica principal
- a nota oficial passa a separar **fonte da nota** de **grau de confianca**
- a confianca publica nao deve depender apenas de quantas reviews individuais o nosso scraping conseguiu baixar
- a confianca publica deve considerar a **evidencia publica do Vivino**, via `total_ratings`
- a cascata contextual continua existindo, mas como fallback estrutural, nao como substituto para vinhos que ja tem nota publica forte

As decisoes de produto fechadas nesta conversa foram:
- usar a **Cascata B** como cascata final
- usar `pais` como campo tecnico canonico da cascata
- manter `pais_nome` como campo de exibicao, nao como eixo tecnico
- fixar o clamp em **`vivino -0,30 / +0,20`**
- fixar a `nota_base` como **media ponderada com teto `min(n,50)`**
- aplicar penalidade contextual **so quando `n = 0`**
- interpretar os vinhos com nota publica do Vivino e pouco sample WCF como caso de **gap operacional de scraping**, nao como caso de falta de evidencia
- tratar o `total_ratings` publico como base do selo de confianca
- nao deixar um WCF minuscule dominar um vinho que ja tem nota publica forte no Vivino

Tambem ficou fechado o principio mais importante para os `309k`:
- se o vinho tem nota publica do Vivino, ele **nao deve** cair para contextual so porque nosso scraping esta incompleto
- nesses casos, o Vivino vira **ancora forte**
- o WCF pequeno pode contribuir, mas nao deve mandar sozinho
- quando o scraping completar, o sistema se ajusta automaticamente para uma nota cada vez mais WCF-real

### 2.1. Adendo de decisoes posteriores fechadas

Este adendo vence qualquer trecho antigo deste handoff que ainda deixe ambiguidade operacional.

**Selo publico:**
- qualquer vinho com `public_ratings_count >= 75` (`total_ratings` publico canonico) e **sempre `verified`**
- `25 <= public_ratings_count < 75` continua como `estimated`
- `nota_wcf_sample_size` nao decide se um vinho `75+` e `verified`
- `nota_wcf_sample_size` decide apenas a fonte numerica da nota

**Fonte numerica para vinhos com Vivino:**
- se `nota_wcf_sample_size >= 25`, usar WCF v2 com `nota_base` via shrinkage e clamp contra Vivino
- se `nota_wcf_sample_size < 25`, usar Vivino como ancora, tentar `delta_contextual` aprendido pela Cascata B, usar `nota_base` como freio e aplicar clamp
- se nao houver contexto suficiente para o delta contextual, usar Vivino direto com 2 casas (`4.2` vira `4.20`)
- nao copiar Vivino puro como regra principal quando houver contexto suficiente
- nao usar `delta global` grosseiro como regra principal

**Clamp:**
- manter clamp fixo `vivino -0,30 / vivino +0,20`
- aplicar quando a nota vier de WCF com Vivino disponivel ou de Vivino + delta contextual

**Penalidade contextual:**
- a formula `penalidade = -0.5 * bucket_stddev` fica decidida para esta implementacao
- aplicar somente em nota puramente contextual com `n = 0`
- nao aplicar em vinhos com WCF proprio
- nao aplicar em vinhos com Vivino fallback/proxy

**Metrica publica de ratings:**
- usuario ve apenas buckets: `25+`, `50+`, `100+`, `200+`, `300+`, `500+`
- `500+` e teto visual, nao truncamento de dados
- o numero bruto real deve continuar salvo integralmente (`10000` continua `10000`, mas exibe `500+`)
- nunca apagar reviews, truncar ratings ou substituir dado real por bucket visual

---

## 3. Documentos-fonte que sustentam este handoff

Ler estes docs ajuda a reconstituir a trilha completa:

- `reports/2026-04-11_handoff_nota_wcf_v2.md`
- `reports/2026-04-12_estudo_clamp_e_confianca.md`
- `reports/2026-04-12_pesquisa_05_nota_base_penalidade_fallback.md`
- `prompts/nota_wcf_v2_research/01_ESTUDO_PAIS_VS_PAIS_NOME.md`
- `prompts/nota_wcf_v2_research/04_RESULTADO_CASCATA_COBERTURA_E_UVAS.md`
- `prompts/HANDOFF_WCF_REVIEW_GAP_2026-04-15.md`

Arquivos de codigo relevantes para o estado atual:

- `backend/services/display.py`
- `scripts/calc_score.py`
- `scripts/calc_wcf_fast.py`
- `scripts/clean_wines.py`
- `backend/prompts/baco_system.py`

---

## 4. Termos e campos que precisam ser entendidos sem ambiguidade

### 4.1. `nota_wcf`

E a nota calculada pelo WCF historico do WineGod, baseada nas reviews individuais e nos pesos por experiencia do reviewer.

Ela **ja existe** e **ja e gravada** no banco.

Ela nao e a `nota_estimada` antiga. Ela e a nota principal que o projeto decidiu preservar como base.

### 4.2. `nota_wcf_sample_size`

E o numero de reviews validas que efetivamente entraram no calculo da `nota_wcf`.

Esse campo:
- nao guarda pesos
- nao recalcula a nota
- nao diz quantas avaliacoes publicas o vinho tem no Vivino
- diz apenas quantas reviews individuais nos temos de fato no pipeline WCF

### 4.3. `vivino_rating`

E a nota publica exibida pelo Vivino.

No raciocinio fechado nesta conversa, esse campo tem peso especial porque:
- nota publica no Vivino ja implica validacao publica minima
- portanto, quando ela existe, nao e justo tratar o vinho como "sem evidencia" so porque o nosso scraping nao baixou todas as reviews

### 4.4. `total_ratings`

E a quantidade publica de avaliacoes do vinho no universo Vivino.

Este campo ganhou status central nesta conversa porque ele expressa:
- a massa publica de gente que avaliou o vinho
- a forca publica da evidencia
- a confianca do mercado naquele vinho

Em linguagem simples:
- `nota_wcf_sample_size` diz o que **nos** conseguimos baixar
- `total_ratings` diz o que o **Vivino** afirma que existe publicamente

### 4.5. `total_reviews_db`

E quantas reviews individuais nos efetivamente coletamos e temos no banco local.

Esse campo foi essencial para descobrir o gap dos `309.616` vinhos.

### 4.6. `vivino_reviews`

Este nome precisa ser tratado com cuidado.

Durante a investigacao, surgiu uma confusao entre:
- um campo chamado `vivino_reviews` no Render
- e o `total_ratings` do banco local `vivino_vinhos`

O insight pratico foi:
- **o campo confiavel para o problema dos 309k e `total_ratings`**
- nao se deve decidir este caso usando uma leitura ingenua do `vivino_reviews` do Render

### 4.7. `nota_base`

E a nota contextual do balde da cascata.

Ela existe para fazer o shrinkage:
- com pouca amostra, a nota do vinho e puxada para um centro contextual
- com muita amostra, a nota do vinho passa a ser dominada pela propria `nota_wcf`

### 4.8. `contextual`

`contextual` nao significa "nota ruim".

Significa:
- a nota veio principalmente da cascata contextual
- e nao de um conjunto robusto de reviews individuais do proprio vinho

Depois da conversa dos `309k`, ficou ainda mais importante nao confundir:
- vinho sem evidencias publicas -> pode ser `contextual`
- vinho com nota publica forte, mas scraping incompleto -> **nao deve** ser tratado como meramente `contextual`

---

## 5. O estado historico antes do fechamento atual

### 5.1. O desenho original da `nota_wcf v2`

O desenho antigo, consolidado no handoff de 2026-04-11, era:
- manter `nota_wcf` como base
- criar uma `nota_base` contextual por cascata
- usar shrinkage com `k = 20`
- classificar:
  - `verified = 100+`
  - `estimated = 1-99`
  - `contextual = 0`

Formula-alvo antiga:

```text
nota_final = (n / (n + 20)) * nota_wcf_bruta
           + (20 / (n + 20)) * nota_base
```

Onde:
- `nota_wcf_bruta` = WCF do vinho
- `nota_base` = media contextual do balde
- `n` = tamanho da amostra usada no WCF

### 5.2. A cascata original de 7 degraus

A cascata originalmente aprovada era:

1. `vinicola + sub_regiao + tipo` `min=2`
2. `sub_regiao + tipo` `min=10`
3. `vinicola + regiao + tipo` `min=3`
4. `regiao + tipo` `min=10`
5. `vinicola + pais + tipo` `min=3`
6. `pais + tipo` `min=10`
7. `vinicola + tipo` `min=5`
8. senao `sem nota`

### 5.3. O runtime que existe hoje no repo

O runtime atual **nao implementa** a v2 final.

O que existe hoje:

- `display.py` usa uma logica antiga/hibrida:
  - `sample >= 25` + Vivino -> `verified`
  - `sample >= 1` + Vivino -> `estimated`
  - senao Vivino direto
  - senao `ai` em alguns casos

- `calc_score.py` ainda esta mais atras:
  - usa WCF apenas com `sample >= 25`
  - trata `>=100` como `wcf_verified` e `>=25` como `wcf_estimated`
  - portanto esta inconsistente com o `display.py`

- `calc_wcf_fast.py` hoje **ja grava** `nota_wcf_sample_size`
  - isso e importante porque parte dos docs antigos ainda dizia que ele nao gravava
  - esse ponto foi superado pelo estado atual do codigo

Conclusao:
- a definicao de produto avancou
- o runtime do repo ainda nao esta alinhado com ela

---

## 6. O que a pesquisa de cascata realmente mostrou

### 6.1. O problema nao era "ordem da cascata"

A Pesquisa 4 mostrou que a cascata original com minimos `2/10/3/10/3/10/5` cobre apenas:
- `42,9%` dos `596.290` candidatos com `tipo`

E deixa sem nota:
- `340.405` vinhos

### 6.2. A causa raiz descoberta

O gargalo estrutural nao era a cascata em si.

Era o campo `pais`.

Achado central:
- `99,9%` dos vinhos que ficam `SEM_NOTA` nao tem `pais`

Isso importa porque o degrau mais poderoso era:
- `pais + tipo`

Ou seja:
- o melhor degrau existia
- mas nao podia ser usado na maior parte dos casos porque o dado `pais` estava ausente

### 6.3. O que funcionava e o que era decorativo

Na simulacao completa da cascata original:
- D6 (`pais + tipo`) era o grande motor de cobertura
- D4 (`regiao + tipo`) ajudava de forma relevante
- D2 (`sub_regiao + tipo`) ajudava moderadamente
- D1, D3 e D5 eram quase decorativos

Cobertura dos degraus decorativos:
- D1 = `0,2%`
- D3 = `0,4%`
- D5 = `0,4%`
- juntos = `0,9%`

Isso foi decisivo para simplificar a cascata.

### 6.4. O papel real de `uvas`

A pesquisa fechou um ponto importante:
- `uvas` **nao** deve virar degrau principal da cascata

O que `uvas` mostrou:
- baixa cobertura estrutural nos feeders
- utilidade real como **refinador de precisao**
- nao como motor de cobertura

Em termos simples:
- `uvas` pode melhorar a nota contextual em alguns casos
- mas nao serve para sustentar o desenho principal da cascata

---

## 7. Quais eram os concorrentes de cascata

Esta foi a competicao real entre desenhos.

### 7.1. Concorrente 1: cascata original de 7 degraus

Vantagens:
- ja estava aprovada historicamente
- capturava todos os niveis de granularidade imaginados

Desvantagens:
- mais complexa
- tinha degraus com ganho quase nulo
- escondia o fato de que o gargalo real era `pais`
- D7 com `min=5` tinha baixa eficacia pratica

### 7.2. Concorrente 2: Opcao A

Opcao A mantinha a estrutura antiga, mudando pouco:
- baixar D7 de `min=5` para `min=3`
- manter o resto
- nao usar `uvas`

Leitura:
- era a alternativa conservadora
- tinha baixo risco
- trazia ganho pequeno
- nao atacava o excesso de complexidade

### 7.3. Concorrente 3: Opcao B

Opcao B simplificava a cascata:
- removia D1, D3, D5
- mantinha apenas os degraus realmente uteis
- baixava `vinicola + tipo` para `min=2`
- aceitava `uvas` apenas como refinador opcional

Cobertura estimada:
- `45-46%`

Vantagens:
- mais simples
- melhor cobertura estimada que a original
- mais facil de explicar
- mais coerente com o que os dados mostraram

### 7.4. Concorrente 4: Opcao C

Opcao C era:
- a Opcao B
- mais uma frente de inferencia/preenchimento de `pais`

Leitura:
- era a alternativa de maior cobertura potencial
- mas tambem a mais cara e mais dependente de pipeline de enrichment

### 7.5. Qual venceu

A opcao vencedora foi a **Opcao B**.

Razao:
- cobria mais que a original
- tinha mais chance de acerto imediato
- simplificava manutencao
- eliminava degraus decorativos
- mantinha D7 num ponto defensavel com `min=2`

Importante:
- a Opcao B venceu como **decisao de produto**
- a Opcao C continuou como frente estrutural futura ligada ao problema de `pais`

---

## 8. A cascata final fechada

A cascata que ficou definida foi:

1. `sub_regiao + tipo` `min=10`
2. `regiao + tipo` `min=10`
3. `pais + tipo` `min=10`
4. `vinicola + tipo` `min=2`
5. senao `sem nota`

Regras conceituais complementares:
- `uvas` nao entra como degrau principal
- `uvas` pode entrar apenas como refinador opcional em baldes amplos, especialmente nos degraus de geografia
- `pais` continua sendo o campo tecnico canonico
- `pais_nome` nao substitui `pais` na logica

---

## 9. O que ficou definido sobre `pais` e `pais_nome`

### 9.1. O problema real

Nao era apenas duplicidade semantica.

Era uma combinacao de 2 coisas:
- duplicidade de campo
- e ausencia material de `pais` em muitos candidatos sem nota

### 9.2. O que a Pesquisa 1 mostrou

O desenho mais seguro era:
- `pais` como campo tecnico canonico
- `pais_nome` como derivacao de exibicao

Razoes:
- `pais` e ISO2 e mais padronizado
- `pais_nome` estava mais incompleto
- a medicao de partida indicava:
  - `0` casos com `pais` vazio e `pais_nome` preenchido
  - `263.950` casos com `pais` preenchido e `pais_nome` vazio

Conclusao:
- `pais_nome` nao ajudava a recuperar o que `pais` nao tivesse
- portanto o caminho seguro era continuar usando `pais` no calculo

### 9.3. O ponto que continua verdadeiro

Resolver `pais_nome` **nao bloqueia** implementar a cascata.

Mas resolver o preenchimento de `pais` continua sendo a maior alavanca de cobertura.

---

## 10. O que ficou definido sobre clamp

Houve debate real entre:
- clamp fixo
- clamp progressivo
- e soltura maior do WCF com n alto

O estudo estatistico apontou argumentos a favor de clamp progressivo.

Mesmo assim, a decisao final fechada nesta conversa foi manter:

```text
clamp = vivino - 0,30 / vivino + 0,20
```

Interpretacao:
- mais espaco para WCF corrigir para baixo
- menos espaco para inflar acima do Vivino

Este ponto esta fechado como decisao de produto, mesmo que os estudos antigos tenham explorado outros desenhos.

---

## 11. O que ficou definido sobre `nota_base`

### 11.1. Agregacao dentro do balde

A `nota_base` fechada foi:
- **media ponderada com teto `min(n,50)`**

Isto significa:
- vinhos com mais reviews pesam mais
- mas nao podem dominar infinitamente o balde

O teto existe para impedir que vinhos gigantes de mercado puxem sozinhos o centro contextual.

### 11.2. Penalidade contextual

Ficou fechado:
- para `n > 0`: **sem penalidade extra**
- para `n = 0`: penalidade baseada na variancia real do balde

Racional:
- com `n > 0`, o shrinkage ja faz o trabalho de freio
- aplicar penalidade adicional viraria desconto duplo
- com `n = 0`, a nota e puramente contextual, entao faz sentido um freio conservador

### 11.3. O que isso significa em linguagem simples

- com reviews proprias do vinho: mistura a nota do vinho com a nota do contexto
- sem reviews proprias: usa a nota do contexto, mas com desconto de seguranca

---

## 12. O grande problema dos `309.616` vinhos

### 12.1. O achado

Foi identificado no banco local um conjunto de:
- `309.616` vinhos

Com a seguinte condicao:
- `total_ratings >= 25`
- `total_reviews_db < 25`
- `reviews_coletados = true`

Em outras palavras:
- o Vivino diz publicamente que esses vinhos ja tem massa suficiente de ratings
- mas nosso scraping so coletou uma parte pequena das reviews individuais

### 12.2. O que isso provou

Provou que existe um gap operacional serio entre:
- a evidencia publica do Vivino
- e o que o nosso WCF tem materialmente em maos

Na media desse bloco:
- o Vivino reporta bem mais ratings do que nos coletamos
- e o scraping parou cedo, apesar do flag `reviews_coletados = true`

### 12.3. Por que isso virou um problema de produto, nao apenas de dados

Se a confianca continuar sendo decidida apenas por `nota_wcf_sample_size`, esses vinhos parecem:
- pouco amostrados
- `estimated` fracos
- ou ate candidatos a fallback ruim

Mas essa leitura e enganosa.

Ela confunde:
- **limite do nosso scraping**
- com **limite real de evidencia do vinho**

E isso foi justamente o ponto que o usuario recusou.

### 12.4. A intuicao central do usuario

O usuario trouxe um raciocinio de produto que foi aceito:

- se o vinho ja tem nota publica do Vivino, ele ja passou por um minimo de validacao publica
- entao usar um WCF montado em cima de `1`, `2`, `6` ou `12` reviews baixadas localmente pode ser menos justo do que usar a propria ancora publica do Vivino
- especialmente quando o vinho tem `150`, `200` ou mais ratings publicos

Em frase simples:
- o erro maior nao e confiar demais no Vivino nesses casos
- o erro maior e confiar demais no nosso sample incompleto

---

## 13. A mudanca conceitual mais importante: separar selo de fonte

Antes, a tendencia era usar uma so coisa para tudo:
- a contagem do sample WCF

Depois desta conversa, a separacao correta ficou assim:

### 13.1. O selo de confianca publica vem de `total_ratings`

Regra fechada para vinhos com **nota publica do Vivino**:
- `25-74 total_ratings` -> `estimated`
- `75+ total_ratings` -> `verified`

Leitura:
- o selo representa a forca publica da evidencia
- nao o quanto do scraping local ja terminou

### 13.2. A fonte da nota pode ser outra coisa

A nota numerica pode vir de fontes diferentes:
- `wcf_direct`
- `wcf_shrunk`
- `vivino_proxy`
- `contextual`

Esse foi um ponto importante da conversa:
- o vinho pode ser `verified` pelo mercado publico
- mesmo que a nota numerica, provisoriamente, ainda nao venha de WCF completo

Ou seja:
- **selo** e **fonte** foram desacoplados

---

## 14. A regra provisoria fechada para os 309k

### 14.1. O principio

Para vinhos com nota publica do Vivino e WCF muito raso por falha de scraping:
- **nao usar contextual**
- **nao deixar um WCF minuscule mandar sozinho**
- **usar Vivino como ancora forte**

### 14.2. O que isso nao significa

Nao significa:
- abandonar WCF
- dizer que Vivino sempre manda
- ou usar Vivino puro para sempre

Significa:
- enquanto o scraping estiver incompleto, existe um fallback provisoriamente mais justo do que confiar num sample WCF muito pequeno

### 14.3. O que ficou acordado como desenho conceitual

Casos com nota publica do Vivino:

- se o WCF ja tiver massa robusta:
  - o WCF domina

- se o WCF existir, mas ainda estiver raso/incompleto:
  - a nota deve ser ancorada no Vivino
  - o WCF pequeno pode ajudar, mas nao dominar

- se nao houver WCF individual nenhum, mas houver nota publica:
  - usar um fallback ancorado no Vivino
  - nao tratar como contextual

### 14.4. O que foi explicitamente corrigido na conversa

Em um momento, apareceu a ideia de algo como:

```text
vivino + nota_base + delta
```

Essa forma **nao** ficou aceita literalmente.

O entendimento corrigido foi:
- o fallback deve ser um **Vivino ajustado por um delta aprendido**
- e a `nota_base` entra apenas como ancora/freio
- nao como soma bruta de componentes heterogeneos

### 14.5. O principio de justica que ficou fechado

Quando o vinho tem nota publica forte e nos so temos 1, 2, 6 ou 12 reviews individuais:
- e mais injusto deixar esse sample minuscule mandar sozinho
- do que confiar no Vivino como ancora forte

Esse foi um dos fechamentos conceituais mais claros desta conversa.

---

## 15. O que ficou fechado sobre a classificacao publica

No fechamento final, a classificacao publica ficou assim:

- vinho com nota publica e `25-74 total_ratings` -> `estimated`
- vinho com nota publica e `75+ total_ratings` -> `verified`
- vinho sem nota publica suficiente -> `contextual` ou sem nota, dependendo do contexto estrutural

Importante:
- o range `1-24` nao deve ser confundido com o caso dos vinhos de nota publica
- a conversa dos `309k` tratou especificamente de vinhos onde a nota publica ja existe

Portanto, a nova logica nao e:
- "qualquer sample WCF 1-74 = estimated"

E sim:
- "quando ha nota publica, o selo vem do `total_ratings` publico"

---

## 16. O que isso muda na interpretacao do WCF pequeno

Antes do fechamento atual, era facil cair nesta leitura:
- `sample pequeno = nota fraca = estimated fraco`

Depois da conversa, a leitura correta passou a ser:

- `sample pequeno` pode significar duas coisas bem diferentes:
  - o vinho realmente tem pouca evidencia
  - ou o nosso scraping ainda nao terminou de capturar o que o Vivino ja confirma publicamente

O caso dos `309k` mostrou que os dois cenarios nao podem ser tratados da mesma forma.

---

## 17. O que acontece quando o scraping completar

Esse ponto tambem ficou claro.

O fallback dos `309k` e uma **ponte**, nao um estado final.

Quando as reviews faltantes forem coletadas:
- o `nota_wcf_sample_size` sobe
- o WCF passa a ser calculado com mais material real
- a dependencia do fallback provisoriamente ancorado no Vivino diminui
- o proprio banco "se corrige" naturalmente

Em outras palavras:
- o fallback foi pensado para nao punir o produto hoje
- sem bloquear a convergencia para WCF real amanha

---

## 18. O que ja esta implementado e o que ainda nao esta

### 18.1. Ja existe hoje

- `nota_wcf` gravada no banco
- `nota_wcf_sample_size` sendo escrita por `calc_wcf_fast.py`
- display runtime usando WCF/Vivino em logica antiga
- Baco lendo `display_note` e `display_note_type`

### 18.2. Ainda nao existe no runtime

- a `nota_wcf v2` completa conforme o fechamento atual
- a cascata B em producao
- o novo uso de `total_ratings` como base do selo
- o fallback `vivino_proxy` para os `309k`
- a separacao formal entre fonte e selo em todo o pipeline

### 18.3. Ponto de cuidado

O repo esta num estado misto:
- parte dos docs antigos refletem decisoes ja superadas
- parte do codigo reflete ajustes intermediarios
- e o fechamento atual desta conversa ainda nao foi codificado

---

## 19. O que foi superado em relacao aos docs antigos

Este bloco existe para evitar reabertura de decisoes.

### 19.1. Threshold antigo `100+ / 1-99 / 0`

Esse era o desenho historico.

Foi superado, no caso dos vinhos com nota publica, por:
- `25-74 total_ratings` -> `estimated`
- `75+ total_ratings` -> `verified`

### 19.2. Sample WCF como unico juiz de confianca

Esse desenho foi superado.

Agora:
- o sample WCF continua importante
- mas ele nao e mais o unico juiz da confianca publica

### 19.3. Queda automatica para contextual quando WCF e baixo

Isso tambem foi superado para o caso dos vinhos com nota publica.

Se o vinho tem nota publica e nosso scraping esta incompleto:
- ele nao deve cair automaticamente para contextual

### 19.4. `uvas` como possivel eixo principal

Isso foi descartado.

`uvas` ficou restrito ao papel de refinador opcional.

### 19.5. `pais_nome` como candidato serio a eixo tecnico imediato

Tambem foi descartado.

`pais` segue como eixo tecnico canonico.

---

## 20. O que ficou conceitualmente fechado e o que ainda depende de especificacao tecnica

### 20.1. Fechado

- a Cascata B e a escolhida
- `pais` e o campo tecnico da cascata
- `pais_nome` e campo de exibicao
- clamp fixo `-0,30 / +0,20`
- `nota_base` com media ponderada e teto `min(n,50)`
- penalidade contextual so para `n=0`, com formula `-0.5 * bucket_stddev`
- `25-74 total_ratings = estimated`
- `75+ total_ratings = verified` sempre
- `nota_wcf_sample_size >= 25` e o corte para WCF assumir como fonte numerica principal
- `nota_wcf_sample_size < 25` usa Vivino como ancora, com `delta_contextual` quando houver suporte
- sem contexto suficiente para delta, o fallback e Vivino direto com 2 casas
- vinho com nota publica e WCF raso nao deve cair para contextual
- Vivino e ancora forte para o fallback desses casos
- o usuario ve buckets publicos `25+`, `50+`, `100+`, `200+`, `300+`, `500+`
- `500+` e apenas rotulo visual; o dado bruto de ratings deve ser preservado integralmente

### 20.2. Ainda nao transformado em especificacao operacional exata

Este ponto precisa ser escrito com honestidade:

o principio de produto esta fechado, e o crossover principal tambem:
- `75+ total_ratings` define `verified`
- `25+ reviews WCF` define uso de WCF como fonte numerica principal
- abaixo de `25` reviews WCF, usar Vivino ancorado por `delta_contextual` quando houver contexto suficiente
- sem contexto suficiente, usar Vivino direto com 2 casas

O que ainda depende de especificacao tecnica de implementacao:
- thresholds minimos para aceitar um `delta_contextual` como confiavel
- se o delta sera media robusta, mediana ou outro agregador defensavel
- como persistir os buckets de contexto e os deltas
- o contrato final de nomes/campos para expor `source` interno e `public_ratings_bucket`

Isso **nao significa** que a definicao de produto esteja em aberto.

Significa apenas:
- o conceito foi fechado
- a engenharia ainda precisa materializar os detalhes em codigo, migrations e testes

---

## 21. Leitura correta para qualquer nova IA que retomar daqui

Se uma nova IA reabrir esta frente, ela deve partir destas premissas:

1. O WCF antigo continua sendo a base numerica principal do sistema.
2. A v2 nao quer matar WCF; quer protegelo quando a amostra e pequena.
3. A cascata vencedora e a **B**, nao a original de 7 degraus.
4. O problema mais estrutural de cobertura nao e a cascata; e a falta de `pais`.
5. `uvas` nao vira degrau principal.
6. Para vinhos com nota publica forte, `total_ratings` importa mais para o selo do que o sample local do scraping.
7. Os `309.616` vinhos nao sao "fracos"; eles sao vinhos com evidencia publica e captura local incompleta.
8. E injusto deixar um sample WCF muito pequeno mandar sozinho num vinho que ja tem nota publica forte.
9. O fallback provisoriamente correto para esses casos e Vivino ancorado/ajustado, nao contextual puro.
10. Este handoff fecha produto; o proximo trabalho e traduzir isso em especificacao tecnica e implementacao.

---

## 22. Referencias cruzadas recomendadas

Para discutir cobertura e cascata:
- `prompts/nota_wcf_v2_research/04_RESULTADO_CASCATA_COBERTURA_E_UVAS.md`

Para discutir `pais` vs `pais_nome`:
- `prompts/nota_wcf_v2_research/01_ESTUDO_PAIS_VS_PAIS_NOME.md`

Para discutir `nota_base`:
- `reports/2026-04-12_pesquisa_05_nota_base_penalidade_fallback.md`

Para discutir clamp e thresholds antigos:
- `reports/2026-04-12_estudo_clamp_e_confianca.md`

Para discutir a linha historica completa da v2:
- `reports/2026-04-11_handoff_nota_wcf_v2.md`

Para discutir o gap dos `309k` e a evidencia bruta do scraping incompleto:
- `prompts/HANDOFF_WCF_REVIEW_GAP_2026-04-15.md`

Para ver o runtime atual que ainda esta atras do fechamento de produto:
- `backend/services/display.py`
- `scripts/calc_score.py`
- `scripts/calc_wcf_fast.py`

---

## 23. Frase final que resume o estado da frente

A frente `nota_wcf v2` deixou de ser apenas uma discussao sobre shrinkage e cascata; ela virou uma redefinicao mais justa da relacao entre **evidencia publica**, **coleta real de reviews**, **nota contextual** e **confianca exibida ao usuario**.

O fechamento atual diz:
- usar WCF como base
- usar a Cascata B como contexto
- usar `total_ratings` para o selo publico
- considerar `75+ total_ratings` como `verified` sempre
- usar `25+ reviews WCF` como corte para WCF assumir a fonte numerica principal
- usar Vivino como ancora forte quando a evidencia publica existe mas o scraping ainda esta incompleto
- exibir ratings publicos em buckets `25+` ate `500+`, sem truncar o dado bruto
- e reservar `contextual` para quem realmente nao tem base publica suficiente
