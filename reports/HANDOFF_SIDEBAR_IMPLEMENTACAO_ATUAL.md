# Prompt de Handoff - Sidebar / Legal Rollout

Use este documento como contexto inicial de um novo chat. Ele foi escrito para permitir continuidade sem perda de informacao relevante.

Regra operacional:
- Leia primeiro `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`.
- Leia este handoff inteiro antes de propor qualquer mudanca.
- Nao reverta alteracoes nao relacionadas que ja existem no working tree.
- Trabalhe por subfase fechada.
- Atualize este documento apenas em checkpoints relevantes.

## Continuidade Operacional

Documento complementar de coordenacao multiaba:
- `reports/COORDENACAO_SIDEBAR_MULTIABA.md`
  - registra prompts emitidos para outras abas, resultados das revisoes e estado operacional atual
  - deve ser atualizado em checkpoints operacionais, incluindo a regra definida nesta conversa: a cada 3 prompts emitidos para outra aba

## Objetivo

Executar o plano do sidebar com disciplina de escopo:
- primeiro estabilizar auth e creditos
- depois publicar rotas legais obrigatorias
- depois entrar em shell, paginas do sidebar, historico, favoritos e busca

Decisoes centrais do plano:
- auth real vem de `/api/auth/me`, nao de `localStorage`
- limites reais da v1:
  - guest: 5 mensagens por sessao
  - user free logado: 15 mensagens por dia
- favoritos v1 = conversas salvas, nao vinhos
- buscar v1 = command palette de conversas/salvos + CTA para jogar busca nova no chat
- paginas legais publicas devem existir em rotas dedicadas:
  - `/privacy`
  - `/terms`
  - `/data-deletion`

## Status Atual Verificado

### Fase 0A - Concluida

Implementado e revisado no codigo:
- `backend/config.py`
  - `GUEST_CREDIT_LIMIT = 5`
  - `USER_CREDIT_LIMIT = 15`
- `backend/routes/auth.py`
  - criado `get_current_user(req)`
  - `GET /api/auth/me` usa `get_current_user()`
  - payload inclui `provider` e `last_login`
  - limite vem de `Config.USER_CREDIT_LIMIT`
- `backend/routes/credits.py`
  - limites usam `Config`
- `frontend/lib/api.ts`
  - chat envia `Authorization: Bearer <token>` quando houver token
  - `getSessionId()` foi exportado
- `frontend/app/page.tsx`
  - frontend deixou de depender de `creditsLimit = 5` hardcoded
  - mount busca creditos reais
  - logout deixa de resetar para numero magico local

### Fase 0B - Concluida

Implementado e revisado no codigo:
- `frontend/lib/auth.ts`
  - `provider` e `last_login` ficaram opcionais em `UserData`
  - `getCredits()` remove token em `401`
- `frontend/lib/api.ts`
  - `sendMessageStream()` trata `429` pre-SSE
  - callback opcional `onCreditsExhausted(reason)`
  - `resetSessionId()` existe para gerar nova sessao guest apos logout
- `frontend/app/page.tsx`
  - `refreshCredits()` centraliza atualizacao de creditos
  - mount faz fallback de user para guest se token falhar
  - logout usa `refreshCredits()`
  - `onDone` atualiza creditos no fim da resposta
  - `onCreditsExhausted` usa o `reason` real do backend
  - se token expirar no meio da sessao, limpa `user` e cai para guest
  - logout gera novo `session_id` guest antes de recalcular creditos
- `frontend/components/auth/UserMenu.tsx`
  - guard contra divisao por zero na barra de progresso
- `backend/routes/credits.py`
  - `GET /api/credits` retorna `401` se houver Bearer invalido/expirado
  - path guest so e usado quando nao existe Bearer

### Fase 0.5A - Concluida

Implementado:
- `frontend/components/LegalPage.tsx`
  - shell publico reutilizavel para paginas legais
  - header com logo, area central legivel, footer simples
  - props:
    - `title`
    - `description?`
    - `lastUpdated?`
    - `children`

### Fase 0.5B - Concluida

Arquivos implementados:
- `frontend/app/privacy/page.tsx`
- `frontend/app/terms/page.tsx`
- `frontend/app/data-deletion/page.tsx`

Estado:
- usam `LegalPage`
- cada rota exporta `metadata`
- frontend build passou com as tres rotas presentes
- as 3 rotas aparecem no build output como paginas estaticas
- conteudo esta honesto, simples e publico
- `/data-deletion` descreve fluxo manual por email, sem prometer automacao atual

Resumo de conteudo:
- `/privacy`
  - dados coletados: OAuth, uso, armazenamento local
  - uso dos dados, terceiros, retencao e direitos do usuario
- `/terms`
  - natureza informativa das respostas
  - conta e creditos
  - uso aceitavel
  - limitacao de responsabilidade
- `/data-deletion`
  - o que e excluido
  - o que nao e excluido
  - processo manual via email
  - prazo manual declarado
  - exclusao automatica ainda nao existe

Riscos de conteudo:
- as paginas usam `privacy@winegod.ai`
- esse email precisa existir de verdade antes de producao
- se Facebook/Microsoft exigirem ingles para compliance OAuth, pode ser necessario texto bilingue
- nenhuma entidade juridica foi citada; se houver exigencia formal, adicionar depois
- `lastUpdated` esta fixado manualmente em `13 de abril de 2026`

### Fase 1A - Concluida (com patch corretivo ja aplicado)

Implementado:
- `frontend/components/AppShell.tsx`
  - client component que centraliza sidebar + header + area de conteudo
  - recebe `user`, `creditsUsed`, `creditsLimit`, `onLogout`, `onNewChat` como props
  - gerencia `sidebarOpen` internamente
  - header: hamburger mobile + logo (Link para `/`) + UserMenu ou LoginButton
  - children renderizados em `flex-1 min-h-0`
- `frontend/components/Sidebar.tsx`
  - navegacao real com `next/link`
  - Favoritos, Conta, Plano e Ajuda agora apontam para rotas reais
  - Novo chat e Buscar continuam como botoes
- `frontend/app/page.tsx`
  - home refatorada para usar `AppShell`
  - logica de auth, chat e creditos mantida
- `frontend/app/not-found.tsx`
  - 404 customizado com visual do produto
- stubs criados:
  - `frontend/app/ajuda/page.tsx`
  - `frontend/app/conta/page.tsx`
  - `frontend/app/plano/page.tsx`
  - `frontend/app/favoritos/page.tsx`
  - todos usam `AppShell`
  - todos exportam `metadata`

Patch corretivo aplicado:
- `AppShell` agora auto-hidrata auth quando props nao sao fornecidas (self-managed mode)
- `Novo chat` navega para `/` quando `onNewChat` nao e fornecido (via `useRouter`)

### Fase 1B - Concluida

Implementado:
- `frontend/app/ajuda/page.tsx` — substituido o stub por conteudo real
  - usa `AppShell` para layout
  - exporta `metadata` com titulo e description
  - indice rapido com anchor links
  - FAQ em 6 secoes: Chat, Fotos/OCR/PDF, Notas e Score, Creditos, Compartilhamento, Conta e Login
  - glossario com 16 termos (vinhos + produto)
  - contato via `privacy@winegod.ai`
  - versao: v0.1.0 beta, Abril 2026
  - 3 subcomponentes locais: `Section`, `Q`, `Term`
  - conteudo alinhado com estado real: limites 5/15, exclusao manual, favoritos nao implementados
- build: 14 paginas, 0 erros

### Fase 1C - Concluida

Implementado:
- `frontend/lib/useAuth.ts`
  - hook minimo: retorna `{ user, credits, loading, error }`
  - chama `getUser()` se houver token, senao retorna guest state
  - distingue erro de rede (token presente, fetch falhou) de token expirado (401 removeu token)
- `frontend/app/conta/ContaContent.tsx` + `frontend/app/conta/page.tsx`
  - page.tsx e server component com metadata, renderiza ContaContent
  - ContaContent e client component com useAuth
  - auth guard: guest ve CTA de login, logado ve perfil
  - perfil: avatar, nome, email, provider, ultimo login, logout, link para /data-deletion
  - loading skeleton, error state com retry, guest state com LoginButton
- `frontend/app/plano/PlanoContent.tsx` + `frontend/app/plano/page.tsx`
  - mesma arquitetura server/client
  - auth guard: guest ve CTA com comparacao 5 vs 15 creditos
  - logado ve: plano Free ativo, barra de progresso de creditos, creditos usados/restantes, tabela de custos por tipo de midia
  - bloco "Em breve: Pro" honesto (sem billing, sem promessas)
  - loading skeleton, error state
- build: 14 paginas, 0 erros

### Fase 2A - Concluida

