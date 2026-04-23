from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ExportState = Literal[
    "observed",
    "registered_planned",
    "blocked_external_host",
    "blocked_missing_source",
    "blocked_contract_missing",
]


class DiscoveryStoreRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    domain: str
    normalized_domain: str
    url: str | None = None
    store_name: str | None = None
    country: str | None = None
    platform: str | None = None
    validation_status: str
    tier_hint: str | None = None
    already_known_store: bool = False
    known_store_id: int | None = None
    recipe_candidate: dict[str, Any] | None = None
    source_lineage: dict[str, Any]


class ExportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    state: ExportState
    items: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
