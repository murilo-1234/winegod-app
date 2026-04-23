"""Pydantic v2 models — contratos do SDK (Design Freeze v2).

Todos os modelos usam extra='forbid' — payload com campo nao previsto eh rejeitado.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums (como strings — CHECK no banco)
# ---------------------------------------------------------------------------

FAMILY_VALUES = (
    "commerce", "discovery", "catalog_identity", "review", "reviewer",
    "community_rating", "critic", "market", "enrichment", "canary",
)
STATUS_VALUES = (
    "draft", "registered", "contract_validated", "active", "paused",
    "stale", "error", "blocked_quality", "deprecated",
)
RUN_STATUS_VALUES = (
    "started", "running", "success", "failed", "timeout", "aborted",
)
RUN_END_OK = ("success", "aborted")
RUN_END_FAIL = ("failed", "timeout")
LEVEL_VALUES = ("info", "warn", "error", "anomaly", "audit")
SOURCE_KIND_VALUES = ("table", "file", "api", "stream", "manual", "synthetic")
DELIVERY_TARGET_VALUES = ("ops", "dq_v3_stub", "matching_stub", "final_stub")
DELIVERY_STATUS_VALUES = ("ok", "failed", "buffered", "replayed")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ScraperRegisterPayload(_StrictModel):
    scraper_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    family: str
    source: str
    variant: Optional[str] = None
    host: str
    owner: str = "murilo"
    connector_type: str
    contract_name: str
    contract_version: str
    status: str = "registered"
    can_create_wine_sources: bool = False
    requires_dq_v3: bool = False
    requires_matching: bool = False
    schedule_hint: Optional[str] = None
    freshness_sla_hours: int = 24
    declared_fields: List[str] = Field(default_factory=list)
    pii_policy: str = "strict"
    retention_policy: str = "default"
    manifest_path: Optional[str] = None
    manifest_hash: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    @field_validator("family")
    @classmethod
    def _check_family(cls, v: str) -> str:
        if v not in FAMILY_VALUES:
            raise ValueError(f"family must be one of {FAMILY_VALUES}")
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in STATUS_VALUES:
            raise ValueError(f"status must be one of {STATUS_VALUES}")
        return v

    @field_validator("pii_policy")
    @classmethod
    def _check_pii(cls, v: str) -> str:
        if v not in ("strict", "debug_sample"):
            raise ValueError("pii_policy must be 'strict' or 'debug_sample'")
        return v

    @field_validator("freshness_sla_hours")
    @classmethod
    def _sla_ge_zero(cls, v: int) -> int:
        if v < 0:
            raise ValueError("freshness_sla_hours must be >= 0")
        return v


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

class StartRunPayload(_StrictModel):
    run_id: UUID
    scraper_id: str
    host: str
    contract_name: str
    contract_version: str
    run_params: Dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    idempotency_key: str

    @field_validator("idempotency_key")
    @classmethod
    def _check_idem(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("idempotency_key required")
        return v


class HeartbeatPayload(_StrictModel):
    run_id: UUID
    scraper_id: str
    ts: datetime
    agent_id: str = "default"
    items_collected_so_far: int = 0
    items_per_minute: Optional[float] = None
    mem_mb: Optional[int] = None
    cpu_pct: Optional[float] = None
    note: Optional[str] = Field(default=None, max_length=256)
    idempotency_key: str

    @field_validator("items_collected_so_far")
    @classmethod
    def _ge_zero(cls, v: int) -> int:
        if v < 0:
            raise ValueError("items_collected_so_far must be >= 0")
        return v

    @field_validator("items_per_minute")
    @classmethod
    def _ipm_nonneg(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("items_per_minute must be >= 0")
        return v

    @field_validator("mem_mb")
    @classmethod
    def _mem_nonneg(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("mem_mb must be >= 0")
        return v

    @field_validator("cpu_pct")
    @classmethod
    def _cpu_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0 or v > 100):
            raise ValueError("cpu_pct must be in [0, 100]")
        return v


class EndRunPayload(_StrictModel):
    run_id: UUID
    status: str
    ended_at: Optional[datetime] = None
    items_extracted: Optional[int] = None
    items_valid_local: Optional[int] = None
    items_sent: Optional[int] = None
    items_rejected_schema: Optional[int] = None
    items_final_inserted: int = 0
    batches_total: Optional[int] = None
    error_count_transient: Optional[int] = None
    retry_count: Optional[int] = None
    rate_limit_hits: Optional[int] = None
    idempotency_key: str

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in RUN_END_OK:
            raise ValueError(f"status must be one of {RUN_END_OK}")
        return v

    @field_validator("items_final_inserted")
    @classmethod
    def _must_be_zero(cls, v: int) -> int:
        # MVP: items_final_inserted sempre 0 (regra inegociavel).
        if v != 0:
            raise ValueError(
                "items_final_inserted must be 0 in MVP (no business data writes)"
            )
        return v

    @field_validator(
        "items_extracted", "items_valid_local", "items_sent",
        "items_rejected_schema", "batches_total",
        "error_count_transient", "retry_count", "rate_limit_hits",
    )
    @classmethod
    def _counter_nonneg(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("counter must be >= 0")
        return v


class FailRunPayload(_StrictModel):
    run_id: UUID
    status: str
    ended_at: Optional[datetime] = None
    error_count_fatal: int = 1
    error_summary: str = Field(max_length=2048)
    idempotency_key: str

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in RUN_END_FAIL:
            raise ValueError(f"status must be one of {RUN_END_FAIL}")
        return v

    @field_validator("error_count_fatal")
    @classmethod
    def _ge_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError("error_count_fatal must be >= 1")
        return v


# ---------------------------------------------------------------------------
# Events / Batch
# ---------------------------------------------------------------------------

class EventPayload(_StrictModel):
    event_id: UUID
    run_id: Optional[UUID] = None
    scraper_id: str
    ts: datetime
    level: str = "info"
    code: str = Field(max_length=64)
    message: str = Field(max_length=1024)
    payload_hash: Optional[str] = Field(default=None, max_length=64)
    payload_sample: Optional[str] = Field(default=None, max_length=1024)
    payload_pointer: Optional[str] = None
    idempotency_key: str

    @field_validator("level")
    @classmethod
    def _check_level(cls, v: str) -> str:
        if v not in LEVEL_VALUES:
            raise ValueError(f"level must be one of {LEVEL_VALUES}")
        return v


class SourceLineage(_StrictModel):
    source_system: str
    source_kind: str
    source_pointer: str
    source_record_count: Optional[int] = None
    source_read_at: Optional[datetime] = None
    notes: Optional[str] = None

    @field_validator("source_kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        if v not in SOURCE_KIND_VALUES:
            raise ValueError(f"source_kind must be one of {SOURCE_KIND_VALUES}")
        return v

    @field_validator("source_record_count")
    @classmethod
    def _src_count_nonneg(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("source_record_count must be >= 0")
        return v


class BatchEventPayload(_StrictModel):
    batch_id: UUID
    run_id: UUID
    scraper_id: str
    seq: int
    ts: datetime
    items_extracted: int = 0
    items_valid_local: int = 0
    items_sent: int = 0
    items_accepted_ready: int = 0
    items_rejected_notwine: int = 0
    items_needs_enrichment: int = 0
    items_uncertain: int = 0
    items_duplicate: int = 0
    items_final_inserted: int = 0
    items_errored_transport: int = 0
    items_per_second: Optional[float] = None
    time_to_first_item_ms: Optional[int] = None
    items_rejected_schema: int = 0
    field_coverage: Dict[str, float] = Field(default_factory=dict)
    source_lineage: Optional[SourceLineage] = None
    delivery_target: str = "ops"
    delivery_status: str = "ok"
    idempotency_key: str

    @field_validator("seq")
    @classmethod
    def _seq_ge_zero(cls, v: int) -> int:
        if v < 0:
            raise ValueError("seq must be >= 0")
        return v

    @field_validator("items_final_inserted")
    @classmethod
    def _must_be_zero(cls, v: int) -> int:
        if v != 0:
            raise ValueError(
                "items_final_inserted must be 0 in MVP (no business data writes)"
            )
        return v

    @field_validator(
        "items_extracted", "items_valid_local", "items_sent",
        "items_accepted_ready", "items_rejected_notwine",
        "items_needs_enrichment", "items_uncertain",
        "items_duplicate", "items_errored_transport",
        "items_rejected_schema",
    )
    @classmethod
    def _counters_nonneg(cls, v: int) -> int:
        if v < 0:
            raise ValueError("counter must be >= 0")
        return v

    @field_validator("items_per_second")
    @classmethod
    def _ips_nonneg(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("items_per_second must be >= 0")
        return v

    @field_validator("time_to_first_item_ms")
    @classmethod
    def _ttfi_nonneg(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("time_to_first_item_ms must be >= 0")
        return v

    @field_validator("field_coverage")
    @classmethod
    def _coverage_range(cls, v: Dict[str, float]) -> Dict[str, float]:
        for k, val in v.items():
            if val < 0 or val > 1:
                raise ValueError(f"field_coverage[{k}] must be in [0,1]")
        return v

    @field_validator("delivery_target")
    @classmethod
    def _check_target(cls, v: str) -> str:
        if v not in DELIVERY_TARGET_VALUES:
            raise ValueError(f"delivery_target must be one of {DELIVERY_TARGET_VALUES}")
        return v

    @field_validator("delivery_status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in DELIVERY_STATUS_VALUES:
            raise ValueError(f"delivery_status must be one of {DELIVERY_STATUS_VALUES}")
        return v