Implementado:
- `database/migrations/011_add_conversations.sql`
  - tabela `conversations`: id VARCHAR(36) PK, user_id FK, title, messages JSONB, created_at, updated_at
  - indice por (user_id, updated_at DESC)
  - ON DELETE CASCADE para users
  - nota: 010 ja estava ocupado por `010_discovery_log.sql`, por isso usou 011
- `database/rollback/011_rollback.sql`
  - DROP INDEX + DROP TABLE
- `backend/db/models_conversations.py`
  - CRUD: create_conversation, get_conversation, list_conversations, update_conversation, delete_conversation
  - list nao retorna messages no array (so id, title, timestamps) — otimizacao para sidebar
  - busca por title via ILIKE
  - paginacao com limit/offset
- `backend/routes/conversations.py`
  - endpoints: GET list, GET by id, POST, PUT, DELETE
  - autenticacao obrigatoria via get_current_user
  - ownership: 403 se user_id da conversa != usuario autenticado
  - parametros: q, limit, offset no GET list
  - POST exige id no body (compativel com session_id UUID do frontend)
- `backend/app.py`
  - conversations_bp registrado com url_prefix='/api'
- validacao: syntax OK, imports OK, SQL consistente

## Build e Validacao Ja Feitos

Validado localmente nesta conversa:
- `npm run build` em `frontend` passou apos as fases 0A/0B
- `npm run build` em `frontend` passou novamente com `/privacy`, `/terms` e `/data-deletion` presentes
- `npm run build` em `frontend` passou com a `1A` implementada
- as rotas legais aparecem no build output como paginas estaticas
- as rotas `/ajuda`, `/conta`, `/plano` e `/favoritos` aparecem no build output

Validacoes ainda pendentes de ambiente rodando:
- `GET /api/auth/me` em runtime retornando `provider` e `last_login`
- `GET /api/credits` com Bearer valido e com Bearer expirado
- `429` pre-SSE disparando `onCreditsExhausted` corretamente
- transicao automatica user -> guest quando token expira no meio da sessao
- smoke test das rotas:
  - `/privacy`
  - `/terms`
  - `/data-deletion`
  - `/ajuda`
  - `/conta`
  - `/plano`
  - `/favoritos`
- confirmacao visual das paginas legais no browser
- confirmacao visual do `AppShell` e da navegacao real do `Sidebar`
- confirmacao visual da pagina `/ajuda` com conteudo real

## Arquivos Alterados no Track Sidebar / Legal

Arquivos efetivamente mudados neste track:
- `backend/config.py`
- `backend/routes/auth.py`
- `backend/routes/credits.py`
- `frontend/lib/api.ts`
- `frontend/lib/auth.ts`
- `frontend/app/page.tsx`
- `frontend/components/auth/UserMenu.tsx`
- `frontend/components/LegalPage.tsx`
- `frontend/components/AppShell.tsx`
- `frontend/components/Sidebar.tsx`
- `frontend/app/not-found.tsx`
- `frontend/app/ajuda/page.tsx`
- `frontend/app/conta/page.tsx`
- `frontend/app/plano/page.tsx`
- `frontend/app/favoritos/page.tsx`
- `frontend/lib/useAuth.ts` *(novo — Fase 1C)*
- `frontend/app/conta/ContaContent.tsx` *(novo — Fase 1C)*
- `frontend/app/plano/PlanoContent.tsx` *(novo — Fase 1C)*
- `frontend/app/privacy/page.tsx`
- `frontend/app/terms/page.tsx`
- `frontend/app/data-deletion/page.tsx`
- `database/migrations/011_add_conversations.sql` *(novo — Fase 2A)*
- `database/rollback/011_rollback.sql` *(novo — Fase 2A)*
- `backend/db/models_conversations.py` *(novo — Fase 2A)*
- `backend/routes/conversations.py` *(novo — Fase 2A)*
- `backend/app.py` *(modificado — Fase 2A)*
- `frontend/lib/conversations.ts` *(novo — Fase 2C)*

### Fase 2B - Concluida (com correcoes de ownership e shell)

Implementado em `backend/routes/chat.py`:
- imports: `get_current_user`, `create_conversation`, `get_conversation`, `update_conversation`, `delete_conversation`, `DuplicateConversationError`
- `_get_session()`: sessoes incluem `clean_messages` (com backward compat)
- `_sanitize_user_message()`: mensagem limpa com prefixo de midia ([Foto], [Video], [PDF])
- `_generate_title()`: titulo do primeiro texto do usuario, fallback para resposta do Baco
- `_init_clean_messages()`: recarrega clean_messages do banco em server restart
- `_ensure_conversation_shell()`: cria shell vazia no primeiro chat autenticado de session_id novo; retorna True se criou (para cleanup)
- `_persist_conversation()`: atualiza messages e title no fim da resposta; ownership verificada inclusive em race condition (DuplicateConversationError -> recheck owner -> so update se owner confere)
- `_cleanup_conversation_shell()`: deleta shell vazia se resposta falhar; verifica ownership e so deleta se messages esta vazio
- `chat()`: shell criada no inicio, cleanup se baco falhar, persist se sucesso
- `chat_stream()`: `current_user` capturado antes do generator, shell criada antes do generator, cleanup se stream falhar, persist se sucesso
- nenhum outro arquivo alterado

Contrato de persistencia:
- usuario autenticado: shell criada no inicio do primeiro chat de session_id novo; messages e title preenchidos no fim da resposta bem-sucedida; se resposta falhar, shell vazia e removida
- guest: sem persistencia, comportamento inalterado
- mensagens salvas: texto do usuario (com prefixo [Foto]/[Video]/[PDF]) + resposta do Baco
- nunca persiste: base64, blobs, prompts internos OCR/PDF, contexto do resolver
- titulo: derivado do primeiro texto util do usuario, fallback para resposta do assistente; so definido na primeira resposta, nao recalculado depois
- ownership: verificada em todos os caminhos — _ensure, _persist, _cleanup; race condition com DuplicateConversationError faz recheck de owner antes de qualquer update

### Fase 2C - Concluida (com correcoes)

Implementado:
- `frontend/lib/conversations.ts` *(novo)*
  - tipos: `ConversationSummary`, `ConversationFull`
  - `fetchConversations()`: GET /api/conversations?limit=30 — lanca erro em falha (nao engole)
  - `fetchConversation(id)`: GET /api/conversations/<id> — retorna null em falha (uso individual)
- `frontend/lib/api.ts`
  - `setSessionId(id)` adicionado para restaurar sessao ao abrir conversa antiga
- `frontend/components/Sidebar.tsx`
  - props novas: `onOpenConversation`, `activeConversationId`, `conversationsRefreshKey`
  - estado interno: conversations, convLoading, convError
  - fetch de conversas no mount e quando `conversationsRefreshKey` muda
  - error state: convError setado quando fetchConversations lanca; limpo quando isLoggedIn muda para false
  - substituicao do placeholder de historico por lista real com 5 estados:
    - loading (skeleton pulse)
    - error (retry button)
    - guest (CTA login)
    - empty (texto informativo)
    - lista real (botoes com title truncado, active highlighting)
  - click: usa callback direto se na home, ou `router.push("/?conv=<id>")` se em outra pagina
  - conversas sem titulo (shells vazias) filtradas via `.filter(c => c.title)`
- `frontend/components/AppShell.tsx`
  - props novas repassadas para Sidebar: `onOpenConversation`, `activeConversationId`, `conversationsRefreshKey`
- `frontend/app/page.tsx`
  - estado novo: `conversationId` (persistido em sessionStorage), `convRefreshKey`
  - `handleOpenConversation(id)`: fetch do backend, converte messages (adiciona id/timestamp), seta estado
  - `handleNewChat`: reseta `conversationId`; so chama `resetSessionId()` se `user` esta logado (guest preserva sessao e creditos)
  - init effect: detecta `?conv=<id>` na URL (cross-page navigation), carrega conversa, limpa URL
  - init effect: restaura conversa do backend na refresh (fetch real, nao confia em MESSAGES_KEY)
  - `onDone` do chat: seta `conversationId = getSessionId()` para conversas novas autenticadas; bumpa `convRefreshKey`
  - persist messages effect: so escreve em MESSAGES_KEY quando `conversationId` e null (guest draft)
  - persist conversationId effect: quando `conversationId` e setado, limpa MESSAGES_KEY (draft -> backend-managed)
  - `loadMessages()`: pula storage se `CONV_ID_KEY` existe (init vai buscar do backend)
  - AppShell recebe `onOpenConversation`, `activeConversationId`, `conversationsRefreshKey`
- backend nao foi alterado

Contrato de storage:
- MESSAGES_KEY: usado SOMENTE para guest draft (sem conversationId ativo)
- CONV_ID_KEY: identifica conversa ativa autenticada; persist e restore por sessionStorage
- quando conversationId e setado, MESSAGES_KEY e limpo (transicao para backend-managed)
- quando conversationId e null, MESSAGES_KEY funciona normalmente (guest behavior original)
- refresh com conversa ativa: loadMessages retorna [], init busca do backend
- refresh sem conversa ativa: loadMessages carrega do storage (guest draft)

