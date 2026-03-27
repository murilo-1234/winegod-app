# CHAT A — Frontend Next.js (Tela de Chat do WineGod)

## O QUE E O WINEGOD
WineGod.ai e uma IA sommelier global. O usuario conversa com "Baco" (um personagem — deus do vinho) pelo chat. Baco responde sobre vinhos, recomenda, compara. O site e chat.winegod.ai.

## SUA TAREFA
Criar o frontend do chat em Next.js. Tela de chat escura (tema vinho/roxo), mobile-first, funcional no browser. NAO precisa de backend real ainda — use um mock que simula resposta do Baco.

## ONDE CRIAR
Diretorio: `C:\winegod-app\frontend\`

Se o diretorio nao existir, crie. NAO toque em nada fora desta pasta.

## ESTRUTURA A CRIAR

```
C:\winegod-app\frontend\
  package.json
  next.config.ts
  tsconfig.json
  tailwind.config.ts
  postcss.config.mjs
  .env.local              ← NEXT_PUBLIC_API_URL=http://localhost:5000
  .gitignore
  public/
    favicon.ico           ← pode ser placeholder
  app/
    layout.tsx            ← layout base, font, metadata
    page.tsx              ← tela principal = chat
    globals.css           ← tema escuro base
  components/
    ChatWindow.tsx        ← container com scroll das mensagens
    MessageBubble.tsx     ← bolha (user a direita, Baco a esquerda)
    ChatInput.tsx         ← campo de texto + botao enviar
    TypingIndicator.tsx   ← "Baco esta digitando..." (3 pontinhos)
    WelcomeScreen.tsx     ← tela inicial antes da primeira mensagem
  lib/
    api.ts                ← funcao sendMessage(text) que chama o backend
    types.ts              ← tipos TypeScript (Message, etc.)
```

## ESPECIFICACOES DO VISUAL

### Tema de cores (OBRIGATORIO)
- Background principal: #0D0D0D (quase preto)
- Background secundario (bolhas do Baco): #1A1A2E
- Background bolha do usuario: #4A1942 (roxo escuro/vinho)
- Texto principal: #E0E0E0
- Texto secundario: #888888
- Accent/destaque: #8B1A4A (vinho)
- Input background: #1A1A1A
- Input border: #333333, focus: #8B1A4A
- Nao usar branco puro em nada

### Layout
- Mobile-first (max-width 100% no celular, max-width 768px centralizado no desktop)
- Chat ocupa tela inteira (100vh)
- Input fixo no rodape
- Mensagens rolam pra cima
- Auto-scroll pra ultima mensagem

### Tela de boas-vindas (WelcomeScreen)
Aparece antes da primeira mensagem. Contem:
- Logo/titulo "winegod.ai" (minusculo, sempre)
- Subtitulo: "Seu sommelier pessoal com milhares de anos de experiencia"
- 3-4 sugestoes clicaveis:
  - "Qual vinho combina com pizza?"
  - "Me indica um tinto ate R$80"
  - "O que e terroir?"
  - "Cabernet ou Merlot?"
- Ao clicar numa sugestao, envia como mensagem

### Bolhas de mensagem (MessageBubble)
- Baco (esquerda): background #1A1A2E, borda arredondada, icone pequeno do Baco (pode ser emoji de uva por enquanto)
- Usuario (direita): background #4A1942, borda arredondada
- Timestamp discreto embaixo de cada mensagem (ex: "14:32")
- Suportar markdown basico na resposta do Baco (negrito, italico, listas)

### Input (ChatInput)
- Campo de texto com placeholder "Pergunte ao Baco sobre vinhos..."
- Botao enviar (icone de seta ou aviao)
- Enter envia, Shift+Enter pula linha
- Desabilita input enquanto Baco "digita"
- Icone de camera/foto ao lado (desabilitado por enquanto, so visual)

### Typing Indicator
- Aparece quando esperando resposta
- 3 pontinhos animados com texto "Baco esta pensando..."

## MOCK DO BACKEND (TEMPORARIO)

No arquivo `lib/api.ts`, crie uma funcao que SIMULA a resposta do backend:

```typescript
const MOCK_RESPONSES = [
  "Ah, que pergunta magnifica! Deixa eu te contar sobre esse nectar...",
  "Pelo Olimpo! Voce tem bom gosto. Esse vinho e transcendente.",
  "Olha, eu ja bebi muita coisa em 4 mil anos, mas isso aqui me surpreende.",
  "Sabe o que combina com isso? Uma boa conversa e companhia. E mais vinho.",
  "Nota 4.18 — os avaliadores mais experientes concordam que e excepcional pra faixa de preco."
];

export async function sendMessage(message: string): Promise<string> {
  // Simula delay de 1-2 segundos
  await new Promise(r => setTimeout(r, 1000 + Math.random() * 1000));

  // Quando o backend estiver pronto, trocar por:
  // const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/chat`, {
  //   method: 'POST',
  //   headers: { 'Content-Type': 'application/json' },
  //   body: JSON.stringify({ message, session_id: getSessionId() })
  // });
  // return (await res.json()).response;

  return MOCK_RESPONSES[Math.floor(Math.random() * MOCK_RESPONSES.length)];
}
```

Quando o Chat B (backend) estiver pronto, basta descomentar o fetch real e comentar o mock.

## O QUE NAO FAZER
- NAO instalar bibliotecas de UI pesadas (shadcn, chakra, material). Tailwind puro
- NAO criar login, auth, ou paginas extras. So o chat
- NAO criar rotas de API no Next.js. O backend e Flask separado
- NAO usar "use server" ou server actions. Tudo client-side
- NAO tocar em nada fora de `C:\winegod-app\frontend\`
- NAO fazer git init, commit ou push (o CTO faz isso depois)
- NAO usar emojis no codigo

## COMO TESTAR
```bash
cd C:\winegod-app\frontend
npm install
npm run dev
```
Abrir http://localhost:3000 no browser. Deve:
1. Mostrar tela de boas-vindas com sugestoes
2. Clicar numa sugestao → envia mensagem
3. Aparecer "Baco esta pensando..." por 1-2 seg
4. Resposta mock aparece na bolha do Baco
5. Funcionar no celular (redimensionar browser pra testar)

## ENTREGAVEL
Pasta `C:\winegod-app\frontend\` com projeto Next.js funcional. Tela de chat bonita, escura, mobile-first, com mock de respostas.
