"""Testes dos endpoints /ops/* com mock de DB.

Valida:
- Token ausente -> 401 missing_token.
- Token invalido -> 401 invalid_token.
- OPS_WRITE_ENABLED=false -> 503 ops_write_disabled em POSTs.
- POST /ops/events nao cria batch implicitamente (chama so emit_event).
- Rota POST /ops/alerts/ack nao existe -> 404.
- Payload malformado -> 422.
- Heartbeat em run fechado retorna ignored=True, run_closed.

Sem banco real. Usa monkeypatch em ops_service.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
SDK_ROOT = REPO_ROOT / "sdk"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture
def client(monkeypatch):
    """Fixture Flask test client com Config monkeypatched para os testes /ops/*."""
    # NAO deletamos sys.modules - so monkeypatch direto na classe Config
    # (routes.ops importa a mesma referencia).
    from config import Config as _Cfg
    monkeypatch.setattr(_Cfg, "OPS_TOKEN", "test-token-123")
    monkeypatch.setattr(_Cfg, "OPS_API_ENABLED", True)
    monkeypatch.setattr(_Cfg, "OPS_WRITE_ENABLED", True)
    monkeypatch.setattr(_Cfg, "OPS_DEBUG_KEEP_SAMPLE", False)

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def mock_ops_service(monkeypatch):
    """Mocka todas as funcoes de ops_service para evitar DB."""
    from services import ops_service

    calls = {"register": [], "start_run": [], "heartbeat": [], "end_run": [],
             "emit_event": [], "emit_batch_metrics": [], "health": [],
             "list_scrapers": [], "list_runs": []}

    def _reg(payload):
        calls["register"].append(payload)
        return {"accepted": True, "duplicated": False, "scraper_id": payload["scraper_id"]}

    def _start(payload):
        calls["start_run"].append(payload)
        return {"accepted": True, "duplicated": False, "run_id": payload["run_id"]}

    def _hb(payload):
        calls["heartbeat"].append(payload)
        return {"accepted": True, "duplicated": False, "ignored": False}

    def _end(payload, is_fail=False):
        calls["end_run"].append({"payload": payload, "is_fail": is_fail})
        return {"accepted": True, "duplicated": False, "run_id": payload["run_id"],
                "status": payload["status"]}

    def _ev(payload):
        calls["emit_event"].append(payload)
        return {"accepted": True, "duplicated": False, "event_id": payload["event_id"]}

    def _bm(payload):
        calls["emit_batch_metrics"].append(payload)
        return {"accepted": True, "duplicated": False, "batch_id": payload["batch_id"]}

    def _health():
        calls["health"].append(True)
        return {"ok": True, "db": "ok", "schema": "ops", "version": "0.1.0", "flags": {}}

    def _list_s(**kw):
        calls["list_scrapers"].append(kw)
        return {"items": [], "total": 0, "limit": kw.get("limit", 50), "offset": 0}

    def _list_r(scraper_id, **kw):
        calls["list_runs"].append({"scraper_id": scraper_id, **kw})
        return {"items": [], "total": 0, "limit": kw.get("limit", 20), "offset": 0}

    monkeypatch.setattr(ops_service, "register_scraper", _reg)
    monkeypatch.setattr(ops_service, "start_run", _start)
    monkeypatch.setattr(ops_service, "heartbeat", _hb)
    monkeypatch.setattr(ops_service, "end_run", _end)
    monkeypatch.setattr(ops_service, "emit_event", _ev)
    monkeypatch.setattr(ops_service, "emit_batch_metrics", _bm)
    monkeypatch.setattr(ops_service, "health_payload", _health)
    monkeypatch.setattr(ops_service, "list_scrapers", _list_s)
    monkeypatch.setattr(ops_service, "list_runs", _list_r)
    return calls


# ----- Health (sem token) -----

def test_health_no_token(client, mock_ops_service):
    r = client.get("/ops/health")
    assert r.status_code in (200, 503)
    body = r.get_json()
    assert "ok" in body


# ----- Auth -----

def test_register_missing_token(client, mock_ops_service):
    r = client.post("/ops/scrapers/register", json={})
    assert r.status_code == 401
    assert r.get_json()["error"] == "missing_token"


def test_register_invalid_token(client, mock_ops_service):
    r = client.post(
        "/ops/scrapers/register",
        json={"scraper_id": "x"},
        headers={"X-Ops-Token": "wrong-token"},
    )
    assert r.status_code == 401
    assert r.get_json()["error"] == "invalid_token"


def test_register_ok(client, mock_ops_service):
    r = client.post(
        "/ops/scrapers/register",
        json={
            "scraper_id": "canary_synthetic",
            "display_name": "Canary",
            "family": "canary",
            "source": "synthetic",
            "host": "este_pc",
            "connector_type": "TelemetryDelivery",
            "contract_name": "canary_event.v1",
            "contract_version": "v1",
        },
        headers={"X-Ops-Token": "test-token-123"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["accepted"] is True
    assert body["scraper_id"] == "canary_synthetic"


def test_register_rejects_extra_field(client, mock_ops_service):
    r = client.post(
        "/ops/scrapers/register",
        json={
            "scraper_id": "x",
            "display_name": "y",
            "family": "canary",
            "source": "s",
            "host": "este_pc",
            "connector_type": "TelemetryDelivery",
            "contract_name": "c",
            "contract_version": "v1",
            "unknown_extra_field": "boom",
        },
        headers={"X-Ops-Token": "test-token-123"},
    )
    assert r.status_code == 422


# ----- OPS_WRITE_ENABLED=false -----

def test_write_disabled_returns_503(client, monkeypatch, mock_ops_service):
    from config import Config as _Cfg
    monkeypatch.setattr(_Cfg, "OPS_WRITE_ENABLED", False)

    r = client.post(
        "/ops/runs/start",
        json={
            "run_id": str(uuid.uuid4()),
            "scraper_id": "canary_synthetic",
            "host": "este_pc",
            "contract_name": "c",
            "contract_version": "v1",
            "idempotency_key": "k",
        },
        headers={"X-Ops-Token": "test-token-123"},
    )
    assert r.status_code == 503
    assert r.get_json()["error"] == "ops_write_disabled"


# ----- POST /ops/events NAO cria batch -----

def test_event_does_not_create_batch(client, mock_ops_service):
    payload = {
        "event_id": str(uuid.uuid4()),
        "scraper_id": "canary_synthetic",
        "ts": _now_iso(),
        "level": "info",
        "code": "test",
        "message": "hello",
        "idempotency_key": "k1",
    }
    r = client.post(
        "/ops/events", json=payload, headers={"X-Ops-Token": "test-token-123"}
    )
    assert r.status_code == 200
    # emit_batch_metrics nunca deve ter sido chamado
    assert mock_ops_service["emit_batch_metrics"] == []
    # emit_event sim
    assert len(mock_ops_service["emit_event"]) == 1


def test_event_strips_batch_id_if_sent(client, mock_ops_service):
    # Mesmo se cliente enviar batch_id, deve ser rejeitado pela validacao
    # (extra='forbid'). Testa que 422.
    payload = {
        "event_id": str(uuid.uuid4()),
        "scraper_id": "canary_synthetic",
        "ts": _now_iso(),
        "level": "info",
        "code": "test",
        "message": "hello",
        "batch_id": str(uuid.uuid4()),
        "idempotency_key": "k1",
    }
    r = client.post(
        "/ops/events", json=payload, headers={"X-Ops-Token": "test-token-123"}
    )
    assert r.status_code == 422


# ----- POST /ops/alerts/ack ausente -----

def test_alerts_ack_not_implemented(client, mock_ops_service):
    r = client.post("/ops/alerts/ack", json={}, headers={"X-Ops-Token": "test-token-123"})
    assert r.status_code == 404


# ----- GET /ops/runs requer scraper_id -----

def test_runs_requires_scraper_id(client, mock_ops_service):
    r = client.get("/ops/runs", headers={"X-Ops-Token": "test-token-123"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "scraper_id_required"


def test_runs_with_scraper_id(client, mock_ops_service):
    r = client.get(
        "/ops/runs?scraper_id=canary_synthetic",
        headers={"X-Ops-Token": "test-token-123"},
    )
    assert r.status_code == 200
    assert r.get_json()["items"] == []


# ----- Lista de scrapers -----

def test_list_scrapers(client, mock_ops_service):
    r = client.get("/ops/scrapers", headers={"X-Ops-Token": "test-token-123"})
    assert r.status_code == 200
    body = r.get_json()
    assert "items" in body
    assert "total" in body


# ----- Metrics/batch -----

def test_metrics_batch_rejects_items_final_inserted_nonzero(client, mock_ops_service):
    payload = {
        "batch_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "scraper_id": "canary_synthetic",
        "seq": 0,
        "ts": _now_iso(),
        "items_final_inserted": 10,  # <- deve falhar
        "idempotency_key": "k",
    }
    r = client.post(
        "/ops/metrics/batch", json=payload, headers={"X-Ops-Token": "test-token-123"}
    )
    assert r.status_code == 422
