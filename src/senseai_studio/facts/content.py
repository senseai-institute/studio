# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Founder-owned content under ``STUDIO_CONTENT``: modalities, senses, pipeline steps, use cases.

Studio writes nothing but use-case *templates* (``senseai-studio check --write-templates``),
and only into ``STUDIO_CONTENT``; it never writes into an upstream checkout.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from markdown_it import MarkdownIt

from senseai_studio.prov import Located, load_located

_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)
USE_CASE_SECTIONS = (
    "The job",
    "Where human perception fails",
    "What the model offers",
    "Caveats",
)


def modalities(content: Path) -> Located:
    """``modalities.yaml``: library modality -> streams, datasets, live view."""
    p = content / "modalities.yaml"
    if not p.is_file():
        return Located({}, {}, "studio/content/modalities.yaml")
    return load_located(p, "studio/content/modalities.yaml")


def circuits(content: Path) -> Located:
    """``circuits.yaml``: circuit knob prefix -> name, library modalities it serves."""
    p = content / "circuits.yaml"
    if not p.is_file():
        return Located({}, {}, "studio/content/circuits.yaml")
    return load_located(p, "studio/content/circuits.yaml")


def senses(content: Path) -> Located:
    """``senses.yaml``: library modality -> label and the terms Explore searches papers for."""
    p = content / "senses.yaml"
    if not p.is_file():
        return Located({}, {}, "studio/content/senses.yaml")
    return load_located(p, "studio/content/senses.yaml")


def pipeline_steps(content: Path, profiles: Path) -> Located:
    """The step list: the profiles checkout's ``docs/pipeline/steps.yaml`` when present."""
    up = profiles / "docs" / "pipeline" / "steps.yaml"
    if up.is_file():
        return load_located(up, "profiles/docs/pipeline/steps.yaml")
    p = content / "pipeline.yaml"
    if not p.is_file():
        return Located({"steps": []}, {}, "studio/content/pipeline.yaml")
    return load_located(p, "studio/content/pipeline.yaml")


def front_matter(text: str) -> tuple[dict[str, Any], str, int]:
    """(front matter, body, line where the body starts)."""
    m = _FRONT.match(text)
    if not m:
        return {}, text, 1
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return (
        (meta if isinstance(meta, dict) else {}),
        text[m.end() :],
        text[: m.end()].count("\n") + 1,
    )


@dataclass
class UseCase:
    """One use-case file."""

    path: Path
    niche: str
    sense: str
    meta: dict[str, Any]
    body: str
    body_line: int

    @property
    def label(self) -> str:
        """``studio/content/use_cases/<file>``."""
        return f"studio/content/use_cases/{self.path.name}"

    @property
    def is_template(self) -> bool:
        """A template nobody has filled in yet."""
        return bool(self.meta.get("template"))


def use_cases(content: Path) -> list[UseCase]:
    """Every ``use_cases/<niche>.<sense>.md``."""
    out: list[UseCase] = []
    d = content / "use_cases"
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.md")):
        stem = p.name[: -len(".md")]
        niche, _, sense = stem.rpartition(".")
        if not niche:
            continue
        meta, body, line = front_matter(p.read_text(encoding="utf-8"))
        out.append(UseCase(p, niche, sense, meta, body, line))
    return out


def matching(cases: list[UseCase], clade: str, sense: str, names: list[str]) -> list[UseCase]:
    """Use cases for a clade+sense: by file niche, or by ``species`` in the front matter."""
    keys = {clade, *names}
    out = []
    for c in cases:
        if c.sense != sense:
            continue
        species = {str(s) for s in (c.meta.get("species") or [])}
        if c.niche in keys or species & keys:
            out.append(c)
    return out


_md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")


def render(body: str) -> str:
    """Markdown to HTML. Raw HTML in the source is escaped, not passed through."""
    return str(_md.render(body))


def template(niche: str, sense: str) -> str:
    """An empty use-case file: front matter and the four headings, no claims."""
    heads = "\n\n".join(f"## {h}\n\n_Not written yet._" for h in USE_CASE_SECTIONS)
    return f"---\nspecies: [{niche}]\nstatus: idea\nevidence: []\ntemplate: true\n---\n\n{heads}\n"


def write_templates(content: Path, pairs: list[tuple[str, str]]) -> list[Path]:
    """Create a template for every (niche, sense) that has no file yet."""
    d = content / "use_cases"
    d.mkdir(parents=True, exist_ok=True)
    made = []
    for niche, sense in pairs:
        p = d / f"{niche}.{sense}.md"
        if not p.exists():
            p.write_text(template(niche, sense), encoding="utf-8")
            made.append(p)
    return made
