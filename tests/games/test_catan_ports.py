"""Port access (PRD-v1 FR-14.1; RULES.md 4.12.1).

A harbour belongs to whoever has built on it, and the rules are explicit in both directions: a
settlement or city on a coastal intersection controls the harbour, and a harbour with somebody
else's settlement on it is not yours to use. The ratios are therefore *derived* - from the
board's port placement and the player's own buildings - and the tests derive them a second time,
independently, rather than trusting the function to agree with itself.
"""

from __future__ import annotations

from typing import Any, Final

from lgbg.core.config import GameConfig
from lgbg.core.game import get_game
from lgbg.core.rng import SeededRandomSource
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.rules.trading import GENERAL, ratio, ratios
from lgbg.games.catan.state import RESOURCE_ORDER, CatanState
from tests.games.catan_boards import layout, vertices_of

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20260216


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _generic(state: CatanState) -> int:
    """An edge carrying a 3:1 harbour."""
    return next(port.edge for port in state.board.ports if port.resource is None)


def _specific(state: CatanState, resource: Resource) -> int:
    """An edge carrying the 2:1 harbour for this resource."""
    return next(port.edge for port in state.board.ports if port.resource is resource)


def test_a_player_with_no_harbour_trades_at_four_to_one() -> None:
    """S2 p.4: the 4:1 trade is always possible, harbour or not."""
    state = layout(_opening())

    assert ratios(state, 0) == dict.fromkeys(RESOURCE_ORDER, GENERAL)
    assert ratio(state, 0, Resource.WOOD) == 4


def test_a_building_on_a_generic_harbour_gives_three_to_one() -> None:
    state = _opening()
    edge = _generic(state)
    vertex = vertices_of(state, edge)[0]
    built = layout(state, settlements=[(vertex, 0)])

    assert ratio(built, 0, Resource.WOOD) == 3
    assert ratio(built, 0, Resource.ORE) == 3, "a generic harbour is generic for every resource"


def test_a_specific_harbour_gives_two_to_one_for_its_own_resource_only() -> None:
    """S2 Almanac p.9: a special harbour does not improve any other resource, not even to 3:1."""
    state = _opening()
    vertex = vertices_of(state, _specific(state, Resource.WOOD))[0]
    built = layout(state, settlements=[(vertex, 0)])

    assert ratio(built, 0, Resource.WOOD) == 2
    for other in RESOURCE_ORDER:
        if other is not Resource.WOOD:
            assert ratio(built, 0, other) == 4, f"{other.value} is not improved by a wood harbour"


def test_a_city_controls_a_harbour_as_much_as_a_settlement_does() -> None:
    state = _opening()
    vertex = vertices_of(state, _specific(state, Resource.ORE))[0]
    built = layout(state, cities=[(vertex, 0)])

    assert ratio(built, 0, Resource.ORE) == 2


def test_another_players_building_does_not_give_access() -> None:
    """S5: "May I trade via a harbor where an opponent has a settlement? No." """
    state = _opening()
    vertex = vertices_of(state, _specific(state, Resource.WHEAT))[0]
    built = layout(state, settlements=[(vertex, 1)])

    assert ratio(built, 0, Resource.WHEAT) == 4
    assert ratio(built, 1, Resource.WHEAT) == 2


def test_the_best_of_the_harbours_a_player_touches_is_the_one_that_counts() -> None:
    """RULES.md 4.12.1 item 3: the ratio is the minimum of the applicable terms."""
    state = _opening()
    generic = vertices_of(state, _generic(state))[0]
    wood = vertices_of(state, _specific(state, Resource.WOOD))[0]
    built = layout(state, settlements=[(generic, 0), (wood, 0)])

    assert ratio(built, 0, Resource.WOOD) == 2, "the specific harbour wins for wood"
    assert ratio(built, 0, Resource.BRICK) == 3, "and the generic one is what is left for the rest"


def test_the_ratios_are_derived_from_the_board_and_the_buildings() -> None:
    """The derivation, recomputed here the long way round, so the two must agree."""
    state = _opening()
    settlements = [(vertices_of(state, port.edge)[1], 2) for port in state.board.ports[:3]]
    built = layout(state, settlements=settlements)

    expected: dict[Resource, int] = dict.fromkeys(RESOURCE_ORDER, GENERAL)
    for port in built.board.ports:
        touched = any(
            built.placed.settlements[vertex] == 2 or built.placed.cities[vertex] == 2
            for vertex in built.board.topology.vertices_of_edge(port.edge)
        )
        if not touched:
            continue
        for resource in RESOURCE_ORDER:
            if port.resource is None or port.resource is resource:
                expected[resource] = min(expected[resource], port.ratio)

    assert ratios(built, 2) == expected
    assert ratios(built, 0) == dict.fromkeys(RESOURCE_ORDER, GENERAL), "and only for 2"


def test_the_curated_board_carries_the_nine_harbours_the_rules_describe() -> None:
    """Four generic and five specific, one per resource (S2 Almanac p.9)."""
    ports = _opening().board.ports

    assert len(ports) == 9
    assert sum(1 for port in ports if port.resource is None) == 4
    specific = [port.resource for port in ports if port.resource is not None]
    assert sorted(item.value for item in specific if item is not None) == [
        "brick",
        "ore",
        "wheat",
        "wood",
        "wool",
    ]


def test_a_harbour_may_be_used_the_turn_it_is_built() -> None:
    """S4 3.0.10 and S5: nothing about the derivation waits for the next turn."""
    state = _opening()
    vertex = vertices_of(state, _generic(state))[1]
    before = layout(state)
    after = layout(layout(state), settlements=[(vertex, 0)])

    assert ratio(before, 0, Resource.WOOL) == 4
    assert ratio(after, 0, Resource.WOOL) == 3
