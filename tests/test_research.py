# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""The research proxy against a fake research backend (httpx MockTransport)."""

from __future__ import annotations

import base64
import json

import httpx
from fastapi.testclient import TestClient

from senseai_studio.app import create_app
from senseai_studio.settings import Settings
from tests.conftest import with_

SEEN: list[httpx.Request] = []


def fake_research(request: httpx.Request) -> httpx.Response:
    SEEN.append(request)
    if request.url.path == "/api/research/health":
        return httpx.Response(200, json={"ok": True})
    if request.url.path == "/api/research/conversations" and request.method == "POST":
        return httpx.Response(201, json={"id": "c1"})
    if request.url.path.endswith("/messages"):
        body = json.loads(request.content)
        stream = (
            "event: text_delta\n"
            f"data: {json.dumps({'text': 'focus ' + body['focus']['library_path']})}\n\n"
            "event: done\ndata: {}\n\n"
        )
        return httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})
    return httpx.Response(404, json={"detail": "nope"})


def test_proxy_off_without_url(client: TestClient) -> None:
    assert client.get("/api/studio/research/health").status_code == 404


def test_proxy_forwards_user_and_streams(cfg: Settings) -> None:
    SEEN.clear()
    app = create_app(
        with_(cfg, research_url="http://127.0.0.1:8100", password="pw"),
        research_transport=httpx.MockTransport(fake_research),
    )
    c = TestClient(app)
    auth = {"Authorization": "Basic " + base64.b64encode(b"ana:pw").decode()}
    assert c.get("/api/studio/research/health").status_code == 401
    assert c.get("/api/studio/research/health", headers=auth).json() == {"ok": True}
    conv = c.post("/api/studio/research/conversations", headers=auth, json={}).json()
    r = c.post(
        f"/api/studio/research/conversations/{conv['id']}/messages",
        headers=auth,
        json={"text": "hi", "focus": {"library_path": "strigidae.senses.hearing"}},
    )
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "focus strigidae.senses.hearing" in r.text
    assert all(q.headers["x-senseai-user"] == "ana" for q in SEEN)
    assert all("authorization" not in q.headers for q in SEEN)
    assert str(SEEN[0].url) == "http://127.0.0.1:8100/api/research/health"
    h = c.get("/api/studio/health").json()
    assert h["research"]["configured"]


def test_proxy_unreachable(cfg: Settings) -> None:
    def boom(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("")

    c = TestClient(
        create_app(
            with_(cfg, research_url="http://127.0.0.1:1"),
            research_transport=httpx.MockTransport(boom),
        )
    )
    r = c.get("/api/studio/research/health")
    assert r.status_code == 502
    assert r.json()["detail"].startswith(
        "research service unreachable at http://127.0.0.1:1: ConnectError (is it running"
    )


def test_proxy_sends_the_shared_token_and_drops_spoofed_identity(cfg: Settings) -> None:
    SEEN.clear()
    app = create_app(
        with_(cfg, research_url="http://research.internal:8100", research_token="s3cret"),
        research_transport=httpx.MockTransport(fake_research),
    )
    c = TestClient(app)
    spoof = {"X-SenseAI-User": "mallory", "x-senseai-proxy-token": "guess"}
    assert c.get("/api/studio/research/health", headers=spoof).status_code == 200
    (q,) = SEEN
    assert q.headers.get_list("x-senseai-user") == ["senseai"], "only the proxy's own name"
    assert q.headers.get_list("x-senseai-proxy-token") == ["s3cret"]
    assert c.get("/api/studio/health").json()["research"]["token"] is True


def test_no_token_header_without_a_token(cfg: Settings) -> None:
    SEEN.clear()
    app = create_app(
        with_(cfg, research_url="http://127.0.0.1:8100"),
        research_transport=httpx.MockTransport(fake_research),
    )
    TestClient(app).get(
        "/api/studio/research/health", headers={"X-SenseAI-Proxy-Token": "from-browser"}
    )
    assert "x-senseai-proxy-token" not in SEEN[0].headers


def test_health_says_whether_research_lets_studio_in(cfg: Settings, monkeypatch: object) -> None:
    def gate(request: httpx.Request) -> httpx.Response:
        ok = request.headers.get("x-senseai-proxy-token") == "s3cret"
        return httpx.Response(200 if ok else 403, json={"detail": "front end only"})

    def health(**kw: object) -> dict[str, object]:
        c = TestClient(create_app(with_(cfg, **kw), research_transport=httpx.MockTransport(gate)))
        return c.get("/api/studio/health").json()["research"]  # type: ignore[no-any-return]

    url = "http://research.internal:8100"
    assert health()["reachable"] is None
    assert health(research_url=url, research_token="s3cret")["reachable"] == "ok"
    assert "no RESEARCH_PROXY_TOKEN" in health(research_url=url)["reachable"]
    wrong = health(research_url=url, research_token="s3cret ")["reachable"]
    assert "differs" in wrong and "7 characters" in wrong


def test_pasted_values_are_cleaned(monkeypatch: object) -> None:
    import pytest

    mp: pytest.MonkeyPatch = monkeypatch  # type: ignore[assignment]
    mp.setenv("RESEARCH_URL", ' "http://research.internal:8100/" ')
    mp.setenv("RESEARCH_PROXY_TOKEN", "'s3cret'\n")
    s = Settings.from_env()
    assert s.research_url == "http://research.internal:8100"
    assert s.research_token == "s3cret"
