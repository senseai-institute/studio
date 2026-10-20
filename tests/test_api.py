# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import base64
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openapi_spec_validator import validate

from senseai_studio.app import create_app
from senseai_studio.settings import Settings
from tests.conftest import with_

PAIRS = [
    ("felidae", "vision"),
    ("felidae", "hearing"),
    ("felidae", "vibrissae"),
    ("strigidae", "hearing"),
    ("strigidae", "vision"),
]
TABS = ["sources", "model", "pipeline", "use-cases", "run/options"]


def _walk(obj: Any, path: list[str]) -> bool:
    for k in path:
        if isinstance(obj, list):
            if not k.isdigit() or int(k) >= len(obj):
                return False
            obj = obj[int(k)]
        elif isinstance(obj, dict):
            if k not in obj:
                return False
            obj = obj[k]
        else:
            return False
    return True


def assert_provenance(body: dict[str, Any]) -> None:
    prov = body["provenance"]
    assert prov, "every response carries provenance"
    for e in prov:
        assert set(e) == {"field", "source_file", "line_or_key"}
        top = e["field"].split("/")[0]
        assert top in body, e
        assert e["source_file"]


def test_species(client: TestClient) -> None:
    r = client.get("/api/studio/species")
    assert r.status_code == 200
    body = r.json()
    assert_provenance(body)
    cards = {c["clade"]: c for c in body["cards"]}
    assert set(cards) == {"felidae", "strigidae"}
    cat = {s["id"]: s for s in cards["felidae"]["senses"]}
    assert cat["vision"]["state"] == "modelled"
    assert cat["vision"]["profiles"] == ["panther", "panther_vision"]
    assert cat["vision"]["data"] == "synthetic"
    assert cat["vibrissae"]["state"] == "described"
    owl = {s["id"]: s for s in cards["strigidae"]["senses"]}
    assert owl["hearing"]["state"] == "described" and owl["vision"]["state"] == "empty"
    assert cards["strigidae"]["names"] == ["owls", "typical owls"]


@pytest.mark.parametrize("clade,sense", PAIRS)
@pytest.mark.parametrize("tab", TABS)
def test_every_tab_renders(client: TestClient, clade: str, sense: str, tab: str) -> None:
    r = client.get(f"/api/studio/{clade}/{sense}/{tab}")
    assert r.status_code == 200, r.text
    body = r.json()
    if tab not in ("run/options",) or body["provenance"]:
        assert_provenance(body)


def test_sources_cats_vision(client: TestClient) -> None:
    body = client.get("/api/studio/felidae/vision/sources").json()
    q = body["quantities"][0]
    assert q["value"] == -0.74 and q["unit"] == "log10 re human"
    assert q["verification"] == {"tabled": True, "status": "unverified", "quote": None}
    assert q["citations"][0]["link"] == "https://doi.org/10.1152/jn.90641.2008"
    assert body["table"] == {
        "present": True,
        "file": "profiles/library/tables/felidae.vision.csv",
        "verified": 1,
        "total": 2,
    }
    assert any(r["id"] == "felidae-vision-q-1" for r in body["requests"])
    assert any(
        r["id"] == "panther-vision-reflex-commit-threshold-literal" for r in body["requests"]
    )
    lines = {e["field"]: e for e in body["provenance"]}
    assert lines["quantities/0/value"]["source_file"] == "profiles/library/felidae.yaml"
    assert isinstance(lines["quantities/0/value"]["line_or_key"], int)


def test_sources_owls_hearing(client: TestClient) -> None:
    body = client.get("/api/studio/strigidae/hearing/sources").json()
    q = body["quantities"][0]
    assert q["value"] == 2 and q["unit"] == "deg" and q["species"] == "Tyto alba"
    assert q["citations"][0]["year"] == "1979"
    assert q["verification"]["status"] == "not tabled"
    assert body["table"]["present"] is False
    assert any("audiogram" in o["text"] for o in body["open_questions"])


def test_model_cats_vision(client: TestClient) -> None:
    body = client.get("/api/studio/felidae/vision/model").json()
    assert body["engine"] == "yaml-fallback"
    assert [p["name"] for p in body["profiles"]] == ["panther", "panther_vision"]
    gl = next(f for f in body["profiles"][1]["fields"] if f["field"] == "gain_lut")
    assert gl["kind"] == "rule" and gl["reads_this_sense"]
    assert body["circuits"] == {
        "installed": False,
        "ok": False,
        "error": "circuits: not installed",
        "knobs": [],
    }
    assert body["learned"] == []  # untrained
    assert body["world_prior"]["ok"] is False  # no world checkout in the fixture stack
    assert body["rulebook"]["rules"][0]["id"] == "felidae-vision-gain"
    assert {r["profile"] for r in body["reflex"]} == {"panther", "panther_vision"}


def test_model_owls_hearing_has_no_profile(client: TestClient) -> None:
    body = client.get("/api/studio/strigidae/hearing/model").json()
    assert body["profiles"] == [] and body["reflex"] == [] and body["circuits"]["knobs"] == []


def test_use_cases_template_and_step(client: TestClient) -> None:
    body = client.get("/api/studio/felidae/vision/use-cases").json()
    assert body["items"][0]["template"] is True
    assert body["step"] == 3 and body["steps"] == 10
    assert "<h2>The job</h2>" in body["items"][0]["html"]


def test_not_found(client: TestClient) -> None:
    assert client.get("/api/studio/canidae/vision/sources").status_code == 404
    assert client.get("/api/studio/felidae/smell/model").status_code == 404
    assert client.get("/api/studio/nope").status_code == 404


def test_health(client: TestClient) -> None:
    body = client.get("/api/studio/health").json()
    assert body["ok"] and body["clades"] == 2
    assert body["repos"]["profiles"]["found"]
    assert body["research"] == {"configured": False, "url": None}
    assert body["bench"]["features"]["synthetic"]


def test_openapi_validates(client: TestClient) -> None:
    doc = client.get("/api/studio/openapi.json").json()
    validate(doc)
    for p in (
        "/api/studio/species",
        "/api/studio/{clade}/{sense}/sources",
        "/api/studio/{clade}/{sense}/model",
        "/api/studio/{clade}/{sense}/pipeline",
        "/api/studio/{clade}/{sense}/use-cases",
        "/api/studio/{clade}/{sense}/run/options",
        "/api/studio/{clade}/{sense}/run",
        "/api/studio/jobs/{job_id}/events",
        "/api/studio/health",
    ):
        assert p in doc["paths"], p


def test_web_routes(client: TestClient) -> None:
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/studio"
    assert client.get("/studio/felidae/vision").status_code in (200, 503)
    assert client.get("/healthz").json() == {"ok": True}


def test_password(cfg: Settings) -> None:
    c = TestClient(create_app(with_(cfg, password="pw")))
    assert c.get("/api/studio/species").status_code == 401
    assert c.get("/api/studio/health").status_code == 200
    tok = base64.b64encode(b"senseai:pw").decode()
    assert (
        c.get("/api/studio/species", headers={"Authorization": f"Basic {tok}"}).status_code == 200
    )
    bad = base64.b64encode(b"senseai:no").decode()
    assert (
        c.get("/api/studio/species", headers={"Authorization": f"Basic {bad}"}).status_code == 401
    )
