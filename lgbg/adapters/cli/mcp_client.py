"""A generic MCP client: it asks the server what exists and never names a game (PRD-v2 SC-6).

This is the surface's honest test, not a convenience wrapper. It discovers the tools with
`tools/list`, discovers the reads with `list_resources`, and turns the first open decision into a
tool call whose action name and parameters both come from the server. There is no table of games,
actions, pieces or coordinates here; if a second game needed a line in this file, plug-and-play
would not be real.

The client is deliberately small. It creates a session through the lifecycle tool the sandbox
serves, reads one projection through the advertised resource, and acts once on a decision. A
scripted full game (K-009) is the same primitives in a loop.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

from mcp import types
from mcp.client.session import ClientSession

LIFECYCLE_TOOLS: Final[frozenset[str]] = frozenset(
    {"create_session", "list_sessions", "end_session"}
)
"""Names owned by the protocol's profile, not by any game (PRD-v2 FR-3.4)."""

STATE_RESOURCE: Final[str] = "state"
DECISIONS_RESOURCE: Final[str] = "decisions"
"""The two reads the server advertises (PRD-v2 FR-3.6, FR-3.7)."""

SESSION_FIELD: Final[str] = "session_id"
PLAYER_FIELD: Final[str] = "player"


class ClientError(RuntimeError):
    """The server answered in a way this generic client cannot use."""


class GameClient:
    """One MCP connection, used without any knowledge of the game behind it."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._tools: dict[str, types.Tool] = {}
        self._resources: list[types.Resource] = []
        self._discovered = False

    @property
    def tool_names(self) -> frozenset[str]:
        """The tools the server served, which is the only vocabulary the client has."""
        return frozenset(self._tools)

    async def discover(self) -> None:
        """Read the server's two declarations: what it can do, and what it can show."""
        self._tools = {tool.name: tool for tool in (await self._session.list_tools()).tools}
        self._resources = list((await self._session.list_resources()).resources)
        self._discovered = True

    async def create_session(
        self,
        *,
        seed: int,
        players: int,
        extra: Mapping[str, Any] | None = None,
    ) -> str:
        """Open a session through the lifecycle tool the server advertised."""
        await self._ensure_discovered()
        if "create_session" not in self._tools:
            raise ClientError("this server serves no create_session tool")
        arguments: dict[str, Any] = {"seed": seed, "players": players}
        if extra is not None:
            arguments.update(extra)
        result = await self._session.call_tool("create_session", arguments)
        payload = self._payload(result)
        game_id = payload.get(SESSION_FIELD)
        if not isinstance(game_id, str):
            raise ClientError("create_session returned no session id")
        await self._refresh_resources()
        return game_id

    async def read_projection(self, session_id: str, *, player: int) -> str:
        """Read the projection resource the server advertised for that session and seat."""
        await self._ensure_discovered()
        uri = self._resource_uri(session_id, STATE_RESOURCE, player=player)
        return await self._read_text(uri)

    async def decisions(self, session_id: str) -> list[dict[str, Any]]:
        """All open decisions, read from the resource the server advertised."""
        await self._ensure_discovered()
        uri = self._resource_uri(session_id, DECISIONS_RESOURCE)
        payload = json.loads(await self._read_text(uri))
        if not isinstance(payload, list):
            raise ClientError("the decisions resource is not a list")
        decisions: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise ClientError("a decision is not an object")
            decisions.append(item)
        return decisions

    async def next_decision(self, session_id: str) -> dict[str, Any] | None:
        """The first open decision, read from the resource rather than guessed from the state."""
        decisions = await self.decisions(session_id)
        return decisions[0] if decisions else None

    async def act(self, session_id: str, decision: Mapping[str, Any]) -> types.CallToolResult:
        """Turn one decision into one tool call, with arguments sampled from the tool's schema."""
        await self._ensure_discovered()
        tool = self._tool_for(decision)
        player = decision.get(PLAYER_FIELD)
        if not isinstance(player, int) or isinstance(player, bool):
            raise ClientError("the decision names no seat")
        arguments = _arguments_for(tool.inputSchema, session_id=session_id, player=player)
        return await self._session.call_tool(tool.name, arguments)

    async def submit(
        self,
        session_id: str,
        *,
        action: str,
        player: int,
        params: Mapping[str, Any] | None = None,
    ) -> types.CallToolResult:
        """Call one named action tool exactly as the server declared it."""
        await self._ensure_discovered()
        tool = self._tools.get(action)
        if tool is None:
            raise ClientError(f"the server serves no {action!r} tool")
        shape = _first_shape(tool.inputSchema)
        properties = shape.get("properties")
        arguments: dict[str, Any] = dict(params or {})
        if isinstance(properties, Mapping):
            if SESSION_FIELD in properties:
                arguments[SESSION_FIELD] = session_id
            if PLAYER_FIELD in properties:
                arguments[PLAYER_FIELD] = player
        return await self._session.call_tool(tool.name, arguments)

    async def end_session(self, session_id: str) -> None:
        """Close the session through the advertised lifecycle tool, if it is still open."""
        await self._ensure_discovered()
        if "end_session" not in self._tools:
            raise ClientError("this server serves no end_session tool")
        self._payload(await self._session.call_tool("end_session", {SESSION_FIELD: session_id}))

    # --- discovery helpers --------------------------------------------------------------------

    async def _ensure_discovered(self) -> None:
        if not self._discovered:
            await self.discover()

    async def _refresh_resources(self) -> None:
        self._resources = list((await self._session.list_resources()).resources)

    def _tool_for(self, decision: Mapping[str, Any]) -> types.Tool:
        schema_ref = decision.get("schema_ref")
        if isinstance(schema_ref, str):
            tool = self._tools.get(schema_ref)
            if tool is not None:
                return tool
        for name, tool in self._tools.items():
            if name not in LIFECYCLE_TOOLS:
                return tool
        raise ClientError("the server serves no action tool")

    def _resource_uri(self, session_id: str, read: str, *, player: int | None = None) -> str:
        for resource in self._resources:
            parsed = urlsplit(str(resource.uri))
            segments = [segment for segment in parsed.path.split("/") if segment]
            if parsed.netloc != "sessions" or len(segments) != 2:
                continue
            if segments[0] != session_id or segments[1] != read:
                continue
            if player is not None and parse_qs(parsed.query).get(PLAYER_FIELD) != [str(player)]:
                continue
            return str(resource.uri)
        seat = "" if player is None else f" for seat {player}"
        raise ClientError(f"the server advertises no {read!r} resource{seat}")

    async def _read_text(self, uri: str) -> str:
        result = await self._session.read_resource(uri)  # type: ignore[arg-type]
        content = result.contents[0]
        if not isinstance(content, types.TextResourceContents):
            raise ClientError("the resource is not text")
        return content.text

    @staticmethod
    def _payload(result: types.CallToolResult) -> Mapping[str, Any]:
        if result.isError:
            text = " ".join(
                item.text for item in result.content if isinstance(item, types.TextContent)
            )
            raise ClientError(text or "the tool call failed")
        payload = result.structuredContent
        if not isinstance(payload, Mapping):
            raise ClientError("the tool returned no structured answer")
        return payload


