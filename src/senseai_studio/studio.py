# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""What each Studio screen shows, assembled from the facts with provenance for every item.

One :class:`Snapshot` per request reads the library, the profile specs (cached by the probe)
and Studio's content. Every public function returns a plain dict that ends up as an API
response, with ``provenance`` listing where each item came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from senseai_studio.facts import content, data, evidence, pipeline, upstream
from senseai_studio.facts import library as lib
from senseai_studio.facts import profiles as prof
from senseai_studio.facts.citations import Citation, lookup
from senseai_studio.facts.citations import parse as parse_citations
from senseai_studio.prov import Located, Prov, rel
from senseai_studio.settings import Settings


class NotFound(LookupError):
    """No such clade or sense in the library."""


@dataclass
class Snapshot:
    """The facts one request works from."""

    cfg: Settings
    clades: dict[str, lib.Clade]
    specs: prof.Specs
    modalities: Located
    steps: Located
    _citations: list[Citation] | None = field(default=None, repr=False)

    @classmethod
    def take(cls, cfg: Settings) -> Snapshot:
        """Read everything a screen may need."""
        clades = lib.load(cfg.profiles) if (cfg.profiles / "library").is_dir() else {}
        return cls(
            cfg,
            clades,
            prof.load(cfg) if clades else prof.Specs("none", {}, {}, []),
            content.modalities(cfg.content),
            content.pipeline_steps(cfg.content, cfg.profiles),
        )

    @property
    def citations(self) -> list[Citation]:
        """Rows of CITATIONS.md (read once per snapshot)."""
        if self._citations is None:
            p = self.cfg.profiles / "library" / "CITATIONS.md"
            self._citations = parse_citations(p) if p.is_file() else []
        return self._citations

    def clade(self, key: str) -> lib.Clade:
        """A clade by file stem; :class:`NotFound` otherwise."""
        c = self.clades.get(key.lower())
        if c is None:
            raise NotFound(f"no library entry {key!r}; have {sorted(self.clades)}")
        return c

    def sense(self, key: str, sense: str) -> tuple[lib.Clade, lib.Sense]:
        """A clade and one of its senses; :class:`NotFound` otherwise."""
        c = self.clade(key)
        s = c.senses.get(sense)
        if s is None:
            raise NotFound(f"{key} has no sense {sense!r}; it has {sorted(c.senses)}")
        return c, s

    def modality(self, s: lib.Sense) -> dict[str, Any]:
        """The modalities.yaml row for a sense (empty if the modality has no stream)."""
        m = (self.modalities.data or {}).get(s.modality)
        return m if isinstance(m, dict) else {}

    def label(self, path: Path | str | None) -> str | None:
        """``profiles/<path>`` for a file in the profiles checkout."""
        return rel(Path(path), self.cfg.profiles, "profiles") if path else None


# --------------------------------------------------------------------------- shared bits


def _pipeline(snap: Snapshot, c: lib.Clade, sense: str) -> dict[str, Any]:
    ctx = pipeline.Ctx(snap.cfg, c, sense, snap.specs.profiles_reading(c, sense), snap.specs.specs)
    res = pipeline.run(ctx, snap.steps, snap.steps.label)
    res["provenance"] = ctx.prov.out()
    return res


def sense_state(snap: Snapshot, c: lib.Clade, sense: str) -> str:
    """``modelled`` (a profile reads it), ``described`` (cited values only) or ``empty``."""
    if snap.specs.readers(c, sense):
        return "modelled"
    return "described" if lib.describes(c, sense) else "empty"


def data_state(snap: Snapshot, s: lib.Sense) -> dict[str, Any]:
    """Whether real recordings exist for the sense's modality, or only synthetic streams."""
    m = snap.modality(s)
    if not m.get("streams"):
        return {
            "state": "none",
            "recordings": 0,
            "reason": f"no data stream defined for modality {s.modality!r}",
        }
    recs = data.recordings(snap.cfg.data_root, list(m.get("datasets") or []))
    return {
        "state": "available" if recs else "synthetic",
        "recordings": len(recs),
        "datasets": list(m.get("datasets") or []),
        "streams": list(m["streams"]),
    }


