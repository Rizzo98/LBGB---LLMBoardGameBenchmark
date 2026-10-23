"""The HTTP host: a JSON API over the one facade, written against ASGI (PRD-v2 FR-2).

The host is a transport and nothing else. It parses a request, names an operation of the facade,
and serialises the answer. It holds no game state and no rules: every read is a facade read and
every write is a facade write, which is what keeps HTTP, MCP and the in-process runner from
drifting into three different games (FR-1.4, SC-2).

**Two kinds of failure, kept apart (FR-2.3).** An illegal move is an answer from the engine: the
response is 200 and the body carries the rejection. A request that could not reach the engine - a
malformed body, an unknown session, the wrong method - is an HTTP error with a JSON body. A client
that cannot tell those apart cannot tell a bad model from a bad server.

**Routing is the ASGI interface, directly (FR-2.7).** There are six routes; a framework would be
another dependency, another request path and another thing to pin. The application is a callable
that reads the scope, drains the body, dispatches on method and path, and sends the two ASGI
messages a response is made of. A test calls it exactly that way, with no server or socket
(NFR-8).

**The version is in the body (FR-2.2).** Every response - success or failure - carries
`"schema": "lgbg.host.v1"`. A client can therefore refuse an answer it does not understand
without guessing from the status code.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.parse import parse_qs, unquote

from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import CORE_KEYS, ConfigError, RunConfig
from lgbg.core.game import Applied, GamePluginError
from lgbg.core.log import rejected_result
from lgbg.core.run import AmbiguousRequestError
from lgbg.core.types import Action, GameId, JsonValue, Observation, Outcome, PlayerId
from lgbg.host.facade import (
    SessionClosedError,
    SessionError,
    SessionExistsError,
    SessionFacade,
    SessionNotFoundError,
)
from lgbg.host.registry import InvalidSessionIdError, SessionRegistry

HOST_SCHEMA: Final[str] = "lgbg.host.v1"
"""The JSON schema version every response names (FR-2.2)."""

DEFAULT_PROTOCOL: Final[str] = "decline_only"

CONTENT_TYPE: Final[bytes] = b"application/json; charset=utf-8"

type Receive = Callable[[], Awaitable[dict[str, Any]]]
type Send = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class _Answer:
    """One response, before it becomes ASGI messages."""

    status: int
    payload: Mapping[str, JsonValue]
    headers: tuple[tuple[bytes, bytes], ...] = ()


class _RequestError(Exception):
    """A failure to understand the request, which becomes an HTTP error."""

    def __init__(self, status: int, kind: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.kind = kind


class HttpHost:
    """The ASGI application: routing over the facade, with a registry of live sessions."""

    def __init__(
        self,
        facade: SessionFacade | None = None,
        *,
        directory: Path | None = None,
    ) -> None:
        self._facade = SessionFacade() if facade is None else facade
        self._registry = SessionRegistry(self._facade)
        self._directory = directory

    @property
    def registry(self) -> SessionRegistry:
        """The live-session table, for a caller that already owns this application."""
        return self._registry

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        kind = scope.get("type")
        if kind == "lifespan":
            await self._lifespan(receive, send)
            return
        if kind != "http":
            raise RuntimeError(f"this application serves HTTP and lifespan, not {kind!r}")
        try:
            body = await _read_body(receive)
            answer = self._dispatch(scope, body)
        except _RequestError as error:
            answer = _error(error.status, error.kind, str(error))
        except InvalidSessionIdError as error:
            answer = _error(400, "invalid_request", str(error))
        except SessionNotFoundError as error:
            answer = _error(404, "not_found", str(error))
        except SessionExistsError as error:
            answer = _error(409, "conflict", str(error))
        except SessionClosedError as error:
            answer = _error(409, "conflict", str(error))
        except (AmbiguousRequestError, ConfigError, GamePluginError, ValueError) as error:
            answer = _error(400, "invalid_request", str(error))
        except SessionError as error:
            answer = _error(400, "invalid_request", str(error))
        await _send(send, answer)

    # --- routing ----------------------------------------------------------------------------

    def _dispatch(self, scope: dict[str, Any], body: bytes) -> _Answer:
        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", "/"))
        query = parse_qs(str(scope.get("query_string", b"").decode("utf-8", "replace")))
        segments = [unquote(segment) for segment in path.split("/") if segment]

        if segments == ["sessions"]:
            if method == "POST":
                return self._create(body)
            if method == "GET":
                return self._list()
            return _method_not_allowed("GET, POST")
        if len(segments) == 2 and segments[0] == "sessions":
            if method == "DELETE":
                return self._end(segments[1])
            return _method_not_allowed("DELETE")
        if len(segments) == 3 and segments[0] == "sessions":
            session_id, read = segments[1], segments[2]
            if read == "state" and method == "GET":
                return self._state(session_id, query)
            if read == "decisions" and method == "GET":
                return self._decisions(session_id)
            if read == "surface" and method == "GET":
                return self._surface(session_id, query)
            if read == "outcome" and method == "GET":
                return self._outcome(session_id)
            if read == "actions" and method == "POST":
                return self._act(session_id, body)
            if read in {"actions", "decisions", "outcome", "state", "surface"}:
                return _method_not_allowed("GET" if read != "actions" else "POST")
        raise _RequestError(404, "not_found", f"no route for {method} {path!r}")

    # --- lifecycle --------------------------------------------------------------------------

    def _create(self, body: bytes) -> _Answer:
        fields = _body(body)
        _only(
            fields,
            {
                "assist",
                "game",
                "game_config",
                "interaction_protocol",
                "players",
                "rejection_detail",
                "seed",
                "session_id",
            },
        )
        game = _string(fields, "game")
        requested = _string_optional(fields, "session_id")
        options = _mapping_or(fields, "game_config", {})
        shadowing = sorted(set(options) & CORE_KEYS)
        if shadowing:
            raise _RequestError(
                400,
                "invalid_request",
                f"game option(s) {shadowing} would shadow core configuration keys",
            )
        raw = {
            key: value
            for key, value in fields.items()
            if key not in {"game", "game_config", "session_id"}
        }
        raw.update(options)
        raw.setdefault("interaction_protocol", DEFAULT_PROTOCOL)
        # The core's own reader validates the run configuration. The host does not re-implement
        # that ladder, and in particular never names the assist enum: the level is parsed where
        # the core parses it, not in a transport.
        config = RunConfig.from_mapping(raw, game_option_keys=None)
        assigned = self._registry.create(game, config, game_id=requested, directory=self._directory)
        return _answer(201, {"session_id": assigned})

    def _list(self) -> _Answer:
        return _answer(
            200,
            {
                "sessions": [
                    {"session_id": entry.session_id, "game": entry.game}
                    for entry in self._registry.entries()
                ]
            },
        )

    def _end(self, session_id: GameId) -> _Answer:
        self._registry.end(session_id)
        return _answer(200, {"ok": True})

    # --- reads ------------------------------------------------------------------------------

    def _state(self, session_id: GameId, query: Mapping[str, list[str]]) -> _Answer:
        self._registry.game_of(session_id)
        player = _seat(query, "state")
        observation: Observation = self._facade.projection(session_id, player)
        return _answer(200, {"player": player, "state": observation})

    def _decisions(self, session_id: GameId) -> _Answer:
        self._registry.game_of(session_id)
        requests = self._facade.pending_decisions(session_id)
        return _answer(
            200,
            {
                "decisions": [
                    {
                        "request_id": request.request_id,
                        "player": request.player,
                        "kind": request.kind,
                        "schema_ref": request.schema_ref,
                        "context": request.context,
                        "phase": request.phase,
                    }
                    for request in requests
                ]
            },
        )

    def _surface(self, session_id: GameId, query: Mapping[str, list[str]]) -> _Answer:
        self._registry.game_of(session_id)
        player = _seat(query, "surface")
        return _answer(
            200,
            {"player": player, "surface": self._facade.decision_surface(session_id, player)},
        )

    def _outcome(self, session_id: GameId) -> _Answer:
        self._registry.game_of(session_id)
        outcome = self._facade.outcome(session_id)
        return _answer(200, {"outcome": None if outcome is None else _outcome(outcome)})

    # --- writes -----------------------------------------------------------------------------

    def _act(self, session_id: GameId, body: bytes) -> _Answer:
        self._registry.game_of(session_id)
        fields = _body(body)
        _only(fields, {"params", "player", "request_id", "type"})
        player = _integer(fields, "player")
        action_type = _string(fields, "type")
        params = _mapping_or(fields, "params", {})
        request_id = _string_optional(fields, "request_id")
        result = self._facade.submit_action(
            session_id,
            Action(player=player, type=action_type, params=params),
            request_id=request_id,
        )
        if isinstance(result, Applied):
            return _answer(
                200,
                {
                    "result": {
                        "ok": True,
                        "events": [
                            {"type": event.type, "payload": event.payload}
                            for event in result.events
                        ],
                    }
                },
            )
        return _answer(200, {"result": rejected_result(result.rejection)})

    # --- ASGI internals ---------------------------------------------------------------------

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return


# --- request parsing ---------------------------------------------------------------------


def _body(body: bytes) -> dict[str, Any]:
    """The request's JSON object, or a 400 that says why there is not one."""
    if not body:
        return {}
    try:
        parsed: Any = json.loads(body)
    except json.JSONDecodeError as error:
        raise _RequestError(400, "invalid_request", f"the body is not JSON: {error}") from None
    if not isinstance(parsed, Mapping):
        raise _RequestError(400, "invalid_request", "the body must be a JSON object")
    return dict(parsed)


