INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# CHAT S — Cache Redis (Upstash)

## CONTEXTO

WineGod.ai e uma IA sommelier com backend Flask + Claude API. As tools (search_wine, get_prices, compare_wines, etc.) fazem queries PostgreSQL no Render. Muitas buscas se repetem ("melhores tintos argentinos", "Malbec ate 100 reais") e reprocessam as mesmas queries.

Precisamos de cache com Redis (Upstash) para:
1. Evitar queries repetidas ao banco
2. Reduzir latencia das respostas
3. Economizar recursos do banco Render

## SUA TAREFA

Implementar 4 camadas de cache usando Upstash Redis (gratuito):
1. **Cache de busca** — resultados de search_wine por query
2. **Cache de detalhes** — get_wine_details por wine_id
3. **Cache de precos** — get_prices por wine_id
4. **Cache de recomendacoes** — get_recommendations por filtros

## UPSTASH — COMO CRIAR

O fundador ainda NAO criou o Redis no Upstash. Criar o codigo usando variaveis de ambiente:
```
UPSTASH_REDIS_URL=...    # URL do Redis (ex: rediss://default:xxx@xxx.upstash.io:6379)
```

Para o fundador criar depois:
1. Ir em https://console.upstash.com
2. Create Database → nome "winegod" → regiao "US West" (perto do Render Oregon)
3. Copiar UPSTASH_REDIS_REST_URL e UPSTASH_REDIS_REST_TOKEN
4. Ou copiar a connection string redis:// para usar com redis-py

Deixar o sistema **funcionando sem cache** quando UPSTASH_REDIS_URL nao estiver definida (fallback gracioso).

## CREDENCIAIS

```
# Banco WineGod no Render (para testar as tools)
DATABASE_URL=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod
```

## ARQUIVOS A CRIAR/MODIFICAR

### 1. backend/services/cache.py (NOVO)

Modulo central de cache:

```python
import os
import json
import hashlib
import redis
import logging

logger = logging.getLogger(__name__)

# TTLs por tipo de cache
TTL_SEARCH = 300        # 5 min — buscas mudam pouco
TTL_DETAILS = 3600      # 1 hora — detalhes de vinho sao estaveis
TTL_PRICES = 600        # 10 min — precos podem mudar
TTL_RECOMMENDATIONS = 300  # 5 min

_redis_client = None

def get_redis():
    """Retorna cliente Redis. None se nao configurado."""
    global _redis_client
    url = os.getenv("UPSTASH_REDIS_URL")
    if not url:
        return None
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(url, decode_responses=True)
            _redis_client.ping()
            logger.info("Redis conectado (Upstash)")
        except Exception as e:
            logger.warning(f"Redis indisponivel: {e}. Operando sem cache.")
            _redis_client = None
            return None
    return _redis_client

def cache_key(prefix, **kwargs):
    """Gera chave de cache deterministica a partir dos parametros."""
    raw = json.dumps(kwargs, sort_keys=True, default=str)
    h = hashlib.md5(raw.encode()).hexdigest()[:12]
    return f"wg:{prefix}:{h}"

def cache_get(key):
    """Busca no cache. Retorna None se nao encontrado ou Redis indisponivel."""
    r = get_redis()
    if not r:
        return None
    try:
        val = r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None

def cache_set(key, value, ttl):
    """Salva no cache. Silenciosamente falha se Redis indisponivel."""
    r = get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, json.dumps(value, default=str, ensure_ascii=False))
    except Exception:
        pass

def cache_delete_pattern(pattern):
    """Deleta chaves por pattern. Para invalidacao."""
    r = get_redis()
    if not r:
        return
    try:
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
    except Exception:
        pass
```

### 2. backend/tools/search.py (MODIFICAR)

Adicionar cache ao `search_wine` e `get_similar_wines`:

```python
from services.cache import cache_get, cache_set, cache_key, TTL_SEARCH

def search_wine(query, limit=5):
    # Tentar cache primeiro
    key = cache_key("search", query=query.lower(), limit=limit)
    cached = cache_get(key)
    if cached:
        return cached

    # Query normal ao banco (codigo existente)
    ...
    result = {"wines": results, "total": len(results)}

    # Salvar no cache
    cache_set(key, result, TTL_SEARCH)
    return result
```

Mesmo padrao para `get_similar_wines`.

### 3. backend/tools/details.py (MODIFICAR)

