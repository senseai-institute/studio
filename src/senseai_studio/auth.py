# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""HTTP Basic auth for the whole app when ``VIEWER_PASSWORD`` is set.

Ported from ``senseai_viewer.auth`` (viewer@8106abf) so Studio and the viewer share one
password; the username is what the research proxy forwards as ``X-SenseAI-User`` (default
``senseai``). Plain ASGI middleware, so Server-Sent Events stream unbuffered.
"""

from __future__ import annotations

import base64
import binascii
import secrets
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

OPEN_PATHS = {"/api/studio/health", "/healthz"}
DEFAULT_USER = "senseai"


def credentials(header: str | None) -> tuple[str, str] | None:
    """``(user, password)`` from an ``Authorization: Basic …`` header."""
    if not header or not header.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    user, _, given = decoded.partition(":")
    return user, given


def password_ok(header: str | None, password: str) -> bool:
    """Whether an ``Authorization: Basic …`` header carries ``password``."""
    c = credentials(header)
    return c is not None and secrets.compare_digest(c[1].encode(), password.encode())


def user_of(header: str | None) -> str:
    """The Basic-auth user name, or ``senseai``."""
    c = credentials(header)
    return (c[0] if c and c[0] else DEFAULT_USER)[:64]


class BasicAuth:
    """Require the shared password on every HTTP request except :data:`OPEN_PATHS`."""

    def __init__(self, app: ASGIApp, password: str) -> None:
        self.app = app
        self.password = password

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass the request on if it is open or carries the password; else answer 401."""
        if scope["type"] != "http" or scope.get("path") in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        if password_ok(headers.get("authorization"), self.password):
            await self.app(scope, receive, send)
            return
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"www-authenticate", b'Basic realm="SenseAI", charset="UTF-8"'),
                    (b"content-type", b"text/plain; charset=utf-8"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"Password required."})
