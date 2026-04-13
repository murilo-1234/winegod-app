# VIDEO AUTOMACAO — Creatomate + HeyGen Avatar

INSTRUCAO: Este prompt e para executar no Claude Code. Ele cria/evolui o pipeline de videos promocionais automatizados para Instagram Reels/TikTok usando Creatomate (composicao) + HeyGen (avatar IA).

---

## 1. VISAO GERAL

Pipeline automatizado que gera videos promocionais verticais (9:16) para produtos Natura/Avon. Um avatar digital (HeyGen) apresenta produtos em promocao com layouts dinamicos compostos via API do Creatomate.

**Repositorio:** `C:\natura-automation`
**Servico Render:** `natura-client-automation-1`
**URL Render:** `https://natura-client-automation-1.onrender.com`
**Banco:** PostgreSQL no Render — `natura_db`

---

## 2. REGRA FUNDAMENTAL: DUAS FASES SEPARADAS

```
FASE 1 — CARDS DE PRODUTO (esta fase)
  Foco: metade superior da tela (y: 0-50%)
  Avatar: quadrado PRETO placeholder (#000000)
  Objetivo: acertar o layout dos cards de produto
  Testes: JSON no Creatomate (barato/gratis) → video so no teste final

FASE 2 — AVATAR (depois de fechar os cards)
  Foco: metade inferior da tela (y: 50-100%)
  Integrar: HeyGen, voz, sincronizacao
  Substituir: quadrado preto pelo video do avatar real
```

**NAO misturar as fases.** Enquanto estiver na Fase 1, o avatar e sempre um shape preto. Isso evita gastar creditos do HeyGen e Creatomate com renders de video completo durante o ajuste visual.

---

## 3. ARQUITETURA DA TELA

```
720x1280 (ou 1080x1920)
┌─────────────────────────────┐
│                             │
│     SLOT CARD (template)    │  y: 0% a 50%
│     Vem do Creatomate       │  Cada slide = 1 template de card
│                             │
├─────────────────────────────┤
│                             │
│     SLOT AVATAR             │  y: 50% a 100%
│     FASE 1: shape #000000   │  Quadrado preto (placeholder)
│     FASE 2: video HeyGen    │  Avatar real
│                             │
└─────────────────────────────┘
```

O template Creatomate controla APENAS o slot do card (metade de cima).
O Source JSON do Python controla a composicao final: posiciona o card em cima, o avatar/placeholder embaixo, e sequencia os slides.

---

## 4. COMO FUNCIONA NA PRATICA

### O Source JSON (Python) e a "moldura":

```python
source = {
    "output_format": "mp4",
    "width": 720, "height": 1280,
    "frame_rate": 15,
    "duration": total_segundos,
    "fill_color": "#000000",
    "elements": [
        # SLIDE 1 — Card do Produto 1 (metade de cima)
        {
            "type": "composition",
            "track": 1, "time": 0, "duration": 5,
            "x": "50%", "y": "25%",
            "width": "100%", "height": "50%",
            "x_alignment": "50%", "y_alignment": "50%",
            "elements": [...]  # ← elementos extraidos do template
        },
        # SLIDE 2 — Card do Produto 2
        {
            "type": "composition",
            "track": 1, "time": 5, "duration": 5,
            "x": "50%", "y": "25%",
            "width": "100%", "height": "50%",
            "x_alignment": "50%", "y_alignment": "50%",
            "elements": [...]  # ← mesmo template ou outro, dados diferentes
        },
        # SLIDE CTA
        {
            "type": "composition",
            "track": 1, "time": 10, "duration": 5,
            "x": "50%", "y": "25%",
            "width": "100%", "height": "50%",
            "x_alignment": "50%", "y_alignment": "50%",
            "elements": [...]  # ← template de CTA
        },

        # AVATAR/PLACEHOLDER — metade de baixo (track 2, persistente)
        # FASE 1:
        {
            "type": "shape",
            "track": 2, "time": 0, "duration": total_segundos,
            "x": "50%", "y": "75%",
            "width": "100%", "height": "50%",
            "x_alignment": "50%", "y_alignment": "50%",
            "fill_color": "#000000",
        },
        # FASE 2 (substituir o shape acima por):
        # {
        #     "type": "video",
        #     "track": 2, "time": 0, "duration": total_segundos,
        #     "source": avatar_url,
        #     "x": "50%", "y": "75%",
        #     "width": "100%", "height": "50%",
        #     "x_alignment": "50%", "y_alignment": "50%",
        #     "fit": "cover", "volume": "100%",
        # },
    ],
}
```

