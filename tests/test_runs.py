# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from senseai_studio.app import create_app
from senseai_studio.settings import Settings
from tests.conftest import with_


def dsec_fixture(root: Path, name: str = "zurich_city_fixture") -> Path:
    """The folder layout senseai_ingest.testing.make_dsec_fixture writes (files left empty)."""
    d = root / name
    (d / "events/left").mkdir(parents=True)
    (d / "events/left/events.h5").write_bytes(b"")
    (d / "images/left/rectified").mkdir(parents=True)
    return d


def wait(client: TestClient, job_id: str) -> dict:  # type: ignore[type-arg]
    app = client.app
    jobs = app.state.jobs  # type: ignore[attr-defined]
    return jobs.wait(job_id, timeout=30)  # type: ignore[no-any-return]


def test_options_synthetic_and_arms(client: TestClient) -> None:
    o = client.get("/api/studio/felidae/vision/run/options").json()
    src = {s["id"]: s for s in o["sources"]}
    assert src["synthetic"]["available"] and src["synthetic"]["streams"] == ["EVENT", "FRAME"]
    arms = {a["id"]: a for a in o["arms"]}
    assert arms["panther_vision@prior"]["available"]
    assert arms["panther_vision@prior"]["bench_arm"] == "profile:panther_vision@prior"
    assert arms["null@prior"]["role"] == "control"
    assert not arms["panther_vision@learned"]["available"]
    assert "untrained" in arms["panther_vision@learned"]["reason"]
    assert o["prereg"][0]["id"] == "E1" and o["prereg"][0]["clips"] == ["zurich_city_fixture"]


def test_options_owls_hearing(client: TestClient) -> None:
    o = client.get("/api/studio/strigidae/hearing/run/options").json()
    assert o["sources"][0]["streams"] == ["AUDIO"]
    assert [a["id"] for a in o["arms"]] == ["null@prior"]  # no profile reads owl hearing yet
    assert o["view"] == "spectrogram"


def test_legacy_bench_disables_with_reasons(cfg: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_BENCH_LEGACY", "1")
    c = TestClient(create_app(cfg))
    o = c.get("/api/studio/felidae/vision/run/options").json()
    assert not o["sources"][0]["available"]
    assert "--synthetic" in o["sources"][0]["reason"]
    arm = next(a for a in o["arms"] if a["id"] == "panther_vision@prior")
    assert not arm["available"] and "generic profile" in arm["reason"]
    r = c.post(
        "/api/studio/felidae/vision/run", json={"source": "synthetic", "arms": ["null@prior"]}
    )
    assert r.status_code == 422


def test_dsec_recordings_listed(cfg: Settings) -> None:
    dsec_fixture(cfg.data_root)  # type: ignore[arg-type]
    c = TestClient(create_app(cfg))
    o = c.get("/api/studio/felidae/vision/run/options").json()
    rec = next(s for s in o["sources"] if s["dataset"] == "dsec")
    assert rec["id"] == "dsec:zurich_city_fixture" and rec["available"]
    sp = c.get("/api/studio/species").json()
    cat = next(x for x in sp["cards"] if x["clade"] == "felidae")
    assert next(s for s in cat["senses"] if s["id"] == "vision")["data"] == "available"
    assert next(s for s in cat["senses"] if s["id"] == "hearing")["data"] == "synthetic"


def test_synthetic_run_streams_events(client: TestClient) -> None:
    r = client.post(
        "/api/studio/felidae/vision/run",
        json={"source": "synthetic", "arms": ["panther_vision@prior", "null@prior"], "seconds": 2},
    )
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["synthetic"] and not job["preregistered"]
    cmd = job["cmd"]
    assert cmd[cmd.index("--synthetic") + 1] == "2"
    assert cmd[cmd.index("--arms") + 1] == "profile:panther_vision@prior,profile:null@prior"
    assert cmd[cmd.index("--prior-library") + 1].endswith("library/felidae.yaml")
    with client.stream("GET", f"/api/studio/jobs/{job['id']}/events") as s:
        text = "".join(s.iter_text())
    evs = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]
    kinds = [e["type"] for e in evs]
    assert kinds[0] == "run_start" and kinds[-1] == "run_end"
    assert "fire" in kinds and "frame" in kinds
    done = wait(client, job["id"])
    assert done["status"] == "succeeded", done
    assert len(done["summaries"]) == 2
    frame = next(e for e in evs if e["type"] == "frame")
    img = client.get(f"/api/studio/jobs/{job['id']}/files/{frame['path']}")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert client.get(f"/api/studio/jobs/{job['id']}/files/job.json").status_code == 404
    assert client.get(f"/api/studio/jobs/{job['id']}/files/../../x.png").status_code == 404
    assert "Replay report" in client.get(f"/api/studio/jobs/{job['id']}/report").text
    assert client.get("/api/studio/jobs?clade=felidae").json()[0]["id"] == job["id"]


