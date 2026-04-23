"""Correcao 2 — Schema parity SDK <-> backend.

Testes exigidos pelo prompt:
1. ScraperRegisterPayload rejeita freshness_sla_hours=-1.
2. Manifest rejeita freshness_sla_hours=-1 (via model_validate e via load_manifest YAML).
3. SourceLineage rejeita source_record_count=-1.
4. BatchEventPayload com source_lineage.source_record_count=-1 rejeita (nested).
5. Reporter.batch_metrics com source_lineage.source_record_count=-1 rejeita antes de delivery.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from winegod_scraper_sdk.schemas import (
    BatchEventPayload,
    ScraperRegisterPayload,
    SourceLineage,
)
from winegod_scraper_sdk.manifest import Manifest, load_manifest
from winegod_scraper_sdk.reporter import Reporter
from winegod_scraper_sdk.connectors import DeliveryResult


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ----- 1. ScraperRegisterPayload.freshness_sla_hours -----

def test_sdk_register_rejects_negative_freshness_sla_hours():
    with pytest.raises(Exception):
        ScraperRegisterPayload.model_validate({
            "scraper_id": "x", "display_name": "x", "family": "commerce",
            "source": "x", "host": "este_pc",
            "connector_type": "TelemetryDelivery",
            "contract_name": "c", "contract_version": "v1",
            "freshness_sla_hours": -1,
        })


def test_sdk_register_accepts_zero_freshness_sla_hours():
    p = ScraperRegisterPayload.model_validate({
        "scraper_id": "x", "display_name": "x", "family": "commerce",
        "source": "x", "host": "este_pc",
        "connector_type": "TelemetryDelivery",
        "contract_name": "c", "contract_version": "v1",
        "freshness_sla_hours": 0,
    })
    assert p.freshness_sla_hours == 0


# ----- 2. Manifest.freshness_sla_hours -----

def test_sdk_manifest_rejects_negative_freshness_sla_hours():
    """Via Manifest.model_validate direto."""
    with pytest.raises(Exception):
        Manifest.model_validate({
            "scraper_id": "x",
            "display_name": "x",
            "family": "canary",
            "source": "synthetic",
            "host": "este_pc",
            "contracts": [{"name": "c", "version": "v1"}],
            "outputs": ["ops"],
            "freshness_sla_hours": -1,
        })


def test_sdk_manifest_load_rejects_negative_freshness(tmp_path: Path):
    """Via load_manifest(yaml_path)."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
scraper_id: x
display_name: x
family: canary
source: synthetic
host: este_pc
contracts:
  - { name: c, version: v1 }
outputs: [ops]
freshness_sla_hours: -1
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        load_manifest(bad)


# ----- 3. SourceLineage.source_record_count -----

def test_sdk_source_lineage_rejects_negative_record_count():
    with pytest.raises(Exception):
        SourceLineage.model_validate({
            "source_system": "x",
            "source_kind": "table",
            "source_pointer": "x",
            "source_record_count": -1,
        })


def test_sdk_source_lineage_accepts_none_record_count():
    sl = SourceLineage.model_validate({
        "source_system": "x", "source_kind": "synthetic", "source_pointer": "x",
    })
    assert sl.source_record_count is None


def test_sdk_source_lineage_accepts_zero_record_count():
    sl = SourceLineage.model_validate({
        "source_system": "x", "source_kind": "synthetic", "source_pointer": "x",
        "source_record_count": 0,
    })
    assert sl.source_record_count == 0


# ----- 4. BatchEventPayload nested -----

def test_sdk_batch_rejects_nested_negative_source_record_count():
    with pytest.raises(Exception):
        BatchEventPayload.model_validate({
            "batch_id": str(uuid.uuid4()),
            "run_id": str(uuid.uuid4()),
            "scraper_id": "x",
            "seq": 0,
            "ts": _now(),
            "items_final_inserted": 0,
            "source_lineage": {
                "source_system": "x",
                "source_kind": "table",
                "source_pointer": "x",
                "source_record_count": -1,  # nested invalido
            },
            "idempotency_key": "k",
        })


# ----- 5. Reporter.batch_metrics nao chega a delivery se payload invalido -----

CANARY_PATH = Path(__file__).resolve().parent.parent / "examples" / "canary_manifest.yaml"


class _RecordingDelivery:
    def __init__(self):
        self.calls = []

    def _ok(self, name, p):
        self.calls.append((name, p))
        return DeliveryResult(ok=True, duplicated=False, status_code=200, body={"accepted": True})

    def register_scraper(self, p): return self._ok("register_scraper", p)
    def start_run(self, p):        return self._ok("start_run", p)
    def heartbeat(self, p):        return self._ok("heartbeat", p)
    def end_run(self, p):          return self._ok("end_run", p)
    def fail_run(self, p):         return self._ok("fail_run", p)
    def emit_event(self, p):       return self._ok("emit_event", p)
    def emit_batch_metrics(self, p): return self._ok("emit_batch_metrics", p)
    def health(self):              return self._ok("health", {})


def test_reporter_batch_metrics_rejects_invalid_source_lineage_before_delivery(tmp_path):
    m = load_manifest(CANARY_PATH)
    rec = _RecordingDelivery()
    rep = Reporter(manifest=m, delivery=rec, buffer_dir=str(tmp_path))
    rep.start_run()

    # Delivery recebeu start_run, mas nenhum batch ainda.
    batch_calls_before = [c for c in rec.calls if c[0] == "emit_batch_metrics"]
    assert batch_calls_before == []

    with pytest.raises(Exception):
        rep.batch_metrics(
            seq=0,
            items_extracted=10,
            items_sent=10,
            source_lineage={
                "source_system": "x",
                "source_kind": "table",
                "source_pointer": "x",
                "source_record_count": -1,  # invalido
            },
        )

    # Delivery NUNCA recebeu o batch invalido.
    batch_calls_after = [c for c in rec.calls if c[0] == "emit_batch_metrics"]
    assert batch_calls_after == [], (
        "Reporter permitiu chamar delivery com payload invalido; "
        "Pydantic deveria ter rejeitado antes."
    )
