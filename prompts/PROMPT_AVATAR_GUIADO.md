INSTRUCAO: Este prompt e INTERATIVO. Voce vai ajudar o fundador a criar o avatar visual do personagem Baco. O fundador NAO e programador — guie com linguagem simples. Sua funcao e preparar tudo, gerar o que for possivel automaticamente, e guiar o fundador no que exigir plataformas externas.

# AVATAR DO BACO — Criacao Guiada

## CONTEXTO

WineGod.ai e uma IA sommelier global. O personagem central e Baco — Dionisio (deus grego do vinho) no mundo moderno. Personalidade: Jack Sparrow + Hemingway + Lyonel Baratheon. Precisa de um visual definitivo para: foto de perfil, redes sociais, videos com IA, e presenca no chat.

## DOCUMENTOS DE REFERENCIA (LER TODOS ANTES DE COMECAR)

1. **Character Bible** — quem o Baco E (personalidade, psicologia, voz, aparencia fisica, presenca). Usar python-docx pra ler:
   `C:\winegod\Documentos conceito final\finalizacao\arquivos-aplicar-execucao\baco-character-bible-completo.docx`

2. **Addendum V3** — como o Baco opera dentro do produto (tom, regras, idiomas):
   `C:\winegod\Documentos conceito final\finalizacao\arquivos-aplicar-execucao\baco-character-bible_ADDENDUM_V3.md`

3. **Prompts de imagem prontos** — descricao visual compilada + prompts master pra IAs de imagem:
   `C:\winegod-app\prompts\PROMPT_AVATAR_BACO.md`

A secao 2.3 da Character Bible (Aparencia e Presenca Fisica) e a mais importante pra este trabalho. Leia ela com atencao especial.

## SEU PAPEL

1. Apresentar ao fundador as opcoes visuais (gaps que precisam de decisao)
2. Gerar imagens diretamente se tiver acesso a API de geracao de imagem
3. Se nao tiver API, preparar os prompts otimizados pra cada plataforma
4. Guiar o fundador em cada plataforma externa
5. Ajudar a comparar resultados e refinar o escolhido

## PASSO 1 — DECISOES VISUAIS (perguntar ao fundador)

Antes de gerar qualquer imagem, confirme com o fundador estes gaps da Character Bible:

**Apresente assim:**
"Antes de criar o Baco, preciso de algumas decisoes suas. Vou sugerir opcoes pra cada uma — me diz se concorda ou quer mudar."

| Atributo | Sugestao | Alternativas |
|---|---|---|
| Cabelo | Escuro, ondulado, ate os ombros, levemente selvagem | Mais curto (acima das orelhas)? Mais claro (castanho medio)? Liso? |
| Barba | Cheia mas nao longa, parece cuidada e descuidada ao mesmo tempo | Mais aparada? Mais longa/viking? Cavanhaque? |
| Olhos | Ambar-dourado com brilho intenso | Castanho escuro? Verde? Azul? |
| Pele | Oliva mediterranea, bronzeada | Mais clara? Mais escura? |
| Roupa | Camisa de linho vinho/burgundy aberta no peito, aneis de ouro, colar com videira | Jaqueta de couro? Blazer? Mais casual (camiseta)? |
| Cenario | Adega com barris e luz dourada | Vinhedo ao por do sol? Bar sofisticado? Templo grego em ruinas? |

**Aceite a resposta do fundador e ajuste os prompts de acordo.**

## PASSO 2 — GERAR OU PREPARAR IMAGENS

### Opcao A: Se tiver acesso a geracao de imagem (Gemini, etc.)
- Use a API disponivel pra gerar 4 variacoes do retrato (Versao 1 do PROMPT_AVATAR_BACO.md)
- Mostre ao fundador e peca pra escolher a melhor
- Refine a escolhida com variacoes

### Opcao B: Se NAO tiver acesso a geracao de imagem
Prepare os prompts otimizados pra cada plataforma e guie o fundador:

**Midjourney (melhor pra rostos realistas):**
1. Diga ao fundador: "Abra o Discord e va no canal do Midjourney (ou midjourney.com)"
2. Forneca o prompt adaptado com parametros: `--ar 1:1 --s 250 --v 6.1`
3. Peca pra ele colar e enviar
4. Peca pra ele te mostrar os resultados (descrever ou colar link)

**DALL-E 3:**
1. "Abra o ChatGPT e peca pra gerar uma imagem"
2. Forneca o prompt adaptado (DALL-E prefere linguagem natural, sem parametros tecnicos)
3. Peca os resultados

**Ideogram 2.0:**
1. "Abra ideogram.ai"
2. Forneca o prompt
3. Bom se quiser texto "winegod.ai" na imagem

**Flux Pro:**
1. "Abra fal.ai e busque Flux Pro"
2. Forneca o prompt
3. Excelente fotorealismo

**Leonardo Phoenix:**
1. "Abra app.leonardo.ai"
2. Use preset "Cinematic" ou "Photography"
3. Forneca o prompt

**Instrucao:** Gere em TODAS as plataformas que o fundador tiver acesso. Quanto mais opcoes, melhor a comparacao.

## PASSO 3 — COMPARAR E ESCOLHER

Pergunte ao fundador:
- "Qual das imagens mais parece o Baco que voce imagina?"
- "O que voce mudaria nessa imagem?"

Se o fundador quiser ajustes:
- Modifique o prompt (mais/menos barba, roupa diferente, expressao, cenario)
- Gere novamente na plataforma que teve o melhor resultado

## PASSO 4 — PACK COMPLETO

Com o rosto definido, gere na MESMA plataforma:
1. **Foto de perfil** (1:1, close no rosto) — pra redes sociais e chat
2. **Banner** (16:9, corpo inteiro) — pra YouTube, Twitter
3. **Thumbnail Reels** (9:16, acao/danca) — pra Instagram, TikTok
4. **Fundo transparente** (se a plataforma suportar) — pra overlays

Adapte os prompts (Versao 1, 2 e 3 do PROMPT_AVATAR_BACO.md) com os detalhes aprovados.

## PASSO 5 — ORGANIZAR E SALVAR

Crie a pasta e o documento de referencia:

```
C:\winegod-app\assets\baco\
  baco_perfil_1x1.png
  baco_banner_16x9.png
  baco_reels_9x16.png
  baco_referencia.png       (imagem master)
```

Crie `C:\winegod-app\assets\baco\AVATAR_DEFINICAO.md` com:
- Qual IA gerou a imagem final
- Qual prompt exato foi usado
- Quais decisoes visuais foram tomadas (cabelo, olhos, pele, roupa)
- Data da criacao

## PASSO 6 — TESTE DE VIDEO (opcional, se o fundador quiser)

1. "Quer testar como o Baco fica falando num video?"
2. Se sim: "Abra heygen.com, crie conta gratuita, suba a foto do rosto do Baco"
3. Use como texto de teste: "Esse vinho? E roubo. O cara do lado esta pagando cinco vezes mais num rotulo famoso que nao e melhor que esse aqui."
4. Se o video ficar bom → avatar oficial definido

## QUANDO TERMINAR

Informe:
- "Avatar do Baco definido. Imagens salvas em C:\winegod-app\assets\baco\. Documentacao em AVATAR_DEFINICAO.md."
- "Proximo passo: desbloquear Bloco 5 (agent_content.py — pipeline de videos automaticos)."
