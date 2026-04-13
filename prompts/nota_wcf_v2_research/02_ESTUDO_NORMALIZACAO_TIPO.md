# Pesquisa 2: Normalização do campo `tipo`

Quero que você atue como pesquisador de qualidade de dados e arquitetura de classificação no WineGod.

Sua missão nesta aba é estudar como normalizar o campo `tipo` para sustentar a `nota_wcf v2`.

Importante:
- não implemente nada
- não altere banco
- não altere código de produção
- este trabalho é somente de estudo e proposta

## Contexto do problema

Na cascata da `nota_wcf v2`, `tipo` é obrigatório.

`tipo` aqui significa a categoria ampla do vinho, por exemplo:
- `tinto`
- `branco`
- `rose` / `Rosé`
- `espumante`
- `sobremesa`
- `fortificado`

Ele não é:
- uva
- safra
- região
- estilo detalhado

Motivo de `tipo` ser obrigatório:
- evita comparar coisas absurdamente diferentes
- por exemplo, espumante com tinto

Medição já conhecida:
- há ruído real de grafia e caixa
- exemplos atuais:
  - `tinto` = `1.086.314`
  - `Tinto` = `115.044`
  - `branco` = `606.861`
  - `Branco` = `99.984`
  - `espumante` = `156.618`
  - `Espumante` = `30.839`
  - `rose` = `106.783`
  - `Rosé` = `21.077`
  - `Sobremesa` e `sobremesa`
  - `fortificado` e `Fortificado`

## O que já está decidido

Não reabra estes pontos:
- `tipo` vai continuar existindo
- `tipo` vai continuar sendo obrigatório na cascata
- precisamos normalizar esse campo

## O que você precisa responder

1. Qual é o inventário real de valores atuais de `tipo`?
- todos os valores distintos
- frequência de cada um
- variantes óbvias
- valores estranhos ou ambíguos

2. Qual deveria ser o conjunto canônico de `tipo` para a v2?
- poucos tipos amplos?
- incluir categorias novas?
- o que entra e o que não entra?

3. Como mapear os valores atuais para o conjunto canônico?
- caixa
- acento
- sinônimos
- grafias mistas
- categorias compostas

4. Quais valores são perigosos para normalizar automaticamente?
- exemplos ambíguos
- riscos de juntar coisas diferentes no mesmo tipo

5. O que fazer com valores fora do padrão?
- jogar em `outro`?
- deixar `NULL`?
- tentar inferir por outros campos?

6. Como essa normalização impacta a cascata?
- cobertura
- precisão
- risco de falsos agrupamentos

## O que você deve investigar

No banco:
- lista completa de valores de `tipo`
- distribuição
- vazios
- raridades

No código:
- onde `tipo` já é usado hoje
- se há filtros, buscas, ordenações ou telas que assumem valores específicos

No desenho de produto:
- se faz mais sentido trabalhar com `tipo` mínimo e robusto
- ou com um conjunto mais rico, porém mais frágil

## O que eu quero como resposta

1. Resumo executivo
2. Inventário do estado atual
3. Proposta de taxonomia canônica
4. Tabela de mapeamento sugerida
5. Casos ambíguos
6. Riscos
7. Recomendação final
8. Plano de normalização em etapas

## Regras de rigor

- não invente taxonomia só por gosto
- se propuser novas categorias, justifique com dados do banco
- se um valor for ambíguo, marque como ambíguo
- diga claramente o que pode ser normalizado com segurança e o que não pode
