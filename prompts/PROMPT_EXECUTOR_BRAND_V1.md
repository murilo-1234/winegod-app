# EXECUTOR — Redesign Frontend WineGod.ai

## INSTRUCAO PARA O EXECUTOR

Voce vai implementar o redesign do frontend do WineGod.ai. Este prompt contem TODAS as decisoes visuais ja aprovadas pelo fundador. NAO mude nenhuma decisao — apenas implemente exatamente o que esta descrito.

**REGRA CRITICA:** Este prompt esta dividido em 6 FASES. Ao final de CADA fase, voce deve:
1. Mostrar um resumo do que fez (arquivos criados/modificados)
2. Rodar `npm run build` pra verificar erros
3. Dizer "FASE X CONCLUIDA" e PARAR
4. Esperar o fundador validar antes de continuar pra proxima fase

**NAO** pule fases. **NAO** continue sem validacao. O fundador vai consultar o gestor (outro chat) pra aprovar.

---

## CONTEXTO DO PROJETO

- **Repo:** `C:\winegod-app\frontend\` (Next.js 15 + React 19 + Tailwind 3 + TypeScript)
- **Design reference:** ChatGPT (layout, sidebar, input) + Google Gemini (6 cards de boas-vindas) + Claude (mensagem welcome quente)
- **Accent color:** Vinho #8B1A4A + Dourado #FFD700
- **Modo:** Somente LIGHT (fundo branco). Dark mode e futuro.
- **Fonte corpo:** Inter (ja instalada)
- **Fonte logo:** Playfair Display (precisa adicionar)
- **Icones:** Lucide React (precisa instalar)

---

## DOCUMENTOS PARA LER ANTES DE COMECAR

1. **Brand Guidelines completo:** `C:\winegod-app\prompts\BRAND_GUIDELINES_WINEGOD.md`

Leia este arquivo inteiro ANTES de comecar qualquer fase. Ele contem todas as decisoes de cores, fontes, layout, componentes, meta tags.

---

# FASE 1 — Dependencias + Config (Tailwind + Layout + CSS)

## 1.1 — Instalar lucide-react

```bash
cd C:\winegod-app\frontend && npm install lucide-react
```

## 1.2 — Atualizar Tailwind Config

**Arquivo:** `C:\winegod-app\frontend\tailwind.config.ts`

**Estado atual:** Tem cores wine.* basicas. Falta: gold, success, error, warning, fontFamily display.

**Resultado esperado:**
```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        wine: {
          bg: "#ffffff",
          surface: "#f7f7f8",
          user: "#f4f4f4",
          accent: "#8B1A4A",
          input: "#f4f4f5",
          border: "#e5e5e5",
          text: "#111827",
          muted: "#6b7280",
          gold: "#FFD700",
          success: "#16A34A",
          error: "#DC2626",
          warning: "#D97706",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "serif"],
      },
    },
  },
  plugins: [],
};

export default config;
```

## 1.3 — Atualizar Layout (meta tags + Playfair Display)

**Arquivo:** `C:\winegod-app\frontend\app\layout.tsx`

**Estado atual:**
```typescript
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "winegod.ai - Seu sommelier pessoal",
  description: "Converse com Baco, seu sommelier pessoal com milhares de anos de experiencia.",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
