# Executor - Foto de Cardapio / Lista

Voce vai executar a proxima sprint de cobertura de midia do WineGod: foto de cardapio/lista.

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

- o fluxo de imagem atual passa por `C:\winegod-app\backend\tools\media.py`
- hoje a classificacao principal e `label`, `screenshot`, `shelf`, `not_wine`
- `shelf` ja recebeu OCR estruturado, matching endurecido, contexto batch melhor e estados explicitos
- foto de cardapio/lista ainda nao deve ser tratada como fluxo dedicado resolvido

## Escopo exato desta sprint

Melhorar o fluxo de IMAGEM para:
- foto de cardapio
- foto de carta
- foto de lista/catalogo impresso

Isso NAO inclui:
- PDF
- video
- text upload
- reabrir matching de shelf

## Arquivos-alvo

- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\routes\chat.py`
- opcionalmente 1 teste pequeno focado em imagem/contexto

## Arquivos que voce pode ler para contexto

- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\routes\chat.py`
- `C:\winegod-app\backend\tools\resolver.py`
- `C:\winegod-app\prompts\HANDOFF_MEDIA_P3B_FOTO_CARDAPIO.md`

## Arquivos que voce NAO deve tocar

- `C:\winegod-app\backend\tools\search.py`
- `C:\winegod-app\backend\prompts\baco_system.py` salvo necessidade minima e muito bem justificada
- frontend salvo bug claro de payload/preview
- deploy
- qualquer refatoracao ampla fora desta frente

## Regras de produto

- foto de cardapio/lista e fluxo de IMAGEM, nao de PDF
- precos da imagem devem ser tratados como ancora visual da cena quando houver associacao razoavel
- melhor omitir do que inventar item ou preco
- nao fingir confirmacao forte de banco se o fluxo for so visual
- nao confundir cardapio/lista com shelf lotada de garrafas

## O que voce deve fazer

1. Ler o fluxo atual de `process_image()` em `C:\winegod-app\backend\tools\media.py`
2. Identificar como foto de cardapio/lista esta sendo classificada hoje
3. Melhorar o pipeline minimo para este tipo de imagem, sem quebrar `label`, `shelf` e `screenshot`
4. Ajustar o contexto em `C:\winegod-app\backend\routes\chat.py` se necessario
5. Validar com foco em nome/preco/sections, sem misturar com PDF

## Restricoes

- Nao misturar esta sprint com PDF
- Nao reabrir matching de shelf
- Nao reescrever prompt/persona do Baco como solucao principal
- Nao assumir deploy automatico
- Melhor mudanca pequena e correta do que redesign

## Criterios de sucesso

- uma foto de cardapio gera resposta util
- uma foto de lista/catalogo gera resposta util
- precos da imagem sao tratados como ancora visual
- o sistema nao inventa itens nao lidos
- nao ha regressao em `label`, `shelf` e `screenshot`

## O que eu NAO aceito como entrega

- misturar foto de cardapio com PDF
- texto bonito sem codigo
- reabrir `resolver.py` ou `search.py` sem necessidade real
- "funciona em tese" sem evidencia de validacao

## Sugestoes de validacao

- uma foto simples de cardapio
- uma foto com varios precos
- uma foto com secoes/titulos
- uma foto inclinada ou com qualidade media

## Formato obrigatorio do relatorio final

1. `Diagnostico do fluxo atual`
2. `O que mudou no pipeline de imagem`
3. `O que mudou no contexto enviado ao Baco`
4. `Testes e validacoes executados`
5. `Riscos restantes`

## Importante

- Nao diga que foi deployado
- Se nao rodar algum teste, diga isso explicitamente
- Melhor output honesto do que leitura "milagrosa"
