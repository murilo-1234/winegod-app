# CHAT E — Integracao Frontend + Backend + System Prompt

## O QUE E O WINEGOD
WineGod.ai e uma IA sommelier global. Este e o repositorio do PRODUTO (chat web + backend API). Voce vai conectar todas as pecas que 4 chats criaram em paralelo.

## CONTEXTO
4 chats rodaram ANTES de voce:
- **Chat A** (frontend): criou `frontend/` — Next.js + TypeScript + Tailwind CSS, tela de chat com Baco
- **Chat B** (backend): criou `backend/` — Flask API com rotas de chat, servico Claude, conexao PostgreSQL
- **Chat C** (database): criou `database/` — migracoes SQL, documentacao do schema
- **Chat D** (system prompt): criou `backend/prompts/baco_system.py` — persona Baco completa
- **Chat F** (setup): criou repo GitHub, .gitignore, CLAUDE.md

Todos os arquivos ja existem em `C:\winegod-app\`. Sua tarefa e CONECTAR tudo.

## SUA TAREFA
6 tarefas, nesta ordem:

### TAREFA 1 — Conectar Frontend ao Backend

1. Abrir `frontend/lib/api.ts` (ou equivalente)
2. Substituir o mock/placeholder pelo fetch real apontando para o backend Flask
3. URL base: `http://localhost:5000` (dev) ou variavel de ambiente `NEXT_PUBLIC_API_URL`
4. Endpoint principal: `POST /api/chat` com body `{ message: string, conversation_id?: string }`
5. Adicionar suporte a SSE (Server-Sent Events) para streaming da resposta do Baco
6. Tratar erros de rede com mensagem amigavel pro usuario

Verificar se o frontend ja tem componente de streaming. Se nao, adicionar:
```typescript
// Exemplo de consumo SSE
const response = await fetch(`${API_URL}/api/chat`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message, conversation_id }),
});

const reader = response.body?.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader!.read();
  if (done) break;
  const chunk = decoder.decode(value);
  // Parsear SSE e atualizar UI
}
```

### TAREFA 2 — Configurar CORS no Backend

1. Abrir `backend/app.py` (ou equivalente)
2. Verificar se Flask-CORS ja esta configurado
3. Se nao, adicionar:
```python
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=[
    "http://localhost:3000",      # Next.js dev
    "https://chat.winegod.ai",    # producao
])
```
4. Garantir que os headers SSE estejam corretos:
```python
response.headers['Content-Type'] = 'text/event-stream'
response.headers['Cache-Control'] = 'no-cache'
response.headers['Connection'] = 'keep-alive'
```

### TAREFA 3 — Integrar System Prompt do Baco

1. Abrir `backend/prompts/baco_system.py` — este e o arquivo que Chat D criou
2. Abrir `backend/services/claude_service.py` (ou equivalente do Chat B)
3. Verificar que o servico Claude esta importando o system prompt corretamente:
```python
from prompts.baco_system import BACO_SYSTEM_PROMPT
```
4. Verificar que o prompt esta sendo passado na chamada da API Claude:
```python
response = client.messages.create(
    model="claude-haiku-4-5-20251001",  # ou sonnet para queries complexas
    system=BACO_SYSTEM_PROMPT,
    messages=messages,
    stream=True,
)
```
5. Se Chat B usou um placeholder, substituir pelo import real

### TAREFA 4 — Testar Fluxo Completo

Rodar tudo e testar:

```bash
# Terminal 1 — Backend
cd C:\winegod-app\backend
python -m pip install -r requirements.txt
python app.py
# Deve rodar em http://localhost:5000

# Terminal 2 — Frontend
cd C:\winegod-app\frontend
npm install
npm run dev
# Deve rodar em http://localhost:3000
```

Testar manualmente:
1. Abrir http://localhost:3000 no browser
2. Digitar "Ola Baco, me recomenda um vinho tinto ate R$80"
3. Verificar que:
   - Resposta aparece com streaming (palavra por palavra)
   - Baco responde com personalidade (deus do vinho)
   - Nao menciona "Vivino"
   - Responde em portugues (idioma da pergunta)

Testar as 5 perguntas padrao do Baco:
1. "Ola" (deve cumprimentar como Baco)
2. "Me recomenda um vinho tinto ate R$80" (deve buscar no banco)
3. "What's a good Malbec under $20?" (deve responder em ingles)
4. "O que e o WineGod Score?" (deve explicar sem revelar formula)
5. "Voce usa dados do Vivino?" (NUNCA deve mencionar Vivino)