Contrato de navegacao:
- usuario autenticado: sidebar mostra lista real de conversas
- clicar conversa na home: callback direto, carrega messages, seta sessionId para conversa
- clicar conversa em outra pagina (/ajuda, /conta, etc.): navega para `/?conv=<id>`, home detecta e carrega
- novo chat: limpa messages, reseta conversationId; so reseta sessionId se user logado
- continuar conversa: sessionId aponta para o conversationId, backend recebe no mesmo fio
- conversa nova autenticada: onDone seta conversationId = sessionId automaticamente
- guest: sem historico backend, conversa local inalterada, sessionId preservado em novo chat

## Pontos de Cuidado

- O working tree esta sujo com varias alteracoes nao relacionadas ao sidebar/legal rollout.
- Nao reverta nem reorganize arquivos fora do escopo sem necessidade.
- Em especial, existem mudancas nao revisadas aqui em areas como:
  - `backend/routes/chat.py`
  - `backend/tools/media.py`
  - `backend/tools/resolver.py`
  - testes e arquivos de discovery
  - prompts e relatorios diversos

### Fase 2D - Concluida (com correcoes de storage)

Implementado:
- `frontend/lib/conversations.ts`
  - `migrateGuestConversation(id, title, messages)`: POST /api/conversations com id/title/messages; trata 201 (criado) e 409 (ja existe) como sucesso; 403 ou erro de rede retorna false
- `frontend/app/page.tsx`
  - `generateMigrationTitle()`: extrai titulo da primeira mensagem do usuario, stripando prefixos de midia; fallback para primeira resposta do assistente; fallback final "Nova conversa"
  - init effect: apos getUser() bem-sucedido, se nao ha CONV_ID_KEY nem ?conv=, checa sessionStorage[MESSAGES_KEY] para guest draft; se existe draft, sanitiza (so role+content), gera titulo, chama migrateGuestConversation com session_id atual; se sucesso, seta conversationId e bumpa convRefreshKey
  - idempotencia: retry/refresh nao duplica — 409 e tratado como sucesso; apos primeira migracao, CONV_ID_KEY existe e a branch de migracao nao e alcancada
  - se migracao falhar (backend fora, rede), draft permanece local
- backend nao foi alterado

Disciplina de storage (correcoes aplicadas):
- MESSAGES_KEY agora usa SOMENTE sessionStorage para leitura e escrita
  - `loadMessages()`: le apenas de sessionStorage (nao mais localStorage)
  - persist effect: escreve apenas em sessionStorage, removeu write de localStorage e dep de `user`
  - migracao: le apenas de sessionStorage
- localStorage[MESSAGES_KEY] nunca e mais escrito; so e removido em cleanup (logout, conversationId transition)
- isso fecha o vazamento entre sessoes: draft de usuario anterior nao vaza para guest/login novo
- handleLogout agora limpa: messages state, conversationId state, MESSAGES_KEY de ambos storages

Contrato de migracao:
- disparo: init effect apos getUser() resolver, branch else (sem ?conv=, sem CONV_ID_KEY)
- fonte: sessionStorage[MESSAGES_KEY] — garante que e o draft do guest na aba atual
- condicao: pelo menos uma mensagem com role+content
- id da conversa: session_id atual do guest (getSessionId())
- titulo: primeira mensagem util do usuario, sem prefixos de midia
- persistencia: somente role+content — sem imagePreviews, wines, quickButtons, blobs
- idempotencia: 409 = sucesso (conversa ja existe com mesmo id)
- falha: draft permanece local, nenhum efeito colateral

### Fase 3A - Concluida

Implementado:
- `database/migrations/012_add_conversation_saved.sql` *(novo)*
  - `is_saved BOOLEAN NOT NULL DEFAULT FALSE`
  - `saved_at TIMESTAMP NULL`
  - indice `idx_conversations_saved(user_id, is_saved, saved_at DESC NULLS LAST, updated_at DESC)`
- `database/rollback/012_rollback.sql` *(novo)*
  - DROP INDEX + DROP COLUMN saved_at + DROP COLUMN is_saved
- `backend/db/models_conversations.py`
  - todos os SELECT/RETURNING incluem `is_saved, saved_at`
  - `_row_to_dict()`: retorna `is_saved` e `saved_at` em todos os dicts
  - `list_conversations()`: novo parametro `saved` (True/False/None) para filtrar por is_saved; quando `saved=True`, ordena por `saved_at DESC NULLS LAST`
  - `set_saved(conversation_id, saved)`: marca (is_saved=TRUE, saved_at=NOW) ou desmarca (is_saved=FALSE, saved_at=NULL)
- `backend/routes/conversations.py`
  - import de `set_saved`
  - `GET /api/conversations`: aceita `?saved=true` ou `?saved=false`
  - `PUT /api/conversations/<id>/saved`: auth + ownership + body `{"saved": true|false}`; retorna conversa atualizada; 400 se saved nao for boolean
- frontend nao foi alterado

Endpoints novos/alterados:
- `GET /api/conversations?saved=true` — lista conversas salvas, ordenadas por saved_at DESC
- `PUT /api/conversations/<id>/saved` — marca/desmarca salvo

### Fase 3B - Concluida (com correcao de auth error)

Implementado:
- `frontend/lib/conversations.ts`
  - `ConversationSummary` expandida com `is_saved?` e `saved_at?` opcionais
  - `fetchSavedConversations()`: GET /api/conversations?saved=true&limit=50; lanca em erro (Sidebar pattern)
- `frontend/app/favoritos/page.tsx`
  - server component com metadata atualizada ("Conversas salvas — winegod.ai")
  - renderiza FavoritosContent
- `frontend/app/favoritos/FavoritosContent.tsx` *(novo)*
  - client component com useAuth + AppShell
  - 6 estados em prioridade: loading, auth error (retry=reload), fetch error (retry=loadSaved), guest (CTA login), empty, lista real
  - ErrorState aceita `message` opcional para diferenciar auth error de fetch error
  - lista: titulo truncado + "Salva em DD mmm YYYY" (formatado via saved_at)
  - navegacao: clique em item faz `router.push("/?conv=<id>")` (reusa cross-page nav da 2C)
  - conversas sem titulo filtradas via `.filter(c => c.title)`
- backend nao foi alterado

### Fase 3C - Concluida (com correcoes de cleanup e texto)

Implementado:
- `backend/db/models_auth.py`
  - `delete_user(user_id)`: DELETE FROM users; cascade: conversations deletadas, message_log.user_id SET NULL
- `backend/routes/auth.py`
  - import de `delete_user`
  - `DELETE /api/auth/me`: auth obrigatoria, deleta usuario autenticado, retorna 200/401/404
- `frontend/lib/auth.ts`
  - `deleteAccount()`: chama DELETE /api/auth/me, remove token em sucesso, retorna boolean
- `frontend/app/data-deletion/DeleteAccountSection.tsx` *(novo)*
  - client component com 3 estados: guest (texto + email fallback), botao de exclusao, confirmacao com acao real
  - confirmacao: botao vermelho + cancelar, loading state, error state com retry
  - sucesso: deleteAccount() remove token, depois limpa CONV_ID_KEY + MESSAGES_KEY + session_id, depois redireciona para /
- `frontend/app/data-deletion/page.tsx`
  - secoes "Como solicitar" e "Exclusao automatica (em desenvolvimento)" substituidas por `<DeleteAccountSection />`
  - "O que e excluido": agora lista historico de conversas e conversas salvas explicitamente
  - "O que nao e excluido": agora menciona registros de uso anonimizados e que dados locais sao limpos automaticamente
- `/conta` continua com link para `/data-deletion` — nao precisa de mudanca

Dados afetados pela exclusao:
- backend: users row deletada, conversations CASCADE, message_log SET NULL
- frontend: token removido, CONV_ID_KEY limpo, MESSAGES_KEY limpo, session_id resetado
- resultado: usuario volta para guest state completamente limpo

### Fase 4A - Concluida (com correcao de sidebar desktop)

Implementado:
- `frontend/components/SearchModal.tsx` *(novo)*
  - modal com overlay, input com autofocus, placeholder para resultados
  - fecha com Escape (listener interno) e com click no overlay
  - visual: rounded-xl, borda wine-border, sombra, badge Esc
- `frontend/components/Sidebar.tsx`
  - `onToggle` substituido por `onSearch` no interface e no wiring
  - collapsed icon strip: Menu icon (hamburger) abre sidebar expandido, Search icon abre modal
  - layout do collapsed strip: Menu → separador → Plus + Search → separador → nav links
  - expanded sidebar: Search button chama `onSearch` + `onClose`
  - props novas: `onSearch`, `onExpandSidebar`
  - import de `Menu` de lucide-react
