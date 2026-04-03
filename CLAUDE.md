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
- Ao mencionar ou gerar qualquer arquivo, SEMPRE usar o caminho completo (ex: `C:\winegod-app\scripts\arquivo.py`). Nunca usar caminho relativo.

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
