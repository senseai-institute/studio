# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Provenance: where every item of a response came from, and YAML read with line numbers.

Every API response carries ``provenance: [{field, source_file, line_or_key}]``. ``field`` is a
slash path into the response (``quantities/2/value``); ``source_file`` is ``<repo>/<path>``
(``profiles/library/felidae.yaml``); ``line_or_key`` is a 1-based line number when the file has
lines, else a key (a CLI's JSON key, a CSV row id).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

Key = tuple[str | int, ...]


@dataclass
class Prov:
    """Collects provenance entries while a response is built."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(self, fld: str, source_file: str, line_or_key: int | str | None) -> None:
        """Record that ``fld`` of the response came from ``source_file`` at ``line_or_key``."""
        self.entries.append({"field": fld, "source_file": source_file, "line_or_key": line_or_key})

    def extend(self, prefix: str, other: Prov) -> None:
        """Take another collector's entries under ``prefix``."""
        for e in other.entries:
            self.entries.append(e | {"field": f"{prefix}/{e['field']}" if prefix else e["field"]})

    def out(self) -> list[dict[str, Any]]:
        """The entries, for the response."""
        return self.entries


@dataclass
class Located:
    """A YAML document and the line of every node in it."""

    data: Any
    lines: dict[Key, int]
    label: str  # "<repo>/<relative path>"

    def line(self, *key: str | int) -> int | None:
        """Line of the node at ``key`` (or of its nearest parent)."""
        k: Key = tuple(key)
        while k:
            if k in self.lines:
                return self.lines[k]
            k = k[:-1]
        return self.lines.get((), 1)


def _walk(node: yaml.Node, key: Key, out: dict[Key, int]) -> None:
    out.setdefault(key, node.start_mark.line + 1)
    if isinstance(node, yaml.MappingNode):
        for k_node, v_node in node.value:
            k = (*key, str(k_node.value))
            out[k] = k_node.start_mark.line + 1
            _walk(v_node, k, out)
    elif isinstance(node, yaml.SequenceNode):
        for i, v in enumerate(node.value):
            _walk(v, (*key, i), out)


def load_located(path: Path, label: str) -> Located:
    """Read a YAML file keeping the line of every node (mapping keys are strings)."""
    text = path.read_text(encoding="utf-8")
    lines: dict[Key, int] = {}
    node = yaml.compose(text, Loader=yaml.SafeLoader)
    if node is not None:
        _walk(node, (), lines)
    return Located(yaml.safe_load(text), lines, label)


def rel(path: Path, root: Path, repo: str) -> str:
    """``<repo>/<path relative to root>``, or the path itself when outside the root."""
    try:
        return f"{repo}/{path.resolve().relative_to(root.resolve()).as_posix()}"
    except ValueError:
        return str(path)