- `frontend/components/AppShell.tsx`
  - import de `SearchModal`
  - estado `searchOpen` controlado localmente
  - `Ctrl+K` listener: abre modal, nao dispara em input/textarea/contentEditable, e.preventDefault()
  - passa `onSearch`, `onExpandSidebar` para Sidebar
  - renderiza `<SearchModal isOpen={searchOpen} onClose={...} />`
- backend nao foi alterado

Atalhos e acessos entregues:
- click no icone Menu (collapsed strip): abre sidebar expandido no desktop
- click no icone Buscar (collapsed strip): abre search modal
- click em "Buscar" (expanded sidebar): abre modal + fecha sidebar
- `Ctrl+K` (ou `Cmd+K`): abre modal, exceto dentro de input/textarea/contentEditable
- `Escape`: fecha modal
- click no overlay: fecha modal

Correcao aplicada:
- icone Menu (hamburger) adicionado ao topo do collapsed strip para abrir sidebar expandido no desktop; antes, nao havia caminho desktop para acessar o sidebar expandido apos Search passar a abrir o modal

### Fase 4B - Concluida (com correcoes de race condition)

Implementado:
- `frontend/lib/conversations.ts`
  - `searchConversations(query)`: GET /api/conversations?q=<query>&limit=10; lanca em erro
- `frontend/components/SearchModal.tsx`
  - reescrito com busca real: estado controlado (query, results, saved, loading, error)
  - debounce 300ms via setTimeout ref
  - version guard completo via versionRef:
    - query trocando de texto: versao incrementada, resposta antiga descartada
    - query ficando vazia: versao incrementada, results limpos, resposta em voo descartada
    - modal fechando: versao resetada para 0, resposta em voo descartada
  - saved: carregado uma vez ao abrir modal, filtrado client-side por query
  - dedup: results filtrados para excluir salvos
  - 5 estados: idle, loading, error, empty, resultados (Conversas + Salvos)
  - click: onOpenConversation(id) + onClose()
- `frontend/components/AppShell.tsx`
  - SearchModal recebe onOpenConversation: callback direto na home, router.push fora dela
- backend nao foi alterado

### Fase 4C - Concluida (com correcoes de cross-page guest e reset de conversa)

Implementado:
- `frontend/components/SearchModal.tsx`
  - import de `MessageCircle`
  - prop `onAskBaco: (text: string) => void`
  - CTA footer: aparece quando ha query nao-vazia e nao esta loading/error
  - texto: 'Perguntar ao Baco sobre "<query>"' com truncamento a 60 chars
  - click chama `onAskBaco(query.trim())`
- `frontend/components/AppShell.tsx`
  - prop `onAskBaco?: (text: string) => void`
  - SearchModal recebe onAskBaco: callback direto na home, `router.push("/?ask=<text>")` fora dela
  - modal fecha apos disparar CTA
- `frontend/app/page.tsx`
  - estado `pendingAsk` para processar pergunta de forma segura
  - `handleAskBaco`: chama handleNewChat + setPendingAsk
  - init effect: `?ask=` tratado NO INICIO do init, antes de qualquer checagem de auth; funciona para guest, autenticado e fallback guest
  - quando `?ask=` detectado no init: limpa URL, reseta messages/conversationId/storage/typing/credits, reseta sessionId se checkLoggedIn() (espelhando handleNewChat), seta pendingAsk
  - se askParam presente e auth sucede: pula conv/restore/migrate (askParam tem prioridade)
  - effect apos handleSend: processa pendingAsk quando isTyping e false
  - AppShell recebe `onAskBaco={handleAskBaco}`
- backend nao foi alterado

Correcoes aplicadas sobre a versao inicial da 4C:
1. `?ask=` movido para fora do ramo autenticado: agora funciona para guest e fallback guest (token presente mas getUser falha)
2. cross-page `?ask=` agora reseta conversation state (messages, conversationId, sessionId se logado, storage) antes de setPendingAsk, matching o comportamento de handleAskBaco na home

### Pos-plano: UI de toggle salvo no chat - Concluido (com correcoes de concorrencia)

Implementado como extensao pos-plano (rollout original 0-4C ja estava fechado):
- `frontend/lib/conversations.ts`
  - `ConversationFull` expandida com `is_saved?` e `saved_at?`
  - `updateConversationSaved(id, saved)`: PUT /api/conversations/<id>/saved com body {saved}
- `frontend/app/page.tsx`
  - estado `conversationSaved` (default false)
  - estado `togglePending` e `toggleError` para feedback e lock
  - `toggleRequestRef` (useRef numerico) como version counter
  - effect que incrementa ref e reseta pending/error ao mudar conversationId — invalida toggles em voo de outra conversa
  - hidratacao em handleOpenConversation, init effect (?conv= e savedConvId) via `conv.is_saved`
  - reset de conversationSaved em handleNewChat
  - `handleToggleSaved`:
    - guard: retorna early se `!conversationId` ou `togglePending`
    - captura `targetId` e incrementa `version`
    - optimistic update + setTogglePending(true) + setToggleError(false)
    - apos API, guard de staleness: `toggleRequestRef.current !== version` → descarta (conversa mudou ou toggle mais novo)
    - sucesso: setTogglePending(false) + bump convRefreshKey
    - falha: rollback saved + setTogglePending(false) + setToggleError(true)
  - AppShell recebe `activeConversationSaved`, `onToggleSaved`, `toggleSavedPending`, `toggleSavedError`
- `frontend/components/AppShell.tsx`
  - import de `Heart` de lucide-react
  - props `activeConversationSaved?`, `onToggleSaved?`, `toggleSavedPending?`, `toggleSavedError?`
  - botao Heart no header, visivel apenas quando `user && activeConversationId && onToggleSaved`
  - `disabled={toggleSavedPending}` + `opacity-50 cursor-not-allowed` durante request
  - cor do icone: red-500 em erro, wine-accent (fill) quando salvo, wine-muted quando nao
  - title dinamico: "Erro ao salvar. Clique para tentar novamente." / "Salvando..." / "Salvar conversa" / "Remover dos salvos"
- backend nao foi alterado (reutiliza 3A)

Correcoes aplicadas sobre a versao inicial:
1. lock via togglePending: bloqueia double-click durante request em voo
2. version guard via toggleRequestRef: incrementado em cada toggle E em cada mudanca de conversationId; respostas staless sao descartadas
3. cross-conversation guard: se usuario muda de conversa com toggle em voo, o ref e incrementado, o pending e limpo, e a resposta antiga e descartada sem tocar o novo conversationSaved
4. feedback de UI: botao disabled durante pending, tooltip de erro ao falhar, cor red-500 em erro

## Proximo Passo Recomendado

O rollout completo do sidebar esta concluido. Todas as fases do plano foram implementadas:
- Fase 0: auth e creditos
- Fase 0.5: paginas legais
- Fase 1: shell, paginas simples
- Fase 2: historico (backend, frontend, migracao guest)
- Fase 3: favoritos, exclusao de conta
- Fase 4: busca (modal, resultados, CTA)
- Pos-plano: UI de toggle salvo no chat

Proximos passos fora do plano original:
- prioridade operacional atual nesta coordenacao: validacao visual/browser dos fluxos guest e atalhos do sidebar
- aplicar migrations 011 e 012 no banco de producao
- teste manual completo end-to-end com stack rodando
- refinamentos visuais apos validacao no browser

### Pos-plano: Validacao runtime local (2026-04-14)

Executado de verdade:
- backend booted localmente (FLASK em 5000) com DATABASE_URL real
- `GET /health` = 200 → `database: connected`, `wines_count_estimate: 2501466`, `claude_api: configured` → stack completo saudavel
- `GET /api/conversations` sem auth → 401 (auth guard OK)
- `GET /api/conversations?saved=true` sem auth → 401 (3A route montada)
- `PUT /api/conversations/<id>/saved` sem auth → 401 (3A endpoint montado)
- `PUT /saved` com Bearer invalido → 401 (auth prioriza sobre validacao de payload)
- `DELETE /api/auth/me` sem auth → 401 (3C endpoint montado)
- `GET /api/auth/me` sem auth → 401
- `GET /api/credits` guest sem session → 200
- frontend dev server booted em 3000
- GET em todas as 8 rotas (/, /favoritos, /conta, /plano, /ajuda, /privacy, /terms, /data-deletion) → 200
- HTML de `/favoritos` validado por inspecao: collapsed strip com Menu + Plus + Search + nav links presentes, sidebar expandido renderizado, history com guest CTA "Entre com sua conta", page com titulo "Conversas salvas" + skeleton loader, title metadata correta, LoginButton "Entrar"

Findings reais:
- **GUEST_CREDIT_LIMIT mismatch** — CORRIGIDO em 2026-04-14:
  - antes: `backend/config.py` default `1000`, runtime guest `limit: 1000`
  - depois: default `5`, runtime guest `limit: 5` confirmado via `GET /api/credits` real
  - env override continua possivel via `GUEST_CREDIT_LIMIT` env var; default agora coincide com o contrato do plano/handoff

