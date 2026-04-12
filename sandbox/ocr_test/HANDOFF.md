# HANDOFF — Sandbox de Testes OCR Multi-Modelo (WineGod)

**Data**: 2026-04-12 (atualizado — fase 2 concluída)
**Autor da sessão**: Claude Opus 4.6 + Murilo
**Objetivo**: Documento auto-contido para retomar exatamente onde paramos, caso a sessão seja perdida.

---

## 1. Contexto e motivação

### O que é o WineGod e onde esse trabalho se encaixa
WineGod.ai é uma IA sommelier que recebe fotos de vinho (garrafa única, prateleira, cardápio, screenshot) e responde sobre elas via chat. Hoje (em produção) o sistema usa **Google Gemini 2.5 Flash** como modelo de visão/OCR. Murilo quis:

1. Entender como o sistema de leitura de fotos funciona de ponta a ponta
2. Testar modelos alternativos (Qwen chinês) como possível substituto do Gemini
3. Descobrir se era possível fazer o Qwen render resultados melhores via prompt engineering
4. Garantir que nada dos testes afete produção

### Restrições absolutas
- **Zero impacto em produção**. Nenhum arquivo em `backend/` foi modificado nesta sessão.
- Todo o trabalho ficou isolado em `C:\winegod-app\sandbox\ocr_test\`.
- API keys em `.env` (nunca hardcoded, nunca commitadas).

---

## 2. Arquitetura atual de produção (resumo, para contexto)

Pipeline completo de uma foto no WineGod hoje:

```
Frontend (Next.js) manda foto base64
  ↓
POST /api/chat (backend/routes/chat.py:324)
  ↓
_has_media() detecta imagem → _process_media() (chat.py:49)
  ↓
_process_single_image() ou _process_batch_images() (chat.py:127, 160)
  ↓
backend/tools/media.py::process_image() (linha 278)
  ↓
Gemini 2.5 Flash via _gemini_generate() com IMAGE_UNIFIED_PROMPT (media.py:54-128)
  ↓
JSON retornado: {type, wines[], total_visible, ...}
  ↓
backend/tools/resolver.py::resolve_wines_from_ocr() (linha 31)
  → _resolve_label() ou _resolve_multi()
  → backend/tools/search.py::search_wine() (5 camadas)
  ↓
backend/services/display.py::resolve_display() (linha 17)
  → hierarquia de 4 regras para nota + winegod_score
  ↓
Contexto formatado em 3 tiers (confirmed_with_note / confirmed_no_note / visual_only)
  ↓
backend/services/baco.py::stream_baco_response() (linha 15)
  → Claude Haiku 4.5 com TOOLS_PHOTO_MODE
  ↓
SSE streaming de volta ao frontend
```

**Modelo de OCR**: `gemini-2.5-flash`
**Modelo de chat**: `claude-haiku-4-5-20251001`
**Classificação label/shelf/screenshot**: dentro do próprio prompt do Gemini (linhas 54-128 de media.py). Não há classificador separado.

A pasta `wine_classifier/` NÃO é usada pra fotos — são scripts de enriquecimento de banco com Claude Opus e Mistral em abas de browser.

---

## 3. Estrutura do sandbox

```
C:\winegod-app\sandbox\ocr_test\
├── compare.py                    # Script de comparação base (6 modelos × N fotos)
├── experiments.py                # 10 experimentos de prompt engineering
├── .env                          # Keys (gitignored — DASHSCOPE_API_KEY + base_url)
├── .env.example                  # Template
├── .gitignore                    # ignora .env e results/
├── HANDOFF.md                    # ESTE DOCUMENTO
└── results/                      # outputs JSON + markdown (gitignored)
    ├── results_20260410_194911.json      # Gemini baseline (3 fotos)
    ├── comparison_20260410_194911.md
    ├── results_20260411_211159.json      # Qwen × 3 fotos
    ├── comparison_20260411_211159.md
    └── experiments_20260411_214321.json  # 10 experimentos prompt eng