def _cite(snap: Snapshot, cid: str, fld: str, p: Prov) -> dict[str, Any]:
    row = lookup(snap.citations, str(cid))
    out: dict[str, Any] = {"id": str(cid), "found": row is not None}
    if row is None:
        out["link"] = (
            cid
            if str(cid).startswith("http")
            else (f"https://doi.org/{cid}" if str(cid).startswith("10.") else None)
        )
        return out
    out |= {
        "reference": row.reference,
        "authors": row.authors,
        "year": row.year,
        "title": row.title,
        "link": row.link,
        "doi": row.doi,
        "checked": row.checked,
        "used_for": row.used_for,
    }
    p.add(fld, "profiles/library/CITATIONS.md", row.line)
    return out


# --------------------------------------------------------------------------- species


def species(snap: Snapshot) -> dict[str, Any]:
    """Home: one card per clade, a chip per sense."""
    p = Prov()
    cards = []
    for ci, c in enumerate(snap.clades.values()):
        d = c.data
        lab = c.doc.label
        senses = []
        for si, s in enumerate(c.senses.values()):
            pl = _pipeline(snap, c, s.id)
            ds = data_state(snap, s)
            senses.append(
                {
                    "id": s.id,
                    "modality": s.modality,
                    "state": sense_state(snap, c, s.id),
                    "profiles": snap.specs.profiles_reading(c, s.id),
                    "data": ds["state"],
                    "recordings": ds["recordings"],
                    "step": pl["at"],
                    "steps": pl["total"],
                    "complete": pl["complete"],
                }
            )
            p.add(f"cards/{ci}/senses/{si}/id", lab, c.doc.line("senses", s.index, "id"))
            p.add(f"cards/{ci}/senses/{si}/state", lab, c.doc.line("senses", s.index))
            p.add(
                f"cards/{ci}/senses/{si}/data",
                snap.modalities.label,
                snap.modalities.line(s.modality),
            )
            p.add(f"cards/{ci}/senses/{si}/step", snap.steps.label, "steps")
        best = max(senses, key=lambda x: (x["state"] == "modelled", -x["step"]), default=None)
        cards.append(
            {
                "clade": c.key,
                "latin": d.get("clade"),
                "rank": d.get("rank"),
                "names": list(d.get("common_names") or []),
                "representative": [
                    {"name": r.get("name"), "common_name": r.get("common_name")}
                    for r in d.get("representative_species") or []
                ],
                "niche": d.get("niche"),
                "review_status": d.get("review_status"),
                "version": d.get("version"),
                "senses": senses,
                "data": "available"
                if any(x["data"] == "available" for x in senses)
                else ("synthetic" if any(x["data"] == "synthetic" for x in senses) else "none"),
                "step": best["step"] if best else None,
                "steps": best["steps"] if best else None,
            }
        )
        for k, key in (
            ("names", "common_names"),
            ("latin", "clade"),
            ("representative", "representative_species"),
            ("niche", "niche"),
            ("review_status", "review_status"),
        ):
            if key in d:
                p.add(f"cards/{ci}/{k}", lab, c.doc.line(key))
    return {"cards": cards, "engine": snap.specs.engine, "provenance": p.out()}


# --------------------------------------------------------------------------- sources


