# Plano Final de Implementacao do Sidebar WineGod.ai

## Contexto

- O sidebar atual tem 7 entradas visiveis: `Novo chat`, `Buscar`, `Favoritos`, `Minha conta`, `Plano & creditos`, `Historico`, `Ajuda`.
- Hoje, na pratica, so `Novo chat` funciona de forma real.
- O escopo desta entrega e:
- `4 rotas` do produto: `/ajuda`, `/conta`, `/plano`, `/favoritos`
- `1 busca global`: `Buscar`
- `1 feature de sidebar`: `Historico`
- `3 rotas legais obrigatorias`: `/privacy`, `/terms`, `/data-deletion`
- As URLs legais ja foram cadastradas nos portais OAuth do Facebook e da Microsoft e nao podem continuar quebradas.
- O produto e chat-first. Busca nova de vinho deve levar o usuario para o chat, nao para um catalogo paralelo dentro do modal.
- `Favoritos` da v1 nao serao vinhos individuais. Na v1, favoritos = conversas salvas.

## Principios

- Corrigir `auth` e `creditos` antes de construir paginas que dependem de login.
- Reaproveitar a busca existente em `backend/tools/search.py`; nao criar nova stack de search de vinhos para a v1.
- Nao esconder paginas legais dentro de `Ajuda`; `privacy`, `terms` e `data-deletion` precisam existir como rotas publicas estaveis.
- Evitar duplicacao de layout; usar um shell compartilhado para chat e paginas do sidebar.
- Nao confiar so em `localStorage` para auth guard; validade real do login vem de `/api/auth/me`.
- Usar IDs compativeis com o `session_id` atual do chat.
- Persistir apenas dados de conversa que facam sentido para o usuario final; nunca salvar base64, blobs grandes ou prompts internos de OCR/PDF como historico visivel.
- Toda tela que busca dados assincronos deve ter `loading state`, `empty state` e fallback de erro.
- Para recursos novos do sidebar, adotar migrations SQL versionadas em `database/migrations` e rollbacks em `database/rollback`.
- Nao assumir `WineCard` ou favoritos de vinho antes de existir uma UI estruturada real para isso.

## Sequencia Recomendada

1. Fase 0 - Fundacao de Auth e Creditos
2. Fase 0.5 - Paginas Legais Publicas
3. Fase 1 - Shell + Paginas Simples
4. Fase 2 - Historico
5. Fase 3 - Favoritos + Exclusao de Conta
6. Fase 4 - Buscar

## Plano de Conducao da Execucao

- A execucao deve ser feita em modo controlado, com escopo fechado por rodada.
- Nao executar uma fase inteira de uma vez quando ela mexer em auth, chat, creditos, historico ou estruturas centrais.
- Cada subfase deve terminar com validacao local e revisao antes de seguir.
- Sem refactors paralelos, sem melhorias oportunistas e sem pular etapa.

### Fase 0 em subfases

- `Fase 0A` - auth no chat + limites reais + payload de `/api/auth/me`
- Entrega:
- enviar Bearer token no chat quando logado
- trocar placeholders de creditos por limites reais da v1
- retornar `provider` e `last_login`
- criar `get_current_user(request)`
- ajustar frontend para parar de depender de hardcodes errados
- `Fase 0B` - endurecimento e validacao de creditos na UI
- Entrega:
- garantir que logout, refresh e erro `429` reflitam o estado real
- revisar banners, contadores e estados de usuario/guest
- fechar qualquer inconsistência residual de contrato entre frontend e backend

### Fase 0.5 em subfases

- `Fase 0.5A` - shell legal reutilizavel
- Entrega:
- criar `LegalPage.tsx`
- definir estrutura visual e metadados basicos
- `Fase 0.5B` - paginas publicas
- Entrega:
- publicar `/privacy`
- publicar `/terms`
- publicar `/data-deletion`
- validar slugs exatos ja cadastrados nos provedores OAuth

### Fase 1 em subfases

- `Fase 1A` - navegacao e shell
- Entrega:
- criar `AppShell`
- ligar `Sidebar` a rotas reais
- criar `not-found.tsx`
- `Fase 1B` - pagina `Ajuda`
- Entrega:
- FAQ
- glossario
- contato
- versao
- `Fase 1C` - paginas `Conta` e `Plano`
- Entrega:
- guards de auth
- loading/empty/error states
- dados reais de conta e creditos

### Fase 2 em subfases

