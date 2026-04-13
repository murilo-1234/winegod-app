INSTRUCAO: Este prompt e INTERATIVO. Voce vai guiar o fundador passo a passo por 3 configuracoes externas. O fundador NAO e programador — use linguagem simples, diga exatamente onde clicar, o que digitar, o que copiar. Apos cada configuracao, VERIFIQUE se funcionou rodando um teste real.

# SETUP GUIADO — DNS + Google OAuth + Upstash Redis

## CONTEXTO

WineGod.ai e uma IA sommelier. O backend esta live em winegod-app.onrender.com e o frontend em winegod-app.vercel.app. O codigo de auth (Google OAuth), cache (Redis) e compartilhamento ja esta pronto e deployado. Falta apenas configurar 3 servicos externos.

## DOCUMENTOS E CODIGO DE REFERENCIA (LER ANTES DE COMECAR)

Antes de guiar o fundador, leia estes arquivos pra entender exatamente o que o codigo espera:

1. **Auth backend** — como o Google OAuth esta implementado, quais env vars espera, quais rotas existem:
   `C:\winegod-app\backend\routes\auth.py`

2. **Creditos** — como o sistema de creditos funciona com o auth:
   `C:\winegod-app\backend\routes\credits.py`

3. **Cache Redis** — qual formato de URL o codigo espera, como conecta:
   `C:\winegod-app\backend\services\cache.py`

4. **Config** — quais env vars o backend carrega:
   `C:\winegod-app\backend\config.py`

5. **Frontend auth** — como o frontend faz login, callback URL, redirect:
   `C:\winegod-app\frontend\lib\auth.ts`
   `C:\winegod-app\frontend\app\auth\callback\page.tsx`

6. **Deploy** — referencia de deploy:
   `C:\winegod-app\DEPLOY.md`

**Por que ler:** o passo a passo abaixo e um guia generico. O codigo real pode esperar env vars com nomes diferentes, URLs de callback diferentes, ou formato de Redis diferente. Leia o codigo e AJUSTE as instrucoes abaixo se necessario antes de guiar o fundador.

## SEU PAPEL

Voce e um assistente tecnico guiando o fundador. Para CADA tarefa:
1. Explique o que vamos fazer e por que (1 frase)
2. De instrucoes passo a passo com prints de onde clicar
3. Depois que o fundador disser que fez, VERIFIQUE se funcionou
4. Se nao funcionou, ajude a corrigir
5. So passe pra proxima tarefa quando a atual estiver verificada

## TAREFA 1 — DNS (apontar chat.winegod.ai → Vercel)

**O que:** Fazer o endereco chat.winegod.ai abrir o site do WineGod.

**Passo a passo:**
1. Abra https://dcc.godaddy.com/ e faca login
2. Clique no dominio `winegod.ai`
3. Va em "DNS" ou "Gerenciar DNS"
4. Clique em "Adicionar registro"
5. Preencha:
   - Tipo: **CNAME**
   - Nome: **chat**
   - Valor: **cname.vercel-dns.com**
   - TTL: pode deixar padrao
6. Salve

**Depois:** Abra o painel da Vercel (vercel.com), va no projeto winegod-app, Settings > Domains, e adicione `chat.winegod.ai`. A Vercel vai verificar o DNS automaticamente.

**Como verificar:**
- Espere 2-5 minutos
- Rode: `curl -I https://chat.winegod.ai` (ou abra no navegador)
- Se retornar HTTP 200 ou redirecionar pra Vercel, funcionou

**Se der erro:**
- "DNS not configured" → espere mais (pode levar ate 48h, mas geralmente 5-15 min)
- "SSL error" → a Vercel gera o certificado automaticamente, espere uns minutos
- Outro erro → me mostre a mensagem

## TAREFA 2 — Google OAuth (login com Google no WineGod)

**O que:** Permitir que usuarios facam login no WineGod com conta Google.

**Passo a passo:**
1. Abra https://console.cloud.google.com/
2. Crie um projeto novo (ou use um existente):
   - Clique no seletor de projeto no topo
   - "Novo Projeto" → nome: `winegod-ai` → Criar
3. No menu lateral, va em "APIs e Servicos" > "Tela de consentimento OAuth"
   - Tipo: **Externo**
   - Nome do app: **WineGod.ai**
   - Email de suporte: seu email
   - Dominios autorizados: **winegod.ai**
   - Salve e continue (pode pular escopos e usuarios de teste por enquanto)
4. Va em "APIs e Servicos" > "Credenciais"
   - Clique "Criar credenciais" > "ID do cliente OAuth"
   - Tipo: **Aplicativo da Web**
   - Nome: `WineGod Web`
   - Origens JavaScript autorizadas:
     - `https://chat.winegod.ai`
     - `https://winegod-app.vercel.app`
     - `http://localhost:3000` (pra testes)
   - URIs de redirecionamento autorizados:
     - `https://winegod-app.onrender.com/api/auth/callback`
     - `http://localhost:5000/api/auth/callback` (pra testes)
   - Criar
5. Copie o **Client ID** e o **Client Secret** que aparecem

**Depois:** Setar no Render:
1. Abra https://dashboard.render.com
2. Va no servico `winegod-app`
3. Environment > Add Environment Variable:
   - `GOOGLE_CLIENT_ID` = (o Client ID que voce copiou)
   - `GOOGLE_CLIENT_SECRET` = (o Client Secret que voce copiou)
   - `JWT_SECRET` = (uma string aleatoria longa, pode ser qualquer coisa tipo `winegod-jwt-secret-2026-baco-rules`)
4. Salve e faca deploy manual

**Como verificar:**
- Abra https://chat.winegod.ai (ou winegod-app.vercel.app)
- Clique no botao "Entrar com Google"
- Se abrir a tela de login do Google, funcionou
- Se der erro, me mostre a mensagem

## TAREFA 3 — Upstash Redis (cache)

**O que:** Ativar o cache pra respostas do WineGod ficarem mais rapidas.

**Passo a passo:**
1. Abra https://console.upstash.com/
2. Crie conta (pode usar login com GitHub)
3. Clique "Create Database"
   - Nome: `winegod-cache`
   - Regiao: **US-West-1** (Oregon — mais perto do Render)
   - Tipo: **Regional**
   - Plano: **Free** (10K comandos/dia, suficiente)
4. Depois de criar, copie a **UPSTASH_REDIS_REST_URL** (nao a REST, a normal que comeca com `redis://` ou `rediss://`)
   - Se so tiver REST URL, copie a `UPSTASH_REDIS_REST_URL` e o `UPSTASH_REDIS_REST_TOKEN`

**Depois:** Setar no Render:
1. Abra https://dashboard.render.com
2. Va no servico `winegod-app`
3. Environment > Add Environment Variable:
   - `UPSTASH_REDIS_URL` = (a URL que voce copiou)
4. Salve e faca deploy manual

**Como verificar:**
- Depois do deploy, abra: `https://winegod-app.onrender.com/health`
- Se retornar JSON com status OK, o backend ta rodando
- Faca uma busca no chat — a segunda busca igual deve ser mais rapida (cache hit)

## ORDEM RECOMENDADA

1. DNS primeiro (enquanto propaga, voce faz o resto)
2. Google OAuth segundo (mais passos)
3. Upstash Redis terceiro (mais rapido)

## QUANDO TERMINAR

Depois das 3 tarefas verificadas, informe:
- "Setup completo. DNS: OK/PENDENTE. OAuth: OK/PENDENTE. Redis: OK/PENDENTE."
- Se alguma ficou pendente, explique o que falta
