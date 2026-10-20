# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""The species library (``<profiles>/library/*.yaml``) read as located records.

Studio reads the files directly so every value keeps its line number. It never validates or
rewrites them: that is ``senseai-profiles validate``'s job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from senseai_studio.prov import Located, load_located

#: The quantity slots of a sense, in the schema's order (clade.schema.json ``$defs.sense``).
SENSE_SLOTS = (
    "detection_threshold",
    "range",
    "latency_ms",
    "bandwidth",
    "spatial_resolution",
    "field_of_view_deg",
)
QUANTITY_KEYS = ("value", "unit", "confidence", "species", "conditions", "notes", "citations")


@dataclass
class Quantity:
    """One cited value with the library path that names it and the line it sits on."""

    path: str  # felidae.senses.vision.detection_threshold
    slot: str  # detection_threshold | measurement id | behaviour.<name>.latency_ms
    description: str | None
    record: dict[str, Any]
    key: tuple[str | int, ...]  # location in the YAML document

    def get(self, k: str) -> Any:
        """A field of the quantity record."""
        return self.record.get(k)


@dataclass
class Sense:
    """A sense of a clade."""

    clade: str
    id: str
    index: int
    record: dict[str, Any]

    @property
    def modality(self) -> str:
        """The schema's modality enum value."""
        return str(self.record.get("modality", ""))


@dataclass
class Clade:
    """A library entry."""

    key: str  # file stem, lower case: felidae
    doc: Located
    path: Path
    senses: dict[str, Sense] = field(default_factory=dict)

    @property
    def data(self) -> dict[str, Any]:
        """The parsed YAML."""
        return self.doc.data if isinstance(self.doc.data, dict) else {}

    def quantities(self, sense: str) -> list[Quantity]:
        """Every quantity of a sense, then of the behaviours that use it, in document order."""
        s = self.senses[sense]
        out: list[Quantity] = []
        base = ("senses", s.index)
        for slot in SENSE_SLOTS:
            rec = s.record.get(slot)
            if isinstance(rec, dict) and "value" in rec:
                out.append(
                    Quantity(f"{self.key}.senses.{sense}.{slot}", slot, None, rec, (*base, slot))
                )
        for j, m in enumerate(s.record.get("measurements") or []):
            out.append(
                Quantity(
                    f"{self.key}.senses.{sense}.measurements.{m.get('id')}",
                    str(m.get("id")),
                    m.get("description"),
                    m,
                    (*base, "measurements", j),
                )
            )
        for i, b in enumerate(self.data.get("behaviours") or []):
            if sense not in (b.get("uses_senses") or []):
                continue
            name = b.get("name")
            lat = b.get("latency_ms")
            if isinstance(lat, dict) and "value" in lat:
                out.append(
                    Quantity(
                        f"{self.key}.behaviours.{name}.latency_ms",
                        f"{name}.latency_ms",
                        b.get("description"),
                        lat,
                        ("behaviours", i, "latency_ms"),
                    )
                )
            for j, m in enumerate(b.get("measurements") or []):
                out.append(
                    Quantity(
                        f"{self.key}.behaviours.{name}.measurements.{m.get('id')}",
                        f"{name}.{m.get('id')}",
                        m.get("description"),
                        m,
                        ("behaviours", i, "measurements", j),
                    )
                )
        return out

    def open_questions(self, sense: str) -> list[tuple[str, tuple[str | int, ...]]]:
        """Open questions of the sense, of behaviours using it, and of the whole entry."""
        s = self.senses[sense]
        out: list[tuple[str, tuple[str | int, ...]]] = [
            (q, ("senses", s.index, "open_questions", i))
            for i, q in enumerate(s.record.get("open_questions") or [])
        ]
        for bi, b in enumerate(self.data.get("behaviours") or []):
            if sense in (b.get("uses_senses") or []):
                out += [
                    (f"{b.get('name')}: {q}", ("behaviours", bi, "open_questions", i))
                    for i, q in enumerate(b.get("open_questions") or [])
                ]
        out += [
            (q, ("open_questions", i)) for i, q in enumerate(self.data.get("open_questions") or [])
        ]
        return out


def load(repo: Path) -> dict[str, Clade]:
    """Every ``library/*.yaml`` of a profiles checkout, keyed by file stem."""
    lib = repo / "library"
    out: dict[str, Clade] = {}
    for p in sorted(lib.glob("*.yaml")):
        doc = load_located(p, f"profiles/library/{p.name}")
        c = Clade(p.stem, doc, p)
        for i, s in enumerate(c.data.get("senses") or []):
            if isinstance(s, dict) and s.get("id"):
                c.senses[str(s["id"])] = Sense(p.stem, str(s["id"]), i, s)
        out[p.stem] = c
    return out


def describes(c: Clade, sense: str) -> bool:
    """Whether the entry holds at least one cited value for the sense."""
    return bool(c.quantities(sense))
