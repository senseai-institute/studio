# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""How far a clade+sense is through the ten-step species pipeline.

The step list is data (``content/pipeline.yaml``, or the profiles checkout's
``docs/pipeline/steps.yaml``); this module only knows how to run each kind of ``check`` against
files. A step is done or not; the pipeline is *at* the first step that is not done. The clock
counts days since step 1; it is *partial* when step 1 has no date or a later step is done
while an earlier one is not.
"""

from __future__ import annotations

import glob
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from senseai_studio.facts import evidence, upstream
from senseai_studio.facts.content import front_matter
from senseai_studio.facts.library import Clade
from senseai_studio.prov import Prov, rel
from senseai_studio.settings import Settings


@dataclass
class Ctx:
    """What a check needs."""

    cfg: Settings
    clade: Clade
    sense: str
    species: list[str]  # profiles reading this clade+sense
    specs: dict[str, dict[str, Any]]
    prov: Prov = field(default_factory=Prov)

    def expand(self, pattern: str) -> list[str]:
        """Glob a pattern after filling the placeholders (once per species for {species})."""
        names = [*self.species, self.clade.key] if "{species}" in pattern else [""]
        out: list[str] = []
        for sp in names:
            pat = pattern.format(
                profiles=self.cfg.profiles,
                stack=self.cfg.stack,
                clade=self.clade.key,
                sense=self.sense,
                species=sp,
            )
            out += [p for p in sorted(glob.glob(pat)) if p not in out]
        return out

    def label(self, p: Path) -> str:
        """``<repo>/<path>`` for a file in one of the known checkouts."""
        for root, repo in ((self.cfg.profiles, "profiles"), (self.cfg.stack / "bench", "bench")):
            r = rel(p, root, repo)
            if r != str(p):
                return r
        return str(p)

    def names(self) -> set[str]:
        """Names a record may use for this clade (key, Latin name, common names, profiles)."""
        d = self.clade.data
        return {
            self.clade.key,
            str(d.get("clade", "")).lower(),
            *self.species,
            *[str(n).lower() for n in d.get("common_names") or []],
        }


def _repo_of(p: Path) -> Path | None:
    for d in [p.parent, *p.parents]:
        if (d / ".git").exists():
            return d
    return None


def file_date(p: Path) -> tuple[str, bool]:
    """(ISO date of the last commit touching ``p``, committed) or (mtime, False)."""
    repo = _repo_of(p.resolve())
    if repo is not None:
        c = upstream.committed_at(repo, p)
        if c:
            return c[1], True
    return datetime.fromtimestamp(p.stat().st_mtime, UTC).isoformat(timespec="seconds"), False


def _load_any(p: Path) -> Any:
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".json":
        return json.loads(text)
    if p.suffix == ".md":
        return front_matter(text)[0]
    return yaml.safe_load(text)


def _names_us(rec: dict[str, Any], ctx: Ctx) -> bool:
    keys = ctx.names()
    vals: list[str] = []
    for k in ("clade", "species", "profile", "niche"):
        v = rec.get(k)
        vals += [str(x).lower() for x in v] if isinstance(v, list) else [str(v).lower()] * bool(v)
    if not keys & set(vals):
        return False
    s = rec.get("sense") or rec.get("senses")
    if s is None:
        return True
    return ctx.sense in (s if isinstance(s, list) else [s])


Result = dict[str, Any]


def check_front_matter(step: dict[str, Any], ctx: Ctx) -> Result:
    """Step done when a species file header names the clade and has every field."""
    fields = [str(f) for f in step.get("fields") or []]
    for pat in step.get("paths") or []:
        for f in ctx.expand(pat):
            p = Path(f)
            try:
                meta = _load_any(p)
            except (OSError, ValueError, yaml.YAMLError):
                continue
            if not isinstance(meta, dict) or not (_names_us(meta, ctx) or p.stem in ctx.names()):
                continue
            have = {k: meta.get(k) for k in fields if meta.get(k)}
            at = str(meta.get("started") or meta.get("date") or file_date(p)[0])
            return {
                "done": len(have) == len(fields),
                "at": at,
                "source": p,
                "detail": "; ".join(f"{k}: {v}" for k, v in have.items())
                or f"{', '.join(fields)} not set",
            }
    return {"done": False, "detail": "no species file with a header for this clade yet"}


def check_library(_step: dict[str, Any], ctx: Ctx) -> Result:
    """Step done when the library holds a cited value for the sense."""
    qs = ctx.clade.quantities(ctx.sense)
    cites = {c for q in qs for c in (q.get("citations") or [])}
    at, _ = file_date(ctx.clade.path)
    return {
        "done": bool(qs),
        "at": at if qs else None,
        "source": ctx.clade.path,
        "detail": f"{len(qs)} cited value(s) from {len(cites)} source(s)"
        if qs
        else "no cited value for this sense in the library",
    }


def check_table(step: dict[str, Any], ctx: Ctx) -> Result:
    """Step done when every evidence-table row is verified."""
    pats = step.get("paths") or [None]
    files = [f for pat in pats if pat for f in ctx.expand(pat)]
    t = evidence.table(ctx.cfg.profiles, ctx.clade.key, ctx.sense, files[0] if files else None)
    if not t.present:
        return {"done": False, "detail": f"no evidence table ({t.label})"}
    ok, total = t.counts(tuple(str(s).lower() for s in step.get("verified") or ["verified"]))
    p = Path(files[0]) if files else None
    return {
        "done": total > 0 and ok == total,
        "at": file_date(p)[0] if p else None,
        "source": p,
        "detail": f"{ok} of {total} rows verified",
        "counts": {"verified": ok, "total": total},
    }


def check_rules(step: dict[str, Any], ctx: Ctx) -> Result:
    """Step done when every rulebook rule for the sense has an accepted status."""
    pats = [
        p.format(
            profiles=ctx.cfg.profiles,
            stack=ctx.cfg.stack,
            clade=ctx.clade.key,
            sense=ctx.sense,
            species="*",
        )
        for p in step.get("paths") or []
    ]
    rb = evidence.rulebook(ctx.cfg.profiles, pats, ctx.clade.key, ctx.sense)
    if not rb["present"]:
        return {"done": False, "detail": "no rulebook in this profiles checkout"}
    rules = rb["rules"]
    accepted = {str(s).lower() for s in step.get("accepted") or []}
    statuses: dict[str, int] = {}
    for r in rules:
        statuses[str(r["status"])] = statuses.get(str(r["status"]), 0) + 1
    done = bool(rules) and all(str(r["status"]).lower() in accepted for r in rules)
    detail = ", ".join(f"{n} {s}" for s, n in sorted(statuses.items())) or "no rule yet"
    return {"done": done, "detail": f"{len(rules)} rule(s): {detail}", "rules": rules}


def check_committed(step: dict[str, Any], ctx: Ctx) -> Result:
    """Step done when the species file is committed to git."""
    for pat in step.get("paths") or []:
        for f in ctx.expand(pat):
            p = Path(f)
            at, committed = file_date(p)
            name = p.name.split(".")[0]
            h = (ctx.specs.get(name) or {}).get("spec_hash") or hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            return {
                "done": committed,
                "at": at if committed else None,
                "source": p,
                "detail": f"{p.name} · hash {h[:12]} · "
                + (f"committed {at[:10]}" if committed else "not committed"),
            }
    return {"done": False, "detail": "no species file for this clade+sense"}


def check_records(step: dict[str, Any], ctx: Ctx) -> Result:
    """Step done when a record naming the clade has the required key."""
    need = str(step.get("require") or "")
    seen = 0
    for pat in step.get("paths") or []:
        for f in ctx.expand(pat):
            p = Path(f)
            try:
                rec = _load_any(p)
            except (OSError, ValueError, yaml.YAMLError):
                continue
            if not isinstance(rec, dict) or not (
                _names_us(rec, ctx) or p.parent.name in ctx.names()
            ):
                continue
            seen += 1
            if rec.get(need):
                bits = [
                    f"{k}: {rec[k]}"
                    for k in ("id", need, "clips", "frozen_at")
                    if k in rec and not isinstance(rec[k], (dict, list))
                ]
                at = rec.get("frozen_at") or rec.get("at") or rec.get("date") or file_date(p)[0]
                return {
                    "done": True,
                    "at": str(at),
                    "source": p,
                    "detail": "; ".join(bits),
                    "record": rec,
                }
    return {
        "done": False,
        "detail": f"{seen} record(s), none with {need}" if seen else "nothing recorded yet",
    }


CHECKS = {
    "front_matter": check_front_matter,
    "library": check_library,
    "table": check_table,
    "rules": check_rules,
    "committed": check_committed,
    "records": check_records,
}


def _days(at: str | None, now: datetime) -> int | None:
    if not at:
        return None
    try:
        t = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return max(0, (now - t).days)


def run(ctx: Ctx, steps_doc: Any, steps_label: str, now: datetime | None = None) -> dict[str, Any]:
    """Every step's state, the step the pipeline is at, and the clock."""
    now = now or datetime.now(UTC)
    raw = (steps_doc.data or {}).get("steps", []) if steps_doc else []
    steps: list[dict[str, Any]] = []
    for i, s in enumerate(raw):
        fn = CHECKS.get(str(s.get("check")))
        res: Result = (
            fn(s, ctx) if fn else {"done": False, "detail": f"unknown check {s.get('check')!r}"}
        )
        row = {
            "n": int(s.get("n", i + 1)),
            "id": s.get("id"),
            "name": s.get("name"),
            "done": bool(res.get("done")),
            "at": res.get("at"),
            "detail": res.get("detail", ""),
            "source_file": ctx.label(res["source"]) if res.get("source") else None,
        }
        for key in ("counts", "rules"):
            if key in res:
                row[key] = res[key]
        k = len(steps)
        ctx.prov.add(f"steps/{k}/name", steps_label, steps_doc.line("steps", i))
        if row["source_file"]:
            ctx.prov.add(f"steps/{k}/done", row["source_file"], "file")
        steps.append(row)
    total = len(steps)
    at = next((s["n"] for s in steps if not s["done"]), total)
    first_not = next((i for i, s in enumerate(steps) if not s["done"]), total)
    out_of_order = any(s["done"] for s in steps[first_not + 1 :])
    start = steps[0]["at"] if steps and steps[0]["done"] else None
    days = _days(start, now)
    return {
        "steps": steps,
        "at": at,
        "total": total,
        "complete": total > 0 and all(s["done"] for s in steps),
        "clock": {
            "since": start,
            "days": days,
            "partial": days is None or out_of_order,
            "out_of_order": out_of_order,
        },
    }
