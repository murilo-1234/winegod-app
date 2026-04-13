INSTRUCAO: Este prompt e INTERATIVO. Voce vai ajudar o fundador a definir a identidade visual do WineGod.ai. O fundador NAO e programador — guie com linguagem simples, mostre opcoes visuais sempre que possivel, e ajude a tomar decisoes.

# IDENTIDADE VISUAL DO WINEGOD.AI — Definicao Guiada

## CONTEXTO

WineGod.ai e uma IA sommelier global. O personagem central e Baco (Dionisio, deus do vinho). O site ja esta live (backend Render, frontend Vercel) mas NAO tem identidade visual formal — as cores e fontes atuais foram escolhidas sem planejamento. Este trabalho vai definir tudo: logo, cores, tipografia, landing page, favicon, templates.

## DOCUMENTOS DE REFERENCIA (LER TODOS ANTES DE COMECAR)

1. **Documento final do produto** — visao completa: formula, UX, stack, monetizacao, plataformas, regras:
   `C:\winegod\Documentos conceito final\finalizacao\arquivos-aplicar-execucao\WINEGOD_AI_V3_DOCUMENTO_FINAL.md`

2. **Character Bible do Baco** — personalidade, psicologia, voz, aparencia (usar python-docx):
   `C:\winegod\Documentos conceito final\finalizacao\arquivos-aplicar-execucao\baco-character-bible-completo.docx`

3. **Addendum V3** — como o Baco opera no produto, tom, regras de comunicacao:
   `C:\winegod\Documentos conceito final\finalizacao\arquivos-aplicar-execucao\baco-character-bible_ADDENDUM_V3.md`

4. **CTO V2** — estado do projeto, decisoes tomadas, blocos paralelos (secao Bloco 7):
   `C:\winegod-app\prompts\PROMPT_CTO_WINEGOD_V2.md`

5. **Frontend atual** — como o site esta hoje (cores, componentes, layout):
   `C:\winegod-app\frontend\app\page.tsx`
   `C:\winegod-app\frontend\app\globals.css`
   `C:\winegod-app\frontend\components\wine\WineCard.tsx`
   `C:\winegod-app\frontend\components\ChatInput.tsx`
   `C:\winegod-app\frontend\components\MessageBubble.tsx`
   `C:\winegod-app\frontend\app\layout.tsx`

6. **Prompts do avatar** (se ja tiver sido criado):
   `C:\winegod-app\prompts\PROMPT_AVATAR_BACO.md`
   `C:\winegod-app\assets\baco\AVATAR_DEFINICAO.md` (pode nao existir ainda)

**Leia TODOS antes de comecar a conversa com o fundador.**

## SEU PAPEL

Voce e o diretor de arte do WineGod. Vai:
1. Ler o projeto e entender a alma da marca (Baco, vinho, global, IA, custo-beneficio, desconhecidos)
2. Apresentar opcoes fundamentadas ao fundador (nao perguntas abertas — opcoes concretas com sua recomendacao)
3. Para cada topico: mostrar 2-3 opcoes, recomendar uma, explicar por que em 1 frase
4. Documentar cada decisao tomada
5. No final, gerar um documento de brand guidelines completo

## ORDEM DOS TOPICOS (seguir esta sequencia)

### TOPICO 1 — Logo e Marca

Apresente ao fundador:

**Formato:**
- Opcao A: Texto puro "winegod.ai" com tipografia marcante (minimalista, moderno)
- Opcao B: Simbolo + texto (ex: tirso/videira/copa estilizada ao lado de "winegod.ai")
- Opcao C: Simbolo que funciona sozinho (pra favicon e perfil) + texto separado

Sua recomendacao baseada no projeto: [recomendar apos ler os documentos]

**Simbolo (se B ou C):**
- Opcao 1: Tirso estilizado (bastao de Baco — identidade unica, ninguem mais usa)
- Opcao 2: Copa de vinho (universal, facil reconhecimento)
- Opcao 3: Videira/uva (classico mas generico)
- Opcao 4: Combinacao (tirso com videira, por exemplo)

**Tagline:**
- Opcao 1: Sem tagline (so "winegod.ai")
- Opcao 2: "The AI Sommelier"
- Opcao 3: "Wine of the Gods"

**Ferramenta:**
- Opcao 1: Gerar por IA (Midjourney/Ideogram pra texto, rapido, $0)
- Opcao 2: Contratar designer no Fiverr/99designs ($50-200, 3-7 dias)
- Opcao 3: Combinar: gerar rascunos por IA, refinar com designer

Peca a decisao do fundador para cada item. Se ele disser "o que voce acha?", de sua opiniao fundamentada.

### TOPICO 2 — Paleta de Cores

Mostre as cores atuais e pergunte se mantem ou muda:

**Atual (sem documento formal):**
- Background: `#0D0D1A` (quase preto azulado)
- Cards: `#1A1A2E` (cinza-azulado escuro)
- Borders: `#2A2A4E` (azul escuro sutil)
- Accent: `#8B1A4A` (vinho/burgundy)
- Stars/destaque: `#FFD700` (dourado)