def sources(snap: Snapshot, clade: str, sense: str) -> dict[str, Any]:
    """Sources: every cited value of the sense with its papers and verification status."""
    c, s = snap.sense(clade, sense)
    p = Prov()
    lab = c.doc.label
    table = evidence.table(snap.cfg.profiles, c.key, s.id)
    quantities = []
    for i, q in enumerate(c.quantities(s.id)):
        f = f"quantities/{i}"
        row: dict[str, Any] = {"path": q.path, "slot": q.slot, "description": q.description}
        for k in lib.QUANTITY_KEYS[:-1]:
            row[k] = q.get(k)
            if q.get(k) is not None:
                p.add(f"{f}/{k}", lab, c.doc.line(*q.key, k))
        row["citations"] = [
            _cite(snap, cid, f"{f}/citations/{j}", p)
            for j, cid in enumerate(q.get("citations") or [])
        ]
        p.add(f"{f}/path", lab, c.doc.line(*q.key))
        trows = table.for_path(q.path)
        if trows:
            t = trows[0]
            row["verification"] = {
                "tabled": True,
                "status": t["_status"] or "unverified",
                "quote": t["_quote"],
            }
            p.add(f"{f}/verification", table.label, t["_line"])
        else:
            row["verification"] = {"tabled": False, "status": "not tabled", "quote": None}
        row["consumers"] = [x for x in snap.specs.consumers.get(q.path, [])]
        quantities.append(row)
    oq = []
    for i, (text, key) in enumerate(c.open_questions(s.id)):
        oq.append(
            {
                "text": text,
                "scope": "sense"
                if key[0] == "senses"
                else ("behaviour" if key[0] == "behaviours" else "clade"),
            }
        )
        p.add(f"open_questions/{i}", lab, c.doc.line(*key))
    reqs = evidence.requests(snap.cfg.profiles, c.key, s.id, snap.specs.profiles_reading(c, s.id))
    for i, r in enumerate(reqs):
        p.add(f"requests/{i}", r.pop("source_file"), r.pop("line"))
    sense_cites = [
        _cite(snap, cid, f"sense/citations/{j}", p)
        for j, cid in enumerate(s.record.get("citations") or [])
    ]
    for k in ("organ", "signal", "modality", "notes"):
        if s.record.get(k):
            p.add(f"sense/{k}", lab, c.doc.line("senses", s.index, k))
    ok, total = table.counts()
    return {
        "clade": c.key,
        "sense": s.id,
        "sense_info": {k: s.record.get(k) for k in ("organ", "signal", "modality", "notes")}
        | {"citations": sense_cites},
        "review_status": c.data.get("review_status"),
        "quantities": quantities,
        "table": {"present": table.present, "file": table.label, "verified": ok, "total": total},
        "open_questions": oq,
        "requests": reqs,
        "provenance": p.out(),
    }


# --------------------------------------------------------------------------- model


def _knob_matches(k: dict[str, Any], names: set[str], sense: str) -> bool:
    who = {str(k.get(x, "")).lower() for x in ("species", "clade", "profile")} - {""}
    s = k.get("sense")
    return bool(who & names) and (s is None or s == sense)