Nao validado (bloqueado por ambiente):
- fluxos autenticados (OAuth real): Google/Facebook/Apple/Microsoft sign-in nao executado
- endpoints que requerem JWT valido: `GET /api/conversations` autenticado, criacao/delecao de conversa, toggle salvo, migracao guest->logado
- SSE `POST /api/chat/stream` real: requer auth + Claude API + interacao
- interacoes de navegador: clicks (SearchModal, toggle salvo, CTA "Perguntar ao Baco"), `Ctrl+K`, `Escape`, shortcuts
- navegacao cross-page com `?conv=<id>` e `?ask=<text>` em runtime real
- toggle salvo no chat em runtime
- aplicacao das migrations 011 e 012 no banco: nao confirmada (precisa SELECT no banco com credenciais admin)

Observacoes operacionais:
- apos varios curls concorrentes, Next.js dev server e backend ficaram lentos/sem resposta (comportamento tipico de dev mode no Windows, nao bug da aplicacao)
- para validacao visual completa, ambiente real com OAuth configurado + browser sao necessarios

Conclusao operacional desta etapa:
- a divergencia de `GUEST_CREDIT_LIMIT` foi corrigida
- hardening runtime local sem OAuth/browser volta a ficar sem blocker conhecido
- os proximos gaps reais continuam sendo browser/interacao e fluxos autenticados dependentes de ambiente

### Pos-plano: Validacao visual/browser dos fluxos guest e atalhos do sidebar (2026-04-14)

Status: **NAO executada nesta aba — bloqueada por falta de tool de browser automation**.

Contexto honesto:
- esta aba nao dispoe de Playwright, Puppeteer ou qualquer tool de browser real
- ferramentas disponiveis: Bash, Read, Edit, Grep, Glob, Write
- curl foi usado para verificar resposta HTTP e inspecao estatica de HTML, mas isso NAO valida:
  - execucao de JavaScript client-side
  - interacoes de teclado (Ctrl+K, Escape, foco em input/textarea)
  - click em botoes
  - abertura/fechamento de SearchModal
  - toggle salvo em runtime
  - CTA "Perguntar ao Baco" disparando novo chat
  - navegacao cross-page real (?conv=, ?ask=)
  - estado guest visual apos carregamento do useAuth

O que foi confirmado nesta aba (nao substitui validacao browser):
- build static continua passando: 14 paginas, 0 erros
- tsc --noEmit: exit 0 (sequencial apos build)
- codigo no disco nao regrediu desde o ultimo checkpoint (config.py so mudou GUEST_CREDIT_LIMIT default)
- instabilidade do Next.js dev server em Windows observada novamente (compile-on-demand deadlock) ao tentar re-hitar rotas multiplas vezes concorrentemente — nao e bug de app

Validacao browser necessaria (pendente de executor humano ou ambiente com browser tool):

1. Home e shell (`/`):
   - [ ] shell, header e collapsed strip renderizam
   - [ ] Menu icon abre sidebar expandido no desktop
   - [ ] hamburger do header abre sidebar no mobile
   - [ ] overlay do sidebar fecha com click

2. SearchModal e atalhos:
   - [ ] click em Buscar (collapsed) abre modal
   - [ ] click em Buscar (expandido) abre modal + fecha sidebar
   - [ ] Ctrl+K (Windows) e Cmd+K (Mac) abrem modal fora de input/textarea
   - [ ] Ctrl+K NAO abre modal quando foco esta em input do chat
   - [ ] Escape fecha modal
   - [ ] click no overlay fecha modal

3. SearchModal estados (guest):
   - [ ] idle (sem query): "Digite para buscar em suas conversas."
   - [ ] query sem resultado: "Nenhum resultado encontrado." + CTA
   - [ ] CTA "Perguntar ao Baco sobre <query>" visivel
   - [ ] click no CTA fecha modal e inicia novo chat com a pergunta

4. Paginas guest:
   - [ ] `/favoritos` → GuestState com LoginButton
   - [ ] `/conta` → GuestState com LoginButton
   - [ ] `/plano` → GuestState com comparacao 5/15 creditos
   - [ ] `/ajuda` → conteudo completo renderiza
   - [ ] `/privacy`, `/terms`, `/data-deletion` → conteudo legal renderiza
   - [ ] `/data-deletion` para guest → mostra texto de email fallback (nao o botao de exclusao)

5. Chat guest:
   - [ ] home mostra WelcomeScreen inicial
   - [ ] digitar mensagem habilita enviar
   - [ ] enviar reflete user message + resposta do Baco (requer Claude API e backend)
   - [ ] contador de creditos decresce a cada envio ate 0
   - [ ] ao chegar em 0, banner de creditos exauridos aparece e input fica disabled

6. Cross-page navigation guest:
   - [ ] acessar `/?ask=teste` carrega home com a pergunta iniciada (requer Claude API)
   - [ ] botao "Novo chat" do sidebar limpa state

Ferramenta de validacao recomendada para o proximo passo:
- executor humano abrindo `http://localhost:3001` (ou 3000) apos `npm run dev`
- ou uma aba com tool de browser automation (Playwright/Puppeteer)

**Roteiro manual pronto em:** `reports/ROTEIRO_VALIDACAO_BROWSER_SIDEBAR.md` — 12 passos enxutos cobrindo home/shell, SearchModal + atalhos, guard de `Ctrl+K` em input, estado empty + CTA, paginas guest (`/favoritos`, `/conta`, `/plano`, `/data-deletion`). Inclui template de anotacao de falha. Proximo executor (humano ou agente com browser tool) pode seguir direto.

Nao e possivel marcar este pos-plano como fechado sem esse passo. Backend/static continuam saudaveis.

## Prompt Sugerido Para Um Novo Chat

O rollout do sidebar esta completo. Todas as fases do plano (0 a 4) foram implementadas e aprovadas.

