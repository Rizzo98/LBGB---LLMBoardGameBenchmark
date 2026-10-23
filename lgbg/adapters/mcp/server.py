"""The MCP surface: generated tools and resources over the one facade (PRD-v2 FR-3).

The adapter is deliberately thin. It knows the shape the protocol asks for and nothing about any
game: every action tool comes from `lgbg.core.tools.tool_definitions`, which reads the plugin's
own declaration, and every observation resource is rendered by the plugin's own `render` method.
If a second game needed a line of code here, the plugin system would have failed.

**Tools act; resources read.** An action tool is an intent and is the only thing that reaches
`submit_action`. A resource read is a projection, a list of open decisions, or the rendered
decision surface, and all of them are pure reads in the facade (FR-3.8), so a client may re-read
without changing the game.

**Two profiles.** A benchmark surface is constructed for one live session and one seat. The
runner creates that session; the surface does not hold a lifecycle capability at all, so no
request can reach one. A sandbox surface is constructed for an operator and adds the lifecycle
tools, which are exactly the facade's own operations. The profile is chosen once, at construction
and never again (FR-3.4 to FR-3.4c).

**The assist level gates what the resources reveal.** At L0 the surface is the projection and a
refusal is a category. At L1 the decision surface and the pending decisions appear, as action
types, costs and parameter domains. At L2 the same surface carries the enumeration, and a refusal
carries the alternatives. The level is fixed when the process is built; no request can read or
move it (FR-4.1 to FR-4.4). The tools do not move at all (FR-3.3).

**Resource URIs are a shape, not a vocabulary.** `<game>://sessions/{id}/state?player=N`,
`<game>://sessions/{id}/decisions` and `<game>://sessions/{id}/surface?player=N` name a session,
a read and a seat - never a board, a piece or any other mechanic (FR-3.7).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, cast
from urllib.parse import parse_qs, unquote, urlsplit

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from lgbg.core.assist import rejection_view
from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import DEFAULT_DETAIL_FOR_ASSIST, AssistLevel, GameConfig, RunConfig
from lgbg.core.game import Applied, Game, get_game
from lgbg.core.run import AmbiguousRequestError
from lgbg.core.tools import DESCRIPTION, INPUT_SCHEMA, NAME, tool_definitions
from lgbg.core.types import Action, GameId, JsonValue, PlayerId
from lgbg.host.facade import SessionError, SessionFacade, SessionNotFoundError

PROFILE_BENCHMARK: Final[str] = "benchmark"
PROFILE_SANDBOX: Final[str] = "sandbox"
"""The two process profiles. A server is one of them for its whole life (FR-3.4)."""

LIFECYCLE_TOOLS: Final[frozenset[str]] = frozenset(
    {"create_session", "list_sessions", "end_session"}
)
"""The operator capabilities. A benchmark process never constructs these (FR-3.4a, FR-3.4b)."""

SESSION_ID: Final[str] = "session_id"
PLAYER: Final[str] = "player"
"""The two envelope fields a sandbox action needs; a benchmark surface binds them instead."""

STATE_RESOURCE: Final[str] = "state"
DECISIONS_RESOURCE: Final[str] = "decisions"
SURFACE_RESOURCE: Final[str] = "surface"
"""The sibling reads FR-3.6 names, spelled as path segments rather than mechanics.

