# Deploy — WineGod.ai

Backend no Render + Frontend na Vercel.

---

## 1. Deploy do Backend (Render)

### Passo a passo

1. Acessar **dashboard.render.com**
2. Clicar **"New"** → **"Web Service"**
3. Conectar ao repo: `github.com/murilo-1234/winegod-app`
4. Configurar:
   - **Name**: `winegod-app`
   - **Region**: Oregon (US West) — mesmo do banco
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --config gunicorn.conf.py`
   - **Plan**: Free (ou Starter $7/mes pra nao dormir)
5. Na aba **Environment**, adicionar:
   - `ANTHROPIC_API_KEY` = (valor da chave Claude)
   - `DATABASE_URL` = (URL **interna** do banco Render — sem `.oregon-postgres.render.com`)
   - `FLASK_ENV` = `production`
   - `FLASK_PORT` = `5000`
6. Clicar **"Create Web Service"**
7. Aguardar deploy (2-5 minutos)

### Verificar

```
curl https://winegod-app.onrender.com/health
```

Deve retornar JSON com `"status": "ok"`.

### IMPORTANTE sobre DATABASE_URL

Usar a URL **interna** do banco (sem `.oregon-postgres.render.com`), porque backend e banco estao no mesmo Render. A URL interna e mais rapida e gratuita.

---

## 2. Deploy do Frontend (Vercel)

### Passo a passo

1. Acessar **vercel.com**
2. Clicar **"Add New"** → **"Project"**
3. Importar repo: `github.com/murilo-1234/winegod-app`
4. Configurar:
   - **Framework Preset**: Next.js
   - **Root Directory**: `frontend`
5. **Environment Variables**:
   - `NEXT_PUBLIC_API_URL` = `https://winegod-app.onrender.com`
6. Clicar **"Deploy"**
7. Aguardar (1-2 minutos)
8. Testar a URL que a Vercel gerar

### Verificar

Abrir a URL da Vercel no browser. Deve mostrar a tela de chat do WineGod. Digitar uma pergunta e verificar que o Baco responde.

---

## 3. Variaveis de Ambiente (resumo)

### Backend (Render)

| Variavel | Descricao |
|---|---|
| `ANTHROPIC_API_KEY` | Chave da API Claude |
| `DATABASE_URL` | URL interna do PostgreSQL no Render |
| `FLASK_ENV` | `production` |
| `FLASK_PORT` | `5000` |

### Frontend (Vercel)

| Variavel | Descricao |
|---|---|
| `NEXT_PUBLIC_API_URL` | URL do backend no Render (ex: `https://winegod-app.onrender.com`) |

---

## 4. URLs dos Servicos

| Servico | URL |
|---|---|
| Backend (Render) | `https://winegod-app.onrender.com` |
| Frontend (Vercel) | (gerada pela Vercel ao criar o projeto) |
| Banco (Render) | ja existe — `dpg-d6o56scr85hc73843pvg-a` |
| Dominio final | `chat.winegod.ai` (configurar depois no GoDaddy) |

---

## 5. Redeploy apos mudancas

### Backend
O Render faz redeploy automatico quando voce faz push para `main`. Se precisar forcar:
1. Ir no dashboard do Render → servico `winegod-app`
2. Clicar **"Manual Deploy"** → **"Deploy latest commit"**

### Frontend
A Vercel faz redeploy automatico quando voce faz push para `main`. Se precisar forcar:
1. Ir no dashboard da Vercel → projeto
2. Clicar **"Redeploy"**

---

## 6. Troubleshooting

### Backend nao responde
- Verificar logs no Render (aba "Logs")
- Verificar se as ENVs estao corretas
- No plano Free, o servico "dorme" apos 15min sem uso — primeira request demora ~30s

### Frontend mostra erro de conexao
- Verificar se `NEXT_PUBLIC_API_URL` aponta pro backend correto
- Verificar se o backend esta no ar (testar `/health`)
- Verificar CORS nos logs do browser (F12 → Console)

### Chat nao funciona mas health sim
- Verificar `ANTHROPIC_API_KEY` no Render
- Verificar `DATABASE_URL` no Render (usar URL interna!)