O template Creatomate fornece o DESIGN do card. O codigo busca o JSON do template via API, extrai os `elements`, e injeta dentro da composition do slide. Os dados dinamicos (nome, preco, imagem) sao substituidos programaticamente.

---

## 5. ESTRATEGIA DE TEMPLATES (Flexivel)

### Comecar com 1 template, replicar depois

```
Passo 1: Criar UM template de card que funcione bem
Passo 2: Testar com dados reais ate ficar bom
Passo 3: Replicar mudando pouco (cores, layout espelhado)
Passo 4: O codigo alterna entre templates por slide
```

O sistema deve aceitar:
- **1 template**: usa o mesmo para todos os slides (muda so os dados)
- **2 templates**: alterna entre eles (impar/par)
- **N templates**: cicla na ordem que forem cadastrados

```python
CARD_TEMPLATE_IDS = [
    'ID_DO_PRIMEIRO_TEMPLATE',
    # Adicionar mais quando criar variacoes
]
CTA_TEMPLATE_ID = 'ID_DO_TEMPLATE_CTA'  # ou None = CTA via Source JSON
```

---

## 6. FLUXO DE BUSCA E INJECAO DO TEMPLATE

O codigo faz isto pra cada slide:
1. `GET /v1/templates/{template_id}` → recebe JSON com `source.elements`
2. Extrair os elements do template
3. Substituir textos/imagens com dados do produto (encontrar por `name`)
4. Embedir os elements como filhos de uma composition
5. Posicionar a composition em y=25%, height=50%

### Cache dos templates:

```python
_TEMPLATE_CACHE = {}

def buscar_template(template_id):
    if template_id in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[template_id]
    resp = requests.get(
        f'{CREATOMATE_BASE}/v1/templates/{template_id}',
        headers=_headers(),
    )
    template = resp.json()
    _TEMPLATE_CACHE[template_id] = template
    return template
```

---

## 7. COMO TESTAR BARATO

```
1. Preview no editor Creatomate  → 0 creditos
2. Render como JPG               → barato
3. Render MP4 com render_scale 0.5 → intermediario
4. Render MP4 escala 1.0         → teste final (so quando aprovado)
```

Render como JPG:
```json
{ "source": { ... }, "output_format": "jpg" }
```

Render com resolucao reduzida:
```json
{ "source": { ... }, "output_format": "mp4", "render_scale": 0.5 }
```

---

## 8. CONVENCAO DE NOMES NOS TEMPLATES

Todo elemento dinamico no template DEVE ter `name`. Se nao tiver, modifications nao encontram.

```
Produto-Imagem    → url da foto do produto
Produto-Nome      → nome do produto
Preco-De          → preco original (riscado)
Preco-Por         → preco com desconto (grande, destaque)
Badge-Desconto    → texto do badge (ex: "-50%")
Badge-Cashback    → texto do cashback (ex: "+R$8 cashback")
BG-Card           → fundo do card (cor ou imagem blur)
CTA-Texto         → texto do call to action
CTA-Botao         → texto do botao
```

### Funcao Python de mapeamento:

