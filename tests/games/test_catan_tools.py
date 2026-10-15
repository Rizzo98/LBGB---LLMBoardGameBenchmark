"""Tool definitions generated from the declaration (PRD-v1 FR-18.4; kanban card K-058).

The plug-and-play claim is that a game arrives as data. This is where it is checked, by
generating one tool per action type from the schema the plugin declares and comparing the result
with a statement of the same surface written by hand - the parameter list below comes from
RULES.md, not from the schema, so the two accounts have to agree or one of them is wrong.

Nothing here builds a server. A list of tool definitions is what an MCP adapter would serve, and
generating it is the part that proves the claim; serving it is v2's business.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Final

from lgbg.core.game import get_game
from lgbg.core.tools import DESCRIPTION, INPUT_SCHEMA, NAME, parameters, tool_definitions
from lgbg.games.catan import phases

GAME: Final[Any] = get_game("catan")
CHECKOUT: Final[Path] = Path(__file__).resolve().parents[2]
RESOURCES: Final[tuple[str, ...]] = ("brick", "wood", "wool", "wheat", "ore")

PARAMETERS: Final[dict[str, set[str]]] = {
    phases.PLACE_SETTLEMENT: {"vertex"},
    phases.PLACE_ROAD: {"edge"},
    phases.ROLL_DICE: set(),
    phases.END_TURN: set(),
    phases.DISCARD_RESOURCES: set(RESOURCES),
    phases.MOVE_ROBBER: {"hex"},
    phases.CHOOSE_ROBBER_VICTIM: {"victim"},
    phases.BUILD_ROAD: {"edge"},
    phases.BUILD_SETTLEMENT: {"vertex"},
    phases.BUILD_CITY: {"vertex"},
    phases.BUY_DEV_CARD: set(),
    phases.PLAY_DEV_CARD: {"card", "resources"},
    phases.PLACE_FREE_ROAD: {"edge"},
    phases.MARITIME_TRADE: {"give_resource", "give_count", "want_resource"},
    phases.OFFER_TRADE: {"give", "want"},
    phases.RESPOND_TRADE: {"response"},
    phases.CHOOSE_PARTNER: {"partner"},
    phases.CANCEL_TRADE: set(),
}
"""The same surface, written from RULES.md by hand: nineteen actions and what each is told."""


def _by_name() -> dict[str, dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for definition in tool_definitions(GAME):
        name = definition[NAME]
        assert isinstance(name, str)
        by_name[name] = dict(definition)
    return by_name


def test_one_tool_per_action_type_the_game_declares() -> None:
    """FR-18.4: the definition set is the declared surface, and nothing else."""
    names = [definition[NAME] for definition in tool_definitions(GAME)]

    assert names == sorted(GAME.action_schema())
    assert set(_by_name()) == set(names), "one definition per name, and no name twice"
    assert set(names) == set(PARAMETERS), "the generated surface and the hand-written one"
    for definition in tool_definitions(GAME):
        assert definition[DESCRIPTION], "a tool with no description is one nobody can choose"
        assert definition[INPUT_SCHEMA] == GAME.action_schema()[definition[NAME]]


def test_every_action_type_appears_with_the_parameters_the_rules_give_it() -> None:
    """The generated list against the one written from RULES.md, action by action."""
    schema = GAME.action_schema()

    for name, expected in PARAMETERS.items():
        declared = schema[name]
        assert set(parameters(declared)) == expected, name


def test_the_generator_knows_nothing_about_this_game() -> None:
    """The claim, read off the syntax: a generator with a game in it is not a generator.

    The module's docstring may mention Catan - it is documentation, and a scan that failed on prose
    would be a scan nobody could keep - so the check is on the code: what it imports, and what it
    defines. The import half is the layering rule the core already lives under, restated where the
    plug-and-play claim is actually made.
    """
    tree = ast.parse((CHECKOUT / "lgbg" / "core" / "tools.py").read_text(encoding="utf-8"))
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    defined = {
        node.name.lstrip("_")
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }

    assert imported, "a scan that saw nothing would pass anything"
    assert not any(module.startswith("lgbg.games") for module in imported)
    for name in sorted(defined):
        for forbidden in ("catan", "vertex", "edge", "resource", "board"):
            assert forbidden not in name.lower(), name


def test_a_definition_is_json_and_its_parameters_are_shapes() -> None:
    definitions = tool_definitions(GAME)

    assert json.dumps(definitions), "a definition that cannot be serialised cannot be served"
    for definition in definitions:
        declared = GAME.action_schema()[definition[NAME]]
        for name, shape in parameters(declared).items():
            assert isinstance(shape, dict), name
