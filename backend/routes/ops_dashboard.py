"""Winegod Data Ops — Dashboard blueprint (Fase 3A).

Rotas HTML sob `/ops/...` + rotas JSON internas sob `/ops/ui/api/...`.

Todas as rotas HTML e UI-API respeitam `OPS_DASHBOARD_ENABLED`:
- Se false -> 404 (rota "não existe").

Login por `OPS_DASHBOARD_TOKEN` com cookie httponly SameSite=Lax (7 dias).
Endpoints JSON legados `/ops/scrapers` e `/ops/runs` do blueprint `ops_bp`
continuam intactos (cuidado para NÃO colidir — usamos `/ops/ui/api/*` aqui).

Regras de segurança:
- Nunca logar `OPS_DASHBOARD_TOKEN`.
- `hmac.compare_digest` para comparação constante.
- Rate limit simples in-memory: 3 tentativas por IP em 15min.
- Sem `/ops/alerts/ack` — propositalmente ausente (D-F0-03).
- Sem WhatsApp, passwordless, magic link — sub-projetos pós-MVP.
- Labels "Observado" / "Enviado" — nunca "inseridos/contribuição".
"""
from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

from flask import (
    Blueprint, abort, jsonify, make_response, redirect, render_template,
    request, session, url_for,
)

try:
    from config import Config
except ImportError:  # pragma: no cover
    from backend.config import Config  # type: ignore

try:
    from db.connection import get_connection, release_connection
except ImportError:  # pragma: no cover
    from backend.db.connection import get_connection, release_connection  # type: ignore


ops_dashboard_bp = Blueprint(
    "ops_dashboard",
    __name__,
    template_folder="../templates",
    static_folder="../static",
)


# ---------------------------------------------------------------------------
# Rate limiter simples in-memory
# ---------------------------------------------------------------------------

_LOGIN_ATTEMPTS: Dict[str, List[float]] = defaultdict(list)
_MAX_ATTEMPTS = 3
_WINDOW_SECONDS = 15 * 60


def _rate_limited(ip: str) -> bool:
    now = time.time()
    cutoff = now - _WINDOW_SECONDS
    _LOGIN_ATTEMPTS[ip] = [t for t in _LOGIN_ATTEMPTS[ip] if t >= cutoff]
    return len(_LOGIN_ATTEMPTS[ip]) >= _MAX_ATTEMPTS


def _record_attempt(ip: str) -> None:
    _LOGIN_ATTEMPTS[ip].append(time.time())


# ---------------------------------------------------------------------------
# Helpers puros (testáveis sem DB): classificação de saúde e dedup determinístico
# ---------------------------------------------------------------------------

_FAILED_STATUSES = {"failed", "timeout", "error"}
_RUNNING_STATUSES = {"started", "running"}


def classify_freshness(last_end, freshness_hours, last_status, now=None):
    """Classifica freshness/saúde de um scraper considerando status do último run.

    - 'never'        -> sem run.
    - 'running'      -> last run em started/running.
    - 'error'        -> last run em failed/timeout/error (NÃO conta como saudável).
    - 'fresh'        -> last success dentro da janela SLA.
    - 'stale'        -> last success entre 1x e 3x a janela.
    - 'very_stale'   -> last success além de 3x a janela.
    """
    import datetime as _dt
    if last_end is None:
        return "never"
    if last_status in _RUNNING_STATUSES:
        return "running"
    if last_status in _FAILED_STATUSES:
        return "error"
    # success (ou legacy sem status)
    now = now or _dt.datetime.now(_dt.timezone.utc)
    delta = now - last_end
    hours = delta.total_seconds() / 3600
    if hours <= freshness_hours:
        return "fresh"
    elif hours <= 3 * freshness_hours:
        return "stale"
    else:
        return "very_stale"


def is_healthy(last_end, freshness_hours, last_status, now=None):
    """Healthy = last run success E dentro da janela SLA. Qualquer outro caso não é healthy."""
    return classify_freshness(last_end, freshness_hours, last_status, now) == "fresh"


