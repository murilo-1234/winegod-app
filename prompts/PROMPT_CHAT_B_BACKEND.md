# CHAT B — Backend Flask (API do Chat WineGod)

## O QUE E O WINEGOD
WineGod.ai e uma IA sommelier global. O usuario conversa com "Baco" (personagem — deus do vinho irreverente, estilo Jack Sparrow + Hemingway) pelo chat. O backend recebe mensagens, chama Claude API com a persona do Baco, e retorna respostas.

## SUA TAREFA
Criar o backend Flask com:
1. Endpoint POST /api/chat (recebe mensagem, retorna resposta do Baco)
2. Integracao com Claude API (Haiku para respostas simples)
3. Conexao com banco PostgreSQL (para buscar vinhos no futuro)
4. CORS configurado para o frontend
5. Streaming SSE (Server-Sent Events) para resposta em tempo real

## ONDE CRIAR
Diretorio: `C:\winegod-app\backend\`

Se o diretorio nao existir, crie. NAO toque em nada fora desta pasta.

## CREDENCIAIS

```
# Claude API (Anthropic)
ANTHROPIC_API_KEY=your_key_here

# Banco PostgreSQL (Render)
DATABASE_URL=postgresql://winegod_user:PASSWORD@dpg-XXXXX.oregon-postgres.render.com/winegod

# Configuracoes
FLASK_ENV=development
FLASK_PORT=5000
```

## ESTRUTURA A CRIAR

```
C:\winegod-app\backend\
  app.py                  ← Flask app principal (entry point)
  config.py               ← Carrega .env, configuracoes
  requirements.txt        ← Dependencias
  gunicorn.conf.py        ← Config de deploy (futuro)
  .env                    ← Credenciais (NAO commitar)
  .env.example            ← Template sem valores reais
  .gitignore
  routes/
    __init__.py
    chat.py               ← POST /api/chat + GET /api/chat/stream (SSE)
    health.py             ← GET /health (status do sistema)
  services/
    __init__.py
    baco.py               ← Chama Claude API com system prompt
    wine_search.py        ← Busca vinhos no banco (basico por enquanto)
  prompts/
    __init__.py
    baco_system.py        ← BACO_SYSTEM_PROMPT (versao basica, Chat D faz a versao completa)
  db/
    __init__.py
    connection.py         ← Pool de conexoes PostgreSQL
    queries.py            ← Queries SQL para buscar vinhos
```

## ESPECIFICACOES TECNICAS

### requirements.txt
```
flask==3.1.0
flask-cors==5.0.1
anthropic==0.49.0
psycopg2-binary==2.9.10
python-dotenv==1.0.1
gunicorn==23.0.0
```

### app.py (entry point)
```python
from flask import Flask
from flask_cors import CORS
from config import Config
from routes.chat import chat_bp
from routes.health import health_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app, origins=["http://localhost:3000", "https://chat.winegod.ai"])

    app.register_blueprint(chat_bp, url_prefix='/api')
    app.register_blueprint(health_bp)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=int(Config.FLASK_PORT), debug=True)
```

### POST /api/chat (routes/chat.py)

Request:
```json
{
  "message": "Me indica um tinto bom ate R$100",
  "session_id": "uuid-gerado-pelo-frontend",
  "language": "pt"
}
```

Response (normal):
```json
{
  "response": "Ah, por R$100 eu tenho achados que fariam Zeus descer do Olimpo...",
  "session_id": "uuid",
  "model": "claude-haiku-4-5-20251001"
}
```

### GET /api/chat/stream (SSE)

Query params: `?message=texto&session_id=uuid`

Response: Server-Sent Events (streaming palavra por palavra)
```
data: {"type": "start"}

data: {"type": "text", "content": "Ah, "}

data: {"type": "text", "content": "por R$100 "}

data: {"type": "text", "content": "eu tenho achados..."}

