# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""The Design tab: research's circuit candidates in, circuit designs out.

    research  GET  /api/research/circuit-candidates?clade=&sense=   scored candidates
              POST /api/research/circuit-candidates/{id}/decision   in_design / adopted / rejected
    circuits  senseai-circuits catalogue | figures | design check | design patch

A *design* is senseai-circuits' ``design@1`` record (knob values for one profile, each bound to
the candidate and claims it came from) plus what Studio keeps about the people's side: who
changed it, the last check, the adoption. Designs live in ``STUDIO_DATA/designs/<id>.json``;
every change is appended to ``history.jsonl``.

The lifecycle is draft → validated (``design check``: every figure of every touched circuit
passes) → adopted (a person, with a one-sentence rationale) or rejected. Any edit sends it back
to draft. Adopting writes nothing into the profiles checkout (Studio reads repos read-only): it
runs ``design patch`` against the profile spec and keeps the patched ``circuits:`` block as a
diff to download and open as a profiles PR, the same way research hands over library changes.
Research hears about each decision on the candidates the design came from.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from senseai_studio import studio
from senseai_studio.facts import profiles as prof
from senseai_studio.facts import upstream
from senseai_studio.prov import Prov
from senseai_studio.settings import Settings

SCHEMA = "senseai-circuits/design@1"
STATUSES = ("draft", "validated", "adopted", "rejected")
EDITABLE = ("title", "profile", "values", "bindings", "candidate_ids", "notes")


