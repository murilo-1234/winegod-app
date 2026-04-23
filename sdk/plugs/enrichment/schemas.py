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


class EnrichmentStageRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    route: str
    wine_identity: dict[str, Any]
    enrichment: dict[str, Any]
    source_lineage: dict[str, Any]


class ExportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    state: ExportState
    items: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
