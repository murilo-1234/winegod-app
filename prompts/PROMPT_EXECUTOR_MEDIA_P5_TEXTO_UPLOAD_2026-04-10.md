# Executor - Texto Colado / Upload de Texto

Voce vai executar a proxima sprint de cobertura de midia do WineGod: texto colado / upload textual.

## Objetivo desta aba

Esta aba e a EXECUTORA.

Voce NAO vai rediscutir produto amplo.
Voce NAO vai abrir novas frentes.
Voce vai pegar um escopo curto e entregar codigo + validacao.

## Projeto

- app: `https://chat.winegod.ai/`
- backend: `https://winegod-app.onrender.com/healthz`
- repo local: `C:\winegod-app`

## Estado resumido aprovado

- o usuario ja pode colar texto diretamente no chat
- esta frente e separada de OCR e de arquivos visuais
- o caso real aqui e quando o usuario:
  - cola texto de um site
  - cola uma lista grande de vinhos
  - sobe um arquivo textual simples com muitas informacoes de vinhos
- ainda nao ha definicao fechada do menor escopo util para upload textual

## Escopo exato desta sprint

Definir e implementar o MENOR fluxo util para texto colado / upload textual.

Isso pode incluir, se fizer sentido:
- texto colado mais bem tratado
- `.txt`
- lista exportada simples

Isso NAO inclui:
- PDF
- foto de cardapio/lista
- video
- OCR
- suporte generico a "qualquer arquivo" sem recorte

## Arquivos-alvo

- `C:\winegod-app\backend\routes\chat.py`
- possivelmente helper novo pequeno no backend
- `C:\winegod-app\frontend\components\ChatInput.tsx`
- `C:\winegod-app\frontend\lib\api.ts`
- opcionalmente 1 teste pequeno focado em payload/contrato

## Arquivos que voce pode ler para contexto

- `C:\winegod-app\backend\routes\chat.py`
- `C:\winegod-app\frontend\components\ChatInput.tsx`
- `C:\winegod-app\frontend\lib\api.ts`
- `C:\winegod-app\prompts\HANDOFF_MEDIA_P5_TEXT_UPLOAD.md`

## Arquivos que voce NAO deve tocar

- `C:\winegod-app\backend\tools\search.py`
- `C:\winegod-app\backend\prompts\baco_system.py`
- `C:\winegod-app\backend\tools\media.py` salvo necessidade minima e muito bem justificada
- deploy
- qualquer refatoracao ampla do chat

## Regras de produto

- diferenciar claramente:
  - texto colado
  - upload textual simples
- nao vender "qualquer arquivo" se o fluxo real nao suportar isso
- se o menor escopo util for pequeno, manter pequeno
- se o ganho real for baixo, documentar isso com honestidade

## O que voce deve fazer

1. Ler o fluxo atual do chat e do frontend para texto e anexos
2. Definir o menor contrato util para texto colado / upload textual
3. Implementar apenas o minimo necessario
4. Validar sem misturar esta frente com PDF/foto/video

## Restricoes

- Nao transformar esta sprint em sistema generico de ingestao de documentos
- Nao misturar esta sprint com OCR
- Nao assumir deploy automatico
- Melhor fluxo pequeno e claro do que feature ampla e confusa

## Criterios de sucesso

- fica claro o que e texto colado e o que e upload textual
- o menor escopo util fica funcionando
- o chat nao fica mais confuso por causa disso
- nao ha regressao nos fluxos existentes

## O que eu NAO aceito como entrega

- feature textual enorme sem necessidade
- mistura com PDF/foto/video
- texto bonito sem codigo ou sem decisao clara
- "agora suporta qualquer arquivo" sem verdade tecnica

## Sugestoes de validacao

- texto colado de site com varios vinhos
- lista textual grande
- upload textual simples, se implementado
- caso vazio ou mal formatado

## Formato obrigatorio do relatorio final

1. `Diagnostico do fluxo atual`
2. `Escopo final escolhido`
3. `O que mudou no contrato/pipeline`
4. `Testes e validacoes executados`
5. `Riscos restantes`

## Importante

- Nao diga que foi deployado
- Se decidir que uma parte nao vale implementar agora, diga isso explicitamente
- Simplicidade e preferivel a uma pseudo-solucao generica
