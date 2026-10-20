# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""``/api/studio/research/*`` → ``RESEARCH_URL/api/research/*``, as research's SPEC §8/§10 asks.

Studio keeps auth and adds ``X-SenseAI-User`` (the signed-in name) and, when
``RESEARCH_PROXY_TOKEN`` is set, ``X-SenseAI-Proxy-Token``. The research service trusts the
name only from its own machine or with that token, so the token is what lets Studio reach it
over a network (Railway's private network). Headers of those names sent by the browser are
dropped, never forwarded. Server-Sent Events (the chat stream) pass through unbuffered.
Studio makes no model call of its own: this module only forwards bytes. The contract is
research's ``docs/API.md``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from senseai_studio.auth import user_of
from senseai_studio.settings import Settings

HOP = {
    "connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "proxy-authorization",
    "proxy-authenticate",
    "host",
    "content-length",
    "authorization",
    "content-encoding",
}  # aiter_bytes() decodes the body
OURS = {"x-senseai-user", "x-senseai-proxy-token"}  # set here only, never taken from the browser


def add_research_routes(
    app: FastAPI, cfg: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> None:
    """Register the proxy (always registered; answers 404 when ``RESEARCH_URL`` is unset)."""

    @app.api_route(
        "/api/studio/research/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def proxy(path: str, request: Request) -> Response:
        if not cfg.research_url:
            raise HTTPException(404, "research is not configured (RESEARCH_URL unset)")
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP | OURS}
        headers["X-SenseAI-User"] = user_of(request.headers.get("authorization"))
        if cfg.research_token:
            headers["X-SenseAI-Proxy-Token"] = cfg.research_token
        url = f"{cfg.research_url}/api/research/{path}"
        client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(30, read=None))
        req = client.build_request(
            request.method,
            url,
            params=request.query_params,
            headers=headers,
            content=await request.body(),
        )
        try:
            resp = await client.send(req, stream=True)
        except httpx.HTTPError as e:
            await client.aclose()
            raise HTTPException(502, f"research service unreachable: {e}") from e

        async def body() -> AsyncIterator[bytes]:
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()
                await client.aclose()

        out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in HOP}
        return StreamingResponse(
            body(),
            status_code=resp.status_code,
            headers=out_headers,
            media_type=resp.headers.get("content-type"),
        )
