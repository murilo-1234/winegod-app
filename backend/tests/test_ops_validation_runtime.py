"""Testes §5.1 — backend valida Pydantic sem SDK no path.

Simula o runtime Docker/Render: importa `routes.ops` a partir de
`C:\\winegod-app\\backend` (sem `sdk/` no sys.path) e exige que
`_validate` rejeite payloads com campo extra.

Tambem cobre §5.6 via endpoints: contador negativo retorna 422.
"""
from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# §5.1 — subprocess prova que backend valida sem SDK
# ---------------------------------------------------------------------------

def test_backend_validates_without_sdk_in_path():
    """Executa python a partir de backend/ (sem sdk no PYTHONPATH).

    Verifica que _validate_payload rejeita payload com campo extra,
    sem contexto Flask (funcao pura).
    """
    script = (
        "import sys, os; "
        # Garante que sdk NAO esta no sys.path
        "sys.path = [p for p in sys.path if 'sdk' not in p.lower()]; "
        # Muda para backend/
        f"os.chdir(r'{BACKEND_ROOT}'); "
        # Adiciona apenas backend ao sys.path (como Render/Docker faz)
        f"sys.path.insert(0, r'{BACKEND_ROOT}'); "
        "from routes import ops; "
        "validated, err = ops._validate_payload('ScraperRegisterPayload', {'unknown_field_x': 1}); "
        "assert err is not None, 'payload with extra field must be rejected'; "
        "assert validated is None; "
        "err_dict, status = err; "
        "assert status == 422, f'expected 422, got {status}'; "
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"subprocess failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "OK" in result.stdout


def test_validate_unknown_model_returns_500_error():
    """Se model_name nao existe, _validate_payload deve retornar erro fechado 500."""
    sys.path.insert(0, str(BACKEND_ROOT))
    from routes import ops
    validated, err = ops._validate_payload("NonExistentModel", {"x": 1})
    assert validated is None
    assert err is not None
    err_dict, status = err
    assert status == 500
    assert err_dict["error"] == "ops_schema_unavailable"


def test_validate_payload_accepts_valid():
    """Valida que payload correto passa."""
    sys.path.insert(0, str(BACKEND_ROOT))
    from routes import ops
    validated, err = ops._validate_payload("ScraperRegisterPayload", {
        "scraper_id": "canary_synthetic",
        "display_name": "Canary",
        "family": "canary",
        "source": "synthetic",
        "host": "este_pc",
        "connector_type": "TelemetryDelivery",
        "contract_name": "canary_event.v1",
        "contract_version": "v1",
    })
    assert err is None
    assert validated["scraper_id"] == "canary_synthetic"


def test_validate_payload_accepts_extended_registry_status():
    sys.path.insert(0, str(BACKEND_ROOT))
    from routes import ops
    validated, err = ops._validate_payload("ScraperRegisterPayload", {
        "scraper_id": "commerce_tier2_chat1",
        "display_name": "Tier2 Chat1",
        "family": "commerce",
        "source": "winegod_admin",
        "host": "este_pc",
        "connector_type": "TelemetryDelivery",
        "contract_name": "commerce_offer_candidate.v1",
        "contract_version": "v1",
        "status": "blocked_contract_missing",
    })
    assert err is None
    assert validated["status"] == "blocked_contract_missing"


# ---------------------------------------------------------------------------
# §5.6 — contadores negativos via endpoint retornam 422
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    sys.path.insert(0, str(BACKEND_ROOT))
    from config import Config as _Cfg
    monkeypatch.setattr(_Cfg, "OPS_TOKEN", "tok")
    monkeypatch.setattr(_Cfg, "OPS_API_ENABLED", True)
    monkeypatch.setattr(_Cfg, "OPS_WRITE_ENABLED", True)
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_heartbeat_negative_items_returns_422(client):
    body = {
        "run_id": str(uuid.uuid4()),
        "scraper_id": "x",
        "ts": _now_iso(),
        "items_collected_so_far": -1,  # negativo
        "idempotency_key": "k",
    }
    r = client.post("/ops/runs/heartbeat", json=body, headers={"X-Ops-Token": "tok"})
    assert r.status_code == 422


def test_heartbeat_cpu_pct_over_100_returns_422(client):
    body = {
        "run_id": str(uuid.uuid4()),
        "scraper_id": "x",
        "ts": _now_iso(),
        "cpu_pct": 150.0,
        "idempotency_key": "k",
    }
    r = client.post("/ops/runs/heartbeat", json=body, headers={"X-Ops-Token": "tok"})
    assert r.status_code == 422


def test_batch_negative_counter_returns_422(client):
    body = {
        "batch_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "scraper_id": "x",
        "seq": 0,
        "ts": _now_iso(),
        "items_extracted": -1,  # negativo
        "items_final_inserted": 0,
        "idempotency_key": "k",
    }
    r = client.post("/ops/metrics/batch", json=body, headers={"X-Ops-Token": "tok"})
    assert r.status_code == 422


def test_end_run_negative_retry_count_returns_422(client):
    rid = str(uuid.uuid4())
    body = {
        "run_id": rid,
        "status": "success",
        "retry_count": -5,
        "items_final_inserted": 0,
        "idempotency_key": rid,
    }
    r = client.post("/ops/runs/end", json=body, headers={"X-Ops-Token": "tok"})
    assert r.status_code == 422
