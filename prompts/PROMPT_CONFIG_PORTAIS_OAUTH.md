INSTRUCAO: Este prompt guia a configuracao de 3 portais OAuth (Facebook, Apple, Microsoft) + env vars no Render para o WineGod.ai. O codigo ja esta pronto — so falta configurar os servicos externos. Vou mandar prints de cada tela e voce me guia passo a passo.

# CONFIGURACAO DOS PORTAIS OAuth — Facebook + Apple + Microsoft

## CONTEXTO

WineGod.ai e uma IA sommelier. O login com Google ja funciona em producao. O codigo para Facebook, Apple e Microsoft ja foi implementado e esta pronto para deploy. Agora falta APENAS:

1. Configurar cada portal externo (criar apps OAuth)
2. Setar as env vars no Render

## DADOS DO PROJETO

- Frontend: `https://chat.winegod.ai` (Vercel)
- Backend: `https://winegod-app.onrender.com` (Render, Flask)
- Redirect URI padrao (Google, Facebook, Microsoft): `https://chat.winegod.ai/auth/callback`
- Redirect URI Apple (diferente!): `https://winegod-app.onrender.com/api/auth/apple/web-callback`
- Dashboard Render: https://dashboard.render.com (servico: winegod-app)

## ETAPA 0 — BACKEND_URL no Render (1 minuto)

Antes de tudo, preciso adicionar UMA env var nova no Render:

- **Onde:** Render > winegod-app > Environment > Add Environment Variable
- **Key:** `BACKEND_URL`
- **Value:** `https://winegod-app.onrender.com`

Me guie para fazer isso. Vou mandar print da tela do Render.

---

## ETAPA 1 — FACEBOOK (mais facil, ~10 min)

### Portal: https://developers.facebook.com/

### O que preciso criar:
1. Um app novo tipo **Consumer**
2. Nome: `WineGod.ai`
3. Adicionar produto **Facebook Login for Web**

### Configuracoes necessarias:
- Em **Settings > Basic**: copiar **App ID** e **App Secret**
- Em **Facebook Login > Settings**:
  - Valid OAuth Redirect URIs:
    - `https://chat.winegod.ai/auth/callback`
    - `http://localhost:3000/auth/callback`

### Env vars para o Render:
- `FACEBOOK_APP_ID` = App ID copiado
- `FACEBOOK_APP_SECRET` = App Secret copiado

### IMPORTANTE:
- O app precisa estar em modo **Live** (nao Development) para funcionar com qualquer usuario
- Para colocar em Live, Facebook pode pedir: Privacy Policy URL, Terms of Service URL, e icone do app
- Se pedir Privacy Policy, posso usar: `https://chat.winegod.ai/privacy` (preciso criar depois)
- Se pedir revisao de permissoes, as permissoes `email` e `public_profile` sao basicas e NAO precisam de revisao

Me guie passo a passo. Vou mandar print de cada tela.

---

## ETAPA 2 — MICROSOFT (medio, ~15 min)

### Portal: https://portal.azure.com/

### O que preciso criar:
1. Ir em **Azure Active Directory** (ou **Microsoft Entra ID**) > **App registrations**
2. Clicar **New registration**
3. Configurar:
   - Nome: `WineGod.ai`
   - Supported account types: **"Accounts in any organizational directory and personal Microsoft accounts"** (a opcao mais ampla — pega Hotmail, Outlook, contas corporativas)
   - Redirect URI (Web): `https://chat.winegod.ai/auth/callback`

### Depois de criar:
1. Copiar **Application (client) ID** (aparece na pagina Overview)
2. Ir em **Certificates & secrets** > **New client secret** > copiar o **Value** (NAO o Secret ID!)
3. Ir em **Authentication** e adicionar mais Redirect URIs:
   - `http://localhost:3000/auth/callback`

### Env vars para o Render:
- `MICROSOFT_CLIENT_ID` = Application (client) ID
- `MICROSOFT_CLIENT_SECRET` = Value do client secret

### IMPORTANTE:
- O client secret expira! Escolher duracao de **24 meses** (maximo)
- Copiar o Value IMEDIATAMENTE — ele so aparece uma vez
- NAO confundir "Application ID" com "Object ID" ou "Directory ID"
- NAO confundir "Value" do secret com "Secret ID"

Me guie passo a passo. Vou mandar print de cada tela.

---

## ETAPA 3 — APPLE (mais complexo, ~30 min, custa $99/ano)

### Pre-requisito: Conta Apple Developer ($99/ano)
- Se nao tiver: https://developer.apple.com/programs/enroll/
- Demora ate 48h para aprovar

### Portal: https://developer.apple.com/ > Account > Certificates, Identifiers & Profiles

