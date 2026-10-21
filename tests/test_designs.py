# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""The Design tab API: research candidates in, circuits checks, adoption out to a profile patch."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from senseai_studio.app import create_app
from senseai_studio.settings import Settings
from tests.conftest import FIXTURES, with_

FAKE = f"{sys.executable} {FIXTURES.parent / 'fake_circuits.py'}"
CID = "cc:felidae.vision:felidae.senses.vision.measurements.rf_center_radius"
CANDIDATE = {
    "id": CID,
    "clade": "felidae",
    "sense": "vision",
    "library_path": "felidae.senses.vision.measurements.rf_center_radius",
    "claim_ids": ["lib:felidae.senses.vision.measurements.rf_center_radius"],
    "likelihood": 1.0,
    "quality": 0.4,
    "priority": 0.4,
    "circuits_version": "0.0.9",
    "circuitability": {"level": "knob", "knob": "cs.sigma_center_deg", "value": 0.57},
    "status": "open",
}


class FakeResearch:
    def __init__(self, fail: bool = False) -> None:
        self.seen: list[tuple[str, str, dict[str, str], Any]] = []
        self.fail = fail

    def __call__(self, r: httpx.Request) -> httpx.Response:
        body = json.loads(r.content) if r.content else None
        self.seen.append((r.method, r.url.path, dict(r.headers), body))
        if self.fail:
            return httpx.Response(500, json={"detail": "ledger locked"})
        if r.url.path == "/api/research/circuit-candidates":
            assert r.url.params["clade"] == "felidae" and r.url.params["sense"] == "vision"
            return httpx.Response(200, json=[CANDIDATE])
        if r.url.path.endswith("/decision"):
            return httpx.Response(200, json=CANDIDATE | {"status": body["status"]})
        return httpx.Response(404, json={"detail": "no"})

    def decisions(self) -> list[str]:
        return [b["status"] for m, p, _, b in self.seen if p.endswith("/decision")]


def app(cfg: Settings, research: FakeResearch | None = None, **kw: Any) -> TestClient:
    cfg = with_(cfg, circuits_cmd=FAKE, **kw)
    if research is not None:
        cfg = with_(cfg, research_url="http://research.internal", research_token="tok")
    transport = httpx.MockTransport(research) if research else None
    return TestClient(create_app(cfg, research_transport=transport))


def new_design(c: TestClient, **over: Any) -> dict[str, Any]:
    body = {
        "title": "cat centre",
        "profile": "panther_vision",
        "values": {"cs.sigma_center_deg": 0.57},
        "bindings": {
            "cs.sigma_center_deg": {"candidate_id": CID, "claim_ids": CANDIDATE["claim_ids"]}
        },
        "candidate_ids": [CID],
    } | over
    r = c.post("/api/studio/felidae/vision/designs", json=body)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def test_page_joins_circuits_profiles_research_and_designs(cfg: Settings) -> None:
    research = FakeResearch()
    c = app(cfg, research)
    page = c.get("/api/studio/felidae/vision/design").json()
    assert page["modality"] == "vision" and page["circuits"]["installed"] and page["circuits"]["ok"]
    assert [t["prefix"] for t in page["circuit_types"]] == ["cs", "ts"]
    assert page["measures"] == []  # the fake's only measure is for hearing
    assert {k["name"] for k in page["knobs"]} >= {"cs.sigma_center_deg", "lgmd.w_inhib"}
    assert [p["name"] for p in page["profiles"]] == ["panther", "panther_vision"]
    pv = page["profiles"][1]
    assert pv["circuits"] == {"cs.sigma_center_deg": 0.7} and pv["source_file"].endswith(
        "panther_vision.profile.yaml"
    )
    assert page["candidates"][0]["id"] == CID
    assert page["research"] == {
        "configured": True,
        "ok": True,
        "error": None,
        "scored_with": ["0.0.9"],
        "stale": True,  # research scored with another circuits version than Studio runs
    }
    fields = {p["field"] for p in page["provenance"]}
    assert "candidates/0" in fields and "circuit_types/0" in fields and "profiles/1" in fields
    _, _, headers, _ = research.seen[0]
    assert headers["x-senseai-proxy-token"] == "tok" and headers["x-senseai-user"]
    assert c.get("/api/studio/felidae/nosuch/design").status_code == 404