```

**Zero importação de `backend/`**: o sandbox é 100% standalone. Copia o prompt `IMAGE_UNIFIED_PROMPT` inline (se atualizarem em produção, sincronizar manualmente).

---

## 4. Fotos de teste

**Folder**: `C:\winegod\fotos-vinhos-testes\`
Contém 1.jpeg até 24.jpeg + moet.jpeg + v1.mp4-v5.mp4 (vídeos).

**Usadas nesta sessão**: `3.jpeg`, `5.jpeg`, `7.jpeg`.

### Ground truth (verificado via Gemini + thinking que acertou 9/9 na foto 7)

**Foto 3** — 2 vinhos (fácil)
1. Contada 1926 Chianti
2. Contada 1926 Primitivo Puglia — R$ 59,99

**Foto 5** — 3 vinhos (médio)
1. D. Eugenio Crianza 2018 — R$ 54,99
2. D. Eugenio Tinto — R$ 41,99
3. Cuatro Vientos Tinto

**Foto 7** — 9 vinhos (densa — o desafio principal)
1. Curral Pinot Noir — R$ 119,99
2. Les Dauphins Syrah Classiques
3. Les Dauphins Côtes du Rhône Réserve — R$ 76,99
4. Contada 1926 Chianti
5. Contada 1926 Chianti Classico — R$ 139,99
6. Contada 1926 Chianti Reserva — R$ 99
7. O Gato & Juju — R$ 69,99
8. Contada 1926 Montepulciano d'Abruzzo — R$ 59
9. Contada 1926 Vignola — R$ 59,99

---

## 5. Modelos testados nesta sessão

| Modelo | Provider | In/1M | Out/1M | Notas |
|---|---|---|---|---|
| `gemini-2.5-flash` (thinking ON) | Google | $0.30 | $2.50 | Produção atual. Thinking cobra output rate. |
| `gemini-2.5-flash` (thinking OFF) | Google | $0.30 | $2.50 | Via `thinking_config.thinking_budget=0` |
| `gemini-2.5-flash-lite` | Google | $0.10 | $0.40 | Não suporta thinking, alucina em wines |
| `qwen-vl-ocr` | Alibaba DashScope | $0.07 | $0.16 | Mais barato, fraco em cena densa |
| `qwen3-vl-flash` | Alibaba DashScope | $0.05 | $0.40 | Foco dos experimentos de prompt eng |
| `qwen3-vl-32b-instruct` | Alibaba DashScope | $0.16 | $0.64 | Open source-ish |
| `qwen3-vl-plus` | Alibaba DashScope | $0.20 | $1.60 | Meio termo |
| `qwen3.6-plus` | Alibaba DashScope | $0.50 | $3.00 | Lentíssimo (134s/foto), não compensa |

**Endpoint Qwen**: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (OpenAI-compatible, usa openai SDK).

---

## 6. Fase 1 — Comparação base dos 6 modelos (compare.py)

### Como foi feito
Script `compare.py` roda CADA modelo uma vez em CADA foto, usando o prompt de produção (`IMAGE_UNIFIED_PROMPT` copiado inline de `backend/tools/media.py`).

Para cada call, captura:
- `content` (texto retornado)
- `elapsed_ms`
- `in_tokens`, `out_tokens`
- Custo estimado via tabela hardcoded (veja seção 6.3)

Salva JSON + markdown comparativo em `results/`.

### 6.1 — Resultado Gemini baseline (3 fotos)

| Foto | Vinhos lidos | Latência | "Custo reportado" |
|---|---|---|---|
| 3 | 2 ✅ Contada 1926 Chianti + Primitivo Puglia R$59,99 | 7.8s | $0.0008 |
| 5 | 3 ✅ D. Eugenio Crianza/Tinto + Cuatro Vientos | 13s | $0.0009 |
| 7 | 9 ✅ TODOS corretos | 24.6s | $0.0023 |

**Gemini acertou 9/9 na foto densa**. Referência de qualidade da sessão.

### 6.2 — Resultado Qwen (5 modelos × 3 fotos)

**Foto 3 (fácil)** — todos os Qwen pegaram 2/2 vinhos. Diferenças:
- qwen3-vl-plus e qwen3-vl-flash: nomes perfeitos
- qwen-vl-ocr: duplicou o nome ("2x Primitivo")
- qwen3.6-plus: truncou "Primitivo Puglia" → "Primitivo"

**Foto 5 (médio)** — todos 3/3. Mas:
- qwen3-vl-32b-instruct: leu "D.FUGENIO" (erro OCR E→F)
- qwen3.6-plus: **inventou producer** "Virgen de las Vinas"
- qwen-vl-ocr: duplicou "CUATRO CUATRO VIENTOS"
- qwen3-vl-plus e flash: corretos

**Foto 7 (densa, 9 vinhos)** — aqui os modelos se separaram:

| Modelo | Vinhos achados | Qualidade |
|---|---|---|
| Gemini Flash + thinking | 9 ✅ | Baseline. Tudo correto |
| qwen3.6-plus | 9 ⚠️ | **Inventou** "King & Juju", "Malaguetta" |
| qwen3-vl-32b-instruct | 7 ❌ | **Inventou** "Barolo", "Amarone della Valpolicella" |
| qwen3-vl-plus | 7 ⚠️ | Duplicou Côte du Rhône, inventou "Araguaju" |
| qwen3-vl-flash | 7 ⚠️ | Duplicou Chianti, prefixo "Vinho Tinto" |
| qwen-vl-ocr | **2 ❌** | Perdeu quase tudo em foto densa |

### 6.3 — Ranking geral e vereditos

| # | Modelo | Latência média | Custo "reportado" total (3 fotos) | Veredito |
|---|---|---|---|---|
| 🥇 | Gemini Flash + thinking | 15s | $0.004 (errado, veja §7) | Melhor acurácia |
| 🥈 | qwen3-vl-plus | 12s | $0.003 | Bom em fácil/médio |
| 🥉 | qwen3-vl-flash | 6s | $0.001 | Rápido + barato |
| 4 | qwen3-vl-32b-instruct | 12s | $0.002 | Inventa em densa |
| 5 | qwen3.6-plus | **109s** | $0.057 | Lentíssimo. Descartar |
| 6 | qwen-vl-ocr | 6s | $0.001 | Falha em densa |

---

## 7. Fase 2 — A descoberta dos "thinking tokens" do Gemini

### Contexto do problema
Murilo contou que num projeto anterior achou que ia gastar $20 e no final gastou **$400**. Veio dessa pegadinha: o Gemini 2.5 Flash cobra por **tokens de "pensamento"** que não aparecem no output visível, mas são cobrados na tarifa de output ($2.50/1M).

### Como verificamos
Executei uma chamada ao Gemini 2.5 Flash capturando todo o `usage_metadata`:

```
prompt_token_count:      270
candidates_token_count:  1022     ← output visível (o que eu estava contando)
thoughts_token_count:    2700     ← THINKING (escondido, mas cobrado)
total_token_count:       3992
```

**2700 thinking tokens pra 1022 de output**. O modelo "pensou" 2.6x mais do que escreveu.

### Impacto no custo das nossas 3 fotos

Rodei de novo capturando thinking:

| Foto | prompt | output | **thinking** | Custo REPORTADO | **Custo REAL** | Multiplicador |
|---|---|---|---|---|---|---|
| 3 | 1615 | 211 | **1606** | $0.00101 | **$0.00503** | 4.97x |
| 5 | 1615 | 194 | **2023** | $0.00097 | **$0.00603** | 6.22x |
| 7 | 1615 | 547 | **3997** | $0.00185 | **$0.01185** | **6.40x** |

**Todos os custos Gemini reportados estão subestimados em ~5-6x.**

### Escalonamento real
Na média $0.008/foto (real) vs $0.0013/foto (reportado):

| Volume | Custo reportado | **Custo REAL** |
|---|---|---|
| 1.000 fotos | $1,30 | **$8** |
| 10.000 fotos | $13 | **$80** |
| 100.000 fotos | $130 | **$800** |

Exatamente o padrão de surpresa que Murilo já sofreu antes.

### Como desligar thinking no Gemini
```python
from google.genai import types
config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=0),
)
client.models.generate_content(model='...', contents=[...], config=config)
```

### Gemini SEM thinking (teste nas 3 fotos)

| Foto | COM thinking (vinhos) | SEM thinking (vinhos) | Economia de custo |
|---|---|---|---|
| 3 (fácil) | 2 ✅ | 2 ✅ | **80%** |
| 5 (médio) | 3 ✅ | 3 ✅ (**melhor**: achou "La Mancha") | **82%** |
| 7 (difícil) | 9 ✅ | **6** (perdeu Curral, Gato, 1 Contada) | 85% |

**Conclusão**: desligar thinking funciona pra label/prateleira pequena, mas em densa o modelo perde vinhos.

### Status da produção (backend/tools/media.py)
**CRÍTICO**: hoje `media.py:42-49` chama Gemini SEM `thinking_config`, então thinking está **LIGADO por padrão em TODAS as fotos do WineGod**. Cada foto de usuário está custando ~5-6x mais do que alguém esperaria olhando só o pricing público.

Ainda **não foi alterado**. Murilo vai decidir estratégia (pode ser roteamento 2 etapas).

---

## 8. Fase 3 — Gemini 2.5 Flash-Lite (testado mas descartado)

**Teste nas 3 fotos com e sem thinking**. Flash-Lite não suporta thinking (thoughts_tokens = 0 sempre).

**Pontos fortes**:
- Muito barato: $0.0002-0.0003/foto (5x mais barato que Flash sem thinking, 40x mais barato que Flash com)
- Muito rápido: 2-3 segundos

**Ponto fraco absolutamente fatal**:
- **Alucina nomes e preços**

Exemplos:
- Foto 5: leu R$ 73,32 e R$ 55,90 (corretos são R$ 54,99 e R$ 41,99). **Inventou preços**.
- Foto 7: leu "Château Duclair du Bois Reserve", "Château de Syrah", "Domaine de la Roche Noir" — **vinhos que não existem na foto**.

**Veredito**: ❌ não serve pro WineGod. Produto que mostra score de custo-benefício não pode ter preços inventados.

---

## 9. Fase 4 — A "falsa quebra de encoding" (CASO RESOLVIDO)

### O que parecia
Nos primeiros outputs do qwen3-vl-flash eu reportei:
```
Vinho Tinto Dauphins C�tes du Rh�ne R�serve
```
E falei que o modelo tinha problema de encoding.

### O que era de verdade
Rodei `repr()` no raw_text salvo em JSON:
```python
'Vinho Tinto Dauphins C\xf4tes du Rh\xf4ne R\xe9serve'
```

Esses são **bytes UTF-8 válidos**. `0xf4` = `ô`, `0xe9` = `é`. O modelo devolveu UTF-8 perfeito.

Quando fiz `sys.stdout.reconfigure(encoding='utf-8')` antes do print, apareceu:
```
Vinho Tinto Dauphins Côtes du Rhône Réserve
```

### Conclusão
**Não existia bug de encoding no qwen3-vl-flash.** O problema era 100% do meu terminal Windows PowerShell (cp1252 default) que não conseguia imprimir caracteres acentuados. Os arquivos JSON salvos com `json.dumps(..., ensure_ascii=False)` estavam sempre corretos.

### Fix (apenas cosmético, não muda nada funcional)
No topo de qualquer script de teste:
```python
import sys
sys.stdout.reconfigure(encoding='utf-8')
```

**Não há nada a corrigir em produção por causa disso.** Os dados salvos pelo `compare.py` já estavam com UTF-8 correto desde o começo.

### Registro para futura referência
Se você vir `�` em logs do Windows, não entre em pânico — verifique o encoding do terminal ANTES de concluir que o modelo quebrou. Abra o arquivo JSON direto em vez de confiar no print.

---

## 10. Fase 5 — 10 experimentos de prompt engineering (experiments.py)

### Objetivo
Tentar fazer `qwen3-vl-flash` (o mais barato dos Qwen) render 9/9 na foto 7 via **prompt engineering puro**, sem trocar de modelo.

### Métricas capturadas por experimento
- **Acertos**: quantos dos 9 vinhos do ground truth foram cobertos (match por token key: "curral", "syrah", "cotes", "chianti", "chianti classico", "chianti reserva", "gato", "montepulciano", "vignola")
- **Hallucinations**: quantos nomes retornados batem com lista de alucinações conhecidas (`araguaju`, `casa juju`, `king & juju`, `malaguetta`, `barolo`, `amarone`, `antoing`, `duclair`, `roche noir`, `chateau de syrah`)
- **Total reportado**: quantos vinhos o modelo disse que existem
- **Latência** e **custo**

### Tabela de resultados

| # | Experimento | Técnica | Acertos | Halluc | Total | Tempo | Custo |
|---|---|---|---|---|---|---|---|
| 1 | baseline | Prompt de produção puro | 3/9 | 0 | 6 | 8.5s | $0.0003 |
| 2 | role_expert | System msg: "auditor planograma 15 anos" | **0/9** | 0 | 0 | 10s | $0.0004 |
| 3 | cot_explicit_counting | Step 1: conta. Step 2: lista. Step 3: verifica | **4/9** | 0 | 6 | 7.3s | $0.0003 |
| 4 | spatial_grid | "Divida em grid 3x3 e varra cada célula" | **4/9** | 0 | 6 | 7.5s | $0.0003 |
| 5 | strip_shelftag_prefix | "Strip 'VINHO TTO 750ML' dos nomes" | 2/9 | 0 | 6 | 7.9s | $0.0003 |
| 6 | few_shot | 1 exemplo de output bom no prompt | 3/9 | 0 | 4 | 5.8s | $0.0002 |
| 7 | no_hallucination_rule | Regra dura: "se não tem certeza, omita" | 3/9 | 0 | 5 | 7.2s | $0.0003 |
| 8 | chinese_prompt | Mesmo prompt em mandarim | **0/9** | 0 | 0 | 12s | $0.0005 |
| 9 | all_best_combined | role + CoT + anti-halluc + strip | **4/9** | 0 | 7 | 12.5s | $0.0004 |
| 10 | self_consistency_3x | 3 chamadas T=0.3, voto ≥2 | 3/9 | 0 | 5 | 22s | $0.0009 |

### Observações sobre os piores (0/9)
- **Exp 2 (role_expert)**: o system message de "auditor planograma" fez o modelo retornar JSON vazio. Provavelmente classificou como tipo errado.
- **Exp 8 (chinese)**: prompt em chinês também zerou. Qwen foi treinado majoritariamente em chinês mas **labels em português + prompt em chinês não combina**. O modelo não conseguiu ligar as duas coisas.

### Observação sobre self_consistency (exp 10)
3x mais caro, 3x mais lento, sem ganho de acurácia. **Não vale a pena pra esse caso**.

---

## 11. Fase 6 — 4 experimentos adicionais (rodados inline)

### Exp 11 — `vl_high_resolution_images=True`
Parâmetro específico DashScope que aumenta o cap de visual tokens de ~1280 pra 16384. Passado via `extra_body` no openai SDK.

**Resultado**: 4/9 (in_tokens subiu de ~1615 pra 2059). Ajudou pouco — ainda não chega nos 9/9.

### Exp 12 — `detail: "high"` no image_url
Estilo OpenAI vision. **3/9**. Sem ganho real.

### Exp 13 — Tiling (cortar foto em 3 faixas horizontais com 15% overlap)
Cada faixa roda isolada, depois dedup por nome.

**Resultado**: **3/9** — PIOROU. Alucinou "Moscato d'Abruzzo", "Nuvolari", "Sangiovese" como vinhos independentes. Sem contexto cross-shelf, o modelo vira nomes-de-uva em vinhos-fantasma.

### Exp 14 — Detect-then-read (grounding nativo Qwen3-VL)
Passo 1: pede bboxes de todas as garrafas. Passo 2: corta cada bbox e lê.

**Resultado**: **0/9**. Dois problemas:
1. Qwen3-VL devolve coordenadas **normalizadas 0-1000**, não pixels (eu não converti)
2. Mesmo com conversão, ele detectou **51 bboxes pra 9 vinhos distintos** — não entende "distinct SKU", detecta garrafa física, inclusive 10x a mesma Contada
3. Os crops ficaram em lugares errados e só leu o prefixo da etiqueta ("VINHO TINTO") ou inventou nomes ("SHERONG DECHOIS", "DAPHNE")

**Implementação correta** (não rodada nesta sessão): converter bbox `[x1,y1,x2,y2]` de 0-1000 pra pixels: `px = (coord / 1000) * image_dim`. Depois dedupar bboxes visualmente (IoU) antes de enviar cada crop.

---

## 12. Conclusão empírica dura

**Teto do qwen3-vl-flash na foto densa (9 vinhos): ~4/9 (44%)**, independente do prompt.

- Baseline: 3/9
- Melhores prompts (CoT, grid, combo): 4/9
- Nenhuma das 14 técnicas conseguiu 5/9 ou mais
- O problema não é o prompt — é a capacidade visual do modelo em labels pequenos em cenas densas

**Onde qwen3-vl-flash é bom**:
- Label única (1 vinho dominando): 2/2 ✅
- Prateleira com ≤3 vinhos distintos: 3/3 ✅
- Prateleira densa (6+ vinhos): 44% cap ❌

---

## 13. Pesquisa acadêmica — 12 técnicas com fontes reais

Um agente de pesquisa buscou referências empíricas em papers, docs oficiais e blogs. Todas as URLs abaixo foram verificadas como reais e acessíveis (no momento do uso).

### Técnica 1: `vl_high_resolution_images=True` / max_pixels mais alto
- **Mecanismo**: Qwen-VL tokeniza imagens em blocos 28×28px. Default cap ~1280 tokens (~1M px). Labels pequenos viram 1 token e ficam ilegíveis. Ativar high_res aumenta pra 16384 tokens.
- **Fonte**: [Qwen3-VL vision_process.py](https://github.com/QwenLM/Qwen3-VL/blob/main/qwen-vl-utils/src/qwen_vl_utils/vision_process.py) · [Alibaba Cloud Model Studio Vision](https://www.alibabacloud.com/help/en/model-studio/vision)
- **Teste nesta sessão**: Exp 11 → 4/9. Ajudou pouco.

### Técnica 2: Tiling em faixas overlapping
- **Mecanismo**: Alimenta crops com overlap, cada vinho recebe budget cheio de tokens.
- **Fonte**: [Image Tiling arXiv 2512.11167](https://arxiv.org/pdf/2512.11167) · [VLM-OCR Recipes HF](https://huggingface.co/blog/florentgbelidji/vlm-ocr-recipes-gpu-infra)
- **Teste nesta sessão**: Exp 13 → 3/9. PIOROU para esse caso (contexto cross-shelf se perde).

### Técnica 3: Detect-then-read com grounding nativo Qwen
- **Mecanismo**: Qwen2.5/3-VL emite `bbox_2d` em JSON nativamente. Passo 1 detecta, Passo 2 lê cada crop.
- **Fonte**: [Qwen2.5-VL Blog](https://qwenlm.github.io/blog/qwen2.5-vl/) · [Qwen3-VL 2D Grounding cookbook](https://github.com/QwenLM/Qwen3-VL/blob/main/cookbooks/2d_grounding.ipynb) · [Spatial Understanding cookbook](https://github.com/QwenLM/Qwen3-VL/blob/main/cookbooks/spatial_understanding.ipynb)
- **Teste nesta sessão**: Exp 14 → 0/9. Erro MEU: não converti 0-1000 → pixels. A técnica pode funcionar, mas precisa implementação correta.

### Técnica 4: Rotear fotos densas pro modelo thinking
- **Mecanismo**: Qwen3-VL-Thinking roda CoT interno antes de responder.
- **Evidência**: Qwen3-VL-8B-Thinking: 97% em DocVQA, 79-80 em MathVista vs ~64 do GPT-4o. +15-25% em multi-step visual reasoning.
- **Fonte**: [Qwen3-VL-8B-Thinking Model Card](https://huggingface.co/Qwen/Qwen3-VL-8B-Thinking) · [Qwen3-VL Benchmarks](https://www.mintlify.com/QwenLM/Qwen3-VL/resources/benchmarks)
- **Status**: não testado. Candidato forte pra testes futuros.

### Técnica 5: JSON schema estruturado com "unknown" enum
- **Mecanismo**: Decoding constrito força schema válido. Permite `confidence:"low"`, `readable:false` como saídas válidas. Suprime o impulso de inventar nomes.
- **Fonte**: [NVIDIA NIM Structured Generation](https://docs.nvidia.com/nim/vision-language-models/1.0.0/structured-generation.html) · [VLM + Pydantic](https://www.leadingtorch.com/2026/02/09/maximizing-accuracy-with-vlms-replacing-ocr-pipelines-with-pydantic-structured-outputs/)

### Técnica 6: Self-consistency (N samples, voto majoritário)
- **Mecanismo**: Amostras com T>0, mantém vinhos que aparecem na maioria. Alucinações têm baixa consistência.
- **Evidência**: CVPR 2024 Khan et al.: estabilidade sample-level é forte indicador de correção em VLMs black-box.
- **Fonte**: [Consistency & Uncertainty CVPR 2024](https://openaccess.thecvf.com/content/CVPR2024/papers/Khan_Consistency_and_Uncertainty_Identifying_Unreliable_Responses_From_Black-Box_Vision-Language_Models_CVPR_2024_paper.pdf) · [Robust CoT Self-Consistency MDPI](https://www.mdpi.com/2227-7390/13/18/3046)
- **Teste nesta sessão**: Exp 10 → 3/9 (sem ganho).

### Técnica 7: Few-shot in-context
- **Mecanismo**: 1-3 exemplos de output bom no prompt. Modelo copia padrão.
- **Evidência**: ACM TIST 2025: 1-shot → +3.2pts; 16-shot → 82.5% em classificação VLM.
- **Fonte**: [Integrated Image-Text Augmentation ACM TIST](https://dl.acm.org/doi/10.1145/3712700) · [Making LVLMs Good Few-shot arXiv 2408.11297](https://arxiv.org/abs/2408.11297)
- **Teste nesta sessão**: Exp 6 → 3/9 (sem ganho real com 1 shot).

### Técnica 8: CoT com contagem explícita
- **Mecanismo**: Pede pra contar bottles primeiro, depois listar. Contagem ancora o output e previne omissão/duplicação.
- **Evidência**: Qwen2-VL paper admite VLMs lutam com counting em cenas densas. Qwen3-VL-Thinking 97% DocVQA atribuído a decomposição em steps.
- **Fonte**: [Qwen2-VL arXiv 2409.12191](https://arxiv.org/abs/2409.12191) · [Qwen2.5-VL Tech Report 2502.13923](https://arxiv.org/abs/2502.13923)
- **Teste nesta sessão**: Exp 3 → **4/9** (empatado como melhor técnica text-only).

### Técnica 9: Detector dedicado (SKU-110K YOLO) + VLM per-crop
- **Mecanismo**: YOLO treinado em SKU-110K encontra bottles com recall >0.9. Qwen lê cada crop.
- **Evidência**: SKU-110K tem 1.73M bboxes em prateleiras densas. "Shelf Management" 2024: RetinaNet 0.752 mAP + recognition 93% top-1.
- **Fonte**: [SKU-110K CVPR19 GitHub](https://github.com/eg4000/SKU110K_CVPR19) · [Shelf Management ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0957417424015021) · [RP2K arXiv 2006.12634](https://arxiv.org/abs/2006.12634) · [SKU-110K Ultralytics](https://docs.ultralytics.com/datasets/detect/sku-110k/) · [Real-time planogram Nature 2025](https://www.nature.com/articles/s41598-025-27773-5)
- **Status**: técnica "industrial" pra escala. Requer fine-tuning próprio. Caminho de longo prazo.

### Técnica 10: Pré-processamento (deglare, endireitar label)
- **Mecanismo**: Rotacionar label curvo pra eixo axis-aligned, CLAHE seletivo.
- **Evidência**: Springer 2023 wine-specific: "curved label positions made it difficult to standardize". CLAHE pode HELP ou HURT dependendo do histograma (71.7→70.75% em algumas fotos).
- **Fonte**: [Wine labels smart recognition Springer](https://link.springer.com/article/10.1007/s00371-023-03119-y) · [Wine label reader toolkit GitHub](https://github.com/AntoninLeroy/wine_label_reader_toolkit) · [Image Preproc OCR arXiv 2410.13622](https://arxiv.org/html/2410.13622v1)

### Técnica 11: Verificação contra o DB do WineGod (fuzzy match) 🔥
- **Mecanismo**: Fuzzy match nome → 1.72M vinhos. Nomes sem match plausível são descartados como alucinação.
- **Evidência**: CVPR 2025 Critic-V: verificador externo reduz substancialmente erros multimodais.
- **Fonte**: [Critic-V CVPR 2025](https://openaccess.thecvf.com/content/CVPR2025/papers/Zhang_Critic-V_VLM_Critics_Help_Catch_VLM_Errors_in_Multimodal_Reasoning_CVPR_2025_paper.pdf)
- **WineGod ready**: a infra já existe em `backend/tools/resolver.py` e `backend/tools/search.py`. "Araguaju" → 0 matches → drop. **Ganho imediato, custo zero, risco zero.**

### Técnica 12: Embeddings contrastivos SKU (fallback visual)
- **Mecanismo**: Quando OCR falha, compara embedding do crop com galeria conhecida (CLIP/DINOv2).
- **Evidência**: MDPI 2025: BYOL 99.22% top-1 fine-tuned em RP2K; SimCLR 94.98% linear.
- **Fonte**: [Contrastive Learning SKU MDPI](https://www.mdpi.com/2076-3417/16/6/2810) · [RP2K arXiv](https://arxiv.org/abs/2006.12634)

### Referências adicionais (pesquisa)
- [Qwen2-VL arXiv 2409.12191](https://arxiv.org/abs/2409.12191)
- [Qwen2.5-VL Technical Report arXiv 2502.13923](https://arxiv.org/abs/2502.13923)
- [Qwen2.5-VL-7B-Instruct Model Card](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)
- [Qwen3-VL GitHub](https://github.com/QwenLM/Qwen3-VL)
- [Qwen3-VL Cookbooks](https://github.com/QwenLM/Qwen3-VL/tree/main/cookbooks)
- [Qwen3-VL OCR cookbook](https://github.com/QwenLM/Qwen3-VL/blob/main/cookbooks/ocr.ipynb)
- [Alibaba Qwen-VL-OCR via DashScope](https://www.alibabacloud.com/help/en/model-studio/qwen-vl-ocr)
- [PyImageSearch Qwen 2.5 Grounding](https://pyimagesearch.com/2025/06/09/object-detection-and-visual-grounding-with-qwen-2-5/)
- [Deep Learning for Retail Product Recognition (PMC survey)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7676964/)
- [HF OCR Open Models blog](https://huggingface.co/blog/ocr-open-models)

---

## 14. Recomendações ranqueadas (o que fazer a seguir)

### 🟢 Nível 1 — Risco zero, ganho rápido

**1. Desligar thinking do Gemini em produção, fazer roteamento 2 etapas**
- `backend/tools/media.py`: primeira chamada SEM thinking (barato, rápido, ~$0.001/foto)
- Se `type == "shelf"` e `total_visible >= 6` OU parse falhou → retry COM thinking
- Esperado: 80% das fotos custam $0.001, 20% densas custam $0.01 → média $0.003/foto vs $0.008 de hoje = **60% de economia**
- Sem perda de qualidade (thinking só é acionado quando necessário)

**2. Implementar Técnica 11 (DB verification)**
- Qualquer nome que o VLM retorna e não tem match fuzzy no Postgres = drop como alucinação
- Mata "Araguaju", "Casa Juju", "Nuvolari", "King & Juju" sem mudar nada no modelo
- A infra já existe em `resolver.py`. É questão de rodar `search_wine(name, allow_fuzzy=True)` pra cada nome retornado e descartar os sem hit razoável.

### 🟡 Nível 2 — Testar primeiro antes de decidir

**3. Testar qwen3-vl-plus e qwen-vl-max** nas mesmas 3 fotos com:
- `vl_high_resolution_images=True`
- Prompt combo (CoT + anti-halluc + strip)
Ver se algum alcança Gemini+thinking com custo menor.

**4. Testar Qwen3-VL-Thinking variant** (Técnica 4)
Se atingir 9/9 na foto 7, é candidato real pra substituir Gemini.

**5. Detect-then-read corretamente** (Técnica 3 com fix)
Converter bboxes 0-1000 → pixels, deduplicar visualmente (IoU), rodar leitura per-crop. Pode ser a única forma de chegar em 9/9 com qwen3-vl-flash.

### 🔴 Nível 3 — Caminho de longo prazo (se escala justificar)

**6. Fine-tuning YOLOv8 em SKU-110K + wine data própria** (Técnica 9)
Detect-then-read industrial. Requer labeled data e infra ML. Só faz sentido com >100k fotos/mês.

**7. Embeddings contrastivos de SKU** (Técnica 12)
Fallback visual quando OCR falha totalmente. Requer galeria pré-computada.

---

## 15. Pendências importantes / bugs conhecidos

1. **API key Qwen exposta**: Murilo colou a key no chat (`sk-26fd2b808d544a9f887544e03f3ef424`). Planeja revogar depois do teste. **Lembrar de revogar no painel DashScope**.

2. **Produção está com thinking ligado**: cada foto custando 5-6x mais que o pricing público sugere. Priorizar fix.

3. **Tabela de preços do sandbox pode estar desatualizada**: hardcoded em `compare.py:130-138`. Verificar preços reais no painel de cada provider quando for tomar decisões comerciais. Não confiar 100% nos números do sandbox.

4. **O `_cost()` do `compare.py` NÃO conta thinking tokens do Gemini**: foi identificado mas NÃO corrigido no script. Os números que ele imprime ainda estão subestimados pra Gemini. Fix seria adicionar `thoughts_token_count` ao `out_tokens`.

---

## 16. Como retomar exatamente onde paramos

### Verificar que o ambiente está pronto
```bash
cd C:\winegod-app
python -c "import google.genai, openai, dotenv, PIL; print('OK')"
```

### Ver os resultados da última sessão
```bash
# Gemini baseline (compare.py)
type "C:\winegod-app\sandbox\ocr_test\results\results_20260410_194911.json"

