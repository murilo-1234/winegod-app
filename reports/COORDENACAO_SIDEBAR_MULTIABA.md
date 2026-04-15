# Coordenacao Multiaba - Sidebar Rollout

Este documento registra a coordenacao por prompts entre abas, separado do handoff principal de implementacao.

## Documentos herdados do prompt original

Estes documentos ja vieram como fonte de verdade do trabalho:
- `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
- `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`

Uso recomendado:
- `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`: fonte de verdade do estado tecnico por fase/subfase
- `PLANO_IMPLEMENTACAO_SIDEBAR.md`: plano mestre e ordem de dependencia
- `COORDENACAO_SIDEBAR_MULTIABA.md` (este arquivo): historico operacional da coordenacao, prompts emitidos para outra aba e estado atual da revisao

## Regra operacional de persistencia

Regra definida nesta conversa:
- salvar a coordenacao a cada 3 prompts desenvolvidos para colar no Claude Code
- checkpoints automaticos esperados nos prompts `#3`, `#6`, `#9`, `#12`, ...
- checkpoint extraordinario pode ser salvo antes disso se o usuario pedir ou se houver risco de perder contexto

Contador atual:
- prompts emitidos ate agora: `26`
- proximo checkpoint automatico obrigatorio: apos o prompt `#24`

## Linha do tempo desta coordenacao

### Prompt #1 - Execucao inicial da Fase 2B

Objetivo:
- implementar somente a `Fase 2B - ponte session_id -> conversation`

Parecer recebido:
- outra aba reportou a 2B como concluida

Revisao feita nesta aba:
- nao aprovado
- encontrado bug de ownership em race condition no fallback de `DuplicateConversationError`
- handoff tambem estava inconsistente com o contrato real da fase