Para retomar trabalho neste repositorio, leia:
- `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
- `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`

Fases concluidas:
- 0A/0B: auth e creditos
- 0.5A/0.5B: paginas legais
- 1A/1B/1C: shell, ajuda, conta, plano
- 2A/2B/2C/2D: historico (backend, frontend, migracao guest)
- 3A/3B/3C: favoritos, exclusao de conta
- 4A/4B/4C: busca (modal, resultados, CTA cross-page)

## Log de Checkpoints

### 2026-04-13 - Checkpoint inicial deste handoff

Registrado neste documento:
- leitura e entendimento profundo do `PLANO_IMPLEMENTACAO_SIDEBAR.md`
- fechamento da Fase 0A
- fechamento da Fase 0B
- implementacao do `LegalPage`
- fechamento da Fase 0.5B
- build do frontend com as rotas legais compilando como paginas estaticas
- registro dos riscos de conteudo das paginas legais

### 2026-04-13 - Fase 1A implementada, revisada e corrigida

Registrado neste documento:
- `AppShell`, `Sidebar` com navegacao real, `not-found`, stubs de rotas
- build do frontend com 14 paginas
- 2 regressoes identificadas e corrigidas via patch:
  - `AppShell` auto-hidrata auth fora da home
  - `Novo chat` navega para `/` quando `onNewChat` nao e fornecido

### 2026-04-13 - Fase 1B concluida

Registrado neste documento:
- `/ajuda` substituido de stub para conteudo real
- FAQ em 6 secoes, glossario com 16 termos, contato e versao
- conteudo alinhado com estado real do produto (limites 5/15, exclusao manual)
- build do frontend segue passando com 14 paginas

### 2026-04-13 - Fase 1C concluida

Registrado neste documento:
- `/conta` e `/plano` substituidos de stubs para conteudo real
- `useAuth` hook criado em `frontend/lib/useAuth.ts`
- ambas as paginas: auth guard, loading skeleton, error state, guest CTA
- `/conta`: perfil, provider, ultimo login, logout, link para data-deletion
- `/plano`: creditos reais, barra de progresso, tabela de custos, bloco Pro honesto
- build do frontend segue passando com 14 paginas

### 2026-04-13 - Fase 2A concluida

Registrado neste documento:
- migration 011 (conversations): tabela, indice, rollback
- models_conversations.py: CRUD completo com paginacao e busca por title
- conversations.py: 5 endpoints com auth obrigatoria e ownership
- app.py: blueprint registrado
- nota: 010 ja ocupado por discovery_log, usou 011
- validacao: syntax OK, imports OK, SQL consistente
- frontend nao foi tocado

### 2026-04-13 - Fase 2B concluida (com correcoes de ownership e shell)

Implementado em `backend/routes/chat.py`:
- ponte `session_id -> conversation` para usuarios autenticados
- 6 helpers privados: `_sanitize_user_message`, `_generate_title`, `_init_clean_messages`, `_ensure_conversation_shell`, `_persist_conversation`, `_cleanup_conversation_shell`
- shell vazia criada no inicio do primeiro chat autenticado de session_id novo
- messages e title preenchidos no fim da resposta bem-sucedida
- se a resposta falhar, shell vazia e removida (sem fantasma)
- ownership verificada em todos os caminhos: _ensure, _persist, _cleanup
- race condition (DuplicateConversationError) faz recheck de owner antes de qualquer update
- guest continua sem persistencia, sem regressao
- nenhum payload tecnico persiste: sem base64, blob, prompt OCR/PDF, contexto do resolver
- nenhum arquivo frontend alterado

Correcoes aplicadas sobre a versao inicial:
- bug de ownership no fallback de DuplicateConversationError: agora faz recheck
- alinhamento ao contrato: shell criada no inicio, nao so no save final
- cleanup de shell vazia em caso de falha de resposta

Validacao executada:
- syntax OK: py_compile em chat.py e demais arquivos do track
- app boot OK: create_app() com 9 blueprints
- testes unitarios: _sanitize_user_message, _generate_title, _get_session, signatures
- NAO foi feita validacao HTTP/SSE real (requer stack completa)

Riscos resolvidos pela 2C:
- frontend agora sabe que conversas existem
- `Novo chat` agora reseta conversation state e sessionId

### 2026-04-13 - Fase 2C concluida (com correcoes)

Implementado:
- `frontend/lib/conversations.ts`: API helpers, fetchConversations lanca em erro
- `frontend/lib/api.ts`: `setSessionId()` adicionado
- `frontend/components/Sidebar.tsx`: lista real, error state funcional, limpa erro ao deslogar
- `frontend/components/AppShell.tsx`: props de conversa repassadas
- `frontend/app/page.tsx`: conversationId, storage separado, guest preservado, active state coerente

Correcoes aplicadas sobre a versao inicial da 2C:
1. guest credit/session: handleNewChat so chama resetSessionId se user logado
2. storage mixing: MESSAGES_KEY so para guest draft; loadMessages pula se CONV_ID_KEY existe; persist effect skipa se conversationId ativo; conversationId effect limpa MESSAGES_KEY; refresh com conversa busca do backend
3. error state: fetchConversations lanca em erro real; Sidebar catch funciona; convError limpo ao deslogar
4. active state: onDone seta conversationId = getSessionId() para conversas novas autenticadas
5. fallback user->guest: onDone faz await refreshCredits() antes de checar checkLoggedIn(); se token expirou mid-session, refreshCredits detecta 401 e remove token antes da promocao; convRefreshKey tambem so bumpa apos resolucao

Validacao executada:
- npm run build: 14 paginas, zero errors
- tsc --noEmit: exit code 0 (requer build previo para gerar .next/types — comportamento padrao Next.js)
- NAO foi feita validacao visual no browser (requer stack completa)
- NAO foi feita validacao HTTP real

Riscos resolvidos pela 2D:
- guest que faz login NAO perde mais a conversa ativa — draft e migrado para o backend

### 2026-04-13 - Fase 2D concluida (com correcoes de storage)

Implementado:
- `frontend/lib/conversations.ts`: migrateGuestConversation — POST com idempotencia (201/409)
- `frontend/app/page.tsx`: generateMigrationTitle + migracao no init effect apos login

Correcoes aplicadas sobre a versao inicial da 2D:
1. migracao agora le SOMENTE de sessionStorage (nao mais localStorage || sessionStorage)
2. loadMessages() alinhado: le SOMENTE de sessionStorage
3. persist effect alinhado: escreve SOMENTE em sessionStorage, removeu localStorage write
4. handleLogout agora limpa: messages state, conversationId state, MESSAGES_KEY de ambos storages
5. localStorage[MESSAGES_KEY] nunca e mais escrito; so removido em cleanup

Validacao executada:
- npm run build: 14 paginas, zero errors
- tsc --noEmit: exit code 0 (apos build)
- NAO foi feita validacao visual no browser
- NAO foi feita validacao HTTP real

Riscos resolvidos pela 3A:
- backend agora tem schema e endpoints para salvar/desmarcar conversas

### 2026-04-13 - Fase 3A concluida

Implementado:
- migration 012: is_saved + saved_at + indice
- models_conversations.py: set_saved, list com filtro saved, _row_to_dict com 8 colunas
- conversations.py: PUT /saved com auth+ownership, GET ?saved=true

Validacao executada:
- py_compile em models_conversations.py, conversations.py, chat.py, app.py: OK
- create_app() com 9 blueprints, rota /api/conversations/<conv_id>/saved presente: OK
- testes unitarios: set_saved signature, list_conversations saved param, _row_to_dict 8 colunas: OK
- NAO foi feita validacao HTTP real
- frontend nao foi alterado

Riscos resolvidos pela 3B:
- /favoritos agora e pagina real, nao stub

### 2026-04-13 - Fase 3B concluida (com correcao de auth error)

Implementado:
- conversations.ts: ConversationSummary expandida, fetchSavedConversations
- favoritos/page.tsx: server component com metadata
- favoritos/FavoritosContent.tsx: client component com 6 estados (auth error adicionado)

Correcao aplicada:
- useAuth().error agora e tratado explicitamente: auth error mostra mensagem de verificacao + retry=reload, alinhado ao padrao de ContaContent/PlanoContent

Validacao executada:
- npm run build: 14 paginas, zero errors (favoritos 2.72kB)
- tsc --noEmit: exit code 0 (apos build)
- NAO foi feita validacao visual no browser
- NAO foi feita validacao HTTP real

Riscos para a 3C:
- migration 012 precisa estar aplicada no banco de producao
- UI de toggle salvo no chat ainda nao existe (o usuario nao tem como salvar uma conversa ainda — precisa do toggle na UI do chat ou em outro lugar, fora do escopo 3B)
- image previews nao sobrevivem ao carregar conversa do backend

### 2026-04-13 - Fase 3C concluida (com correcoes de cleanup e texto)

Implementado:
- backend: delete_user + DELETE /api/auth/me com cascade
- frontend: deleteAccount() em auth.ts + DeleteAccountSection com cleanup completo
- /data-deletion: texto alinhado ao comportamento real

Correcoes aplicadas:
1. pos-exclusao: DeleteAccountSection agora limpa CONV_ID_KEY, MESSAGES_KEY, session_id antes de redirecionar para /
2. texto /data-deletion: "O que e excluido" agora lista conversas e favoritos; "O que nao e excluido" menciona registros anonimizados

Validacao executada:
- py_compile em models_auth.py, auth.py, app.py: OK
- create_app() com DELETE /api/auth/me registrada: OK
- npm run build: 14 paginas, zero errors (/data-deletion 2.31kB)
- tsc --noEmit: exit code 0 (apos build)
- NAO foi feita validacao HTTP real
- NAO foi feita validacao visual no browser

Riscos resolvidos pela 4A:
- botao Buscar agora abre modal real em vez de togglear o sidebar

### 2026-04-14 - Fase 4A concluida (com correcao de sidebar desktop)

Implementado:
- SearchModal.tsx: modal com input, placeholder, overlay, Escape
- Sidebar.tsx: Menu icon + onExpandSidebar, Search icon + onSearch
- AppShell.tsx: searchOpen state, Ctrl+K listener, SearchModal render, onExpandSidebar

Correcao aplicada:
- Menu icon (hamburger) adicionado ao topo do collapsed strip para abrir sidebar expandido no desktop

Validacao executada:
- npm run build: 14 paginas, zero errors
- tsc --noEmit: exit code 0 (apos build)
- NAO foi feita validacao visual no browser

Riscos resolvidos pela 4B:
- SearchModal agora busca resultados reais

### 2026-04-14 - Fase 4B concluida (com correcoes de race condition)

Implementado ate aqui:
- conversations.ts: searchConversations(query)
- SearchModal.tsx: reescrito com busca real, debounce, secoes Conversas/Salvos, dedup, 5 estados
- AppShell.tsx: SearchModal recebe onOpenConversation com callback direto ou router.push

Validacao executada nesta revisao:
- npm run build: 14 paginas, zero errors
- tsc --noEmit: exit code 0 (apos build)
- NAO foi feita validacao visual no browser
- NAO foi feita validacao HTTP real

Correcoes aplicadas:
1. versionRef: cada effect run com query nao-vazia incrementa versao; resposta so aplica se versao confere
2. query vazia: agora tambem incrementa versao, invalidando qualquer request em voo
3. modal fechando: versao resetada para 0

Validacao final:
- npm run build: 14 paginas, zero errors
- tsc --noEmit: exit code 0 (apos build)
- NAO foi feita validacao visual no browser

Riscos resolvidos pela 4C:
- busca sem resultados agora oferece CTA para perguntar ao Baco

### 2026-04-14 - Fase 4C concluida (com correcoes de cross-page guest e reset)

Implementado:
- SearchModal.tsx: CTA footer "Perguntar ao Baco sobre <texto>", prop onAskBaco
- AppShell.tsx: prop onAskBaco, wiring callback/router.push
- page.tsx: pendingAsk state, handleAskBaco, ?ask= URL param tratado no inicio do init, effect de processamento

Correcoes aplicadas sobre a versao inicial:
1. `?ask=` movido para fora do ramo autenticado — agora funciona para guest, autenticado e fallback guest (token presente mas getUser falha)
2. cross-page `?ask=` agora reseta messages/conversationId/storage/isTyping/creditsExhausted + sessionId (se logado) antes de setPendingAsk — garante novo chat

Validacao final:
- npm run build: 14 paginas, zero errors
- tsc --noEmit: exit code 0 (apos build sequencial)
- NAO foi feita validacao visual no browser
- NAO foi feita validacao HTTP real

Rollout completo. Proximos passos fora do plano original:
- prioridade operacional atual nesta coordenacao: validacao visual/browser dos fluxos guest e atalhos do sidebar
- aplicar migrations 011 e 012 no banco de producao
- teste manual completo end-to-end com stack rodando
- implementar UI de toggle salvo no chat (feito — ver checkpoints abaixo)
- refinamentos visuais

### 2026-04-14 - Pos-plano: UI de toggle salvo no chat concluida (com correcoes de concorrencia)

Implementado:
- conversations.ts: ConversationFull expandida (is_saved, saved_at); updateConversationSaved(id, saved) wrapper PUT /api/conversations/<id>/saved
- page.tsx: estado conversationSaved + togglePending + toggleError + toggleRequestRef; effect de invalidacao ao mudar conversationId; hidratacao em handleOpenConversation + init effect (ambos branches); reset em handleNewChat; handleToggleSaved com version guard
- AppShell.tsx: import Heart, props activeConversationSaved/onToggleSaved/toggleSavedPending/toggleSavedError, botao no header com disabled/opacity em pending e cor red-500 + tooltip em erro

Correcoes de concorrencia aplicadas:
1. lock via togglePending: bloqueia double-click enquanto request em voo
2. version guard via toggleRequestRef: increment a cada toggle E a cada mudanca de conversationId; respostas stale descartadas
3. cross-conversation guard: se usuario muda conversa com toggle em voo, ref incrementado + pending resetado + resposta antiga nao toca conversa nova
4. UI honesta: botao disabled durante request, tooltip e cor red-500 em erro

Gates de visibilidade (inalterados):
- guest: botao nao aparece
- autenticado sem conversa ativa: botao nao aparece
- draft autenticado antes do primeiro send: botao nao aparece
- conversa backend-managed: botao aparece, estado reflete is_saved

Validacao executada:
- npm run build: 14 paginas, zero errors
- tsc --noEmit: exit code 0 (sequencial apos build)
- NAO foi feita validacao visual no browser
- NAO foi feita validacao HTTP real

Esta extensao reutiliza o endpoint da 3A, nao reabre fases 0-4.

### 2026-04-14 - Pos-plano: Validacao runtime local

Backend booted em 5000 (stack saudavel: DB connected, 2.5M vinhos, Claude API configured).
Frontend dev booted em 3000. Todas as 8 rotas retornaram 200.
HTML de `/favoritos` validado: Menu icon (4A) presente, sidebar OK, guest CTA presente, skeleton/title corretos.

Endpoints autenticacao testados sem token:
- /api/conversations (GET/POST/PUT/DELETE, /saved) → 401 consistente
- /api/auth/me (GET/DELETE) → 401
- /api/credits guest → 200
- /health → 200 com database connected

Validacao static (ja feita):
- npm run build: 14 paginas, zero errors
- tsc --noEmit: exit 0 (apos build)

Finding real bloqueante desta validacao — CORRIGIDO em 2026-04-14:
- antes: GUEST_CREDIT_LIMIT runtime = 1000 (config default), plano/handoff/UI esperam 5
- depois: `backend/config.py` default ajustado para `5`; backend reboot confirmou `GET /api/credits` guest retorna `{"limit": 5, "remaining": 5, "type": "guest", "used": 0}`

Bloqueado por ambiente (nao validado):
- OAuth real, fluxos autenticados, SSE streaming, interacoes de browser (SearchModal, toggle salvo, Ctrl+K), migrations 011/012 aplicadas no banco

### 2026-04-14 - Pos-plano: alinhar contrato de creditos guest (correcao)

Alterado:
- `backend/config.py`: `GUEST_CREDIT_LIMIT = int(os.getenv("GUEST_CREDIT_LIMIT", "5"))` (era "1000")

Nao alterado:
- `USER_CREDIT_LIMIT` permanece 15 (ja correto)
- env override continua disponivel via `GUEST_CREDIT_LIMIT` env var
- frontend/banners/textos ja assumem 5 — sem mudanca necessaria

Validacao executada:
- py_compile config.py: OK
- Config import: GUEST_CREDIT_LIMIT=5, USER_CREDIT_LIMIT=15
- backend reboot localmente (app.py em 5000)
- GET /health: 200 database connected
- GET /api/credits (guest sem session): {"limit":5,"remaining":5,"type":"guest","used":0}
- GET /api/credits?session_id=test123 (guest): {"limit":5,"remaining":5,"type":"guest","used":0}

Divergencia resolvida. Runtime, config default e contrato documentado agora coincidem em 5.

### 2026-04-14 - Pos-plano: Validacao visual/browser NAO executada (bloqueada por ambiente)

Esta aba nao tem tool de browser automation (Playwright/Puppeteer). Ferramentas disponiveis (Bash, curl, Read, Edit) nao validam interacoes client-side.

O que foi reconfirmado nesta aba:
- npm run build: 14 paginas, zero errors
- tsc --noEmit: exit 0 (sequencial apos build)
- codigo estavel desde a correcao do GUEST_CREDIT_LIMIT
- Next.js dev server em Windows continua com instabilidade de compile-on-demand sob multiplos requests concorrentes (nao bug da app)

Gap real: checklist de 6 grupos de interacoes browser registrado acima em "Pos-plano: Validacao visual/browser..."

Status: este pos-plano NAO esta fechado. Precisa de executor humano com browser ou aba com browser tool para rodar o checklist.

### 2026-04-14 - Pos-plano: Roteiro manual de validacao browser preparado

Criado `reports/ROTEIRO_VALIDACAO_BROWSER_SIDEBAR.md` com:
- pre-requisitos (backend + frontend rodando, aba anonima ou storage limpo, guest mode)
- 12 passos enxutos cobrindo:
  - home renderiza shell
  - abrir sidebar expandido (Menu icon)
  - fechar sidebar com overlay
  - abrir SearchModal com Ctrl+K (foco fora de input)
  - fechar com Escape
  - abrir SearchModal por click em Search
  - fechar com overlay
  - guard do atalho dentro do input do chat
  - estado empty + CTA com query `xyz123teste`
  - CTA inicia nova conversa guest com "xyz123teste"
  - `/favoritos`, `/conta`, `/plano` guest states
  - `/data-deletion` guest mostra email fallback, sem botao de exclusao
- template de anotacao de falha (passo, URL, navegador, observado, esperado, reproducibilidade, console, screenshot)
- secao "Fora deste roteiro" listando o que requer OAuth real

Nenhum codigo foi alterado — apenas documento operacional criado.

### 2026-04-14 - Pos-plano: Validacao visual/browser executada (roteiro manual) — CONCLUIDA com 1 finding corrigido

Executor: humano (Murilo), browser real, frontend em `http://localhost:3003` (portas 3000-3002 ocupadas), backend em `http://localhost:5000`, aba anonima (guest, storage limpo).

