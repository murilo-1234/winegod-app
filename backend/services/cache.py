"""Cache Redis (Upstash) com fallback gracioso."""

import os
import json
import hashlib
import logging

import redis

logger = logging.getLogger(__name__)

# TTLs por tipo de cache
TTL_SEARCH = 300           # 5 min
TTL_DETAILS = 3600         # 1 hora
TTL_PRICES = 600           # 10 min
TTL_RECOMMENDATIONS = 300  # 5 min

# Incrementar para invalidar todo cache após hotfix de busca/dados.
# Chaves antigas expiram naturalmente pelo TTL.
CACHE_VERSION = 3

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
    return f"wg:v{CACHE_VERSION}:{prefix}:{h}"


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
