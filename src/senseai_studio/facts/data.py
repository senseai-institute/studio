# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Recordings under ``SENSEAI_DATA_ROOT`` that a dataset adapter can replay.

``dsec``: a sequence folder with ``events/left/events.h5`` and ``images/left`` (the layout
``senseai_ingest.testing.make_dsec_fixture`` writes and the viewer's Prepare step arranges).
``wav``: ``.wav`` files. Studio only lists files; it never opens them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

DSEC_EVENTS = Path("events/left/events.h5")
DSEC_IMAGES = Path("images/left")
DSEC_LABELS = Path("object_detections/left/tracks.npy")
DSEC_CALIBRATION = Path("calibration/cam_to_cam.yaml")
MAX_DEPTH = 3


def _dsec(root: Path) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    def walk(d: Path, depth: int) -> None:
        if (d / DSEC_EVENTS).is_file() and (d / DSEC_IMAGES).is_dir():
            out.setdefault(
                d.name,
                {
                    "id": f"dsec:{d.name}",
                    "dataset": "dsec",
                    "name": d.name,
                    "path": str(d),
                    "labelled": (d / DSEC_LABELS).is_file(),
                    "calibration": str(d / DSEC_CALIBRATION)
                    if (d / DSEC_CALIBRATION).is_file()
                    else None,
                },
            )
            return
        if depth >= MAX_DEPTH:
            return
        try:
            kids = sorted(p for p in d.iterdir() if p.is_dir() and not p.name.startswith("."))
        except OSError:
            return
        for k in kids:
            walk(k, depth + 1)

    walk(root, 0)
    return [out[k] for k in sorted(out)]


def _wav(root: Path) -> list[dict[str, Any]]:
    out = []
    for p in sorted(root.rglob("*.wav")):
        if len(p.relative_to(root).parts) > MAX_DEPTH + 1:
            continue
        labels = p.with_suffix(".labels.json")
        out.append(
            {
                "id": f"wav:{p.relative_to(root).as_posix()}",
                "dataset": "wav",
                "name": p.relative_to(root).as_posix(),
                "path": str(p),
                "labelled": labels.is_file(),
                "calibration": None,
            }
        )
    return out


ADAPTERS = {"dsec": _dsec, "wav": _wav}


def recordings(root: Path | None, datasets: list[str]) -> list[dict[str, Any]]:
    """Recordings of the given datasets under the data root (empty without a root)."""
    if root is None or not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for ds in datasets:
        fn = ADAPTERS.get(ds)
        if fn is not None:
            out += fn(root)
    return out
