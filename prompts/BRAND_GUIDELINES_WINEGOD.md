# BRAND GUIDELINES — WINEGOD.AI

**Versao:** 1.0
**Data:** 2026-04-12
**Status:** Definido (pendencias listadas no final)

---

## 1. LOGO

- **Formato:** Simbolo independente (favicon/perfil) + texto separado
- **Simbolo:** Coroa de louros (sem uvas, sem videira — louros puros)
- **Texto:** "WineGod" stacked (Wine em cima, God embaixo) + ".ai" centralizado abaixo, com pontos decorativos
- **Tipografia do logo:** Serif bold (estilo Playfair Display Black)
- **Cores do logo:** Preto e branco (monocromatico) — versao colorida a definir
- **Tagline:** "The AI Sommelier"
- **Arquivo base:** `C:\Users\muril\OneDrive\Documentos\WINEGOD\logo\logo_inegod.jpeg`
- **Ferramenta de criacao:** IA (sem designer externo)

### Usos do logo
- Header do app: logo pequeno (40-56px) + texto "winegod.ai"
- Favicon: coroa de louros simplificada (placeholder: "W" em Playfair Display ate vetorizar)
- Perfil de redes sociais: coroa de louros 1:1
- og:image: logo completo sobre fundo vinho (#8B1A4A)

---

## 2. PALETA DE CORES

### Cores principais
| Nome | Hex | Uso |
|------|-----|-----|
| **Background** | `#FFFFFF` | Fundo do app |
| **Surface** | `#F7F7F8` | Cards, areas elevadas |
| **Input** | `#F4F4F5` | Campos de texto |
| **Border** | `#E5E5E5` | Bordas, divisores |
| **Text** | `#111827` | Texto principal |
| **Muted** | `#6B7280` | Texto secundario |
| **Accent (vinho)** | `#8B1A4A` | Botoes, links, destaques, hover |
| **Gold** | `#FFD700` | Estrelas, scores, destaques premium |

### Cores de sistema
| Nome | Hex | Uso |
|------|-----|-----|
| **Sucesso** | `#16A34A` | Confirmacoes, status positivo |
| **Erro** | `#DC2626` | Erros, alertas criticos |
| **Aviso** | `#D97706` | Alertas, avisos |

### Regras
- **Modo:** Somente light na v1. Dark mode futuro.
- **Wine cards:** Fundo claro (mesmo tom do app), NAO mais fundo escuro (#1A1A2E)
- **Gradientes:** Nao usar na v1
- **Design unificado:** Tudo claro, coeso, estilo ChatGPT

---

## 3. TIPOGRAFIA

| Uso | Fonte | Peso | Tamanho referencia |
|-----|-------|------|--------------------|
| **Logo** | Playfair Display | Black (900) | Variavel |
| **Headings** | Inter | Bold (700) | 24-30px |
| **Corpo/UI** | Inter | Regular (400) / Medium (500) | 14-16px |
| **Mensagens do Baco** | Inter | Regular (400) | 14px |
| **Labels/meta** | Inter | Regular (400) | 12px |
| **Timestamps** | Inter | Regular (400) | 11px |

### Regras
- Baco usa a MESMA fonte do corpo (Inter). Diferenciacao e por avatar + posicao.
- Nao usar fontes decorativas/cursivas no UI.

---

## 4. LAYOUT DO APP (estilo ChatGPT)

### Estrutura geral
```
+--------------------------------------------------+
| [=] Logo "winegod.ai"           [Login/Avatar]   |
+--------------------------------------------------+
|                                                    |
|            Saudacoes, alma curiosa!               |
|            Sou Baco — deus do vinho e seu         |
|            sommelier pessoal. Me pergunte sobre   |
|            qualquer vinho, mande uma foto de      |
|            rotulo, ou me diga quanto quer gastar  |
|            que eu resolvo.                        |
|                                                    |
|     [Card 1]  [Card 2]  [Card 3]  [Card 4]       |
|              [Card 5]  [Card 6]                   |
|                                                    |
+--------------------------------------------------+
|  [+] [Pergunte ao Baco sobre vinhos...]    [->]   |
+--------------------------------------------------+
```

### Welcome screen
- **Saudacao do Baco** (estilo Claude): texto quente e pessoal
- **6 cards** (estilo Gemini): 4 em cima + 2 embaixo
- Aparece quando `messages.length === 0`
- Cards sao clicaveis — preenchem o input automaticamente

### 6 Cards definidos
| # | Card | Texto | Icone |
|---|------|-------|-------|
| 1 | Foto de rotulo | "Tire foto de um rotulo" | Camera |
| 2 | Recomendacao por preco | "Me indica um vinho ate R$80" | Copa |
| 3 | Cardapio de restaurante | "Analise um cardapio de vinhos" | Clipboard |
| 4 | Foto de prateleira | "Foto da prateleira do mercado" | Store |
| 5 | Comparar vinhos | "Compare dois vinhos pra mim" | Scale |
| 6 | Lista de vinhos | "Envie uma lista de vinhos" | FileText |

### Sidebar (hamburger ☰)
**v1 — itens:**
1. Novo chat
2. Historico de conversas (agrupado por data)
3. --- separador ---
4. Meus vinhos favoritos
5. --- separador ---
6. Minha conta
7. Plano & creditos
8. --- separador ---
9. Ajuda / FAQ

**Futuros (pos-v1):**
- Minhas listas
- Alertas de preco
- Vinhos ja provados
- Idioma
- Tema (dark mode)
- Compartilhar WineGod
- Termos de uso
- Sobre o WineGod

---

## 5. DESIGN SYSTEM

### WineCard
- Fundo claro (wine-surface #F7F7F8)
- Borda suave (wine-border #E5E5E5)
- Borda vinho (#8B1A4A) no hover
- Sombra leve
- Score com estrela dourada (#FFD700)
- Botoes de acao: outline vinho

### Botoes
- **Primario:** Fundo vinho (#8B1A4A), texto branco
- **Secundario:** Outline vinho (borda vinho, fundo transparente, texto vinho)
- **Hierarquia:** Primario pra acoes principais, secundario pra acoes complementares

### Badges (termos: Avaliacoes, Paridade, Legado, Capilaridade)
- Pill com fundo vinho a 10% opacidade (`#8B1A4A1A`)
- Texto vinho (#8B1A4A)
- Border-radius: full (pill)

### Loading
- Typing dots animados (3 bolinhas vinho pulsando) pra mensagens
- Skeleton screens (cinza pulsando) pra wine cards enquanto carregam

### Icones
- Biblioteca: Lucide React
- Estilo: Outline, 20-24px
- Cor: wine-muted (#6B7280), wine-accent (#8B1A4A) quando ativo

---

## 6. FAVICON E META TAGS

### Favicon
- **Definitivo:** Coroa de louros do logo (quando vetorizado)
- **Placeholder:** Letra "W" em Playfair Display sobre fundo vinho

### Meta tags
```html
<title>winegod.ai — Wine Intelligence, Powered by Gods</title>
<meta name="description" content="Your personal wine god. Find the best wines for your budget. Photo, voice, or text — just ask." />

<meta property="og:title" content="winegod.ai — Wine Intelligence, Powered by Gods" />
<meta property="og:description" content="Your personal wine god. Find the best wines for your budget. Photo, voice, or text — just ask." />
<meta property="og:type" content="website" />
<meta property="og:url" content="https://chat.winegod.ai" />
<meta property="og:image" content="[URL da og:image]" />

<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="winegod.ai — Wine Intelligence, Powered by Gods" />
<meta name="twitter:description" content="Your personal wine god. Find the best wines for your budget. Photo, voice, or text — just ask." />
```

### og:image
- Fundo vinho escuro (#8B1A4A)
- Logo "WineGod.ai" centralizado em branco/dourado
- Dimensao: 1200x630px

---

## 7. ASSETS DE REDES SOCIAIS

### Status: PENDENTE (depende do logo vetorizado)

**Assets necessarios quando logo estiver pronto:**

| Asset | Formato | Pra que |
|-------|---------|--------|
| Foto de perfil | 1:1 (400x400) | Instagram, Twitter/X, TikTok, WhatsApp Business |
| Banner/header | 16:9 (1500x500) | Twitter/X, YouTube, LinkedIn |
| Template de post | 1:1 (1080x1080) | Instagram feed, Facebook |
| Template de Reels/Stories | 9:16 (1080x1920) | Instagram Reels, TikTok, YouTube Shorts |
| og:image | 1200x630 | Preview de link |

### Avatar do Baco (DEFINIDO)
- Arquivo: `C:\winegod-app\assets\baco\v4_final\baco_closeup_recraft_v4pro.png`
- Uso: foto de perfil nas redes, avatar no chat, materiais de marketing

---

## 8. EMAIL TEMPLATES

### Emails na v1
1. **Boas-vindas** — dispara quando usuario cria conta
2. **Creditos esgotados** — dispara quando acabam os creditos do dia

### Estilo visual
- Fundo branco
- Logo no topo (centralizado)
- Texto em Inter
- Botao CTA: fundo vinho (#8B1A4A), texto branco, border-radius
- Assinatura: "— Baco"
- Footer: link pro app + unsubscribe

### Tom
- Baco falando (mesma personalidade do chat)
- NAO corporativo/formal

### Exemplo — Boas-vindas
> **Assunto:** Saudacoes, alma curiosa!
>
> Voce acaba de ganhar acesso ao deus do vinho.
>
> Me mande uma foto de rotulo, pergunte qual vinho combina com seu jantar,
> ou me diga quanto quer gastar — eu resolvo.
>
> [Abrir o WineGod]
>
> — Baco, seu sommelier com milhares de anos de experiencia

### Exemplo — Creditos esgotados
> **Assunto:** Acabamos as tacas por hoje!
>
> Suas mensagens gratuitas acabaram, mas amanha tem mais.
>
> Se nao puder esperar (eu entendo, vinho e urgente),
> o plano Pro libera tudo por menos que uma taca de vinho por mes.
>
> [Ver plano Pro]
>
> — Baco

---

## PENDENCIAS

| Item | Depende de | Prioridade |
|------|-----------|------------|
| Logo vetorizado (SVG/AI) | Vetorizar a logo base em ferramenta profissional | Alta |
| Favicon definitivo | Logo vetorizado | Alta |
| og:image | Logo vetorizado | Media |
| Assets de redes sociais | Logo vetorizado + avatar | Media |
| Dark mode | Implementacao futura | Baixa |
| Templates de email (Brevo) | Implementacao no codigo | Media |
| Emails de upgrade Pro e alerta de preco | Mes 2-3 | Baixa |

---

## REFERENCIAS DE DESIGN

- **Layout geral:** ChatGPT (chat.openai.com)
- **Cards de boas-vindas:** Google Gemini (gemini.google.com)
- **Mensagem de welcome:** Claude (claude.ai)
- **Sidebar:** ChatGPT
- **Cores accent:** Proprio (#8B1A4A vinho + #FFD700 dourado)

---

*Documento gerado em 2026-04-12. Todas as decisoes tomadas pelo fundador durante sessao guiada de identidade visual.*