def compute_fake_alert_keys(scraper_id):
    """scope_key + dedup_key determinísticos para POST /ops/alerts/fake.

    Repetidas chamadas para o mesmo scraper devem produzir o MESMO dedup_key,
    permitindo ON CONFLICT (dedup_key) DO UPDATE incrementar occurrences.
    """
    import hashlib
    sid = scraper_id or "__global__"
    scope_key = f"dashboard_fake_test:{sid}"
    dedup_key = hashlib.sha256(
        f"{sid}|dashboard.fake_test|P3|{scope_key}".encode()
    ).hexdigest()
    return scope_key, dedup_key


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def _dashboard_enabled() -> bool:
    return bool(getattr(Config, "OPS_DASHBOARD_ENABLED", False))


def _token_configured() -> bool:
    tok = getattr(Config, "OPS_DASHBOARD_TOKEN", "") or ""
    return bool(tok.strip())


def _valid_session() -> bool:
    return bool(session.get("ops_dashboard_ok"))


def requires_dashboard(f: Callable) -> Callable:
    @wraps(f)
    def wrapper(*a, **kw):
        if not _dashboard_enabled():
            abort(404)
        return f(*a, **kw)
    return wrapper


def requires_auth(f: Callable) -> Callable:
    @wraps(f)
    def wrapper(*a, **kw):
        if not _dashboard_enabled():
            abort(404)
        if not _valid_session():
            # HTML routes redirect; API routes return 401.
            if request.path.startswith("/ops/ui/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("ops_dashboard.login_get"))
        return f(*a, **kw)
    return wrapper


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------

@ops_dashboard_bp.route("/ops/login", methods=["GET"])
@requires_dashboard
def login_get():
    return render_template("ops/login.html", error=None)


@ops_dashboard_bp.route("/ops/login", methods=["POST"])
@requires_dashboard
def login_post():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    if _rate_limited(ip):
        return render_template("ops/login.html", error="rate_limited"), 429

    token_input = (request.form.get("token") or "").strip()
    configured = (getattr(Config, "OPS_DASHBOARD_TOKEN", "") or "").strip()

    if not configured:
        # Dashboard habilitado mas sem token -> não libera.
        _record_attempt(ip)
        return render_template("ops/login.html", error="not_configured"), 401

    if not token_input or not hmac.compare_digest(token_input, configured):
        _record_attempt(ip)
        return render_template("ops/login.html", error="invalid"), 401

    session.clear()
    session["ops_dashboard_ok"] = True
    session["ops_login_at"] = int(time.time())
    # Limpa tentativas do IP após sucesso.
    _LOGIN_ATTEMPTS.pop(ip, None)

    resp = make_response(redirect(url_for("ops_dashboard.home")))
    return resp


@ops_dashboard_bp.route("/ops/logout", methods=["GET", "POST"])
@requires_dashboard
def logout():
    session.clear()
    return redirect(url_for("ops_dashboard.login_get"))


# ---------------------------------------------------------------------------
# HTML — home / detail / alerts
# ---------------------------------------------------------------------------

@ops_dashboard_bp.route("/ops", methods=["GET"])
@ops_dashboard_bp.route("/ops/", methods=["GET"])
@ops_dashboard_bp.route("/ops/home", methods=["GET"])
@requires_auth
def home():
    return render_template("ops/home.html")


@ops_dashboard_bp.route("/ops/scraper/<scraper_id>", methods=["GET"])
@requires_auth
def scraper_detail(scraper_id: str):
    # Validação leve: scraper_id <= 128 chars, printáveis.
    if not scraper_id or len(scraper_id) > 128:
        abort(404)
    return render_template("ops/scraper_detail.html", scraper_id=scraper_id)


@ops_dashboard_bp.route("/ops/alerts", methods=["GET"])
@requires_auth
def alerts():
    return render_template("ops/alerts.html")


# ---------------------------------------------------------------------------
# UI-API JSON (polling 10s consome isto)
# ---------------------------------------------------------------------------

@ops_dashboard_bp.route("/ops/ui/api/summary", methods=["GET"])
@requires_auth
def api_summary():
    """Cards da Home: scrapers ativos, observado hoje, enviado hoje, SLA."""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # scrapers ativos (em RUN)
                cur.execute("""
                    SELECT count(DISTINCT scraper_id)
                    FROM ops.scraper_runs
                    WHERE status IN ('started','running')
                """)
                active = cur.fetchone()[0] or 0

                # observado hoje (items_extracted)
                cur.execute("""
                    SELECT coalesce(sum(items_extracted), 0)
                    FROM ops.scraper_runs
                    WHERE started_at >= date_trunc('day', now())
                """)
                observed_today = int(cur.fetchone()[0] or 0)

                # enviado hoje (items_sent)
                cur.execute("""
                    SELECT coalesce(sum(items_sent), 0)
                    FROM ops.scraper_runs
                    WHERE started_at >= date_trunc('day', now())
                """)
                sent_today = int(cur.fetchone()[0] or 0)

                # SLA health = % de scrapers active com last run SUCCESS E fresh.
                # last_status IN ('failed','timeout','error') NÃO conta como saudável.
                # last_status IN ('started','running') também NÃO conta (ainda sem resultado).
                cur.execute("""
                    WITH last_run AS (
                      SELECT DISTINCT ON (scraper_id)
                        scraper_id, ended_at AS last_end, status AS last_status
                      FROM ops.scraper_runs
                      ORDER BY scraper_id, started_at DESC
                    )
                    SELECT
                      count(*) AS total,
                      count(*) FILTER (
                        WHERE lr.last_end IS NOT NULL
                          AND lr.last_status = 'success'
                          AND lr.last_end >= now() - (rg.freshness_sla_hours || ' hours')::interval
                      ) AS healthy
                    FROM ops.scraper_registry rg
                    LEFT JOIN last_run lr ON lr.scraper_id = rg.scraper_id
                    WHERE rg.status IN ('active','registered')
                """)
                row = cur.fetchone()
                total = int(row[0] or 0)
                healthy = int(row[1] or 0)
                sla_pct = round(100.0 * healthy / total, 1) if total else 100.0
        finally:
            release_connection(conn)

        return jsonify({
            "scrapers_ativos_agora": active,
            "observado_hoje": observed_today,
            "enviado_hoje": sent_today,
            "sla_health_pct": sla_pct,
        })
    except Exception as e:  # pragma: no cover
        return jsonify({"error": "internal", "detail": str(e)[:200]}), 500


@ops_dashboard_bp.route("/ops/ui/api/scrapers", methods=["GET"])
@requires_auth
def api_scrapers():
    """Lista para tabela da Home."""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                      rg.scraper_id, rg.display_name, rg.family, rg.host, rg.status,
                      rg.freshness_sla_hours,
                      (SELECT started_at FROM ops.scraper_runs r
                         WHERE r.scraper_id = rg.scraper_id
                         ORDER BY started_at DESC LIMIT 1) AS last_started,
                      (SELECT ended_at FROM ops.scraper_runs r
                         WHERE r.scraper_id = rg.scraper_id
                         ORDER BY started_at DESC LIMIT 1) AS last_ended,
                      (SELECT status FROM ops.scraper_runs r
                         WHERE r.scraper_id = rg.scraper_id
                         ORDER BY started_at DESC LIMIT 1) AS last_run_status,
                      coalesce((
                        SELECT sum(items_extracted) FROM ops.scraper_runs r
                        WHERE r.scraper_id = rg.scraper_id
                          AND r.started_at >= date_trunc('day', now())
                      ), 0) AS observed_today,
                      coalesce((
                        SELECT sum(items_sent) FROM ops.scraper_runs r
                        WHERE r.scraper_id = rg.scraper_id
                          AND r.started_at >= date_trunc('day', now())
                      ), 0) AS sent_today
                    FROM ops.scraper_registry rg
                    ORDER BY rg.family, rg.scraper_id
                    LIMIT 500
                """)
                rows = cur.fetchall()
                items = []
                for r in rows:
                    last_end = r[7]
                    freshness_hours = r[5]
                    last_run_status = r[8]
                    freshness = classify_freshness(
                        last_end, freshness_hours, last_run_status
                    )
                    items.append({
                        "scraper_id": r[0],
                        "display_name": r[1],
                        "family": r[2],
                        "host": r[3],
                        "status": r[4],
                        "freshness_sla_hours": r[5],
                        "last_started": r[6].isoformat() if r[6] else None,
                        "last_ended": r[7].isoformat() if r[7] else None,
                        "last_run_status": r[8],
                        "observado_hoje": int(r[9] or 0),
                        "enviado_hoje": int(r[10] or 0),
                        "freshness": freshness,
                    })
        finally:
            release_connection(conn)
        return jsonify({"items": items, "total": len(items)})
    except Exception as e:  # pragma: no cover
        return jsonify({"error": "internal", "detail": str(e)[:200]}), 500


@ops_dashboard_bp.route("/ops/ui/api/scraper/<scraper_id>", methods=["GET"])
@requires_auth
def api_scraper_detail(scraper_id: str):
    """Drill-down completo de 1 scraper (10 seções)."""
    if not scraper_id or len(scraper_id) > 128:
        return jsonify({"error": "invalid_scraper_id"}), 400

    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # Seção 1: identidade (registry)
                cur.execute("""
                    SELECT scraper_id, display_name, family, source, variant, host,
                           status, contract_name, contract_version,
                           freshness_sla_hours, declared_fields, tags,
                           can_create_wine_sources, requires_dq_v3, requires_matching,
                           manifest_hash, updated_at
                    FROM ops.scraper_registry WHERE scraper_id = %s
                """, (scraper_id,))
                row = cur.fetchone()
                if not row:
                    return jsonify({"error": "scraper_not_found"}), 404
                identity = {
                    "scraper_id": row[0], "display_name": row[1], "family": row[2],
                    "source": row[3], "variant": row[4], "host": row[5],
                    "status": row[6], "contract_name": row[7],
                    "contract_version": row[8], "freshness_sla_hours": row[9],
                    "declared_fields": row[10] or [], "tags": row[11] or [],
                    "can_create_wine_sources": row[12],
                    "requires_dq_v3": row[13], "requires_matching": row[14],
                    "manifest_hash": row[15],
                    "updated_at": row[16].isoformat() if row[16] else None,
                }

                # Seção 2: cards de saúde
                cur.execute("""
                    SELECT run_id, status, started_at, last_heartbeat_at, ended_at,
                           duration_ms, items_extracted, items_valid_local, items_sent,
                           items_final_inserted, batches_total,
                           error_count_transient, error_count_fatal,
                           retry_count, rate_limit_hits
                    FROM ops.scraper_runs WHERE scraper_id = %s
                    ORDER BY started_at DESC LIMIT 1
                """, (scraper_id,))
                lr = cur.fetchone()
                last_run = None
                if lr:
                    last_run = {
                        "run_id": str(lr[0]), "status": lr[1],
                        "started_at": lr[2].isoformat() if lr[2] else None,
                        "last_heartbeat_at": lr[3].isoformat() if lr[3] else None,
                        "ended_at": lr[4].isoformat() if lr[4] else None,
                        "duration_ms": lr[5],
                        "items_extracted": int(lr[6] or 0),
                        "items_valid_local": int(lr[7] or 0),
                        "items_sent": int(lr[8] or 0),
                        "items_final_inserted": int(lr[9] or 0),
                        "batches_total": int(lr[10] or 0),
                        "error_count_transient": int(lr[11] or 0),
                        "error_count_fatal": int(lr[12] or 0),
                        "retry_count": int(lr[13] or 0),
                        "rate_limit_hits": int(lr[14] or 0),
                    }

                # Seção 3: funil do último run (batch_metrics agregado)
                funnel = None
                if lr:
                    cur.execute("""
                        SELECT
                          coalesce(sum(items_extracted),0),
                          coalesce(sum(items_valid_local),0),
                          coalesce(sum(items_sent),0),
                          coalesce(sum(items_accepted_ready),0),
                          coalesce(sum(items_rejected_notwine),0),
                          coalesce(sum(items_needs_enrichment),0),
                          coalesce(sum(items_uncertain),0),
                          coalesce(sum(items_duplicate),0),
                          coalesce(sum(items_final_inserted),0)
                        FROM ops.batch_metrics
                        WHERE run_id = %s
                    """, (lr[0],))
                    fr = cur.fetchone()
                    funnel = {
                        "extracted": int(fr[0] or 0),
                        "valid_local": int(fr[1] or 0),
                        "sent": int(fr[2] or 0),
                        "accepted_ready": int(fr[3] or 0),
                        "rejected_notwine": int(fr[4] or 0),
                        "needs_enrichment": int(fr[5] or 0),
                        "uncertain": int(fr[6] or 0),
                        "duplicate": int(fr[7] or 0),
                        "final_inserted": int(fr[8] or 0),
                    }

                # Seção 4: velocidade (heartbeats últimas 3h)
                speed = []
                if lr:
                    cur.execute("""
                        SELECT ts, items_collected_so_far, items_per_minute
                        FROM ops.scraper_heartbeats
                        WHERE run_id = %s
                        ORDER BY ts DESC LIMIT 180
                    """, (lr[0],))
                    for hb in cur.fetchall():
                        speed.append({
                            "ts": hb[0].isoformat() if hb[0] else None,
                            "items_collected_so_far": int(hb[1] or 0),
                            "items_per_minute": float(hb[2]) if hb[2] is not None else None,
                        })
                    speed = list(reversed(speed))

                # Seção 5: cobertura de campos declarados
                field_coverage = {}
                if lr:
                    cur.execute("""
                        SELECT field_coverage FROM ops.batch_metrics
                        WHERE run_id = %s
                        ORDER BY ts DESC LIMIT 1
                    """, (lr[0],))
                    fc = cur.fetchone()
                    if fc and fc[0]:
                        field_coverage = fc[0]

                # Seção 6: dedup 3 níveis
                dedup = {"intra": 0, "cross_run": 0, "cross_scraper": 0}
                if lr:
                    cur.execute("""
                        SELECT
                          coalesce(sum(items_duplicate_intra),0),
                          coalesce(sum(items_duplicate_cross_run),0),
                          coalesce(sum(items_duplicate_cross_scraper),0)
                        FROM ops.ingestion_batches WHERE run_id = %s
                    """, (lr[0],))
                    d = cur.fetchone()
                    dedup = {
                        "intra": int(d[0] or 0),
                        "cross_run": int(d[1] or 0),
                        "cross_scraper": int(d[2] or 0),
                    }

                # Seção 7: histórico últimos 20 runs
                cur.execute("""
                    SELECT run_id, started_at, ended_at, duration_ms,
                           items_extracted, items_sent, status
                    FROM ops.scraper_runs WHERE scraper_id = %s
                    ORDER BY started_at DESC LIMIT 20
                """, (scraper_id,))
                history = []
                for h in cur.fetchall():
                    history.append({
                        "run_id": str(h[0]),
                        "started_at": h[1].isoformat() if h[1] else None,
                        "ended_at": h[2].isoformat() if h[2] else None,
                        "duration_ms": h[3],
                        "items_extracted": int(h[4] or 0),
                        "items_sent": int(h[5] or 0),
                        "status": h[6],
                    })

                # Seção 8: eventos/alertas 24h
                cur.execute("""
                    SELECT ts, level, code, message
                    FROM ops.scraper_events
                    WHERE scraper_id = %s AND ts >= now() - interval '24 hours'
                      AND level IN ('warn','error','anomaly')
                    ORDER BY ts DESC LIMIT 50
                """, (scraper_id,))
                events = []
                for ev in cur.fetchall():
                    events.append({
                        "ts": ev[0].isoformat() if ev[0] else None,
                        "level": ev[1], "code": ev[2], "message": ev[3],
                    })

                cur.execute("""
                    SELECT alert_id, priority, code, title, description,
                           status, first_seen, last_seen, occurrences
                    FROM ops.scraper_alerts
                    WHERE (scraper_id = %s OR scraper_id IS NULL)
                      AND status = 'open'
                    ORDER BY priority, last_seen DESC LIMIT 20
                """, (scraper_id,))
                open_alerts = []
                for al in cur.fetchall():
                    open_alerts.append({
                        "alert_id": str(al[0]), "priority": al[1],
                        "code": al[2], "title": al[3], "description": al[4],
                        "status": al[5],
                        "first_seen": al[6].isoformat() if al[6] else None,
                        "last_seen": al[7].isoformat() if al[7] else None,
                        "occurrences": int(al[8] or 0),
                    })

                # Seção 9: observado/enviado 30d (NUNCA "inseridos/contribuição")
                cur.execute("""
                    SELECT
                      coalesce(sum(items_extracted),0) AS observed,
                      coalesce(sum(items_sent),0)      AS sent,
                      count(*)                         AS runs
                    FROM ops.scraper_runs
                    WHERE scraper_id = %s
                      AND started_at >= now() - interval '30 days'
                """, (scraper_id,))
                obs = cur.fetchone()
                observed_30d = {
                    "observado_30d": int(obs[0] or 0),
                    "enviado_30d": int(obs[1] or 0),
                    "runs_30d": int(obs[2] or 0),
                }

                # Seção 10: lineage por batch (últimos 10)
                lineage = []
                if lr:
                    cur.execute("""
                        SELECT b.batch_id, b.seq, b.started_at, l.source_system,
                               l.source_kind, l.source_pointer, l.source_record_count
                        FROM ops.ingestion_batches b
                        LEFT JOIN ops.source_lineage l ON l.batch_id = b.batch_id
                        WHERE b.run_id = %s
                        ORDER BY b.seq LIMIT 10
                    """, (lr[0],))
                    for ln in cur.fetchall():
                        lineage.append({
                            "batch_id": str(ln[0]), "seq": ln[1],
                            "started_at": ln[2].isoformat() if ln[2] else None,
                            "source_system": ln[3], "source_kind": ln[4],
                            "source_pointer": ln[5],
                            "source_record_count": int(ln[6]) if ln[6] is not None else None,
                        })
        finally:
            release_connection(conn)

        return jsonify({
            "identity": identity,
            "last_run": last_run,
            "funnel": funnel,
            "speed": speed,
            "field_coverage": field_coverage,
            "dedup": dedup,
            "history": history,
            "events_24h": events,
            "open_alerts": open_alerts,
            "observed_30d": observed_30d,
            "lineage": lineage,
        })
    except Exception as e:  # pragma: no cover
        return jsonify({"error": "internal", "detail": str(e)[:200]}), 500


@ops_dashboard_bp.route("/ops/ui/api/alerts", methods=["GET"])
@requires_auth
def api_alerts():
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT alert_id, scraper_id, priority, code, title,
                           description, status, occurrences,
                           first_seen, last_seen, needs_human
                    FROM ops.scraper_alerts
                    ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END,
                             priority, last_seen DESC
                    LIMIT 200
                """)
                items = []
                for r in cur.fetchall():
                    items.append({
                        "alert_id": str(r[0]), "scraper_id": r[1],
                        "priority": r[2], "code": r[3], "title": r[4],
                        "description": r[5], "status": r[6],
                        "occurrences": int(r[7] or 0),
                        "first_seen": r[8].isoformat() if r[8] else None,
                        "last_seen": r[9].isoformat() if r[9] else None,
                        "needs_human": bool(r[10]),
                    })
        finally:
            release_connection(conn)
        return jsonify({"items": items, "total": len(items)})
    except Exception as e:  # pragma: no cover
        return jsonify({"error": "internal", "detail": str(e)[:200]}), 500


