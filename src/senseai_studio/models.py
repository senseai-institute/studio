# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Response shapes of the Studio API: the interoperability contract published as OpenAPI.

Top-level fields are typed; nested records stay open (``extra="allow"``) because they mirror
upstream files whose optional keys Studio passes through unchanged.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Open(BaseModel):
    """A record that may carry more keys than listed."""

    model_config = ConfigDict(extra="allow")


class Provenance(BaseModel):
    """Where one item of a response came from."""

    field: str = Field(description="slash path into this response, e.g. quantities/0/value")
    source_file: str = Field(description="<repo>/<path>, e.g. profiles/library/<clade>.yaml")
    line_or_key: int | str | None = Field(description="1-based line, or a key for non-text sources")


class Envelope(Open):
    """Every response carries provenance."""

    provenance: list[Provenance]


class SenseChip(Open):
    """A sense on a Home card."""

    id: str
    modality: str
    state: str = Field(description="modelled | described | empty")
    data: str = Field(description="available | synthetic | none")
    step: int
    steps: int
    profiles: list[str]


class Card(Open):
    """A clade on Home."""

    clade: str
    latin: str | None
    names: list[str]
    niche: str | None
    senses: list[SenseChip]


class SpeciesOut(Envelope):
    """``GET /api/studio/species``."""

    cards: list[Card]
    engine: str


class SourcesOut(Envelope):
    """``GET /api/studio/{clade}/{sense}/sources``."""

    clade: str
    sense: str
    sense_info: dict[str, Any]
    quantities: list[Open]
    table: dict[str, Any]
    open_questions: list[Open]
    requests: list[Open]


class ModelOut(Envelope):
    """``GET /api/studio/{clade}/{sense}/model``."""

    clade: str
    sense: str
    engine: str
    circuits: dict[str, Any]
    profiles: list[Open]
    world_prior: dict[str, Any]
    learned: list[Open]
    reflex: list[Open]
    rulebook: dict[str, Any]


class Step(Open):
    """One pipeline step."""

    n: int
    name: str | None
    done: bool
    at: str | None
    detail: str


class PipelineOut(Envelope):
    """``GET /api/studio/{clade}/{sense}/pipeline``."""

    clade: str
    sense: str
    steps: list[Step]
    at: int
    total: int
    clock: dict[str, Any]


class UseCasesOut(Envelope):
    """``GET /api/studio/{clade}/{sense}/use-cases``."""

    clade: str
    sense: str
    items: list[Open]
    step: int
    steps: int


class RunOptionsOut(Envelope):
    """``GET /api/studio/{clade}/{sense}/run/options``."""

    sources: list[Open]
    arms: list[Open]
    bench: dict[str, Any]
    prereg: list[Open]


class JobOut(Open):
    """A run job."""

    id: str
    status: str


class HealthOut(Envelope):
    """``GET /api/studio/health``."""

    ok: bool
    repos: dict[str, Any]
    engine: str


class Taxon(Open):
    """A taxon from GBIF's backbone, with the library entry covering it, if any."""

    key: int
    scientific_name: str | None
    rank: str | None
    common_names: list[str]
    library: dict[str, Any] | None


class ExploreSpeciesOut(Envelope):
    """``GET /api/studio/explore/species``."""

    query: str
    taxa: list[Taxon]


class ExploreTaxonOut(Envelope):
    """``GET /api/studio/explore/taxon/{key}``."""

    taxon: Taxon
    senses: list[Open] = Field(description="{id, label, terms, filter, count, top, library}")


class ExplorePapersOut(Envelope):
    """``GET /api/studio/explore/taxon/{key}/{sense}/papers``."""

    taxon: Taxon
    sense: dict[str, Any]
    source: str = Field(description="openalex, or europepmc when OpenAlex is rate-limiting")
    filter: str = Field(description="the query the papers came from, in that source's syntax")
    sort: str
    page: int
    per_page: int
    pages: int
    total: int
    papers: list[Open]
    years: list[Open]


class DesignOut(Open):
    """A circuit design (senseai-circuits design@1 plus Studio's record of the people's side)."""

    id: str
    title: str
    clade: str
    sense: str
    profile: str | None
    values: dict[str, Any]
    bindings: dict[str, Any]
    candidate_ids: list[str]
    status: str = Field(description="draft | validated | adopted | rejected")
    check: dict[str, Any] | None = Field(description="the last senseai-circuits design check")
    adoption: dict[str, Any] | None
    research_sync: list[dict[str, Any]] = Field(description="decisions sent to research")
    history: list[dict[str, Any]]


class DesignPageOut(Envelope):
    """``GET /api/studio/{clade}/{sense}/design``."""

    clade: str
    sense: str
    modality: str
    circuits: dict[str, Any]
    circuit_types: list[dict[str, Any]]
    measures: list[dict[str, Any]]
    knobs: list[dict[str, Any]]
    profiles: list[dict[str, Any]]
    research: dict[str, Any]
    candidates: list[dict[str, Any]] = Field(description="research's circuit candidates, ranked")
    designs: list[DesignOut]


class FiguresOut(Open):
    """``POST /api/studio/design/figures``: senseai-circuits figures."""

    ok: bool
    figures: list[dict[str, Any]]
