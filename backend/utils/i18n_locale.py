"""F2.4b - Normalizador de locale por request (backend).

Reaproveita a fonte de verdade do kill switch da F1.8 (`routes.config`):
ALLOWED_LOCALES, DEFAULT_LOCALE e _resolve_enabled_locales (DB -> env ->
fail_safe). Nao duplica logica de DB/env/fail-safe.

Contrato:
  - normalize_locale: pura, valida + aplica fallback chain.
  - extract_request_locale: le header X-WG-UI-Locale ou body JSON ui_locale.
  - resolve_request_locale: combina extract + enabled locales + normalize.
  - apply_request_locale: grava resultado em flask.g (sem bloquear request).
  - with_request_locale: decorator de rota que chama apply_request_locale
    antes da view. Nunca transforma locale invalido em erro HTTP.

NUNCA retorna 400 por locale desabilitado. Locale fora da whitelist /
desligado simplesmente cai pelo fallback chain ate o primeiro habilitado.
"""

from functools import wraps

from flask import g, request as flask_request

from routes.config import (
    ALLOWED_LOCALES,
    DEFAULT_LOCALE,
    FAIL_SAFE_LOCALES,
    _resolve_enabled_locales,
)

FALLBACK_CHAIN = {
    "pt-BR": ["pt-BR"],
    "en-US": ["en-US", "pt-BR"],
    "es-419": ["es-419", "en-US", "pt-BR"],
    "fr-FR": ["fr-FR", "en-US", "pt-BR"],
}


def is_allowed_locale(value):
    """Retorna True se value e um locale Tier 1 valido."""
    return isinstance(value, str) and value in ALLOWED_LOCALES


def normalize_locale(requested_locale, enabled_locales=None):
    """Normaliza locale contra whitelist + lista de habilitados.

    Regras:
      - requested_locale fora do Tier 1 -> DEFAULT_LOCALE como ponto de partida.
      - enabled_locales vazio/invalido -> usa FAIL_SAFE_LOCALES (["pt-BR"]).
      - Se requested esta habilitado, retorna requested.
      - Se nao, segue FALLBACK_CHAIN ate achar um habilitado.
      - Nunca retorna locale fora de ALLOWED_LOCALES; nunca retorna None.
    """
    # Normaliza enabled_locales: filtra invalidos; vazio -> fail-safe.
    if not isinstance(enabled_locales, (list, tuple)):
        enabled_clean = list(FAIL_SAFE_LOCALES)
    else:
        enabled_clean = [loc for loc in enabled_locales if is_allowed_locale(loc)]
        if not enabled_clean:
            enabled_clean = list(FAIL_SAFE_LOCALES)

    # Normaliza requested.
    starting = requested_locale if is_allowed_locale(requested_locale) else DEFAULT_LOCALE

    # Aplica fallback chain do starting.
    chain = FALLBACK_CHAIN.get(starting, [starting, DEFAULT_LOCALE])
    for candidate in chain:
        if candidate in enabled_clean:
            return candidate

    # Garantia final: sempre devolve algo dentro da whitelist e habilitado.
    return enabled_clean[0]


def extract_request_locale(req):
    """Le locale solicitado por header ou body JSON. Retorna (value, source).

    Ordem:
      1. Header `X-WG-UI-Locale`
      2. Header `x-wg-ui-locale`
      3. Body JSON `ui_locale` (so se o body for JSON valido)
      4. (None, "default")

    Nao levanta excecao em body invalido / Content-Type inesperado.
    """
    header_value = req.headers.get("X-WG-UI-Locale")
    if not header_value:
        header_value = req.headers.get("x-wg-ui-locale")
    if isinstance(header_value, str) and header_value.strip():
        return header_value.strip(), "header"

    try:
        body = req.get_json(silent=True)
    except Exception:
        body = None
    if isinstance(body, dict):
        body_value = body.get("ui_locale")
        if isinstance(body_value, str) and body_value.strip():
            return body_value.strip(), "body"

    return None, "default"


def resolve_request_locale(req):
    """Combina extract + enabled locales + normalize. Retorna dict pronto."""
    requested, source = extract_request_locale(req)

    try:
        enabled, _updated_at, _enabled_source = _resolve_enabled_locales()
    except Exception:
        enabled = list(FAIL_SAFE_LOCALES)

    effective = normalize_locale(requested, enabled)
    fallback_applied = bool(requested) and is_allowed_locale(requested) and requested != effective

    return {
        "requested_locale": requested,
        "effective_locale": effective,
        "enabled_locales": enabled,
        "fallback_applied": fallback_applied,
        "source": source,
    }


def apply_request_locale(req=None):
    """Grava resultado em flask.g. Nao bloqueia request, nao retorna response."""
    if req is None:
        req = flask_request

    info = resolve_request_locale(req)
    g.wg_requested_locale = info["requested_locale"]
    g.wg_ui_locale = info["effective_locale"]
    g.wg_enabled_locales = info["enabled_locales"]
    g.wg_locale_fallback_applied = info["fallback_applied"]

    if info["fallback_applied"]:
        route_path = getattr(req, "path", "?")
        print(
            f"locale_fallback{{from:{info['requested_locale']}, "
            f"to:{info['effective_locale']}, route:{route_path}}}",
            flush=True,
        )

    return info


def with_request_locale(fn):
    """Decorator: aplica apply_request_locale antes de chamar a view.

    Nunca transforma locale invalido em erro HTTP. Sempre passa adiante.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            apply_request_locale()
        except Exception as exc:
            # Defensivo: se algo quebrar, registra mas NUNCA bloqueia a rota.
            print(f"locale_normalize_error: {exc}", flush=True)
            g.wg_requested_locale = None
            g.wg_ui_locale = DEFAULT_LOCALE
            g.wg_enabled_locales = list(FAIL_SAFE_LOCALES)
            g.wg_locale_fallback_applied = False
        return fn(*args, **kwargs)

    return wrapper