def test_owls_synthetic_run(client: TestClient) -> None:
    r = client.post(
        "/api/studio/strigidae/hearing/run",
        json={"source": "synthetic", "arms": ["null@prior"], "seconds": 1},
    )
    assert r.status_code == 201
    job = r.json()
    assert "AUDIO" in job["cmd"]
    assert wait(client, job["id"])["status"] == "succeeded"


def test_dsec_run_is_preregistered_clip(cfg: Settings) -> None:
    dsec_fixture(cfg.data_root)  # type: ignore[arg-type]
    c = TestClient(create_app(cfg))
    r = c.post(
        "/api/studio/felidae/vision/run",
        json={"source": "dsec:zurich_city_fixture", "arms": ["panther_vision@prior"]},
    )
    assert r.status_code == 201, r.text
    job = r.json()
    assert not job["synthetic"] and job["preregistered"]
    assert "--sequence" in job["cmd"] and "--max-seconds" in job["cmd"]
    assert wait(c, job["id"])["status"] == "succeeded"


def test_crash_fails_with_reason(cfg: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_BENCH_MODE", "crash")
    c = TestClient(create_app(cfg))
    job = c.post(
        "/api/studio/felidae/vision/run", json={"source": "synthetic", "arms": ["null@prior"]}
    ).json()
    done = wait(c, job["id"])
    assert done["status"] == "failed" and "crashing" in done["error"]


def test_cancel_and_one_at_a_time(cfg: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_BENCH_MODE", "hang")
    c = TestClient(create_app(cfg))
    job = c.post(
        "/api/studio/felidae/vision/run", json={"source": "synthetic", "arms": ["null@prior"]}
    ).json()
    again = c.post(
        "/api/studio/felidae/vision/run", json={"source": "synthetic", "arms": ["null@prior"]}
    )
    assert again.status_code == 409
    assert c.post(f"/api/studio/jobs/{job['id']}/cancel").json()["status"] == "cancelling"
    assert wait(c, job["id"])["status"] == "cancelled"


def test_bad_requests(client: TestClient) -> None:
    post = client.post
    assert (
        post(
            "/api/studio/felidae/vision/run", json={"source": "nope", "arms": ["null@prior"]}
        ).status_code
        == 422
    )
    assert (
        post(
            "/api/studio/felidae/vision/run", json={"source": "synthetic", "arms": ["x@prior"]}
        ).status_code
        == 422
    )
    assert (
        post(
            "/api/studio/felidae/vision/run",
            json={"source": "synthetic", "arms": ["panther_vision@learned"]},
        ).status_code
        == 422
    )
    assert (
        post("/api/studio/felidae/vision/run", json={"source": "synthetic", "arms": []}).status_code
        == 422
    )
    assert (
        post(
            "/api/studio/canidae/vision/run", json={"source": "synthetic", "arms": ["null@prior"]}
        ).status_code
        == 404
    )
    assert client.get("/api/studio/jobs/r000").status_code == 404


def test_restart_marks_dead_jobs_failed(cfg: Settings) -> None:
    d = cfg.data_dir / "jobs" / "r20260101-000000-abcd"
    d.mkdir(parents=True)
    (d / "job.json").write_text(
        json.dumps(
            {
                "id": d.name,
                "clade": "felidae",
                "sense": "vision",
                "status": "running",
                "pid": 999999,
            }
        )
    )
    c = TestClient(create_app(with_(cfg)))
    assert c.get(f"/api/studio/jobs/{d.name}").json()["status"] == "failed"
