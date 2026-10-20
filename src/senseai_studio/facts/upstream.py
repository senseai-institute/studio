# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Answers from upstream code, run out of process and cached.

Profiles specs and consumers, the world prior's provenance, bench's arm table, checkpoint
metadata, circuits knobs, and repo SHAs.

Everything runs out of process (``probe.py`` or a CLI) and is cached until the files it read
change. A probe that cannot run returns ``{"ok": False, "error": ...}``; callers show that as a
badge instead of failing.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from senseai_studio.settings import Settings

T = TypeVar("T")
PROBE = Path(__file__).resolve().parents[1] / "probe.py"
PROFILES_SRC = Path("packages/senseai-profiles/src")
_cache: dict[tuple[Any, ...], tuple[Any, Any]] = {}
_lock = threading.Lock()


def fingerprint(*paths: Path) -> tuple[Any, ...]:
    """Cheap change detector: newest mtime and file count under each path (one level deep)."""
    out: list[Any] = []
    for p in paths:
        if not p.exists():
            out.append(None)
            continue
        if p.is_file():
            out.append(p.stat().st_mtime_ns)
            continue
        newest, n = p.stat().st_mtime_ns, 0
        for c in p.iterdir():
            try:
                newest = max(newest, c.stat().st_mtime_ns)
                n += 1
            except OSError:
                continue
        out.append((newest, n))
    return tuple(out)


def cached(key: tuple[Any, ...], fp: tuple[Any, ...], fn: Callable[[], T]) -> T:
    """``fn()`` once per ``key`` until the fingerprint changes."""
    with _lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] == fp:
            return hit[1]  # type: ignore[no-any-return]
    val = fn()
    with _lock:
        _cache[key] = (fp, val)
    return val


def clear() -> None:
    """Forget every cached answer (tests, ``?refresh=1``)."""
    with _lock:
        _cache.clear()