# ---------------------------------------------------------------------------
# Alertas sintéticos (só para UX; jamais envia WhatsApp/email)
# ---------------------------------------------------------------------------

@ops_dashboard_bp.route("/ops/alerts/fake", methods=["POST"])
@requires_auth
def post_alert_fake():
    """Gera alerta sintético P3 em `ops.scraper_alerts`. Nunca envia externo.

    dedup_key DETERMINÍSTICO (scraper_id|code|priority|scope_key) para que
    chamadas repetidas incrementem `occurrences` via ON CONFLICT em vez de
    criar alertas duplicados. Regra de dedup deterministico dos alertas.
    """
    import uuid as _uuid

    scraper_id = (request.json or {}).get("scraper_id") if request.is_json else None
    code = "dashboard.fake_test"
    priority = "P3"
    scope_key, dedup_key = compute_fake_alert_keys(scraper_id)

    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ops.scraper_alerts
                      (alert_id, scraper_id, priority, code, scope_key, title,
                       description, dedup_key, status, needs_human)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'open', false)
                    ON CONFLICT (dedup_key) DO UPDATE SET
                      last_seen = now(), occurrences = ops.scraper_alerts.occurrences + 1
                    RETURNING alert_id
                """, (
                    str(_uuid.uuid4()), scraper_id, priority, code, scope_key,
                    "Alerta sintético de teste",
                    "Alerta P3 criado pelo dashboard para prova visual. NÃO foi enviado externamente.",
                    dedup_key,
                ))
                aid = cur.fetchone()[0]
            conn.commit()
        finally:
            release_connection(conn)
        return jsonify({"accepted": True, "alert_id": str(aid), "external": False})
    except Exception as e:  # pragma: no cover
        return jsonify({"error": "internal", "detail": str(e)[:200]}), 500