data: {"type": "end", "model": "claude-haiku-4-5-20251001"}
```

### services/baco.py

Funcao principal: `get_baco_response(message, session_id, history=[])`

- Chama Claude API (model: claude-haiku-4-5-20251001)
- Usa BACO_SYSTEM_PROMPT como system prompt
- Envia historico da conversa (ultimas 10 mensagens)
- Temperature: 0.7 (criativo mas controlado)
- Max tokens: 1024

Para streaming: `stream_baco_response(message, session_id, history=[])` — retorna generator

### prompts/baco_system.py (VERSAO BASICA)

O Chat D vai criar a versao completa. Por enquanto, use este placeholder:

```python
BACO_SYSTEM_PROMPT = """Voce e Baco, o deus imortal do vinho. Sua personalidade:

QUEM VOCE E:
- Dionisio (grego) / Baco (romano), deus do vinho, festas e extase
- Personalidade: mistura de Jack Sparrow + Hemingway + Dionisio
- Caloroso, irreverente, generoso, NUNCA arrogante ou esnobe
- Fala como se ja fosse amigo do usuario ha anos
- Usa superlativos ("magnifico!", "transcendente!", "pelo Olimpo!")
- Esquece palavras as vezes (timing comico)
- Conta historias de epocas passadas naturalmente

REGRAS ABSOLUTAS:
1. NUNCA mencionar "Vivino" — diga "nota publica" ou "na nossa base"
2. NUNCA revelar numero exato de reviews — diga "bastante avaliado" ou "amplamente reconhecido"
3. NUNCA explicar a formula do score — diga "milenios de experiencia e uma pitada de magia algoritmica"
4. NUNCA inventar dados (nota, preco, disponibilidade) — se nao sabe, diga "Baco ainda nao conhece este nectar"
5. NUNCA ser condescendente com iniciantes
6. NUNCA usar linguagem corporativa
7. SEMPRE valorizar vinhos desconhecidos com entusiasmo genuino
8. SEMPRE oferecer proximo passo ("Quer comparar?", "Quer ver similar?", "Posso buscar mais barato?")

COMO RESPONDER:
- Comece SEMPRE com a informacao que o usuario pediu (direto, nao enrola)
- Depois adicione personalidade (historia, opiniao, humor)
- Termine com sugestao de proximo passo
- Respostas de 2-4 paragrafos no maximo
- Use markdown para formatacao (negrito, italico, listas)

IDIOMA:
- Responda no idioma do usuario
- Nomes de vinhos NUNCA sao traduzidos ("Chateau Margaux" e "Chateau Margaux" em qualquer idioma)
"""
```

### db/connection.py

Crie um pool de conexoes simples com psycopg2:

```python
import psycopg2
from psycopg2 import pool
from config import Config

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=Config.DATABASE_URL
        )
    return _pool

def get_connection():
    return get_pool().getconn()

def release_connection(conn):
    get_pool().putconn(conn)
```

### db/queries.py

Funcao basica para buscar vinhos por nome:

```python
def search_wines(query, limit=5):
    """Busca vinhos por nome (LIKE simples por enquanto, pg_trgm depois)"""
    # Busca na tabela wines do Render
    sql = """
        SELECT id, nome, produtor, safra, tipo, pais_nome, regiao,
               vivino_rating, vivino_reviews, preco_min, preco_max, moeda
        FROM wines
        WHERE nome_normalizado ILIKE %s
        ORDER BY vivino_reviews DESC NULLS LAST
        LIMIT %s
    """
    # ...implementar com connection pool
```

### GET /health (routes/health.py)

Retorna status do sistema:
```json
{
  "status": "ok",
  "database": "connected",
  "claude_api": "configured",
  "wines_count": 1727058,
  "version": "0.1.0"
}
```

## GERENCIAMENTO DE SESSAO

- Sessao = historico da conversa
- Por enquanto, guardar em memoria (dict Python): `sessions = {session_id: [messages]}`
- Limite: 10 ultimas mensagens por sessao
- Sessoes expiram apos 1 hora sem uso
- NO FUTURO: guardar no banco (tabela conversations). Nao implementar agora

## O QUE NAO FAZER
- NAO criar sistema de login/auth
- NAO criar tabelas no banco (Chat C faz isso)
- NAO implementar OCR, fotos, video, PDF (semana 3+)
- NAO implementar tools do Claude (semana 4)
- NAO implementar cache Redis (semana 3)
- NAO tocar em nada fora de `C:\winegod-app\backend\`
- NAO fazer git init, commit ou push
- NAO usar emojis no codigo
- NAO instalar bibliotecas alem das listadas no requirements.txt

## COMO TESTAR

```bash
cd C:\winegod-app\backend
pip install -r requirements.txt
python app.py
```

Teste 1 — Health check:
```bash
curl http://localhost:5000/health
```
Deve retornar JSON com status "ok"

Teste 2 — Chat normal:
```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Me indica um vinho tinto bom", "session_id": "test123"}'
```
Deve retornar resposta do Baco (via Claude Haiku)

Teste 3 — Streaming:
```bash
curl "http://localhost:5000/api/chat/stream?message=qual+vinho+combina+com+pizza&session_id=test123"
```
Deve retornar eventos SSE em tempo real

Teste 4 — Historico:
Enviar 3 mensagens seguidas com mesmo session_id. A terceira resposta deve demonstrar que Baco lembra do contexto anterior.

## ENTREGAVEL
Pasta `C:\winegod-app\backend\` com Flask funcional. Baco responde via Claude Haiku. Streaming SSE funciona. Health check mostra banco conectado.
