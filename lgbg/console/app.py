"""The console's read-only ASGI application (PRD-v3 FR-7, FR-8.4, FR-12.4).

Two surfaces, one application:

- ``/api/...`` answers JSON. Every body, success or failure, carries ``"schema": "lgbg.console.v1"``
  so a client can refuse an answer it does not understand without guessing from the status code.
  A record that does not verify is a **200 finding**; only a request that could not be understood
  is a 4xx.
- Everything else is the browser client: ``index.html`` at ``/`` and the hashed assets Vite emits.
  There is no history-mode fallback, because the client keeps its state in the URL fragment.

The application imports neither ``lgbg.host`` nor any game. It reads records through
:class:`LogStore` and verifies them through the core's replay layer; the game is resolved from the
record's own header by name. That is what keeps the console a consumer of the record rather than a
second engine.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote

from lgbg import __version__
from lgbg.console.records import (
    ConsoleError,
    InvalidLogIdError,
    LogEntry,
    LogStore,
    LogSummary,
    UnknownLogError,
    read_summary,
)
from lgbg.core.canonical import to_canonical_json
from lgbg.core.types import JsonValue

CONSOLE_SCHEMA: Final[str] = "lgbg.console.v1"
"""The JSON schema every API response names (FR-7.1)."""

JSON_CONTENT_TYPE: Final[str] = "application/json; charset=utf-8"
TEXT_CONTENT_TYPE: Final[str] = "text/plain; charset=utf-8"
MISSING_BUILD: Final[str] = (
    "the frontend build is missing; run `pnpm --dir web build` and start the console again"
)

type Receive = Callable[[], Awaitable[dict[str, Any]]]
type Send = Callable[[dict[str, Any]], Awaitable[None]]


class ConsoleApp:
    """The ASGI application. Construction resolves nothing; every read is a request."""

    def __init__(self, store: LogStore, dist: Path) -> None:
        self._store = store
        self._dist = dist
        self._index = dist / "index.html"

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await _lifespan(receive, send)
            return
        if scope["type"] != "http":
            return

        method = str(scope["method"]).upper()
        segments = [unquote(part) for part in str(scope["path"]).split("/") if part]
        if segments[:1] == ["api"]:
            await self._api(method, segments, send)
        else:
            await self._static(method, segments, send)

    async def _api(self, method: str, segments: Sequence[str], send: Send) -> None:
        if method != "GET":
            await _send_json(
                send,
                405,
                _error("method_not_allowed", "the console API is read-only"),
                extra=((b"allow", b"GET"),),
            )
            return
        if segments == ["api", "health"]:
            await _send_json(send, 200, self._health())
            return
        if segments == ["api", "logs"]:
            await _send_json(send, 200, self._logs())
            return
        if len(segments) == 3 and segments[:2] == ["api", "logs"]:
            await self._open(segments[2], send)
            return
        await _send_json(send, 404, _error("not_found", "no such console route"))

    async def _open(self, handle: str, send: Send) -> None:
        try:
            entry = self._store.resolve(handle)
        except InvalidLogIdError as error:
            await _send_json(send, 400, _error("invalid_log", str(error)))
            return
        except UnknownLogError as error:
            await _send_json(send, 404, _error("unknown_log", str(error)))
            return
        except ConsoleError as error:
            await _send_json(send, 500, _error("console_error", str(error)))
            return
        await _send_json(send, 200, _summary_payload(read_summary(entry)))

    def _health(self) -> dict[str, JsonValue]:
        return {
            "schema": CONSOLE_SCHEMA,
            "ok": True,
            "name": "lgbg-console",
            "version": __version__,
        }

    def _logs(self) -> dict[str, JsonValue]:
        rows: list[JsonValue] = [_entry_payload(entry) for entry in self._store.entries()]
        return {"schema": CONSOLE_SCHEMA, "logs": rows}

    async def _static(self, method: str, segments: Sequence[str], send: Send) -> None:
        if method != "GET":
            await _send(
                send,
                405,
                b"the console serves GET requests only\n",
                TEXT_CONTENT_TYPE,
                extra=((b"allow", b"GET"),),
            )
            return
        if not self._index.is_file():
            await _send(send, 503, (MISSING_BUILD + "\n").encode(), TEXT_CONTENT_TYPE)
            return
        if not segments:
            await self._send_file(self._index, send, cache="no-cache")
            return
        candidate = self._dist.joinpath(*segments)
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._dist.resolve()) or not resolved.is_file():
            await _send(send, 404, b"not found\n", TEXT_CONTENT_TYPE)
            return
        cache = "public, max-age=31536000, immutable" if segments[0] == "assets" else "no-cache"
        await self._send_file(resolved, send, cache=cache)

    async def _send_file(self, path: Path, send: Send, *, cache: str) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript",):
            content_type += "; charset=utf-8"
        await _send(
            send,
            200,
            path.read_bytes(),
            content_type,
            extra=((b"cache-control", cache.encode()),),
        )


def _entry_payload(entry: LogEntry) -> dict[str, JsonValue]:
    return {
        "log": entry.id,
        "game": entry.game,
        "rules_version": entry.rules_version,
        "problem": entry.problem,
    }


def _summary_payload(summary: LogSummary) -> dict[str, JsonValue]:
    failure: JsonValue = None
    if summary.failure is not None:
        failure = {
            "kind": summary.failure.kind,
            "seq": summary.failure.seq,
            "detail": summary.failure.detail,
        }
    return {
        "schema": CONSOLE_SCHEMA,
        "log": summary.id,
        "game": summary.game,
        "rules_version": summary.rules_version,
        "schema_version": summary.schema_version,
        "engine_version": summary.engine_version,
        "actions": summary.actions,
        "rejections": summary.rejections,
        "verified": summary.verified,
        "completed": summary.completed,
        "terminal_hash": summary.terminal_hash,
        "failure": failure,
    }


def _error(code: str, message: str) -> dict[str, JsonValue]:
    detail: dict[str, JsonValue] = {"code": code, "message": message}
    return {"schema": CONSOLE_SCHEMA, "ok": False, "error": detail}


async def _send_json(
    send: Send,
    status: int,
    payload: Mapping[str, JsonValue],
    *,
    extra: Sequence[tuple[bytes, bytes]] = (),
) -> None:
    body = to_canonical_json(payload).encode("utf-8")
    await _send(send, status, body, JSON_CONTENT_TYPE, extra=extra)


async def _send(
    send: Send,
    status: int,
    body: bytes,
    content_type: str,
    *,
    extra: Sequence[tuple[bytes, bytes]] = (),
) -> None:
    headers = [
        (b"content-type", content_type.encode()),
        (b"content-length", str(len(body)).encode()),
        *extra,
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _lifespan(receive: Receive, send: Send) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


__all__ = ["CONSOLE_SCHEMA", "ConsoleApp"]
