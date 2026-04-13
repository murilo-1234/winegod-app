# HANDOFF — Problemas de Infra: P6, P8, P9, P10

## Quem é você neste chat
Você é um engenheiro backend sênior otimizando a infraestrutura e performance do WineGod.ai. Sua missão é **diagnosticar cada problema, propor soluções técnicas concretas e explicar trade-offs**. NÃO implemente nada — entregue o diagnóstico e proposta.

---

## O que é o WineGod.ai

WineGod.ai é uma IA sommelier. Fluxo quando o usuário manda foto:

```
Foto (base64) → Flask API → Gemini OCR (5-43s) → Claude Haiku + tool calls (20-80s) → resposta
```

### Stack
- **Frontend**: Next.js + TypeScript (Vercel/Cloudflare)
- **Backend**: Python 3.11, Flask, Gunicorn (`C:\winegod-app\backend\`)
- **Hosting backend**: Render (plano **Starter**, NÃO é free)
- **Banco**: PostgreSQL 16 no Render (~1.72M vinhos)
- **IA Chat**: Claude Haiku 4.5 via Anthropic API (com tool use)
- **IA OCR**: Gemini 2.5 Flash via google.generativeai (DEPRECATED)
- **Cache**: Upstash Redis
- **Frontend URL**: chat.winegod.ai
- **Backend URL**: winegod-app.onrender.com

---

## OS 4 PROBLEMAS

### P6 — Busca no banco retorna vinhos ERRADOS (40% dos matches)

**O que acontece:** O search_wine retorna vinhos completamente diferentes do que foi pedido:

| Busca | Retornou | Correto? |
|-------|---------|---------|
| "Alamos" | Los Alamos Vineyard Syrah (Califórnia) | ERRADO — deveria ser Alamos de Catena (Argentina) |
| "Novecento" | MCMXI / Millenovecentoundici (Itália) | ERRADO — deveria ser Novecento argentino |
| "Moet" | Moette (vinho desconhecido) | ERRADO — deveria ser Moët & Chandon |
| "Chandon" | Hommage à Léonard Chandon Pouilly-Fuissé | ERRADO — deveria ser Chandon espumante |

**Código atual:** `C:\winegod-app\backend\tools\search.py`

```python
def search_wine(query, limit=5):
    # Tenta pg_trgm fuzzy match primeiro
    sql = """
        SELECT ... similarity(nome_normalizado, %s) as sim
        FROM wines
        WHERE nome_normalizado %% %s
        ORDER BY sim DESC, vivino_reviews DESC NULLS LAST
        LIMIT %s
    """
    try:
        cur.execute(sql, (query.lower(), query.lower(), limit))
    except Exception:
        # Fallback: ILIKE se pg_trgm não está habilitado
        conn.rollback()
        sql = """
            SELECT ...
            FROM wines
            WHERE nome_normalizado ILIKE %s
            ORDER BY vivino_reviews DESC NULLS LAST
            LIMIT %s
        """
        cur.execute(sql, (f"%{query}%", limit))
```

**Perguntas-chave:**
1. O pg_trgm está ATIVADO no Render? Ou está caindo no fallback ILIKE toda vez?
2. Se pg_trgm está ativo, por que "Alamos" retorna "Los Alamos Vineyard"?
3. O `nome_normalizado` está populado para todos os vinhos?
4. A OCR extrai país, tipo, produtor — esses dados poderiam filtrar a busca?

**Para verificar pg_trgm:**
```sql
SELECT * FROM pg_extension WHERE extname = 'pg_trgm';
-- Se retorna vazio, pg_trgm NÃO está instalado!

-- Testar similarity:
SELECT nome, similarity(nome_normalizado, 'alamos') as sim
FROM wines
WHERE nome_normalizado % 'alamos'
ORDER BY sim DESC LIMIT 10;
```

---

### P8 — Performance inaceitável (28-98 segundos por foto)

**Tempos medidos (2026-04-08):**
- Texto simples (sem foto): ~3-5s
- OCR Gemini isolada: 5-43s (média 14.4s)
- Pipeline completo com foto: **28-98s** (média 72s)
- O gargalo é Claude Haiku + tool calls: ~20-80s

**Breakdown estimado:**
```
Upload/decode base64:    <1s
Gemini OCR:              5-43s (média 14s)
Claude Haiku:            20-80s (múltiplas tool calls)
  - search_wine x N:     ~2-5s cada (DB + cache)
  - get_wine_details:    ~1-2s cada
  - Total tool calls:    2-5 ida-e-volta
DB queries:              <2s total
Total:                   28-98s
```

**Ferramentas que Baco tem:**
O Haiku tem acesso a 14+ tools (search_wine, get_wine_details, get_similar_wines, get_prices, compare_wines, get_recommendations, etc). Cada tool call é uma ida-e-volta.

**Arquivos relevantes:**
- `C:\winegod-app\backend\routes\chat.py` — endpoint /api/chat e /api/chat/stream
- `C:\winegod-app\backend\tools\` — todos os tools disponíveis
- `C:\winegod-app\backend\services\cache.py` — configuração do Redis cache

**Perguntas:**
1. Quantas tool calls o Haiku faz em média por request com foto?
2. Seria possível combinar search_wine + get_details em 1 tool?
3. O OCR poderia rodar em paralelo com uma pre-busca genérica?
4. O cache Redis está efetivo? Qual o hit rate?
5. Flask com Gunicorn — quantos workers estão configurados?

---

### P9 — Render Starter dorme (cold starts)

**O que acontece:** O backend dorme após ~15 minutos de inatividade. Em testes:
- 1ª rodada: 7/12 requests timeout (120s)
- 2ª rodada: 12/12 requests timeout
- Mesmo mensagens de texto simples ("oi") deram timeout

**Plano atual:** Render **Starter** (não é free). Custa ~$7/mês.
- Starter DORME após inatividade (documentação Render confirma)
- Cold start: 30-60s+ (Python + Flask + imports de google.generativeai + anthropic)

**Opções conhecidas:**
1. Cron keep-alive (pingar /health a cada 10min)
2. Upgrade para Render Standard ($25/mês) — nunca dorme
3. Pre-warm no frontend (quando página carrega, manda ping)
4. Trocar para outro host (Railway, Fly.io, etc)

**Perguntas:**
1. Existe um endpoint /health no backend?
2. Qual o tempo exato de cold start? (medir)
3. Gunicorn preload_app está habilitado? (reduz cold start)
4. Quais imports são mais pesados? (pode fazer lazy import)

---

### P10 — Gemini SDK deprecated

**O que acontece:** O backend usa `google.generativeai` que está DEPRECATED:
```
FutureWarning: All support for the google.generativeai package has ended.
Please switch to the google.genai package as soon as possible.
```

**Arquivo:** `C:\winegod-app\backend\tools\media.py` (linha 10)
```python
import google.generativeai as genai
# ...
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")
response = model.generate_content([prompt, {"mime_type": mime, "data": bytes}])
```

**O que precisa mudar:**
- `google.generativeai` → `google.genai`
- API ligeiramente diferente
- Docs de migração: https://github.com/google-gemini/deprecated-generative-ai-python/blob/main/README.md

**Risco:** Pode parar de funcionar a qualquer momento sem aviso.

---

## ARQUIVOS QUE VOCÊ PRECISA LER

### Busca e tools:
- `C:\winegod-app\backend\tools\search.py` — search_wine, get_similar_wines
- `C:\winegod-app\backend\tools\details.py` — get_wine_details
- `C:\winegod-app\backend\tools\compare.py` — compare_wines
- `C:\winegod-app\backend\tools\prices.py` — get_prices (se existir)
- `C:\winegod-app\backend\tools\media.py` — process_image (Gemini SDK)

### Infraestrutura:
- `C:\winegod-app\backend\app.py` — Flask app setup
- `C:\winegod-app\backend\routes\chat.py` — endpoints de chat
- `C:\winegod-app\backend\services\cache.py` — Redis cache
- `C:\winegod-app\backend\db\connection.py` — pool de conexões
- `C:\winegod-app\Procfile` ou `render.yaml` — configuração de deploy
- `C:\winegod-app\backend\requirements.txt` — dependências

### Banco:
```sql
-- Verificar pg_trgm
SELECT * FROM pg_extension WHERE extname = 'pg_trgm';

-- Verificar nome_normalizado
SELECT COUNT(*) FROM wines WHERE nome_normalizado IS NOT NULL;
SELECT COUNT(*) FROM wines WHERE nome_normalizado IS NULL;

-- Sample de nome_normalizado
SELECT nome, nome_normalizado FROM wines WHERE vivino_rating > 4.0 LIMIT 10;
```

---

## O QUE VOCÊ DEVE ENTREGAR

### Para P6 (busca errada):
1. **pg_trgm está ativado?** — verificar com query SQL
2. **Diagnóstico** — por que retorna vinhos errados
3. **Proposta de melhoria do search_wine** — novo SQL, filtros, ranking
4. **Antes/depois** — como os 4 exemplos errados seriam resolvidos

### Para P8 (performance):
1. **Profiling** — onde exatamente o tempo é gasto (logs, timing)
2. **Mapa de tool calls** — quantas o Haiku faz por request
3. **Proposta de otimização** — combinar tools, paralelismo, cache, etc
4. **Estimativa de ganho** — "de 90s para ~Xs"

### Para P9 (Render cold start):
1. **Diagnóstico** — tempo real de cold start, o que é pesado
2. **Proposta** — qual opção é melhor (keep-alive, upgrade, pre-warm)
3. **Implementação do keep-alive** (se for a opção) — endpoint + cron job
4. **Custo** — comparar opções

### Para P10 (Gemini SDK):
1. **Diff exato** — o que muda de google.generativeai para google.genai
2. **Arquivos afetados** — listar todos
3. **Riscos da migração** — o que pode quebrar
4. **Proposta de migração** — passo a passo

---

## REGRAS

- NÃO implemente nada. Só diagnóstico e proposta.
- NÃO faça commit ou push.
- NÃO delete dados do banco.
- NÃO altere colunas existentes.
- Pode rodar queries SELECT e comandos de leitura.
- Use caminhos completos ao mencionar arquivos.
- Respostas em português, simples e diretas.
- O usuário NÃO é programador.
- Credenciais estão em `C:\winegod-app\backend\.env` (não commitado).