- `Fase 2A` - backend de conversations
- Entrega:
- migration `conversations`
- models
- routes
- ownership basico
- `Fase 2B` - ponte `session_id -> conversation`
- Entrega:
- criar conversa ao iniciar sessao autenticada nova
- atualizar conversa ao fim da resposta SSE
- manter sessao em memoria como cache quente
- `Fase 2C` - frontend de historico
- Entrega:
- `conversationId`
- abrir conversa antiga
- lista real no sidebar
- loading/empty states
- `Fase 2D` - migracao guest -> logado
- Entrega:
- ao fazer login, migrar conversa ativa local para o backend
- limpar storage local so apos sucesso

### Fase 3 em subfases

- `Fase 3A` - salvar conversas
- Entrega:
- `is_saved`
- `saved_at`
- endpoints de marcar/desmarcar salvo
- `Fase 3B` - pagina `/favoritos`
- Entrega:
- lista de conversas salvas
- ordenacao por `saved_at`
- loading/empty states
- `Fase 3C` - exclusao de conta
- Entrega:
- `DELETE /api/auth/me`
- validacao do cascade
- alinhar `/conta` e `/data-deletion` ao fluxo real

### Fase 4 em subfases

- `Fase 4A` - modal e atalhos
- Entrega:
- `SearchModal`
- abrir por click e `Ctrl+K`
- fechar com `Escape`
- nao disparar dentro de `input` e `textarea`
- `Fase 4B` - busca de conversas e salvos
- Entrega:
- listar resultados de conversas
- listar resultados de salvos
- reabrir conversa ao clicar
- `Fase 4C` - CTA para nova pergunta no chat
- Entrega:
- `Perguntar ao Baco sobre "<texto>"`
- jogar busca nova para o chat
- manter command palette simples, sem catalogo de vinhos e sem buscas recentes na v1

## Fase 0 - Fundacao de Auth e Creditos

### Objetivo

- Fechar as inconsistencias que hoje quebram `Conta`, `Plano`, `Historico` e qualquer fluxo confiavel de usuario logado.

### Arquivos modificados

- `frontend/lib/api.ts`
- `frontend/lib/auth.ts`
- `frontend/app/page.tsx`
- `backend/routes/auth.py`
- `backend/routes/credits.py`
- `backend/db/models_auth.py`

### Mudancas

- Fazer o frontend enviar `Authorization: Bearer <token>` em `/api/chat` e `/api/chat/stream` quando houver login.
- Unificar limites de creditos em uma fonte unica no backend. O frontend nao deve mais hardcodear `5` ou `15`.
- Definir limites reais da v1 em vez de placeholders `9999`.
- Recomendacao de partida:
- Guest: `5` mensagens por sessao
- Free logado: `15` mensagens por dia
- Pro: fora de escopo, apenas placeholder visual
- Expandir `GET /api/auth/me` para retornar `provider` e `last_login`.
- Criar helper backend `get_current_user(request)` reutilizavel para todos os endpoints autenticados.
- Ajustar a home para consumir o limite real devolvido pela API.
- Ajustar o frontend para ler o `reason` real de erro de creditos quando o backend responder `429`, em vez de adivinhar so pelo estado local.
- Garantir que login, logout e refresh da pagina mantenham `user`, `creditsUsed` e `creditsLimit` coerentes.
- Nao implementar `DELETE /api/auth/me` nesta fase. Ate a Fase 3, `/data-deletion` deve apontar para fluxo manual real.

### Endpoints

- `GET /api/auth/me` - manter, mas expandir payload
- `GET /api/credits` - manter, mas alinhar contrato com os limites reais

### Migracoes

- Nenhuma

### Criterio de pronto

- Usuario logado consome o chat como usuario autenticado.
- `Conta` e `Plano` podem confiar nos dados da API.
- Os limites exibidos na UI batem com o backend.
- A API de auth retorna `provider` e `last_login`.
- Os limites da v1 deixaram de ser placeholders absurdos.
- `/data-deletion` ainda pode descrever fluxo manual, mas de forma explicita e honesta.

## Fase 0.5 - Paginas Legais Publicas

### Objetivo

- Publicar as rotas obrigatorias de compliance ja cadastradas em provedores OAuth e eliminar links quebrados em producao.

### Arquivos novos

- `frontend/app/privacy/page.tsx`
- `frontend/app/terms/page.tsx`
- `frontend/app/data-deletion/page.tsx`
- `frontend/components/LegalPage.tsx`

### Mudancas

