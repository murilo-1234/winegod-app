"""Reporter — API de alto nivel para scrapers/adapters.

Uso minimo:

    from winegod_scraper_sdk import Reporter
    rep = Reporter.from_manifest("canary_manifest.yaml")
    rep.register()
    rep.start_run()
    for item in coletar():
        rep.heartbeat(items_collected_so_far=n)
    rep.end(status="success", items_extracted=n, items_sent=n)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from .connectors import TelemetryDelivery, ConnectorError, DeliveryResult
from .buffer import OfflineBuffer, kind_for_endpoint
from .idempotency import (
    idem_key_for_batch,
    idem_key_for_event,
    idem_key_for_heartbeat,
    idem_key_for_run,
    new_uuid,
)
from .manifest import Manifest, load_manifest
from .schemas import (
    BatchEventPayload,
    EndRunPayload,
    EventPayload,
    FailRunPayload,
    HeartbeatPayload,
    ScraperRegisterPayload,
    SourceLineage,
    StartRunPayload,
)


logger = logging.getLogger("winegod_scraper_sdk.reporter")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Reporter:
    """Reporter de alto nivel."""

    def __init__(
        self,
        manifest: Manifest,
        delivery: TelemetryDelivery,
        buffer_dir: str | Path | None = None,
    ):
        self.manifest = manifest
        self.delivery = delivery
        self.run_id: Optional[UUID] = None
        self._heartbeat_agent_id = "default"
        if buffer_dir is None:
            buffer_dir = os.environ.get(
                "OPS_BUFFER_DIR",
                str(Path.home() / ".winegod_ops_buffer"),
            )
        self.buffer = OfflineBuffer(base_dir=buffer_dir, scraper_id=manifest.scraper_id)

    # ----- Factory -----

    @classmethod
    def from_manifest(
        cls,
        manifest_path: str | Path,
        delivery: Optional[TelemetryDelivery] = None,
    ) -> "Reporter":
        manifest = load_manifest(manifest_path)
        if delivery is None:
            delivery = TelemetryDelivery.from_env()
        return cls(manifest=manifest, delivery=delivery)

    # ----- Envio direto (sem passar por buffer) -----

    _DELIVERY_MAP = {
        "/ops/scrapers/register": "register_scraper",
        "/ops/runs/start":        "start_run",
        "/ops/runs/heartbeat":    "heartbeat",
        "/ops/runs/end":          "end_run",
        "/ops/runs/fail":         "fail_run",
        "/ops/events":            "emit_event",
        "/ops/metrics/batch":     "emit_batch_metrics",
    }

    def _send_direct(
        self,
        endpoint: str,
        payload: Dict[str, Any],
    ) -> DeliveryResult:
        """Envia e NUNCA bufferiza. Propaga ConnectorError."""
        method_name = self._DELIVERY_MAP[endpoint]
        method = getattr(self.delivery, method_name)
        return method(payload)

    def _send_or_buffer(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        idempotency_key: str,
    ) -> Optional[DeliveryResult]:
        """Envia; se falhar, bufferiza e retorna None.

        Usado no fluxo NORMAL do scraper. NAO deve ser usado ao reenviar do buffer
        (use _send_direct para isso, senão duplica).
        """
        kind = kind_for_endpoint(endpoint)
        try:
            return self._send_direct(endpoint, payload)
        except ConnectorError as e:
            logger.warning("buffering payload for %s (err=%s)", endpoint, e)
            self.buffer.enqueue(endpoint, payload, idempotency_key, kind)
            return None

    # ----- API pub -----

    def register(self) -> Optional[DeliveryResult]:
        payload = self.manifest.to_register_payload()
        ScraperRegisterPayload.model_validate(payload)  # valida local
        return self._send_or_buffer("/ops/scrapers/register", payload, idempotency_key=self.manifest.scraper_id)

    def start_run(self, run_id: Optional[UUID] = None, run_params: Optional[Dict[str, Any]] = None) -> UUID:
        rid = run_id or new_uuid()
        self.run_id = rid
        primary = self.manifest.contract_primary()
        raw_payload = {
            "run_id": str(rid),
            "scraper_id": self.manifest.scraper_id,
            "host": self.manifest.host,
            "contract_name": primary.name,
            "contract_version": primary.version,
            "run_params": run_params or {},
            "started_at": _utc_now_iso(),
            "idempotency_key": idem_key_for_run(rid),
        }
        StartRunPayload.model_validate(raw_payload)
        self._send_or_buffer("/ops/runs/start", raw_payload, idempotency_key=str(rid))
        return rid

    def heartbeat(
        self,
        items_collected_so_far: int = 0,
        items_per_minute: Optional[float] = None,
        mem_mb: Optional[int] = None,
        cpu_pct: Optional[float] = None,
        note: Optional[str] = None,
    ) -> Optional[DeliveryResult]:
        if self.run_id is None:
            raise RuntimeError("heartbeat called before start_run()")
        ts = _utc_now_iso()
        raw_payload = {
            "run_id": str(self.run_id),
            "scraper_id": self.manifest.scraper_id,
            "ts": ts,
            "agent_id": self._heartbeat_agent_id,
            "items_collected_so_far": int(items_collected_so_far),
            "items_per_minute": items_per_minute,
            "mem_mb": mem_mb,
            "cpu_pct": cpu_pct,
            "note": note,
            "idempotency_key": idem_key_for_heartbeat(self.run_id, ts, self._heartbeat_agent_id),
        }
        HeartbeatPayload.model_validate(raw_payload)
        return self._send_or_buffer("/ops/runs/heartbeat", raw_payload, idempotency_key=raw_payload["idempotency_key"])

    def end(self, status: str = "success", **extra) -> Optional[DeliveryResult]:
        if self.run_id is None:
            raise RuntimeError("end called before start_run()")
        raw_payload = {
            "run_id": str(self.run_id),
            "status": status,
            "ended_at": _utc_now_iso(),
            "items_final_inserted": 0,
            "idempotency_key": idem_key_for_run(self.run_id),
        }
        raw_payload.update(extra)
        EndRunPayload.model_validate(raw_payload)
        return self._send_or_buffer("/ops/runs/end", raw_payload, idempotency_key=str(self.run_id))

    def fail(self, error_summary: str, status: str = "failed", error_count_fatal: int = 1) -> Optional[DeliveryResult]:
        if self.run_id is None:
            raise RuntimeError("fail called before start_run()")
        raw_payload = {
            "run_id": str(self.run_id),
            "status": status,
            "ended_at": _utc_now_iso(),
            "error_count_fatal": int(error_count_fatal),
            "error_summary": error_summary[:2048],
            "idempotency_key": idem_key_for_run(self.run_id),
        }
        FailRunPayload.model_validate(raw_payload)
        return self._send_or_buffer("/ops/runs/fail", raw_payload, idempotency_key=str(self.run_id))

    def event(
        self,
        code: str,
        message: str,
        level: str = "info",
        payload_hash: Optional[str] = None,
        payload_sample: Optional[str] = None,
        payload_pointer: Optional[str] = None,
    ) -> Optional[DeliveryResult]:
        eid = new_uuid()
        ts = _utc_now_iso()
        raw_payload = {
            "event_id": str(eid),
            "run_id": str(self.run_id) if self.run_id else None,
            "scraper_id": self.manifest.scraper_id,
            "ts": ts,
            "level": level,
            "code": code,
            "message": message[:1024],
            "payload_hash": payload_hash,
            "payload_sample": (payload_sample[:1024] if payload_sample else None),
            "payload_pointer": payload_pointer,
            "idempotency_key": idem_key_for_event(eid),
        }
        EventPayload.model_validate(raw_payload)
        return self._send_or_buffer("/ops/events", raw_payload, idempotency_key=str(eid))

    def batch_metrics(
        self,
        seq: int,
        items_extracted: int = 0,
        items_valid_local: int = 0,
        items_sent: int = 0,
        items_accepted_ready: int = 0,
        items_rejected_notwine: int = 0,
        items_needs_enrichment: int = 0,
        items_uncertain: int = 0,
        items_duplicate: int = 0,
        items_errored_transport: int = 0,
        items_per_second: Optional[float] = None,
        time_to_first_item_ms: Optional[int] = None,
        field_coverage: Optional[Dict[str, float]] = None,
        source_lineage: Optional[Dict[str, Any]] = None,
        delivery_target: str = "ops",
        delivery_status: str = "ok",
        items_final_inserted: int = 0,
    ) -> Optional[DeliveryResult]:
        # MVP: items_final_inserted deve ser 0. Se caller passar outro valor,
        # deixa Pydantic rejeitar abaixo — falha rapida, sem silenciar.
        if self.run_id is None:
            raise RuntimeError("batch_metrics called before start_run()")
        bid = new_uuid()
        ts = _utc_now_iso()
        raw_payload: Dict[str, Any] = {
            "batch_id": str(bid),
            "run_id": str(self.run_id),
            "scraper_id": self.manifest.scraper_id,
            "seq": int(seq),
            "ts": ts,
            "items_extracted": int(items_extracted),
            "items_valid_local": int(items_valid_local),
            "items_sent": int(items_sent),
            "items_accepted_ready": int(items_accepted_ready),
            "items_rejected_notwine": int(items_rejected_notwine),
            "items_needs_enrichment": int(items_needs_enrichment),
            "items_uncertain": int(items_uncertain),
            "items_duplicate": int(items_duplicate),
            "items_final_inserted": int(items_final_inserted),
            "items_errored_transport": int(items_errored_transport),
            "items_per_second": items_per_second,
            "time_to_first_item_ms": time_to_first_item_ms,
            "field_coverage": field_coverage or {},
            "source_lineage": source_lineage,
            "delivery_target": delivery_target,
            "delivery_status": delivery_status,
            "idempotency_key": idem_key_for_batch(bid),
        }
        if raw_payload["source_lineage"] is not None:
            SourceLineage.model_validate(raw_payload["source_lineage"])
        BatchEventPayload.model_validate(raw_payload)
        return self._send_or_buffer("/ops/metrics/batch", raw_payload, idempotency_key=str(bid))

    # ----- Buffer flush -----

    def flush_buffer(self, max_items: int = 1000) -> int:
        """Re-envia tudo que estava bufferizado. Retorna contagem enviada.

        Correcao (auditoria Fase 1 §5.3): usa _send_direct (NAO _send_or_buffer).
        Assim, se o re-envio falhar, o arquivo original eh MANTIDO, sem criar
        uma segunda copia.
        """
        sent = 0
        for item in self.buffer.iter_pending():
            if sent >= max_items:
                break
            try:
                result = self._send_direct(item.endpoint, item.payload)
            except ConnectorError:
                # Falhou -> mantém arquivo original, para aqui.
                break
            if result is not None and result.ok:
                self.buffer.mark_sent(item)
                sent += 1
            else:
                # Resposta !=ok mas sem exception — para evitar loop.
                break
        return sent