def _arguments_for(schema: Mapping[str, Any], *, session_id: str, player: int) -> dict[str, Any]:
    """Build the minimal arguments the schema requires, with no game fact in this module."""
    shape = _first_shape(schema)
    properties = shape.get("properties")
    required = shape.get("required")
    if not isinstance(properties, Mapping) or not isinstance(required, list):
        raise ClientError("an action tool declares no object schema")
    arguments: dict[str, Any] = {}
    for name in required:
        if not isinstance(name, str):
            continue
        if name == SESSION_FIELD:
            arguments[name] = session_id
        elif name == PLAYER_FIELD:
            arguments[name] = player
        else:
            declared = properties.get(name)
            if not isinstance(declared, Mapping):
                raise ClientError(f"the action tool declares no shape for {name!r}")
            arguments[name] = _sample(declared)
    return arguments


def _first_shape(schema: Mapping[str, Any]) -> Mapping[str, Any]:
    alternatives = schema.get("oneOf")
    if isinstance(alternatives, list):
        for branch in alternatives:
            if isinstance(branch, Mapping):
                return branch
    return schema


def _sample(schema: Mapping[str, Any]) -> Any:
    """One value a schema permits, chosen without knowing what the value means."""
    if "const" in schema:
        return schema["const"]
    if "default" in schema:
        return schema["default"]
    values = schema.get("enum")
    if isinstance(values, list) and values:
        return values[0]
    alternatives = schema.get("oneOf")
    if isinstance(alternatives, list):
        for branch in alternatives:
            if isinstance(branch, Mapping):
                return _sample(branch)
    kind = schema.get("type")
    if kind == "integer":
        minimum = schema.get("minimum")
        return int(minimum) if isinstance(minimum, int) and not isinstance(minimum, bool) else 0
    if kind == "number":
        minimum = schema.get("minimum")
        return minimum if isinstance(minimum, int | float) else 0
    if kind == "boolean":
        return False
    if kind == "string":
        length = schema.get("minLength")
        return "a" * int(length) if isinstance(length, int) and length > 0 else ""
    if kind == "object":
        properties = schema.get("properties")
        required = schema.get("required")
        if not isinstance(properties, Mapping):
            return {}
        if not isinstance(required, list):
            return {}
        return {
            str(name): _sample(properties[name])
            for name in required
            if isinstance(name, str) and isinstance(properties.get(name), Mapping)
        }
    if kind == "array":
        return []
    return None
