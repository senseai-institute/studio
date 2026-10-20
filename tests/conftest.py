# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import shutil
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from senseai_studio.app import create_app
from senseai_studio.facts import upstream
from senseai_studio.settings import REPO_DIR, Settings

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_BENCH = Path(__file__).parent / "fake_bench.py"


@pytest.fixture
def stack(tmp_path: Path) -> Path:
    """A stack folder: a fixture profiles checkout (no senseai-profiles source) and bench."""
    root = tmp_path / "stack"
    shutil.copytree(FIXTURES / "profiles", root / "profiles")
    shutil.copytree(FIXTURES / "bench", root / "bench")
    return root


@pytest.fixture
def cfg(stack: Path, tmp_path: Path) -> Iterator[Settings]:
    upstream.clear()
    content = tmp_path / "content"
    shutil.copytree(REPO_DIR / "content", content)
    yield Settings(
        profiles_repo=stack / "profiles",
        stack_dir=stack,
        data_root=tmp_path / "data_root",
        bench_cmd=f"{sys.executable} {FAKE_BENCH}",
        circuits_cmd="senseai-circuits-not-installed",
        content=content,
        data_dir=tmp_path / "studio_data",
    )
    upstream.clear()


@pytest.fixture
def client(cfg: Settings) -> TestClient:
    return TestClient(create_app(cfg))


def with_(cfg: Settings, **kw: object) -> Settings:
    return replace(cfg, **kw)  # type: ignore[arg-type]
