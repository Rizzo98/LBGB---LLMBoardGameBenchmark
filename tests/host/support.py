"""An ASGI test client small enough to read (PRD-v2 FR-2.7, NFR-8).

The host is an ASGI application, so the honest test calls it with a scope and collects the
messages it sends. No server, no port, no socket: the application is the interface.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from lgbg.core.canonical import to_canonical_json
from lgbg.host.http import HttpHost

BODY = "body"


@dataclass(frozen=True, slots=True)
class Answer:
    """One ASGI response, decoded as a client would decode it."""

    status: int
    headers: dict[str, str]
    body: Any


def call(
    app: HttpHost,
    method: str,
    target: str,
    *,
    json_body: Any = None,
    raw_body: bytes | None = None,
) -> Answer:
    """Drive the application with one ASGI HTTP request."""
    split = urlsplit(target)
    payload = (
        raw_body
        if raw_body is not None
        else (b"" if json_body is None else to_canonical_json(json_body).encode())
    )
    incoming: list[dict[str, Any]] = [{"type": "http.request", BODY: payload, "more_body": False}]
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return incoming.pop(0) if incoming else {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": split.path,
        "raw_path": split.path.encode(),
        "query_string": split.query.encode(),
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 80),
        "state": {},
    }
    asyncio.run(app(scope, receive, send))

    start = next(message for message in sent if message["type"] == "http.response.start")
    headers = {key.decode().lower(): value.decode() for key, value in start.get("headers", [])}
    body = b"".join(
        message.get(BODY, b"") for message in sent if message["type"] == "http.response.body"
    )
    return Answer(status=int(start["status"]), headers=headers, body=json.loads(body))