Resultado:
- emitido prompt corretivo (#2)

### Prompt #2 - Correcao da Fase 2B

Objetivo:
- corrigir ownership em race condition
- alinhar criacao de shell ao contrato da 2B
- corrigir o handoff

Parecer recebido:
- outra aba reportou 2B corrigida

Revisao feita nesta aba:
- aprovado
- ownership protegido em `_persist_conversation()`
- shell criada no inicio e removida se a resposta falhar
- handoff passou a apontar corretamente para a `Fase 2C`

Resultado:
- emitido prompt de execucao da `Fase 2C` (#3)

### Prompt #3 - Execucao inicial da Fase 2C

Objetivo:
- implementar somente a `Fase 2C - frontend de historico`

Parecer recebido:
- outra aba reportou a 2C como concluida

Revisao feita nesta aba:
- nao aprovado
- encontrados problemas reais:
  - regressao de guest: `Novo chat` estava resetando `session_id` para guest
  - storage de mensagens ainda misturava contextos de conversas diferentes
  - estado de erro do historico nao funcionava de verdade
  - validacao `npx tsc --noEmit` reportada nao era confiavel

Resultado:
- emitido prompt corretivo (#4)

### Prompt #4 - Correcao da Fase 2C

Objetivo:
- corrigir os problemas bloqueantes da 2C detectados na revisao do prompt #3

Parecer recebido:
- outra aba reportou 2C corrigida

Revisao feita nesta aba:
- ainda nao aprovado
- problemas remanescentes identificados:
  - risco de marcar conversa ativa backend-managed usando apenas `checkLoggedIn()` em `onDone`, o que pode quebrar o fallback user -> guest quando o token expira no meio da sessao
  - validacao `npx tsc --noEmit` continua NAO reproduzindo sucesso nesta aba

Resultado:
- emitido prompt corretivo (#5)

### Prompt #5 - Correcao adicional da Fase 2C

Objetivo:
- fechar regressao residual no fallback user -> guest e alinhar a validacao reportada com o resultado real

Parecer consolidado nesta aba:
- aprovado no workspace atual
- o codigo ja contem a correcao residual pedida no `onDone`
- `npm run build` passou
- `npx tsc --noEmit` tambem passou quando executado apos o build

Observacao relevante:
- a divergencia anterior de validacao veio do timing: `tsc` pode falhar se rodar antes de o Next gerar `.next/types`

Resultado:
- `Fase 2C` considerada fechada
- emitido prompt de execucao da `Fase 2D` (#6)

### Prompt #6 - Execucao da Fase 2D

Objetivo:
- implementar somente a `Fase 2D - migracao guest -> logado`

Parecer recebido:
- outra aba reportou a 2D como concluida

Revisao feita nesta aba:
- nao aprovado
- problemas reais identificados:
  - a migracao pode persistir no backend um draft antigo de `localStorage`, que nao pertence ao guest atual
  - a UI pode mostrar um draft e a migracao persistir outro, porque `loadMessages()` preferia `localStorage` e a migracao preferia `sessionStorage`

Resultado:
- emitido prompt corretivo (#7)

### Prompt #7 - Correcao da Fase 2D

Objetivo:
- corrigir a origem do draft da migracao guest -> logado e alinhar a leitura do storage ao que a UI realmente mostra

Parecer consolidado nesta aba:
- aprovado no workspace atual
- `loadMessages()` passou a ler somente de `sessionStorage`
- a migracao passou a ler somente de `sessionStorage`
- o persist effect passou a escrever somente em `sessionStorage`
- `handleLogout()` passou a limpar `messages`, `conversationId` e `MESSAGES_KEY`
- `npm run build` passou
- `npx tsc --noEmit` passou quando executado apos o build

Resultado:
- `Fase 2D` considerada fechada
- emitido prompt de execucao da `Fase 3A` (#8)

### Prompt #8 - Execucao da Fase 3A

Objetivo:
- implementar somente a `Fase 3A - salvar conversas`

Parecer consolidado nesta aba:
- aprovado no workspace atual
- migration `012_add_conversation_saved.sql` e rollback correspondentes presentes
- model layer inclui `is_saved` e `saved_at` sem quebrar o contrato anterior
- endpoint `PUT /api/conversations/<id>/saved` registrado com auth e ownership
- validacao backend local passou

Resultado:
- `Fase 3A` considerada fechada
- emitido prompt de execucao da `Fase 3B` (#9)

### Prompt #9 - Execucao da Fase 3B

Objetivo:
- implementar somente a `Fase 3B - pagina /favoritos`

Parecer recebido:
- outra aba reportou a `3B` como concluida

Revisao feita nesta aba:
- nao aprovado
- problema real identificado:
  - `frontend/app/favoritos/FavoritosContent.tsx` ignorava `useAuth().error`, entao falha de `/api/auth/me` para usuario com token presente aparecia como guest CTA em vez de error state real

Resultado:
- emitido prompt corretivo (#10)

### Prompt #10 - Correcao da Fase 3B

Objetivo:
- corrigir o tratamento de erro de auth em `/favoritos` sem quebrar os estados bons ja entregues

Parecer consolidado nesta aba:
- aprovado no workspace atual
- `FavoritosContent` agora trata `useAuth().error` explicitamente
- `/favoritos` ficou com 6 estados em prioridade: loading, auth error, fetch error, guest, empty, lista
- `npm run build` passou
- `npx tsc --noEmit` passou quando executado apos o build

Resultado:
- `Fase 3B` considerada fechada
- emitido prompt de execucao da `Fase 3C` (#11)

### Prompt #11 - Execucao da Fase 3C

Objetivo:
- implementar somente a `Fase 3C - exclusao de conta`

Parecer recebido:
- outra aba reportou a `3C` como concluida

Revisao feita nesta aba:
- nao aprovado
- problemas reais identificados:
  - apos excluir a conta, o frontend remove o token e redireciona para `/`, mas nao limpa `CONV_ID_KEY` nem o `session_id` atual; a home pode continuar com `conversationId` stale de conversa deletada e bloquear o comportamento guest normal
  - `/data-deletion` nao lista explicitamente que conversas e favoritos tambem sao excluidos, apesar de o backend realmente deletar `conversations` via cascade

Resultado:
- emitido prompt corretivo (#12)

### Prompt #12 - Correcao da Fase 3C

Objetivo:
- corrigir o pos-exclusao no frontend e alinhar o texto de `/data-deletion` ao comportamento real da exclusao

Parecer consolidado nesta aba:
- aprovado no workspace atual
- pos-exclusao agora limpa `winegod_token`, `winegod_session_id`, `winegod_conversation_id` e `winegod_messages` antes do redirect
- `/data-deletion` agora lista explicitamente historico de conversas e favoritos como dados excluidos
- `npm run build` passou
- `npx tsc --noEmit` passou quando executado apos o build

Resultado:
- `Fase 3C` considerada fechada
- emitido prompt de execucao da `Fase 4A` (#13)

### Prompt #13 - Execucao da Fase 4A

Objetivo:
- implementar somente a `Fase 4A - modal e atalhos`

Parecer recebido:
- outra aba reportou a `4A` como concluida

Revisao feita nesta aba:
- nao aprovado
- problema real identificado:
  - no desktop, a `4A` removeu o unico caminho de abertura do sidebar expandido: o botao de abrir sidebar existe apenas no mobile em `AppShell`, e o Search do collapsed strip foi redirecionado para abrir apenas o modal

Resultado:
- emitido prompt corretivo (#14)

### Prompt #14 - Correcao da Fase 4A

Objetivo:
- restaurar o acesso ao sidebar expandido no desktop sem perder o SearchModal e os atalhos da `4A`

Parecer consolidado nesta aba:
- aprovado no workspace atual
- sidebar expandido no desktop voltou a abrir por um Menu icon dedicado no collapsed strip
- SearchModal e atalhos da `4A` foram preservados
- `npm run build` passou
- `npx tsc --noEmit` passou quando executado apos o build

Resultado:
- `Fase 4A` considerada fechada
- emitido prompt de execucao da `Fase 4B` (#15)

### Prompt #15 - Execucao da Fase 4B

Objetivo:
- implementar somente a `Fase 4B - busca de conversas e salvos`

Parecer recebido:
- outra aba reportou a `4B` como concluida

Revisao feita nesta aba:
- nao aprovado
- problema real identificado:
  - no `SearchModal`, requests anteriores nao sao invalidados nem versionados; se a resposta de uma query antiga chegar depois da nova, `results` pode ser sobrescrito com dados que nao correspondem mais ao texto atual

Resultado:
- emitido prompt corretivo (#16)

### Prompt #16 - Correcao da Fase 4B

Objetivo:
- impedir que respostas fora de ordem sobrescrevam a query atual no `SearchModal`

Parecer recebido:
- outra aba reportou a `4B` como concluida

Revisao feita nesta aba:
- ainda nao aprovado
- problema real residual identificado:
  - quando a query e limpa, a effect retorna cedo sem invalidar a request anterior ja disparada; se ela retornar depois, `results` pode ser repovoado mesmo com o campo vazio

Resultado:
- emitido prompt corretivo (#17)

### Prompt #17 - Correcao adicional da Fase 4B

Objetivo:
- invalidar tambem requests em voo quando a query for limpa no `SearchModal`

Parecer consolidado nesta aba:
- aprovado no workspace atual
- limpar a query agora tambem invalida request anterior em voo
- `npm run build` passou
- `npx tsc --noEmit` passou quando executado depois do build

Observacao de validacao:
- neste workspace, `tsc` continua sensivel a timing se rodar em paralelo com o build por causa de `.next/types`
- o resultado valido considerado nesta aba e o sequencial: build primeiro, `tsc` depois

Resultado:
- `Fase 4B` considerada fechada
- emitido prompt de execucao da `Fase 4C` (#18)

### Prompt #18 - Execucao da Fase 4C

Objetivo:
- implementar somente a `Fase 4C - CTA para nova pergunta no chat`

Parecer recebido:
- outra aba reportou a `4C` como concluida

Revisao feita nesta aba:
- nao aprovado
- problemas reais identificados:
  - o fluxo cross-page `/?ask=` so e processado no ramo autenticado com `getUser()` bem-sucedido; guest e fallback para guest nao consomem `ask`
  - no fluxo cross-page, `?ask=` nao chama `handleNewChat()`, entao uma conversa ativa anterior pode ser reutilizada indevidamente

Resultado:
- emitido prompt corretivo (#19)

### Prompt #19 - Correcao da Fase 4C

Objetivo:
- corrigir o fluxo cross-page do `?ask=` para guest/fallback guest e garantir novo chat antes de enviar

Parecer consolidado nesta aba:
- aprovado no workspace atual
- `?ask=` agora e processado no inicio do init, antes da auth, cobrindo home, cross-page logado, cross-page guest e fallback guest
- o fluxo cross-page agora reseta `messages`, `conversationId`, storage e `session_id` quando apropriado antes de disparar `pendingAsk`
- `npm run build` passou
- `npx tsc --noEmit` passou quando executado de forma sequencial apos o build

Observacao de validacao:
- neste workspace, `tsc` continua sensivel a timing se rodar junto com o build por causa de `.next/types`
- o resultado valido considerado nesta aba e o sequencial: build primeiro, `tsc` depois

Resultado:
- `Fase 4C` considerada fechada
- rollout do plano original considerado completo
- emitido prompt operacional pos-plano para UI de toggle salvo no chat (#20)

### Prompt #20 - Pos-plano: UI de toggle salvo no chat

Objetivo:
- expor no chat a acao de salvar/remover salvo usando o backend da `Fase 3A`

Parecer recebido:
- outra aba reportou o passo pos-plano como concluido

Revisao feita nesta aba:
- nao aprovado
- problemas reais identificados:
  - o toggle aceita cliques repetidos sem estado pending/disabled, entao pode disparar requests concorrentes fora de ordem e terminar com estado divergente do ultimo clique do usuario
  - falha de persistencia ainda faz apenas rollback silencioso, sem feedback honesto de loading/erro na UI

Resultado:
- emitido prompt corretivo (#21)

### Prompt #21 - Correcao do pos-plano: UI de toggle salvo no chat

Objetivo:
- fechar concorrencia, loading e erro honesto no toggle de salvo do chat

Parecer consolidado nesta aba:
- aprovado no workspace atual
- o toggle agora bloqueia double-click com `togglePending`
- respostas stale sao descartadas via `toggleRequestRef`
- troca de conversa invalida request antiga e limpa feedback local
- a UI agora expone pending e erro minimo de forma honesta
- `npm run build` passou
- `npx tsc --noEmit` passou quando executado de forma sequencial apos o build

Observacao de validacao:
- neste workspace, `tsc` continua sensivel a timing se rodar junto com o build por causa de `.next/types`
- o resultado valido considerado nesta aba e o sequencial: build primeiro, `tsc` depois

Resultado:
- pos-plano de toggle salvo no chat considerado fechado
- emitido prompt operacional de validacao manual/end-to-end (#22)

### Prompt #22 - Pos-plano: validacao manual/end-to-end do rollout

Objetivo:
- subir o stack local e validar de ponta a ponta o rollout completo do sidebar

Parecer recebido:
- outra aba reportou a validacao runtime local como sem bug bloqueante

Revisao feita nesta aba:
- nao aprovado
- problema real identificado:
  - `backend/config.py` continua com default `GUEST_CREDIT_LIMIT = 1000`
  - runtime local confirmou `limit: 1000`
  - plano, handoff e UI inteira dizem `5`
  - nao existe override visivel no repo local, entao isto nao pode ser tratado so como observacao de ambiente

Resultado:
- emitido prompt corretivo (#23)

### Prompt #23 - Correcao do pos-plano: alinhar contrato de creditos guest

Objetivo:
- alinhar runtime, config, UI e handoff para o limite guest correto

Parecer consolidado nesta aba:
- aprovado no workspace atual
- `backend/config.py` agora usa default `5` para `GUEST_CREDIT_LIMIT`
- validacao local confirmou `Config.GUEST_CREDIT_LIMIT = 5` e `Config.USER_CREDIT_LIMIT = 15`
- backend reboot local confirmou `GET /api/credits` guest retornando `limit: 5`

Resultado:
- correcao do contrato de creditos guest considerada fechada
- hardening runtime local sem OAuth/browser volta a ficar sem blocker conhecido
- emitido prompt operacional de validacao visual/browser (#24)

### Prompt #24 - Pos-plano: validacao visual/browser dos fluxos guest e atalhos

Objetivo:
- validar em browser os fluxos guest e os atalhos/interacoes principais do sidebar

Parecer recebido:
- outra aba reportou honestamente que nao tem browser tool e nao executou validacao real em browser

Revisao feita nesta aba:
- nao aprovado como validacao concluida
- sem finding novo de codigo
- bloqueio real identificado:
  - esta aba nao executou nenhum passo de browser
  - portanto nao pode afirmar ausencia de blockers de interacao
  - o pos-plano de validacao visual/browser continua aberto

Resultado:
- emitido prompt operacional (#25) para transformar o checklist existente em roteiro manual executavel por humano ou aba com browser tool

### Prompt #25 - Pos-plano: roteiro manual para validacao visual/browser

Objetivo:
- preparar roteiro curto, executavel e sem ambiguidade para um executor humano ou aba com browser tool

Parecer consolidado nesta aba:
- aprovado no workspace atual
- `reports/ROTEIRO_VALIDACAO_BROWSER_SIDEBAR.md` ficou objetivo, curto e operacional
- cobre os fluxos guest e atalhos principais sem fingir validacao de browser
- inclui template de anotacao de falha e explicita o que depende de OAuth real

Resultado:
- roteiro manual considerado fechado
- emitido prompt operacional (#26) para consolidacao dos resultados quando houver execucao humana/browser real

### Prompt #26 - Pos-plano: consolidacao dos resultados do roteiro manual

Objetivo:
- receber o resultado do executor humano/browser e converter em findings acionaveis ou aprovacao final

## Estado atual exato

Neste momento, esta aba esta fazendo o seguinte:
- mantendo `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md` como fonte de verdade do rollout
- mantendo este arquivo como fonte de verdade da coordenacao multiaba
- mantendo a `Fase 3C` como fechada no workspace atual
- mantendo a `Fase 4A` como fechada no workspace atual
- mantendo a `Fase 4B` como fechada no workspace atual
- mantendo a `Fase 4C` como fechada no workspace atual
- mantendo o handoff principal apontando corretamente para rollout completo
- mantendo o pos-plano de toggle salvo no chat como fechado no workspace atual
- mantendo a validacao runtime local sem OAuth/browser como fechada no workspace atual
- mantendo a validacao visual/browser real como pendente de execucao humana ou agente com browser tool
- aguardando resultados reais do roteiro manual para consolidacao via prompt #26
- proxima acao planejada:
  - receber o resultado do roteiro manual executado de verdade
  - consolidar findings reais ou aprovar a validacao visual/browser
  - se reprovar, emitir prompt corretivo com achados objetivos

## Ultimo prompt emitido para a outra aba

Este e o prompt ativo mais recente, para reaproveitamento em caso de queda de terminal:

```text
Continue somente a correcao da `Fase 3C - exclusao de conta` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Importante:
- a `Fase 3C` NAO esta aprovada ainda
- nao avance para `4A+`
- nao reverta alteracoes fora do escopo
- preserve as partes boas ja feitas da `3C`

Findings obrigatorios desta revisao:

1. Corrigir o pos-exclusao na home
- Hoje `deleteAccount()` remove o token e `DeleteAccountSection` faz `router.push("/")`, mas isso nao limpa `CONV_ID_KEY` nem o `session_id` atual.
- Em `frontend/app/page.tsx`, a home inicializa `conversationId` a partir de `sessionStorage[CONV_ID_KEY]`.
- Resultado possivel apos exclusao:
  - o usuario volta para guest
  - mas continua com `conversationId` stale de conversa deletada
  - o draft guest pode parar de persistir corretamente
  - o `session_id` antigo continua ativo sem necessidade
- Corrija para que, apos exclusao bem-sucedida, o frontend realmente volte para um guest state limpo.

2. Alinhar o texto de `/data-deletion` ao que o backend faz
- O backend realmente deleta `conversations` via cascade.
- A pagina `/data-deletion` precisa dizer isso explicitamente em “O que e excluido”.
- Hoje o texto esta incompleto se nao listar historico/conversas salvas.
- Mantenha o texto honesto sobre `message_log` anonimizados com `user_id = NULL`.

3. Nao quebrar o que ja foi consertado
- mantenha intacto:
  - auth/creditos da `0A/0B`
  - historico da `2C`
  - migracao guest -> logado da `2D`
  - favoritos backend da `3A`
  - pagina `/favoritos` da `3B`

Validacao minima obrigatoria:
- backend:
  - syntax/imports
  - app boot / rota registrada
- frontend:
  - `npm run build` em `frontend`
  - `npx tsc --noEmit` depois do build
- nao diga que validou HTTP real ou browser real sem de fato testar

Atualizacao do handoff:
- NAO mantenha a `Fase 3C` como concluida se os bugs acima ainda existirem
- so atualize `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md` se a `3C` ficar realmente fechada
- se fechar a `3C`, atualize o proximo passo recomendado para `Fase 4A - modal e atalhos`

Entrega final, exatamente com:
A. resumo do que mudou
B. arquivos alterados
C. validacao executada de verdade
D. confirmacao explicita do que e limpo no frontend apos exclusao e do que e deletado/anonimizado no backend
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima registra o prompt `#25`
- o prompt ativo mais recente agora e o `#26`, abaixo

```text
Continue somente o pos-plano: `consolidacao dos resultados do roteiro manual de browser` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/ROTEIRO_VALIDACAO_BROWSER_SIDEBAR.md`
3. codigo atual
4. resultado bruto do executor humano ou da aba com browser tool

Estado confirmado nesta aba:
- o rollout 0-4 esta fechado
- o toggle salvo no chat esta fechado
- o runtime local sem browser ja foi validado
- o roteiro manual de browser ja foi preparado
- o que falta agora e consolidar o resultado da execucao real do roteiro

Importante:
- nao invente passos executados
- nao marque validacao browser como concluida sem evidencia de execucao real
- nao reabra fases antigas sem finding objetivo
- nao altere codigo se o executor nao reportou bug real

Objetivo:
- receber o resultado bruto do roteiro manual
- converter isso em:
  - aprovacao final da validacao visual/browser
  - ou findings objetivos com proximo prompt corretivo

Como trabalhar:

1. Ler o resultado bruto
- mapear cada falha ao numero do passo do roteiro
- separar:
  - passou
  - falhou
  - nao executado

2. Se houver falha real
- produzir finding objetivo com:
  - passo do roteiro
  - rota
  - comportamento observado
  - comportamento esperado
  - impacto
- se a falha for de codigo, emitir o proximo prompt corretivo para implementacao

3. Se tudo passar
- declarar a validacao visual/browser como fechada
- consolidar riscos residuais apenas do que segue bloqueado por OAuth/ambiente

4. Atualizar handoff
- registrar o resultado real da execucao do roteiro
- manter honestidade sobre o que foi ou nao foi validado

Entrega final, exatamente com:
A. resumo do resultado consolidado
B. passos que passaram, falharam ou nao foram executados
C. findings reais ou confirmacao de ausencia de blockers
D. proximo prompt corretivo ou confirmacao de fechamento
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima registra o prompt `#24`
- o prompt ativo mais recente agora e o `#25`, abaixo

```text
Continue somente o pos-plano: `roteiro manual para validacao visual/browser do sidebar` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Estado confirmado nesta aba:
- o rollout 0-4 esta fechado
- o toggle salvo no chat esta fechado
- o runtime backend/local sem browser ja foi validado no que era possivel
- a validacao visual/browser continua pendente porque esta aba nao tem browser tool

Importante:
- NAO finja validacao de browser
- NAO diga que clicou/pressionou atalhos/viu estados no navegador sem realmente executar
- nao reabra fases antigas
- nao altere codigo sem finding real

Objetivo:
- converter o checklist de browser pendente em um roteiro manual curto, executavel e sem ambiguidade
- esse roteiro deve servir para:
  - o usuario executar no navegador
  - ou outra aba/agente que tenha browser tool executar

Entrega obrigatoria:

1. Preparar roteiro manual enxuto
- no maximo 12 passos
- cada passo com:
  - URL
  - acao
  - resultado esperado
- foque em fluxos guest e atalhos

2. Cobrir no minimo:
- home e shell
- abrir sidebar expandido
- abrir SearchModal por click
- abrir SearchModal por `Ctrl+K` / `Cmd+K`
- fechar por `Escape`
- fechar por overlay
- confirmar guard de atalho dentro do input
- `/favoritos`, `/conta`, `/plano` em estado guest
- CTA `Perguntar ao Baco` iniciando nova conversa guest

3. Incluir template de anotacao de falha
- passo
- comportamento observado
- comportamento esperado
- screenshot opcional

4. Atualizar handoff
- registrar que o proximo executor precisa ser humano ou agente com browser tool
- deixar o roteiro manual facil de encontrar

Sem codigo por padrao:
- so altere codigo se encontrar algum problema objetivo enquanto prepara o roteiro
- caso contrario, este prompt e apenas de preparacao operacional

Entrega final, exatamente com:
A. roteiro manual final
B. arquivos alterados
C. se houve ou nao alteracao de codigo
D. observacao explicita de que a validacao real ainda depende de executor com browser
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima registra o prompt `#23`
- o prompt ativo mais recente agora e o `#24`, abaixo

```text
Continue somente o pos-plano: `validacao visual/browser dos fluxos guest e atalhos do sidebar` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Estado confirmado nesta aba:
- o rollout original 0-4 esta fechado e aprovado
- o pos-plano do toggle salvo no chat esta fechado
- a divergencia de `GUEST_CREDIT_LIMIT` foi corrigida e o backend local voltou a responder `limit: 5` para guest
- o gap restante agora e validacao visual/browser e interacoes reais

Importante:
- isto e validacao pos-plano, nao reabra fases antigas sem finding objetivo
- nao reverta alteracoes fora do escopo
- preserve as partes boas ja feitas
- nao diga que validou browser real/atalho real sem de fato abrir e testar

Objetivo:
- validar de verdade, em browser local, os fluxos guest e as interacoes principais do sidebar/search

Escopo minimo:

1. Home e shell
- abrir `/`
- confirmar shell, header e collapsed sidebar strip renderizando
- abrir sidebar expandido no desktop
- abrir/fechar sidebar no mobile se o ambiente permitir viewport/responsividade

2. SearchModal e atalhos
- abrir SearchModal por click em `Buscar`
- abrir por `Ctrl+K` / `Cmd+K`
- fechar por `Escape`
- fechar por click no overlay
- confirmar que o atalho NAO abre quando o foco esta em input/textarea/contentEditable

3. Fluxos guest acessiveis sem OAuth
- `/favoritos`, `/conta`, `/plano`, `/ajuda`, `/privacy`, `/terms`, `/data-deletion`
- confirmar estados guest coerentes
- no SearchModal:
  - idle
  - empty com query sem resultado
  - CTA `Perguntar ao Baco`
- validar que o CTA injeta nova pergunta no chat em fluxo guest, se der para observar no browser real

4. Honestidade de validacao
- se algum passo nao puder ser testado por limite do ambiente/browser, diga exatamente o que bloqueou
- diferencie claramente:
  - validado de verdade
  - nao validado
  - bloqueado por ambiente

5. Nao quebrar o que ja foi consertado
- nao entrar em refactor paralelo
- so mexer em codigo se encontrar bug real reproduzido

Validacao minima obrigatoria:
- se tocar frontend durante correcao de bug encontrado:
  - `npm run build`
  - `npx tsc --noEmit` depois do build, de forma sequencial
- reporte explicitamente quais interacoes de browser voce executou de verdade

Atualizacao do handoff:
- se encontrar bug real, registrar finding e nao tratar o hardening visual como fechado
- se nao encontrar blocker, atualizar o handoff com status da validacao visual/browser e riscos residuais

Entrega final, exatamente com:
A. o que foi validado de verdade em browser
B. comandos/ferramentas realmente usados
C. findings reais ou confirmacao de ausencia de blockers
D. o que ficou nao validado ou bloqueado por ambiente
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima registra o prompt `#22`
- o prompt ativo mais recente agora e o `#23`, abaixo

```text
Continue somente a correcao do pos-plano: `alinhar contrato de creditos guest` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Importante:
- o rollout 0-4 e o pos-plano do toggle continuam fechados
- a validacao runtime local NAO esta aprovada ainda
- nao reabra fases antigas sem necessidade
- nao reverta alteracoes fora do escopo

Finding obrigatorio desta revisao:
- `backend/config.py` continua com `GUEST_CREDIT_LIMIT = int(os.getenv("GUEST_CREDIT_LIMIT", "1000"))`
- runtime local confirmou guest `limit: 1000`
- plano, handoff e UI inteira dizem `5 mensagens por sessao`
- nao ha override visivel no repo local que justifique tratar isso apenas como detalhe de ambiente

Objetivo:
- alinhar runtime, config default e documentacao ao contrato correto de guest credits

Correcao obrigatoria:

1. Corrigir a fonte de verdade do limite guest
- ajustar o backend para que o comportamento padrao/local fique coerente com o contrato aprovado
- o objetivo esperado e guest = 5 por sessao
- se houver motivo tecnico forte para manter override por env, tudo bem; o default local nao pode continuar 1000

2. Nao quebrar o resto do contrato
- manter user free logado = 15 por dia
- manter auth/credits da 0A/0B
- manter banners/textos/frontend coerentes com o backend

3. Validar de verdade o runtime corrigido
- rode de novo o backend local
- confirme via request real qual `limit` guest volta em `GET /api/credits`
- reporte o valor observado, nao apenas o codigo alterado

4. Atualizar handoff sem ambiguidade
- remover a leitura de que isso era "fora do escopo" se a correcao for aplicada
- registrar claramente que a divergencia foi corrigida ou, se nao conseguir corrigir, por que nao

Validacao minima obrigatoria:
- backend:
  - syntax/imports
  - boot local
  - request real em `GET /api/credits` guest mostrando o `limit`
- frontend, se tocar algo:
  - `npm run build` em `frontend`
  - `npx tsc --noEmit` depois do build, de forma sequencial

Entrega final, exatamente com:
A. resumo do que mudou
B. arquivos alterados
C. validacao executada de verdade
D. valor guest observado em runtime apos a correcao
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima registra o prompt `#21`
- o prompt ativo mais recente agora e o `#22`, abaixo

```text
Continue somente o pos-plano: `validacao manual/end-to-end do rollout do sidebar` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Estado confirmado nesta aba:
- o rollout original 0-4 esta fechado e aprovado
- o pos-plano de toggle salvo no chat tambem esta fechado no workspace atual
- falta validacao real de runtime/browser/fluxos integrados

Importante:
- isto e validacao/hardening pos-plano, nao reabra fases antigas sem finding objetivo
- nao reverta alteracoes fora do escopo
- preserve as partes boas ja feitas
- nao diga que validou browser real, OAuth real ou HTTP real sem de fato subir e testar

Objetivo:
- subir o stack local e validar de ponta a ponta os fluxos principais do rollout
- consolidar o que realmente funciona em runtime e o que ainda depende de ambiente/producao

Escopo minimo de validacao:

1. Boot local
- subir backend e frontend localmente
- confirmar que a aplicacao abre sem erro fatal

2. Fluxos principais para validar de verdade, no que for viavel
- home abre com shell e sidebar
- sidebar abre/fecha desktop/mobile
- SearchModal abre por click e por `Ctrl+K` / `Cmd+K`
- `/favoritos`, `/conta`, `/plano`, `/ajuda`, `/privacy`, `/terms`, `/data-deletion` carregam
- busca no modal mostra estados coerentes
- CTA `Perguntar ao Baco` abre nova conversa
- toggle salvo no chat funciona em runtime, se houver contexto autenticado viavel localmente

3. Limites honestos
- se OAuth real nao estiver viavel localmente, nao invente
- se algum fluxo depender de token/DB/migrations/seed, declare exatamente o bloqueio
- diferencie:
  - validado de verdade
  - nao validado
  - bloqueado por ambiente

4. Saida esperada
- se encontrar bug real de runtime, descreva com precisao suficiente para emitir prompt corretivo
- se nao encontrar bug bloqueante, consolide riscos residuais de ambiente/producao

5. Nao quebrar o que ja foi consertado
- nao entrar em refactor paralelo
- nao mexer em UI/codigo sem motivo concreto de bug encontrado

Validacao minima obrigatoria:
- `npm run build` em `frontend`
- `npx tsc --noEmit` depois do build, de forma sequencial
- qualquer boot local/stack que voce realmente executar deve ser reportado com honestidade

Atualizacao do handoff:
- se a validacao encontrar bug real, registre os findings com clareza
- se a validacao passar no que foi possivel, atualize o handoff com status de hardening pos-plano e riscos residuais

Entrega final, exatamente com:
A. o que foi validado de verdade
B. comandos/stack realmente executados
C. findings reais ou confirmacao de ausencia de blockers
D. o que ficou nao validado ou bloqueado por ambiente
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima registra o prompt `#20`
- o prompt ativo mais recente agora e o `#21`, abaixo

```text
Continue somente a correcao do pos-plano: `UI de toggle salvo no chat` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Importante:
- o rollout original 0-4 continua fechado
- este passo pos-plano NAO esta aprovado ainda
- nao reabra fases antigas
- nao reverta alteracoes fora do escopo
- preserve as partes boas ja feitas

Findings obrigatorios desta revisao:

1. Corrigir concorrencia no toggle
- hoje `handleToggleSaved` faz optimistic update e dispara `updateConversationSaved(...)`, mas nao existe estado pending nem bloqueio de clique repetido
- isso permite requests concorrentes fora de ordem para a mesma conversa
- resultado possivel:
  - o usuario clica duas vezes rapido
  - a resposta antiga chega depois da nova
  - UI e backend podem terminar em estado diferente da ultima intencao do usuario
- corrija de forma simples e robusta

2. Tratar loading e erro de forma honesta
- hoje a falha so faz rollback silencioso
- isso nao atende o contrato pedido para esse pos-plano
- a UI precisa expor pelo menos:
  - estado pending coerente no botao
  - bloqueio ou disable enquanto a request esta em voo
  - feedback minimo de erro se a persistencia falhar

3. Nao deixar resposta antiga contaminar conversa nova
- considere tambem o caso em que o usuario troca de conversa ou inicia novo chat enquanto o toggle anterior ainda esta em voo
- a resolucao/rollback nao pode sobrescrever o estado salvo de outra conversa aberta depois

4. Nao quebrar o que ja foi consertado
- mantenha intacto:
  - historico da `2C`
  - migracao guest -> logado da `2D`
  - favoritos da `3A/3B`
  - exclusao de conta da `3C`
  - modal/atalhos da `4A`
  - busca e CTA da `4B/4C`

Validacao minima obrigatoria:
- `npm run build` em `frontend`
- `npx tsc --noEmit` depois do build, de forma sequencial
- nao diga que validou browser real ou HTTP real sem de fato testar

Atualizacao do handoff:
- NAO mantenha este pos-plano como concluido se os bugs acima ainda existirem
- atualize `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md` somente se esta correcao ficar realmente fechada

Entrega final, exatamente com:
A. resumo do que mudou
B. arquivos alterados
C. validacao executada de verdade
D. confirmacao explicita de como ficou o controle de concorrencia/loading/erro no toggle
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima ficou historicamente no arquivo, mas o prompt ativo mais recente agora e o `#20`, abaixo

```text
Continue somente o pos-plano: `UI de toggle salvo no chat` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Estado confirmado nesta aba:
- o rollout original do sidebar esta fechado e aprovado ate a `Fase 4C`
- backend de salvos da `3A` ja existe:
  - `PUT /api/conversations/<id>/saved`
  - `GET /api/conversations?saved=true`
- `/favoritos` ja lista conversas salvas
- `SearchModal` ja busca conversas/salvos e ja injeta `?ask=` no chat

Importante:
- isto e trabalho pos-plano, nao reabra fases 0 a 4
- nao reverta alteracoes fora do escopo
- preserve as partes boas ja feitas

Objetivo:
- permitir que o usuario marque e desmarque a conversa atual como salva diretamente no chat
- reutilizar o contrato backend ja existente, sem criar stack paralela

Implementacao obrigatoria:

1. Expor toggle de salvo no chat
- adicionar um controle visivel e discreto para salvar/remover salvo da conversa ativa
- o controle deve aparecer apenas quando fizer sentido:
  - usuario autenticado
  - conversa backend-managed ativa (`conversationId` real)
- nao mostrar toggle funcional para guest
- nao tentar salvar draft local sem conversa persistida

2. Wiring com backend existente
- usar o endpoint ja entregue:
  - `PUT /api/conversations/<id>/saved` com body `{"saved": true|false}`
- pode adicionar wrapper fino no frontend se necessario
- refletir o estado atual de salvo na UI
- tratar loading e erro de forma honesta

3. Coerencia com o resto do produto
- apos salvar/desalvar, manter `/favoritos` e o resto da navegacao coerentes
- se precisar, atualizar `conversationsRefreshKey` ou mecanismo equivalente
- nao quebrar historico, busca, nem abertura de conversa

4. Escopo
- nao criar pagina nova
- nao refatorar chat inteiro
- nao inventar favoritos de vinho; continua sendo conversa salva
- prefira um patch pequeno e claro no fluxo atual

5. Nao quebrar o que ja foi consertado
- mantenha intacto:
  - historico da `2C`
  - migracao guest -> logado da `2D`
  - favoritos backend da `3A`
  - pagina `/favoritos` da `3B`
  - exclusao de conta da `3C`
  - modal/atalhos da `4A`
  - busca real e CTA da `4B/4C`

Validacao minima obrigatoria:
- `npm run build` em `frontend`
- `npx tsc --noEmit` depois do build, de forma sequencial
- nao diga que validou browser real ou HTTP real sem de fato testar

Atualizacao do handoff:
- atualize `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md` somente se este passo pos-plano ficar realmente fechado
- registre este trabalho como extensao pos-plano, nao como reabertura das fases 0 a 4

Entrega final, exatamente com:
A. resumo do que mudou
B. arquivos alterados
C. validacao executada de verdade
D. comportamento final do toggle salvo no chat
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima era o prompt `#13`
- o prompt ativo mais recente agora e o `#14`, abaixo

```text
Continue somente a correcao da `Fase 4A - modal e atalhos` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Importante:
- a `Fase 4A` NAO esta aprovada ainda
- nao avance para `4B+`
- nao reverta alteracoes fora do escopo
- preserve as partes boas ja feitas da `4A`

Finding obrigatorio desta revisao:
- no desktop, a `4A` removeu o unico caminho de abertura do sidebar expandido
- hoje o botao de abrir sidebar em `AppShell` existe apenas no mobile (`md:hidden`)
- e em `Sidebar` o Search do collapsed strip passou a abrir apenas o modal
- resultado: no desktop, o usuario perde acesso ao sidebar expandido e ao historico/lista real entregues na `2C`

Correcao obrigatoria:
1. Restaurar um caminho claro para abrir o sidebar expandido no desktop
- pode ser um novo botao dedicado no collapsed strip
- ou outro controle desktop coerente com o shell atual
- o importante e nao depender do botao mobile

2. Nao perder o que a `4A` fez de bom
- mantenha:
  - `SearchModal`
  - abertura por click em `Buscar`
  - `Ctrl+K` / `Cmd+K`
  - fechar com `Escape`
  - fechar com click no overlay

3. Nao quebrar o que ja foi consertado
- mantenha intacto:
  - historico da `2C`
  - migracao guest -> logado da `2D`
  - favoritos da `3A/3B`
  - exclusao de conta da `3C`

Validacao minima obrigatoria:
- `npm run build` em `frontend`
- `npx tsc --noEmit` depois do build
- nao diga que validou browser real sem de fato testar

Atualizacao do handoff:
- NAO mantenha a `Fase 4A` como concluida se o bug acima ainda existir
- so atualize `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md` se a `4A` ficar realmente fechada
- se fechar a `4A`, atualize o proximo passo recomendado para `Fase 4B - busca de conversas e salvos`

Entrega final, exatamente com:
A. resumo do que mudou
B. arquivos alterados
C. validacao executada de verdade
D. confirmacao explicita de como o sidebar expandido voltou a abrir no desktop sem perder os atalhos da busca
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima era o prompt `#14`
- o prompt ativo mais recente agora e o `#15`, abaixo

```text
Continue somente a `Fase 4B - busca de conversas e salvos` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Estado confirmado nesta aba:
- a `Fase 4A` esta fechada no workspace atual
- o sidebar expandido no desktop voltou a abrir por Menu icon dedicado no collapsed strip
- SearchModal, `Ctrl+K` / `Cmd+K`, `Escape` e click no overlay continuam funcionando no codigo
- `npm run build` passou
- `npx tsc --noEmit` passou quando executado apos o build

Nao volte para `4A`. Nao avance para `5A+`.
- nao reverta alteracoes fora do escopo
- preserve as partes boas ja feitas ate aqui

Objetivo da 4B:
- transformar o SearchModal de placeholder em busca real de conversas e salvos
- listar resultados uteis e navegaveis
- reutilizar o backend/contratos ja existentes, sem inventar stack paralela

Implementacao obrigatoria:

1. Buscar conversas reais
- usar `GET /api/conversations?q=<texto>` para busca de conversas
- pode criar wrapper fino no frontend se necessario
- nao quebrar o historico ja existente no sidebar

2. Mostrar salvos no modal
- usar o contrato da `3A`
- opcao recomendada:
  - buscar `GET /api/conversations?saved=true`
  - aplicar filtro client pelo texto digitado
- se houver escolha melhor e simples, tudo bem; evite refactor paralelo

3. Estrutura da UI no SearchModal
- manter o input atual
- entregar estados reais:
  - idle
  - loading
  - empty
  - erro
  - resultados
- separar visualmente `Conversas` e `Salvos` se ambos existirem
- se a query estiver vazia, pode mostrar placeholder honesto ou itens iniciais uteis; seja coerente

4. Navegacao de resultado
- clicar em um resultado deve reabrir a conversa
- reutilize o fluxo existente do produto
- se a melhor opcao for navegar para `/?conv=<id>`, tudo bem
- o modal deve fechar apos navegar

5. Comportamento minimo esperado
- debounce simples e barato, se necessario
- evitar flood de requests por tecla
- nao abrir busca dentro de input/textarea/contentEditable
- nao duplicar listeners globais

6. Nao quebrar o que ja foi consertado
- mantenha intacto:
  - historico da `2C`
  - migracao guest -> logado da `2D`
  - favoritos da `3A/3B`
  - exclusao de conta da `3C`
  - atalhos/modal da `4A`

Validacao minima obrigatoria:
- `npm run build` em `frontend`
- `npx tsc --noEmit` depois do build
- nao diga que validou browser real ou HTTP real sem de fato testar

Atualizacao do handoff:
- so atualize `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md` se a `4B` estiver realmente fechada
- se fechar a `4B`, atualize o proximo passo recomendado para `Fase 5A - pagina /c/[id] e deep links`
- nao reescreva fases antigas

Entrega final, exatamente com:
A. resumo do que mudou
B. arquivos alterados
C. validacao executada de verdade
D. comportamento final da busca, incluindo como conversa/salvo aparecem e como a navegacao fecha o modal
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima era o prompt `#15`
- o prompt ativo mais recente agora e o `#16`, abaixo

```text
Continue somente a correcao da `Fase 4B - busca de conversas e salvos` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Importante:
- a `Fase 4B` NAO esta aprovada ainda
- nao avance para `4C+`
- nao reverta alteracoes fora do escopo
- preserve as partes boas ja feitas da `4B`

Finding obrigatorio desta revisao:
- no `SearchModal`, requests anteriores nao sao invalidados nem versionados
- hoje, se a resposta de uma query antiga chegar depois da nova, `setResults(list)` ainda roda
- resultado: o modal pode mostrar resultados que nao correspondem mais ao texto atual digitado pelo usuario

Correcao obrigatoria:
1. Garantir coerencia entre query atual e resultados renderizados
- aceite qualquer abordagem simples e robusta:
  - sequence id / request version
  - comparar a query retornada com a query atual antes de aplicar
  - ou outra protecao equivalente
- o importante e impedir overwrite fora de ordem

2. Nao perder o que a `4B` fez de bom
- mantenha:
  - debounce
  - secoes `Conversas` e `Salvos`
  - deduplicacao
  - click abre conversa e fecha modal
  - callback direto na home e `router.push("/?conv=<id>")` fora dela

3. Nao quebrar o que ja foi consertado
- mantenha intacto:
  - historico da `2C`
  - migracao guest -> logado da `2D`
  - favoritos da `3A/3B`
  - exclusao de conta da `3C`
  - atalhos/modal da `4A`

Validacao minima obrigatoria:
- `npm run build` em `frontend`
- `npx tsc --noEmit` depois do build
- nao diga que validou browser real ou HTTP real sem de fato testar

Atualizacao do handoff:
- NAO mantenha a `Fase 4B` como concluida se o bug acima ainda existir
- so atualize `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md` se a `4B` ficar realmente fechada
- se fechar a `4B`, atualize o proximo passo recomendado para `Fase 4C - CTA para nova pergunta no chat`

Entrega final, exatamente com:
A. resumo do que mudou
B. arquivos alterados
C. validacao executada de verdade
D. confirmacao explicita de como ficou a protecao contra respostas fora de ordem no SearchModal
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima era o prompt `#16`
- o prompt ativo mais recente agora e o `#17`, abaixo

```text
Continue somente a correcao da `Fase 4B - busca de conversas e salvos` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Importante:
- a `Fase 4B` NAO esta aprovada ainda
- nao avance para `4C+`
- nao reverta alteracoes fora do escopo
- preserve as partes boas ja feitas da `4B`

Finding obrigatorio desta revisao:
- o version guard melhorou o caso principal, mas ainda ha um residual quando a query e limpa
- hoje, se uma request da query anterior ja tiver disparado e o usuario limpar o campo, a effect retorna cedo sem invalidar essa request
- se a resposta voltar depois, `results` ainda pode ser repovoado mesmo com o campo vazio

Correcao obrigatoria:
1. Invalidar tambem requests em voo quando a query for limpa
- a protecao precisa cobrir:
  - query trocando de texto
  - query ficando vazia
  - modal fechando
- aceite qualquer abordagem simples e robusta, desde que garanta coerencia entre texto atual e resultados renderizados

2. Nao perder o que a `4B` fez de bom
- mantenha:
  - debounce
  - secoes `Conversas` e `Salvos`
  - deduplicacao
  - click abre conversa e fecha modal
  - callback direto na home e `router.push("/?conv=<id>")` fora dela

3. Nao quebrar o que ja foi consertado
- mantenha intacto:
  - historico da `2C`
  - migracao guest -> logado da `2D`
  - favoritos da `3A/3B`
  - exclusao de conta da `3C`
  - atalhos/modal da `4A`

Validacao minima obrigatoria:
- `npm run build` em `frontend`
- `npx tsc --noEmit` depois do build
- nao diga que validou browser real ou HTTP real sem de fato testar

Atualizacao do handoff:
- NAO mantenha a `Fase 4B` como concluida se o bug acima ainda existir
- so atualize `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md` se a `4B` ficar realmente fechada
- se fechar a `4B`, atualize o proximo passo recomendado para `Fase 4C - CTA para nova pergunta no chat`

Entrega final, exatamente com:
A. resumo do que mudou
B. arquivos alterados
C. validacao executada de verdade
D. confirmacao explicita de como ficou a protecao contra respostas fora de ordem, inclusive quando a query e limpa
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima era o prompt `#17`
- o prompt ativo mais recente agora e o `#18`, abaixo

```text
Continue somente a `Fase 4C - CTA para nova pergunta no chat` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Estado confirmado nesta aba:
- a `Fase 4B` esta fechada no workspace atual
- SearchModal agora protege contra respostas fora de ordem em 3 caminhos:
  - query trocando de texto
  - query ficando vazia
  - modal fechando
- `npm run build` passou
- `npx tsc --noEmit` passou quando executado depois do build

Importante:
- neste workspace, nao use `npx tsc --noEmit` em paralelo com o build como fonte de verdade
- o resultado valido para validacao desta fase deve ser sequencial: build primeiro, `tsc` depois

Nao volte para `4B`. Nao avance para `5A+`.
- nao reverta alteracoes fora do escopo
- preserve as partes boas ja feitas ate aqui

Objetivo da 4C:
- quando a query nao encontrar conversa/salvo correspondente, oferecer CTA para jogar essa busca como nova pergunta no chat
- manter o SearchModal simples, sem catalogo de vinhos e sem command palette inflada

Implementacao obrigatoria:

1. CTA de nova pergunta
- quando houver query preenchida e nenhum resultado util, mostrar CTA claro:
  - exemplo de contrato: `Perguntar ao Baco sobre "<texto>"`
- o CTA deve ser clicavel e ter cara de acao primaria secundaria, nao apenas texto morto

2. Navegacao/acao ao clicar
- clicar no CTA deve abrir o chat com essa pergunta
- reutilize o fluxo atual do produto
- escolha recomendada:
  - navegar para `/` com um mecanismo simples que a home consiga consumir
  - ou outro mecanismo minimo, claro e sem refactor paralelo
- o modal deve fechar apos disparar a acao

3. Escopo
- nao criar busca de vinhos estruturada
- nao criar recentes
- nao expandir para command palette genérica
- mantenha a UX focada em:
  - achar conversa existente
  - ou perguntar algo novo ao chat

4. Nao quebrar o que ja foi consertado
- mantenha intacto:
  - historico da `2C`
  - migracao guest -> logado da `2D`
  - favoritos da `3A/3B`
  - exclusao de conta da `3C`
  - atalhos/modal da `4A`
  - busca real da `4B`

Validacao minima obrigatoria:
- `npm run build` em `frontend`
- `npx tsc --noEmit` depois do build
- nao diga que validou browser real ou HTTP real sem de fato testar

Atualizacao do handoff:
- so atualize `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md` se a `4C` estiver realmente fechada
- se fechar a `4C`, atualize o proximo passo recomendado para `Fase 5A - pagina /c/[id] e deep links`
- nao reescreva fases antigas

Entrega final, exatamente com:
A. resumo do que mudou
B. arquivos alterados
C. validacao executada de verdade
D. comportamento final do CTA e como ele injeta a pergunta no chat
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima era o prompt `#18`
- o prompt ativo mais recente agora e o `#19`, abaixo

```text
Continue somente a correcao da `Fase 4C - CTA para nova pergunta no chat` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Importante:
- a `Fase 4C` NAO esta aprovada ainda
- nao trate o rollout como completo ainda
- nao reverta alteracoes fora do escopo
- preserve as partes boas ja feitas da `4C`

Findings obrigatorios desta revisao:

1. Corrigir o fluxo cross-page para guest / fallback guest
- hoje `frontend/app/page.tsx` le `?ask=` apenas dentro do ramo autenticado com `getUser()` bem-sucedido
- isso quebra o CTA vindo de paginas com `AppShell` quando o usuario esta guest
- tambem quebra o caso de token presente mas `getUser()` falha e a home cai para guest
- `/?ask=` precisa ser consumido de forma coerente independentemente de o usuario estar logado ou nao

2. Garantir novo chat no fluxo cross-page
- hoje, no caso cross-page, `?ask=` apenas faz `setPendingAsk(askText)`
- diferente da home, isso NAO chama `handleNewChat()`
- se existir `CONV_ID_KEY` / `session_id` ativo, a pergunta pode entrar na conversa anterior
- o contrato correto da `4C` e tratar isso como nova pergunta em novo chat, nao reaproveitar um fio antigo por acidente

3. Nao quebrar o que ja foi consertado
- mantenha intacto:
  - historico da `2C`
  - migracao guest -> logado da `2D`
  - favoritos da `3A/3B`
  - exclusao de conta da `3C`
  - modal/atalhos da `4A`
  - busca real da `4B`

Validacao minima obrigatoria:
- `npm run build` em `frontend`
- `npx tsc --noEmit` depois do build
- nao rode `tsc` em paralelo com o build como fonte de verdade neste workspace
- nao diga que validou browser real ou HTTP real sem de fato testar

Atualizacao do handoff:
- NAO mantenha a `Fase 4C` como concluida se os bugs acima ainda existirem
- so atualize `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md` se a `4C` ficar realmente fechada
- so trate o rollout como completo se a `4C` ficar realmente fechada

Entrega final, exatamente com:
A. resumo do que mudou
B. arquivos alterados
C. validacao executada de verdade
D. confirmacao explicita de como `?ask=` funciona agora para home, cross-page logado e cross-page guest
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

ATUALIZACAO OPERACIONAL:
- o bloco acima era o prompt `#12`
- o prompt ativo mais recente agora e o `#13`, abaixo

```text
Continue somente a `Fase 4A - modal e atalhos` no repositorio `C:\winegod-app`.

Fonte de verdade:
1. `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
2. `reports/PLANO_IMPLEMENTACAO_SIDEBAR.md`
3. codigo atual

Estado confirmado nesta aba:
- a `Fase 3C` esta fechada no workspace atual
- exclusao de conta agora limpa token + session_id + conversationId + draft local antes do redirect
- `/data-deletion` agora lista historico e favoritos como dados excluidos
- `npm run build` passou
- `npx tsc --noEmit` passou quando executado apos o build

Nao volte para `3C`. Nao avance para `4B+`.
- nao reverta alteracoes fora do escopo
- preserve as partes boas ja feitas ate aqui

Objetivo da 4A:
- implementar o primeiro passo da busca v1 com modal real e atalhos
- entregar a abertura/fechamento do modal e o wiring minimo no shell/sidebar
- nao implementar ainda a busca completa de resultados (`4B+`)

Implementacao obrigatoria:

1. SearchModal component
- criar `SearchModal` reutilizavel no frontend
- abrir como modal/dialog real, nao inline panel
- precisa ter estrutura minima util:
  - campo de busca
  - area de estado inicial
  - area para resultados futuros ou placeholder honesto
- manter visual coerente com o produto atual

2. Wiring no shell/sidebar
- integrar abertura do modal a partir do botao `Buscar`
- integrar no layout real usado pelo app (`AppShell` / `Sidebar`)
- escolha um ponto de controle claro do estado do modal
- nao criar fluxo paralelo desconectado do shell atual

3. Atalhos obrigatorios
- abrir por click no botao `Buscar`
- abrir por `Ctrl+K`
- fechar por `Escape`
- nao abrir o atalho quando o foco estiver em `input`, `textarea` ou elemento editavel
- evite listeners duplicados ou vazando entre rotas

4. Escopo desta subfase
- pode deixar resultados reais para a proxima fase
- se ainda nao houver search backend/frontend pronto, use estado inicial honesto no modal
- nao entrar em command palette completa ainda
- nao implementar busca nova no chat ainda

5. Nao quebrar o que ja foi consertado
- mantenha intacto:
  - auth/creditos da `0A/0B`
  - historico da `2C`
  - migracao guest -> logado da `2D`
  - favoritos backend da `3A`
  - pagina `/favoritos` da `3B`
  - exclusao de conta da `3C`

Validacao minima obrigatoria:
- frontend:
  - `npm run build` em `frontend`
  - `npx tsc --noEmit` depois do build
- nao diga que validou HTTP real ou browser real sem de fato testar

Atualizacao do handoff:
- so atualize `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md` se a `4A` estiver realmente fechada
- se fechar a `4A`, atualize o proximo passo recomendado para `Fase 4B - conteudo e comportamento do search modal`
- nao reescreva fases antigas

Entrega final, exatamente com:
A. resumo do que mudou
B. arquivos alterados
C. validacao executada de verdade
D. comportamento final do modal e dos atalhos entregues
E. atualizacao aplicada no `HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
```

### Prompt #26 - Resultado consolidado do roteiro manual (2026-04-14)

Execucao real:
- executor: humano (Murilo), browser real em aba anonima
- frontend: `http://localhost:3003` (3000-3002 ocupadas), backend: `http://localhost:5000`
- os 12 passos do `reports/ROTEIRO_VALIDACAO_BROWSER_SIDEBAR.md` foram executados in-session

A. Resumo consolidado
- 12/12 passos passaram apos 2 correcoes aplicadas durante a execucao
- validacao visual/browser do sidebar fica pronta para ser marcada como fechada apos reconfirmacao de build/tsc pelo executor humano

B. Mapa passo a passo
- 1-9: passou
- 10: passou apos corrigir contador de creditos guest (finding real descrito abaixo) e CORS (pre-condicao de conexao)
- 11: passou (`/favoritos`, `/conta`, `/plano` — botao "Entrar" fixo no topo direito, lista de providers OAuth aparece embaixo do CTA da pagina, comportamento esperado)
- 12: passou (`/data-deletion` guest, sem botao vermelho, so email fallback)
- nenhum passo ficou "nao executado"

C. Findings reais encontrados e resolvidos nesta aba
1. CORS restrito a `localhost:3000` em `backend/app.py` quebrava qualquer porta alternativa do Next dev server. Efeito no roteiro: passo 10 mostrava `Failed to fetch` antes de Baco responder. Correcao: trocado por regex `http://localhost:\d+` na lista de origens.
2. Contador de creditos guest nao renderizado em `frontend/components/AppShell.tsx`. Efeito no roteiro: passo 10 nao exibia `5/5 → 4/5` no header esperado pelo roteiro. Causa: bloco `{user ? <UserMenu /> : <LoginButton />}` so mostrava contador quando logado. Correcao: quando `user === null && creditsLimit > 0`, renderizar span `{remaining}/{limit}` antes do `<LoginButton compact />`. Refresh no `onDone` ja existia em `page.tsx:363`.

D. Proximo prompt corretivo / confirmacao
- nao ha blocker residual de codigo ou UI dentro do escopo do roteiro
- executor humano vai rodar `npm run build` + `npx tsc --noEmit` em `frontend/` e validar que as duas correcoes nao quebram build/types
- se build/tsc verdes: declarar validacao visual/browser FECHADA e encerrar rollout 0A-4C + pos-plano no workspace atual
- se vermelhos: abrir prompt corretivo com o erro bruto do build/tsc como finding objetivo

E. Atualizacao aplicada no handoff
- adicionada secao "2026-04-14 - Pos-plano: Validacao visual/browser executada (roteiro manual) — CONCLUIDA com 1 finding corrigido" em `reports/HANDOFF_SIDEBAR_IMPLEMENTACAO_ATUAL.md`
- secao registra: execucao real, correcoes aplicadas, arquivos alterados (`backend/app.py` e `frontend/components/AppShell.tsx`), validacao pendente (build/tsc), trilho OAuth separado que continua fora deste gate

Estado operacional apos este prompt:
- rollout 0-4 fechado
- pos-plano de toggle salvo no chat fechado
- validacao runtime local sem browser fechada
- roteiro manual de browser preparado e executado
- resultado real do roteiro consolidado aqui e no handoff
- validacao visual/browser AGUARDANDO build+tsc do executor humano para ser formalmente fechada
- trilho OAuth real continua aberto e separado

### Fechamento formal apos reconfirmacao tecnica (2026-04-14)

Reconfirmacao executada no workspace atual apos o resultado do prompt #26:
- `npm run build` em `frontend/`: OK
- `npx tsc --noEmit` em `frontend/`, sequencial apos o build: OK
- backend local saudavel: `GET /health` = 200

Hardening adicional feito apos a validacao humana:
- `frontend/components/WelcomeScreen.tsx`: corrigido hydration mismatch da saudacao inicial
- causa: escolha de greeting no primeiro render com `new Date()` + `Math.random()`
- correcao: greeting inicial estavel no SSR e atualizacao dinamica somente apos mount
- frontend dev local tambem precisou de limpeza de `.next` e restart por artefatos corrompidos do Next; isto foi ruido de ambiente, nao blocker de produto apos restart

Status operacional final desta coordenacao:
- validacao visual/browser: FECHADA
- rollout `0A-4C` + pos-plano: FORMALMENTE ENCERRADO no workspace atual
- nao ha blocker conhecido restante dentro do escopo do sidebar/legal/search rollout
- trilho OAuth real continua aberto e separado do fechamento deste track
