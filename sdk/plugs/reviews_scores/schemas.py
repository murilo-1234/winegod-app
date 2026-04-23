from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# Map de origem -> fonte canonica armazenada em wine_scores.fonte
# Manter curto e estavel porque vira chave unica junto com wine_id.
SIGNAL_KIND_BY_SOURCE = {
    "vivino_wines_to_ratings": "vivino",
    "vivino_reviews_to_scores_reviews": "vivino_review",
    "cellartracker_to_scores_reviews": "cellartracker",
    "decanter_to_critic_scores": "decanter",
    "wine_enthusiast_to_critic_scores": "wine_enthusiast",
    "winesearcher_to_market_signals": "winesearcher",
}

# Sinais que suportam UPDATE em wines.vivino_rating / wines.vivino_reviews.
SOURCES_THAT_UPDATE_WINES = {"vivino_wines_to_ratings"}

# Sinais que sao per-review (nao per-wine). Nao aplicam em wine_scores.
PER_REVIEW_SOURCES = {"vivino_reviews_to_scores_reviews"}


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
