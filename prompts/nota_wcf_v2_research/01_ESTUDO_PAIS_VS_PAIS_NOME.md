# Pesquisa 1: Campo `pais` vs `pais_nome`

Quero que você atue como pesquisador técnico e de modelagem de dados do WineGod.

Seu trabalho nesta aba não é implementar nada. É estudar qual é a melhor forma de sair da duplicidade entre os campos `pais` e `pais_nome` sem perder contexto, sem criar inconsistência e sem atrapalhar o sistema de notas.

Importante:
- não execute alterações no banco
- não gere migration
- não edite código de produção
- trabalhe apenas em modo leitura, análise e recomendação

## Contexto do problema

Hoje existem dois campos ligados a país na tabela `wines`:
- `pais` -> código ISO de 2 letras
- `pais_nome` -> nome por extenso

No desenho atual da `nota_wcf v2`, a cascata passou a usar `pais`, não `pais_nome`, porque `pais_nome` parecia incompleto.

Medição já feita e que você deve considerar como ponto de partida:
- casos com `pais` vazio e `pais_nome` preenchido = `0`
- casos com `pais` preenchido e `pais_nome` vazio = `263.950`

Ou seja:
- hoje `pais_nome` não ajuda a recuperar contexto que `pais` não tenha
- o caminho mais óbvio parece ser preencher `pais_nome` a partir de `pais`, não o contrário

Mas o fundador tem uma preferência conceitual:
- ele prefere trabalhar com o nome completo do país, não com sigla, se isso for seguro e sustentável

Sua função é estudar isso sem viés.

## O que já está decidido

Não reabra estes pontos:
- o sistema de notas vai usar país na cascata
- a duplicidade `pais` vs `pais_nome` não deve continuar indefinidamente
- o objetivo é eventualmente ficar com um modelo mais limpo e menos confuso

## O que você precisa responder

1. Qual é a situação real dos dois campos hoje?
- quantos vinhos têm só `pais`
- quantos têm só `pais_nome`
- quantos têm ambos
- quantos têm ambos vazios
- quantos têm conflito aparente entre `pais` e `pais_nome`

2. `pais_nome` hoje é confiável o suficiente para virar campo canônico?
- ele está padronizado?
- há variações de idioma?
- há diferenças de grafia?
- há nomes ruins, parciais ou inconsistentes?

3. `pais` hoje é mais seguro como campo canônico?
- é mais padronizado?
- permite backfill confiável de `pais_nome`?
- tem menor risco de sujeira?

4. Se a meta for “ficar com um campo só”, qual é a melhor escolha?
- manter `pais` e derivar o nome na exibição?
- migrar tudo para `pais_nome` por extenso?
- manter tecnicamente `pais`, mas expor sempre nome completo em produto?

5. Qual é o plano mais seguro para eliminar um dos campos no futuro?
- etapas
- riscos
- dependências
- rollback conceitual

6. Quais impactos isso tem na cascata da nota?
- cobertura
- consistência
- risco de reduzir contexto

## O que você deve investigar

No banco:
- distribuição real dos dois campos
- conflitos entre código e nome
- cardinalidade de valores
- exemplos de valores ruins

No código:
- onde `pais` é usado
- onde `pais_nome` é usado
- se algum deles é apenas de exibição
- se algum deles alimenta score, busca, ranking ou filtros

Nos documentos:
- conferir se o schema, o CTO doc e o handoff descrevem uso coerente ou contraditório

## Perguntas de decisão que quero respondidas

Quero que você me diga, com clareza:
- é seguro adotar `pais_nome` como campo único?
- é mais seguro manter `pais` como canônico e preencher/exibir `pais_nome`?
- existe algum cenário em que apagar um dos dois agora seria erro?

## Entregável esperado

Responda em tópicos curtos, mas completos:

1. Resumo executivo
2. Estado atual real dos campos
3. Principais problemas encontrados
4. Opções de arquitetura
5. Prós e contras de cada opção
6. Recomendação final
7. Plano sugerido em etapas
8. Riscos
9. O que ainda não deu para provar

## Critério de qualidade

Eu não quero uma resposta diplomática nem genérica.
Quero uma recomendação prática, baseada em dados reais do banco e do código.
