INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia o codigo atual antes de editar. Implemente ponta a ponta, rode os testes relevantes, corrija as falhas e reteste ate tudo passar ou ate existir bloqueio externo real.

# CHAT MEDIA-2: Multiplas Fotos + Screenshot + Prateleira

## CONTEXTO

WineGod.ai ja processa uma foto de rotulo via `process_image`. Agora a feature precisa evoluir para:
- multiplas fotos por mensagem
- screenshots e prints de tela
- fotos de prateleira com varios vinhos

## REPO

`C:\winegod-app` com backend em `backend/` e frontend em `frontend/`.

## MANDATO DE EXECUCAO

1. Inspecione o codigo atual antes de editar.
2. Ajuste todos os contratos necessarios entre frontend, backend e credito.
3. Rode os testes e checks deste prompt antes de encerrar.
4. Se algo falhar, corrija e rode de novo.
5. So pare por bloqueio externo real.

## SITUACAO ATUAL

Hoje:
- `backend/tools/media.py` processa uma unica imagem base64
- `backend/routes/chat.py` so conhece `image`
- `frontend/components/ChatInput.tsx` so envia uma foto
- `frontend/lib/api.ts` e `frontend/app/page.tsx` usam contrato de envio singular para imagem

## O QUE VOCE VAI FAZER

### 1. Multiplas fotos no frontend

Atualizar `frontend/components/ChatInput.tsx` para:
1. Permitir selecao de ate 5 fotos.
2. Mostrar preview de todas as fotos em grid.
3. Permitir remover cada imagem individualmente.
4. Mostrar contador visual, como `3/5 fotos`.
5. Rejeitar excedente com mensagem amigavel.
6. Enviar `images` como array de base64.
7. Manter compatibilidade com 1 foto.
8. Redimensionar cada foto individualmente com a logica atual.

Tambem ajustar o contrato real em:
- `frontend/lib/api.ts`
- `frontend/app/page.tsx`

### 2. Batch de imagens no backend

Implementar em `backend/tools/media.py`:
- `process_images_batch(images)`

Fluxo:
1. Receber array de imagens base64.
2. Processar uma a uma com a logica principal de imagem.
3. Consolidar resultados.
4. Deduplicar vinhos repetidos.
5. Retornar estrutura amigavel para o chat.

### 3. Prompt unificado de imagem

Evoluir `process_image` para detectar e lidar com 4 cenarios:
1. `label`
2. `screenshot`
3. `shelf`
4. `not_wine`

O prompt do Gemini deve decidir o tipo e retornar JSON consistente.

Requisitos por tipo:
- `label`: nome, produtor, safra, regiao, uva
- `screenshot`: lista de vinhos + preco + nota + fonte quando visivel
- `shelf`: lista de vinhos visiveis + preco quando visivel + contagem
- `not_wine`: descricao amigavel do que foi detectado

Nao faca classificacao dupla desnecessaria se der para resolver em um unico prompt.

### 4. Integracao no chat

Atualizar `backend/routes/chat.py` para:
1. Aceitar `images` no payload.
2. Usar `process_images_batch` quando vier array.
3. Gerar contexto especifico para label, screenshot e shelf.
4. Preservar compatibilidade com o fluxo existente de 1 foto.

### 5. Creditos

O sistema atual usa `message_log` com custo implicito de 1. Isso nao suporta regra de custo variavel sozinho.

Implementar corretamente:
- 1 foto = custo 1
- 2 a 5 fotos = custo 3
- screenshot = custo 1
- shelf = custo 1

Para isso, ajustar:
- `backend/routes/credits.py`
- `backend/db/models_auth.py`

### 6. Descricao das tools

Se `process_image` ganhar capacidade significativamente maior, atualize a descricao correspondente em `backend/tools/schemas.py` para nao deixar a tool documentada de forma defasada.

## CREDENCIAIS

Usar apenas o que ja existe:
- `GEMINI_API_KEY`

## ARQUIVOS QUE PODEM SER MODIFICADOS

- `backend/tools/media.py`
- `backend/routes/chat.py`
- `backend/routes/credits.py`
- `backend/db/models_auth.py`
- `backend/tools/schemas.py`
- `frontend/components/ChatInput.tsx`
- `frontend/lib/api.ts`
- `frontend/app/page.tsx`

## ARQUIVOS QUE NAO DEVEM SER MODIFICADOS

- `backend/app.py`
- `backend/services/baco.py`

## COMO TESTAR

Voce DEVE rodar os checks abaixo antes de encerrar. Se algo falhar, corrija e rode novamente.

```powershell
# Backend - sintaxe/imports/rotas
cd C:\winegod-app\backend
python -m compileall .
@'
from app import create_app
from tools.media import process_image, process_images_batch

app = create_app()
routes = sorted(str(rule) for rule in app.url_map.iter_rules())
print("chat_route_ok", any("/api/chat" in route for route in routes))
print("batch_callable_ok", callable(process_images_batch))
'@ | python -

# Frontend - lint e build
cd C:\winegod-app\frontend
npm run lint
npm run build
```

Validacao adicional obrigatoria:
- Se houver fixtures locais ou se for seguro criar temporarios, rode smoke test real para `label`, `screenshot` e batch
- Nao dependa de arquivos `test_label.jpg`, `test_screenshot.png` ou `test1.jpg` inexistentes no repo
- Se o ambiente nao permitir chamada real ao Gemini, valide pelo menos contrato, parsing e caminhos de erro sem quebrar o app

## O QUE NAO FAZER

- NAO modificar `backend/app.py`
- NAO modificar `backend/services/baco.py`
- NAO fazer git commit ou push
- NAO quebrar a compatibilidade com uma unica foto
- NAO criar endpoints novos
- NAO fazer deteccao de screenshot no frontend
- NAO encerrar sem rodar os testes deste prompt

## ENTREGAVEL

Quando terminar, deve existir:
1. Frontend com ate 5 fotos e preview em grid
2. Backend com `process_images_batch`
3. `process_image` capaz de distinguir `label`, `screenshot`, `shelf` e `not_wine`
4. Contextos corretos no chat para cada tipo
5. Creditos variaveis implementados corretamente
6. Testes/checks executados, com correcao e reteste se algo falhar