- Criar `GET /privacy` como pagina publica e estavel de politica de privacidade.
- Criar `GET /terms` como pagina publica e estavel de termos de uso.
- Criar `GET /data-deletion` como pagina publica e estavel com instrucoes de exclusao de dados.
- Manter os slugs exatamente como ja cadastrados:
- `https://chat.winegod.ai/privacy`
- `https://chat.winegod.ai/terms`
- `https://chat.winegod.ai/data-deletion`
- Reaproveitar `LegalPage.tsx` como shell visual simples para nao duplicar estrutura.
- Ate a Fase 3, a pagina `/data-deletion` deve explicar o fluxo manual real, sem prometer automacao inexistente.

### Endpoints

- Nenhum endpoint backend novo obrigatorio nesta fase

### Migracoes

- Nenhuma

### Criterio de pronto

- As 3 URLs publicas respondem com pagina real em producao.
- O conteudo e claro, publico e estavel.
- O conteudo nao promete exclusao automatica antes da Fase 3.
- Facebook e Microsoft deixam de apontar para rotas inexistentes.

## Fase 1 - Shell + Paginas Simples

### Objetivo

- Transformar o sidebar em navegacao real e entregar as paginas basicas do produto sem backend novo pesado.

### Arquivos novos

- `frontend/components/AppShell.tsx`
- `frontend/lib/useAuth.ts`
- `frontend/app/ajuda/page.tsx`
- `frontend/app/conta/page.tsx`
- `frontend/app/plano/page.tsx`
- `frontend/app/not-found.tsx`

### Arquivos modificados

- `frontend/components/Sidebar.tsx`
- `frontend/components/auth/UserMenu.tsx`
- `frontend/app/page.tsx`

### Mudancas

- Criar `AppShell` para compartilhar header, sidebar e area principal entre `/`, `/ajuda`, `/conta`, `/plano` e depois `/favoritos`.
- Se o App Router pedir outra estrutura, o principio e o mesmo: layout compartilhado, nao duplicacao manual.
- Transformar `Sidebar.tsx` em componente de navegacao real:
- `Novo chat` continua limpando o chat
- `Buscar` passa a abrir modal
- `Favoritos`, `Minha conta`, `Plano & creditos` e `Ajuda` passam a navegar
- Criar `useAuth()` para guard de paginas protegidas, usando `auth.ts` e validacao via `/api/auth/me`, nao so leitura cega de `localStorage`.
- Implementar `/ajuda` com:
- FAQ em aproximadamente 6 secoes
- como usar o chat
- foto, OCR e PDF
- notas e score
- creditos
- compartilhamento
- conta e login
- glossario com cerca de 15 a 20 termos
- contato
- versao do produto
- Implementar `/conta` com:
- perfil
- provider OAuth
- ultimo login
- logout
- link para `/data-deletion` enquanto a exclusao automatica nao existir
- Implementar `/plano` com:
- creditos reais da API
- barra de progresso
- estado atual do plano
- bloco `Em breve: Pro` com CTA honesto, sem billing real
- Adicionar `loading state` e `empty state` nas paginas de `Conta` e `Plano`.
- Criar `frontend/app/not-found.tsx` com visual do produto e link de volta para o chat.

### Endpoints

- Reaproveitar apenas os endpoints da Fase 0

### Migracoes

- Nenhuma

### Criterio de pronto

- Todos os itens navegaveis do sidebar abrem algum destino real.
- Paginas protegidas mostram guard de login coerente.
- Nao existe duplicacao grosseira de layout entre chat e paginas.
- `Ajuda`, `Conta` e `Plano` deixam de ser placeholder mental e passam a ter conteudo concreto.
- URLs invalidas deixam de cair na 404 padrao do Next.

## Fase 2 - Historico

### Objetivo

- Substituir o placeholder do sidebar por conversas reais persistidas para usuarios logados.

### Arquivos novos

- `frontend/lib/conversations.ts`
- `backend/routes/conversations.py`
- `backend/db/models_conversations.py`
- `database/migrations/010_add_conversations.sql`
- `database/rollback/010_rollback.sql`

### Arquivos modificados

- `frontend/app/page.tsx`
- `frontend/components/Sidebar.tsx`
- `frontend/lib/api.ts`
- `backend/app.py`
- `backend/routes/chat.py`

### Mudancas

