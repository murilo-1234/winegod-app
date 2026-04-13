# Executor - PDF

Voce vai executar a proxima sprint de cobertura de midia do WineGod: PDF.

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

- `label`, `shelf`, `screenshot` e `multiplas fotos` ja tiveram trabalho real no request path
- `shelf` ja recebeu OCR estruturado, matching endurecido, contexto batch melhor e estados explicitos
- o fluxo de PDF ja existe:
  - `process_pdf()` em `C:\winegod-app\backend\tools\media.py`
  - extrai texto com `pdfplumber`
  - se necessario, faz fallback visual com `pypdfium2` + Gemini
  - entrega descricao textual em `C:\winegod-app\backend\routes\chat.py`
- isso NAO significa que PDF esta validado como fluxo robusto

## Escopo exato desta sprint

Melhorar o fluxo de PDF como DOCUMENTO.

Isso inclui:
- PDF nativo com texto
- PDF escaneado
- carta, catalogo ou lista de vinhos em PDF

Isso NAO inclui:
- foto de cardapio/lista
- video
- text upload
- reabrir matching

## Arquivos-alvo

- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\routes\chat.py`
- opcionalmente 1 teste pequeno focado em PDF/contexto

## Arquivos que voce pode ler para contexto

- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\routes\chat.py`
- `C:\winegod-app\backend\tools\resolver.py`
- `C:\winegod-app\backend\prompts\baco_system.py`
- `C:\winegod-app\prompts\HANDOFF_MEDIA_P3_PDF_CARDAPIO.md`

## Arquivos que voce NAO deve tocar

- `C:\winegod-app\backend\tools\search.py`
- `C:\winegod-app\backend\prompts\baco_system.py` salvo necessidade minima e muito bem justificada
- frontend
- deploy
- qualquer refatoracao ampla fora do PDF

## Regras de produto

- PDF e fluxo de documento, nao de foto
- separar vinho de texto decorativo quando possivel
- associar preco ao item certo apenas quando houver ancora razoavel
- se nao houver confianca, melhor omitir do que inventar
- deixar claro quando o fluxo esta so descrevendo itens lidos e quando houver confirmacao real
- NAO fingir que PDF tem a mesma certeza de um label confirmado

## O que voce deve fazer

1. Ler o fluxo atual de `process_pdf()` em `C:\winegod-app\backend\tools\media.py`
2. Identificar onde PDF nativo e PDF escaneado falham ou ficam ambiguos
3. Melhorar o pipeline minimo para:
   - separar itens reais de ruido
   - preservar nome/preco quando confiavel
   - manter fallback honesto
4. Ajustar o contexto em `C:\winegod-app\backend\routes\chat.py` se necessario
5. Validar sem ampliar a frente para foto de cardapio/lista

## Restricoes

- Nao misturar esta sprint com foto de cardapio/lista
- Nao reabrir matching
- Nao reescrever prompt/persona do Baco como solucao principal
- Nao assumir deploy automatico
- Melhor mudanca pequena e correta do que redesign

## Criterios de sucesso

- PDF simples gera resposta util
- PDF com varios precos nao associa preco errado de forma grosseira
- PDF escaneado tem fallback honesto
- o sistema nao inventa itens nao lidos
- nao ha regressao nos fluxos de imagem

## O que eu NAO aceito como entrega

- misturar PDF com foto de cardapio/lista
- texto bonito sem codigo
- reabrir `resolver.py` ou `search.py` sem necessidade real
- "funciona em tese" sem evidencia de validacao

## Sugestoes de validacao

- um PDF simples de carta
- um PDF com varios precos
- um PDF com secoes/titulos
- um PDF escaneado

## Formato obrigatorio do relatorio final

1. `Diagnostico do fluxo atual`
2. `O que mudou no pipeline de PDF`
3. `O que mudou no contexto enviado ao Baco`
4. `Testes e validacoes executados`
5. `Riscos restantes`

## Importante

- Nao diga que foi deployado
- Se nao rodar algum teste, diga isso explicitamente
- Melhor output honesto do que PDF "magicamente perfeito"