### TAREFA 5 — Primeiro Commit e Push

Fazer o primeiro commit com TODOS os arquivos do projeto:

```bash
cd C:\winegod-app

# Verificar que .env NAO esta na lista
git status

# Adicionar arquivos por pasta (NAO usar git add . nem git add -A)
git add .gitignore
git add CLAUDE.md
git add frontend/
git add backend/
git add database/
git add prompts/

# Verificar que .env nao esta incluido
git diff --cached --name-only | grep -i env

# Commit
git commit -m "feat: initial release — WineGod.ai chat with Baco

- Frontend: Next.js chat interface with streaming SSE
- Backend: Flask API with Claude integration
- Database: PostgreSQL schema and migrations
- System prompt: Baco persona (god of wine)
- Config: .gitignore, CLAUDE.md"

# Push
git push -u origin main
```

IMPORTANTE:
- PERGUNTAR ao usuario antes de fazer o push
- Verificar que `.env` NAO esta nos arquivos staged
- Se algum arquivo sensivel aparecer, remover do staging

### TAREFA 6 — Criar README.md

Criar `C:\winegod-app\README.md`:

```markdown
# winegod.ai

AI sommelier global. Chat with Baco, the god of wine.

## What is WineGod?

WineGod.ai is an AI-powered wine recommendation platform. Ask Baco — the god of wine — about any wine, get personalized recommendations, compare options, and discover hidden gems from our database of 1.7M+ wines across 50 countries.

## Features

- Chat with Baco (AI sommelier persona)
- Wine recommendations by price, region, grape, occasion
- WineGod Score — proprietary value-for-money rating
- Multi-language support (responds in your language)
- Photo/label recognition (coming soon)
- Voice input (coming soon)

## Tech Stack

- **Frontend**: Next.js + TypeScript + Tailwind CSS
- **Backend**: Python/Flask
- **Database**: PostgreSQL (Render)
- **AI**: Claude API (Anthropic)
- **OCR**: Gemini Flash (Google)

## Getting Started

### Prerequisites
- Node.js >= 18
- Python >= 3.10
- PostgreSQL access (Render)

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Fill in your API keys
python app.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 and start chatting with Baco.

## Environment Variables

Create a `.env` file in the backend directory:

```
ANTHROPIC_API_KEY=your_key
DATABASE_URL=your_postgresql_url
GEMINI_API_KEY=your_key
FLASK_PORT=5000
FLASK_ENV=development
```

## License

Proprietary. All rights reserved.
```

Commitar o README separadamente:
```bash
git add README.md
git commit -m "docs: add README.md"
git push
```

## CREDENCIAIS

Variaveis de ambiente necessarias (arquivo `.env` na raiz ou em `backend/`):

| Variavel | Onde pegar |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `DATABASE_URL` | Dashboard Render > winegod > Connect |
| `GEMINI_API_KEY` | aistudio.google.com |
| `FLASK_PORT` | default 5000 |
| `FLASK_ENV` | development |
| `NEXT_PUBLIC_API_URL` | http://localhost:5000 (dev) |

## O QUE NAO FAZER

- NAO alterar o system prompt do Baco sem testar as 5 perguntas
- NAO expor a connection string do banco no frontend
- NAO fazer fetch direto do frontend para o banco — sempre via backend API
- NAO commitar .env
- NAO mencionar "Vivino" em nenhum lugar do codigo visivel ao usuario
- NAO alterar schema do banco (isso e responsabilidade do Chat C / repo winegod)

## COMO TESTAR

1. Backend rodando? `curl http://localhost:5000/health` deve retornar `{"status": "ok"}`
2. Frontend rodando? Abrir http://localhost:3000 deve mostrar tela de chat
3. Conexao frontend-backend? Digitar mensagem e ver resposta streaming
4. Persona Baco? Resposta deve ter personalidade de deus do vinho
5. Idioma? Perguntar em ingles, resposta em ingles. Perguntar em portugues, resposta em portugues.

## ENTREGAVEL

1. Frontend conectado ao backend via fetch + SSE streaming
2. CORS configurado corretamente
3. System prompt do Baco integrado no servico Claude
4. Fluxo completo testado (pergunta -> resposta streaming com personalidade)
5. Primeiro commit e push no GitHub (sem .env)
6. README.md no repo
