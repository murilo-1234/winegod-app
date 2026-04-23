from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReviewScoreRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    wine_identity: dict[str, Any]
    score: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    reviewer_ref: dict[str, Any] | None = None
    source_lineage: dict[str, Any]


class ExportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
