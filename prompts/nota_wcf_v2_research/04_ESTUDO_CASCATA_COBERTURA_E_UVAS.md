# Pesquisa 4: Cobertura da cascata, reforço dos degraus amplos e uso de `uvas`

Quero que você atue como pesquisador de modelagem hierárquica e cobertura de produto para a `nota_wcf v2`.

Esta aba deve responder como dar nota para mais vinhos sem destruir a confiança da nota.

Importante:
- não implemente nada
- não altere banco ou código
- faça estudo, medições e proposta

## Contexto do problema

A cascata aprovada até aqui é:
- `vinícola + sub_regiao + tipo`
- `sub_regiao + tipo`
- `vinícola + regiao + tipo`
- `regiao + tipo`
- `vinícola + pais + tipo`
- `pais + tipo`
- `vinícola + tipo`
- senão `sem nota`

Mínimos por degrau aprovados até agora:
- `2 / 10 / 3 / 10 / 3 / 10 / 5`

Leitura já conhecida:
- a cascata estrutural parecia cobrir mais do que realmente cobre
- quando se exige suporte mínimo, a cobertura cai bastante
- os degraus amplos viram os mais importantes na prática

Também já sabemos:
- `uvas` tem cobertura baixa:
  - banco inteiro: `9,54%`
  - bloco sem nota real: `18,80%`

Mesmo assim, o fundador quer saber se existe alguma forma de usar `uvas` para ampliar cobertura com algum lastro.

## O que já está decidido

Não reabra estes pontos:
- `tipo` é obrigatório
- não usar `tipo global`
- não usar fallback global universal
- `vinícola + tipo` é o último degrau antes de `sem nota`

## O que você precisa responder

1. O que explica a perda de cobertura quando entram os mínimos por degrau?
- quais degraus concentram a cobertura real
- quais degraus ficaram quase decorativos

2. Como aumentar cobertura sem perder muita confiança?
- mudar mínimos por degrau?
- criar caminhos alternativos?
- reforçar buckets amplos com mais critérios?
- usar pesos dentro do balde?

3. Como fortalecer os degraus amplos?
- `regiao + tipo`
- `pais + tipo`
- `vinícola + tipo`

Quero ideias concretas, por exemplo:
- usar suporte mínimo maior?
- usar dispersão do balde?
- usar uva como refinador quando existir?
- usar produtor normalizado?
- usar safra ou não?

4. `uvas` pode ajudar nesta fase?
- não como eixo central obrigatório
- mas como reforço opcional?
- em quais cenários?
- isso aumenta cobertura ou só melhora precisão de poucos casos?

5. Quero opções reais de desenho
- opção mais conservadora
- opção intermediária
- opção mais abrangente

6. O que fazer com quem continua sem bucket?
- deixar sem nota
- fallback especial
- regra condicional

## O que você deve investigar

No banco:
- distribuição por degrau com e sem mínimos
- tamanho dos baldes
- campos adicionais disponíveis que possam ajudar
- cobertura e qualidade de `uvas`
- presença de `produtor_normalizado`
- qualquer outro campo que melhore contexto sem virar chute

## O que eu quero como resposta

1. Resumo executivo
2. Diagnóstico da cobertura atual
3. Por que a cascata perdeu cobertura
4. Como fortalecer os degraus amplos
5. Como `uvas` poderia ajudar
6. Opções de desenho com trade-offs
7. Recomendação final
8. O que ainda não foi provado

## Regras de rigor

- não proponha solução bonita que dependa de campo mal preenchido
- não trate `uvas` como salvação automática
- se sugerir usar `uvas`, explique exatamente onde ela entra e onde não entra
- cobertura maior só vale se a confiança continuar defensável
