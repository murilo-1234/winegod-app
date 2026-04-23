"""Testes da correcao Fase 1 no Reporter.

Cobre:
- `Reporter.batch_metrics(items_final_inserted=0)` funciona sem TypeError.
- `items_final_inserted=1` eh rejeitado pelo Pydantic.
- `flush_buffer()` NAO duplica quando reenvio falha.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from winegod_scraper_sdk.connectors import ConnectorError, DeliveryResult, TelemetryDelivery
from winegod_scraper_sdk.reporter import Reporter
from winegod_scraper_sdk.manifest import load_manifest


CANARY_PATH = Path(__file__).resolve().parent.parent / "examples" / "canary_manifest.yaml"


class _FakeDelivery:
    """Delivery fake que grava chamadas e pode falhar sob comando."""

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = set(fail_on or [])

    def _fake(self, name, payload):
        self.calls.append((name, payload))
        if name in self.fail_on:
            raise ConnectorError(f"forced failure on {name}")
        return DeliveryResult(ok=True, duplicated=False, status_code=200, body={"accepted": True, "duplicated": False})

    def register_scraper(self, p):  return self._fake("register_scraper", p)
    def start_run(self, p):         return self._fake("start_run", p)
    def heartbeat(self, p):         return self._fake("heartbeat", p)
    def end_run(self, p):           return self._fake("end_run", p)
    def fail_run(self, p):          return self._fake("fail_run", p)
    def emit_event(self, p):        return self._fake("emit_event", p)
    def emit_batch_metrics(self, p): return self._fake("emit_batch_metrics", p)
    def health(self):                return self._fake("health", {})


# ---------------------------------------------------------------------------
# §5.2 — batch_metrics com items_final_inserted
# ---------------------------------------------------------------------------

def test_reporter_batch_metrics_accepts_items_final_inserted_zero(tmp_path):
    m = load_manifest(CANARY_PATH)
    delivery = _FakeDelivery()
    rep = Reporter(manifest=m, delivery=delivery, buffer_dir=str(tmp_path))
    rep.start_run()

    # Deve NAO levantar TypeError
    result = rep.batch_metrics(
        seq=0,
        items_extracted=10,
        items_valid_local=10,
        items_sent=10,
        items_final_inserted=0,  # <- core do fix
    )
    assert result is not None
    assert result.ok is True
    # Delivery recebeu items_final_inserted=0 no payload
    (_, payload) = delivery.calls[-1]
    assert payload["items_final_inserted"] == 0


def test_reporter_batch_metrics_rejects_items_final_inserted_nonzero(tmp_path):
    m = load_manifest(CANARY_PATH)
    delivery = _FakeDelivery()
    rep = Reporter(manifest=m, delivery=delivery, buffer_dir=str(tmp_path))
    rep.start_run()

    with pytest.raises(Exception):
        rep.batch_metrics(
            seq=0,
            items_extracted=10,
            items_final_inserted=5,  # <- deve falhar
        )


# ---------------------------------------------------------------------------
# §5.3 — flush_buffer nao duplica em falha
# ---------------------------------------------------------------------------

def test_flush_buffer_does_not_duplicate_on_failure(tmp_path):
    m = load_manifest(CANARY_PATH)
    # Delivery que falha SEMPRE
    failing_delivery = _FakeDelivery(fail_on=["heartbeat", "emit_event", "emit_batch_metrics",
                                              "start_run", "end_run", "fail_run", "register_scraper"])
    rep = Reporter(manifest=m, delivery=failing_delivery, buffer_dir=str(tmp_path))

    # Coloca 1 item manualmente no buffer (simula um heartbeat que ficou pendente)
    rep.buffer.enqueue(
        endpoint="/ops/runs/heartbeat",
        payload={"run_id": str(uuid.uuid4()), "scraper_id": m.scraper_id,
                 "ts": "2026-04-22T10:00:00Z", "idempotency_key": "k1"},
        idempotency_key="k1",
        kind="heartbeat",
    )
    assert rep.buffer.pending_count() == 1

    # Chama flush — delivery falha. O arquivo original deve permanecer; nao pode virar 2.
    sent = rep.flush_buffer(max_items=10)
    assert sent == 0, "flush should not mark as sent when delivery fails"
    assert rep.buffer.pending_count() == 1, (
        "flush_buffer duplicated pending item on failure — exactly 1 expected"
    )


def test_flush_buffer_marks_sent_on_success(tmp_path):
    m = load_manifest(CANARY_PATH)
    ok_delivery = _FakeDelivery()  # nao falha
    rep = Reporter(manifest=m, delivery=ok_delivery, buffer_dir=str(tmp_path))

    rep.buffer.enqueue(
        endpoint="/ops/events",
        payload={"event_id": str(uuid.uuid4()), "scraper_id": m.scraper_id,
                 "ts": "2026-04-22T10:00:00Z", "code": "x", "message": "y",
                 "idempotency_key": "ek1"},
        idempotency_key="ek1",
        kind="event",
    )
    assert rep.buffer.pending_count() == 1
    sent = rep.flush_buffer(max_items=10)
    assert sent == 1
    assert rep.buffer.pending_count() == 0


def test_send_or_buffer_enqueues_on_failure(tmp_path):
    m = load_manifest(CANARY_PATH)
    failing = _FakeDelivery(fail_on=["emit_event"])
    rep = Reporter(manifest=m, delivery=failing, buffer_dir=str(tmp_path))
    rep.start_run()

    # Evento falha -> deve enfileirar 1 arquivo
    rep.event(code="t", message="m")
    assert rep.buffer.pending_count() >= 1
