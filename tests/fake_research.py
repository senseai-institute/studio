# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""A stand-in research service (research SPEC §8): conversations, an SSE reply, approvals.

Run: python tests/fake_research.py PORT. It echoes the focus and the X-SenseAI-User it saw, and
proposes one pending action, so the Research tab can be exercised without a model.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()
APPROVALS: list[dict[str, Any]] = []


@app.get("/api/research/health")
def health() -> dict[str, Any]:
    return {"ok": True, "fake": True}


@app.post("/api/research/conversations", status_code=201)
def conversation() -> dict[str, str]:
    return {"id": "c1"}


@app.post("/api/research/conversations/{cid}/messages")
async def message(cid: str, request: Request) -> StreamingResponse:
    body = await request.json()
    user = request.headers.get("x-senseai-user", "?")
    focus = (body.get("focus") or {}).get("library_path", "?")

    def sse(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    def stream() -> Any:
        yield sse("tool_call", {"name": "claim_get", "label": f"Reading {focus}"})
        yield sse("text_delta", {"text": f"(fake research) {user} asked about {focus}: "})
        yield sse("text_delta", {"text": body.get("text", "")})
        yield sse("pending_action", {"id": "a1", "summary": f"Propose a revision to {focus}"})
        yield sse("done", {})

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/research/actions/{aid}/{verb}")
async def act(aid: str, verb: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    APPROVALS.append(
        {
            "id": aid,
            "verb": verb,
            "rationale": body.get("rationale"),
            "user": request.headers.get("x-senseai-user"),
        }
    )
    return {"ok": True, "approvals": APPROVALS}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