class DesignError(Exception):
    """A request the design store refuses; ``status`` is the HTTP code to answer with."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sentence(text: str | None) -> str:
    t = (text or "").strip()
    if len(t.split()) < 3:
        raise DesignError(422, "write a reason of at least one sentence")
    return t


class Research:
    """Studio's server-side calls to the research service (same headers as the proxy)."""

    def __init__(self, cfg: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.cfg = cfg
        self.transport = transport

    @property
    def configured(self) -> bool:
        """Whether RESEARCH_URL is set."""
        return bool(self.cfg.research_url)

    def _call(self, method: str, path: str, user: str, **kw: Any) -> tuple[Any, str | None]:
        if not self.cfg.research_url:
            return None, "research is not configured (RESEARCH_URL unset)"
        headers = {"X-SenseAI-User": user}
        if self.cfg.research_token:
            headers["X-SenseAI-Proxy-Token"] = self.cfg.research_token
        try:
            with httpx.Client(transport=self.transport, timeout=30) as c:
                r = c.request(
                    method, f"{self.cfg.research_url}/api/research/{path}", headers=headers, **kw
                )
        except httpx.HTTPError as e:
            return None, f"research service unreachable: {e}"
        try:
            data = r.json()
        except ValueError:
            data = None
        if r.status_code >= 400:
            detail = data.get("detail") if isinstance(data, dict) else r.text[:300]
            return None, f"research answered {r.status_code}: {detail}"
        return data, None

    def candidates(
        self, clade: str, sense: str, user: str
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Research's ranked candidates for one sense, and an error if it could not answer."""
        data, err = self._call(
            "GET", "circuit-candidates", user, params={"clade": clade, "sense": sense}
        )
        return (data if isinstance(data, list) else []), err

    def decide(
        self, cid: str, status: str, rationale: str, design_id: str, user: str
    ) -> dict[str, Any]:
        """Tell research a person moved a candidate; the outcome, never an exception."""
        body = {"status": status, "rationale": rationale, "design_id": design_id}
        _, err = self._call("POST", f"circuit-candidates/{cid}/decision", user, json=body)
        return {"candidate_id": cid, "status": status, "ok": err is None, "error": err}


class Designs:
    """The design store (JSON files) and the operations the API exposes."""

    def __init__(self, cfg: Settings, research: Research) -> None:
        self.cfg = cfg
        self.research = research
        self.dir = cfg.data_dir / "designs"
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ storage

    def _path(self, did: str) -> Path:
        if not did.startswith("dz-") or not did[3:].isalnum():
            raise DesignError(404, f"no design {did!r}")
        return self.dir / f"{did}.json"

    def get(self, did: str) -> dict[str, Any]:
        """One design; 404 if there is none."""
        p = self._path(did)
        if not p.is_file():
            raise DesignError(404, f"no design {did!r}")
        d: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
        return d

    def all(self, clade: str | None = None, sense: str | None = None) -> list[dict[str, Any]]:
        """Designs, most recently changed first."""
        if not self.dir.is_dir():
            return []
        out = []
        for p in self.dir.glob("dz-*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            if (clade is None or d.get("clade") == clade) and (
                sense is None or d.get("sense") == sense
            ):
                out.append(d)
        return sorted(out, key=lambda d: d.get("updated_at", ""), reverse=True)

    def _save(self, d: dict[str, Any], user: str, event: str, note: str = "") -> dict[str, Any]:
        d["updated_at"] = _now()
        d.setdefault("history", []).append(
            {"at": d["updated_at"], "by": user, "event": event, "note": note}
        )
        self.dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            tmp = self._path(d["id"]).with_suffix(".tmp")
            tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
            tmp.replace(self._path(d["id"]))
            with (self.dir / "history.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"design_id": d["id"], **d["history"][-1]}) + "\n")
        return d

    # ------------------------------------------------------------------ circuits

    def _validate_values(self, d: dict[str, Any]) -> None:
        r = upstream.circuits_json(self.cfg, ["design", "check", "-", "--no-figures"], stdin=d)
        if isinstance(r, dict) and r.get("ok") is False and "error" in r:
            code = 503 if r.get("installed") is False else 422
            raise DesignError(code, str(r["error"]))

    def figures(self, values: dict[str, Any], circuits: list[str] | None) -> dict[str, Any]:
        """``senseai-circuits figures`` for these values (the live preview)."""
        args = ["figures", "--values", json.dumps(values)]
        for c in circuits or []:
            args += ["--circuit", c]
        r = upstream.circuits_json(self.cfg, args)
        if not isinstance(r, dict) or "figures" not in r:
            raise DesignError(
                503 if isinstance(r, dict) and r.get("installed") is False else 422,
                str(r.get("error") if isinstance(r, dict) else r),
            )
        return r

    # ------------------------------------------------------------------ operations

    def create(self, clade: str, sense: str, body: dict[str, Any], user: str) -> dict[str, Any]:
        """A new draft; research hears which candidates it uses."""
        d: dict[str, Any] = {
            "schema": SCHEMA,
            "id": f"dz-{int(time.time()):x}{secrets.token_hex(3)}",
            "title": body.get("title") or "Untitled design",
            "clade": clade,
            "sense": sense,
            "profile": body.get("profile"),
            "values": dict(body.get("values") or {}),
            "bindings": dict(body.get("bindings") or {}),
            "candidate_ids": list(body.get("candidate_ids") or []),
            "notes": body.get("notes") or "",
            "status": "draft",
            "created_by": user,
            "created_at": _now(),
            "check": None,
            "adoption": None,
            "research_sync": [],
        }
        self._validate_values(d)
        self._save(d, user, "created")
        for cid in d["candidate_ids"]:
            d["research_sync"].append(
                self.research.decide(
                    cid, "in_design", f"Designing it in Studio as {d['id']}.", d["id"], user
                )
            )
        return (
            self._save(d, user, "research notified")
            if d["candidate_ids"] and self.research.configured
            else d
        )

    def update(self, did: str, body: dict[str, Any], user: str) -> dict[str, Any]:
        """Edit a draft or validated design; it goes back to draft."""
        d = self.get(did)
        if d["status"] in ("adopted", "rejected"):
            raise DesignError(
                409, f"design {did} is {d['status']}; start a new design to change it"
            )
        for k in EDITABLE:
            if k in body and body[k] is not None:
                d[k] = body[k]
        self._validate_values(d)
        d["status"], d["check"] = "draft", None
        return self._save(d, user, "edited")

    def check(self, did: str, user: str) -> dict[str, Any]:
        """``design check``: validated only when every touched figure passes."""
        d = self.get(did)
        if d["status"] in ("adopted", "rejected"):
            raise DesignError(409, f"design {did} is {d['status']}")
        r = upstream.circuits_json(self.cfg, ["design", "check", "-"], stdin=d)
        if not isinstance(r, dict) or "status" not in r:
            raise DesignError(
                503 if isinstance(r, dict) and r.get("installed") is False else 422,
                str(r.get("error") if isinstance(r, dict) else r),
            )
        d["check"] = r | {"at": _now()}
        d["status"] = "validated" if r["status"] == "validated" else "draft"
        failed = [f["circuit"] for f in r.get("figures", []) if not f.get("ok")]
        return self._save(
            d, user, "checked", "all figures pass" if not failed else "fails: " + ", ".join(failed)
        )

    def _spec_path(self, snap: studio.Snapshot, d: dict[str, Any]) -> Path:
        name = d.get("profile")
        spec = snap.specs.specs.get(name or "")
        if not name or spec is None:
            raise DesignError(422, "choose the profile this design is for")
        src = spec.get("source")
        path = Path(src) if src else snap.cfg.profiles / prof.SPECS_DIR / f"{name}.profile.yaml"
        if not path.is_file():
            raise DesignError(422, f"profile spec not found: {path}")
        return path

    def adopt(
        self, snap: studio.Snapshot, did: str, rationale: str | None, user: str
    ) -> dict[str, Any]:
        """Adopt a validated design: keep the profile patch, tell research."""
        d = self.get(did)
        why = _sentence(rationale)
        if d["status"] != "validated":
            raise DesignError(409, "only a validated design can be adopted: run the check first")
        spec = self._spec_path(snap, d)
        name = (
            str(spec.relative_to(snap.cfg.profiles))
            if spec.is_relative_to(snap.cfg.profiles)
            else spec.name
        )
        args = ["design", "patch", "-", "--spec", str(spec), "--name", name]
        r = upstream.circuits_json(self.cfg, args, stdin=d)
        if not isinstance(r, dict) or "diff" not in r:
            raise DesignError(422, str(r.get("error") if isinstance(r, dict) else r))
        patch = self.dir / f"{did}.patch"
        patch.write_text(r["diff"], encoding="utf-8")
        d["status"] = "adopted"
        d["adoption"] = {
            "by": user,
            "at": _now(),
            "rationale": why,
            "spec_file": snap.label(spec),
            "patch": f"/api/studio/designs/{did}/patch",
            "circuits": r.get("circuits"),
            "diff": r["diff"],
        }
        d["research_sync"] = [
            self.research.decide(cid, "adopted", why, did, user)
            for cid in d.get("candidate_ids", [])
        ]
        return self._save(d, user, "adopted", why)

    def reject(self, did: str, rationale: str | None, user: str) -> dict[str, Any]:
        """Reject a design with a reason; its candidates go back to open."""
        d = self.get(did)
        why = _sentence(rationale)
        if d["status"] == "adopted":
            raise DesignError(409, f"design {did} is adopted")
        d["status"] = "rejected"
        d["research_sync"] = [
            self.research.decide(cid, "open", f"Design {did} was rejected: {why}", did, user)
            for cid in d.get("candidate_ids", [])
        ]
        return self._save(d, user, "rejected", why)

    def patch_text(self, did: str) -> str:
        """The adopted design's unified diff of the profile spec."""
        self.get(did)
        p = self.dir / f"{did}.patch"
        if not p.is_file():
            raise DesignError(404, "this design has not been adopted")
        return p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- the page


def page(
    snap: studio.Snapshot, store: Designs, clade: str, sense: str, user: str
) -> dict[str, Any]:
    """Everything the Design tab shows: catalogue, knobs, profiles, candidates, designs."""
    c, s = snap.sense(clade, sense)
    p = Prov()
    readers = snap.specs.profiles_reading(c, s.id)
    model_circuits = studio._circuits(snap, s, readers, Prov())
    for i, k in enumerate(model_circuits["knobs"]):
        p.add(f"knobs/{i}", f"cli:{snap.cfg.circuits_cmd} knobs --json", k["name"])
    cat = upstream.catalogue(snap.cfg)
    types = (
        [t for t in cat.get("circuits", []) if s.modality in (t.get("modalities") or [])]
        if isinstance(cat, dict)
        else []
    )
    for i, t in enumerate(types):
        p.add(
            f"circuit_types/{i}", f"cli:{snap.cfg.circuits_cmd} catalogue --json", t.get("prefix")
        )
    profiles_out = []
    for i, name in enumerate(readers):
        spec = snap.specs.specs[name]
        set_by = studio._species_circuits(snap, spec)
        profiles_out.append(
            {
                "name": name,
                "source_file": prof.spec_label(snap.cfg, spec),
                "circuits": {k: v["value"] for k, v in set_by.items()},
            }
        )
        p.add(f"profiles/{i}", prof.spec_label(snap.cfg, spec), "circuits")
    cands, err = (
        store.research.candidates(c.key, s.id, user) if store.research.configured else ([], None)
    )
    for i, cd in enumerate(cands):
        p.add(f"candidates/{i}", "research:/api/research/circuit-candidates", cd.get("id"))
    designs = store.all(c.key, s.id)
    for i, d in enumerate(designs):
        p.add(f"designs/{i}", f"studio:data/designs/{d['id']}.json", d["id"])
    local_version = cat.get("circuits_version") if isinstance(cat, dict) else None
    scored_with = sorted(
        {str(x.get("circuits_version")) for x in cands if x.get("circuits_version")}
    )
    return {
        "clade": c.key,
        "sense": s.id,
        "modality": s.modality,
        "circuits": {
            "installed": model_circuits["installed"],
            "ok": model_circuits["ok"] and bool(types or not cat.get("error")),
            "error": model_circuits["error"]
            or (cat.get("error") if isinstance(cat, dict) else None),
            "version": local_version,
        },
        "circuit_types": types,
        "measures": [
            m for m in cat.get("measures", []) if s.modality in (m.get("modalities") or [])
        ]
        if isinstance(cat, dict)
        else [],
        "knobs": model_circuits["knobs"],
        "profiles": profiles_out,
        "research": {
            "configured": store.research.configured,
            "ok": store.research.configured and err is None,
            "error": err,
            "scored_with": scored_with,
            "stale": bool(local_version and scored_with and scored_with != [local_version]),
        },
        "candidates": cands,
        "designs": designs,
        "provenance": p.out(),
    }
