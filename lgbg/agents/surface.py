"""The agent's surface: the generated tools, the reads, and the one action path (FR-6.2, FR-6.6).

The tool loop must not know a game, a transport or a provider. It needs three things: the tools the
model may call, a way to read one of them, and a way to submit an action. This module declares that
small protocol and implements it over the session facade - the same authority every other surface
uses (K-003, K-013).

The action tools are not written here. They come from the plugin's own declaration through
core.tools.tool_definitions, which is the generator the MCP server also uses, so the benchmark
surface and the agent surface cannot disagree about an action's name, description or schema.

The read tools are protocol capabilities, not game facts: read_state, read_decisions and
read_surface map one-to-one onto the facade's pure reads. They exist because the provider seam
carries tools, not resource URIs; the loop still only offers them when the caller configured reads
(FR-6.6). A read is executed only when the model asks for it - the loop never re-reads state on the
model's behalf.

A benchmark surface is bound to one session and one seat, exactly like the benchmark MCP profile:
the model cannot choose another seat or open another game.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from lgbg.agents.providers.base import ToolCall, ToolSpec
from lgbg.core.canonical import to_canonical_json
from lgbg.core.errors import Rejection
from lgbg.core.game import Applied, Game, get_game
from lgbg.core.run import AmbiguousRequestError
from lgbg.core.tools import tool_definitions
from lgbg.core.types import Action, GameId, JsonValue, PlayerId
from lgbg.host.facade import SessionError, SessionFacade

READ_STATE: Final[str] = "read_state"
READ_DECISIONS: Final[str] = "read_decisions"
READ_SURFACE: Final[str] = "read_surface"
READ_TOOLS: Final[frozenset[str]] = frozenset({READ_STATE, READ_DECISIONS, READ_SURFACE})
"""The three reads an agent may ask for, named as protocol capabilities rather than game nouns."""

_READ_SCHEMA: Final[Mapping[str, JsonValue]] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class ToolAnswer:
    """What one tool call produced, in the two forms the loop and the model need.

    'payload' is the text that goes back to the model as the tool result; 'accepted' and
    'rejection' are what the loop decides on. A read is always accepted and carries no rejection.
    """

    accepted: bool
    payload: str
    rejection: str | None = None


class AgentSurface(Protocol):
    """The three things a provider-agnostic loop needs from whatever it is playing through."""

    @property
    def tools(self) -> Sequence[ToolSpec]:
        """Every tool the model is offered, action tools and configured reads."""
        ...

    @property
    def read_names(self) -> frozenset[str]:
        """Which of those tools are reads rather than actions."""
        ...

    async def read(self, call: ToolCall) -> ToolAnswer:
        """Execute one read the model asked for."""
        ...

    async def act(self, call: ToolCall) -> ToolAnswer:
        """Submit one action attempt and return the engine's answer."""
        ...


class FacadeSurface:
    """One session and one seat, exposed as generated tools over the facade (FR-6.2)."""

    def __init__(
        self,
        facade: SessionFacade,
        game: str,
        session_id: GameId,
        player: PlayerId,
        *,
        refusal_view: Callable[[Rejection], dict[str, JsonValue]],
        read_tools: bool = True,
        render_detail: str = "full",
    ) -> None:
        self._facade = facade
        self._game = game
        self._plugin: Game = get_game(game)
        self._session_id = session_id
        self._player = player
        self._refusal_view = refusal_view
        self._render_detail = render_detail
        self._read_names = READ_TOOLS if read_tools else frozenset()
        actions = _action_tools(self._plugin)
        collision = self._read_names & {tool.name for tool in actions}
        if collision:
            raise ValueError(f"action(s) {sorted(collision)} collide with the read tools")
        self._tools = tuple(actions) + (
            tuple(_read_tool(name) for name in sorted(self._read_names)) if self._read_names else ()
        )

    @property
    def tools(self) -> Sequence[ToolSpec]:
        return self._tools

    @property
    def read_names(self) -> frozenset[str]:
        return self._read_names

    async def read(self, call: ToolCall) -> ToolAnswer:
        """One pure read, mapped onto the facade operation it names."""
        if call.name not in self._read_names:
            return _error("UNKNOWN_READ", f"{call.name!r} is not a configured read")
        if not isinstance(call.arguments, Mapping):
            return _error("MALFORMED_ARGUMENTS", "read arguments must be an object")
        try:
            if call.name == READ_STATE:
                observation = self._facade.projection(self._session_id, self._player)
                return ToolAnswer(
                    accepted=True,
                    payload=self._plugin.render(observation, detail=self._render_detail),
                )
            if call.name == READ_DECISIONS:
                return ToolAnswer(accepted=True, payload=self._decisions())
            return ToolAnswer(
                accepted=True,
                payload=self._facade.decision_surface(self._session_id, self._player),
            )
        except SessionError as error:
            return _error("READ_FAILED", str(error))

    async def act(self, call: ToolCall) -> ToolAnswer:
        """Submit one action attempt through the facade, rejection included (FR-1.6)."""
        if not isinstance(call.arguments, Mapping):
            return _error("MALFORMED_ARGUMENTS", "the action arguments are not a JSON object")
        try:
            result = self._facade.submit_action(
                self._session_id,
                Action(player=self._player, type=call.name, params=dict(call.arguments)),
            )
        except (AmbiguousRequestError, SessionError) as error:
            return _error("ACTION_FAILED", str(error))
        if isinstance(result, Applied):
            events: list[JsonValue] = [
                {"type": event.type, "payload": dict(event.payload)} for event in result.events
            ]
            return ToolAnswer(
                accepted=True, payload=to_canonical_json({"ok": True, "events": events})
            )
        view = self._refusal_view(result.rejection)
        return ToolAnswer(
            accepted=False,
            payload=to_canonical_json(view),
            rejection=result.rejection.code.code,
        )

    def _decisions(self) -> str:
        requests = self._facade.pending_decisions(self._session_id)
        payload: list[JsonValue] = [
            {
                "request_id": request.request_id,
                "player": request.player,
                "kind": request.kind,
                "schema_ref": request.schema_ref,
                "context": dict(request.context),
                "phase": request.phase,
            }
            for request in requests
            if request.player == self._player
        ]
        return to_canonical_json(payload)


def _action_tools(game: Game) -> list[ToolSpec]:
    """The plugin's generated definitions, in the same order the MCP surface serves them."""
    return [
        ToolSpec(
            name=str(definition["name"]),
            description=str(definition["description"]),
            input_schema=dict(definition["inputSchema"]),  # type: ignore[arg-type]
        )
        for definition in tool_definitions(game)
    ]


def _read_tool(name: str) -> ToolSpec:
    """One read, described as a protocol capability rather than as a game mechanic."""
    descriptions = {
        READ_STATE: "Read your current projection of the game.",
        READ_DECISIONS: "Read the decisions open to you in this game.",
        READ_SURFACE: "Read the decision surface for your seat.",
    }
    return ToolSpec(name=name, description=descriptions[name], input_schema=dict(_READ_SCHEMA))


def _error(code: str, message: str) -> ToolAnswer:
    return ToolAnswer(
        accepted=False,
        payload=to_canonical_json({"ok": False, "error": code, "message": message}),
        rejection=code,
    )


__all__: list[str] = [
    "READ_DECISIONS",
    "READ_STATE",
    "READ_SURFACE",
    "READ_TOOLS",
    "AgentSurface",
    "FacadeSurface",
    "ToolAnswer",
]
