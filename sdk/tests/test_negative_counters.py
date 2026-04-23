"""Testes §5.6 — contadores negativos rejeitados."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from winegod_scraper_sdk.schemas import (
    BatchEventPayload,
    EndRunPayload,
    HeartbeatPayload,
)


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ----- EndRunPayload: contadores opcionais >= 0 -----

@pytest.mark.parametrize("field", [
    "items_extracted", "items_valid_local", "items_sent",
    "items_rejected_schema", "batches_total",
    "error_count_transient", "retry_count", "rate_limit_hits",
])
def test_end_run_rejects_negative_counter(field):
    rid = uuid.uuid4()
    base = {
        "run_id": str(rid),
        "status": "success",
        "items_final_inserted": 0,
        "idempotency_key": str(rid),
        field: -1,
    }
    with pytest.raises(Exception):
        EndRunPayload.model_validate(base)


def test_end_run_accepts_nonneg_counters():
    rid = uuid.uuid4()
    EndRunPayload.model_validate({
        "run_id": str(rid),
        "status": "success",
        "items_final_inserted": 0,
        "idempotency_key": str(rid),
        "items_extracted": 0,
        "items_valid_local": 1,
        "items_sent": 1,
        "retry_count": 2,
    })


# ----- HeartbeatPayload: items_per_minute/mem_mb/cpu_pct -----

def test_heartbeat_rejects_negative_items_per_minute():
    rid = uuid.uuid4()
    with pytest.raises(Exception):
        HeartbeatPayload.model_validate({
            "run_id": str(rid), "scraper_id": "x", "ts": _now(),
            "items_collected_so_far": 0,
            "items_per_minute": -1.0,
            "idempotency_key": "k",
        })


def test_heartbeat_rejects_negative_mem_mb():
    rid = uuid.uuid4()
    with pytest.raises(Exception):
        HeartbeatPayload.model_validate({
            "run_id": str(rid), "scraper_id": "x", "ts": _now(),
            "mem_mb": -10, "idempotency_key": "k",
        })


def test_heartbeat_rejects_cpu_over_100():
    rid = uuid.uuid4()
    with pytest.raises(Exception):
        HeartbeatPayload.model_validate({
            "run_id": str(rid), "scraper_id": "x", "ts": _now(),
            "cpu_pct": 150.0, "idempotency_key": "k",
        })


def test_heartbeat_rejects_cpu_negative():
    rid = uuid.uuid4()
    with pytest.raises(Exception):
        HeartbeatPayload.model_validate({
            "run_id": str(rid), "scraper_id": "x", "ts": _now(),
            "cpu_pct": -0.1, "idempotency_key": "k",
        })


def test_heartbeat_accepts_valid_cpu_range():
    rid = uuid.uuid4()
    p = HeartbeatPayload.model_validate({
        "run_id": str(rid), "scraper_id": "x", "ts": _now(),
        "cpu_pct": 99.9, "idempotency_key": "k",
    })
    assert p.cpu_pct == 99.9


# ----- BatchEventPayload: items_*, items_per_second, time_to_first_item_ms -----

@pytest.mark.parametrize("field", [
    "items_extracted", "items_valid_local", "items_sent",
    "items_accepted_ready", "items_rejected_notwine",
    "items_needs_enrichment", "items_uncertain",
    "items_duplicate", "items_errored_transport",
    "items_rejected_schema",
])
def test_batch_rejects_negative_counter(field):
    with pytest.raises(Exception):
        BatchEventPayload.model_validate({
            "batch_id": str(uuid.uuid4()),
            "run_id": str(uuid.uuid4()),
            "scraper_id": "x", "seq": 0, "ts": _now(),
            field: -1,
            "items_final_inserted": 0,
            "idempotency_key": "k",
        })


def test_batch_rejects_negative_items_per_second():
    with pytest.raises(Exception):
        BatchEventPayload.model_validate({
            "batch_id": str(uuid.uuid4()),
            "run_id": str(uuid.uuid4()),
            "scraper_id": "x", "seq": 0, "ts": _now(),
            "items_per_second": -5.0,
            "items_final_inserted": 0,
            "idempotency_key": "k",
        })


def test_batch_rejects_negative_time_to_first_item_ms():
    with pytest.raises(Exception):
        BatchEventPayload.model_validate({
            "batch_id": str(uuid.uuid4()),
            "run_id": str(uuid.uuid4()),
            "scraper_id": "x", "seq": 0, "ts": _now(),
            "time_to_first_item_ms": -1,
            "items_final_inserted": 0,
            "idempotency_key": "k",
        })
