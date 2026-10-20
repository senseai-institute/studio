# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Evidence beside the library: the P0 evidence tables, the rulebook and research requests.

Tables (``library/tables/<clade>.<sense>.csv``) and the rulebook (``rulebook/*.yaml``) arrive
with the profiles P0 change. Until a checkout has them every reader returns ``present: False``
and the UI says so. Column and key names are matched loosely (see docs/UPSTREAM.md) so a
renamed column degrades to a blank cell, never to an error.
"""

from __future__ import annotations

import csv
import glob
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from senseai_studio.prov import Located, load_located, rel

PATH_COLS = ("path", "library_path", "quantity", "target")
STATUS_COLS = ("status", "verification", "verified")
QUOTE_COLS = ("quote", "verbatim_quote", "verbatim")


def _col(row: dict[str, str], names: tuple[str, ...]) -> str | None:
    lower = {k.strip().lower(): v for k, v in row.items() if k}
    for n in names:
        v = lower.get(n)
        if v not in (None, ""):
            return str(v).strip()
    return None


@dataclass
class Table:
    """One evidence table."""

    present: bool
    label: str
    rows: list[dict[str, Any]] = field(default_factory=list)  # each with _line

    def for_path(self, path: str) -> list[dict[str, Any]]:
        """Rows about one library path."""
        return [r for r in self.rows if r.get("_path") in (path, path.split(".", 1)[-1])]

    def counts(self, verified: tuple[str, ...] = ("verified",)) -> tuple[int, int]:
        """(verified rows, all rows)."""
        ok = sum(1 for r in self.rows if (r.get("_status") or "").lower() in verified)
        return ok, len(self.rows)


def table(profiles: Path, clade: str, sense: str, pattern: str | None = None) -> Table:
    """The evidence table of a clade+sense."""
    p = Path(pattern) if pattern else profiles / "library" / "tables" / f"{clade}.{sense}.csv"
    label = rel(p, profiles, "profiles")
    if not p.is_file():
        return Table(False, label)
    rows: list[dict[str, Any]] = []
    with p.open(newline="", encoding="utf-8") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):  # line 1 is the header
            rows.append(
                dict(r)
                | {
                    "_line": i,
                    "_path": _col(r, PATH_COLS),
                    "_status": _col(r, STATUS_COLS),
                    "_quote": _col(r, QUOTE_COLS),
                }
            )
    return Table(True, label, rows)


# --------------------------------------------------------------------------- rulebook


def rulebook(profiles: Path, patterns: list[str], clade: str, sense: str) -> dict[str, Any]:
    """Rules naming this clade+sense (by fields or by the library paths they read)."""
    files = sorted({Path(f) for pat in patterns for f in glob.glob(pat)})
    if not files:
        return {"present": False, "rules": [], "files": []}
    out: list[dict[str, Any]] = []
    prefix = f"{clade}.senses.{sense}"
    for f in files:
        doc = load_located(f, rel(f, profiles, "profiles"))
        data = doc.data
        items = data.get("rules", []) if isinstance(data, dict) else data
        base: tuple[str | int, ...] = ("rules",) if isinstance(data, dict) else ()
        for i, r in enumerate(items or []):
            if not isinstance(r, dict):
                continue
            reads = [str(x) for x in (r.get("reads") or r.get("library_paths") or [])]
            names_sense = (
                str(r.get("clade", "")).lower() == clade and str(r.get("sense", "")) == sense
            )
            if names_sense or any(x.startswith(prefix) for x in reads):
                out.append(
                    {
                        "id": r.get("id") or r.get("name"),
                        "status": r.get("status"),
                        "sets": r.get("sets") or r.get("knob") or r.get("field"),
                        "species": r.get("species") or r.get("profile"),
                        "reads": reads,
                        "source_file": doc.label,
                        "line": doc.line(*base, i),
                    }
                )
    return {"present": True, "rules": out, "files": [rel(f, profiles, "profiles") for f in files]}


# --------------------------------------------------------------------------- research requests


def requests(
    profiles: Path, clade: str, sense: str, profile_names: list[str]
) -> list[dict[str, Any]]:
    """Research requests targeting this sense, or a literal of a profile that reads it."""
    d = profiles / "research" / "requests"
    out: list[dict[str, Any]] = []
    if not d.is_dir():
        return out
    prefix = f"{clade}.senses.{sense}"
    for p in sorted(d.glob("*.yaml")):
        try:
            doc: Located = load_located(p, rel(p, profiles, "profiles"))
        except yaml.YAMLError:
            continue
        r = doc.data if isinstance(doc.data, dict) else {}
        target = str(r.get("target", ""))
        lit = r.get("target_kind") == "profile_literal" and target.split(".")[0] in profile_names
        if target == prefix or target.startswith(prefix + ".") or lit:
            why = r.get("why") or {}
            out.append(
                {
                    "id": r.get("id"),
                    "question": r.get("question"),
                    "status": r.get("status"),
                    "kind": r.get("kind"),
                    "target": target,
                    "priority": why.get("priority"),
                    "consumers": list(why.get("consumers") or []),
                    "source_file": doc.label,
                    "line": doc.line("question"),
                }
            )
    return out
