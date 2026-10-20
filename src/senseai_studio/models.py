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
    source_file: str = Field(description="<repo>/<path>, e.g. profiles/library/felidae.yaml")
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
