# Roteiro Manual — Validacao Visual/Browser do Sidebar

Ultima atualizacao: 2026-04-14

Este roteiro valida os fluxos guest e os atalhos do sidebar em um browser real. **Ele NAO substitui nenhuma etapa automatica — ele e o passo que o runtime local sem browser nao consegue cobrir.**

## Pre-requisitos

- backend rodando: `cd backend && python app.py` (porta 5000, confirmar `GET /health` retorna 200)
- frontend dev rodando: `cd frontend && npm run dev` (porta 3000 ou 3001)
- browser aberto em `http://localhost:<porta>`
- storage limpo: abrir em aba anonima OU em DevTools limpar `localStorage` e `sessionStorage` antes de comecar
- NAO estar logado (este roteiro e guest-only)

## Convencao

Em cada passo:
- **URL** = rota a visitar antes da acao
- **Acao** = o que fazer
- **Esperado** = o que deve acontecer

Em `Windows`/`Linux` use `Ctrl`; em `Mac` use `Cmd`.

---

## Passos

### 1. Home renderiza shell
- **URL:** `/`
- **Acao:** abrir a rota
- **Esperado:** logo no header; no desktop, strip vertical esquerda com icones Menu (hamburger) / Plus / Search / separador / Wine / User / CreditCard / (spacer) / Ajuda; centro mostra WelcomeScreen do Baco com input de chat embaixo

### 2. Abrir sidebar expandido no desktop
- **URL:** `/`
- **Acao:** clicar no icone Menu (hamburger, topo do strip)
- **Esperado:** painel lateral desliza da esquerda; titulo "winegod.ai"; Novo chat, Buscar (com badge `Ctrl+K`), Meus vinhos favoritos, Minha conta, Plano & creditos, Ajuda; secao Historico mostra "Entre com sua conta para ver seu historico."

### 3. Fechar sidebar com click no overlay
- **URL:** `/` (sidebar ainda aberto)
- **Acao:** clicar na area escura fora do painel
- **Esperado:** sidebar fecha

### 4. Abrir SearchModal com `Ctrl+K`
- **URL:** `/`
- **Acao:** garantir que o foco NAO esta em input; pressionar `Ctrl+K`
- **Esperado:** modal aparece centralizado, overlay escuro cobre o resto; input esta com foco, placeholder "Buscar conversas..."; badge `Esc` a direita; corpo mostra "Digite para buscar em suas conversas."

### 5. Fechar SearchModal com `Escape`
- **URL:** `/` (modal aberto)
- **Acao:** pressionar `Escape`
- **Esperado:** modal fecha instantaneamente

### 6. Abrir SearchModal por click
- **URL:** `/`
- **Acao:** clicar no icone Search do collapsed strip
- **Esperado:** mesmo modal do passo 4 abre

### 7. Fechar SearchModal com click no overlay
- **URL:** `/` (modal aberto)
- **Acao:** clicar na area escura fora do modal
- **Esperado:** modal fecha

### 8. Guard do atalho dentro do input
- **URL:** `/`
- **Acao:** clicar no input do chat (abaixo da WelcomeScreen) para dar foco; pressionar `Ctrl+K`
- **Esperado:** **modal NAO abre**; o `K` aparece como caractere normal no input, OU o atalho e ignorado; sem reacao visual do modal

### 9. Estado empty + CTA no SearchModal (guest)
- **URL:** `/`
- **Acao:** abrir modal (click Search ou `Ctrl+K`); digitar algo improvavel como `xyz123teste`
- **Esperado:** apos ~300ms (debounce), corpo mostra "Nenhum resultado encontrado."; no rodape do modal, botao "Perguntar ao Baco sobre "xyz123teste"" com icone de mensagem

### 10. CTA inicia nova conversa guest
- **URL:** `/` (modal aberto no passo 9)
- **Acao:** clicar no botao "Perguntar ao Baco..."
- **Esperado:** modal fecha; home sai da WelcomeScreen e entra em modo chat; "xyz123teste" aparece como primeira mensagem do usuario; Baco comeca a responder (streaming) — pode demorar alguns segundos; contador de creditos no UserMenu/header decresce de 5 para 4

### 11. Paginas guest protegidas
- **URL:** `/favoritos`, depois `/conta`, depois `/plano`
- **Acao:** visitar cada uma (pode usar links do sidebar expandido)
- **Esperado:**
  - `/favoritos`: icone Heart + "Entre para ver seus favoritos" + botao Entrar
  - `/conta`: icone User + "Entre para ver sua conta" + botao Entrar
  - `/plano`: comparacao guest 5 / user free 15 creditos + CTA de login

### 12. `/data-deletion` guest — fluxo de exclusao desativado
- **URL:** `/data-deletion`
- **Acao:** abrir a rota sem estar logado
- **Esperado:** pagina legal renderiza com secoes "O que e excluido" listando historico de conversas e favoritos; na secao "Excluir sua conta" aparece apenas o texto orientando login + email `privacy@winegod.ai`; **NAO aparece** o botao vermelho "Excluir minha conta"

---

## Template de anotacao de falha

Para cada passo que falhar, copie e preencha:

```
Passo: [numero]
URL: [rota]
Navegador + versao: [ex: Chrome 120 Windows]
Comportamento observado: [o que aconteceu]
Comportamento esperado: [o que deveria]
Reproducibilidade: [sempre / intermitente / uma vez so]
Console/Network: [erros visiveis em DevTools, se houver]
Screenshot: [anexar se possivel]
```

## Consolidacao

Ao terminar o roteiro:
- se todos os 12 passos passaram: marcar validacao visual/browser como concluida no handoff
- se algum passo falhou: abrir uma rodada de correcao com o finding preenchido acima; NAO marcar como concluido

## Fora deste roteiro (requer auth real)

Este roteiro nao cobre — propositalmente — fluxos que exigem OAuth real:
- login via Google / Facebook / Apple / Microsoft
- historico de conversas listado no sidebar
- toggle de salvar conversa (Heart no header)
- `/favoritos` com lista populada
- exclusao de conta real
- migracao guest -> logado (abrir roteiro separado apos OAuth configurado)

Para esses fluxos, execute apos ter credenciais OAuth configuradas em ambiente real (staging ou producao).
