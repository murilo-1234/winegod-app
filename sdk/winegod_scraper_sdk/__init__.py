"""winegod_scraper_sdk — Fase 1 do Winegod Data Ops.

Objetivo: qualquer scraper/adapter importa este pacote e reporta run/
heartbeat/end/event/batch para o control plane, com buffer offline,
idempotência e PII safe.

Exemplo:

    from winegod_scraper_sdk import Reporter, load_manifest
    rep = Reporter.from_manifest("canary_manifest.yaml")
    rep.start_run()
    rep.heartbeat(items_collected_so_far=10)
    rep.end(status="success")
"""
from .schemas import (
    ScraperRegisterPayload,
    StartRunPayload,
    HeartbeatPayload,
    EndRunPayload,
    FailRunPayload,
    EventPayload,
    BatchEventPayload,
    SourceLineage,
)
from .manifest import Manifest, load_manifest
from .idempotency import new_uuid, idem_key_for_run, idem_key_for_heartbeat
from .buffer import OfflineBuffer
from .connectors import TelemetryDelivery
from .reporter import Reporter

__all__ = [
    "ScraperRegisterPayload",
    "StartRunPayload",
    "HeartbeatPayload",
    "EndRunPayload",
    "FailRunPayload",
    "EventPayload",
    "BatchEventPayload",
    "SourceLineage",
    "Manifest",
    "load_manifest",
    "new_uuid",
    "idem_key_for_run",
    "idem_key_for_heartbeat",
    "OfflineBuffer",
    "TelemetryDelivery",
    "Reporter",
]

__version__ = "0.1.0"