def test_without_research_or_circuits_the_page_says_so(cfg: Settings) -> None:
    c = TestClient(create_app(cfg))  # circuits not installed, research not configured
    page = c.get("/api/studio/felidae/vision/design").json()
    assert not page["circuits"]["installed"] and page["circuit_types"] == []
    assert page["research"]["configured"] is False and page["candidates"] == []
    r = c.post("/api/studio/felidae/vision/designs", json={"values": {"cs.sigma_center_deg": 0.6}})
    assert r.status_code == 503 and "not installed" in r.json()["detail"]
    down = app(cfg, FakeResearch(fail=True))
    page = down.get("/api/studio/felidae/vision/design").json()
    assert page["research"]["ok"] is False and "500" in page["research"]["error"]


def test_draft_check_adopt_tells_research_and_writes_a_patch(cfg: Settings) -> None:
    research = FakeResearch()
    c = app(cfg, research)
    d = new_design(c)
    assert (
        d["status"] == "draft"
        and d["research_sync"][0]["ok"]
        and research.decisions() == ["in_design"]
    )
    did = d["id"]
    r = c.post(f"/api/studio/designs/{did}/adopt", json={"rationale": "This is the cat value."})
    assert r.status_code == 409 and "validated" in r.json()["detail"]
    checked = c.post(f"/api/studio/designs/{did}/check").json()
    assert checked["status"] == "validated" and checked["check"]["figures"][0]["ok"]
    assert c.post(f"/api/studio/designs/{did}/adopt", json={"rationale": "ok"}).status_code == 422
    adopted = c.post(
        f"/api/studio/designs/{did}/adopt",
        json={"rationale": "Rodieck's radius, verified in the ledger."},
    )
    assert adopted.status_code == 200, adopted.text
    a = adopted.json()
    assert a["status"] == "adopted" and a["adoption"]["rationale"].startswith("Rodieck")
    assert (
        a["adoption"]["spec_file"]
        == "profiles/packages/senseai-profiles/profiles/panther_vision.profile.yaml"
    )
    assert research.decisions() == ["in_design", "adopted"]
    _, path, _, body = research.seen[-1]
    assert path == f"/api/research/circuit-candidates/{CID}/decision" and body["design_id"] == did
    patch = c.get(f"/api/studio/designs/{did}/patch")
    assert patch.status_code == 200 and "attachment" in patch.headers["content-disposition"]
    assert patch.text.startswith(
        "--- a/packages/senseai-profiles/profiles/panther_vision.profile.yaml"
    )
    assert "cs.sigma_center_deg: 0.57" in patch.text
    spec = cfg.profiles / "packages/senseai-profiles/profiles/panther_vision.profile.yaml"
    assert (
        "cs.sigma_center_deg: 0.57" not in spec.read_text()
    )  # Studio never writes the profiles checkout
    assert c.put(f"/api/studio/designs/{did}", json={"title": "x"}).status_code == 409
    assert c.post(f"/api/studio/designs/{did}/check").status_code == 409
    assert (
        c.post(
            f"/api/studio/designs/{did}/reject", json={"rationale": "No longer wanted here."}
        ).status_code
        == 409
    )
    hist = [h["event"] for h in c.get(f"/api/studio/designs/{did}").json()["history"]]
    assert hist == ["created", "research notified", "checked", "adopted"]
    lines = (cfg.data_dir / "designs" / "history.jsonl").read_text().splitlines()
    assert len(lines) == 4 and json.loads(lines[-1])["event"] == "adopted"
    page = c.get("/api/studio/felidae/vision/design").json()
    assert [x["id"] for x in page["designs"]] == [did]