Adicionar cache ao `get_wine_details`:

```python
from services.cache import cache_get, cache_set, cache_key, TTL_DETAILS

def get_wine_details(wine_id):
    key = cache_key("details", wine_id=wine_id)
    cached = cache_get(key)
    if cached:
        return cached

    # Query normal (codigo existente)
    ...

    cache_set(key, result, TTL_DETAILS)
    return result
```

### 4. backend/tools/prices.py (MODIFICAR)

Adicionar cache ao `get_prices`:

```python
from services.cache import cache_get, cache_set, cache_key, TTL_PRICES

def get_prices(wine_id, country=None):
    key = cache_key("prices", wine_id=wine_id, country=country)
    cached = cache_get(key)
    if cached:
        return cached

    # Query normal (codigo existente)
    ...

    cache_set(key, result, TTL_PRICES)
    return result
```

### 5. backend/tools/compare.py (MODIFICAR)

Adicionar cache ao `get_recommendations`:

```python
from services.cache import cache_get, cache_set, cache_key, TTL_RECOMMENDATIONS

def get_recommendations(tipo=None, pais=None, regiao=None, uva=None, preco_min=None, preco_max=None, limit=5):
    key = cache_key("recs", tipo=tipo, pais=pais, regiao=regiao, uva=uva, preco_min=preco_min, preco_max=preco_max, limit=limit)
    cached = cache_get(key)
    if cached:
        return cached

    # Query normal (codigo existente)
    ...

    cache_set(key, result, TTL_RECOMMENDATIONS)
    return result
```

`compare_wines` NAO precisa de cache (comparacoes sao quase sempre unicas).

### 6. backend/requirements.txt (MODIFICAR)

Adicionar:
```
redis>=5.0.0
```

## PADRAO IMPORTANTE: FALLBACK GRACIOSO

**O sistema DEVE funcionar sem Redis.** Se `UPSTASH_REDIS_URL` nao estiver definida, ou se o Redis cair:
- `cache_get()` retorna None → tool faz query normal
- `cache_set()` nao faz nada → sem erro
- Zero impacto na funcionalidade

Nunca levantar excecao por causa de cache.

## O QUE NAO FAZER

- **NAO modificar app.py** — cache e transparente nas tools
- **NAO modificar baco.py** — cache e nas tools, nao no orquestrador
- **NAO modificar chat.py** — idem
- **NAO modificar nenhum arquivo frontend** — cache e 100% backend
- **NAO fazer git commit/push** — avisar quando terminar
- **NAO usar Upstash REST API** — usar redis-py com connection string (mais simples)
- **NAO cachear respostas do Claude** — so cachear resultados das tools (banco)

## COMO TESTAR

1. Sem Redis (fallback):
```bash
cd backend
unset UPSTASH_REDIS_URL
python -c "
from tools.search import search_wine
r = search_wine('malbec')
print(f'Resultados: {r[\"total\"]}')  # deve funcionar normal sem cache
"
```

2. Com Redis (se tiver URL):
```bash
cd backend
UPSTASH_REDIS_URL=rediss://default:xxx@xxx.upstash.io:6379 python -c "
from tools.search import search_wine
import time

# Primeira busca (cache miss)
t1 = time.time()
r1 = search_wine('malbec')
t1 = time.time() - t1

# Segunda busca (cache hit)
t2 = time.time()
r2 = search_wine('malbec')
t2 = time.time() - t2

print(f'Sem cache: {t1:.3f}s')
print(f'Com cache: {t2:.3f}s')
print(f'Speedup: {t1/t2:.1f}x')
"
```

3. Build:
```bash
cd backend && pip install redis
```

## ENTREGAVEL

- `backend/services/cache.py` — modulo central de cache Redis
- `backend/tools/search.py` — com cache em search_wine e get_similar_wines
- `backend/tools/details.py` — com cache em get_wine_details
- `backend/tools/prices.py` — com cache em get_prices
- `backend/tools/compare.py` — com cache em get_recommendations
- `backend/requirements.txt` — com redis
- Todas as tools funcionam normalmente SEM Redis configurado

## REGRA DE COMMIT

Commitar APENAS os arquivos que VOCE criou/modificou nesta sessao. NUNCA incluir arquivos de outros chats. Fazer `git pull` antes de `git push` para nao conflitar com outros chats que rodam em paralelo.
