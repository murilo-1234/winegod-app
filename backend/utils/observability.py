"""F11.2 + F11.4 - Observabilidade backend (Sentry + PostHog).

Este modulo concentra:

  - `init_sentry(flask_app)`  -> ativa Sentry se SENTRY_DSN estiver setada.
                                  No-op silencioso quando ausente.
  - `_attach_locale_tags()`   -> before_request hook que marca o scope do
                                  Sentry com `locale` e `market_country`
                                  a partir de `g.wg_ui_locale` e do header
                                  `X-WG-Market-Country` (fallback defensivo).
  - `init_posthog()`          -> instancia um client PostHog backend (no-op
                                  silencioso quando POSTHOG_API_KEY ausente).
                                  Usado por `emit_locale_fallback_applied`.
  - `emit_locale_fallback_applied(info)` -> F11.4: dispara evento do
                                  fluxo de fallback de locale resolvido em
                                  `utils/i18n_locale.apply_request_locale`.

Regras:

  - Nenhum erro de telemetria pode quebrar um request. Todo caminho esta
    envolto em `try/except` com log textual em stderr.
  - Nenhum DSN/API key e hardcoded. Tudo vem de env.
  - Quando as envs nao estao setadas, as funcoes sao no-op silencioso:
    o modulo pode ser importado e exercitado em dev/test sem credenciais.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
except ImportError:  # pragma: no cover - fallback se SDK ausente.
    sentry_sdk = None
    FlaskIntegration = None  # type: ignore[assignment]

try:
    from posthog import Posthog
except ImportError:  # pragma: no cover
    Posthog = None  # type: ignore[assignment]


_posthog_client: Optional[Any] = None
_sentry_ready: bool = False


def init_sentry(flask_app) -> bool:
    """Inicializa Sentry com FlaskIntegration. Retorna True se ativou.

    Env vars relevantes (todas opcionais):
      - SENTRY_DSN            : se ausente, no-op.
      - SENTRY_ENVIRONMENT    : `production`, `staging`, `development`, etc.
      - SENTRY_RELEASE        : opcional, commit sha/tag.
      - SENTRY_TRACES_SAMPLE_RATE : fracao 0..1, default 0.0.

    F11.2 CORRETIVO: NAO registra mais `before_request` para anexar
    tags de locale/market. O hook `before_request` rodava antes do
    decorator `@with_request_locale`, resultando em tags perdidas.
    A partir deste corretivo, o anexo e feito por `attach_sentry_locale_tags`
    chamado explicitamente por `apply_request_locale` (que ja e o ponto
    onde `g.wg_ui_locale` e populado).
    """
    global _sentry_ready

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn or sentry_sdk is None:
        return False

    try:
        traces_sample_rate = float(
            os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")
        )
    except ValueError:
        traces_sample_rate = 0.0

    try:
        integrations = [FlaskIntegration()] if FlaskIntegration else []
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT") or None,
            release=os.environ.get("SENTRY_RELEASE") or None,
            traces_sample_rate=traces_sample_rate,
            integrations=integrations,
            send_default_pii=False,
        )
        _sentry_ready = True
    except Exception as exc:
        print(f"sentry_init_error: {exc}", flush=True)
        return False

    return True


def attach_sentry_locale_tags(locale, market_country) -> None:
    """F11.2 CORRETIVO - anexa `locale` e `market_country` ao scope do
    Sentry apos a resolucao de locale por request ter rodado.

    Chamado explicitamente por `utils.i18n_locale.apply_request_locale` com
    os valores ja resolvidos. Ordem garantida:

        request chega
          -> @with_request_locale
             -> apply_request_locale
                -> set g.wg_ui_locale / g.wg_market_country
                -> attach_sentry_locale_tags(locale, market) <-- AQUI
          -> view executa com scope do Sentry pronto

    Defensivos:
      - no-op se Sentry nao foi inicializado
      - no-op se nenhum valor valido foi resolvido
      - qualquer excecao e logada em stderr e silenciada (telemetria
        nunca quebra request)
    """
    if not _sentry_ready or sentry_sdk is None:
        return

    try:
        if isinstance(locale, str) and locale:
            sentry_sdk.set_tag("locale", locale)

        if isinstance(market_country, str) and market_country.strip():
            sentry_sdk.set_tag("market_country", market_country.strip().upper())
    except Exception as exc:
        print(f"sentry_tag_error: {exc}", flush=True)


def _best_market_signal(req) -> str:
    """F11.2 CORRETIVO - melhor sinal disponivel de `market_country` fora
    de um contexto especifico de rota. Ordem:

      1. Header `X-WG-Market-Country`
      2. Body JSON `market_country` (silencioso se nao JSON)
      3. Cookie `wg_market_country` (se existir no futuro; hoje nao)
      4. String vazia (caller trata como no-op)
    """
    try:
        market = req.headers.get("X-WG-Market-Country")
        if not market:
            market = req.headers.get("x-wg-market-country")
        if isinstance(market, str) and market.strip():
            return market.strip().upper()
    except Exception:
        pass

    try:
        body = req.get_json(silent=True)
        if isinstance(body, dict):
            value = body.get("market_country")
            if isinstance(value, str) and value.strip():
                return value.strip().upper()
    except Exception:
        pass

    return ""


def init_posthog() -> bool:
    """Inicializa cliente PostHog backend. Retorna True se ativou.

    Env vars:
      - POSTHOG_API_KEY  : obrigatoria para ativar.
      - POSTHOG_HOST     : default `https://us.i.posthog.com`.
    """
    global _posthog_client

    api_key = os.environ.get("POSTHOG_API_KEY", "").strip()
    if not api_key or Posthog is None:
        _posthog_client = None
        return False

    host = os.environ.get("POSTHOG_HOST", "https://us.i.posthog.com").strip()

    try:
        _posthog_client = Posthog(project_api_key=api_key, host=host)
    except Exception as exc:
        print(f"posthog_init_error: {exc}", flush=True)
        _posthog_client = None
        return False

    return True


def get_posthog_client():
    """Acessor somente-leitura do client PostHog. Pode ser None."""
    return _posthog_client


def emit_locale_fallback_applied(info: Dict[str, Any]) -> None:
    """F11.4 - dispara `locale_fallback_applied` no PostHog.

    No-op se `_posthog_client` e None. Nunca levanta.
    """
    if _posthog_client is None:
        return

    try:
        from flask import g, request as flask_request
    except Exception:
        g = None  # type: ignore[assignment]
        flask_request = None  # type: ignore[assignment]

    try:
        distinct_id = "anonymous"
        try:
            if g is not None:
                user = getattr(g, "wg_current_user", None)
                if isinstance(user, dict):
                    user_id = user.get("id") or user.get("user_id")
                    if user_id:
                        distinct_id = str(user_id)
        except Exception:
            pass

        route_path = "?"
        try:
            if flask_request is not None:
                route_path = getattr(flask_request, "path", "?")
        except Exception:
            pass

        properties = {
            "requested_locale": info.get("requested_locale"),
            "effective_locale": info.get("effective_locale"),
            "source": info.get("source"),
            "route": route_path,
        }
        _posthog_client.capture(
            distinct_id=distinct_id,
            event="locale_fallback_applied",
            properties=properties,
        )
    except Exception as exc:
        print(f"posthog_capture_error: {exc}", flush=True)