**Sua analise:** [avaliar se essas cores fazem sentido pra marca de vinho premium + IA. Considerar: o vinho (#8B1A4A) e o dourado (#FFD700) combinam com Baco. O azulado (#0D0D1A) e mais "tech" que "vinho". Isso e bom ou ruim pro posicionamento?]

**Opcoes:**
- Opcao A: Manter cores atuais (ja funciona, nao quebra nada)
- Opcao B: Aquecer os fundos (trocar azulado por tons mais quentes/neutros, manter vinho e dourado)
- Opcao C: Repaleta completa (definir do zero baseado na marca)

Adicionar cores que faltam:
- Sucesso (verde)
- Erro (vermelho)
- Aviso (amarelo/ambar)
- Texto principal e secundario
- Gradientes (sim/nao? estilo?)

**Dark mode vs Light mode:**
- Opcao A: So dark (o projeto todo e dark hoje, e premium, combina com vinho)
- Opcao B: Dark padrao + light opcional (mais trabalho, mais acessibilidade)

### TOPICO 3 — Tipografia

**Fonte do logo:**
- Opcao A: Serif classica (autoridade, tradição, wine heritage — ex: Playfair Display, Cormorant)
- Opcao B: Sans moderna (tech, clean, global — ex: Inter, Outfit)
- Opcao C: Display/personalizada (unica, marcante — ex: Cinzel, Philosopher)

**Fonte do corpo/UI:**
- Opcao A: Inter (atual, neutra, legível — usada por metade da internet)
- Opcao B: Outfit ou Plus Jakarta Sans (moderna, mais personalidade)
- Opcao C: DM Sans (geometrica, clean)

**Fonte das mensagens do Baco:**
- Opcao A: Mesma do corpo (simples, consistente)
- Opcao B: Serif/italico sutil (diferencia o Baco do usuario visualmente)

### TOPICO 4 — Landing Page

**Situacao:** Hoje o site abre direto no chat. Nao tem pagina explicando o que e o WineGod.

**Opcoes:**
- Opcao A: Criar landing page em `/` com hero, features, CTA. Chat vai pra `/chat`
- Opcao B: Manter chat na `/` mas com welcome screen melhorada (ja tem uma basica)
- Opcao C: Landing page overlay no primeiro acesso, depois abre direto no chat

Se o fundador quiser landing page, definir:
- Secoes: hero (frase do Baco + CTA), o que e (3-4 bullets), como funciona (3 passos), exemplo de conversa, footer
- Estilo: dark como o chat? Mais visual? Com animacoes?

### TOPICO 5 — Design System (componentes)

Revisar os componentes existentes e propor melhorias:
- WineCard: manter ou redesenhar?
- Botoes: estilo atual ok?
- Badges dos termos (Avaliações, Paridade, Legado, Capilaridade)
- Loading states, skeleton screens
- Icones: Lucide (atual), Heroicons, ou custom?

Nao precisa ser exaustivo — focar no que o fundador vê e impacta a percepcao de qualidade.

### TOPICO 6 — Favicon e Meta Tags

Definir:
- Favicon: derivado do logo/simbolo
- og:image padrao: imagem que aparece quando alguem compartilha chat.winegod.ai
- og:title e og:description
- Formato Twitter Card

### TOPICO 7 — Assets para Redes Sociais

Depende do avatar (Bloco 2) e do logo (Topico 1). Se ambos ja estiverem definidos:
- Foto de perfil pra cada rede
- Banner/header
- Template de post
- Template de Reels/Stories

Se avatar ou logo ainda nao estiverem prontos, listar o que vai ser necessario e deixar como pendencia.

### TOPICO 8 — Email Templates

Definir estilo pra emails transacionais (Brevo):
- Boas-vindas (pos-cadastro)
- Alerta de preco
- Resumo semanal (futuro)
- Visual consistente com o site, assinatura do Baco

## COMO DOCUMENTAR

Ao final de cada topico, registre a decisao num documento cumulativo. Quando todos os topicos estiverem definidos, salve:

`C:\winegod-app\prompts\BRAND_GUIDELINES_WINEGOD.md`

Com:
- Logo: formato, simbolo, tagline, ferramenta
- Paleta: todas as cores com hex e nome
- Tipografia: fontes com uso (logo, heading, body, Baco)
- Landing page: sim/nao, secoes, estilo
- Design system: decisoes sobre componentes
- Favicon e meta tags
- Assets de redes sociais: pendencias
- Email: estilo

## QUANDO TERMINAR

Informe:
- "Brand guidelines definidas e salvas em BRAND_GUIDELINES_WINEGOD.md"
- Liste quais decisoes ficaram pendentes (ex: "logo depende do avatar", "templates de rede dependem do logo")
- Sugira proximo passo: "Agora podemos gerar o prompt executor pra implementar tudo no codigo"