- Criar tabela `conversations`.
- Usar `id` compativel com o `session_id` atual do chat. Recomendacao: `VARCHAR(36)` ou `UUID`.
- Introduzir no frontend o estado de `conversationId`, separado do estado visual de mensagens.
- Expandir o helper de sessao no frontend para suportar:
- `getSessionId()`
- `setSessionId()`
- `resetSessionId()`
- Definir explicitamente a ponte `sessao -> conversa`:
- no primeiro `POST /api/chat/stream` de um `session_id` novo e autenticado, criar a conversa
- a cada resposta SSE completa, atualizar a conversa persistida no banco
- `sessions` em memoria continuam como cache quente, mas a fonte de verdade passa a ser o banco
- Persistir apenas mensagens sanitizadas e visiveis para o usuario.
- Nao salvar base64, blobs de imagem, prompts internos de OCR/PDF nem contexto tecnico oculto do backend.
- Auto-save apenas no fim da resposta SSE, nao a cada chunk.
- Gerar `title` a partir do primeiro texto real do usuario, truncado.
- Se a primeira interacao for so midia, usar como fallback o primeiro texto util da resposta do Baco para compor o titulo.
- Nao adicionar campo `preview` na v1. Para sidebar e favoritos, `title` resolve.
- Na v1, `q` em conversas busca apenas em `title`, nao dentro de todas as mensagens.
- Sidebar passa a renderizar lista real de conversas com clique para reabrir.
- Abrir conversa antiga deve restaurar o `session_id` correto e continuar no mesmo fio.
- Guest continua com historico local.
- Ao fazer login, se existir conversa ativa no `localStorage` com o `session_id` atual, migrar essa conversa para o backend e limpar o storage local apenas apos sucesso.
- Adicionar `loading state` e `empty state` para a lista de historico.

### Endpoints

- `GET /api/conversations`
- `GET /api/conversations?q=<texto>` - busca por `title` na v1
- `GET /api/conversations/<id>`
- `POST /api/conversations`
- `PUT /api/conversations/<id>`
- `DELETE /api/conversations/<id>`

### Migracoes

- `010_add_conversations.sql`
- `010_rollback.sql`

### SQL proposto

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255),
    messages JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user
