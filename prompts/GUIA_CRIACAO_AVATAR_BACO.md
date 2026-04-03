# GUIA: CRIAR O AVATAR DO BACO

## RESUMO

Criar o personagem visual do Baco (rosto, corpo, roupas) usando múltiplas IAs de imagem em paralelo, escolher o melhor, e depois transformar em vídeo.

**Regra:** IMAGEM PRIMEIRO, VÍDEO DEPOIS. Sempre.

---

## FASE 0 — CONDENSAR A CHARACTER BIBLE (30 min)

A Bible tem 100+ páginas. Nenhuma IA de imagem aceita isso. Precisa de um brief visual de 1 parágrafo.

### Como fazer:

1. Abrir Claude.ai (ou ChatGPT, Gemini)
2. Fazer upload do arquivo: `C:\winegod\Documentos conceito final\finalizacao\arquivos-aplicar-execucao\baco-character-bible-completo.docx`
3. Colar este prompt:

```
Leia esta Character Bible inteira. Extraia APENAS a descrição visual do personagem:
- Rosto (formato, expressão, olhos, nariz, boca)
- Cabelo e barba (cor, estilo, comprimento)
- Corpo (altura, porte, postura)
- Roupas e acessórios (o que veste, estilo, cores)
- Idade aparente
- Vibe/energia (como ele se porta, que sensação transmite)

Me dê DOIS outputs:

1. Um parágrafo de 150 palavras em INGLÊS, otimizado para prompt de IA de imagem (Midjourney, DALL-E, Flux)
2. Uma versão de 50 palavras em INGLÊS (para IAs com limite curto)

Estilo visual desejado: concept art premium, semi-realista, cores ricas, iluminação dramática.
O personagem é o deus do vinho Baco — mistura de Jack Sparrow + Hemingway + Dionísio.
```

4. Salvar as 2 versões (150 palavras e 50 palavras) — esse é o **prompt base**

---

## FASE 1 — EXPLORAÇÃO: 5-7 IAs EM PARALELO (1-2 horas)

Pegar o prompt base (150 palavras) e colar nas IAs abaixo. Pedir 4 variações em cada.

### Tier 1 — Prioridade (fazer primeiro)

| IA | Como acessar | O que pedir | Dica |
|---|---|---|---|
| **Midjourney v7** | Discord ou midjourney.com | Colar prompt + `--ar 3:4 --style raw` | Melhor pra personagens estilizados. Usar `--cref` depois pra consistência |
| **DALL-E / gpt-image-1** | ChatGPT Plus ou API OpenAI | Colar prompt direto | Melhor pra seguir instrução complexa à risca |
| **Flux 1.1 Ultra** | replicate.com ou bfl.ml | Colar prompt | Melhor realismo de rosto |
| **Google Imagen 4** | Gemini (gemini.google.com) | "Gere uma imagem: [prompt]" | Grátis, qualidade alta |
| **Ideogram 3.0** | ideogram.ai | Colar prompt, escolher estilo "Design" | Bom pra estilo artístico |

### Tier 2 — Se quiser mais opções

| IA | Como acessar | O que pedir |
|---|---|---|
| **Leonardo AI** | leonardo.ai | Usar "Character Reference" pra manter consistência |
| **Recraft V3** | recraft.ai | Bom pra ilustração/concept art |
| **Stability AI (SD3.5)** | stability.ai | Controle total, mais técnico |
| **Seedream (ByteDance)** | Via Replicate | Rostos realistas, expressões naturais |
| **Kling AI** | kling.ai | Faz imagem E vídeo (2 em 1) |

### O que pedir em cada IA:

```
[Colar o prompt base de 150 palavras]

Generate 4 variations:
1. Front-facing portrait (head and shoulders)
2. Full body standing pose
3. Three-quarter view, holding a wine glass
4. Dramatic lighting, moody atmosphere
```

---

## FASE 2 — REFINAMENTO (1 dia)

