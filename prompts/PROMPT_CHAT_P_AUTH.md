# CHAT P — Auth Google OAuth + Sistema de Creditos

## CONTEXTO

WineGod.ai e uma IA sommelier global. Um chat web onde o personagem "Baco" responde sobre vinhos. O backend e Flask + Claude API, o frontend e Next.js.

Agora precisamos adicionar autenticacao (Google OAuth) e um sistema de creditos para limitar uso.

## SUA TAREFA

Implementar:
1. **Login com Google** (OAuth 2.0) — botao "Entrar com Google"
2. **Sistema de creditos**:
   - Sem login: 5 mensagens gratis (por sessao/IP)
   - Com login: 15 mensagens gratis por dia
   - Quando acabar: mostrar mensagem "Creditos esgotados" + botao de login (se nao logado)
3. **Tabela de usuarios** no banco PostgreSQL Render
4. **Middleware** que checa creditos antes de processar mensagem

## CREDENCIAIS

```
# Banco WineGod no Render
DATABASE_URL=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod

# Google OAuth
# O fundador ainda NAO criou as credenciais Google OAuth.
# Criar o codigo usando variaveis de ambiente:
#   GOOGLE_CLIENT_ID=...
#   GOOGLE_CLIENT_SECRET=...
# Deixar .env.example com esses campos vazios.
# O fundador vai criar no Google Cloud Console depois.
```

## ARQUIVOS A CRIAR

### 1. backend/routes/auth.py (NOVO)

Blueprint Flask com:

```python
auth_bp = Blueprint('auth', __name__)
```

Endpoints:
- `GET /api/auth/google` — redireciona para Google OAuth consent screen
- `GET /api/auth/google/callback` — recebe code do Google, troca por token, cria/atualiza usuario no banco, retorna JWT
- `GET /api/auth/me` — retorna dados do usuario logado (nome, email, foto, creditos restantes)
- `POST /api/auth/logout` — invalida sessao

Usar bibliotecas:
- `authlib` ou `requests-oauthlib` para OAuth
- `PyJWT` para tokens JWT
- Secret para JWT: gerar automatico ou usar env var `JWT_SECRET`

### 2. backend/routes/credits.py (NOVO)

Blueprint Flask com:

```python
credits_bp = Blueprint('credits', __name__)
```

Funcoes:
- `check_credits(request)` — verifica se usuario tem creditos. Retorna `(allowed: bool, remaining: int, reason: str)`
- Logica:
  - Se tem JWT valido no header `Authorization: Bearer ...`:
    - Buscar usuario no banco
    - Contar mensagens hoje (WHERE created_at >= hoje 00:00 UTC)
    - Se < 15: allowed=True
    - Se >= 15: allowed=False, reason="daily_limit"
  - Se NAO tem JWT:
    - Contar mensagens da sessao (session_id no body)
    - Se < 5: allowed=True
    - Se >= 5: allowed=False, reason="guest_limit"

Endpoint:
- `GET /api/credits` — retorna creditos restantes (para o frontend mostrar contador)

### 3. backend/db/models_auth.py (NOVO)

Funcoes para criar tabelas e queries:

```sql
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    google_id VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    picture_url TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS message_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    session_id VARCHAR(255),
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_message_log_user_date ON message_log (user_id, created_at);
CREATE INDEX idx_message_log_session ON message_log (session_id, created_at);
```

Funcoes:
- `create_tables()` — cria as tabelas (chamar no startup)
- `upsert_user(google_id, email, name, picture_url)` — cria ou atualiza usuario
- `get_user_by_id(user_id)` — retorna dados do usuario
- `log_message(user_id, session_id, ip)` — registra uso
- `count_messages_today(user_id)` — conta mensagens do usuario hoje
- `count_messages_session(session_id)` — conta mensagens da sessao

Usar `get_connection()` e `release_connection()` de `db.connection`:
```python
from db.connection import get_connection, release_connection
```

### 4. frontend/components/auth/LoginButton.tsx (NOVO)