```python
def mapear_produto(produto):
    cashback = produto.get('cashback', 0) or 0
    mapa = {
        'Produto-Imagem': produto['url_imagem_principal'],
        'Produto-Nome': produto['nome'],
        'Preco-De': f"De R${int(round(produto['preco_original']))}",
        'Preco-Por': f"R${int(round(produto['preco_atual']))}",
        'Badge-Desconto': f"-{int(produto['percentual_desconto'])}%",
    }
    if cashback > 0:
        mapa['Badge-Cashback'] = f"+R${int(round(cashback))} cashback"
    else:
        mapa['Badge-Cashback'] = {}  # remove o elemento
    return mapa
```

---

## 9. COMO CRIAR TEMPLATE DE CARD NO CREATOMATE

1. **New Template → Custom Size:** largura do video final (720 ou 1080), metade da altura (640 ou 960) — template e so a metade de cima.
2. **Adicionar elementos e NOMEAR cada um** seguindo a convencao da secao 8.
3. **Marcar como dinamico:** ativar "Dynamic" (icone de raio) nos elementos que recebem dados.
4. **Salvar e copiar o Template ID.**

---

## 10. CREDENCIAIS (ja configuradas no .env.local)

```
# HeyGen (Avatar IA)
HEYGEN_API_KEY=<REDACTED>
HEYGEN_AVATAR_ID=419590a4c3104aa99a472ffc6901c3d9
HEYGEN_VOICE_ID=5406b97ef43547d58d6fda32d19dac8e

# Creatomate (Composicao de video)
CREATOMATE_API_KEY=<REDACTED>

# Webhook
WEBHOOK_BASE_URL=https://natura-client-automation-1.onrender.com

# OpenAI (Roteiro + Whisper)
OPENAI_API_KEY=<REDACTED>

# AWS S3
AWS_S3_BUCKET=video-automation-natura-2025
AWS_S3_REGION=us-east-2
```

### Variaveis novas (adicionar ao .env.local):
```
CARD_TEMPLATE_IDS=a8d1b761-5022-447b-a3f6-57cc1db3f4b0
CTA_TEMPLATE_ID=
VIDEO_FASE=1
# 1 = placeholder preto (development)
# 2 = avatar HeyGen real (production)
```

---

## 11. AVATAR HEYGEN (Fase 2)

- **Avatar ID:** `419590a4c3104aa99a472ffc6901c3d9`
- **Voice ID:** `5406b97ef43547d58d6fda32d19dac8e`
- **Fundo:** branco #FFFFFF (NAO usar green screen)
- **Resolucao:** 1080x1920 (9:16)
- **Velocidade da fala:** 1.05x
- **Posicao no video final:** metade inferior (y=75%, height=50%)

---

## 12. ESTILO VISUAL DE REFERENCIA (@orodrigospinola)

