# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Environment-driven settings. Every variable is documented in ``.env.example``.

The names match the viewer runner's (``SENSEAI_PROFILES_REPO``, ``SENSEAI_DATA_ROOT``,
``SENSEAI_BENCH_CMD``, ``SENSEAI_BENCH_PYTHON``, ``SENSEAI_WORLD_CKPT``), so one env file
serves the viewer, the research service and Studio.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parents[1]  # a source checkout: <repo>/src/senseai_studio


def _path(name: str) -> Path | None:
    v = os.environ.get(name)
    return Path(v).expanduser() if v else None


def default_content() -> Path:
    """``content/`` of this checkout, else ``./content``."""
    here = REPO_DIR / "content"
    return here if here.is_dir() else Path("content")


@dataclass(frozen=True)
class Settings:
    """Server settings."""

    profiles_repo: Path | None = None
    stack_dir: Path | None = None
    data_root: Path | None = None
    bench_cmd: str = "senseai-bench"
    bench_python: str | None = None
    world_ckpt: Path | None = None
    tokens_yaml: Path | None = None
    world_repo: Path | None = None
    artefacts: Path | None = None
    circuits_cmd: str = "senseai-circuits"
    research_url: str | None = None
    content: Path = Path("content")
    data_dir: Path = Path("data")
    password: str | None = None
    port: int = 8200

    @property
    def stack(self) -> Path:
        """Folder holding the SenseAI checkouts side by side (``SENSEAI_STACK_DIR``)."""
        return self.stack_dir or Path.home() / "senseai"

    @property
    def profiles(self) -> Path:
        """The profiles checkout: ``SENSEAI_PROFILES_REPO`` or ``<stack>/profiles``."""
        return self.profiles_repo or self.stack / "profiles"

    def sibling(self, name: str) -> Path:
        """Another checkout beside profiles in the stack folder (bench, world, circuits …)."""
        if name == "world" and self.world_repo:
            return self.world_repo
        return self.stack / name

    @classmethod
    def from_env(cls) -> Settings:
        """Read settings from the environment."""
        return cls(
            profiles_repo=_path("SENSEAI_PROFILES_REPO"),
            stack_dir=_path("SENSEAI_STACK_DIR"),
            data_root=_path("SENSEAI_DATA_ROOT"),
            bench_cmd=os.environ.get("SENSEAI_BENCH_CMD") or "senseai-bench",
            bench_python=os.environ.get("SENSEAI_BENCH_PYTHON") or None,
            world_ckpt=_path("SENSEAI_WORLD_CKPT"),
            tokens_yaml=_path("SENSEAI_TOKENS_YAML"),
            world_repo=_path("SENSEAI_WORLD_REPO"),
            artefacts=_path("SENSEAI_ARTEFACTS"),
            circuits_cmd=os.environ.get("SENSEAI_CIRCUITS_CMD") or "senseai-circuits",
            research_url=(os.environ.get("RESEARCH_URL") or "").rstrip("/") or None,
            content=_path("STUDIO_CONTENT") or default_content(),
            data_dir=_path("STUDIO_DATA") or Path("data"),
            password=os.environ.get("VIEWER_PASSWORD") or None,
            port=int(os.environ.get("STUDIO_PORT") or os.environ.get("PORT") or "8200"),
        )
