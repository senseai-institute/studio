# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Ask an upstream package a question and print the answer as JSON on stdout.

Run as a script by :mod:`senseai_studio.facts.upstream` in a subprocess, with whichever
interpreter can import the upstream code (Studio's own for a profiles checkout, the stack's for
bench and checkpoints). Standalone on purpose: it imports nothing from senseai_studio, so any
Python with the upstream package on its path can run it. Studio never imports upstream code
into the server process.

    python probe.py profiles <profiles repo>          specs, rules, consumers_by_path
    python probe.py world <params.py> <library.yaml>  PriorParams.from_library(...).provenance()
    python probe.py bench                             replay-compare's arm table and flags
    python probe.py ckpt <file.ckpt>                  a senseai-world checkpoint's metadata
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def _jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if hasattr(v, "tolist"):
        return _jsonable(v.tolist())
    return str(v)


def profiles(repo: Path) -> dict[str, Any]:
    from senseai_profiles import __file__ as pkg_file
    from senseai_profiles.registry import Registry
    from senseai_profiles.research import consumers_by_path
    from senseai_profiles.rules import all_rules
    from senseai_profiles.spec import RuleCall

    reg = Registry(repo, strict=False)
    out_specs: dict[str, Any] = {}
    for name, spec in reg.specs.items():
        fields: list[dict[str, Any]] = []
        sections = [(f"heads.{h}", h, f) for h, f in spec.heads.items()]
        sections.append(("reflex", "reflex", spec.reflex))
        for where, section, flds in sections:
            for fld, v in flds.items():
                row: dict[str, Any] = {"section": section, "field": fld, "where": f"{where}.{fld}"}
                if isinstance(v, RuleCall):
                    row |= {
                        "kind": "rule",
                        "rule": v.name,
                        "text": " ".join(v.text.split()),
                        "output": v.rule.info.output,
                        "rationale": v.rule.info.rationale,
                        "library_paths": dict(v.library_paths),
                        "sensor_paths": dict(v.sensor_paths),
                        "value": None,
                    }
                    if v.rule.info.output in ("scalar", "reflex_scalar") and not v.sensor_paths:
                        try:
                            d = v.rule.distill(**v.args)
                            row["value"] = float(d.arrays["value"])
                            row["literals"] = _jsonable(d.literals)
                        except Exception as e:
                            row["value_error"] = f"{type(e).__name__}: {e}"
                else:
                    row |= {"kind": "literal", "literal": _jsonable(v)}
                fields.append(row)
        out_specs[name] = {
            "name": name,
            "version": spec.version,
            "description": spec.description,
            "clades": list(spec.clades),
            "spec_hash": spec.spec_hash,
            "source": str(spec.source) if spec.source else None,
            "bundles": reg.versions(name),
            "sensors": dict(spec.sensors),
            "context": dict(spec.context),
            "fields": fields,
            "heads": sorted(spec.heads),
        }
    consumers = {
        p: [
            {"profile": c.profile, "section": c.section, "field": c.field, "rule": c.rule}
            for c in cs
        ]
        for p, cs in consumers_by_path(reg.specs).items()
    }
    rules = {
        n: {"output": r.info.output, "rationale": r.info.rationale} for n, r in all_rules().items()
    }
    return {
        "ok": True,
        "package": str(Path(pkg_file).parent),
        "specs": out_specs,
        "consumers": consumers,
        "rules": rules,
        "issues": list(reg.issues),
    }


def world(params_py: Path, library: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("_senseai_world_prior_params", params_py)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {params_py}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses look the module up while building the class
    spec.loader.exec_module(mod)
    p = mod.PriorParams.from_library(library)
    return {"ok": True, "params": _jsonable(p.provenance()), "proposed": p.proposed()}


def bench() -> dict[str, Any]:
    import contextlib
    import io

    from senseai_bench.replay import cli as rc

    parser_help = ""
    with contextlib.suppress(Exception):
        import argparse

        ap = argparse.ArgumentParser()
        rc.add_parser(ap.add_subparsers())
        sub = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))
        buf = io.StringIO()
        sub.choices["replay-compare"].print_help(buf)
        parser_help = buf.getvalue()
    return {
        "ok": True,
        "arms": dict(getattr(rc, "ARMS", {})),
        "sdk_profiles": dict(getattr(rc, "SDK_PROFILES", {})),
        "world_modes": dict(getattr(rc, "SDK_WORLD_MODES", {})),
        "help": parser_help,
    }


def ckpt(path: Path) -> dict[str, Any]:
    import torch

    blob = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(blob, dict) or blob.get("format") != "senseai-world/ckpt":
        raise ValueError(f"{path}: not a senseai-world checkpoint")
    cfg = blob.get("config") or {}
    return {
        "ok": True,
        "model_id": blob.get("model_id"),
        "step": blob.get("step"),
        "param_counts": _jsonable(blob.get("param_counts") or {}),
        "provenance": _jsonable(blob.get("provenance") or {}),
        "metrics": _jsonable(blob.get("metrics") or {}),
        "tokens": _jsonable(cfg.get("tokens") or cfg.get("tokenizer") or {}),
    }


def main(argv: list[str]) -> int:
    cmd, *args = argv
    try:
        if cmd == "profiles":
            res = profiles(Path(args[0]))
        elif cmd == "world":
            res = world(Path(args[0]), Path(args[1]))
        elif cmd == "bench":
            res = bench()
        elif cmd == "ckpt":
            res = ckpt(Path(args[0]))
        else:
            raise SystemExit(f"unknown probe {cmd!r}")
    except Exception as e:
        res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    json.dump(res, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