def model(snap: Snapshot, clade: str, sense: str) -> dict[str, Any]:
    """Model: circuits, profile rules, world prior, learned networks, reflex."""
    c, s = snap.sense(clade, sense)
    p = Prov()
    readers = snap.specs.profiles_reading(c, s.id)
    names = {c.key, *readers, *[str(n).lower() for n in c.data.get("common_names") or []]}
    prefix = f"{c.key}.senses.{s.id}"

    # circuits
    circ = upstream.circuits(snap.cfg)
    knobs = [
        k for k in circ.get("knobs", []) if isinstance(k, dict) and _knob_matches(k, names, s.id)
    ]
    for i, k in enumerate(knobs):
        p.add(
            f"circuits/knobs/{i}",
            f"cli:{snap.cfg.circuits_cmd} knobs --json",
            str(k.get("knob") or k.get("name") or i),
        )

    # profile rules
    profiles_out = []
    for pi, name in enumerate(readers):
        spec = snap.specs.specs[name]
        label = prof.spec_label(snap.cfg, spec)
        fields = []
        for fi, fl in enumerate(spec["fields"]):
            reads = list((fl.get("library_paths") or {}).values())
            fields.append(
                fl
                | {
                    "reads_this_sense": any(
                        r.startswith(prefix)
                        or r in {x["path"] for x in snap.specs.readers(c, s.id)}
                        for r in reads
                    )
                }
            )
            p.add(f"profiles/{pi}/fields/{fi}", label, prof.spec_line(snap.cfg, spec, fl["where"]))
        profiles_out.append(
            {
                "name": name,
                "description": spec.get("description"),
                "version": spec.get("version"),
                "spec_hash": spec.get("spec_hash"),
                "source_file": label,
                "bundles": spec.get("bundles"),
                "control": name in snap.specs.controls(),
                "fields": fields,
            }
        )
    rb = evidence.rulebook(
        snap.cfg.profiles, [str(snap.cfg.profiles / "rulebook" / "*.yaml")], c.key, s.id
    )
    for i, r in enumerate(rb["rules"]):
        p.add(f"rulebook/rules/{i}", r["source_file"], r["line"])

    # world prior
    wp = upstream.world_prior(snap.cfg, c.path)
    params = []
    for name, v in (wp.get("params") or {}).items():
        src = str(v.get("source", ""))
        params.append(
            {
                "name": name,
                "value": v.get("value"),
                "kind": v.get("kind"),
                "source": src,
                "reads_this_sense": src.lower().startswith(prefix.lower())
                or f"{c.data.get('clade', '')}.senses.{s.id}".lower() in src.lower(),
                "reads_this_clade": src.lower().startswith(c.key),
            }
        )
    for i, prm in enumerate(params):
        p.add(
            f"world_prior/params/{i}",
            "world/src/senseai_world/prior/params.py",
            f"PriorParams.{prm['name']}",
        )
    p.add("world_prior/library", lab := c.doc.label, 1)

    # learned networks
    learned = []
    for i, ck in enumerate(upstream.checkpoints(snap.cfg)):
        meta: dict[str, Any] = (
            upstream.checkpoint(snap.cfg, ck)
            if ck.is_file()
            else {"ok": False, "error": "file not found"}
        )
        counts = meta.get("param_counts") or {}
        prov_ = meta.get("provenance") or {}
        learned.append(
            {
                "path": str(ck),
                "ok": bool(meta.get("ok")),
                "error": meta.get("error"),
                "model_id": meta.get("model_id"),
                "step": meta.get("step"),
                "param_counts": counts,
                "params_total": sum(v for v in counts.values() if isinstance(v, int)) or None,
                "tokenizer": meta.get("tokens") or prov_.get("tokens") or prov_.get("tokenizer"),
                "training_data": prov_.get("data")
                or prov_.get("training_data")
                or prov_.get("tokens_files"),
            }
        )
        p.add(f"learned/{i}", str(ck), meta.get("manifest") or "torch checkpoint")

    # reflex
    reflex = []
    for name in readers:
        spec = snap.specs.specs[name]
        rf = [fl for fl in spec["fields"] if fl["section"] == "reflex"]
        if rf:
            reflex.append(
                {"profile": name, "fields": rf, "source_file": prof.spec_label(snap.cfg, spec)}
            )
    return {
        "clade": c.key,
        "sense": s.id,
        "engine": snap.specs.engine,
        "engine_error": snap.specs.error,
        "circuits": {
            "installed": bool(circ.get("installed")),
            "ok": bool(circ.get("ok")),
            "error": circ.get("error"),
            "knobs": knobs,
        },
        "profiles": profiles_out,
        "controls": snap.specs.controls(),
        "rulebook": {"present": rb["present"], "rules": rb["rules"]},
        "world_prior": {
            "ok": bool(wp.get("ok")),
            "error": wp.get("error"),
            "library": lab,
            "params": params,
        },
        "learned": learned,
        "reflex": reflex,
        "provenance": p.out(),
    }


# --------------------------------------------------------------------------- pipeline


def pipeline_view(snap: Snapshot, clade: str, sense: str) -> dict[str, Any]:
    """Pipeline: the steps, the step it is at, the clock."""
    c, s = snap.sense(clade, sense)
    res = _pipeline(snap, c, s.id)
    return {
        "clade": c.key,
        "sense": s.id,
        "steps_file": snap.steps.label,
        "species": snap.specs.profiles_reading(c, s.id),
    } | res


# --------------------------------------------------------------------------- use cases