`surface` is the rendered decision at the run's level: the domains at L1, the enumeration at L2.
`decisions` is the structured list of open requests that leads to it.
"""

DECISION_RESOURCES: Final[frozenset[str]] = frozenset({DECISIONS_RESOURCE, SURFACE_RESOURCE})
"""The reads L1 adds. L0 exposes the projection and nothing else (FR-4.1)."""

DEFAULT_DETAIL: Final[str] = "full"
DEFAULT_PROTOCOL: Final[str] = "decline_only"


class Profile(StrEnum):
    """Which surface this process serves. Fixed at construction, never a request value."""

    BENCHMARK = PROFILE_BENCHMARK
    SANDBOX = PROFILE_SANDBOX


_SESSION_ID_SCHEMA: Final[dict[str, Any]] = {
    "type": "string",
    "description": "The session this action answers.",
}
_PLAYER_SCHEMA: Final[dict[str, Any]] = {
    "type": "integer",
    "minimum": 0,
    "description": "The seat this action is played by.",
}
_ENVELOPE: Final[dict[str, Any]] = {
    SESSION_ID: _SESSION_ID_SCHEMA,
    PLAYER: _PLAYER_SCHEMA,
}


def build_server(
    facade: SessionFacade,
    game: str,
    *,
    profile: Profile,
    session_id: GameId | None = None,
    player: PlayerId | None = None,
    assist: AssistLevel = AssistLevel.L1,
    detail: str = DEFAULT_DETAIL,
    directory: Path | None = None,
) -> McpSurface:
    """Build one MCP server over the facade, fixed to one profile (FR-3.4).

    A benchmark surface must name the session and seat it serves: the runner creates the game,
    and the process a model talks to has no way to create another. A sandbox surface names
    neither and gets the lifecycle tools instead.
    """
    if profile is Profile.BENCHMARK and (session_id is None or player is None):
        raise ValueError("a benchmark surface must be bound to a session and a seat")
    if profile is Profile.SANDBOX and (session_id is not None or player is not None):
        raise ValueError("a sandbox surface owns its sessions; it must not be bound to one")
    return McpSurface(
        facade,
        game,
        profile=profile,
        session_id=session_id,
        player=player,
        assist=assist,
        detail=detail,
        directory=directory,
    )


class McpSurface:
    """One MCP server: the protocol handlers, the fixed profile, and the facade they reach."""

    def __init__(
        self,
        facade: SessionFacade,
        game: str,
        *,
        profile: Profile,
        session_id: GameId | None,
        player: PlayerId | None,
        assist: AssistLevel,
        detail: str,
        directory: Path | None,
    ) -> None:
        self._profile = profile
        self.game = game
        self.server: Server[Any, Any] = Server(
            name=f"lgbg-{game}-{profile.value}",
            instructions=(
                "Read the game through its resources and act through its tools. A refusal is an "
                "answer, not a failure: read it and decide again."
            ),
        )
        self._facade = facade
        self._plugin: Game = get_game(game)
        self._session_id = session_id
        self._player = player
        self._assist = assist
        self._rejection_detail = DEFAULT_DETAIL_FOR_ASSIST[assist]
        self._detail = detail
        self._directory = directory
        self._known_players: dict[GameId, list[int]] = {}
        if session_id is not None:
            self._known_players[session_id] = [int(player)] if player is not None else []
        self._actions = _action_tools(self._plugin, enveloped=profile is Profile.SANDBOX)
        self._action_names = frozenset(tool.name for tool in self._actions)
        self._tools = tuple(self._actions) + (
            tuple(_lifecycle_tools()) if profile is Profile.SANDBOX else ()
        )
        self._install()

    @property
    def profile(self) -> Profile:
        """The profile this server was constructed with. There is no setter by design."""
        return self._profile

    # --- protocol wiring --------------------------------------------------------------------

    def _install(self) -> None:
        self.server.list_tools()(self._list_tools)  # type: ignore[no-untyped-call]
        self.server.call_tool()(self._call_tool)
        self.server.list_resources()(self._list_resources)  # type: ignore[no-untyped-call]
        self.server.read_resource()(self._read_resource)  # type: ignore[no-untyped-call]

    async def _list_tools(self) -> list[types.Tool]:
        return list(self._tools)

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        if name in LIFECYCLE_TOOLS:
            if self.profile is not Profile.SANDBOX:
                return _error(f"tool {name!r} is not served by this profile")
            return self._lifecycle(name, arguments)
        if name not in self._action_names:
            return _error(f"tool {name!r} is not served by this surface")
        return self._act(name, arguments)

    async def _list_resources(self) -> list[types.Resource]:
        resources: list[types.Resource] = []
        for game_id in sorted(self._known_players):
            for player in self._known_players[game_id]:
                resources.append(
                    types.Resource(
                        name=f"{game_id} state for seat {player}",
                        uri=cast("Any", _uri(self.game, game_id, STATE_RESOURCE, player=player)),
                        mimeType="text/plain",
                    )
                )
            if self._assist is AssistLevel.L0:
                continue
            resources.append(
                types.Resource(
                    name=f"{game_id} pending decisions",
                    uri=cast("Any", _uri(self.game, game_id, DECISIONS_RESOURCE)),
                    mimeType="application/json",
                )
            )
            for player in self._known_players[game_id]:
                resources.append(
                    types.Resource(
                        name=f"{game_id} decision surface for seat {player}",
                        uri=cast("Any", _uri(self.game, game_id, SURFACE_RESOURCE, player=player)),
                        mimeType="text/plain",
                    )
                )
        return resources

    async def _read_resource(self, uri: Any) -> str:
        parsed = urlsplit(str(uri))
        if parsed.scheme != self.game:
            raise _invalid(f"resource scheme must be {self.game!r}, got {parsed.scheme!r}")
        if parsed.netloc != "sessions":
            raise _invalid("a resource URI must name sessions")
        segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
        if len(segments) != 2:
            raise _invalid(f"resource path must be sessions/{{id}}/{{read}}, got {parsed.path!r}")
        game_id, read = segments
        if read in DECISION_RESOURCES and self._assist is AssistLevel.L0:
            raise _invalid(f"resource {read!r} is not served at this assist level")
        if read == STATE_RESOURCE:
            return self._read_state(game_id, parse_qs(parsed.query))
        if read == DECISIONS_RESOURCE:
            return self._read_decisions(game_id)
        if read == SURFACE_RESOURCE:
            return self._read_surface(game_id, parse_qs(parsed.query))
        raise _invalid(f"resource {read!r} is not served by this surface")

    # --- actions ----------------------------------------------------------------------------

    def _act(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        parameters = dict(arguments)
        if self._session_id is None:
            game_id = parameters.pop(SESSION_ID, None)
            player = parameters.pop(PLAYER, None)
            if not isinstance(game_id, str):
                return _error("a sandbox action must name its session")
            if not isinstance(player, int) or isinstance(player, bool):
                return _error("a sandbox action must name its seat")
        else:
            game_id = self._session_id
            player = self._player
        if player is None:
            return _error("this surface has no seat to act as")
        try:
            result = self._facade.submit_action(
                game_id, Action(player=player, type=name, params=parameters)
            )
        except AmbiguousRequestError as error:
            return _error(str(error))
        except SessionError as error:
            return _error(str(error))
        if isinstance(result, Applied):
            events: list[JsonValue] = [
                {"type": event.type, "payload": dict(event.payload)} for event in result.events
            ]
            return _answer({"ok": True, "events": events})
        return _answer(rejection_view(result.rejection, detail=self._rejection_detail))

    # --- lifecycle --------------------------------------------------------------------------

    def _lifecycle(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        if name == "create_session":
            return self._create_session(arguments)
        if name == "list_sessions":
            return _answer({"ok": True, "sessions": list(self._facade.list_sessions())})
        if name == "end_session":
            game_id = arguments.get(SESSION_ID)
            if not isinstance(game_id, str):
                return _error("end_session must name a session")
            try:
                self._facade.end_session(game_id)
            except SessionNotFoundError as error:
                return _error(str(error))
            self._known_players.pop(game_id, None)
            return _answer({"ok": True})
        return _error(f"unknown lifecycle tool {name!r}")

    def _create_session(self, arguments: dict[str, Any]) -> types.CallToolResult:
        seed = arguments.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool):
            return _error("create_session must name an integer seed")
        players = arguments.get("players", 4)
        if not isinstance(players, int) or isinstance(players, bool) or players < 2:
            return _error("players must be an integer of at least 2")
        protocol = arguments.get("interaction_protocol", DEFAULT_PROTOCOL)
        if not isinstance(protocol, str):
            return _error("interaction_protocol must be a string")
        raw_options = arguments.get("game_config", {})
        if not isinstance(raw_options, Mapping):
            return _error("game_config must be an object")
        options = cast("dict[str, JsonValue]", dict(raw_options))
        requested_id = arguments.get(SESSION_ID)
        if requested_id is not None and not isinstance(requested_id, str):
            return _error("session_id must be a string")
        try:
            game_id = self._facade.create_session(
                self.game,
                RunConfig(
                    seed=seed,
                    players=players,
                    interaction_protocol=protocol,
                    assist=self._assist,
                    game_config=GameConfig(options),
                ),
                game_id=requested_id,
                directory=self._directory,
            )
        except (SessionError, ValueError) as error:
            return _error(str(error))
        self._known_players[game_id] = list(range(players))
        return _answer({"ok": True, SESSION_ID: game_id})

    # --- resources --------------------------------------------------------------------------

    def _read_state(self, game_id: GameId, query: dict[str, list[str]]) -> str:
        player = self._seat(query, missing="a state resource must name its seat")
        observation = self._facade.projection(game_id, player)
        return self._plugin.render(observation, detail=self._detail)

    def _read_surface(self, game_id: GameId, query: dict[str, list[str]]) -> str:
        """The rendered decision at the level this process was built for (FR-4.2, FR-4.3)."""
        player = self._seat(query, missing="a surface resource must name its seat")
        return self._facade.decision_surface(game_id, player)

    def _seat(self, query: dict[str, list[str]], *, missing: str) -> PlayerId:
        """The seat a per-player read names, defaulting to the bound one.

        A benchmark surface is bound to one seat and may read no other; a sandbox surface names
        the seat in the URI. The distinction is the profile's, not the request's.
        """
        values = query.get(PLAYER)
        if values is None:
            if self._player is None:
                raise _invalid(missing)
            return self._player
        try:
            player = int(values[0])
        except (IndexError, ValueError):
            raise _invalid("player must be an integer seat") from None
        if self._player is not None and player != self._player:
            raise _invalid("this surface may only read its own seat's projection")
        return player

    def _read_decisions(self, game_id: GameId) -> str:
        requests = self._facade.pending_decisions(game_id)
        if self._player is not None:
            requests = [request for request in requests if request.player == self._player]
        payload = [
            {
                "request_id": request.request_id,
                "player": request.player,
                "kind": request.kind,
                "schema_ref": request.schema_ref,
                "context": dict(request.context),
                "phase": request.phase,
            }
            for request in requests
        ]
        return to_canonical_json(payload)


async def serve_stdio(server: Server[Any, Any]) -> None:
    """Serve one existing server over stdin/stdout, one client per process (FR-3.5)."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


