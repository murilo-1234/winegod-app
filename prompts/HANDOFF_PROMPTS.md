# HANDOFF — Problemas de Prompt: P1, P2, P3, P4, P11, P12, P13

## Quem é você neste chat
Você é um prompt engineer sênior otimizando os prompts do WineGod.ai (Gemini OCR + Baco system prompt). Sua missão é **diagnosticar os problemas, propor novos prompts e explicar as mudanças**. NÃO implemente nada — entregue os prompts revisados como proposta.

---

## O que é o WineGod.ai

WineGod.ai é uma IA sommelier. O fluxo quando o usuário manda uma foto:

```
Foto → Gemini 2.5 Flash (OCR) → extrai vinhos → Claude Haiku (Baco) → resposta ao usuário
```

### Stack
- **OCR**: Google Gemini 2.5 Flash — classifica fotos e extrai dados de vinhos
- **Chat**: Claude Haiku 4.5 — personagem "Baco" (deus do vinho) responde ao usuário
- **Backend**: Python 3.11, Flask (`C:\winegod-app\backend\`)
- **Banco**: PostgreSQL 16 (~1.72M vinhos)

---

## OS 7 PROBLEMAS DE PROMPT

### P1 — OCR classifica TUDO como "shelf" (CRÍTICO)

**O que acontece:** Testamos 24 fotos reais de supermercado. **0 de 24** foram classificadas como "label". Todas viraram "shelf", incluindo close-ups de 1-2 garrafas.

**Por que importa:** Quando é "label", o Gemini extrai dados ricos:
```json
{"type": "label", "name": "...", "producer": "...", "vintage": "...", "region": "...", "grape": "..."}
```
Quando é "shelf", só extrai nome e preço:
```json
{"type": "shelf", "wines": [{"name": "...", "price": "..."}], "total_visible": N}
```

**Exemplos:**
- Foto 2: Close-up de 4-5 garrafas de Pena Vermelha Reserva → classificou "shelf", total_visible=12
- Foto 4: Close-up de 3 garrafas Contada 1926 → classificou "shelf", total_visible=4
- Foto 6: Close-up de D'Eugenio Tinto → classificou "shelf", total_visible=14
- Foto 10: 2 garrafas focadas (Finca Las Moras + Trivento) → classificou "shelf", total_visible=3

**Prompt atual:** (arquivo `C:\winegod-app\backend\tools\media.py`, linhas 29-55)
```
Analyze this image and determine what it contains. Classify as ONE of:
- "label": a wine bottle label or close-up of a single wine bottle
- "screenshot": a screenshot or screen capture showing wine info
- "shelf": a photo of a wine shelf, display, or multiple bottles together
- "not_wine": the image does not contain wine-related content
...
```

**Causa provável:** O prompt diz "label = close-up of a **single** wine bottle". Se há 2+ garrafas (mesmo iguais), vai pra "shelf".

---

### P2 — Preços lidos errados pela OCR

**Exemplos:**
- Foto 9: She Noir → OCR leu R$109,99 / Real era **R$189,99**
- Foto 16: Perez Cruz Grenache → OCR leu R$109,99 / Real era **R$183,99**

**Causa provável:** Etiquetas de supermercado BR têm formato complexo:
```
PREÇO R$T 1 L R$146.60
VG SHE'S ALWAYS 750ML PINOT NOIR
R$ 189,99
```
O Gemini pode pegar o "preço por litro" em vez do preço da garrafa.

---

### P3 — total_visible absurdamente inflado

**Exemplos:**
- Foto 2 (close-up 4-5 garrafas): total_visible = **12**
- Foto 11 (prateleira normal): total_visible = **120**
- Foto 12 (prateleira grande): total_visible = **280**

**Causa:** O Gemini conta garrafas físicas (incluindo repetições do mesmo vinho) em vez de tipos/marcas diferentes.

**Impacto:** Baco disse ao usuário "vi ~15 outras garrafas" quando a foto tinha 2-3 tipos.

---

### P4 — Typos nos nomes dos vinhos

**Exemplos:**
- "Trivent" → deveria ser "Trivento" (foto 10)
- "PONTGRAS" → deveria ser "MONTGRAS" (foto 20)
- "Chateau Ot Noir" → lixo de OCR (foto 7)

**Impacto:** Busca no banco pode falhar. O search_wine usa pg_trgm (fuzzy) mas typos grandes ainda atrapalham.

---

### P11 — Baco exagera informações

**Exemplos:**
- Foto 9: disse "~15 outras garrafas que não consegui ler" — foto tinha 2-3 tipos
- Usa o total_visible inflado do Gemini como base para exagerar

**Prompt relevante:** `C:\winegod-app\backend\prompts\baco_system.py`

---

### P12 — OCR troca nome de uva

**Exemplo:** Foto 13: OCR identificou "Chaski Perez Cruz **Petit Sirah**" mas o vinho real é "Perez Cruz Petit **Verdot** Chaski". Sirah e Verdot são uvas completamente diferentes.

---

### P13 — Preço da foto não é repassado ao Baco

**O que acontece:** A OCR lê o preço (R$89,99 da etiqueta do Pena Vermelha). Mas na resposta, Baco citou preços de Portugal (€12,60) e Canadá (CAD$24,99) em vez do preço que o usuário está vendo na prateleira.

**Causa:** O preço da OCR é passado como contexto, mas Baco não foi instruído a priorizar esse preço.

---

## COMO O CONTEXTO É CONSTRUÍDO

Quando a OCR retorna um "shelf", o backend monta este contexto para o Baco:

```python
# Em _handle_shelf() no media.py
# Retorna um dict com:
# - description: "Vinhos identificados na prateleira: 1. Nome — Preço, 2. Nome — Preço"
# - wines: lista dos vinhos
# - ocr_result: resultado raw do Gemini
```

Este contexto é prepended à mensagem do usuário antes de enviar ao Claude Haiku.

---

## RESULTADOS OCR COMPLETOS DAS 24 FOTOS

Estes são os resultados raw do Gemini para cada foto (tipo, vinhos identificados, preços, total_visible):

| Foto | Tipo | Vinhos identificados | Preços | total_visible | Tempo |
|------|------|---------------------|--------|---------------|-------|
| 1 | shelf | Luigi Bosca, Mosquita Muerta, La Linda + outros | R$79-499 | N/A | 21.2s |
| 2 | shelf | Pena Vermelha Reserva | R$89.99 ✓ | 12 | 5.5s |
| 3 | shelf | Contada 1926 Chianti, Contada 1926 Primitivo | R$59.99 ✓ | 10 | 6.9s |
| 4 | shelf | Contada 1926 Chianti (x2), Primitivo | null | 4 | 5.4s |
| 5 | shelf | D. Eugenio Crianza, D. Eugenio Tinto, Cuatro Vientos | R$41-54 ✓ | 45 | 12.3s |
| 6 | shelf | D. EUGENIO Tinto La Mancha | R$41.99 ✓ | 14 | 6.4s |
| 7 | shelf | Pinot Noir, Les Dauphins, Contada 1926 Riserva/Classico etc | R$69-139 | muitos | 42.8s |
| 8 | shelf | Ardeche Syrah, Les Dauphins, Contada 1926, JP Chenet etc | R$69-139 | muitos | 17.3s |
| 9 | shelf | She's Always Noir Pinot Noir, Freixenet 0.0% Red Blend | **R$109.99 ERRADO**, R$129.99 | 12 | 5.7s |
| 10 | shelf | Finca Las Moras CS 2024, **"Trivent"** Malbec (TYPO) | null | 3 | 9.5s |
| 11 | shelf | MontGras Aura Reserva CS, Merlot, Syrah, Carménère | R$54-69 | **120** | 17.6s |
| 12 | shelf | Balduzzi, MontGras Aura | R$39-99 | **280** | 10.8s |
| 13 | shelf | Chaski Perez Cruz **Petit Sirah** (ERRADO=Verdot), Doña Dominga GR (3 var) | R$69-199 | muitos | 19.3s |
| 14 | shelf | MontGras Amaral Red Blend/Syrah, Casa Silva | R$64-99 | 32 | 14.4s |
| 15 | shelf | Perez Cruz LE CF 2024, Doña Dominga Reserva 2021 | R$69-144 | 17 | 12.6s |
| 16 | shelf | Perez Cruz Piedra Seca CS, Perez Cruz Grenache | **R$109.99 ERRADO** Grenache | 12 | 10.2s |
| 17 | shelf | Pacheca, Perspectiva, Duquesa Maria, Pavão, Fred O.O | R$34-188 | muitos | 15.9s |
| 18 | shelf | Don Pasco, Woodbridge, Quasar, Perez Cruz, Toro | R$74-259 | muitos | 21.2s |
| 19 | shelf | Perez Cruz, Alamos, DV Catena, Toro, Novecento, Saurus etc | R$49-279 | muitos | 17.3s |
| 20 | shelf | Rosa Dominga, **PONTGRAS** Aura (TYPO), Cordero, Reservado | R$31-69 | muitos | 16.6s |
| 21 | shelf | Dom Pérignon, Krug, Freixenet | R$139-4999 | muitos | 21.4s |
| 22 | shelf | Krug Grande Cuvée, Ruinart, Freixenet (3 tipos) | R$89-2999 | muitos | 11.5s |
| 23 | shelf | Freixenet Cava, Corvezzo Prosecco (4 var) | R$89-169 | muitos | 15.4s |
| 24 | shelf | Freixenet ICE (2 tipos), Corvezzo (2 tipos) | R$99-139 | 40 | 8.7s |

---

## ARQUIVOS QUE VOCÊ PRECISA LER

1. `C:\winegod-app\backend\tools\media.py` — prompt OCR do Gemini (IMAGE_UNIFIED_PROMPT), handlers de label/shelf/screenshot, processamento
2. `C:\winegod-app\backend\prompts\baco_system.py` — system prompt do Baco (como apresenta dados)
3. `C:\winegod-app\backend\routes\chat.py` — como o contexto da OCR é passado ao Baco

---

## O QUE VOCÊ DEVE ENTREGAR

### Para cada problema (P1, P2, P3, P4, P11, P12, P13):

1. **Diagnóstico** — causa raiz no prompt atual
2. **Prompt revisado** — o novo texto proposto, pronto para copiar
3. **Justificativa** — por que a mudança resolve o problema
4. **Riscos** — o que pode piorar com a mudança
5. **Como testar** — que fotos usar para validar

### Formato da entrega:
Para o Gemini (IMAGE_UNIFIED_PROMPT): entregar o prompt completo revisado.
Para o Baco (system prompt): entregar as seções específicas que devem mudar.

---

## REGRAS

- NÃO implemente nada. Entregue os prompts como texto.
- NÃO faça commit ou push.
- Pode ler qualquer arquivo do projeto.
- Use caminhos completos ao mencionar arquivos.
- Respostas em português, simples e diretas.
- O usuário NÃO é programador.
- Os prompts do Gemini podem ser em inglês (ele funciona melhor assim).
- Os ajustes do Baco devem manter a persona (deus do vinho, teatral, honesto).
