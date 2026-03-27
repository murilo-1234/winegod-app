# CHAT F — Setup do Projeto WineGod-App (Repo, Config, Verificacoes)

## O QUE E O WINEGOD
WineGod.ai e uma IA sommelier global. Este e o repositorio do PRODUTO (chat web + backend API). Existe um repo separado para o pipeline de dados/scraping (github.com/murilo-1234/winegod).

## SUA TAREFA
5 tarefas de setup, nesta ordem:

1. Criar repositorio GitHub `winegod-app`
2. Criar .gitignore completo
3. Criar CLAUDE.md (biblia do projeto para futuras sessoes)
4. Verificar que Node.js e Python estao instalados e funcionando
5. Rascunhar o Prompt E (integracao frontend+backend — salvar como arquivo)

## CONTEXTO IMPORTANTE
A pasta `C:\winegod-app\` ja existe. Dentro dela:
- `prompts/` — prompts para outros chats (NAO mexer)
- `frontend/` — pode ou nao existir (outro chat esta criando)
- `backend/` — pode ou nao existir (outro chat esta criando)
- `database/` — pode ou nao existir (outro chat esta criando)

Outros 4 chats estao rodando em PARALELO criando frontend, backend, database e system prompt. NAO toque nas pastas deles. Trabalhe apenas na raiz e em arquivos de config.

## TAREFA 1 — Criar repo GitHub

Usuario GitHub: `murilo-1234`

```bash
cd C:\winegod-app
git init
git branch -M main
```

Criar o repo no GitHub:
```bash
gh repo create murilo-1234/winegod-app --public --source=. --description "WineGod.ai — AI sommelier global. Chat with Baco, the god of wine."
```

Se `gh` nao estiver instalado, instalar com:
```bash
winget install GitHub.cli
```

Se `gh` nao autenticar, avisar o usuario para rodar `gh auth login` manualmente.

NAO fazer commit nem push ainda — so criar o repo vazio e conectar o remote. Os outros chats ainda estao trabalhando.

## TAREFA 2 — Criar .gitignore

Criar `C:\winegod-app\.gitignore`:

```
# Dependencies
node_modules/
__pycache__/
*.pyc
.venv/
venv/
env/

# Environment
.env
.env.local
.env.production

# Build
.next/
out/
dist/
build/
*.egg-info/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
desktop.ini

# Logs
*.log
npm-debug.log*

# Testing
coverage/
.pytest_cache/

# Temp
*.tmp
.tmp*
_tmp*
```

## TAREFA 3 — Criar CLAUDE.md

Criar `C:\winegod-app\CLAUDE.md` com o conteudo abaixo. Este arquivo e a biblia que todo Claude Code futuro vai ler ao abrir o projeto.

```markdown
# WINEGOD.AI — Produto (Chat + API)

## Visao Geral

WineGod.ai e uma IA sommelier global. O usuario conversa com Baco (personagem — deus do vinho) via chat web. Baco responde sobre vinhos, recomenda, compara, aceita fotos/video/voz/PDF.

Base: 1.7M vinhos Vivino + 3.8M vinhos de lojas + 57K lojas + 50 paises.

Produto: chat.winegod.ai (web app PWA) + WhatsApp WABA (mes 2-3) + MCP Server (mes 2-3).

## Repositorios

| Repo | O que faz |
|---|---|
| `winegod-app` (ESTE) | Produto: frontend chat + backend API + system prompt |
| `winegod` (separado) | Pipeline de dados: scraping, enrichment, dedup |

## Stack

- **Frontend**: Next.js + TypeScript + Tailwind CSS
- **Backend**: Python 3.11, Flask, Gunicorn
- **Banco**: PostgreSQL 16 no Render (banco: `winegod`)
- **IA Chat**: Claude API (Haiku para simples, Sonnet para complexo)
- **IA OCR**: Gemini Flash (fotos de rotulos/cardapios)
- **IA Bastidores**: DeepSeek V3 (enrichment, templates)
- **Cache**: Upstash Redis
- **Frontend Hosting**: Vercel ou Cloudflare Pages
- **Backend Hosting**: Render (web service separado)
- **CDN**: Cloudflare
- **Analytics**: PostHog

## Estrutura do Projeto

```
winegod-app/
  frontend/          <- Next.js (tela de chat)
  backend/           <- Flask (API + Claude + banco)
    routes/
    services/
    prompts/         <- BACO_SYSTEM_PROMPT
    db/
  database/          <- Migracoes SQL, documentacao schema
  prompts/           <- Prompts para gerar codigo (meta)
```

## Banco de Dados

Banco `winegod` no Render (PostgreSQL 16, plano Basic-256mb, 15GB storage).

Conexao externa:
```
postgresql://winegod_user:PASSWORD@dpg-XXXXX.oregon-postgres.render.com/winegod
```

Tabelas principais:
- `wines` (~1.72M) — vinhos unicos deduplicados
- `wine_sources` — vinho x loja x preco
- `wine_scores` — scores de enrichment (IA)
- `stores` — lojas de vinho
- `store_recipes` — como extrair de cada loja
- `executions` — log de execucoes

Campos do WineGod Score (adicionados na Semana 1):
- `winegod_score` DECIMAL(3,2) — custo-beneficio 0-5
- `winegod_score_type` VARCHAR — verified/estimated/none
- `winegod_score_components` JSONB — termos proprietarios
- `nota_wcf` DECIMAL(3,2) — qualidade pura 0-5
- `nome_normalizado` TEXT — para busca fuzzy
- `confianca_nota` DECIMAL(3,2) — 0.0 a 1.0

