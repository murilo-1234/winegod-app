"""Connectors — entrega de payloads ao control plane.

No MVP apenas `TelemetryDelivery` eh funcional. Outros connectors
(commerce, review, critic) sao STUBS (levantam NotImplementedError)
para o contrato existir sem destino real.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


logger = logging.getLogger("winegod_scraper_sdk.connectors")


class ConnectorError(RuntimeError):
    """Erro no envio (transporte, auth, 5xx)."""


@dataclass
class DeliveryResult:
    ok: bool
    duplicated: bool
    status_code: int
    body: Dict[str, Any]

    @property
    def ignored(self) -> bool:
        return bool(self.body.get("ignored"))


class TelemetryDelivery:
    """Entrega HTTP para /ops/*.

    - Nao chama outros destinos.
    - Nao escreve em dado de negocio.
    - Token vem de OPS_TOKEN.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_seconds: float = 10.0,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout_seconds
        self._session = session or requests.Session()

    @classmethod
    def from_env(
        cls,
        default_url: str = "http://localhost:5000",
    ) -> "TelemetryDelivery":
        return cls(
            base_url=os.environ.get("OPS_BASE_URL", default_url),
            token=os.environ.get("OPS_TOKEN", ""),
        )

    # ----- low level -----

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> DeliveryResult:
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-Ops-Token"] = self.token
        resp = self._session.post(url, json=payload, headers=headers, timeout=self.timeout)
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text[:500]}

        if resp.status_code >= 500:
            raise ConnectorError(f"{endpoint} {resp.status_code}: {body}")
        if resp.status_code in (401, 403):
            raise ConnectorError(f"auth_failed {resp.status_code}: {body}")

        return DeliveryResult(
            ok=(resp.status_code in (200, 201)),
            duplicated=bool(body.get("duplicated", False)),
            status_code=resp.status_code,
            body=body,
        )

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> DeliveryResult:
        url = f"{self.base_url}{endpoint}"
        headers = {}
        if self.token:
            headers["X-Ops-Token"] = self.token
        resp = self._session.get(url, params=params, headers=headers, timeout=self.timeout)
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text[:500]}
        return DeliveryResult(
            ok=(resp.status_code == 200),
            duplicated=False,
            status_code=resp.status_code,
            body=body,
        )

    # ----- API de alto nivel -----

    def health(self) -> DeliveryResult:
        return self._get("/ops/health")

    def register_scraper(self, payload: Dict[str, Any]) -> DeliveryResult:
        return self._post("/ops/scrapers/register", payload)

    def start_run(self, payload: Dict[str, Any]) -> DeliveryResult:
        return self._post("/ops/runs/start", payload)

    def heartbeat(self, payload: Dict[str, Any]) -> DeliveryResult:
        return self._post("/ops/runs/heartbeat", payload)

    def end_run(self, payload: Dict[str, Any]) -> DeliveryResult:
        return self._post("/ops/runs/end", payload)

    def fail_run(self, payload: Dict[str, Any]) -> DeliveryResult:
        return self._post("/ops/runs/fail", payload)

    def emit_event(self, payload: Dict[str, Any]) -> DeliveryResult:
        # Defesa: remove batch_id se tiver (Design Freeze v2: events nao criam batch)
        payload.pop("batch_id", None)
        return self._post("/ops/events", payload)

    def emit_batch_metrics(self, payload: Dict[str, Any]) -> DeliveryResult:
        return self._post("/ops/metrics/batch", payload)

    def list_scrapers(self, **params) -> DeliveryResult:
        return self._get("/ops/scrapers", params)

    def list_runs(self, scraper_id: str, **params) -> DeliveryResult:
        params = {"scraper_id": scraper_id, **params}
        return self._get("/ops/runs", params)


# ---------------------------------------------------------------------------
# Stubs nao funcionais (Design Freeze v2 §5.6: MVP so TelemetryDelivery)
# ---------------------------------------------------------------------------

class _StubConnector:
    name = "stub"

    def send(self, *a, **kw):
        raise NotImplementedError(
            f"{self.name} is a stub in MVP. Only TelemetryDelivery is functional."
        )


class DQV3Delivery(_StubConnector):
    name = "DQV3Delivery"


class ReviewDelivery(_StubConnector):
    name = "ReviewDelivery"


class CriticDelivery(_StubConnector):
    name = "CriticDelivery"
