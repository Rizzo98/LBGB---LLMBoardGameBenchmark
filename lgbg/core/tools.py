"""Tool definitions, generated from a game's own declaration (PRD-v1 FR-18.4; ARCHITECTURE.md 7.3).

The claim the plugin system is built on is that a game arrives as *data* plus code only the game
knows: the platform reads its schemas and presents its actions. If adding a game required
hand-written tools, the claim would be false - so this module is the proof, and it is small on
purpose. It knows the shape MCP uses for a tool and nothing at all about boards or Catan: every
word of a definition comes from the plugin's own declaration.

The definitions are plain JSON, so the adapter that serves them (v2) is a transport concern: a
list of objects with a name, a description and an input schema is what MCP asks for, and nothing
here connects to anything.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from lgbg.core.game import Game, GamePluginError
from lgbg.core.types import JsonSchema, JsonValue

NAME: Final[str] = "name"
DESCRIPTION: Final[str] = "description"
INPUT_SCHEMA: Final[str] = "inputSchema"
"""The three keys every tool definition carries, named the way MCP names them."""


def tool_definitions(game: Game) -> list[dict[str, JsonValue]]:
    """One tool per action type the game declares, in a stable order (FR-18.4)."""
    definitions: list[dict[str, JsonValue]] = []
    for name, declared in sorted(game.action_schema().items()):
        if not isinstance(declared, Mapping):
            raise GamePluginError(f"the declared schema of {name!r} is not an object")
        definitions.append(
            {
                NAME: name,
                DESCRIPTION: _description(game, name),
                INPUT_SCHEMA: dict(declared),
            }
        )
    return definitions


def describe_read(game: Game, read: str, *, game_id: str, player: int | None = None) -> str:
    """One resource's display name, derived from the plugin and the session, never hand-written.

    A resource's URI is a protocol shape; its name is prompt surface, and FR-9.5 requires that
    surface to have one generator. The game's own name comes from its declaration, and the read and
    seat are protocol facts, so adding a game adds no line here.
    """
    seat = "" if player is None else f" for seat {player}"
    return f"{game.name} {read} in {game_id}{seat}"


def parameters(declared: JsonValue) -> dict[str, JsonSchema]:
    """The parameters a declared action takes, by name, across every alternative shape.

    An action with several shapes - a development card told which resources to take, and one that
    is told nothing - still declares one parameter list: the shapes differ in what is *required*,
    not in what exists. The union, in a stable order, is what a prompt or a tool description
    needs, and it is derived here rather than written down a second time.
    """
    found: dict[str, JsonSchema] = {}
    if not isinstance(declared, Mapping):
        return found
    for branch in _branches(declared):
        properties = branch.get("properties")
        if not isinstance(properties, Mapping):
            continue
        for name, shape in properties.items():
            if isinstance(name, str) and isinstance(shape, Mapping):
                found.setdefault(name, shape)
    return found


def _branches(declared: Mapping[str, JsonValue]) -> list[Mapping[str, JsonValue]]:
    """The shapes a declaration is made of: itself, or the branches of its oneOf."""
    alternatives = declared.get("oneOf")
    if isinstance(alternatives, Sequence) and not isinstance(alternatives, str):
        return [branch for branch in alternatives if isinstance(branch, Mapping)]
    return [declared]


def _description(game: Game, name: str) -> str:
    """What the tool does, in the game's own words - there is nothing else to use."""
    return f"the {name} action of {game.name}"