## Persona Baco — Regras Criticas

O chat e operado pelo personagem Baco (deus do vinho). Regras ABSOLUTAS:

1. NUNCA mencionar "Vivino" — usar "nota publica" ou "na nossa base"
2. NUNCA revelar numero exato de reviews
3. NUNCA explicar formula do score
4. NUNCA inventar dados (nota, preco, disponibilidade)
5. NUNCA comparar preco restaurante vs loja online
6. SEMPRE valorizar vinhos desconhecidos
7. SEMPRE responder no idioma do usuario
8. Nomes de vinhos NUNCA traduzidos

System prompt completo: `backend/prompts/baco_system.py`

## Regras Inegociaveis (R1-R13)

- R1: NUNCA scraping Vivino (chamar de "nota publica")
- R2: NUNCA ManyChat
- R3: NUNCA nota sem aviso (estimada = disclaimer)
- R4: NUNCA badge de confianca
- R5: SEMPRE global dia 1
- R6: SEMPRE valorizar desconhecidos
- R7: SEMPRE IA (82-88% automacao)
- R8: Nome: winegod.ai (minusculo)
- R9: SEM app nativo no lancamento
- R10: Formula: Nota WCF / Preco + micro-ajustes
- R11: WhatsApp APENAS WABA
- R12: Tese = hipotese (pivota se falhar)
- R13: SEM n8n

## Credenciais

Todas em `.env` (NAO commitado). Variaveis:
- `ANTHROPIC_API_KEY` — Claude API
- `DATABASE_URL` — PostgreSQL Render
- `GEMINI_API_KEY` — Google Gemini (OCR)
- `FLASK_PORT` — porta do backend (default 5000)
- `FLASK_ENV` — development ou production

## Regras para o Claude

### REGRA 0 — Comunicacao
- Usuario NAO e programador. Respostas simples e diretas.
- Sem jargao. Bullet points > paragrafos.

### REGRA 1 — Commit e Push
- SEMPRE perguntar antes de commit/push
- So commitar arquivos que VOCE alterou nesta sessao
- Nunca `git add .` ou `git add -A`

### REGRA 2 — Banco
- NAO deletar dados existentes
- NAO alterar colunas existentes (so adicionar novas)
- Testar queries com LIMIT antes de rodar em tudo

### REGRA 3 — Baco
- Qualquer mudanca no system prompt deve ser testada com as 5 perguntas padrao
- Ver backend/prompts/baco_test_results.md

### REGRA 4 — Separacao
- Este repo e o PRODUTO. Scraping, enrichment, discovery ficam no repo `winegod`
- NAO criar scrapers aqui
- NAO importar dados brutos aqui
```

## TAREFA 4 — Verificar Node.js e Python

Rodar e reportar versoes:

```bash
node --version
npm --version
npx --version
python --version
pip --version
```

Requisitos minimos:
- Node.js >= 18
- npm >= 9
- Python >= 3.10

Se algum nao estiver instalado ou versao antiga, avisar o usuario com instrucoes claras de como instalar/atualizar.

Verificar tambem:
```bash
gh --version
git --version
```

## TAREFA 5 — Rascunhar Prompt E (Integracao)

Criar arquivo `C:\winegod-app\prompts\PROMPT_CHAT_E_INTEGRACAO.md` com um RASCUNHO do prompt de integracao.

O Prompt E sera usado DEPOIS que os 4 chats (A, B, C, D) terminarem. Ele deve:

1. Conectar frontend (Next.js) ao backend (Flask):
   - Descomentar o fetch real em `frontend/lib/api.ts`
   - Adicionar suporte a SSE (streaming) no frontend
   - Configurar CORS corretamente

2. Integrar o BACO_SYSTEM_PROMPT do Chat D no backend do Chat B:
   - Substituir o placeholder em `backend/prompts/baco_system.py` pelo arquivo real que Chat D criou
   - Verificar que o import funciona

3. Testar o fluxo completo:
   - Rodar backend (python app.py)
   - Rodar frontend (npm run dev)
   - Abrir browser
   - Digitar pergunta
   - Baco responde com personalidade via streaming

4. Fazer o primeiro commit e push:
   - git add dos arquivos corretos (NAO .env)
   - Commit com mensagem descritiva
   - Push para murilo-1234/winegod-app

5. Criar um README.md basico pro repo

Escreva o prompt E completo e auto-suficiente, no mesmo estilo dos prompts A/B/C/D (contexto, tarefa, credenciais, o que nao fazer, como testar, entregavel).

## O QUE NAO FAZER
- NAO mexer nas pastas frontend/, backend/, database/ (outros chats estao trabalhando la)
- NAO fazer commit ou push (so criar o repo e conectar remote)
- NAO instalar dependencias do projeto (cada chat instala as suas)
- NAO rodar o projeto
- NAO alterar nada no banco de dados

## ENTREGAVEL
1. Repo `murilo-1234/winegod-app` criado no GitHub (vazio, remote conectado)
2. Arquivo `.gitignore` na raiz
3. Arquivo `CLAUDE.md` na raiz
4. Relatorio de versoes (Node, Python, npm, git, gh) — informar se algo falta
5. Arquivo `PROMPT_CHAT_E_INTEGRACAO.md` completo em `prompts/`
