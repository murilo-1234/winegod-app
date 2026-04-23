"""Testes dos contratos Pydantic."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from winegod_scraper_sdk.schemas import (
    BatchEventPayload,
    EndRunPayload,
    EventPayload,
    FailRunPayload,
    HeartbeatPayload,
    ScraperRegisterPayload,
    SourceLineage,
    StartRunPayload,
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ----- Registry -----

def test_register_minimal_ok():
    p = ScraperRegisterPayload.model_validate({
        "scraper_id": "canary_synthetic",
        "display_name": "Canary",
        "family": "canary",
        "source": "synthetic",
        "host": "este_pc",
        "connector_type": "TelemetryDelivery",
        "contract_name": "canary_event.v1",
        "contract_version": "v1",
    })
    assert p.scraper_id == "canary_synthetic"
    assert p.can_create_wine_sources is False


def test_register_rejects_extra_field():
    with pytest.raises(Exception):
        ScraperRegisterPayload.model_validate({
            "scraper_id": "x",
            "display_name": "y",
            "family": "canary",
            "source": "s",
            "host": "este_pc",
            "connector_type": "TelemetryDelivery",
            "contract_name": "c",
            "contract_version": "v1",
            "foo_bar_extra": 1,
        })


def test_register_rejects_invalid_family():
    with pytest.raises(Exception):
        ScraperRegisterPayload.model_validate({
            "scraper_id": "x", "display_name": "y", "family": "invalid_fam",
            "source": "s", "host": "este_pc",
            "connector_type": "TelemetryDelivery",
            "contract_name": "c", "contract_version": "v1",
        })


# ----- StartRun -----

def test_start_run_ok():
    rid = uuid.uuid4()
    p = StartRunPayload.model_validate({
        "run_id": str(rid),
        "scraper_id": "canary_synthetic",
        "host": "este_pc",
        "contract_name": "canary_event.v1",
        "contract_version": "v1",
        "idempotency_key": str(rid),
    })
    assert str(p.run_id) == str(rid)


def test_start_run_requires_idempotency_key():
    with pytest.raises(Exception):
        StartRunPayload.model_validate({
            "run_id": str(uuid.uuid4()),
            "scraper_id": "x",
            "host": "este_pc",
            "contract_name": "c",
            "contract_version": "v1",
            "idempotency_key": "",
        })


# ----- Heartbeat -----

def test_heartbeat_ok():
    rid = uuid.uuid4()
    p = HeartbeatPayload.model_validate({
        "run_id": str(rid),
        "scraper_id": "x",
        "ts": _now_iso(),
        "items_collected_so_far": 10,
        "idempotency_key": f"{rid}:t:default",
    })
    assert p.agent_id == "default"


def test_heartbeat_rejects_negative():
    with pytest.raises(Exception):
        HeartbeatPayload.model_validate({
            "run_id": str(uuid.uuid4()),
            "scraper_id": "x",
            "ts": _now_iso(),
            "items_collected_so_far": -1,
            "idempotency_key": "k",
        })


# ----- EndRun / FailRun -----

def test_end_run_items_final_inserted_must_be_zero():
    rid = uuid.uuid4()
    with pytest.raises(Exception):
        EndRunPayload.model_validate({
            "run_id": str(rid),
            "status": "success",
            "items_final_inserted": 5,
            "idempotency_key": str(rid),
        })


def test_end_run_ok_zero():
    rid = uuid.uuid4()
    p = EndRunPayload.model_validate({
        "run_id": str(rid),
        "status": "success",
        "items_final_inserted": 0,
        "idempotency_key": str(rid),
    })
    assert p.items_final_inserted == 0


def test_fail_run_rejects_success_status():
    rid = uuid.uuid4()
    with pytest.raises(Exception):
        FailRunPayload.model_validate({
            "run_id": str(rid),
            "status": "success",
            "error_summary": "whatever",
            "idempotency_key": str(rid),
        })


# ----- Event -----

def test_event_level_enum():
    with pytest.raises(Exception):
        EventPayload.model_validate({
            "event_id": str(uuid.uuid4()),
            "scraper_id": "x",
            "ts": _now_iso(),
            "level": "weird",
            "code": "X",
            "message": "hi",
            "idempotency_key": "k",
        })


def test_event_sample_max_1024():
    with pytest.raises(Exception):
        EventPayload.model_validate({
            "event_id": str(uuid.uuid4()),
            "scraper_id": "x",
            "ts": _now_iso(),
            "code": "X",
            "message": "hi",
            "payload_sample": "a" * 1025,
            "idempotency_key": "k",
        })


def test_event_does_not_accept_batch_id():
    # Regra D-F0 v2: events nao carregam batch_id.
    with pytest.raises(Exception):
        EventPayload.model_validate({
            "event_id": str(uuid.uuid4()),
            "scraper_id": "x",
            "ts": _now_iso(),
            "code": "X",
            "message": "hi",
            "batch_id": str(uuid.uuid4()),
            "idempotency_key": "k",
        })


# ----- BatchEvent -----

def test_batch_items_final_inserted_must_be_zero():
    with pytest.raises(Exception):
        BatchEventPayload.model_validate({
            "batch_id": str(uuid.uuid4()),
            "run_id": str(uuid.uuid4()),
            "scraper_id": "x",
            "seq": 0,
            "ts": _now_iso(),
            "items_final_inserted": 7,
            "idempotency_key": "k",
        })


def test_batch_field_coverage_range():
    with pytest.raises(Exception):
        BatchEventPayload.model_validate({
            "batch_id": str(uuid.uuid4()),
            "run_id": str(uuid.uuid4()),
            "scraper_id": "x",
            "seq": 0,
            "ts": _now_iso(),
            "field_coverage": {"campo": 1.5},
            "idempotency_key": "k",
        })


def test_source_lineage_kind_synthetic_ok():
    sl = SourceLineage.model_validate({
        "source_system": "canary",
        "source_kind": "synthetic",
        "source_pointer": "synthetic",
    })
    assert sl.source_kind == "synthetic"


def test_source_lineage_rejects_unknown_kind():
    with pytest.raises(Exception):
        SourceLineage.model_validate({
            "source_system": "x",
            "source_kind": "invalid",
            "source_pointer": "y",
        })