# --- generated definitions -----------------------------------------------------------------


def _action_tools(game: Game, *, enveloped: bool) -> list[types.Tool]:
    """The v1 generator's answer, translated into the protocol's Tool shape and nothing more."""
    tools: list[types.Tool] = []
    for definition in tool_definitions(game):
        name = definition[NAME]
        description = definition[DESCRIPTION]
        schema = cast("dict[str, Any]", copy.deepcopy(definition[INPUT_SCHEMA]))
        if not isinstance(name, str) or not isinstance(description, str):
            raise ValueError("a generated tool definition must name and describe its action")
        tools.append(
            types.Tool(
                name=name,
                description=description,
                inputSchema=_with_envelope(schema) if enveloped else schema,
            )
        )
    return tools


def _with_envelope(schema: dict[str, Any]) -> dict[str, Any]:
    """Add the two sandbox fields without changing the action's declared shape.

    An action with one object schema gains the fields in its own properties. An action with a
    union of shapes gains them in each branch, because adding them at the top would be a field
    the branch then refuses under its own closed `additionalProperties`.
    """
    branches = schema.get("oneOf")
    if isinstance(branches, list):
        return {
            **schema,
            "oneOf": [
                _with_envelope(cast("dict[str, Any]", branch))
                for branch in branches
                if isinstance(branch, dict)
            ],
        }
    properties = schema.get("properties")
    merged = dict(properties) if isinstance(properties, dict) else {}
    merged.update(_ENVELOPE)
    required = schema.get("required")
    names = list(required) if isinstance(required, list) else []
    for field in _ENVELOPE:
        if field not in names:
            names.append(field)
    return {**schema, "properties": merged, "required": names}


