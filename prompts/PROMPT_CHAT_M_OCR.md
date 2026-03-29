# CHAT M — Pipeline OCR (Gemini Flash)

## CONTEXTO

WineGod.ai e uma IA sommelier global. Um chat web onde o personagem "Baco" responde sobre vinhos. O backend e Flask + Claude API, o frontend e Next.js. O produto ja funciona: usuario digita, Baco busca no banco (1.72M vinhos) e responde.

Agora precisamos que o usuario possa **enviar fotos de rotulos de vinho** e o Baco identifique o vinho automaticamente.

## SUA TAREFA

Implementar o pipeline OCR:
1. **Frontend**: ativar o botao de imagem (ja existe desabilitado no ChatInput.tsx) para o usuario enviar foto
2. **Backend**: receber a imagem, enviar para Gemini Flash para OCR, extrair nome/produtor/safra do rotulo, e retornar ao Claude como contexto
3. **Tool media.py**: substituir o stub `process_image` por implementacao real com Gemini

## FLUXO COMPLETO

```
Usuario tira foto do rotulo
    → Frontend converte para base64
    → Frontend envia POST /api/chat/stream com {message: "texto", image: "base64..."}
    → Backend detecta campo image
    → Backend chama Gemini Flash com a imagem (OCR)
    → Gemini retorna: "Chateau Margaux 2015, Bordeaux, Cabernet Sauvignon"
    → Backend adiciona contexto ao message do usuario:
      "[O usuario enviou foto de um rotulo. OCR detectou: Chateau Margaux 2015, Bordeaux, Cabernet Sauvignon. Responda sobre este vinho.]"
    → Claude/Baco recebe e chama search_wine normalmente
    → Resposta com WineCard aparece no chat
```

## CREDENCIAIS

```
# Gemini API (OCR de fotos)
GEMINI_API_KEY=AIzaSy-XXXXXXXXX (ver .env)
```

Adicionar ao `.env` do backend. NAO commitar o .env.

## ARQUIVOS A MODIFICAR/CRIAR

### 1. backend/tools/media.py (MODIFICAR — substituir stub)

Estado atual: `process_image(base64_image)` retorna `{"status": "not_implemented"}`.

Implementar:
```python
import google.generativeai as genai
import base64
import os

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def process_image(base64_image):
    """Envia imagem para Gemini Flash e extrai info do rotulo de vinho."""
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")

        # Decodificar base64 para bytes
        image_bytes = base64.b64decode(base64_image)

        prompt = """Analyze this wine label/bottle image. Extract:
        - Wine name (full name as on label)
        - Producer/Winery
        - Vintage year (if visible)
        - Region (if visible)
        - Grape variety (if visible)

        Return ONLY a JSON object with these fields:
        {"name": "...", "producer": "...", "vintage": "...", "region": "...", "grape": "..."}

        If you cannot identify a field, use null.
        If this is NOT a wine image, return {"error": "not_wine"}"""

        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])

        # Parsear resposta do Gemini
        text = response.text.strip()
        # Remover markdown code blocks se houver
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        import json
        result = json.loads(text)

        if "error" in result:
            return {"message": "Nao consegui identificar um vinho nessa imagem. Tente outra foto!", "status": "not_wine"}

        # Montar string descritiva para busca
        parts = [result.get("name", "")]
        if result.get("producer"): parts.append(result["producer"])
        if result.get("vintage"): parts.append(str(result["vintage"]))
        if result.get("region"): parts.append(result["region"])

        search_text = " ".join(p for p in parts if p)

        return {
            "status": "success",
            "ocr_result": result,
            "search_text": search_text,
            "description": f"Rotulo identificado: {search_text}"
        }
    except Exception as e:
        return {
            "message": f"Erro ao processar imagem: {str(e)}. Descreva o vinho que voce viu!",
            "status": "error"
        }
```

### 2. backend/routes/chat.py (MODIFICAR — aceitar campo image)

