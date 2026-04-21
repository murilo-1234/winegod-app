"""F1.8 - GET /api/config/enabled-locales (kill switch frontend-readable).

Ordem de resolucao (decidida em F0.6):
  1. Plano A (DB): SELECT feature_flags.value_json WHERE key='enabled_locales'.
  2. Plano B (env): variavel ENABLED_LOCALES em JSON array ou CSV.
  3. Fail-safe: ["pt-BR"].

Sem cache em memoria nesta fase. Cache-Control: max-age=30 no response
segura a carga no CDN/browser sem introduzir estado compartilhado entre
workers do Gunicorn (simplicidade vence sofisticacao nesta fase).
"""

import json
import os

from flask import Blueprint, jsonify

from db.connection import get_connection, release_connection

config_bp = Blueprint('config', __name__)

ALLOWED_LOCALES = ("pt-BR", "en-US", "es-419", "fr-FR")
FAIL_SAFE_LOCALES = ["pt-BR"]
DEFAULT_LOCALE = "pt-BR"
CACHE_CONTROL_VALUE = "max-age=30"


def _normalize_enabled_locales(value):
    """Valida uma lista de locales contra a whitelist Tier 1.

    Retorna nova lista (mesma ordem, sem duplicatas) se todos os itens
    forem strings validas e a lista for nao-vazia. Retorna None caso
    contrario.
    """
    if not isinstance(value, list) or not value:
        return None
    cleaned = []
    seen = set()
    for item in value:
        if not isinstance(item, str) or item not in ALLOWED_LOCALES:
            return None
        if item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned if cleaned else None


def _parse_enabled_locales_env(raw):
    """Parse de ENABLED_LOCALES env var. Aceita JSON array ou CSV.

    Retorna lista validada (via _normalize_enabled_locales) ou None.
    """
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        return None

    # JSON array primeiro (mais estrito).
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return None
        return _normalize_enabled_locales(parsed)

    # Fallback CSV: "pt-BR,en-US" ou "pt-BR, en-US".
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return _normalize_enabled_locales(parts)


def _load_enabled_locales_from_db():
    """Plano A: le feature_flags.enabled_locales.

    Retorna tupla (locales_list, updated_at_str_or_none) ou None se
    qualquer coisa falhar (DB offline, row ausente, JSON invalido,
    locale fora da whitelist, lista vazia).
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT value_json, updated_at FROM feature_flags "
                "WHERE key = %s",
                ("enabled_locales",),
            )
            row = cur.fetchone()
        if not row:
            return None
        raw_value, updated_at = row
        # psycopg2 costuma devolver JSONB como dict/list ja parseado; se
        # vier como string (driver diferente, extensao nao registrada),
        # tentamos parsear. Outros tipos sao rejeitados.
        if isinstance(raw_value, str):
            try:
                parsed = json.loads(raw_value)
            except (ValueError, TypeError):
                return None
        else:
            parsed = raw_value
        locales = _normalize_enabled_locales(parsed)
        if locales is None:
            return None
        updated_at_str = updated_at.isoformat() if updated_at else None
        return locales, updated_at_str
    except Exception:
        return None
    finally:
        if conn is not None:
            try:
                release_connection(conn)
            except Exception:
                pass


def _resolve_enabled_locales():
    """Aplica a cadeia DB -> env -> fail-safe.

    Retorna (enabled_locales, updated_at, source).
    """
    db_result = _load_enabled_locales_from_db()
    if db_result is not None:
        locales, updated_at = db_result
        return locales, updated_at, "db"

    env_locales = _parse_enabled_locales_env(os.environ.get("ENABLED_LOCALES"))
    if env_locales:
        return env_locales, None, "env"

    return list(FAIL_SAFE_LOCALES), None, "fail_safe"


@config_bp.route('/config/enabled-locales', methods=['GET'])
def enabled_locales():
    """F1.8 - Retorna locales ativos para o frontend ler o kill switch."""
    locales, updated_at, source = _resolve_enabled_locales()
    response = jsonify({
        "enabled_locales": locales,
        "default_locale": DEFAULT_LOCALE,
        "updated_at": updated_at,
        "source": source,
    })
    response.headers["Cache-Control"] = CACHE_CONTROL_VALUE
    return response
