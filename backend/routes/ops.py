"""Winegod Data Ops — Flask blueprint `/ops/*` (Fase 1).

Registrado SEM prefixo /api (conforme prompt Fase 1).

Endpoints (10):
    GET  /ops/health
    POST /ops/scrapers/register
    POST /ops/runs/start
    POST /ops/runs/heartbeat
    POST /ops/runs/end
    POST /ops/runs/fail
    POST /ops/events
    POST /ops/metrics/batch
    GET  /ops/scrapers
    GET  /ops/runs?scraper_id=...

Endpoint DELIBERADAMENTE AUSENTE no MVP (D-F0-03):
    POST /ops/alerts/ack
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import Blueprint, jsonify, request

try:
    from config import Config
except ImportError:  # pragma: no cover
    from backend.config import Config  # type: ignore

try:
    from services import ops_service
    from services import ops_schemas
except ImportError:  # pragma: no cover
    from backend.services import ops_service  # type: ignore
    from backend.services import ops_schemas  # type: ignore


ops_bp = Blueprint("ops", __name__)


# ---------------------------------------------------------------------------
# Guards (flags + token)
# ---------------------------------------------------------------------------

def _check_api_enabled():
    """Se OPS_API_ENABLED=false, fake 404 (rota inexistente)."""
    if not Config.OPS_API_ENABLED:
        return jsonify({"error": "not_found"}), 404
    return None


def _check_token() -> Any:
    expected = (Config.OPS_TOKEN or "").strip()
    received = (request.headers.get("X-Ops-Token") or "").strip()
    if not received:
        return jsonify({"error": "missing_token"}), 401
    if not expected or received != expected:
        return jsonify({"error": "invalid_token"}), 401
    return None


def _check_write_enabled() -> Any:
    if not Config.OPS_WRITE_ENABLED:
        return jsonify({"error": "ops_write_disabled"}), 503
    return None


def _json_body() -> Any:
    try:
        body = request.get_json(force=True, silent=False)
        if not isinstance(body, dict):
            return None, (jsonify({"error": "body_must_be_object"}), 400)
        return body, None
    except Exception:
        return None, (jsonify({"error": "invalid_json"}), 400)


def requires_api(f: Callable) -> Callable:
    @wraps(f)
    def wrapper(*a, **kw):
        r = _check_api_enabled()
        if r is not None:
            return r
        return f(*a, **kw)
    return wrapper


def requires_token(f: Callable) -> Callable:
    @wraps(f)
    def wrapper(*a, **kw):
        r = _check_api_enabled()
        if r is not None:
            return r
        r = _check_token()
        if r is not None:
            return r
        return f(*a, **kw)
    return wrapper


def requires_write(f: Callable) -> Callable:
    @wraps(f)
    def wrapper(*a, **kw):
        r = _check_api_enabled()
        if r is not None:
            return r
        r = _check_token()
        if r is not None:
            return r
        r = _check_write_enabled()
        if r is not None:
            return r
        return f(*a, **kw)
    return wrapper


def _validate_payload(model_name: str, body: dict) -> Any:
    """Valida body via Pydantic usando schemas locais do backend.

    Funcao PURA, testavel sem contexto Flask.
    Retorna (payload_validado, (err_dict, status_code)).
    """
    cls = ops_schemas.MODELS.get(model_name)
    if cls is None:
        return None, ({"error": "ops_schema_unavailable", "model": model_name}, 500)
    try:
        obj = cls.model_validate(body)
        return obj.model_dump(mode="json"), None
    except Exception as e:  # pydantic.ValidationError
        return None, ({"error": "validation", "details": str(e)[:2000]}, 422)


def _validate(model_name: str, body: dict) -> Any:
    """Wrapper que aplica jsonify ao erro (requer contexto Flask)."""
    validated, err = _validate_payload(model_name, body)
    if err is None:
        return validated, None
    err_dict, status = err
    return None, (jsonify(err_dict), status)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@ops_bp.route("/ops/health", methods=["GET"])
@requires_api
def ops_health():
    """GET /ops/health — sem token."""
    payload = ops_service.health_payload()
    status_code = 200 if payload["ok"] else 503
    return jsonify(payload), status_code


@ops_bp.route("/ops/scrapers/register", methods=["POST"])
@requires_write
def register_scraper():
    body, err = _json_body()
    if err:
        return err
    validated, err = _validate("ScraperRegisterPayload", body)
    if err:
        return err
    try:
        result = ops_service.register_scraper(validated)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "internal", "detail": str(e)[:500]}), 500


@ops_bp.route("/ops/runs/start", methods=["POST"])
@requires_write
def run_start():
    body, err = _json_body()
    if err:
        return err
    validated, err = _validate("StartRunPayload", body)
    if err:
        return err
    try:
        result = ops_service.start_run(validated)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "internal", "detail": str(e)[:500]}), 500


@ops_bp.route("/ops/runs/heartbeat", methods=["POST"])
@requires_write
def run_heartbeat():
    body, err = _json_body()
    if err:
        return err
    validated, err = _validate("HeartbeatPayload", body)
    if err:
        return err
    try:
        result = ops_service.heartbeat(validated)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "internal", "detail": str(e)[:500]}), 500


@ops_bp.route("/ops/runs/end", methods=["POST"])
@requires_write
def run_end():
    body, err = _json_body()
    if err:
        return err
    validated, err = _validate("EndRunPayload", body)
    if err:
        return err
    try:
        result = ops_service.end_run(validated, is_fail=False)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "internal", "detail": str(e)[:500]}), 500


@ops_bp.route("/ops/runs/fail", methods=["POST"])
@requires_write
def run_fail():
    body, err = _json_body()
    if err:
        return err
    validated, err = _validate("FailRunPayload", body)
    if err:
        return err
    try:
        result = ops_service.end_run(validated, is_fail=True)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "internal", "detail": str(e)[:500]}), 500


@ops_bp.route("/ops/events", methods=["POST"])
@requires_write
def post_event():
    """POST /ops/events — grava APENAS ops.scraper_events. Nao cria batch."""
    body, err = _json_body()
    if err:
        return err
    validated, err = _validate("EventPayload", body)
    if err:
        return err
    # Defesa: remover batch_id se veio por engano (regra Design Freeze v2)
    validated.pop("batch_id", None)
    try:
        result = ops_service.emit_event(validated)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "internal", "detail": str(e)[:500]}), 500


@ops_bp.route("/ops/metrics/batch", methods=["POST"])
@requires_write
def post_batch_metrics():
    body, err = _json_body()
    if err:
        return err
    validated, err = _validate("BatchEventPayload", body)
    if err:
        return err
    try:
        result = ops_service.emit_batch_metrics(validated)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "internal", "detail": str(e)[:500]}), 500


@ops_bp.route("/ops/scrapers", methods=["GET"])
@requires_token
def get_scrapers():
    family = request.args.get("family")
    host = request.args.get("host")
    status = request.args.get("status")
    try:
        limit = min(int(request.args.get("limit", 50)), 500)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_pagination"}), 400
    try:
        result = ops_service.list_scrapers(
            family=family, host=host, status=status,
            limit=limit, offset=offset,
        )
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "internal", "detail": str(e)[:500]}), 500


@ops_bp.route("/ops/runs", methods=["GET"])
@requires_token
def get_runs():
    scraper_id = request.args.get("scraper_id")
    if not scraper_id:
        return jsonify({"error": "scraper_id_required"}), 400
    status = request.args.get("status")
    since = request.args.get("since")
    try:
        limit = min(int(request.args.get("limit", 20)), 500)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_pagination"}), 400
    try:
        result = ops_service.list_runs(
            scraper_id=scraper_id, status=status, since=since,
            limit=limit, offset=offset,
        )
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "internal", "detail": str(e)[:500]}), 500


# ---------------------------------------------------------------------------
# Ausente deliberadamente (D-F0-03):
#     POST /ops/alerts/ack
# Se um cliente chamar, Flask responde 404 natural (rota nao registrada).
# ---------------------------------------------------------------------------
