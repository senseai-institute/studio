# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Profile specs and which of them read a clade's sense.

The answer comes from senseai-profiles itself (``Registry`` + ``research.consumers_by_path``,
through the probe). When that code cannot run, the spec files are read as plain YAML and the
library paths are taken from the ``rule(...)`` text; the response then says ``engine:
"yaml-fallback"`` and rule values are not distilled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from senseai_studio.facts import upstream
from senseai_studio.facts.library import Clade
from senseai_studio.settings import Settings

SPECS_DIR = Path("packages/senseai-profiles/profiles")
_RULE = re.compile(r"^\s*rule\(\s*([A-Za-z_]\w*)\s*(?:,(.*))?\)\s*$", re.S)
_ARG = re.compile(r"([A-Za-z_]\w*)\s*=\s*([^,]+)")
_LIBPATH = re.compile(r"^[a-z][a-z0-9_]*\.(senses|behaviours)\.[a-z0-9_]+(\.[a-z0-9_]+){1,2}$")


@dataclass
class Specs:
    """Profile specs and consumers, from the engine or the fallback."""

    engine: str  # "senseai-profiles" | "yaml-fallback"
    specs: dict[str, dict[str, Any]]
    consumers: dict[str, list[dict[str, Any]]]
    issues: list[str]
    error: str | None = None

    def readers(self, clade: Clade, sense: str) -> list[dict[str, Any]]:
        """Consumers of any library path of this sense, or of a behaviour that uses it."""
        prefix = f"{clade.key}.senses.{sense}."
        behaviours = {
            str(b.get("name"))
            for b in clade.data.get("behaviours") or []
            if sense in (b.get("uses_senses") or [])
        }
        out: list[dict[str, Any]] = []
        for path, cs in sorted(self.consumers.items()):
            parts = path.split(".")
            hit = path.startswith(prefix) or (
                len(parts) > 2
                and parts[0] == clade.key
                and parts[1] == "behaviours"
                and parts[2] in behaviours
            )
            if hit:
                out += [c | {"path": path} for c in cs]
        return out

    def profiles_reading(self, clade: Clade, sense: str) -> list[str]:
        """Profile names that read this clade+sense, in name order."""
        return sorted({c["profile"] for c in self.readers(clade, sense)})

    def controls(self) -> list[str]:
        """Control profiles: specs that set no head prior (every head keeps its default)."""
        return sorted(n for n, s in self.specs.items() if not s.get("heads"))


def _fallback(repo: Path, error: str) -> Specs:
    specs: dict[str, dict[str, Any]] = {}
    consumers: dict[str, list[dict[str, Any]]] = {}
    issues: list[str] = []
    for p in sorted((repo / SPECS_DIR).glob("*.profile.yaml")):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            issues.append(f"{p.name}: {e}")
            continue
        name = str(data.get("name") or p.name.split(".")[0])
        fields: list[dict[str, Any]] = []
        sections = [(h, f) for h, f in (data.get("heads") or {}).items()]
        sections.append(("reflex", data.get("reflex") or {}))
        for section, flds in sections:
            for fld, v in (flds or {}).items():
                m = _RULE.match(v) if isinstance(v, str) else None
                where = f"{'reflex' if section == 'reflex' else 'heads.' + section}.{fld}"
                if m:
                    args = dict(_ARG.findall(m.group(2) or ""))
                    lib = {k: a.strip() for k, a in args.items() if _LIBPATH.match(a.strip())}
                    fields.append(
                        {
                            "section": section,
                            "field": fld,
                            "where": where,
                            "kind": "rule",
                            "rule": m.group(1),
                            "text": " ".join(v.split()),
                            "library_paths": lib,
                            "sensor_paths": {},
                            "value": None,
                        }
                    )
                    for path in lib.values():
                        consumers.setdefault(path, []).append(
                            {"profile": name, "section": section, "field": fld, "rule": m.group(1)}
                        )
                else:
                    fields.append(
                        {
                            "section": section,
                            "field": fld,
                            "where": where,
                            "kind": "literal",
                            "literal": v,
                        }
                    )
        specs[name] = {
            "name": name,
            "version": data.get("version"),
            "description": data.get("description"),
            "clades": list(data.get("clades") or []),
            "spec_hash": None,
            "source": str(p),
            "bundles": [],
            "sensors": dict(data.get("sensors") or {}),
            "context": dict(data.get("context") or {}),
            "fields": fields,
            "heads": sorted(data.get("heads") or {}),
        }
    return Specs("yaml-fallback", specs, consumers, issues, error)


def load(cfg: Settings) -> Specs:
    """Specs from senseai-profiles when it runs, else from the YAML files."""
    res = upstream.profiles(cfg)
    if res.get("ok"):
        return Specs("senseai-profiles", res["specs"], res["consumers"], res.get("issues", []))
    return _fallback(cfg.profiles, str(res.get("error")))


def spec_line(cfg: Settings, spec: dict[str, Any], where: str) -> int | None:
    """Line of ``heads.frame.gain_lut`` (or ``reflex.x``) in the spec file."""
    from senseai_studio.prov import load_located

    src = spec.get("source")
    if not src or not Path(src).is_file():
        return None
    doc = load_located(Path(src), "")
    return doc.line(*where.split("."))


def spec_label(cfg: Settings, spec: dict[str, Any]) -> str:
    """``profiles/packages/senseai-profiles/profiles/<name>.profile.yaml``."""
    src = spec.get("source")
    if not src:
        return "profiles/" + (SPECS_DIR / f"{spec['name']}.profile.yaml").as_posix()
    from senseai_studio.prov import rel

    return rel(Path(src), cfg.profiles, "profiles")