Componente React:
- Botao "Entrar com Google" com icone do Google
- Estilo dark theme (bg #1A1A2E, border #2A2A4E)
- Ao clicar: redireciona para `/api/auth/google`
- Apos login: salvar JWT no localStorage

### 5. frontend/components/auth/UserMenu.tsx (NOVO)

Componente React (mostrar quando logado):
- Foto do Google (arredondada, 32px)
- Nome
- Creditos restantes: "12/15 mensagens hoje"
- Botao "Sair"

### 6. frontend/components/auth/CreditsBanner.tsx (NOVO)

Banner que aparece quando creditos acabam:
- Texto: "Voce usou suas mensagens gratuitas"
- Se nao logado: "Entre com Google para ganhar mais 15 mensagens"
- Se logado: "Seus creditos renovam amanha"
- Estilo: warning banner discreto, cor wine accent

### 7. frontend/lib/auth.ts (NOVO)

Funcoes utilitarias:
- `getToken()` — pega JWT do localStorage
- `setToken(jwt)` — salva JWT
- `removeToken()` — remove JWT (logout)
- `getUser()` — chama GET /api/auth/me com token
- `getCredits()` — chama GET /api/credits com token ou session_id
- `isLoggedIn()` — verifica se tem token valido

### 8. backend/requirements.txt (MODIFICAR)

Adicionar:
```
PyJWT>=2.8.0
requests-oauthlib>=1.3.0
```

## INTEGRACAO COM CHAT EXISTENTE

O chat atual esta em:
- Backend: `backend/routes/chat.py` — POST /api/chat e /api/chat/stream
- Frontend: `frontend/app/page.tsx` — handleSend()

**NAO modifique chat.py diretamente.** Em vez disso:
- Crie um decorator ou middleware `@require_credits` que pode ser aplicado aos endpoints de chat
- Documente como aplicar: "Adicionar `@require_credits` antes das funcoes `chat()` e `chat_stream()` em chat.py"
- O CTO fara a integracao

**NAO modifique page.tsx diretamente.** Em vez disso:
- Crie os componentes auth isolados
- Documente onde inserir: "Adicionar LoginButton/UserMenu no header de page.tsx"
- O CTO fara a integracao

## O QUE NAO FAZER

- **NAO modificar app.py** — o CTO registra blueprints depois
- **NAO modificar chat.py** — documentar como integrar
- **NAO modificar page.tsx** — documentar onde inserir componentes
- **NAO fazer git commit/push** — avisar quando terminar
- **NAO criar credenciais Google OAuth** — usar env vars, fundador cria depois
- **NAO implementar pagamento/Stripe** — isso e futuro

## COMO TESTAR

1. Criar tabelas:
```bash
cd backend
DATABASE_URL=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod python -c "
from db.models_auth import create_tables
create_tables()
print('Tabelas criadas com sucesso')
"
```

2. Testar contagem de creditos sem login:
```bash
curl -X POST http://localhost:5000/api/credits -H "Content-Type: application/json" -d '{"session_id": "test123"}'
```

3. Frontend compila:
```bash
cd frontend && npm run build
```

## ENTREGAVEL

Quando terminar, deve existir:
- `backend/routes/auth.py` — Google OAuth endpoints
- `backend/routes/credits.py` — sistema de creditos
- `backend/db/models_auth.py` — tabelas users + message_log
- `frontend/components/auth/LoginButton.tsx`
- `frontend/components/auth/UserMenu.tsx`
- `frontend/components/auth/CreditsBanner.tsx`
- `frontend/lib/auth.ts`
- `backend/requirements.txt` — atualizado
- Documentacao de integracao (quais linhas adicionar em app.py, chat.py, page.tsx)

## REGRA DE COMMIT

Commitar APENAS os arquivos que VOCE criou/modificou nesta sessao. NUNCA incluir arquivos de outros chats. Fazer `git pull` antes de `git push` para nao conflitar com outros chats que rodam em paralelo.