Após ter 20-30 imagens de várias IAs:

1. **Escolher os 3-5 melhores** — os que mais parecem o Baco da Bible
2. **Pegar o melhor** e gerar variações na MESMA IA:
   - Diferentes ângulos (frente, perfil, 3/4)
   - Diferentes expressões (sorrindo, pensativo, provocador)
   - Diferentes roupas (casual, formal, fantasia)
   - Close-up do rosto (pra avatar do chat)
3. **Travar o design final:**
   - 1 imagem de rosto (avatar do chat)
   - 1 imagem de corpo inteiro (landing page)
   - 1 imagem dramática (OG image / share)

### Ferramentas de consistência:
- **Midjourney:** usar `--cref [URL da imagem escolhida]` pra manter o mesmo rosto
- **Leonardo AI:** usar "Character Reference" (upload da imagem)
- **Flux:** usar IP-Adapter no Replicate

---

## FASE 3 — VÍDEO (após travar imagem)

Pegar a imagem final do Baco e transformar em vídeo curto (5-10 segundos).

### IAs de Image-to-Video (ordenadas por qualidade):

| IA | Site | Melhor pra | Preço |
|---|---|---|---|
| **Kling AI** | kling.ai | Personagem falando/gesticulando | Grátis (limite) |
| **Runway Gen-3 Alpha** | runwayml.com | Qualidade máxima, controle de câmera | $12/mês |
| **Pika 2.0** | pika.art | Estilo artístico, movimentos suaves | Grátis (limite) |
| **Minimax / Hailuo** | hailuoai.video | Grátis, surpreendentemente bom | Grátis |
| **Veo 2 (Google)** | Via Vertex AI | Qualidade alta | Acesso limitado |
| **Luma Dream Machine** | lumalabs.ai | Movimentos naturais | Grátis (limite) |

### O que pedir no vídeo:

```
[Upload da imagem do Baco]

Animate this character: he slowly raises a wine glass, smiles knowingly, 
and gives a slight nod. Camera slowly zooms in. Warm dramatic lighting. 
5 seconds.
```

### Usos do vídeo:
- Welcome screen do chat (Baco te recebe)
- Loading animation
- Landing page winegod.ai
- Posts em redes sociais

---

## CHECKLIST FINAL

- [ ] Fase 0: Condensar Bible → prompt visual (150 + 50 palavras)
- [ ] Fase 1: Colar em 5-7 IAs, gerar 4 variações cada
- [ ] Fase 1: Escolher os 5 melhores resultados
- [ ] Fase 2: Refinar o melhor (ângulos, expressões, roupas)
- [ ] Fase 2: Travar design final (avatar, corpo, OG image)
- [ ] Fase 3: Image-to-video (Kling, Runway ou Minimax)
- [ ] Aplicar: avatar no chat, welcome screen, favicon, OG image, landing page

---

## CUSTO ESTIMADO

| Item | Custo |
|---|---|
| Condensar Bible (Claude/ChatGPT) | Grátis (assinatura existente) |
| Midjourney (1 mês) | ~$10 |
| Imagens nas outras IAs | Grátis (tiers gratuitos) |
| Vídeo (Kling/Minimax gratuito) | Grátis |
| Runway (se quiser qualidade máxima) | ~$12 |
| **Total** | **$10-22** |

---

## ONDE APLICAR O BACO NO PRODUTO

| Local | Imagem necessária | Tamanho |
|---|---|---|
| Avatar no chat (ao lado das mensagens) | Rosto circular | 64x64 / 128x128 |
| Welcome Screen | Corpo inteiro ou meio corpo | 400x600 |
| Favicon | Rosto simplificado | 32x32 |
| OG Image (preview de link) | Baco + logo winegod.ai | 1200x630 |
| Landing page | Corpo inteiro, dramático | 800x1200 |
| Vídeo welcome | Animação 5-10s | 720p ou 1080p |