Passos 1 a 9: todos passaram conforme esperado — shell, sidebar expandido, overlay, Ctrl+K, Escape, click em Search, guard do atalho em input, estado empty + CTA.

Passo 10 (CTA inicia nova conversa guest) — passou parcialmente inicialmente:
- Baco respondeu em streaming corretamente apos CORS fix descrito abaixo.
- **Finding real:** contador de creditos `5/5 → 4/5` NAO renderizava no header para guest. Esperado pelo roteiro: contador visivel.

Passos 11 e 12: todos passaram conforme esperado (`/favoritos`, `/conta`, `/plano`, `/data-deletion` com comportamento guest correto; botao "Entrar" fixo no topo direito em todas as telas, com lista de providers OAuth abaixo do CTA).

Correcoes aplicadas nesta aba durante a execucao:
1. `backend/app.py`: CORS restrito a `localhost:3000` quebrava quando frontend subia em outra porta (3001/3002/3003). Trocado para regex `http://localhost:\d+` em dev. Causa raiz do `Failed to fetch` observado no passo 10.
2. `frontend/components/AppShell.tsx`: bloco `{user ? <UserMenu /> : <LoginButton />}` nao renderizava o contador de creditos para guest. Adicionado span `{remaining}/{limit}` antes do `<LoginButton compact />` quando `user === null && creditsLimit > 0`. O refresh apos mensagem ja existia em `page.tsx:363` (`refreshCredits()` no `onDone`) — bug era so de renderizacao.

