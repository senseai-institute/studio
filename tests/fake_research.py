# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""A stand-in research service for the browser test. Chat turns replay events recorded from the
real service (web/src/research/fixtures/research_events.json); the other routes return
research's shapes (its docs/API.md). Every request must carry the proxy token, as the real
service requires when Studio reaches it over a network."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

TOKEN = "test-proxy-token"
CLAIM = "lib:felidae.senses.vision.detection_threshold"
RECORDED = json.loads(
    (
        Path(__file__).resolve().parents[1] / "web/src/research/fixtures/research_events.json"
    ).read_text()
)


def _turns() -> list[list[dict[str, Any]]]:
    turns: list[list[dict[str, Any]]] = [[]]
    for e in RECORDED["events"]:
        turns[-1].append(e)
        if e["event"] == "done":
            turns.append([])
    return [t for t in turns if t]


def make_app() -> FastAPI:
    app = FastAPI()
    state: dict[str, Any] = {"value": "-0.74 log10 re human", "turn": 0, "history": []}
    seen_users: list[str] = []
    app.state.seen_users = seen_users

    @app.middleware("http")
    async def token_only(request: Request, call_next: Any) -> Any:
        if request.headers.get("x-senseai-proxy-token") != TOKEN:
            return JSONResponse({"detail": "no proxy token"}, 403)
        seen_users.append(request.headers.get("x-senseai-user", ""))
        return await call_next(request)

    @app.get("/api/research/start")
    def start() -> dict[str, Any]:
        return {
            "least_verified": [
                {
                    "claim_id": CLAIM,
                    "library_path": "felidae.senses.vision.detection_threshold",
                    "value": state["value"],
                    "status": "unverified" if not state["history"] else "extracted",
                    "why": "its source is abstract-only",
                    "species": "Felis catus",
                    "read_by": ["panther.frame.gain_lut"],
                },
                {
                    "claim_id": "lib:strigidae.senses.hearing.x",
                    "library_path": "strigidae.senses.hearing.x",
                    "value": "1",
                    "status": "unverified",
                    "why": "",
                    "species": None,
                    "read_by": [],
                },
            ],
            "open_questions": [
                {
                    "hypothesis_id": "hyp:request:felidae-vision-q-1",
                    "statement": "What is the cat's scotopic detection threshold?",
                    "priority": "high",
                    "target": "felidae.senses.vision.detection_threshold",
                    "read_by": [],
                }
            ],
        }

    @app.get("/api/research/claims/{claim_id:path}")
    def claim(claim_id: str) -> dict[str, Any]:
        return {
            "value": state["value"],
            "history": state["history"],
            "sources": [
                {
                    "source_id": "src:10.1152/jn.90641.2008",
                    "title": "Scotopic vision in the cat",
                    "authors": "Kang et al.",
                    "year": 2009,
                    "venue": "J Neurophysiol",
                    "doi": "10.1152/jn.90641.2008",
                    "link": "https://doi.org/10.1152/jn.90641.2008",
                    "full_text": True,
                    "checked": None,
                }
            ],
            "passage": None,
            "claim": {
                "id": claim_id,
                "library_path": "felidae.senses.vision.detection_threshold",
                "status": "unverified" if not state["history"] else "extracted",
                "species": "Felis catus",
                "conditions": "behavioural, scotopic",
                "method": "behavioural",
                "mapping": "close",
                "library_notes": None,
                "notes_by_reviewer": "",
                "unverified_reason": "abstract only",
                "revision": len(state["history"]),
            },
        }

    @app.get("/api/research/settings")
    def settings() -> dict[str, Any]:
        def svc(id_: str, need: str, state_: str, names: list[str]) -> dict[str, Any]:
            return {
                "id": id_,
                "name": id_.title(),
                "group": "Finding papers" if id_ != "anthropic" else "Assistant",
                "purpose": "What it is for.",
                "need": need,
                "without": "Slower.",
                "get_key": "https://example.org/key",
                "state": state_,
                "vars": [
                    {"name": n, "aliases": [], "secret": True, "set": state_ == "set"}
                    for n in names
                ],
                "checkable": True,
            }

        return {
            "groups": ["Assistant", "Finding papers"],
            "integrations": [
                svc("anthropic", "required", "set", ["ANTHROPIC_API_KEY"]),
                svc("openalex", "recommended", "not_set", ["OPENALEX_API_KEY"]),
            ],
            "where": "On Railway: the research service, Variables tab.",
        }

    @app.post("/api/research/settings/{sid}/check")
    def check(sid: str) -> dict[str, Any]:
        return {"id": sid, "ok": True, "detail": "working", "cached": False}

    @app.post("/api/research/conversations")
    def new(x_senseai_user: str | None = Header(None)) -> dict[str, str]:
        if not x_senseai_user:
            raise HTTPException(401, "no user")
        return {"id": "conv-1"}

    @app.get("/api/research/conversations/{cid}")
    def conv(cid: str) -> dict[str, Any]:
        return {"id": cid, "items": []}

    @app.post("/api/research/conversations/{cid}/messages")
    def messages(cid: str) -> StreamingResponse:
        turns = _turns()
        turn = turns[min(state["turn"], len(turns) - 1)]
        state["turn"] += 1

        def stream() -> Iterator[bytes]:
            for e in turn:
                yield f"event: {e['event']}\ndata: {json.dumps(e['data'])}\n\n".encode()

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/research/actions/{aid}/{decision}")
    async def decide(aid: str, decision: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        state["value"] = "-0.08 log10 re human"
        state["history"].append(
            {
                "revision": 1,
                "at": "2026-10-20T00:00:00Z",
                "by": "senseai",
                "summary": "value -0.74 → -0.08",
                "reason": body["rationale"],
            }
        )
        return {
            "message": "senseai approved it.",
            "action": {"id": aid, "kind": "claim_revision", "status": "approved", "card": {}},
        }

    return app
