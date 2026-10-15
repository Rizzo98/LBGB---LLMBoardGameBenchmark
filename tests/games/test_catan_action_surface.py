"""The action surface: what is offered, and what it costs (FR-17.4, FR-17.5; ARCHITECTURE 7.2, 7.3).

legal_actions and action_domains are two halves of one contract. The first enumerates what a
player may do - L2, the level a scripted driver and the fuzzer use. The second describes the
same thing without the cross product: one entry per action type, carrying its cost and the
permitted values of each of its parameters - L1, the level a model is normally given.

The tests hold them to the same rule from both ends. Every action the enumeration produces must
be *accepted*, which is the only claim that makes an enumeration trustworthy, and every value
the description permits must be one the enumeration produces, so the description and the
enumeration cannot drift apart. Both run over a whole recorded game, not over one convenient
position, because the interesting failures are at the steps nobody thought to write a fixture for.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Final

import pytest

from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import GameConfig
from lgbg.core.game import Applied, get_game
from lgbg.core.log import GameLogReader
from lgbg.core.replay import replay
from lgbg.core.rng import SeededRandomSource
from lgbg.core.types import Action, ActionDomain, ParamDomain
from lgbg.games.catan import phases
from lgbg.games.catan.game import ACTIONS, SCHEMA_VERSION
from lgbg.games.catan.rules.building import CITY, COSTS, ROAD, SETTLEMENT
from lgbg.games.catan.state import RESOURCE_ORDER, CatanState, encode_state
from tests.games.catan_boards import at_distance, free_edge, hand, holding, layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20251110
REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
RECORDED_GAME: Final[Path] = REPO_ROOT / "tests" / "golden" / "catan" / "seven_game.god.jsonl"


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _rich(state: CatanState) -> CatanState:
    """A turn in which a player may build everything: a road, a settlement and a city."""
    first = state.board.topology.vertices_of_edge(0)[0]
    second = next(iter(sorted(at_distance(state, first, 2))))
    board = layout(state, roads=[(0, 0)], settlements=[(second, 0)])
    return holding(board, 0, brick=1, wood=1, wool=1, wheat=2, ore=3)


def _domain(domains: list[ActionDomain], name: str) -> ActionDomain:
    found = [domain for domain in domains if domain.type == name]
    assert len(found) == 1, f"{name} must be described exactly once, got {len(found)}"
    return found[0]


def _enumerated(state: CatanState, seat: int, name: str) -> list[Action]:
    return [action for action in GAME.legal_actions(state, seat) if action.type == name]


def test_the_two_halves_describe_the_same_actions() -> None:
    """FR-17.4 and FR-17.5 describe one surface, so the two views must agree on it."""
    state = _rich(_opening())

    for seat in range(PLAYERS):
        enumerated = {action.type for action in GAME.legal_actions(state, seat)}
        described = {domain.type for domain in GAME.action_domains(state, seat)}
        assert enumerated == described
        assert len(GAME.action_domains(state, seat)) == len(described), "one domain per type"


def test_a_rich_turn_offers_everything_the_player_can_do() -> None:
    state = _rich(_opening())

    offered = {action.type for action in GAME.legal_actions(state, 0)}

    assert {phases.BUILD_ROAD, phases.BUILD_SETTLEMENT, phases.BUILD_CITY} <= offered
    assert phases.END_TURN in offered


def test_every_enumerated_action_is_accepted() -> None:
    """FR-17.5: the enumeration is a promise, and this is the promise being kept."""
    state = _rich(_opening())

    enumerated = GAME.legal_actions(state, 0)

    assert enumerated, "the fixture must offer something"
    for action in enumerated:
        result = GAME.apply(state, action, SeededRandomSource(SEED))
        assert isinstance(result, Applied), f"{action.type} was offered and refused: {result}"


def test_a_sample_of_actions_that_are_not_enumerated_is_refused() -> None:
    """The other half of FR-17.5: what is left out was left out for a reason."""
    state = _rich(_opening())
    offered = {
        (action.player, action.type, tuple(sorted(action.params.items())))
        for seat in range(PLAYERS)
        for action in GAME.legal_actions(state, seat)
    }
    settled = next(vertex for vertex, seat in enumerate(state.placed.settlements) if seat == 0)
    crowded = next(iter(sorted(at_distance(state, settled, 1))))
    taken = next(edge for edge in range(len(state.placed.roads)) if state.placed.roads[edge] == 0)

    candidates = [
        Action(player=0, type=phases.BUILD_ROAD, params={"edge": taken}),
        Action(player=0, type=phases.BUILD_SETTLEMENT, params={"vertex": crowded}),
        Action(player=0, type=phases.BUILD_CITY, params={"vertex": crowded}),
        Action(player=0, type="teleport", params={}),
        Action(player=2, type=phases.END_TURN, params={}),
    ]

    for action in candidates:
        assert (action.player, action.type, tuple(sorted(action.params.items()))) not in offered
        assert not isinstance(GAME.apply(state, action, SeededRandomSource(SEED)), Applied), (
            f"{action.type} was not offered but was accepted"
        )


def test_the_domains_name_the_cost_of_each_action() -> None:
    """FR-17.4: costs are part of what L1 renders, and they come from the one price table."""
    domains = GAME.action_domains(_rich(_opening()), 0)

    assert dict(_domain(domains, phases.BUILD_ROAD).cost or {}) == dict(COSTS[ROAD])
    assert dict(_domain(domains, phases.BUILD_SETTLEMENT).cost or {}) == dict(COSTS[SETTLEMENT])
    assert dict(_domain(domains, phases.BUILD_CITY).cost or {}) == dict(COSTS[CITY])
    assert _domain(domains, phases.END_TURN).cost is None, "ending a turn costs nothing"


def test_every_parameter_domain_matches_the_enumeration() -> None:
    """A permitted value the rule refuses, or a legal value that is not permitted, is a bug."""
    for state in (_rich(_opening()), _opening()):
        for seat in range(PLAYERS):
            for domain in GAME.action_domains(state, seat):
                actions = _enumerated(state, seat, domain.type)
                if domain.params:
                    assert actions, f"{domain.type} describes parameters but offers no action"
                else:
                    assert len(actions) == 1, f"{domain.type} takes no parameters"
                for name, param in domain.params.items():
                    assert isinstance(param, ParamDomain)
                    if param.kind == "id_set":
                        assert param.values is not None
                        if all(isinstance(value, int) for value in param.values):
                            assert list(param.values) == sorted(
                                {action.params[name] for action in actions}, key=_as_int
                            )
                        else:
                            # A structured parameter - a composition of cards - is compared
                            # as the canonical JSON a record would hold, in that same order.
                            assert [to_canonical_json(value) for value in param.values] == sorted(
                                {to_canonical_json(action.params[name]) for action in actions}
                            )
                    elif param.kind == "enum":
                        assert param.values is not None
                        assert set(param.values) == {action.params[name] for action in actions}
                    else:
                        assert param.kind == "int_range"
                        assert param.lo == 0
                        assert param.hi is not None


def _as_int(value: Any) -> int:
    assert isinstance(value, int)
    return value


def test_the_domains_are_cross_product_free() -> None:
    """ARCHITECTURE 7.2: one entry per action type, not one per resulting action."""
    state = _rich(_opening())
    domains = GAME.action_domains(state, 0)

    roads = _domain(domains, phases.BUILD_ROAD)
    edges = _enumerated(state, 0, phases.BUILD_ROAD)

    assert len(edges) > 1, "the fixture must offer more than one edge"
    assert len(domains) < len(GAME.legal_actions(state, 0)), (
        "a description that is as long as the enumeration is an enumeration"
    )
    assert set(roads.params) == {"edge"}
    assert roads.params["edge"].kind == "id_set"


def test_both_halves_are_pure_and_take_no_source_of_randomness() -> None:
    """FR-17.6: asking what is legal may not consume a draw or change the position."""
    state = _rich(_opening())
    before = to_canonical_json(encode_state(state))

    first = GAME.legal_actions(state, 0)
    second = GAME.legal_actions(state, 0)
    domains = GAME.action_domains(state, 0)

    assert first == second
    assert domains == GAME.action_domains(state, 0)
    assert to_canonical_json(encode_state(state)) == before
    for function in (GAME.legal_actions, GAME.action_domains):
        assert list(inspect.signature(function).parameters) == ["state", "player"], (
            "neither is handed a source of randomness, which is the strongest form of not "
            "consuming one"
        )


def test_every_action_type_the_game_accepts_is_declared_in_the_schema() -> None:
    """FR-18.1, FR-18.5: schemas, enumeration and implementation cannot drift apart."""
    schema = GAME.action_schema()

    assert set(schema) == set(ACTIONS), "every accepted action is declared, and only those"
    for state in (_rich(_opening()), _opening()):
        for seat in range(PLAYERS):
            for action in GAME.legal_actions(state, seat):
                assert action.type in schema
            for domain in GAME.action_domains(state, seat):
                assert domain.type in schema
    assert GAME.schema_version == SCHEMA_VERSION


def test_the_draft_offers_only_the_draft() -> None:
    """During setup the game offers placement and nothing else, and neither costs anything."""
    state = _opening()

    for seat in range(PLAYERS):
        domains = GAME.action_domains(state, seat)
        for domain in domains:
            assert domain.type in (phases.PLACE_SETTLEMENT, phases.PLACE_ROAD)
            assert domain.cost is None, "the draft is free"


def test_the_surface_is_complete_at_every_step_of_a_recorded_game() -> None:
    """FR-17.5 over a whole game: every action offered at every step is accepted."""
    log = GameLogReader(RECORDED_GAME).read()
    game = get_game(log.header.game)
    states = replay(log, game).states
    checked = 0

    for state in states:
        for seat in range(PLAYERS):
            for action in game.legal_actions(state, seat):
                result = game.apply(state, action, SeededRandomSource(SEED))
                assert isinstance(result, Applied), (
                    f"seq {state.phase_index}: {action.type} was offered and refused: {result}"
                )
                checked += 1

    assert checked > 100, "the fixture must exercise the surface, not one position"
    assert hand() == tuple(0 for _ in RESOURCE_ORDER), "and the helper still builds empty hands"
    assert free_edge(states[-1], 0) >= 0


@pytest.mark.parametrize("seat", range(PLAYERS))
def test_the_surface_is_empty_for_a_seat_with_nothing_to_decide(seat: int) -> None:
    """A seat with no open decision is offered nothing: the surface is per request, not per seat."""
    state = layout(_opening())

    if seat == 0:
        assert GAME.legal_actions(state, seat), "seat 0 is to act in this fixture"
    else:
        assert GAME.legal_actions(state, seat) == []
        assert GAME.action_domains(state, seat) == []
