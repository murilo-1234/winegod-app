INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia o codigo atual antes de editar. Implemente ponta a ponta, rode os testes relevantes, corrija as falhas e reteste ate tudo passar ou ate existir bloqueio externo real.

# CHAT MEDIA-1: Video + PDF + Voz

## CONTEXTO

WineGod.ai e uma IA sommelier global. O backend Flask ja tem `process_image` funcionando para OCR de rotulos via Gemini. Os stubs `process_video`, `process_pdf` e `process_voice` existem, mas ainda nao entregam a feature completa. Sua tarefa e implementar tudo de ponta a ponta.

## REPO

`C:\winegod-app` com backend em `backend/` e frontend em `frontend/`.

## MANDATO DE EXECUCAO

1. Inspecione os arquivos atuais antes de editar para alinhar o prompt ao codigo real.
2. Ajuste todos os contratos necessarios entre frontend, backend e credito. Nao pare no meio por causa de tipagem, payload ou schema.
3. Rode os testes e checks deste prompt antes de encerrar.
4. Se algo falhar, corrija e rode de novo.
5. So pare por bloqueio externo real, como binario `ffmpeg` ausente, credencial faltando ou servico externo indisponivel.

## O QUE VOCE VAI FAZER

### 1. `process_video` em `backend/tools/media.py`

Implementar processamento de video com este fluxo:
1. Receber video em base64.
2. Validar tamanho maximo de 50 MB.
3. Salvar em arquivo temporario.
4. Validar duracao maxima de 30 segundos.
5. Extrair 1 frame por segundo, no maximo 30 frames, usando `ffmpeg-python`.
6. Redimensionar cada frame para no maximo 1024 px no maior lado.
7. Enviar cada frame ao Gemini com um prompt focado em rotulos, nomes de vinhos, produtor, safra, regiao e preco.
8. Consolidar os resultados, deduplicando vinhos repetidos entre frames.
9. Retornar estrutura amigavel em portugues, com lista consolidada e texto pronto para contexto do chat.
10. Limpar todos os temporarios no `finally`.

Especificacoes:
- Formatos aceitos: `mp4`, `mov`, `webm`, `avi`
- Se nenhum vinho for encontrado, retornar mensagem amigavel
- Se `ffmpeg` nao existir no sistema, falhar de forma controlada e explicita

### 2. `process_pdf` em `backend/tools/media.py`

Implementar processamento de PDF com este fluxo:
1. Receber PDF em base64.
2. Validar tamanho maximo de 20 MB.
3. Salvar em arquivo temporario.
4. Ler ate 20 paginas com `pdfplumber`.
5. Concatenar o texto extraido.
6. Se o texto for suficiente, enviar ao Gemini para identificar todos os vinhos mencionados.
7. Se o texto vier muito pobre, tratar como PDF-imagem: renderizar as paginas como imagem e fazer OCR visual pagina a pagina.
8. Consolidar os vinhos encontrados e retornar estrutura amigavel para o chat.
9. Limpar temporarios no `finally`.

Especificacoes:
- Maximo de 20 paginas
- Para OCR de PDF-imagem, use dependencia que de fato renderize pagina em imagem. Nao presuma que `pdfplumber` sozinho resolve isso.
- Se nenhuma informacao util for encontrada, retornar mensagem amigavel

### 3. Voz no frontend

O backend ja recebe texto transcrito. Nao invente STT server-side.

Implementar no `frontend/components/ChatInput.tsx`:
1. Botao de microfone.
2. Uso de `SpeechRecognition` / `webkitSpeechRecognition` quando houver suporte.
3. Indicador visual de gravacao.
4. Transcricao preenchendo o input para edicao antes do envio.
5. Esconder o botao se o browser nao suportar a API.

### 4. Upload de video e PDF no frontend

Atualizar o fluxo do chat para suportar anexos de video e PDF:
1. Em `ChatInput.tsx`, adicionar menu de anexo com Foto, Video e PDF.
2. Video: aceitar `video/*`, maximo 50 MB, preview simples e envio como `video` no payload.
3. PDF: aceitar `.pdf`, maximo 20 MB, preview simples e envio como `pdf` no payload.
4. Ajustar o contrato real do frontend para suportar esses campos sem quebrar o envio atual de imagem.

### 5. Integracao no backend do chat

Atualizar `backend/routes/chat.py` para:
1. Detectar `video` no payload e chamar `process_video`.
2. Detectar `pdf` no payload e chamar `process_pdf`.
3. Gerar contexto textual apropriado para o Claude antes da mensagem do usuario.
4. Preservar compatibilidade com o fluxo atual de `image`.
5. Se fizer sentido, extrair um helper mais geral de media em vez de manter `_process_image_context` limitado a foto.

### 6. Creditos

O sistema atual registra 1 uso por mensagem em `message_log`. Isso nao suporta custo variavel sozinho.

Implemente corretamente:
- Texto, voz e foto = custo 1
- Video = custo 3
- PDF = custo 3

Para isso, ajuste:
- `backend/routes/credits.py` para derivar custo do payload
- `backend/db/models_auth.py` para persistir e somar custo em vez de assumir sempre 1

Se precisar alterar o schema da tabela `message_log`, faca de forma retrocompativel.

## DEPENDENCIAS

Adicionar em `backend/requirements.txt`:

```txt
ffmpeg-python>=0.2.0
pdfplumber>=0.11.0
Pillow>=10.0.0
pypdfium2>=4.30.0
```

Importante:
- `ffmpeg-python` e apenas wrapper. O binario `ffmpeg` precisa existir no sistema.
- No Render, isso provavelmente exigira ajuste externo no build/deploy. Se esse for o unico bloqueio restante, documente-o claramente.

## CREDENCIAIS

Usar apenas o que ja existe no `.env`:
- `GEMINI_API_KEY`

Nenhuma credencial nova deve ser inventada.

## ARQUIVOS QUE PODEM SER MODIFICADOS

- `backend/tools/media.py`
- `backend/routes/chat.py`
- `backend/routes/credits.py`
- `backend/db/models_auth.py`
- `backend/requirements.txt`
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
from tools.media import process_voice, process_video, process_pdf

print(process_voice("teste de voz"))
app = create_app()
routes = sorted(str(rule) for rule in app.url_map.iter_rules())
print("chat_route_ok", any("/api/chat" in route for route in routes))
'@ | python -

# Frontend - lint e build
cd C:\winegod-app\frontend
npm run lint
npm run build
```

Validacao adicional obrigatoria:
- Se houver fixtures locais ou se for seguro criar temporarios, rode smoke test real de `process_pdf` e `process_video`
- Nao dependa de arquivos `test.pdf` ou `test.mp4` inexistentes no repo
- Se `ffmpeg` nao existir no PATH, valide que a falha e amigavel e documente o bloqueio externo

## O QUE NAO FAZER

- NAO modificar `backend/app.py`
- NAO modificar `backend/services/baco.py`
- NAO fazer git commit ou push
- NAO usar Whisper ou outra API de voz no backend
- NAO criar endpoints novos
- NAO encerrar sem rodar os testes deste prompt

## ENTREGAVEL

Quando terminar, deve existir:
1. `process_video` funcional e robusto
2. `process_pdf` funcional e robusto
3. Botao de microfone no frontend
4. Upload de video e PDF no fluxo real do chat
5. Creditos variaveis implementados corretamente
6. Testes/checks executados, com correcao e reteste se algo falhar