Reconfirmacao apos fix: usuario reexecutou passo 10 em aba anonima — header mostra `5/5` na carga, e vira `4/5` apos Baco concluir o streaming. Contador correto.

Arquivos alterados:
- `backend/app.py` (CORS regex dev)
- `frontend/components/AppShell.tsx` (contador guest no header)

Validacao pendente antes do fechamento formal:
- `npm run build` + `npx tsc --noEmit` no `frontend/` para confirmar que o edit no `AppShell.tsx` nao quebra build/types (executor humano vai rodar)
- reconfirmar que `backend/app.py` com regex CORS continua booted e saudavel (ja rodando em background na sessao; basta verificar `/health` 200 apos hot-reload do watchdog)

Status operacional: 12/12 passos do roteiro visual/browser passaram apos as duas correcoes acima. Se build+tsc forem verdes, a validacao visual/browser do sidebar pode ser marcada como CONCLUIDA e o rollout 0A-4C + pos-plano fica formalmente encerrado no workspace atual.

Trilho separado que continua fora deste gate (requer OAuth real em ambiente configurado):
- login real via Google/Facebook/Apple/Microsoft
- historico autenticado listado no sidebar
- toggle salvar conversa (Heart no header)
- `/favoritos` com lista populada
- exclusao de conta real
- migracao guest -> logado

Proximo executor (humano ou agente com browser tool) pode abrir direto o roteiro e marcar os passos. Este pos-plano continua NAO fechado ate o checklist ser rodado.

### 2026-04-14 - Pos-plano: Fechamento formal do rollout do sidebar no workspace atual

Reconfirmacao final executada apos a validacao humana:
- `npm run build` em `frontend/`: OK
- `npx tsc --noEmit` em `frontend/`, de forma sequencial apos o build: OK
- `GET /health` no backend local: 200, database connected
- frontend dev restartado com `.next` limpo para remover artefatos corrompidos do Next em modo dev; issue de cache local resolvida

Hardening adicional aplicado apos a validacao humana:
- `frontend/components/WelcomeScreen.tsx`: corrigido hydration mismatch na saudacao inicial
- causa raiz: saudacao era escolhida no primeiro render com `new Date()` + `Math.random()`, gerando HTML diferente entre server e client
- correcao: fallback inicial estavel no SSR e promocao para saudacao dinamica somente apos mount no client
- `npm run build` e `npx tsc --noEmit` seguiram verdes apos este ajuste

Status final deste track:
- validacao visual/browser do sidebar: FECHADA
- rollout `0A` a `4C`: FECHADO
- pos-plano de toggle salvo no chat: FECHADO
- validacao runtime local sem browser: FECHADA
- rollout completo do sidebar + legal + busca fica FORMALMENTE ENCERRADO no workspace atual

Trilhos que permanecem fora deste fechamento e exigem ambiente com OAuth real:
- login real via Google/Facebook/Apple/Microsoft
- historico autenticado no sidebar em sessao real
- toggle salvar conversa em sessao autenticada real
- `/favoritos` com lista populada por conta real
- exclusao de conta real
- migracao guest -> logado ponta a ponta

### 2026-04-15 - QA autenticado real em producao: CONCLUIDO

Ambiente: producao (https://chat.winegod.ai), executor humano com browser real, login Google real.

Fluxos validados de ponta a ponta:

1. Historico autenticado no sidebar
   - login Google OK
   - historico carrega no sidebar expandido
   - clicar em conversa reabre no chat correto
   - regressao visual inicial (flash da WelcomeScreen durante fetch) foi corrigida em tres patches sequenciais (spinner -> useLayoutEffect -> mounted gate)

2. URL permanente por conversa
   - redesign aplicado: criada rota `/chat/[id]` (cliente) como fonte de verdade da conversa
   - `app/chat/[id]/page.tsx` e wrapper de `components/ChatHome.tsx` (toda a logica do Home foi extraida para esse componente parametrizado por `initialConversationId`)
   - `app/page.tsx` virou wrapper trivial
   - sidebar, `/favoritos` e `SearchModal` passam a navegar direto para `/chat/<id>`
   - legacy `/?conv=<id>` continua funcionando com redirect automatico
   - promocao de conversa (primeira resposta logada, migracao guest->logado) faz `router.replace(`/chat/<id>`)` para atualizar a URL sem reload
   - refresh em `/chat/<id>` restaura a conversa via backend
   - compartilhar o link com quem esta logado abre a conversa

3. Dessalvar em `/favoritos`
   - adicionado `<Heart>` vermelho inline a direita de cada linha
   - click remove otimisticamente (UX imediato) + toast "Removida dos favoritos" por ~2.2s
   - rollback + toast vermelho em caso de falha no backend
   - botao desativado durante request para impedir double-click

4. Links do sidebar pos-deploy
   - `/favoritos`, `/conta`, `/plano`, `/ajuda` navegam sem regressao
   - click em area vazia do collapsed strip agora abre o sidebar expandido (fix de usabilidade)
   - `+` (novo chat) e logo do header fazem `window.location.assign("/")` quando saindo de `/chat/<id>` para eliminar cache do Next/React que estava ressuscitando a conversa antiga

5. `SearchModal` autenticado
   - Ctrl+K abre, Esc fecha, overlay fecha
   - busca retorna secoes `Salvos` + `Conversas`, click abre `/chat/<id>`
   - CTA `Perguntar ao Baco` continua abrindo novo chat com a pergunta

6. Exclusao de conta real
   - `/data-deletion` logado mostra `DeleteAccountSection` com confirmacao em 2 etapas
   - exclusao no backend cascateia: user row, conversations, message_log anonimizado
   - frontend limpa `winegod_token`, `winegod_session_id`, `winegod_conversation_id`, `winegod_messages` e volta a guest limpo
   - portugues das strings da exclusao e do `/favoritos` corrigido (acentuacao)

7. Migracao guest -> logado
   - aba anonima: guest conversa -> login Google -> conversa migrou para o backend
   - aparece no historico autenticado do sidebar imediatamente
   - URL promovida para `/chat/<id>` automaticamente

Commits desta sessao:
- `1e91364b` Suppress WelcomeScreen flash when opening saved conversation
- `b404bd25` Use useLayoutEffect to set opening flag before paint
- `ca831dc2` Gate home body on mounted to fully eliminate WelcomeScreen flash
- `2b1ab40c` Add /chat/<id> route so each conversation has a stable URL
- `5ec292ee` Add inline unsave action on /favoritos with optimistic remove
- `8916a5a2` Clear conversation storage synchronously on new chat and logout
- `4f483abc` Make blank areas of the collapsed strip open the expanded sidebar
- `ecd6e5e5` Force a hard reload when leaving /chat/<id> for new chat or logo
- `8897426d` Restore missing Portuguese accents in delete-account and favoritos copy

Validacao tecnica em cada commit:
- `npm run build` em `frontend/`: OK
- `npx tsc --noEmit` em `frontend/`, sequencial apos build: OK
- Vercel redeployou cada commit em producao antes do QA humano do item seguinte

Arquivos alterados nesta sessao:
- `frontend/app/page.tsx` (vira wrapper trivial de `ChatHome`)
- `frontend/app/chat/[id]/page.tsx` (novo, wrapper de `ChatHome` com prop)
- `frontend/components/ChatHome.tsx` (novo, toda a logica do Home)
- `frontend/components/Sidebar.tsx` (navegacao para `/chat/<id>` + areas vazias clicaveis)
- `frontend/components/AppShell.tsx` (SearchModal navega para `/chat/<id>`, logo com `preventDefault`)
- `frontend/app/favoritos/FavoritosContent.tsx` (Heart inline, optimistic unsave, toast, navegacao `/chat/<id>`, acentos)
- `frontend/app/data-deletion/DeleteAccountSection.tsx` (acentos pt-BR)

Status final do track:
- rollout `0A` a `4C`: FECHADO
- pos-plano de toggle salvo no chat: FECHADO
- validacao runtime local sem browser: FECHADA
- validacao visual/browser guest: FECHADA
- QA autenticado real em producao: FECHADO
- URL permanente por conversa (`/chat/<id>`): IMPLEMENTADA
- `/favoritos` com unsave inline: IMPLEMENTADO
- portugues corrigido nas paginas tocadas neste trilho: CONCLUIDO

Riscos residuais explicitos (fora deste trilho):
- internacionalizacao (i18n) real nao existe ainda — todo texto da UI esta hardcoded em pt-BR; R5 (global dia 1) nao esta atendido na interface mesmo com o system prompt do Baco respondendo em qualquer idioma
- testes automatizados de cobertura de strings multilingue inexistentes
- tradutor humano nativo por idioma ainda nao contratado
