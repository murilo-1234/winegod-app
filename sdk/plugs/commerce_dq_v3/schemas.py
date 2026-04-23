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


class CommerceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: int
    url: str
    preco: float | None = None
    moeda: str | None = None
    disponivel: bool = True
    external_id: str | None = None


class CommerceCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    nome: str = Field(min_length=1)
    produtor: str | None = None
    safra: str | None = None
    tipo: str | None = None
    pais: str | None = None
    regiao: str | None = None
    sub_regiao: str | None = None
    uvas: str | list[str] | None = None
    ean_gtin: str | None = None
    imagem_url: str | None = None
    harmonizacao: str | None = None
    descricao: str | None = None
    preco_min: float | None = None
    preco_max: float | None = None
    moeda: str | None = None
    sources: list[CommerceSource] = Field(default_factory=list)


class ExportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    state: ExportState
    items: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    command_hint: str | None = None
    unresolved_domains: list[str] = Field(default_factory=list)
