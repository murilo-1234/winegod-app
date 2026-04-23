"""UUID / idempotency helpers.

Regra D-F0-02 do Design Freeze v2:
- Preferir UUIDv7 se houver lib simples.
- Aceitar UUIDv4 como fallback.
- Nao adicionar dependencia pesada so por v7.
"""
from __future__ import annotations

import uuid
from typing import Optional

try:  # pragma: no cover — opcional
    from uuid_utils import uuid7  # type: ignore

    def _uuid7() -> uuid.UUID:
        return uuid.UUID(str(uuid7()))

    HAS_UUID7 = True
except Exception:  # pragma: no cover
    HAS_UUID7 = False

    def _uuid7() -> uuid.UUID:  # type: ignore
        raise RuntimeError("uuid7 lib not available")


def new_uuid(prefer_v7: bool = True) -> uuid.UUID:
    """Gera UUID v7 se possivel, senao v4.

    Pura v4 se prefer_v7=False.
    """
    if prefer_v7 and HAS_UUID7:
        try:
            return _uuid7()
        except Exception:
            pass
    return uuid.uuid4()


def idem_key_for_run(run_id: uuid.UUID | str) -> str:
    """Idempotency key canonica para start/end/fail: igual ao run_id."""
    return str(run_id)


def idem_key_for_heartbeat(
    run_id: uuid.UUID | str, ts: str, agent_id: str = "default"
) -> str:
    """Idempotency key para heartbeat: `{run_id}:{ts}:{agent_id}`."""
    return f"{run_id}:{ts}:{agent_id}"


def idem_key_for_batch(batch_id: uuid.UUID | str) -> str:
    return str(batch_id)


def idem_key_for_event(event_id: uuid.UUID | str) -> str:
    return str(event_id)