def run_probe(
    python: str, args: list[str], *, pythonpath: Path | None = None, timeout: float = 60
) -> dict[str, Any]:
    """Run ``probe.py`` with an interpreter and parse its JSON answer."""
    env = dict(os.environ)
    if pythonpath is not None:
        env["PYTHONPATH"] = os.pathsep.join(
            [str(pythonpath), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
        )
    try:
        cp = subprocess.run(
            [python, str(PROBE), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    try:
        res: dict[str, Any] = json.loads(cp.stdout)
        return res
    except ValueError:
        err = (cp.stderr or cp.stdout).strip().splitlines()
        return {"ok": False, "error": err[-1] if err else f"probe exited {cp.returncode}"}


# --------------------------------------------------------------------------- profiles


def profiles(cfg: Settings) -> dict[str, Any]:
    """Specs, rules and ``consumers_by_path`` from the profiles checkout's own code."""
    repo = cfg.profiles
    src = repo / PROFILES_SRC
    fp = fingerprint(
        repo / "library",
        repo / "packages/senseai-profiles/profiles",
        repo / "packages/senseai-profiles/priors",
        src / "senseai_profiles",
    )
    if not (src / "senseai_profiles").is_dir():
        return {"ok": False, "error": f"no senseai-profiles source under {src}"}
    return cached(
        ("profiles", str(repo)),
        fp,
        lambda: run_probe(sys.executable, ["profiles", str(repo)], pythonpath=src),
    )


# --------------------------------------------------------------------------- world


def world_params_file(cfg: Settings) -> Path | None:
    """``prior/params.py`` of a world checkout, else of an installed senseai-world."""
    cand = cfg.sibling("world") / "src/senseai_world/prior/params.py"
    if cand.is_file():
        return cand
    py = bench_python(cfg)
    if py:
        r = subprocess.run(
            [
                py,
                "-c",
                "import importlib.util as u; s=u.find_spec('senseai_world'); "
                "print(s.submodule_search_locations[0] if s else '')",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        loc = r.stdout.strip()
        if loc and (Path(loc) / "prior/params.py").is_file():
            return Path(loc) / "prior/params.py"
    return None


def world_prior(cfg: Settings, library_file: Path) -> dict[str, Any]:
    """``PriorParams.from_library(<clade>.yaml).provenance()``."""
    params = world_params_file(cfg)
    if params is None:
        return {
            "ok": False,
            "error": "senseai-world not found (no checkout beside profiles, "
            "SENSEAI_WORLD_REPO unset, not installed in the stack)",
        }
    res = cached(
        ("world", str(params), str(library_file)),
        fingerprint(params, library_file),
        lambda: run_probe(sys.executable, ["world", str(params), str(library_file)]),
    )
    return dict(res) | {"params_file": str(params)}


# --------------------------------------------------------------------------- bench


def bench_python(cfg: Settings) -> str | None:
    """The stack's Python: ``SENSEAI_BENCH_PYTHON``, the stack venv, or bench's shebang."""
    if cfg.bench_python:
        return cfg.bench_python
    venv = cfg.stack / ".venv/bin/python"
    if venv.exists():
        return str(venv)
    exe = shutil.which(shlex.split(cfg.bench_cmd)[0]) if cfg.bench_cmd else None
    if exe:
        try:
            first = Path(exe).read_text(errors="strict").splitlines()[0]
        except (OSError, UnicodeDecodeError, IndexError):
            return None
        if first.startswith("#!") and "python" in first:
            return first[2:].strip().split()[0]
    return None


def bench_command(cfg: Settings) -> list[str] | None:
    """``senseai-bench`` as a command prefix, or ``None`` when it is not on this machine."""
    parts = shlex.split(cfg.bench_cmd)
    if not parts:
        return None
    if Path(parts[0]).exists() or shutil.which(parts[0]):
        return parts
    venv = cfg.stack / ".venv/bin/senseai-bench"
    return [str(venv)] if venv.exists() else None


def bench(cfg: Settings) -> dict[str, Any]:
    """What this senseai-bench's ``replay-compare`` offers: flags (from ``--help``) and arms."""
    cmd = bench_command(cfg)
    if cmd is None:
        return {"ok": False, "error": f"senseai-bench not found ({cfg.bench_cmd})"}

    def ask() -> dict[str, Any]:
        try:
            cp = subprocess.run(
                [*cmd, "replay-compare", "--help"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        out: dict[str, Any] = {
            "ok": cp.returncode == 0,
            "help": cp.stdout,
            "sdk_profiles": {},
            "world_modes": {},
        }
        if cp.returncode != 0:
            out["error"] = (cp.stderr.strip().splitlines() or ["--help failed"])[-1]
        py = bench_python(cfg)
        if py:
            arms = run_probe(py, ["bench"])
            if arms.get("ok"):
                out |= {"sdk_profiles": arms["sdk_profiles"], "world_modes": arms["world_modes"]}
        return out

    return cached(("bench", tuple(cmd)), (int(time.time() // 300),), ask)


def bench_flags(help_text: str) -> dict[str, bool]:
    """Features Studio needs, detected from ``replay-compare --help``."""
    return {
        "synthetic": "--synthetic" in help_text,
        "profile_arms": "profile:" in help_text,
        "prior_library": "--prior-library" in help_text,
        "profiles_repo": "--profiles-repo" in help_text,
    }


# --------------------------------------------------------------------------- checkpoints


def checkpoint(cfg: Settings, path: Path) -> dict[str, Any]:
    """Metadata of a world checkpoint: a ``<ckpt>.json`` manifest beside it, else torch."""
    for m in (path.with_suffix(path.suffix + ".json"), path.with_suffix(".json")):
        if m.is_file():
            try:
                doc: dict[str, Any] = json.loads(m.read_text())
                return {"ok": True, "manifest": str(m)} | doc
            except ValueError as e:
                return {"ok": False, "error": f"{m}: {e}"}
    py = bench_python(cfg)
    if py is None:
        return {
            "ok": False,
            "error": "no manifest beside the checkpoint and no stack Python "
            "(SENSEAI_BENCH_PYTHON) to read it with",
        }
    return cached(
        ("ckpt", str(path)),
        fingerprint(path),
        lambda: run_probe(py, ["ckpt", str(path)], timeout=120),
    )


def checkpoints(cfg: Settings) -> list[Path]:
    """``SENSEAI_WORLD_CKPT`` and every ``*.ckpt`` in ``SENSEAI_ARTEFACTS``."""
    out: list[Path] = []
    if cfg.world_ckpt is not None:
        out.append(cfg.world_ckpt)
    if cfg.artefacts is not None and cfg.artefacts.is_dir():
        out += sorted(p for p in cfg.artefacts.rglob("*.ckpt") if p not in out)
    return out


# --------------------------------------------------------------------------- circuits


def circuits(cfg: Settings) -> dict[str, Any]:
    """``senseai-circuits knobs --json``: every knob with value, unit, kind, rule, species."""
    parts = shlex.split(cfg.circuits_cmd)
    exe = parts and (shutil.which(parts[0]) or (Path(parts[0]).exists() and parts[0]))
    if not exe:
        return {"ok": False, "installed": False, "error": "circuits: not installed"}

    def ask() -> dict[str, Any]:
        try:
            cp = subprocess.run(
                [*parts, "knobs", "--json"], capture_output=True, text=True, timeout=60, check=False
            )
            data = json.loads(cp.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError) as e:
            return {"ok": False, "installed": True, "error": f"{type(e).__name__}: {e}"}
        knobs = data.get("knobs", data) if isinstance(data, dict) else data
        return {"ok": True, "installed": True, "knobs": knobs if isinstance(knobs, list) else []}

    return cached(("circuits", cfg.circuits_cmd), (int(time.time() // 60),), ask)


# --------------------------------------------------------------------------- git


def git(repo: Path, *args: str) -> str | None:
    """``git -C repo args``' stdout, or ``None``."""
    if not (repo / ".git").exists():
        return None
    try:
        cp = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return cp.stdout.strip() if cp.returncode == 0 else None


def sha(repo: Path) -> str | None:
    """HEAD of a checkout."""
    return git(repo, "rev-parse", "HEAD")


def committed_at(repo: Path, path: Path) -> tuple[str, str] | None:
    """``(commit, ISO date)`` of the last commit touching ``path`` (None if never committed)."""
    try:
        relp = path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return None
    out = cached(
        ("log", str(repo), relp),
        fingerprint(path, repo / ".git" / "HEAD"),
        lambda: git(repo, "log", "-1", "--format=%H %cI", "--", relp),
    )
    if not out:
        return None
    h, _, d = out.partition(" ")
    return h, d