```

**Resultado esperado:**
```typescript
import type { Metadata } from "next";
import { Inter, Playfair_Display } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });
const playfair = Playfair_Display({
  subsets: ["latin"],
  weight: ["700", "900"],
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: "winegod.ai — Wine Intelligence, Powered by Gods",
  description: "Your personal wine god. Find the best wines for your budget. Photo, voice, or text — just ask.",
  icons: { icon: "/favicon.ico" },
  openGraph: {
    title: "winegod.ai — Wine Intelligence, Powered by Gods",
    description: "Your personal wine god. Find the best wines for your budget. Photo, voice, or text — just ask.",
    type: "website",
    url: "https://chat.winegod.ai",
    siteName: "winegod.ai",
  },
  twitter: {
    card: "summary_large_image",
    title: "winegod.ai — Wine Intelligence, Powered by Gods",
    description: "Your personal wine god. Find the best wines for your budget. Photo, voice, or text — just ask.",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className={`${inter.className} ${playfair.variable}`}>{children}</body>
    </html>
  );
}
```

## 1.4 — globals.css (NAO alterar)

O arquivo `C:\winegod-app\frontend\app\globals.css` esta correto. NAO mexa nele.

## Validacao da Fase 1

Rodar `npm run build`. Deve compilar sem erros. Lucide-react deve estar no package.json.

**Diga "FASE 1 CONCLUIDA" e PARE. Espere validacao.**

---

# FASE 2 — Sidebar (componente novo)

## 2.1 — Criar Sidebar.tsx

**Criar arquivo:** `C:\winegod-app\frontend\components\Sidebar.tsx`

Sidebar estilo ChatGPT:
- Desliza da esquerda com animacao (transform + transition 200ms)
- Overlay escuro semi-transparente (bg-black/30) cobrindo o resto
- Fecha ao clicar no overlay OU apertar Escape
- Largura: w-72 (288px)
- Fundo: wine-bg (branco)
- Borda direita: wine-border

**Estrutura da sidebar (de cima pra baixo):**

```
+---------------------------+
| winegod.ai (Playfair)  [X]|  <- header com font-display
+---------------------------+
| [+ Novo chat]              |  <- botao primario (bg-wine-accent, texto branco)
+---------------------------+
| HISTORICO                  |  <- label uppercase, text-xs, wine-muted
| Suas conversas aparecerao  |  <- placeholder, text-sm, wine-muted
| aqui.                      |
|                            |
|                   (flex-1) |  <- area scrollavel, ocupa espaco disponivel
+---------------------------+
| ♡ Meus vinhos favoritos   |  <- SidebarLink
|----------------------------|
| ☺ Minha conta              |  <- SidebarLink
| ☐ Plano & creditos (X/Y)  |  <- SidebarLink com contagem se logado
|----------------------------|
| ? Ajuda                    |  <- SidebarLink
+---------------------------+
```

**Props da Sidebar:**
```typescript
interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onNewChat: () => void;
  userName?: string;
  creditsUsed?: number;
  creditsLimit?: number;
  isLoggedIn: boolean;
}
```

**Icones:** Usar SVG inline (NAO lucide aqui — a sidebar e leve, SVG inline evita bundle desnecessario). Icones necessarios:
- X (fechar): duas linhas cruzadas
- Plus (novo chat): cruz
- Heart (favoritos): coracao outline
- User (conta): pessoa
- CreditCard (plano): cartao
- HelpCircle (ajuda): circulo com interrogacao

**Cada SidebarLink:** botao full-width, flex, items-center, gap-3, px-3 py-2.5, rounded-lg, hover:bg-wine-surface, text-sm, text-wine-text. Icone em wine-muted.

**Separadores:** `<div className="border-t border-wine-border my-2" />` entre os grupos.

**Comportamento:**
- `useEffect` escuta tecla Escape pra fechar
- Overlay e `position: fixed, inset-0, z-40`
- Sidebar e `position: fixed, top-0, left-0, h-full, z-50`
- Quando fechada: `transform -translate-x-full`
- Quando aberta: `transform translate-x-0`

## Validacao da Fase 2

Rodar `npm run build`. Deve compilar sem erros. O componente ainda nao aparece no app (sera conectado na Fase 5).

**Diga "FASE 2 CONCLUIDA" e PARE. Espere validacao.**

---

# FASE 3 — WelcomeScreen (redesign completo)

## 3.1 — Reescrever WelcomeScreen.tsx

**Arquivo:** `C:\winegod-app\frontend\components\WelcomeScreen.tsx`

**Estado atual:** Titulo "winegod.ai" + subtitulo + 4 botoes em grid 2x2 com sugestoes de texto.

**Resultado esperado:** Saudacao do Baco (estilo Claude) + 6 cards com icone (estilo Gemini, 4+2).

**Estrutura:**
```
        [B]  <- circulo vinho com "B" (avatar placeholder), 64x64
  
  Saudacoes, alma curiosa!    <- h1, font-display (Playfair), text-2xl, font-bold
  
  Sou Baco — deus do vinho    <- p, text-wine-muted, text-sm, leading-relaxed
  e seu sommelier pessoal...   <- max-w-md, centralizado
  
  [Camera]  [Copa]  [Clipboard]  [Store]    <- 4 cards, grid responsivo
            [Scale]  [FileText]              <- 2 cards centralizados
