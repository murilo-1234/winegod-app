"""Testes dos helpers de idempotency/UUID."""
from __future__ import annotations

import uuid

from winegod_scraper_sdk.idempotency import (
    idem_key_for_batch,
    idem_key_for_event,
    idem_key_for_heartbeat,
    idem_key_for_run,
    new_uuid,
)


def test_new_uuid_returns_uuid():
    u = new_uuid()
    assert isinstance(u, uuid.UUID)
    # v4 ou v7 (v7 depende de lib opcional). Nunca v1/v3.
    assert u.version in (4, 7)


def test_new_uuid_unique():
    seen = set()
    for _ in range(50):
        seen.add(str(new_uuid()))
    assert len(seen) == 50


def test_new_uuid_fallback_v4():
    u = new_uuid(prefer_v7=False)
    assert u.version == 4


def test_idem_key_for_run():
    u = uuid.uuid4()
    assert idem_key_for_run(u) == str(u)


def test_idem_key_for_heartbeat_format():
    u = uuid.uuid4()
    k = idem_key_for_heartbeat(u, "2026-04-22T10:00:00Z", "agent-a")
    assert k.startswith(str(u))
    assert "2026-04-22T10:00:00Z" in k
    assert k.endswith("agent-a")


def test_idem_key_for_batch_and_event():
    u = uuid.uuid4()
    assert idem_key_for_batch(u) == str(u)
    assert idem_key_for_event(u) == str(u)
