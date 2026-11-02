"""An ASGI test client for the console, small enough to read (PRD-v3 FR-7.1, NFR-4).

The console is an ASGI application, so the honest test calls it with a scope and collects the
messages it sends: no server, no port, no socket.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from lgbg.console.app import ConsoleApp


@dataclass(frozen=True, slots=True)
class Answer:
    """One ASGI response, decoded as a client would decode it."""

    status: int
    headers: dict[str, str]
    body: Any
    text: str


def call(
    app: ConsoleApp,
    method: str,
    target: str,
    *,
    raw_body: bytes = b"",
) -> Answer:
    split = urlsplit(target)
    incoming: list[dict[str, Any]] = [
        {"type": "http.request", "body": raw_body, "more_body": False}
    ]
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
        "headers": [],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 80),
        "state": {},
    }
    asyncio.run(app(scope, receive, send))

    start = next(message for message in sent if message["type"] == "http.response.start")
    headers = {key.decode().lower(): value.decode() for key, value in start.get("headers", [])}
    raw = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    text = raw.decode("utf-8", errors="replace")
    body: Any = None
    if headers.get("content-type", "").startswith("application/json"):
        body = json.loads(raw)
    return Answer(status=int(start["status"]), headers=headers, body=body, text=text)
