"""Manifest YAML loader + validator.

Manifesto eh uma ficha de identidade por scraper. Ver Design Freeze §6.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .schemas import FAMILY_VALUES, STATUS_VALUES


class ManifestContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scraper_id: str
    display_name: str
    family: str
    source: str
    variant: Optional[str] = None
    owner: str = "murilo"
    host: str
    schedule: Optional[str] = None
    entrypoint: Optional[str] = None
    connector_type: str = "TelemetryDelivery"
    contracts: List[ManifestContract]
    outputs: List[str] = Field(default_factory=lambda: ["ops"])
    registry_status: str = "registered"
    status_reason: Optional[str] = None
    pii_policy: str = "strict"
    retention_policy: str = "default"
    declared_fields: List[str] = Field(default_factory=list)
    freshness_sla_hours: int = 24
    can_create_wine_sources: bool = False
    requires_dq_v3: bool = False
    requires_matching: bool = False
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    # Campos derivados (nao entram no YAML, preenchidos no load)
    source_path: Optional[str] = None
    source_hash: Optional[str] = None

    @field_validator("family")
    @classmethod
    def _check_family(cls, v: str) -> str:
        if v not in FAMILY_VALUES:
            raise ValueError(
                f"family must be one of {FAMILY_VALUES}, got {v!r}"
            )
        return v

    @field_validator("outputs")
    @classmethod
    def _ops_required(cls, v: List[str]) -> List[str]:
        if "ops" not in v:
            raise ValueError("outputs must include 'ops' in MVP")
        return v

    @field_validator("registry_status")
    @classmethod
    def _check_registry_status(cls, v: str) -> str:
        if v not in STATUS_VALUES:
            raise ValueError(
                f"registry_status must be one of {STATUS_VALUES}, got {v!r}"
            )
        return v

    @field_validator("can_create_wine_sources", "requires_dq_v3", "requires_matching")
    @classmethod
    def _mvp_false(cls, v: bool) -> bool:
        # MVP: todos false. Scrapers com True serao rejeitados pelo manifesto.
        if v is True:
            raise ValueError(
                "MVP: can_create_wine_sources/requires_dq_v3/requires_matching must be false"
            )
        return v

    @field_validator("freshness_sla_hours")
    @classmethod
    def _sla_ge_zero(cls, v: int) -> int:
        if v < 0:
            raise ValueError("freshness_sla_hours must be >= 0")
        return v

    def contract_primary(self) -> ManifestContract:
        if not self.contracts:
            raise ValueError("manifest has no contracts")
        return self.contracts[0]

    def to_register_payload(self) -> Dict[str, Any]:
        """Converte para payload do endpoint /ops/scrapers/register."""
        primary = self.contract_primary()
        return {
            "scraper_id": self.scraper_id,
            "display_name": self.display_name,
            "family": self.family,
            "source": self.source,
            "variant": self.variant,
            "host": self.host,
            "owner": self.owner,
            "connector_type": self.connector_type,
            "contract_name": primary.name,
            "contract_version": primary.version,
            "status": self.registry_status,
            "can_create_wine_sources": False,
            "requires_dq_v3": False,
            "requires_matching": False,
            "schedule_hint": self.schedule,
            "freshness_sla_hours": int(self.freshness_sla_hours),
            "declared_fields": list(self.declared_fields),
            "pii_policy": self.pii_policy,
            "retention_policy": self.retention_policy,
            "manifest_path": self.source_path,
            "manifest_hash": self.source_hash,
            "tags": list(self.tags),
        }


def load_manifest(path: str | Path) -> Manifest:
    """Le YAML, valida via Pydantic e calcula sha256."""
    p = Path(path)
    raw = p.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    data = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest {path} must be a YAML mapping at root")
    m = Manifest.model_validate(data)
    # Preenche campos derivados
    m = m.model_copy(update={
        "source_path": str(p.resolve()),
        "source_hash": digest,
    })
    return m