### Passo 1 — Criar App ID:
1. Em **Identifiers** > clicar **+**
2. Tipo: **App IDs**
3. Tipo: **App**
4. Description: `WineGod`
5. Bundle ID (Explicit): `ai.winegod.web`
6. Em Capabilities: marcar **Sign In with Apple**
7. Clicar Continue > Register

### Passo 2 — Criar Services ID (esse e o client_id):
1. Em **Identifiers** > clicar **+**
2. Tipo: **Services IDs**
3. Description: `WineGod Web Login`
4. Identifier: `ai.winegod.web.login`
5. Clicar Continue > Register
6. Voltar na lista, clicar no Services ID criado
7. Marcar **Sign In with Apple** > clicar **Configure**
8. Primary App ID: selecionar o App ID criado no passo 1
9. Domains: `chat.winegod.ai`
10. Return URLs: `https://winegod-app.onrender.com/api/auth/apple/web-callback`
    - ATENCAO: Apple aponta pro BACKEND, nao pro frontend!
11. Salvar

### Passo 3 — Criar Key (.p8):
1. Em **Keys** > clicar **+**
2. Nome: `WineGod Sign In`
3. Marcar **Sign In with Apple** > clicar **Configure**
4. Primary App ID: selecionar o App ID do passo 1
5. Clicar Continue > Register
6. BAIXAR o arquivo .p8 (SO PODE BAIXAR UMA VEZ!)
7. Anotar o **Key ID** que aparece na tela

### Passo 4 — Anotar o Team ID:
- Aparece no canto superior direito do portal Apple Developer
- Ou em Membership > Team ID

### Env vars para o Render:
- `APPLE_CLIENT_ID` = o Identifier do Services ID (ex: `ai.winegod.web.login`)
- `APPLE_TEAM_ID` = Team ID (ex: `ABC123DEF4`)
- `APPLE_KEY_ID` = Key ID da key .p8 (ex: `XYZ789`)
- `APPLE_PRIVATE_KEY` = conteudo COMPLETO do arquivo .p8, incluindo as linhas BEGIN/END PRIVATE KEY
  - No Render, colar o conteudo trocando as quebras de linha por `\n` (literal)
  - Exemplo: `-----BEGIN PRIVATE KEY-----\nMIGT...linhas...\n-----END PRIVATE KEY-----`

### IMPORTANTE:
- O arquivo .p8 SO PODE SER BAIXADO UMA VEZ. Se perder, precisa criar outra key.
- O Return URL aponta pro BACKEND (`https://winegod-app.onrender.com/api/auth/apple/web-callback`), NAO pro frontend
- Apple Sign-In na web usa `response_mode=form_post` — por isso o redirect e diferente dos outros provedores
- A conta Apple Developer custa $99/ano — se nao quiser pagar agora, pule esta etapa. Facebook e Microsoft ja cobrem a maioria dos usuarios.

Me guie passo a passo. Vou mandar print de cada tela.

---

## ETAPA 4 — TESTAR TUDO

Depois de configurar tudo, testar na ordem:

1. **Google** — abrir https://chat.winegod.ai, fazer login com Google (tem que continuar funcionando)
2. **Facebook** — clicar "Entrar com Facebook", autenticar, verificar se volta logado
3. **Microsoft** — clicar "Entrar com Microsoft", testar com conta Hotmail
4. **Apple** — clicar "Entrar com Apple", autenticar (pode esconder email — tudo bem, funciona igual)

Para cada teste, verificar:
- Voltou para o chat logado?
- Nome aparece correto no menu?
- Creditos aparecem (15 mensagens)?

Se der erro em algum, me manda o print da tela de erro que eu ajudo.

---

## RESUMO DE TODAS AS ENV VARS NOVAS NO RENDER

| Env var | Valor | Etapa |
|---------|-------|-------|
| `BACKEND_URL` | `https://winegod-app.onrender.com` | 0 |
| `FACEBOOK_APP_ID` | Do portal Facebook | 1 |
| `FACEBOOK_APP_SECRET` | Do portal Facebook | 1 |
| `MICROSOFT_CLIENT_ID` | Do portal Azure | 2 |
| `MICROSOFT_CLIENT_SECRET` | Do portal Azure | 2 |
| `APPLE_CLIENT_ID` | Identifier do Services ID | 3 |
| `APPLE_TEAM_ID` | Team ID da conta Apple | 3 |
| `APPLE_KEY_ID` | Key ID da key .p8 | 3 |
| `APPLE_PRIVATE_KEY` | Conteudo do .p8 com \n | 3 |

Total: 9 env vars novas (alem das que ja existem).

## REGRA

Me guie UMA ETAPA POR VEZ. Eu vou mandando prints e voce me diz onde clicar. Comece pela Etapa 0 (BACKEND_URL no Render).
