# Pesquisa 6: Estudo para remoção segura de `nota_estimada`

Quero que você atue como pesquisador técnico de impacto, dependências e migração para a remoção do campo `nota_estimada`.

Importante:
- não execute nenhuma remoção
- não altere código
- não altere banco
- esta aba deve apenas estudar a forma mais segura de remover esse campo no futuro

## Contexto do problema

Na `nota_wcf v2`, `nota_estimada` saiu da decisão do produto.

Motivo:
- cria confusão conceitual
- induz erro humano
- pode fazer IA ou scripts confundirem `nota_estimada` com a nota oficial

Mas o campo não pode ser apagado cegamente porque já foi confirmado que ainda existe escrita nele fora deste repositório:
- `C:\Users\muril\vivino-broker\server.js`

O objetivo agora é estudar:
- quem ainda lê
- quem ainda escreve
- qual seria o plano seguro para desativar
- quando seria seguro apagar do banco

## O que já está decidido

Não reabra estes pontos:
- `nota_estimada` não entra mais na decisão da nota oficial
- o campo idealmente deve sair do sistema
- a remoção deve ser segura e em etapas

## O que você precisa responder

1. Onde `nota_estimada` ainda existe hoje?
- neste repositório
- em repositórios relacionados
- em scripts
- em documentos
- em integrações

2. Quem ainda escreve nesse campo?
- backend
- broker
- jobs
- importadores
- migrations antigas

3. Quem ainda lê esse campo?
- backend
- score
- ranking
- painéis
- relatórios

4. Qual é o plano mais seguro para remover?
- etapa 1: parar de usar
- etapa 2: parar de escrever
- etapa 3: monitorar
- etapa 4: migration
- etapa 5: limpeza documental

5. Quais riscos existem?
- quebrar fluxo legado
- deixar dependência escondida
- gerar inconsistência em scripts antigos

## O que você deve investigar

No código:
- buscas completas por `nota_estimada`
- uso indireto
- serialização
- payloads
- SQLs

No banco:
- existência da coluna
- possíveis views ou jobs que dependam dela

Nos documentos:
- qualquer lugar que ainda a trate como conceito válido

## O que eu quero como resposta

1. Resumo executivo
2. Inventário de dependências
3. Escritores ainda ativos
4. Leitores ainda ativos
5. Plano de desativação seguro
6. Critérios para saber que já é seguro apagar
7. Riscos
8. Recomendação final

## Regras de rigor

- não diga “pode apagar” sem mapear dependências
- não trate ausência de resultados em um repo como prova de ausência no sistema inteiro
- se existir dependência fora deste repo, destaque isso claramente
