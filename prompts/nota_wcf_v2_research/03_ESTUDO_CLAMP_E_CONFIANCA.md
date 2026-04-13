# Pesquisa 3: Clamp, confiança e thresholds `25 / 50 / 100`

Quero que você atue como pesquisador estatístico e de produto para a camada de confiança da `nota_wcf v2`.

Esta aba deve estudar:
- clamp contra Vivino
- clamp fixo vs progressivo
- thresholds de confiança (`25`, `50`, `100`)
- efeito prático disso na tese do produto

Importante:
- não implemente nada
- não altere código
- não altere banco
- faça estudo e recomendação

## Contexto do problema

O WineGod quer usar `nota_wcf` como nota oficial.

Mas existe uma tensão:
- se ficar preso demais ao Vivino, o sistema não descobre nada novo
- se soltar demais, pode delirar e dar nota alta sem lastro

Medições já conhecidas:
- correlação `nota_wcf` vs `vivino_rating` = `0,916369`
- delta médio `nota_wcf - vivino_rating` = `-0,050294`
- thresholds atuais no CSV:
  - `25+` = `388.078`
  - `50+` = `248.850`
  - `100+` = `147.122`

Direção atual não fechada:
- `contextual = 0`
- `estimated = 1–99`
- `verified = 100+`
- clamp candidato atual = `vivino - 0,30 / vivino + 0,20`

Mas isso ainda não está encerrado.

## O que já está decidido

Não reabra estes pontos:
- `nota_wcf_sample_size` é credibilidade, não trava de existência da nota
- o produto quer distinguir níveis de confiança
- o sistema continua conceitualmente atrelado ao Vivino em alguma medida
- a tese do produto não quer transformar fama antiga em vantagem infinita

## O que você precisa responder

1. O que a correlação `0,916` realmente significa para o produto?
- isso é bom?
- isso é ruim?
- isso limita ou fortalece a tese do WineGod?
- qual parte da diferenciação do WG sobra se a correlação já é tão alta?

2. O clamp fixo atual faz sentido?
- `-0,30 / +0,20`
- ele protege o sistema ou mata discovery?
- em quais caudas ele mais interfere?

3. O clamp progressivo faz mais sentido?
- o que seria, na prática?
- por faixa de `n`?
- por nível de confiança?
- por distância em relação ao Vivino?

4. Quero exemplos reais do banco
- pelo menos um caso com `n` em `25–49`
- um em `50–99`
- um em `100+`
- um caso de cauda negativa
- mostrar como ficaria:
  - sem clamp
  - clamp fixo
  - clamp progressivo

5. Sobre confiança: `verified` deve ser `25`, `50` ou `100`?
- quantos vinhos entram em cada corte
- o que isso muda no produto
- o que isso muda na honestidade do selo

6. Como isso conversa com a tese do fundador?
- valorizar vinhos novos
- não premiar demais volume histórico
- manter lastro

## O que você deve investigar

No banco e CSV:
- distribuição de `n`
- caudas positivas e negativas do delta
- impacto de clamps mais soltos ou mais apertados
- quantos vinhos seriam afetados por diferentes thresholds

No código:
- como `display.py` e `calc_score.py` usam isso hoje
- que comportamentos atuais precisariam mudar conceitualmente

## O que eu quero como resposta

1. Resumo executivo
2. Interpretação da correlação `0,916`
3. Análise do clamp fixo atual
4. Análise de clamp progressivo
5. Exemplos reais
6. Estudo de `25 / 50 / 100`
7. Riscos de cada opção
8. Recomendação final
9. O que ainda ficou incerto

## Regras de rigor

- não trate correlação alta como prova de cópia
- não trate “mais liberdade” como automaticamente melhor
- não trate “mais preso ao Vivino” como automaticamente mais seguro
- se recomendar clamp progressivo, escreva uma regra concreta, não só conceito