ON conversations(user_id, updated_at DESC);
```

### Criterio de pronto

- Conversas de usuarios logados reaparecem no sidebar apos refresh.
- Abrir conversa antiga reaproveita o mesmo `session_id` e nao quebra o contexto do chat.
- Usuario A nao consegue abrir ou deletar conversa do usuario B.
- O historico salvo nao fica poluido com payload interno de OCR/PDF.
- O guest nao perde a conversa ativa ao fazer login.

## Fase 3 - Favoritos + Exclusao de Conta

### Objetivo

- Permitir salvar conversas importantes e, com o schema de conversas ja estabelecido, fechar o fluxo de exclusao de conta.

### Arquivos novos

- `frontend/app/favoritos/page.tsx`
- `frontend/lib/favorites.ts`
- `database/migrations/011_add_conversation_saved_flag.sql`
- `database/rollback/011_rollback.sql`

### Arquivos modificados

- `frontend/components/Sidebar.tsx`
- `frontend/app/page.tsx`
- `backend/routes/conversations.py`
- `backend/db/models_conversations.py`
- `backend/routes/auth.py`
- `backend/db/models_auth.py`

### Mudancas

- Definir `Favoritos` da v1 como `conversas salvas`.
- Nao implementar favoritos de vinho enquanto nao existir uma representacao visual real e consistente de vinho fora do texto livre do chat.
- Adicionar flag de salvo na conversa (`is_saved`) e timestamp (`saved_at`).
- Permitir salvar e remover conversa salva sem recarregar a pagina.
- Exibir `/favoritos` como lista de conversas salvas, com `title` e ultima atualizacao.
- `frontend/lib/favorites.ts` pode ser um wrapper fino por cima da API de `conversations`, sem criar uma stack paralela de dominio.
- Reaproveitar os endpoints de conversas em vez de criar backend separado so para favoritos.
- Implementar agora `DELETE /api/auth/me`, depois que `conversations` ja existir.
- Garantir que exclusao de conta remova conversas do usuario por cascade e mantenha o comportamento esperado de tabelas legadas como `message_log`.
- Atualizar `/conta` para expor o fluxo real de exclusao automatica quando esse endpoint existir.
- Adicionar `loading state` e `empty state` para `/favoritos`.

### Endpoints

- `GET /api/conversations?saved=true`
- `PUT /api/conversations/<id>/saved` com body `{"saved": true}`
- `PUT /api/conversations/<id>/saved` com body `{"saved": false}`
- `DELETE /api/auth/me`

### Migracoes

- `011_add_conversation_saved_flag.sql`
- `011_rollback.sql`

### SQL proposto

```sql
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS is_saved BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS saved_at TIMESTAMP NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_saved
ON conversations(user_id, is_saved, saved_at DESC NULLS LAST, updated_at DESC);
```

### Criterio de pronto

- Usuario autenticado consegue salvar e remover conversa salva sem recarregar a pagina.
- `/favoritos` lista as mesmas conversas marcadas no sidebar ou na tela do chat.
- A ordenacao de favoritos prioriza `saved_at` e nao some apos refresh.
- Exclusao de conta deixa de ser fluxo manual e passa a existir de verdade.
- Depois da exclusao, o usuario perde acesso aos seus dados e o frontend remove o token local.

## Fase 4 - Buscar

### Objetivo

- Entregar `Buscar` como command palette global do produto: encontrar conversas e conversas salvas, e mandar busca nova para o chat.

### Arquivos novos

- `frontend/components/SearchModal.tsx`

### Arquivos modificados

- `frontend/app/page.tsx`
- `frontend/components/Sidebar.tsx`
- `frontend/lib/conversations.ts`

### Mudancas

- Implementar `SearchModal` como command palette com:
- autofocus no input
- `Ctrl+K` para abrir
- `Escape` para fechar
- debounce
- loading state
- empty state
- secoes de resultado para `Conversas` e `Salvos`
- O atalho `Ctrl+K` nao deve disparar quando o foco estiver em `input`, `textarea` ou area editavel do chat.
- Ao clicar em uma conversa, reabrir a conversa.
- Ao clicar em um item salvo, abrir a conversa salva.
- Ao enviar um texto livre que nao seja uma conversa existente, oferecer CTA no formato `Perguntar ao Baco sobre "<texto>"` e abrir ou continuar o chat com essa pergunta.
- Reaproveitar `q` nas conversas gerais e, para salvos, usar a lista de `saved=true` da Fase 3 com filtro simples no client na v1.
- Nao criar, na v1, um catalogo paralelo de vinhos em grid dentro do modal.
- Nao implementar `Buscas recentes` na v1.
- Busca nova de vinho vai para o chat.

### Endpoints

- Reaproveitar `GET /api/conversations`
- Reaproveitar `GET /api/conversations?q=<texto>`
- Reaproveitar `GET /api/conversations?saved=true`

### Migracoes

- Nenhuma

### Criterio de pronto

- `Buscar` funciona tanto pelo sidebar quanto por `Ctrl+K`.
- O modal encontra conversas antigas e conversas salvas.
- Procurar um vinho novo pelo modal leva o usuario de volta ao fluxo principal do produto: o chat.
- O atalho nao atrapalha a digitacao normal no chat.

## Fora de Escopo da v1

- Plano Pro com billing real
- Favoritar vinhos individuais
- Favoritar respostas individuais do chat
- Catalogo de vinhos em grid
- Historico persistente para guest no backend
- Busca semantica separada
- Favoritos em massa, tags ou colecoes
- Busca textual dentro de todas as mensagens da conversa
- Campo `preview` persistido em banco
- `GET /api/conversations?saved=true&q=<texto>`
- `Buscas recentes` no command palette

## Verificacao por Fase

- `npm run build` em `frontend` com zero erros
- smoke test manual das rotas e navegacao do sidebar
- smoke test manual das rotas publicas `/privacy`, `/terms` e `/data-deletion`
- teste HTTP dos endpoints novos
- validacao das migrations em ambiente controlado antes do Render
- teste manual de login, logout e refresh
- teste manual de exclusao de conta e coerencia com `/data-deletion`
- teste manual de abrir conversa antiga e continuar no mesmo `session_id`
- teste manual de migracao de conversa ativa do guest para usuario logado
- teste manual de salvar e remover conversa salva
- teste manual de `Ctrl+K` fora e dentro do campo de input
- verificacao visual de loading, empty e error states nas telas novas

## Observacoes de Risco

- Nao implementar `Conta`, `Plano` ou `Historico` antes de fechar auth e creditos.
- Nao depender de `/ajuda` para cumprir exigencias de OAuth; `privacy`, `terms` e `data-deletion` precisam ser paginas dedicadas.
- Nao usar IDs curtos para `Historico`; o chat atual ja usa UUID.
- Nao prometer limites de plano, billing ou retencao que o backend ainda nao aplica.
- Nao modelar favoritos como vinho enquanto o produto ainda nao exibe vinho como objeto visual consistente e acionavel.
- Nao transformar `Buscar` em catalogo paralelo; busca nova de vinho deve continuar no chat.
- Nao persistir no historico o texto tecnico enriquecido internamente pelo backend para OCR/PDF; salvar so a versao util ao usuario.
- O projeto ja tem legado de criacao imperativa de schema no backend; para as features novas do sidebar, a regra deve ser migration versionada e rollback correspondente.
- Na v1, a busca de conversas por `q` deve ficar simples e restrita a `title`; se isso ficar insuficiente depois, avaliar `search_text` ou normalizacao em tabela separada.
