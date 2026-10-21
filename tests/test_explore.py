# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Explore against fake GBIF and OpenAlex."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from senseai_studio.app import create_app
from senseai_studio.explore import abstract, any_of, english_names
from senseai_studio.settings import Settings
from tests import fake_outside


def _client(cfg: Settings, handler: object = fake_outside.handler) -> TestClient:
    return TestClient(create_app(cfg, explore_transport=httpx.MockTransport(handler)))  # type: ignore[arg-type]


def test_helpers() -> None:
    assert (
        any_of(["vision", "pit organ", 'sub"strate-borne'])
        == '(vision OR "pit organ" OR "substrate-borne")'
    )
    assert abstract({"b": [1], "a": [0]}) == "a b"
    assert abstract(None) is None
    assert english_names(fake_outside.NAMES[5219436]) == ["Leopard", "Panther"]


def test_species_search_any_name(cfg: Settings) -> None:
    r = _client(cfg).get("/api/studio/explore/species", params={"q": "panther"})
    assert r.status_code == 200, r.text
    d = r.json()
    names = [t["scientific_name"] for t in d["taxa"]]
    # the species called exactly "panther" first, then the subspecies, then the genus
    assert names == ["Panthera pardus", "Puma concolor coryi", "Panthera"]
    leopard = d["taxa"][0]
    assert leopard["common_names"][0] == "Panther"
    assert leopard["library"]["clade"] == "felidae"  # family Felidae is in the library
    assert leopard["library"]["senses"]["vision"]["state"] == "modelled"
    assert {"field": "taxa/0", "source_file": "gbif:species", "line_or_key": 5219436} in d[
        "provenance"
    ]
    assert _client(cfg).get("/api/studio/explore/species", params={"q": "x"}).json()["taxa"] == []


def test_taxon_senses_ranked_by_papers(cfg: Settings) -> None:
    d = _client(cfg).get("/api/studio/explore/taxon/5219436").json()
    assert d["taxon"]["query"] == '("Panthera pardus" OR Leopard OR Panther)'
    top = [(s["id"], s["count"]) for s in d["senses"][:4]]
    assert top[:3] == [("vision", 412), ("hearing", 57), ("olfaction", 12)]
    assert top[3][1] == 0
    assert len(d["senses"]) == 13  # every modality in content/senses.yaml
    v = d["senses"][0]
    assert (
        v["filter"].startswith('title_and_abstract.search:("Panthera pardus"')
        and "retina" in v["filter"]
    )
    assert v["library"] == {"id": "vision", "state": "modelled"}
    assert len(v["top"]) == 3
    assert any(
        p["field"] == "senses/0/terms" and p["source_file"] == "studio/content/senses.yaml"
        for p in d["provenance"]
    )


def test_papers(cfg: Settings) -> None:
    c = _client(cfg)
    d = c.get("/api/studio/explore/taxon/5219436/vision/papers", params={"sort": "recent"}).json()
    assert d["total"] == 412 and len(d["papers"]) == 25 and d["sort"] == "recent"
    p = d["papers"][0]
    assert p["authors"] == [f"Author {j}" for j in range(6)] and p["more_authors"] == 2
    assert p["abstract"] == "Leopards see well" and p["open_access"]
    assert d["years"] == [{"year": 2019, "count": 206}, {"year": 2021, "count": 206}]
    sent = [r for r in fake_outside.SEEN if r.url.path == "/works" and r.url.params.get("page")]
    assert sent[-1].url.params["sort"] == "publication_date:desc"
    assert c.get("/api/studio/explore/taxon/5219436/sonar/papers").status_code == 404
    assert c.get("/api/studio/explore/taxon/1/vision/papers").status_code == 404


def test_outside_down_is_502(cfg: Settings) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    r = _client(cfg, down).get("/api/studio/explore/species", params={"q": "panther"})
    assert r.status_code == 502 and "GBIF unreachable" in r.json()["detail"]
