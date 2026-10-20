# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""The Run tab: what can run for a clade+sense, and run jobs that stream live events.

A run is one ``senseai-bench replay-compare`` process writing the live events contract
(``--events``, JSON Lines, see ``senseai_bench.replay.events``) into the job folder; Studio
tails that file as Server-Sent Events, exactly as the viewer's Run page does. A *synthetic*
source uses ``--synthetic <seconds>`` (bench's SyntheticReplay streams through the real SDK);
a recording uses ``--sequence``. Studio never runs the pipeline itself.

Jobs live in ``STUDIO_DATA/jobs/<id>/`` (``job.json``, ``events.jsonl``, ``bench.log``,
``report/``). The bench process runs in its own session, so closing the browser leaves it
running; a Studio restart marks jobs whose process is gone as failed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import secrets
import signal
import subprocess
import threading
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from senseai_studio.facts import data, upstream
from senseai_studio.facts import library as lib
from senseai_studio.facts import profiles as prof
from senseai_studio.facts.pipeline import Ctx, check_records
from senseai_studio.settings import Settings
from senseai_studio.studio import Snapshot

ACTIVE = ("running", "cancelling")
SSE_POLL_S = 0.2
SSE_PING_S = 15.0
DEFAULT_SECONDS = 10.0
MAX_SECONDS = 600.0


class RunError(ValueError):
    """A run request that cannot start; the message says why."""


def now() -> str:
    """UTC timestamp, second resolution."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- options


def _bench_arm(b: dict[str, Any], profile: str, world: str) -> tuple[str | None, str]:
    """The bench arm name for (profile, world mode), or None and why not."""
    flags = upstream.bench_flags(b.get("help", ""))
    if flags["profile_arms"]:
        return f"profile:{profile}@{world}", ""
    for arm, p in (b.get("sdk_profiles") or {}).items():
        if p == profile and (b.get("world_modes") or {}).get(arm) == world:
            return arm, ""
    if not b.get("ok"):
        return None, str(b.get("error") or "senseai-bench not found")
    return None, (
        f"this senseai-bench has no arm for profile {profile!r} on the {world} world "
        "(needs replay-compare's generic profile:<name>@<world> arms)"
    )


def options(snap: Snapshot, clade: str, sense: str) -> dict[str, Any]:
    """Data sources and arms for a clade+sense, each with the reason when it cannot run."""
    c, s = snap.sense(clade, sense)
    m = snap.modality(s)
    b = upstream.bench(snap.cfg)
    flags = upstream.bench_flags(b.get("help", ""))
    prov: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    streams = list(m.get("streams") or [])
    if streams:
        ok = bool(b.get("ok")) and flags["synthetic"]
        sources.append(
            {
                "id": "synthetic",
                "dataset": "synthetic",
                "name": "Synthetic stream",
                "synthetic": True,
                "streams": streams,
                "labelled": False,
                "available": ok,
                "reason": ""
                if ok
                else (
                    str(b.get("error"))
                    if not b.get("ok")
                    else "this senseai-bench has no replay-compare --synthetic yet"
                ),
            }
        )
        prov.append(
            {
                "field": "sources/0/streams",
                "source_file": snap.modalities.label,
                "line_or_key": snap.modalities.line(s.modality, "streams"),
            }
        )
    for r in data.recordings(snap.cfg.data_root, list(m.get("datasets") or [])):
        ok = r["dataset"] == "dsec" and bool(b.get("ok"))
        reason = (
            ""
            if ok
            else (
                str(b.get("error"))
                if not b.get("ok")
                else f"senseai-bench cannot replay {r['dataset']} recordings yet"
            )
        )
        sources.append(r | {"synthetic": False, "available": ok, "reason": reason})
        prov.append(
            {
                "field": f"sources/{len(sources) - 1}",
                "source_file": r["path"],
                "line_or_key": "file",
            }
        )

    arms: list[dict[str, Any]] = []
    readers = snap.specs.profiles_reading(c, s.id)
    have_ckpt = bool(
        snap.cfg.world_ckpt
        and snap.cfg.world_ckpt.is_file()
        and snap.cfg.tokens_yaml
        and snap.cfg.tokens_yaml.is_file()
    )

    def arm(profile: str, world: str, role: str) -> None:
        bench_name, why = _bench_arm(b, profile, world)
        if world == "learned" and not have_ckpt:
            bench_name, why = (
                None,
                (
                    "no trained world checkpoint configured "
                    "(SENSEAI_WORLD_CKPT + SENSEAI_TOKENS_YAML): untrained"
                ),
            )
        spec = snap.specs.specs.get(profile, {})
        arms.append(
            {
                "id": f"{profile}@{world}",
                "profile": profile,
                "world": world,
                "role": role,
                "description": spec.get("description"),
                "bench_arm": bench_name,
                "available": bench_name is not None,
                "reason": why,
            }
        )
        prov.append(
            {
                "field": f"arms/{len(arms) - 1}",
                "source_file": prof.spec_label(snap.cfg, spec) if spec else "profiles",
                "line_or_key": "name",
            }
        )

    for p in readers:
        arm(p, "prior", "species")
    for p in snap.specs.controls():
        arm(p, "prior", "control")
    for p in readers:
        arm(p, "learned", "learned")

    ctx = Ctx(snap.cfg, c, s.id, readers, snap.specs.specs)
    pre = check_records({"paths": ["{stack}/bench/prereg/*.yaml"], "require": "hash"}, ctx)
    verdict = check_records(
        {"paths": ["{stack}/bench/runs/*/verdict.json"], "require": "verdict"}, ctx
    )
    prereg = []
    if pre.get("done"):
        rec = pre["record"]
        prereg.append(
            {
                "file": ctx.label(pre["source"]),
                "id": rec.get("id"),
                "hash": rec.get("hash"),
                "clips": rec.get("clips") or [],
                "frozen_at": pre.get("at"),
                "verdict": verdict["record"].get("verdict") if verdict.get("done") else None,
                "verdict_file": ctx.label(verdict["source"]) if verdict.get("done") else None,
            }
        )
    return {
        "clade": c.key,
        "sense": s.id,
        "modality": s.modality,
        "view": m.get("view"),
        "sources": sources,
        "arms": arms,
        "prereg": prereg,
        "bench": {"found": bool(b.get("ok")), "error": b.get("error"), "features": flags},
        "prior_library": snap.label(c.path),
        "provenance": prov,
    }


# --------------------------------------------------------------------------- jobs


class Jobs:
    """Run jobs under ``STUDIO_DATA/jobs``."""

    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self.root = cfg.data_dir / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._procs: dict[str, subprocess.Popen[bytes]] = {}
        self.recover()

    def dir(self, job_id: str) -> Path:
        """Folder of a job."""
        if not job_id.replace("-", "").isalnum():
            raise KeyError(job_id)
        return self.root / job_id

    def get(self, job_id: str) -> dict[str, Any]:
        """``job.json``; ``KeyError`` if unknown."""
        p = self.dir(job_id) / "job.json"
        if not p.is_file():
            raise KeyError(job_id)
        job: dict[str, Any] = json.loads(p.read_text())
        return job

    def _write(self, job: dict[str, Any]) -> None:
        with self._lock:
            p = self.dir(job["id"]) / "job.json"
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(job, indent=1))
            tmp.replace(p)

    def update(self, job_id: str, **fields: Any) -> dict[str, Any]:
        """Set fields of a job."""
        job = self.get(job_id) | fields
        self._write(job)
        return job

    def recent(
        self, limit: int = 30, clade: str | None = None, sense: str | None = None
    ) -> list[dict[str, Any]]:
        """Newest first."""
        out = []
        for d in sorted(self.root.iterdir(), reverse=True):
            with contextlib.suppress(KeyError, ValueError, OSError):
                j = self.get(d.name)
                if (clade is None or j["clade"] == clade) and (
                    sense is None or j["sense"] == sense
                ):
                    out.append(j)
            if len(out) >= limit:
                break
        return out

    def active(self) -> list[dict[str, Any]]:
        """Jobs still running."""
        return [j for j in self.recent(200) if j["status"] in ACTIVE]

    def recover(self) -> None:
        """After a restart: running jobs whose process is gone failed."""
        for j in self.active():
            if not _alive(j.get("pid")):
                self.update(
                    j["id"],
                    status="failed",
                    ended=now(),
                    error=j.get("error") or "the run stopped while Studio was down",
                )

    # -- start

    def start(self, snap: Snapshot, clade: str, sense: str, body: dict[str, Any]) -> dict[str, Any]:
        """Validate a run request against :func:`options` and start bench."""
        if self.active():
            raise RunError("a run is already going; wait for it or cancel it")
        opts = options(snap, clade, sense)
        src = next((x for x in opts["sources"] if x["id"] == body.get("source")), None)
        if src is None:
            raise RunError(f"unknown data source {body.get('source')!r}")
        if not src["available"]:
            raise RunError(f"{src['name']}: {src['reason']}")
        by_id = {a["id"]: a for a in opts["arms"]}
        picked = [by_id.get(a) for a in body.get("arms") or []]
        if not picked:
            raise RunError("pick at least one arm")
        if None in picked:
            raise RunError(f"unknown arm(s) {[a for a in body['arms'] if a not in by_id]}")
        off = [a for a in picked if a and not a["available"]]
        if off:
            raise RunError("; ".join(f"{a['id']}: {a['reason']}" for a in off))
        seconds = float(body.get("seconds") or DEFAULT_SECONDS)
        if not 0 < seconds <= MAX_SECONDS:
            raise RunError(f"seconds must be in (0, {MAX_SECONDS:.0f}]")
        c = snap.clade(clade)
        job_id = datetime.now(UTC).strftime("r%Y%m%d-%H%M%S-") + secrets.token_hex(2)
        d = self.dir(job_id)
        d.mkdir(parents=True)
        cmd = command(self.cfg, opts, src, [a for a in picked if a], seconds, c, d, job_id)
        job = {
            "id": job_id,
            "clade": c.key,
            "sense": sense,
            "status": "running",
            "source": src,
            "arms": [a for a in picked if a],
            "seconds": seconds,
            "synthetic": bool(src["synthetic"]),
            "preregistered": any(
                src.get("name") in (pr.get("clips") or []) for pr in opts["prereg"]
            ),
            "created": now(),
            "ended": None,
            "error": None,
            "pid": None,
            "cmd": cmd,
            "headline": None,
            "summaries": [],
        }
        self._write(job)
        log = (d / "bench.log").open("ab")
        env = dict(os.environ) | {"PYTHONUNBUFFERED": "1"}
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
                cwd=d,
            )
        except OSError as e:
            return self.update(job_id, status="failed", ended=now(), error=f"{e}")
        self._procs[job_id] = proc
        threading.Thread(target=self._reap, args=(job_id, proc), daemon=True).start()
        return self.update(job_id, pid=proc.pid)

    def _reap(self, job_id: str, proc: subprocess.Popen[bytes]) -> None:
        code = proc.wait()
        self._procs.pop(job_id, None)
        job = self.get(job_id)
        evs = read_events(self.dir(job_id) / "events.jsonl")
        end = next((e for e in reversed(evs) if e.get("type") == "run_end"), None)
        summaries = [
            {
                "arm": e.get("arm"),
                "sequence": e.get("sequence"),
                "error": e.get("error"),
                **(e.get("summary") or {}),
            }
            for e in evs
            if e.get("type") == "arm_end"
        ]
        if job["status"] == "cancelling":
            status, err = "cancelled", None
        elif end is not None and not end.get("error") and code == 0:
            status, err = "succeeded", None
        else:
            status = "failed"
            err = (
                (end or {}).get("error")
                or _last_line(self.dir(job_id) / "bench.log")
                or (f"senseai-bench exited {code} without a run_end event")
            )
        self.update(
            job_id,
            status=status,
            ended=now(),
            error=err,
            exit_code=code,
            headline=(end or {}).get("headline"),
            summaries=summaries,
            report_md=(end or {}).get("report_md"),
        )

    def cancel(self, job_id: str) -> dict[str, Any]:
        """Stop a running job (its whole process group)."""
        job = self.get(job_id)
        if job["status"] not in ACTIVE:
            return job
        job = self.update(job_id, status="cancelling")
        if _alive(job.get("pid")):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(int(job["pid"]), signal.SIGTERM)
        else:
            job = self.update(job_id, status="cancelled", ended=now())
        return job

    def wait(self, job_id: str, timeout: float = 60) -> dict[str, Any]:
        """Block until a job has finished (tests)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            j = self.get(job_id)
            if j["status"] not in ACTIVE and job_id not in self._procs:
                return j
            time.sleep(0.05)
        raise TimeoutError(job_id)


def command(
    cfg: Settings,
    opts: dict[str, Any],
    src: dict[str, Any],
    arms: list[dict[str, Any]],
    seconds: float,
    clade: lib.Clade,
    d: Path,
    job_id: str,
) -> list[str]:
    """The ``senseai-bench replay-compare`` command line for a run."""
    bench = upstream.bench_command(cfg) or [cfg.bench_cmd]
    flags = opts["bench"]["features"]
    cmd = [*bench, "replay-compare"]
    if src["synthetic"]:
        cmd += ["--synthetic", f"{seconds:g}", "--synthetic-streams", ",".join(src["streams"])]
    else:
        cmd += ["--sequence", src["path"], "--max-seconds", f"{seconds:g}"]
        if src.get("calibration"):
            cmd += ["--calibration", src["calibration"]]
    cmd += ["--arms", ",".join(a["bench_arm"] for a in arms)]
    cmd += [
        "--events",
        str(d / "events.jsonl"),
        "--out",
        str(d / "report"),
        "--runlog",
        str(d / "runlog"),
        "--run-id",
        job_id,
    ]
    if flags.get("prior_library"):
        cmd += ["--prior-library", str(clade.path)]
    if flags.get("profiles_repo"):
        cmd += ["--profiles-repo", str(cfg.profiles)]
    if any(a["world"] == "learned" for a in arms) and cfg.world_ckpt and cfg.tokens_yaml:
        cmd += ["--world-ckpt", str(cfg.world_ckpt), "--tokens-yaml", str(cfg.tokens_yaml)]
    return cmd


def _alive(pid: Any) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        stat = Path(f"/proc/{int(pid)}/stat").read_text()
    except OSError:
        return True
    return stat.split(") ")[-1][:1] != "Z"  # a zombie has exited


def _last_line(p: Path) -> str | None:
    try:
        lines = [x for x in p.read_text(errors="replace").splitlines() if x.strip()]
    except OSError:
        return None
    return lines[-1][-500:] if lines else None


def read_events(path: Path) -> list[dict[str, Any]]:
    """Every complete event line of an events file."""
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        with contextlib.suppress(ValueError):
            ev = json.loads(line)
            if isinstance(ev, dict):
                out.append(ev)
    return out


async def tail_events(path: Path, done: Callable[[], bool]) -> AsyncIterator[bytes]:
    """Server-Sent Events from an events.jsonl: replay from the start, then follow.

    Ported from ``senseai_viewer.live.tail_events`` (viewer@8106abf). Ends after the
    ``run_end`` line, or when the run is over and the file is drained.
    """
    pos = 0
    buf = b""
    n = 0
    last = time.monotonic()
    yield b"retry: 2000\n\n"
    while True:
        chunk = b""
        try:
            with path.open("rb") as f:
                f.seek(pos)
                chunk = f.read()
        except OSError:
            pass
        pos += len(chunk)
        buf += chunk
        *lines, buf = buf.split(b"\n")
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            n += 1
            yield b"id: %d\ndata: %s\n\n" % (n, line)
            last = time.monotonic()
            try:
                if json.loads(line).get("type") == "run_end":
                    return
            except ValueError:
                continue
        if not chunk and done():
            return
        if time.monotonic() - last > SSE_PING_S:
            yield b": ping\n\n"
            last = time.monotonic()
        await asyncio.sleep(SSE_POLL_S)
