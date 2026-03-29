# CHAT K — Deploy (Backend no Render + Frontend na Vercel)

## CONTEXTO
WineGod.ai tem frontend Next.js e backend Flask em `C:\winegod-app\`. Tudo funciona no localhost. Voce vai colocar no ar:
- Backend → Render (web service)
- Frontend → Vercel

## CONEXOES E CONTAS
```
# GitHub
Repo: github.com/murilo-1234/winegod-app
Usuario: murilo-1234

# Render
Dashboard: dashboard.render.com
Banco ja existe: dpg-XXXXXXXXX (winegod)
Web service: CRIAR NOVO chamado "winegod-app"

# Vercel
Conta: murilo-1234 (login via GitHub)
Dashboard: vercel.com/murilo-1234s-projects

# Dominio
winegod.ai no GoDaddy (configurar depois, nao agora)

# ENVs pro backend no Render
ANTHROPIC_API_KEY=sk-ant-api03-XXXXXXXXX (ver .env)
DATABASE_URL=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX/winegod
FLASK_ENV=production
FLASK_PORT=5000
```

IMPORTANTE sobre DATABASE_URL no Render: usar URL INTERNA (sem .oregon-postgres.render.com) porque backend e banco estao no mesmo Render.

## SUA TAREFA

### PARTE 1 — Preparar backend pra deploy

1. Verificar que `backend/requirements.txt` tem tudo necessario
2. Verificar que `backend/gunicorn.conf.py` esta correto
3. Criar `backend/Procfile` ou verificar que o start command funciona
4. Criar `backend/render.yaml` (opcional, facilita deploy)
5. Garantir que o app importa tudo corretamente (paths relativos)

O Render precisa saber:
- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --config gunicorn.conf.py`

Verificar gunicorn.conf.py:
```python
bind = "0.0.0.0:5000"
workers = 1
timeout = 120
accesslog = "-"
```

### PARTE 2 — Preparar frontend pra Vercel

1. Verificar `frontend/package.json` tem script "build"
2. Criar `frontend/vercel.json` se necessario
3. Configurar `frontend/.env.production`:
```
NEXT_PUBLIC_API_URL=https://winegod-app.onrender.com
```
(URL do backend no Render — pode mudar se o nome do service for diferente)

4. Verificar que o build funciona:
```bash
cd C:\winegod-app\frontend
npm run build
```

Se der erro, corrigir.

### PARTE 3 — Instrucoes pro fundador

Como voce NAO pode criar servicos no Render ou Vercel (precisa login do fundador), gere instrucoes CLARAS passo a passo.

#### Instrucoes Render (backend):
```
1. Acessar dashboard.render.com
2. Clicar "New" → "Web Service"
3. Conectar ao repo: github.com/murilo-1234/winegod-app
4. Configurar:
   - Name: winegod-app
   - Region: Oregon (US West)
   - Branch: main
   - Root Directory: backend
   - Runtime: Python 3
   - Build Command: pip install -r requirements.txt
   - Start Command: gunicorn app:app --config gunicorn.conf.py
   - Plan: Free (ou Starter $7/mes)
5. Na aba Environment, adicionar:
   - ANTHROPIC_API_KEY = [valor]
   - DATABASE_URL = [URL interna do banco]
   - FLASK_ENV = production
   - FLASK_PORT = 5000
6. Clicar "Create Web Service"
7. Aguardar deploy (2-5 minutos)
8. Testar: https://winegod-app.onrender.com/health
```

#### Instrucoes Vercel (frontend):
```
1. Acessar vercel.com
2. Clicar "Add New" → "Project"
3. Importar repo: github.com/murilo-1234/winegod-app
4. Configurar:
   - Framework Preset: Next.js
   - Root Directory: frontend
5. Environment Variables:
   - NEXT_PUBLIC_API_URL = https://winegod-app.onrender.com
6. Clicar "Deploy"
7. Aguardar (1-2 minutos)
8. Testar a URL que a Vercel gerar
```

### PARTE 4 — CORS no backend

Verificar que o backend aceita requests do dominio da Vercel. Atualizar `backend/app.py`:
```python
CORS(app, origins=[
    "http://localhost:3000",
    "https://chat.winegod.ai",
    "https://winegod-app.vercel.app",        # URL padrao Vercel
    "https://winegod-app-*.vercel.app",      # Preview deployments
])
```

Na verdade, como nao sabemos a URL exata da Vercel ate criar, usar regex ou wildcard:
```python
import re
CORS(app, origins=[
    "http://localhost:3000",
    "https://chat.winegod.ai",
    re.compile(r"https://winegod.*\.vercel\.app"),
])
```

Ou mais simples pro inicio:
```python
CORS(app, origins="*")  # Temporario — restringir depois
```

### PARTE 5 — Verificar que tudo funciona localmente antes de deploy

```bash
# Terminal 1: backend
cd C:\winegod-app\backend
pip install -r requirements.txt
python app.py

# Terminal 2: frontend
cd C:\winegod-app\frontend
npm install
npm run build  # Verificar que build passa
npm run dev

# Terminal 3: teste
curl http://localhost:5000/health
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"oi","session_id":"test"}'
```

Abrir http://localhost:3000 e verificar que o chat funciona.

### PARTE 6 — Salvar instrucoes

Criar arquivo `C:\winegod-app\DEPLOY.md` com:
- Instrucoes completas de deploy (Render + Vercel)
- URLs dos servicos
- ENVs necessarias (sem valores reais)
- Como verificar que funcionou
- Como fazer redeploy apos mudancas

## O QUE NAO FAZER
- NAO criar contas ou servicos (fundador faz)
- NAO alterar logica do backend (so config de deploy)
- NAO alterar componentes do frontend (so config de build)
- NAO fazer git push (so preparar os arquivos)
- NAO colocar credenciais em arquivos commitados
- CORS: nao deixar origins="*" permanente (so temporario)

## COMO VERIFICAR

Apos o fundador criar os servicos:
1. Backend: `curl https://winegod-app.onrender.com/health` → deve retornar JSON com status ok
2. Frontend: abrir URL da Vercel no browser → deve mostrar tela de chat
3. Chat: digitar pergunta → Baco responde

## ENTREGAVEL
1. Backend preparado pra deploy (gunicorn, requirements, paths)
2. Frontend preparado pra Vercel (build funciona, env.production)
3. CORS configurado
4. `DEPLOY.md` com instrucoes passo a passo pro fundador
5. Build do frontend passando sem erros