Imagens de referencia em: `C:\Users\muril\OneDrive\Documentos\lixo\Nova pasta\rodrigoespindola\`

- **Formato:** Vertical 9:16 (Instagram Reels)
- **Layout:** Split-screen — card em cima (~50%), avatar falando embaixo (~50%)
- **Texto:** Bold, branco, fonte grande, centralizado
- **Font:** Montserrat
- **Avatar:** Bust shot, olhando pra camera, cantos arredondados
- **Fundo:** Predominantemente escuro
- **Transicoes:** Fade e slide entre cenas
- **Duracao:** 25-59 segundos (NUNCA >= 60s)

---

## 13. TEMPLATES EXISTENTES NO CREATOMATE (2026-04-07)

| Template | ID | Formato | Util? |
|----------|----|---------|-------|
| Storytelling Video | `a8d1b761-5022-447b-a3f6-57cc1db3f4b0` | 720x1280 | **SIM** — card com produto, preco, desconto, cashback. Usar como BASE. Elementos sem `name` (precisam ser nomeados). |
| Product Hero Discount | `2b9881ad-bd08-43bb-84dd-cc950ad41c12` | 720x1280 | **SIM** — card flutuante com sombra e animacao. |
| Natura-Promocao-Vertical | `cea1d6c8-06af-46b9-b2a9-f5e31a0e849e` | 1080x1920 | PARCIAL — elementos nomeados mas layout flat. |
| Product Hero Discount | `cf6d9f48-5db8-40b9-8c3f-b297b0e9eef4` | 1080x1080 | NAO — quadrado. |
| Quick Promo | `63d90f81-824e-463b-bb77-f8fcb3320a5e` | 1080x1080 | NAO — demo generico. |
| Storytelling Video | `df4c0aaa-22d9-4373-af0e-d8f2be3122d4` | 720x1280 | NAO — demo Creatomate. |

---

## 14. DADOS DOS PRODUTOS (schema do banco)

```python
{
    'nome': 'Desodorante Colonia Humor Envolve 75 ml',
    'preco_original': 164.9,
    'preco_atual': 82.4,
    'percentual_desconto': 50.0,
    'cashback': 8.24,
    'url_imagem_principal': 'https://production.na01.natura.com/...',
    'codigo': '169821',
    'marca': 'NATURA',
}
```

---

## 15. ARQUITETURA DO PIPELINE

### Arquivos em `C:\natura-automation\video_pipeline\`:
```
pipeline.py            # Orquestrador das 7 etapas
script_generator.py    # Roteiro via OpenAI API
heygen_client.py       # Gera avatar + webhook
whisper_api_client.py  # Timestamps via API OpenAI Whisper
timeline_builder.py    # Mapeia timestamps → cenas
image_processor.py     # Processa imagens produtos
creatomate_client.py   # Composicao JSON + envio render
music_manager.py       # Trilhas sonoras
```

### Fluxo de webhooks:
```
POST /gerar-video-promocao → cria job → roteiro → HeyGen → retorna job_id
POST /webhooks/heygen ← HeyGen termina → Whisper → imagens → Creatomate
POST /webhooks/creatomate ← Creatomate termina → S3 → "concluido"
GET /video-status/{job_id} ← consulta resultado
```

---

## 16. DECISOES FIXAS (NAO VIOLAR)

```
1. HeyGen = APENAS gerar clip do avatar falando
2. Creatomate = TODA composicao final (cards, layouts, legendas, musica)
3. Cards compostos NATIVAMENTE no JSON do Creatomate (NAO usar Pillow)
4. NAO rodar Whisper local (usar API OpenAI Whisper)
5. NAO usar background threads (usar webhooks)
6. NAO usar green screen (fundo branco #FFFFFF)
7. Processar imagens UMA por vez (gc.collect — Render 512MB)
8. Cleanup /tmp SEMPRE em try...finally
9. Keys novas no .env existente do Render (nunca hardcoded)
10. Template Creatomate = SO metade de cima (card). NUNCA tela inteira.
```

---

## 17. ERROS JA MAPEADOS (NAO REPETIR)

| Erro | Causa | Solucao |
|------|-------|---------|
| `Shape.fill_color[0].offset: Shouldn't be null` | Gradiente sem offsets | Usar `[{"offset": "0%", "color": "..."}, ...]` |
| `Image.color_filter: Expected a string` | `color_filter` como array | Remover — nao funciona |
| `template_id not provided` | `json=[payload]` (lista) | Usar `json=payload` (objeto) |
| `403 ao baixar asset` | URLs `creatomate.com/files/assets/...` | Usar URLs publicas (GitHub, S3) |
| `remove_background: true` | Aceita sem erro mas efeito visual minimo | Nao confiar nisso |
| Modification nao funciona | Elemento sem `name` no template | Nomear no editor |

---

## 18. COISAS QUE TRAVAM (EVITAR)

1. **Tentar usar template pra tela inteira** → Source JSON como moldura, template so fornece os elements do card
2. **Elementos sem nome no template** → Nomear TODOS os elementos dinamicos no editor
3. **Gastar creditos testando com video** → preview no editor → JPG → MP4 escala 0.5 → MP4 final
4. **Misturar Fase 1 e Fase 2** → quadrado preto no avatar ate fechar os cards
5. **Criar muitos templates antes de acertar 1** → acertar 1 → replicar mudando cor/layout

---

## 19. CORES DO DESIGN

```python
CORES = {
    'fundo':        '#FFFFFF',
    'fundo_bege':   '#F5F5DC',
    'frame_branco': '#FFFFFF',
    'texto':        '#000000',
    'texto_cinza':  '#888888',
    'preco_por':    '#E8820C',   # dourado
    'desconto':     '#FF1744',   # vermelho
    'cashback':     '#00C853',   # verde
    'cta_bg':       '#E91E8C',   # rosa
    'cta_texto':    '#FFFFFF',
}
```

---

## 20. SPECS DE SAIDA

```
Resolucao: 720 x 1280 (source) / 1080 x 1920 (ideal)
FPS: 15 (economia) / 30 (producao)
Codec: H.264/AAC | Formato: MP4
Duracao: 25-59 segundos (NUNCA >= 60)
Tamanho: < 50 MB
```

---

## 21. TABELA NO BANCO

```sql
CREATE TABLE IF NOT EXISTS video_jobs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    input_hash            VARCHAR(64) UNIQUE,
    status                VARCHAR(20) DEFAULT 'pendente',
    etapa_atual           VARCHAR(100),
    video_url             TEXT,
    error_message         TEXT,
    custo_estimado        DECIMAL(8,2),
    roteiro_json          JSONB,
    avatar_video_url      TEXT,
    timestamps_json       JSONB,
    composicao_json       JSONB,
    heygen_video_id       VARCHAR(100),
    heygen_webhook_at     TIMESTAMP,
    creatomate_render_id  VARCHAR(100),
    creatomate_webhook_at TIMESTAMP,
    num_produtos          INTEGER,
    created_at            TIMESTAMP DEFAULT NOW(),
    updated_at            TIMESTAMP DEFAULT NOW()
);
```

---

## 22. DEPLOY

1. Editar arquivos em `C:\natura-automation\video_pipeline\`
2. `git add [arquivo] && git commit -m "msg" && git push`
3. Deploy MANUAL no Render: servico `natura-client-automation-1` → "Manual Deploy"
4. Limpar jobs antigos antes de testar (dedup por hash)

---

## 23. COMO TESTAR

```bash
# 1. Limpar jobs antigos
python -c "
import psycopg2
conn = psycopg2.connect('postgresql://natura_user:3Wm6FxpK2FKORHry5P1p59ZRqduPcT0C@dpg-d4mrbere5dus738jal8g-a.oregon-postgres.render.com/natura_db')
cur = conn.cursor()
cur.execute('DELETE FROM video_jobs')
conn.commit()
conn.close()
"

# 2. Disparar teste
curl -X POST https://natura-client-automation-1.onrender.com/gerar-video-promocao \
     -H "Content-Type: application/json" \
     -d '{"min_desconto": 5, "num_produtos": 2}'

# 3. Consultar resultado (~35s depois)
curl https://natura-client-automation-1.onrender.com/video-status/{JOB_ID}
```

---

## 24. REGRAS PARA O CLAUDE CODE

- SO editar arquivos em `video_pipeline/` (outros so se necessario)
- Compilar antes de commitar: `python -m py_compile video_pipeline/creatomate_client.py`
- Limpar jobs antes de testar (dedup por hash)
- Nunca usar `git add .` — so adicionar o arquivo editado
- Deploy NAO e automatico — avisar para fazer Manual Deploy no Render
- Nunca alterar .env no servidor — pedir pro usuario fazer manualmente
- VIDEO_FASE=1 durante desenvolvimento (placeholder preto no avatar)