def _only(fields: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise _RequestError(400, "invalid_request", f"unknown field(s) {unknown}")


def _string(fields: Mapping[str, Any], name: str) -> str:
    value = fields.get(name)
    if not isinstance(value, str) or not value:
        raise _RequestError(400, "invalid_request", f"{name} must be a non-empty string")
    return value


def _string_optional(fields: Mapping[str, Any], name: str) -> str | None:
    if name not in fields:
        return None
    return _string(fields, name)


def _integer(fields: Mapping[str, Any], name: str) -> int:
    value = fields.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise _RequestError(400, "invalid_request", f"{name} must be an integer")
    return value


def _mapping_or(
    fields: Mapping[str, Any], name: str, default: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    if name not in fields:
        return dict(default)
    value = fields[name]
    if not isinstance(value, Mapping):
        raise _RequestError(400, "invalid_request", f"{name} must be an object")
    return {str(key): item for key, item in value.items()}


def _seat(query: Mapping[str, list[str]], read: str) -> PlayerId:
    values = query.get("player")
    if not values:
        raise _RequestError(400, "invalid_request", f"a {read} read must name its seat")
    try:
        player = int(values[0])
    except ValueError:
        raise _RequestError(400, "invalid_request", "player must be an integer seat") from None
    if player < 0:
        raise _RequestError(400, "invalid_request", f"player {player} is not a seat")
    return player


# --- responses ---------------------------------------------------------------------------


def _answer(status: int, payload: Mapping[str, JsonValue]) -> _Answer:
    return _Answer(status=status, payload={"schema": HOST_SCHEMA, **payload})


def _error(status: int, kind: str, message: str) -> _Answer:
    return _answer(status, {"error": {"kind": kind, "message": message}})


def _method_not_allowed(allow: str) -> _Answer:
    return _Answer(
        status=405,
        payload={
            "schema": HOST_SCHEMA,
            "error": {"kind": "method_not_allowed", "message": f"use {allow}"},
        },
        headers=((b"allow", allow.encode()),),
    )


def _outcome(outcome: Outcome) -> dict[str, JsonValue]:
    return {
        "winner": outcome.winner,
        "scores": dict(outcome.scores),
        "rounds": outcome.rounds,
    }


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            raise _RequestError(400, "invalid_request", "the client disconnected mid-body")
        chunks.append(message.get("body", b""))
        if not message.get("more_body"):
            return b"".join(chunks)


async def _send(send: Send, answer: _Answer) -> None:
    body = to_canonical_json(answer.payload).encode()
    headers = [
        (b"content-type", CONTENT_TYPE),
        (b"content-length", str(len(body)).encode()),
        *answer.headers,
    ]
    await send({"type": "http.response.start", "status": answer.status, "headers": headers})
    await send({"type": "http.response.body", "body": body, "more_body": False})


__all__: list[str] = ["HOST_SCHEMA", "HttpHost"]
