"""Testes de idempotencia dos endpoints /ops/*.

Foco em comportamento observavel via mock do service:
- start duplicado deve retornar duplicated:true.
- heartbeat com mesma key deve retornar duplicated:true.
- heartbeat em run fechado deve retornar ignored:true + note=run_closed.
- event duplicado -> duplicated:true.

Usa mock de ops_service (sem DB).
"""
from __future__ import annotations

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
    from config import Config as _Cfg
    monkeypatch.setattr(_Cfg, "OPS_TOKEN", "tok")
    monkeypatch.setattr(_Cfg, "OPS_API_ENABLED", True)
    monkeypatch.setattr(_Cfg, "OPS_WRITE_ENABLED", True)

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_start_duplicated(client, monkeypatch):
    from services import ops_service

    seen = {}

    def _start(payload):
        rid = payload["run_id"]
        dup = rid in seen
        seen[rid] = True
        return {"accepted": True, "duplicated": dup, "run_id": rid}

    monkeypatch.setattr(ops_service, "start_run", _start)

    rid = str(uuid.uuid4())
    body = {
        "run_id": rid,
        "scraper_id": "x",
        "host": "este_pc",
        "contract_name": "c",
        "contract_version": "v1",
        "idempotency_key": rid,
    }
    r1 = client.post("/ops/runs/start", json=body, headers={"X-Ops-Token": "tok"})
    r2 = client.post("/ops/runs/start", json=body, headers={"X-Ops-Token": "tok"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.get_json()["duplicated"] is False
    assert r2.get_json()["duplicated"] is True


def test_heartbeat_run_closed(client, monkeypatch):
    from services import ops_service

    def _hb(payload):
        return {
            "accepted": True,
            "duplicated": True,
            "ignored": True,
            "note": "run_closed",
        }

    monkeypatch.setattr(ops_service, "heartbeat", _hb)

    body = {
        "run_id": str(uuid.uuid4()),
        "scraper_id": "x",
        "ts": _now_iso(),
        "items_collected_so_far": 10,
        "idempotency_key": "k",
    }
    r = client.post("/ops/runs/heartbeat", json=body, headers={"X-Ops-Token": "tok"})
    assert r.status_code == 200
    body_out = r.get_json()
    assert body_out["ignored"] is True
    assert body_out["note"] == "run_closed"


def test_event_duplicated(client, monkeypatch):
    from services import ops_service

    seen = set()

    def _ev(payload):
        eid = payload["event_id"]
        dup = eid in seen
        seen.add(eid)
        return {"accepted": True, "duplicated": dup, "event_id": eid}

    monkeypatch.setattr(ops_service, "emit_event", _ev)

    eid = str(uuid.uuid4())
    body = {
        "event_id": eid,
        "scraper_id": "x",
        "ts": _now_iso(),
        "code": "test",
        "message": "hi",
        "idempotency_key": eid,
    }
    r1 = client.post("/ops/events", json=body, headers={"X-Ops-Token": "tok"})
    r2 = client.post("/ops/events", json=body, headers={"X-Ops-Token": "tok"})
    assert r1.get_json()["duplicated"] is False
    assert r2.get_json()["duplicated"] is True


def test_batch_duplicated(client, monkeypatch):
    from services import ops_service

    seen = set()

    def _bm(payload):
        bid = payload["batch_id"]
        dup = bid in seen
        seen.add(bid)
        return {"accepted": True, "duplicated": dup, "batch_id": bid}

    monkeypatch.setattr(ops_service, "emit_batch_metrics", _bm)

    bid = str(uuid.uuid4())
    rid = str(uuid.uuid4())
    body = {
        "batch_id": bid,
        "run_id": rid,
        "scraper_id": "x",
        "seq": 0,
        "ts": _now_iso(),
        "items_extracted": 5,
        "items_valid_local": 5,
        "items_sent": 5,
        "items_final_inserted": 0,
        "idempotency_key": bid,
    }
    r1 = client.post("/ops/metrics/batch", json=body, headers={"X-Ops-Token": "tok"})
    r2 = client.post("/ops/metrics/batch", json=body, headers={"X-Ops-Token": "tok"})
    assert r1.get_json()["duplicated"] is False
    assert r2.get_json()["duplicated"] is True