Adicionar suporte ao campo `image` no POST body. Quando presente:
1. Chamar `process_image(image_base64)` ANTES de enviar pro Claude
2. Se OCR bem-sucedido, prepend ao message do usuario:
   `f"[O usuario enviou foto de um rotulo. OCR identificou: {ocr_result['search_text']}. Use search_wine para buscar este vinho e responda sobre ele.]\n\n{message_original}"`
3. Se OCR falhou, prepend aviso:
   `f"[O usuario tentou enviar uma foto mas nao foi possivel identificar o vinho.]\n\n{message_original}"`

Modificar TANTO o endpoint `/chat` quanto `/chat/stream`.

### 3. frontend/components/ChatInput.tsx (MODIFICAR — ativar botao de imagem)

O botao de imagem JA EXISTE mas esta `disabled` e `cursor-not-allowed`. Modificar para:
1. Remover `disabled` e `opacity-50`
2. Adicionar `onClick` que abre file picker (accept="image/*" + capture="environment" para camera no mobile)
3. Quando usuario seleciona imagem:
   - Converter para base64 (usar FileReader)
   - Se imagem > 4MB, redimensionar com canvas (max 1024px lado maior)
   - Chamar callback `onSendImage(base64string)`
4. Mostrar preview pequeno da imagem selecionada antes de enviar
5. Enquanto processa OCR, mostrar indicador de loading no botao

### 4. frontend/app/page.tsx (MODIFICAR — passar imagem pro backend)

Modificar `handleSend` para aceitar parametro opcional de imagem. Quando tem imagem:
- Enviar `{message: text || "O que voce pode me dizer sobre este vinho?", image: base64, session_id: ...}`
- O texto default e para quando o usuario envia so a foto sem digitar nada

### 5. frontend/lib/api.ts (MODIFICAR — enviar campo image)

Modificar `sendMessageStream` para aceitar parametro opcional `image?: string`. Se presente, incluir no body do POST.

### 6. backend/requirements.txt (MODIFICAR — adicionar dependencia)

Adicionar:
```
google-generativeai>=0.8.0
```

## O QUE NAO FAZER

- **NAO modificar app.py** — o CTO faz integracao depois
- **NAO modificar baco.py** — a logica de tools ja funciona, OCR e pre-processado ANTES do Claude
- **NAO modificar nenhum arquivo em tools/ EXCETO media.py**
- **NAO fazer git commit/push** — avisar quando terminar, o CTO comanda
- **NAO alterar os outros stubs** (process_video, process_pdf, process_voice) — manter como estao
- **NAO usar Claude Vision** — usar Gemini Flash (mais barato para OCR)

## COMO TESTAR

1. Backend:
```bash
cd backend
pip install google-generativeai
GEMINI_API_KEY=AIzaSy-XXXXXXXXX (ver .env) python -c "
from tools.media import process_image
import base64
# Testar com uma imagem qualquer (ou criar uma de teste)
print(process_image('iVBORw0KGgoAAAANS...'))  # base64 de teste
"
```

2. Frontend:
```bash
cd frontend && npm run build
```
Verificar que compila sem erros.

3. Integracao:
- Rodar backend: `cd backend && python app.py`
- Rodar frontend: `cd frontend && npm run dev`
- Abrir http://localhost:3000
- Clicar no botao de imagem, enviar foto de rotulo
- Verificar que Baco responde com info do vinho

## ENTREGAVEL

Quando terminar, deve existir:
- `backend/tools/media.py` — com process_image funcional via Gemini Flash
- `backend/routes/chat.py` — aceitando campo image
- `frontend/components/ChatInput.tsx` — botao de imagem funcional
- `frontend/app/page.tsx` — passando imagem pro backend
- `frontend/lib/api.ts` — enviando image no POST
- `backend/requirements.txt` — com google-generativeai

## REGRA DE COMMIT

Commitar APENAS os arquivos que VOCE criou/modificou nesta sessao. NUNCA incluir arquivos de outros chats. Fazer `git pull` antes de `git push` para nao conflitar com outros chats que rodam em paralelo.