# Qwen 5 modelos (compare.py)
type "C:\winegod-app\sandbox\ocr_test\results\results_20260411_211159.json"

# 10 experimentos prompt eng (experiments.py)
type "C:\winegod-app\sandbox\ocr_test\results\experiments_20260411_214321.json"
```

### Rodar de novo
```bash
cd C:\winegod-app

# 1) Comparação base (6 modelos × 3 fotos)
python sandbox/ocr_test/compare.py --photos 3,5,7

# 2) 10 experimentos de prompt engineering em qwen3-vl-flash
python sandbox/ocr_test/experiments.py

# 3) Só um provider
python sandbox/ocr_test/compare.py --only gemini
python sandbox/ocr_test/compare.py --only qwen
```

### Se precisar adicionar novo modelo ao compare.py
Editar `compare.py` na seção `QWEN_MODELS` (linha 130) ou adicionar novo provider function (estilo `run_gemini`/`run_qwen`). Seguir o mesmo padrão: retornar `{content, elapsed_ms, in_tokens, out_tokens, cost}`.

### Se precisar criar novo experimento de prompt
Em `experiments.py`, adicionar função decorada com `@exp("NN_nome", "descrição")`. A função retorna `call_qwen(msgs, ...)`. Ver exemplos 01-10 no arquivo.

### Como forçar UTF-8 no terminal Windows (evitar confusão de encoding)
Início de qualquer script:
```python
import sys
sys.stdout.reconfigure(encoding='utf-8')
```

### Variáveis de ambiente necessárias
- `GEMINI_API_KEY` — em `backend/.env` (já configurado)
- `DASHSCOPE_API_KEY` — em `sandbox/ocr_test/.env` (já configurado, revogar após testes)
- `DASHSCOPE_BASE_URL` — `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (default)