def test_edits_go_back_to_draft_and_failed_figures_block_validation(cfg: Settings) -> None:
    c = app(cfg)
    d = new_design(c, candidate_ids=[])
    did = d["id"]
    assert c.post(f"/api/studio/designs/{did}/check").json()["status"] == "validated"
    edited = c.put(
        f"/api/studio/designs/{did}", json={"values": {"lgmd.w_inhib": 3.5}, "bindings": {}}
    ).json()
    assert edited["status"] == "draft" and edited["check"] is None
    failed = c.post(f"/api/studio/designs/{did}/check").json()
    assert failed["status"] == "draft" and failed["history"][-1]["note"] == "fails: lgmd"
    bad = c.put(f"/api/studio/designs/{did}", json={"values": {"cs.sigma_center_deg": 99}})
    assert bad.status_code == 422 and "outside" in bad.json()["detail"]
    unknown = c.post("/api/studio/felidae/vision/designs", json={"values": {"cs.nope": 1}})
    assert unknown.status_code == 422 and "unknown knob" in unknown.json()["detail"]
    rej = c.post(
        f"/api/studio/designs/{did}/reject", json={"rationale": "Inhibition too strong for a cat."}
    )
    assert rej.json()["status"] == "rejected"
    assert c.get(f"/api/studio/designs/{did}/patch").status_code == 404
    assert c.get("/api/studio/designs/dz-nope").status_code == 404
    assert c.get("/api/studio/designs/../../etc").status_code == 404


def test_adopting_needs_a_profile(cfg: Settings) -> None:
    c = app(cfg)
    d = new_design(c, profile=None, candidate_ids=[])
    c.post(f"/api/studio/designs/{d['id']}/check")
    r = c.post(
        f"/api/studio/designs/{d['id']}/adopt", json={"rationale": "We want this one adopted."}
    )
    assert r.status_code == 422 and "profile" in r.json()["detail"]


def test_reject_reopens_the_candidates_in_research(cfg: Settings) -> None:
    research = FakeResearch()
    c = app(cfg, research)
    d = new_design(c)
    c.post(
        f"/api/studio/designs/{d['id']}/reject",
        json={"rationale": "The radius is for X cells only."},
    )
    assert research.decisions() == ["in_design", "open"]


def test_figures_preview(cfg: Settings) -> None:
    c = app(cfg)
    r = c.post(
        "/api/studio/design/figures", json={"values": {"lgmd.w_inhib": 0.3}, "circuits": ["lgmd"]}
    )
    assert r.status_code == 200 and r.json()["figures"][0]["circuit"] == "lgmd" and r.json()["ok"]
    bad = c.post("/api/studio/design/figures", json={"values": {"cs.nope": 1}})
    assert bad.status_code == 422


REAL = os.environ.get("SENSEAI_CIRCUITS_CMD", "")


@pytest.mark.skipif(
    not REAL or not shutil.which(shlex.split(REAL)[0]),
    reason="set SENSEAI_CIRCUITS_CMD to a real senseai-circuits",
)
def test_against_the_real_circuits(cfg: Settings) -> None:
    cr = TestClient(create_app(with_(cfg, circuits_cmd=REAL)))
    page = cr.get("/api/studio/felidae/vision/design").json()
    assert {"cs", "emd", "lgmd"} <= {t["prefix"] for t in page["circuit_types"]}
    d = new_design(cr, candidate_ids=[])
    checked = cr.post(f"/api/studio/designs/{d['id']}/check").json()
    assert checked["status"] == "validated" and checked["check"]["figures"][0]["circuit"] == "cs"
    adopted = cr.post(
        f"/api/studio/designs/{d['id']}/adopt", json={"rationale": "The real circuits agree here."}
    ).json()
    assert (
        "circuits:" in adopted["adoption"]["diff"]
        and adopted["adoption"]["circuits"]["cs.sigma_center_deg"] == 0.57
    )
    figs = cr.post(
        "/api/studio/design/figures", json={"values": {"emd.delay_tau_ms": 70}, "circuits": ["emd"]}
    ).json()
    assert figs["ok"] and figs["figures"][0]["series"]