```

**6 Cards definidos (EXATAMENTE estes, nesta ordem):**

| # | Icone (Lucide) | Titulo do card | Prompt que envia ao clicar |
|---|----------------|----------------|----------------------------|
| 1 | `Camera` | "Foto de rotulo" | "Tire uma foto de um rotulo de vinho e me envie — eu identifico, avalio e digo onde comprar." |
| 2 | `Wine` | "Recomendacao" | "Me indica um vinho tinto ate R$80 com boa nota" |
| 3 | `ClipboardList` | "Cardapio" | "Analise este cardapio de vinhos e me diga qual e o melhor custo-beneficio" |
| 4 | `Store` | "Prateleira" | "Vou te mandar uma foto da prateleira de vinhos do mercado — me diz quais valem a pena" |
| 5 | `Scale` | "Comparar" | "Compare dois vinhos pra mim" |
| 6 | `FileText` | "Lista de vinhos" | "Vou te enviar uma lista de vinhos — analise todos e me diga quais sao os melhores" |

**Layout dos cards:**
- Linha 1 (4 cards): `grid grid-cols-2 sm:grid-cols-4 gap-3`
- Linha 2 (2 cards): `grid grid-cols-2 gap-3` centralizado (max-w metade do container, mx-auto)
- Container: `max-w-xl`

**Estilo de cada card:**
- `flex flex-col items-center gap-2`
- `px-3 py-4 rounded-xl`
- `bg-wine-surface border border-wine-border`
- `hover:border-wine-accent hover:bg-wine-accent/5 transition-colors`
- Icone: 22px, cor wine-accent
- Texto: `text-xs font-medium text-wine-text text-center`

**Texto de saudacao do Baco (EXATAMENTE este):**
> Saudacoes, alma curiosa!

> Sou Baco — deus do vinho e seu sommelier pessoal. Me pergunte sobre qualquer vinho, mande uma foto de rotulo, ou me diga quanto quer gastar que eu resolvo.

**Props:** Mesma interface: `onSuggestionClick: (text: string) => void`

## Validacao da Fase 3

Rodar `npm run build`. Rodar `npm run dev` e verificar visualmente a tela de welcome. Deve mostrar:
- Avatar "B" centralizado
- Saudacao em Playfair Display
- Texto explicativo em Inter
- 6 cards com icones (4 em cima, 2 embaixo centralizados)
- Ao clicar num card, deve enviar a mensagem

Tirar screenshot da tela e mostrar.

**Diga "FASE 3 CONCLUIDA" e PARE. Espere validacao.**

---

# FASE 4 — Wine Cards + Badges (modo claro)

## 4.1 — WineCard.tsx (fundo claro)

**Arquivo:** `C:\winegod-app\frontend\components\wine\WineCard.tsx`

**Trocar TODAS as cores escuras hardcoded por classes Tailwind do tema wine:**

| De (atual) | Para (novo) |
|------------|-------------|
| `bg-[#1A1A2E]` | `bg-wine-surface` |
| `border-[#2A2A4E]` | `border-wine-border` |
| `border-green-700/50` | `border-wine-accent` |
| `bg-[#2A2A4E]` (placeholder imagem) | `bg-wine-input` |

**Container principal — resultado:**
```tsx
<div
  className={`rounded-xl border p-4 w-full max-w-[400px] hover:border-wine-accent transition-colors ${
    highlight ? "border-wine-accent" : "border-wine-border"
  } bg-wine-surface`}
>
```

**Placeholder de imagem — resultado:**
```tsx
<div className="flex-shrink-0 w-14 h-14 rounded-lg bg-wine-input flex items-center justify-center overflow-hidden">
```

**Botoes de acao ("Onde comprar" e "Similares"):** JA estao corretos — usam border-wine-accent e hover:bg-wine-accent/10. NAO alterar.

## 4.2 — TermBadges.tsx (pill vinho)

**Arquivo:** `C:\winegod-app\frontend\components\wine\TermBadges.tsx`

**Trocar a classe do span de:**
```
bg-[#2A2A4E] text-[#C0C0C0]
```

**Para:**
```
bg-wine-accent/10 text-wine-accent
```

**Resultado da linha completa:**
```tsx
className="px-2 py-0.5 text-xs rounded-full bg-wine-accent/10 text-wine-accent"
```

## 4.3 — Criar WineCardSkeleton.tsx (loading)

**Criar arquivo:** `C:\winegod-app\frontend\components\wine\WineCardSkeleton.tsx`

Skeleton que imita a forma do WineCard mas com blocos cinza pulsando (animate-pulse do Tailwind):

```typescript
export function WineCardSkeleton() {
  return (
    <div className="rounded-xl border border-wine-border p-4 w-full max-w-[400px] bg-wine-surface animate-pulse">
      <div className="flex gap-3">
        <div className="flex-shrink-0 w-14 h-14 rounded-lg bg-wine-border" />
        <div className="flex-1 space-y-2 py-1">
          <div className="h-4 bg-wine-border rounded w-3/4" />
          <div className="h-3 bg-wine-border rounded w-1/2" />
          <div className="h-3 bg-wine-border rounded w-2/3" />
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <div className="h-6 bg-wine-border rounded w-16" />
        <div className="h-5 bg-wine-border rounded-full w-20" />
        <div className="h-5 bg-wine-border rounded-full w-16" />
      </div>
      <div className="mt-3 flex items-center justify-between">
        <div className="h-4 bg-wine-border rounded w-20" />
        <div className="h-4 bg-wine-border rounded w-12" />
      </div>
    </div>
  );
}
```

## 4.4 — ScoreBadge.tsx, PriceTag.tsx, QuickButtons.tsx

**NAO alterar estes arquivos.** Ja estao usando as cores corretas (wine-accent, wine-muted, wine-text, #FFD700).

## Validacao da Fase 4

Rodar `npm run build`. Verificar:
- NENHUMA referencia a `#1A1A2E`, `#2A2A4E`, ou `#C0C0C0` restou nos arquivos de componentes wine/
- Buscar com grep: `grep -r "1A1A2E\|2A2A4E\|C0C0C0" C:\winegod-app\frontend\components\`
- Se encontrar qualquer resultado, corrigir antes de continuar

**Diga "FASE 4 CONCLUIDA" e PARE. Espere validacao.**

---

# FASE 5 — Page.tsx (hamburger + sidebar + new chat)

## 5.1 — Atualizar page.tsx

**Arquivo:** `C:\winegod-app\frontend\app\page.tsx`

**Mudancas necessarias:**

### 5.1.1 — Adicionar imports
```typescript
import { Sidebar } from "@/components/Sidebar";
```

### 5.1.2 — Adicionar estados
```typescript
const [sidebarOpen, setSidebarOpen] = useState(false);
```

### 5.1.3 — Adicionar funcao handleNewChat
```typescript
const handleNewChat = useCallback(() => {
  setMessages([]);
  setIsTyping(false);
  setCreditsExhausted(null);
}, []);
```

### 5.1.4 — Alterar o return inteiro

O `<main>` atual precisa ser envolvido num fragment `<>...</>` porque o Sidebar e fixed e fica fora do main.

**Resultado completo do return:**
```tsx
return (
  <>
    <Sidebar
      isOpen={sidebarOpen}
      onClose={() => setSidebarOpen(false)}
      onNewChat={handleNewChat}
      userName={user?.name}
      creditsUsed={creditsUsed}
      creditsLimit={creditsLimit}
      isLoggedIn={!!user}
    />
    <main className="flex flex-col h-dvh pb-16 max-w-3xl mx-auto">
      <header className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-wine-border">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-lg hover:bg-wine-surface transition-colors text-wine-muted"
            aria-label="Abrir menu"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="8" x2="21" y2="8" />
              <line x1="3" y1="16" x2="21" y2="16" />
            </svg>
          </button>
          <img src="/logo.png" alt="WineGod" className="w-10 h-10" />
          <span className="text-wine-text text-sm font-medium tracking-wide">
            winegod.ai
          </span>
        </div>
        {user ? (
          <UserMenu
            user={user}
            creditsUsed={creditsUsed}
            creditsLimit={creditsLimit}
            onLogout={handleLogout}
          />
        ) : (
          <LoginButton compact />
        )}
      </header>

      {messages.length === 0 && !isTyping ? (
        <WelcomeScreen onSuggestionClick={handleSend} />
      ) : (
        <ChatWindow messages={messages} isTyping={isTyping} onSend={handleSend} />
      )}
      {creditsExhausted && (
        <CreditsBanner isLoggedIn={!!user} reason={creditsExhausted} />
      )}
      <ChatInput onSend={handleSend} disabled={isTyping || !!creditsExhausted} />
    </main>
  </>
);
```

**Mudancas no header vs atual:**
1. Adicionou botao hamburger (2 linhas SVG) ANTES do logo
2. Logo de `w-14 h-14` para `w-10 h-10` (um pouco menor pra caber o hamburger)
3. Tudo mais permanece igual

## Validacao da Fase 5

Rodar `npm run build`. Rodar `npm run dev` e verificar:
- Botao hamburger aparece no canto superior esquerdo
- Clicar no hamburger abre a sidebar com animacao da esquerda
- Sidebar mostra: "winegod.ai" (Playfair), botao "Novo chat", historico placeholder, favoritos, conta, plano, ajuda
- Clicar no overlay fecha a sidebar
- Apertar Escape fecha a sidebar
- Clicar em "Novo chat" limpa as mensagens e fecha a sidebar
- Layout geral parece com ChatGPT

Tirar screenshot mostrando: (1) tela com sidebar aberta, (2) tela welcome com cards.

**Diga "FASE 5 CONCLUIDA" e PARE. Espere validacao.**

---

# FASE 6 — Verificacao Final + Limpeza

## 6.1 — Buscar cores escuras remanescentes

Rodar:
```bash
grep -rn "#1A1A2E\|#2A2A4E\|#0D0D1A\|#C0C0C0" C:\winegod-app\frontend\components/ C:\winegod-app\frontend\app/
```

Se encontrar qualquer resultado (exceto em node_modules), corrigir.

## 6.2 — Verificar build

```bash
cd C:\winegod-app\frontend && npm run build
```

Zero erros, zero warnings relevantes.

## 6.3 — Verificacao visual

Abrir `npm run dev` e verificar TODOS os pontos:

- [ ] Header: hamburger + logo (10x10) + "winegod.ai" + login/avatar
- [ ] Sidebar: abre da esquerda, overlay escuro, fecha com X/overlay/Escape
- [ ] Sidebar: "Novo chat" funciona (limpa conversa)
- [ ] Sidebar: itens de menu com icones (favoritos, conta, plano, ajuda)
- [ ] Welcome: avatar "B" centralizado
- [ ] Welcome: "Saudacoes, alma curiosa!" em Playfair Display (serif, negrito)
- [ ] Welcome: texto explicativo do Baco
- [ ] Welcome: 6 cards com icones (4 em cima, 2 embaixo centralizados)
- [ ] Welcome: clicar num card envia mensagem
- [ ] Wine cards: fundo claro (#F7F7F8), NAO escuro
- [ ] Wine cards: borda vinho no hover
- [ ] Wine cards: highlight com borda vinho (nao verde)
- [ ] Badges termos: pill com fundo vinho 10% opacidade, texto vinho
- [ ] Scores: estrela dourada (#FFD700) funciona
- [ ] Precos: texto vinho (#8B1A4A) funciona
- [ ] Quick buttons: outline vinho funciona
- [ ] Meta tags: titulo "winegod.ai — Wine Intelligence, Powered by Gods"
- [ ] Tudo LIGHT mode — nenhum fundo escuro

## 6.4 — Listar tudo que foi feito

Liste todos os arquivos criados e modificados com um breve resumo de cada mudanca.

**Diga "FASE 6 CONCLUIDA — REDESIGN COMPLETO" e PARE.**

---

## ARQUIVOS — RESUMO

| Arquivo | Acao | Fase |
|---------|------|------|
| `frontend/package.json` | Modificado (npm install lucide-react) | 1 |
| `frontend/tailwind.config.ts` | Modificado (cores + fontFamily) | 1 |
| `frontend/app/layout.tsx` | Modificado (Playfair + meta tags) | 1 |
| `frontend/components/Sidebar.tsx` | **CRIADO** | 2 |
| `frontend/components/WelcomeScreen.tsx` | Reescrito (Baco greeting + 6 cards) | 3 |
| `frontend/components/wine/WineCard.tsx` | Modificado (fundo claro + hover) | 4 |
| `frontend/components/wine/TermBadges.tsx` | Modificado (pill vinho) | 4 |
| `frontend/components/wine/WineCardSkeleton.tsx` | **CRIADO** | 4 |
| `frontend/app/page.tsx` | Modificado (hamburger + sidebar + new chat) | 5 |

## NAO ALTERAR (confirmar que estes arquivos ficaram intocados)

- `frontend/app/globals.css`
- `frontend/components/ChatInput.tsx`
- `frontend/components/ChatWindow.tsx`
- `frontend/components/MessageBubble.tsx`
- `frontend/components/TypingIndicator.tsx`
- `frontend/components/ShareButton.tsx`
- `frontend/components/wine/ScoreBadge.tsx`
- `frontend/components/wine/PriceTag.tsx`
- `frontend/components/wine/QuickButtons.tsx`
- `frontend/components/wine/WineComparison.tsx`
- `frontend/components/auth/LoginButton.tsx`
- `frontend/components/auth/UserMenu.tsx`
- `frontend/components/auth/CreditsBanner.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/auth.ts`
- `frontend/lib/types.ts`

---

*Prompt gerado em 12/04/2026. Baseado em BRAND_GUIDELINES_WINEGOD.md aprovado pelo fundador.*
*Gestor: sessao de identidade visual. Executor: esta sessao.*