def use_cases(snap: Snapshot, clade: str, sense: str) -> dict[str, Any]:
    """Use cases: founder-written Markdown for this clade+sense, rendered."""
    c, s = snap.sense(clade, sense)
    p = Prov()
    readers = snap.specs.profiles_reading(c, s.id)
    niche = str(c.data.get("niche") or c.key)
    pl = _pipeline(snap, c, s.id)
    items = []
    for i, u in enumerate(
        content.matching(content.use_cases(snap.cfg.content), c.key, s.id, [niche, *readers])
    ):
        items.append(
            {
                "file": u.label,
                "niche": u.niche,
                "status": u.meta.get("status"),
                "species": u.meta.get("species") or [],
                "evidence": u.meta.get("evidence") or [],
                "template": u.is_template,
                "html": content.render(u.body),
            }
        )
        p.add(f"items/{i}/html", u.label, u.body_line)
        p.add(f"items/{i}/status", u.label, 1)
    return {
        "clade": c.key,
        "sense": s.id,
        "items": items,
        "step": pl["at"],
        "steps": pl["total"],
        "template_file": f"studio/content/use_cases/{niche}.{s.id}.md",
        "provenance": [
            *p.out(),
            {"field": "step", "source_file": snap.steps.label, "line_or_key": "steps"},
        ],
    }


# --------------------------------------------------------------------------- health / check


REPOS = ("profiles", "bench", "world", "circuits", "sdk", "ingest", "research")


def health(snap: Snapshot) -> dict[str, Any]:
    """Which repos and tools Studio found, at which SHAs."""
    cfg = snap.cfg
    repos = {}
    for r in REPOS:
        path = cfg.profiles if r == "profiles" else cfg.sibling(r)
        repos[r] = {"path": str(path), "found": path.is_dir(), "sha": upstream.sha(path)}
    b = upstream.bench(cfg)
    return {
        "ok": bool(snap.clades),
        "clades": len(snap.clades),
        "repos": repos,
        "engine": snap.specs.engine,
        "engine_error": snap.specs.error,
        "spec_issues": snap.specs.issues,
        "circuits": upstream.circuits(cfg).get("installed", False),
        "research": {"configured": cfg.research_url is not None, "url": cfg.research_url},
        "data_root": {
            "path": str(cfg.data_root) if cfg.data_root else None,
            "exists": bool(cfg.data_root and cfg.data_root.is_dir()),
        },
        "bench": {
            "found": b.get("ok", False),
            "error": b.get("error"),
            "features": upstream.bench_flags(b.get("help", "")),
        },
        "world_ckpt": str(cfg.world_ckpt) if cfg.world_ckpt else None,
        "content": str(cfg.content),
        "provenance": [
            {"field": f"repos/{r}/sha", "source_file": f"{r}/.git", "line_or_key": "HEAD"}
            for r in REPOS
        ],
    }


def check(snap: Snapshot) -> list[dict[str, Any]]:
    """What is missing, per clade+sense: the to-do list ``senseai-studio check`` prints."""
    rows = []
    cases = content.use_cases(snap.cfg.content)
    for c in snap.clades.values():
        niche = str(c.data.get("niche") or c.key)
        for s in c.senses.values():
            readers = snap.specs.profiles_reading(c, s.id)
            missing = []
            if not lib.describes(c, s.id):
                missing.append("no cited value in the library")
            if not readers:
                missing.append("no profile reads this sense")
            t = evidence.table(snap.cfg.profiles, c.key, s.id)
            if not t.present:
                missing.append(f"no evidence table ({t.label})")
            else:
                ok, total = t.counts()
                if ok < total:
                    missing.append(f"evidence table: {total - ok} of {total} rows unverified")
            ds = data_state(snap, s)
            if ds["state"] == "none":
                missing.append(ds["reason"])
            elif ds["state"] == "synthetic":
                missing.append("no recordings for this modality: synthetic only")
            uc = content.matching(cases, c.key, s.id, [niche, *readers])
            if not uc:
                missing.append("no use-case file")
            elif all(u.is_template for u in uc):
                missing.append("use case is still a template")
            pl = _pipeline(snap, c, s.id)
            rows.append(
                {
                    "clade": c.key,
                    "sense": s.id,
                    "state": sense_state(snap, c, s.id),
                    "step": pl["at"],
                    "steps": pl["total"],
                    "missing": missing,
                    "niche": niche,
                }
            )
    return rows