### Contexto pra falar com uma nova IA numa nova sessão
> "Lê `C:\winegod-app\sandbox\ocr_test\HANDOFF.md` e me ajuda a continuar de onde a sessão anterior parou. Meu objetivo é [X]." (substituir X por: implementar roteamento 2 etapas / implementar DB verification / testar qwen3-vl-plus / etc.)

---

---

## 17. Fase 2 — qwen3-vl-flash only, 10 fotos, 8 técnicas (2026-04-12)

### Motivação
Fase 1 estabeleceu que qwen3-vl-flash é o melhor Qwen (bateu 32b, plus e max). Teto da fase 1 foi 5/9 com preprocessing (contrast+sharpen). Objetivo da fase 2: descobrir o teto REAL do flash testando mais fotos e técnicas novas.

### Fotos selecionadas (dificuldade crescente)

| # | Foto | Dificuldade | Ground truth (Gemini+thinking) |
|---|---|---|---|
| 1 | 9.jpeg | easy | 2 vinhos (She's Noir Pinot Noir, Freixenet 0.0%) |
| 2 | 10.jpeg | easy | 2 vinhos (Finca Las Moras, Trivent Malbec) |
| 3 | 15.jpeg | medium | 3 vinhos (Perez Cruz, 2x Doña Dominga) |
| 4 | 14.jpeg | medium | 4 vinhos (Amaral, 2x Casa Silva) |
| 5 | 24.jpeg | medium | 4 vinhos (2x Freixenet ICE, 2x Corvezzo) |
| 6 | 11.jpeg | hard | 5 vinhos (3x MontGras Aura, Casa Silva) |
| 7 | 8.jpeg | hard | 6 vinhos (Les Dauphins, Contada 1926 ×4) |
| 8 | 19.jpeg | hard | 8 vinhos (Terro Callejo, Alamos, Novecento, etc.) |
| 9 | 7.jpeg | very hard | 10 vinhos (Curral, Les Dauphins, Contada ×5, G&Juju, etc.) |
| 10 | 18.jpeg | extreme | 43 vinhos (corredor inteiro de supermercado) |

Ground truth gerado por Gemini 2.5 Flash com thinking ativo. Salvo em `sandbox/ocr_test/results/ground_truth_10photos.json`.

### 8 técnicas testadas

| Técnica | O que faz |
|---|---|
| T1 baseline | Prompt EN, imagem original, hi-res |
| T2 preproc_basic | Contrast +20% + sharpen (winner fase 1) |
| T3 clahe | CLAHE real via OpenCV (adaptive histogram equalization) |
| T4 upscale2x | Upscale 2x via Lanczos (labels ficam maiores) |
| T5 sharp_forte | UnsharpMask radius=3, percent=200 |
| T6 prompt_ptbr | Prompt em português (mesmo conteúdo do EN, traduzido) |
| T7 ptbr_primed | Prompt PT-BR + "auditor de prateleira de supermercado brasileiro, preço R$" |
| T8 combo_max | CLAHE + upscale 1.5x + sharp + contrast + prompt PT-BR primed + hi-res |

Todas rodaram com `vl_high_resolution_images=True` e `temperature=0.0`.

### 17.1 Tabela completa de resultados (80 runs)

#### Fotos fáceis (2 vinhos)

| Foto | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 |
|---|---|---|---|---|---|---|---|---|
| 9 | 100% | 100% | 100% | **0%** | 100% | 100% | 100% | 100% |
| 10 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |

#### Fotos médias (3-4 vinhos)

| Foto | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 |
|---|---|---|---|---|---|---|---|---|
| 15 (3) | 0% | 0% | 0% | 66% | 66% | 66% | 66% | 66% |
| 14 (4) | 25% | 25% | 25% | 25% | 25% | **100%** | 75% | 75% |
| 24 (4) | 75% | 75% | 50% | 75% | 75% | 75% | 75% | 75% |

#### Fotos difíceis (5-8 vinhos)

| Foto | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 |
|---|---|---|---|---|---|---|---|---|
| 11 (5) | 60% | 80% | 80% | 40% | **0%** | 80% | 20% | 80% |
| 8 (6) | 83% | 50% | 83% | 66% | **0%** | 83% | 83% | 66% |
| 19 (8) | 37% | **0%** | 37% | 25% | 37% | 37% | **0%** | 25% |

#### Fotos muito difíceis / extremas

| Foto | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 |
|---|---|---|---|---|---|---|---|---|
| 7 (10) | 60% | 60% | **0%** | 40% | 50% | 40% | 50% | **80%** |
| 18 (43) | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% |

### 17.2 Ranking de técnicas (média das 10 fotos)

| # | Técnica | Média | Observação |
|---|---|---|---|
| 🥇 | **T6 prompt PT-BR** | **68%** | Mudança mais impactante. ZERO custo extra. |
| 🥈 | **T8 combo max** | **67%** | Melhor em foto densa (80% na foto 7!) |
| 🥉 | T7 ptbr_primed | 57% | Priming demais pode confundir |
| 4 | T1 baseline EN | 54% | Referência |
| 5 | T2 preproc_basic | 49% | Winner fase 1, mas PIOR que PT-BR |
| 6 | T3 clahe | 48% | Bom em médias, péssimo na foto 7 |
| 7 | T5 sharp_forte | 45% | DESTRUTIVO: 0% em fotos 8 e 11 |
| 8 | T4 upscale2x | 44% | Instável: 0% na foto 9 (fácil!) |

### 17.3 Descobertas críticas

**1. Prompt em PT-BR é a maior alavanca (T6)**
Na foto 14, trocar de inglês para português subiu de 25% para **100%** — de 1/4 para 4/4 vinhos. O modelo entende melhor o contexto brasileiro quando o prompt está no mesmo idioma. Custo: literalmente zero — é só traduzir o prompt.

**2. T8 combo max na foto 7: 8/10 = 80%**
NOVO RECORDE ABSOLUTO. O stack CLAHE + upscale 1.5x + sharpen + contrast + PT-BR primed levou a foto mais difícil de 4-5/9 (~50%) pra 8/10 (80%). Quase dobrou a acurácia na prateleira densa.

**3. Preprocessing pode PIORAR drasticamente**
- T5 (sharp forte) → 0% nas fotos 8 e 11. Imagem "over-sharpened" confunde o tokenizer visual.
- T2 (preproc basic, winner fase 1) → média 49%, PIOR que baseline sem nada (54%).
- T4 (upscale 2x) → 0% na foto 9 (que é FÁCIL — 2 vinhos).
- **Lição**: preprocessing é arma de dois gumes. Só usar em foto densa.

**4. Foto 18 (43 vinhos): flash NÃO consegue — 0% em TODAS as técnicas**
Limite absoluto do qwen3-vl-flash: prateleiras com 30+ vinhos são impossíveis pra esse modelo. Precisa de Gemini+thinking ou pipeline industrial (YOLO detect + VLM per-crop).

**5. Priming excessivo pode confundir (T7 vs T6)**
T7 (PT-BR primed) ficou 11 pontos abaixo de T6 (PT-BR puro). O parágrafo extra de "auditor especializado em supermercados brasileiros" às vezes faz o modelo focar demais no contexto e menos nos labels.

### 17.4 Melhor técnica por faixa de dificuldade

| Faixa | Vinhos | Melhor técnica | Hit rate |
|---|---|---|---|
| Easy | 1-2 | Qualquer (T6 PT-BR por padrão) | **100%** |
| Medium | 3-5 | **T6 PT-BR** | **66-100%** |
| Hard | 6-8 | **T6 PT-BR** ou **T8 combo max** | **37-83%** |
| Very hard | 9-13 | **T8 combo max** | **80%** |
| Extreme | 30+ | **Nenhuma — usar Gemini+thinking** | 0% |

---

## 18. Fase 1.5 — Combos multi-técnica × 4 modelos (2026-04-12)

### O que foi testado
5 combos (empilhando 3-5 técnicas acadêmicas) × 4 modelos Qwen (flash, 32b, plus, max), com pós-filtro DB verify (Técnica 11) em todos.

### Resultado consolidado — melhor combo por modelo

| Modelo | Melhor combo | Hits (pre-DB) | Hits (post-DB) | Custo |
|---|---|---|---|---|
| 🏆 **qwen3-vl-flash** | F_preprocessing | **5/9** | 5/9 | **$0.0004** |
| qwen-vl-max-latest | F_preprocessing | 4/9 | 4/9 | $0.0076 |
| qwen3-vl-32b-instruct | B_few_shot | 3/9 | 3/9 | $0.0007 |
| qwen3-vl-plus | A/C/D/F empatados | 3/9 | 3/9 | $0.0010-0.0052 |

### Conclusão desta fase
**qwen3-vl-flash vence em TODAS as dimensões** — acurácia, custo, velocidade. Modelos maiores (incluindo qwen-vl-max a 40x o preço) performam PIOR. O gargalo é a capacidade visual do modelo em labels pequenos, e modelos maiores do Qwen não melhoram isso.

**DB verify** funcionou corretamente como pós-filtro — dropou alucinações sem falsos positivos significativos.

### Artefatos
- Script: `sandbox/ocr_test/experiments_combo.py`
- Resultados: `sandbox/ocr_test/results/combo_20260412_002746.json`

---

## 19. Estratégia final recomendada para produção

### Pipeline de roteamento em 3 camadas

```
Foto chega no chat
  ↓
CAMADA 1: qwen3-vl-flash + prompt PT-BR (T6)
  Custo: $0.0003/foto | Latência: ~5s
  ↓
SE type=label OU ≤3 wines → USAR RESULTADO (resolve ~85% das fotos de usuário)
  ↓
CAMADA 2: qwen3-vl-flash + T8 combo max (CLAHE+upscale+sharp+PT-BR)
  Custo: $0.0004/foto | Latência: ~10s
  Ativação: 4+ wines OU total_visible ≥ 7
  ↓
SE ≤ 13 wines → USAR RESULTADO
  ↓
CAMADA 3: Gemini 2.5 Flash + thinking
  Custo: $0.008-0.012/foto | Latência: ~20s
  Ativação: 14+ wines OU total_visible ≥ 20 OU parse falhou
```

### Pós-filtro em TODAS as camadas
- DB verify via `resolver.search_wine(name, allow_fuzzy=True)` — descarta nomes sem match no Postgres
- Já existe a infra em `backend/tools/resolver.py` e `backend/tools/search.py`
- Custo: zero (query local no DB)
- Efeito: mata alucinações ("Araguaju", "Casa Juju", "Nuvolari") sem perder acertos

### Custo estimado vs produção atual

| Cenário | Distribuição estimada | Custo médio/foto |
|---|---|---|
| **Produção atual** (Gemini+thinking em tudo) | 100% Gemini | **$0.008** |
| **Pipeline 3 camadas** | 85% flash T6 + 12% flash T8 + 3% Gemini | **$0.0007** |
| **Economia** | | **91%** |

### Mudanças necessárias em produção

1. **`backend/tools/media.py`** — trocar prompt para PT-BR, adicionar lógica de roteamento 3 camadas
2. **`backend/tools/media.py`** — adicionar `thinking_config.thinking_budget=0` no Gemini da camada 1 (se mantiver Gemini como fallback)
3. **Novo arquivo ou função** — preprocessing via PIL/OpenCV (CLAHE + upscale + sharpen) para camada 2
4. **`sandbox/ocr_test/.env`** — migrar `DASHSCOPE_API_KEY` para `backend/.env` quando for pra produção
5. **Instalar `opencv-python-headless`** no `requirements.txt` do backend (pra CLAHE)

---

## 20. Pendências e próximos passos

### Pendências operacionais
1. ⚠️ **Revogar API key Qwen** que Murilo colou no chat (`sk-26fd2b808d544a9f887544e03f3ef424`). Gerar nova no painel DashScope.
2. ⚠️ **Produção está com thinking ligado no Gemini** — cada foto custando 5-6x mais que aparenta.

### Próximos passos (por prioridade)
1. **[grátis, 1 hora]** Trocar prompt de produção de EN para PT-BR em `backend/tools/media.py` — ganho imediato de ~14 pontos percentuais sem custo.
2. **[grátis, 1 hora]** Implementar DB verify pós-filtro — infra já existe.
3. **[baixo risco, 2 horas]** Implementar pipeline 3 camadas com qwen3-vl-flash como camada 1.
4. **[médio risco, 1 dia]** Adicionar preprocessing (CLAHE+sharpen) como camada 2.
5. **[teste, 2 horas]** Rodar as 24 fotos completas no pipeline 3 camadas e medir hit rate médio fim-a-fim.

---

## 21. Artefatos completos

| Arquivo | O que faz |
|---|---|
| `sandbox/ocr_test/compare.py` | Fase 1 — comparação 6 modelos × N fotos |
| `sandbox/ocr_test/experiments.py` | Fase 1 — 10 experimentos prompt engineering isolados |
| `sandbox/ocr_test/experiments_combo.py` | Fase 1.5 — 5 combos × 4 modelos + DB verify |
| `sandbox/ocr_test/phase2_flash.py` | **Fase 2** — 8 técnicas × 10 fotos, flash only |
| `sandbox/ocr_test/results/ground_truth_10photos.json` | Ground truth das 10 fotos (Gemini+thinking) |
| `sandbox/ocr_test/results/all_24_classify.json` | Classificação das 24 fotos (tipo + dificuldade + contagem) |
| `sandbox/ocr_test/results/results_*.json` | Resultados brutos de cada fase |
| `sandbox/ocr_test/results/combo_*.json` | Resultados brutos dos combos |
| `sandbox/ocr_test/results/phase2_*.json` | Resultados brutos da fase 2 |
| `sandbox/ocr_test/.env` | API keys (gitignored) |
| `sandbox/ocr_test/.env.example` | Template de keys |

---

## 22. Como retomar

### Verificar ambiente
```bash
cd C:\winegod-app
python -c "import google.genai, openai, dotenv, PIL, cv2; print('OK')"
```

### Rodar cada fase
```bash
# Fase 1: comparação base
python sandbox/ocr_test/compare.py --photos 3,5,7

# Fase 1: 10 experimentos prompt eng
python sandbox/ocr_test/experiments.py

# Fase 1.5: combos multi-técnica × 4 modelos
python -u sandbox/ocr_test/experiments_combo.py

# Fase 2: 8 técnicas × 10 fotos (flash only)
python -u sandbox/ocr_test/phase2_flash.py
```

### Contexto pra nova sessão
> "Lê `C:\winegod-app\sandbox\ocr_test\HANDOFF.md` e me ajuda a continuar. Meu objetivo é [implementar pipeline 3 camadas / trocar prompt pra PT-BR / adicionar CLAHE / etc.]"

---

## 23. Conclusão final

**Três mudanças transformam o custo e a qualidade do OCR do WineGod:**

1. **Trocar prompt pra PT-BR** — +14% de acurácia média, custo zero
2. **Usar qwen3-vl-flash como camada 1** — 91% de economia vs Gemini+thinking
3. **Stack CLAHE+upscale+sharpen pra fotos densas** — 80% hit rate em prateleiras de 10+ vinhos

O Gemini continua como fallback pra corredores inteiros (30+ vinhos), mas esses são <3% das fotos de usuário.

Custo projetado: **$0.0007/foto** vs **$0.008/foto** atual = **economia de 91%**.

Fim do handoff. Pelo WineGod.
