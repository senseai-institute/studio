# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Stand-in for ``senseai-bench replay-compare``: writes the live events contract with delays.

Speaks the flags Studio uses, including ``--synthetic`` and ``profile:<name>@<world>`` arms, and
the optional ``frame`` events and ``sample.ring`` field Studio draws live.

FAKE_BENCH_DELAY  seconds between events (default 0.01)
FAKE_BENCH_MODE   ok (default) | crash (exit 3 mid-run, no run_end) | hang (never ends)
FAKE_BENCH_LEGACY 1: no --synthetic and no profile arms (an older bench)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

LEGACY = os.environ.get("FAKE_BENCH_LEGACY") == "1"


def png(path: Path, w: int = 32, h: int = 24, shade: int = 0) -> None:
    """A tiny valid grey PNG (no Pillow needed)."""
    import struct
    import zlib

    raw = b"".join(
        b"\x00" + bytes([(x * 7 + y * 3 + shade) % 256 for x in range(w)]) for y in range(h)
    )

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    ap = argparse.ArgumentParser(prog="senseai-bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("replay-compare")
    p.add_argument("--sequence", action="append", default=[])
    if not LEGACY:
        p.add_argument("--synthetic", type=float, default=None, help="seconds of synthetic data")
        p.add_argument("--synthetic-streams", default="EVENT,FRAME")
    arms_help = "comma list; profile:<name>@<world> for any profile" if not LEGACY else "comma list"
    p.add_argument("--arms", required=True, help=arms_help)
    p.add_argument("--max-seconds", type=float, default=None)
    p.add_argument("--prior-library", default=None)
    p.add_argument("--profiles-repo", default=None)
    p.add_argument("--calibration", default=None)
    p.add_argument("--world-ckpt", default=None)
    p.add_argument("--tokens-yaml", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--events", required=True)
    p.add_argument("--runlog", default=None)
    p.add_argument("--run-id", default="fake")
    a = ap.parse_args()
    delay = float(os.environ.get("FAKE_BENCH_DELAY", "0.01"))
    mode = os.environ.get("FAKE_BENCH_MODE", "ok")
    arms = a.arms.split(",")
    synthetic = getattr(a, "synthetic", None)
    seqs = ["synthetic"] if synthetic else [Path(s).name for s in a.sequence]
    secs = min(synthetic or a.max_seconds or 4.0, 4.0)
    events = Path(a.events)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ev = events.open("a", encoding="utf-8")

    def emit(type_: str, **kw: object) -> None:
        ev.write(
            json.dumps({"type": type_, "t_wall": time.time(), "run_id": a.run_id, **kw}) + "\n"
        )
        ev.flush()
        time.sleep(delay)

    emit(
        "run_start",
        sequences=[
            {"name": s, "duration_s": secs, "labels": False, "synthetic": bool(synthetic)}
            for s in seqs
        ],
        arms=[{"name": n, "kind": "reflex", "label": n} for n in arms],
        config={"fake": True, "prior_library": a.prior_library},
    )
    print(f"fake bench: {seqs} arms {arms}", flush=True)
    for s in seqs:
        for i, arm in enumerate(arms):
            emit("arm_start", sequence=s, arm=arm)
            steps = 8
            for k in range(steps + 1):
                t = secs * k / steps
                if i == 0:
                    rel = f"frames/{s}_{k:03d}.png"
                    png(events.parent / rel, shade=k * 20)
                    emit("frame", sequence=s, t_rel_s=round(t, 2), kind="rgb", path=rel)
                active = t > secs * (0.4 + 0.1 * i)
                ring = [
                    round(
                        0.2 + (1.5 if active and abs(b - 6) < 2 else 0) + 0.1 * math.sin(b + k), 3
                    )
                    for b in range(72)
                ]
                emit(
                    "sample",
                    sequence=s,
                    arm=arm,
                    t_rel_s=round(t, 2),
                    active=active,
                    value=round(0.5 + (4 if active else 0), 2),
                    ring=ring,
                )
                emit(
                    "progress",
                    sequence=s,
                    arm=arm,
                    t_rel_s=round(t, 2),
                    frac=k / steps,
                    fires=int(active),
                    latency_p99_ms=9.5 + 10 * i,
                )
                if mode == "crash" and k == 3:
                    print("fake bench: crashing", flush=True)
                    return 3
                if mode == "hang" and k == 3:
                    time.sleep(3600)
            emit(
                "fire",
                sequence=s,
                arm=arm,
                t_rel_s=round(secs * (0.4 + 0.1 * i), 2),
                bearing_deg=30.0,
                explain=f"{arm} slowed",
            )
            emit(
                "arm_end",
                sequence=s,
                arm=arm,
                error=None,
                summary={
                    "hit_rate": None,
                    "median_delay_s": None,
                    "unattributed_fires_per_h": 0.0,
                    "latency_p50_ms": 9.0 + 10 * i,
                    "latency_p99_ms": 9.5 + 10 * i,
                },
            )
    (out / "replay_report.md").write_text("# Replay report (fake)\n\nNo labels: pipeline check.\n")
    emit(
        "run_end",
        headline="pipeline check (fake producer)",
        report_md=str(out / "replay_report.md"),
        report_json=None,
        runlog=a.runlog,
        error=None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