def _lifecycle_tools() -> list[types.Tool]:
    """The three operator capabilities, built only for the sandbox profile."""
    return [
        types.Tool(
            name="create_session",
            description="Open a game in this process and return its session id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "seed": {"type": "integer", "description": "The seed the run starts from."},
                    "players": {
                        "type": "integer",
                        "minimum": 2,
                        "description": "The number of seats.",
                    },
                    "interaction_protocol": {
                        "type": "string",
                        "description": "The interaction protocol the run records.",
                    },
                    "game_config": {
                        "type": "object",
                        "description": "Options declared by the game and carried opaquely.",
                    },
                    SESSION_ID: {
                        "type": "string",
                        "description": "An id to record the game under; assigned when omitted.",
                    },
                },
                "required": ["seed"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="list_sessions",
            description="List the sessions open in this process.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        types.Tool(
            name="end_session",
            description="Close an open session and its record.",
            inputSchema={
                "type": "object",
                "properties": {SESSION_ID: _SESSION_ID_SCHEMA},
                "required": [SESSION_ID],
                "additionalProperties": False,
            },
        ),
    ]


# --- protocol answers ----------------------------------------------------------------------


def _answer(payload: dict[str, Any]) -> types.CallToolResult:
    """A normal answer: the engine spoke, and its answer is the tool result."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=to_canonical_json(payload))],
        structuredContent=payload,
        isError=False,
    )


def _error(message: str) -> types.CallToolResult:
    """A transport-level failure: the call could not reach the engine at all."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)],
        structuredContent={"ok": False, "error": message},
        isError=True,
    )


def _uri(game: str, game_id: GameId, read: str, *, player: PlayerId | None = None) -> str:
    base = f"{game}://sessions/{game_id}/{read}"
    return base if player is None else f"{base}?player={player}"


def _invalid(message: str) -> McpError:
    return McpError(ErrorData(code=types.INVALID_PARAMS, message=message))
