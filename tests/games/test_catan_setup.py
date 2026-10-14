"""The opening draft (PRD-v1 FR-8.1, FR-8.2, FR-8.3, FR-8.5).

The draft is the first thing in this project that is actually a game: eight placements, two
decisions each, in a snake order, with the distance rule and the road attachment enforced. It
is also where the plugin stops being an interface and starts being Catan.

Two things are asserted beyond "a settlement can be placed". That every refusal is a *specific*
declared code - an occupied vertex is not the same defect as a vertex one edge too close, and a
metric that cannot tell them apart measures nothing. And that the whole draft runs end to end
through the ordinary runtime, producing a record that replays with every hash verified: the
slice's exit condition, and the machinery that will carry every later slice.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

import pytest

from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.errors import BAD_PARAMS, GAME_OVER, UNKNOWN_ACTION
from lgbg.core.game import Applied, Rejected, get_game, registered_games
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import replay, verify
from lgbg.core.rng import NullRandomSource, SeededRandomSource
from lgbg.core.run import GameRun
from lgbg.core.types import Action
from lgbg.games.catan.rejections import (
    DECLARED_CODES,
    EDGE_OCCUPIED,
    NO_PIECES_REMAINING,
    NOT_CONNECTED,
    TOO_CLOSE,
    VERTEX_OCCUPIED,
)
from lgbg.games.catan.rules.setup import neighbouring_vertices, setup_order
from lgbg.games.catan.state import NO_OWNER, Phase, Placed, Supply, decode_state

SEED: Final[int] = 20250401
PLAYERS: Final[int] = 4

GAME: Final[Any] = get_game("catan")
"""The shared instance the registry hands out: one per game, because plugins are stateless."""


def _opening() -> Any:
    return GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )


def _place_settlement(state: Any, vertex: int, *, player: int | None = None) -> Any:
    seat = state.turn if player is None else player
    return GAME.apply(
        state,
        Action(player=seat, type="place_settlement", params={"vertex": vertex}),
        NullRandomSource(),
    )


def _place_road(state: Any, edge: int, *, player: int | None = None) -> Any:
    seat = state.turn if player is None else player
    return GAME.apply(
        state, Action(player=seat, type="place_road", params={"edge": edge}), NullRandomSource()
    )


def _free_vertex(state: Any, *, avoid: tuple[int, ...] = ()) -> int:
    """A vertex the distance rule allows, preferring one far from anything already placed."""
    blocked = set(avoid)
    for vertex in range(len(state.placed.settlements)):
        neighbours = neighbouring_vertices(state, vertex)
        if any(
            state.placed.settlements[site] != NO_OWNER or state.placed.cities[site] != NO_OWNER
            for site in (vertex, *neighbours)
        ):
            continue
        if any(vertex in neighbouring_vertices(state, site) for site in blocked):
            continue
        return vertex
    raise AssertionError("the board has no legal vertex left, which cannot happen in a draft")


def _edge_at(state: Any, vertex: int) -> int:
    edges: tuple[int, ...] = state.board.topology.edges_at(vertex)
    return edges[0]


def test_the_plugin_registers_as_catan_with_its_versions() -> None:
    assert "catan" in registered_games()
    assert get_game("catan") is GAME, "one shared instance per game (FR-6.5)"
    assert GAME.name == "catan"
    assert GAME.rules_version == "catan-rules-1"
    assert GAME.schema_version == "catan-actions-1"


def test_the_draft_opens_with_the_first_seat_placing_a_settlement() -> None:
    state = _opening()

    requests = GAME.pending_decisions(state)

    assert len(requests) == 1
    assert requests[0].player == 0
    assert requests[0].kind == "place_settlement"
    assert state.phase is Phase.SETUP_SETTLEMENT


def test_a_settlement_opens_the_road_decision_for_the_same_player() -> None:
    state = _opening()
    vertex = _free_vertex(state)

    result = _place_settlement(state, vertex)

    assert isinstance(result, Applied)
    assert result.state.phase is Phase.SETUP_ROAD
    assert result.state.placed.settlements[vertex] == 0
    assert result.state.setup_vertex == vertex
    requests = GAME.pending_decisions(result.state)
    assert [request.kind for request in requests] == ["place_road"]
    assert requests[0].player == 0


def test_a_road_must_attach_to_the_settlement_just_placed() -> None:
    state = _opening()
    vertex = _free_vertex(state)
    placed = _place_settlement(state, vertex).state
    attached = set(placed.board.topology.edges_at(vertex))
    elsewhere = next(edge for edge in range(len(placed.placed.roads)) if edge not in attached)

    result = _place_road(placed, elsewhere)

    assert isinstance(result, Rejected)
    assert result.rejection.code == NOT_CONNECTED
    assert dict(result.rejection.details)["must_touch"] == vertex


def test_a_road_attached_to_the_new_settlement_is_accepted_and_advances_the_draft() -> None:
    state = _opening()
    vertex = _free_vertex(state)
    placed = _place_settlement(state, vertex).state

    result = _place_road(placed, _edge_at(placed, vertex))

    assert isinstance(result, Applied)
    assert result.state.setup_vertex == NO_OWNER
    assert result.state.turn == 1, "the snake moves to the next seat after a road"
    assert result.state.supply[0] == Supply(14, 4, 4)


def test_an_occupied_vertex_is_refused_with_its_own_code() -> None:
    state = _opening()
    vertex = _free_vertex(state)
    taken = _place_settlement(state, vertex).state

    result = _place_settlement(replace(taken, phase=Phase.SETUP_SETTLEMENT), vertex)

    assert isinstance(result, Rejected)
    assert result.rejection.code == VERTEX_OCCUPIED


def test_the_distance_rule_refuses_a_vertex_one_edge_away() -> None:
    state = _opening()
    vertex = _free_vertex(state)
    settlement = [NO_OWNER] * len(state.placed.settlements)
    settlement[vertex] = 0
    crowded = replace(
        state,
        placed=Placed(
            settlements=tuple(settlement),
            cities=state.placed.cities,
            roads=state.placed.roads,
        ),
    )
    neighbour = neighbouring_vertices(crowded, vertex)[0]

    result = _place_settlement(crowded, neighbour)

    assert isinstance(result, Rejected)
    assert result.rejection.code == TOO_CLOSE
    assert dict(result.rejection.details)["blocked_by"] == [vertex]


def test_an_occupied_edge_is_refused_with_its_own_code() -> None:
    state = _opening()
    vertex = _free_vertex(state)
    placed = _place_settlement(state, vertex).state
    edge = _edge_at(placed, vertex)
    roaded = _place_road(placed, edge).state
    back = replace(
        roaded,
        phase=Phase.SETUP_ROAD,
        turn=0,
        setup_vertex=vertex,
    )

    result = _place_road(back, edge)

    assert isinstance(result, Rejected)
    assert result.rejection.code == EDGE_OCCUPIED


def test_a_road_without_a_settlement_awaiting_one_is_a_parameter_error() -> None:
    result = _place_road(_opening(), 0)

    assert isinstance(result, Rejected)
    assert result.rejection.code == BAD_PARAMS


@pytest.mark.parametrize("vertex", [-1, 999])
def test_a_vertex_off_the_board_is_a_parameter_error(vertex: int) -> None:
    result = _place_settlement(_opening(), vertex)

    assert isinstance(result, Rejected)
    assert result.rejection.code == BAD_PARAMS


def test_an_action_the_game_does_not_declare_is_refused() -> None:
    result = GAME.apply(
        _opening(), Action(player=0, type="build_space_elevator", params={}), NullRandomSource()
    )

    assert isinstance(result, Rejected)
    assert result.rejection.code == UNKNOWN_ACTION


def test_the_snake_order_is_the_one_the_rulebook_describes() -> None:
    assert setup_order(PLAYERS) == (0, 1, 2, 3, 3, 2, 1, 0)


def test_the_whole_draft_runs_in_snake_order_and_ends_in_the_turn_phase() -> None:
    state = _opening()
    seats = []
    for _ in range(8):
        seats.append(state.turn)
        vertex = _free_vertex(state)
        state = _place_settlement(state, vertex).state
        state = _place_road(state, _edge_at(state, vertex)).state

    assert seats == [0, 1, 2, 3, 3, 2, 1, 0]
    assert state.phase is Phase.TURN_START
    assert state.turn == 0, "the seat that drafts last opens the game"
    settlements = [seat for seat in state.placed.settlements if seat != NO_OWNER]
    roads = [seat for seat in state.placed.roads if seat != NO_OWNER]
    assert Counter(settlements) == Counter({0: 2, 1: 2, 2: 2, 3: 2})
    assert Counter(roads) == Counter({0: 2, 1: 2, 2: 2, 3: 2})
    assert GAME.check_invariants(state) == []
    assert sum(supply.settlements for supply in state.supply) == PLAYERS * 5 - 8
    assert sum(supply.roads for supply in state.supply) == PLAYERS * 15 - 8
    assert not GAME.is_terminal(state)


def test_the_draft_consumes_no_randomness() -> None:
    """The board and the deck are drawn once; the draft is decisions, not chance."""
    state = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    quiet = NullRandomSource()

    vertex = _free_vertex(state)
    GAME.apply(state, Action(player=0, type="place_settlement", params={"vertex": vertex}), quiet)

    assert quiet.draws() == []


def test_a_piece_shortage_is_refused_rather_than_improvised() -> None:
    state = _opening()
    vertex = _free_vertex(state)
    empty = replace(
        state,
        supply=tuple(
            Supply(roads=15, settlements=0, cities=4) if seat == 0 else supply
            for seat, supply in enumerate(state.supply)
        ),
    )

    result = _place_settlement(empty, vertex)

    assert isinstance(result, Rejected)
    assert result.rejection.code == NO_PIECES_REMAINING


def test_every_declared_code_is_unique_and_described() -> None:
    codes = GAME.rejection_codes()

    assert len({code.code for code in codes}) == len(codes)
    assert all(code.description for code in codes)
    assert {
        code.code
        for code in (VERTEX_OCCUPIED, EDGE_OCCUPIED, TOO_CLOSE, NOT_CONNECTED, NO_PIECES_REMAINING)
    } <= {code.code for code in DECLARED_CODES}


def test_an_action_after_termination_is_refused() -> None:
    result = GAME.apply(
        replace(_opening(), phase=Phase.OVER),
        Action(player=0, type="place_settlement", params={"vertex": 0}),
        NullRandomSource(),
    )

    assert isinstance(result, Rejected)
    assert result.rejection.code == GAME_OVER


def test_the_legal_actions_for_the_acting_player_are_accepted_and_others_are_not() -> None:
    """FR-17.5 in miniature: the enumeration is not merely plausible."""
    state = _opening()
    legal = GAME.legal_actions(state, 0)
    assert legal, "the acting player must have something to do"

    for action in legal[:5]:
        assert isinstance(GAME.apply(state, action, NullRandomSource()), Applied)

    vertex = _free_vertex(state)
    taken = _place_settlement(state, vertex).state
    assert isinstance(
        GAME.apply(
            taken,
            Action(player=0, type="place_settlement", params={"vertex": vertex}),
            NullRandomSource(),
        ),
        Rejected,
    )


def test_a_whole_draft_replays_from_its_record(tmp_path: Path) -> None:
    """The slice's exit condition: play a real game's opening, then verify the record."""
    run = GameRun(
        GAME,
        RunConfig(seed=SEED, players=PLAYERS, interaction_protocol="decline_only"),
        game_id="g-0001",
        directory=tmp_path,
    )
    seats = []
    for _ in range(8):
        request = run.pending[0]
        seats.append(request.player)
        vertex = _free_vertex(run.state)
        assert isinstance(
            run.submit(
                Action(player=request.player, type="place_settlement", params={"vertex": vertex})
            ),
            Applied,
        )
        edge = _edge_at(run.state, vertex)
        assert isinstance(
            run.submit(Action(player=request.player, type="place_road", params={"edge": edge})),
            Applied,
        )
    terminal = run.finish()

    log = GameLogReader(god_log_path(tmp_path, "g-0001")).read()
    report = verify(log, GAME)
    replayed = replay(log, GAME)

    assert seats == [0, 1, 2, 3, 3, 2, 1, 0]
    assert report.actions == 16, "eight settlements and eight roads"
    assert report.rejections == 0
    assert terminal.total_actions == 16
    assert len(replayed.states) == 17
    assert replayed.states[-1].phase is Phase.TURN_START
    assert [record.phase for record in log.phases].count("setup_road") == 8


def test_the_state_after_a_draft_round_trips() -> None:
    state = _opening()
    vertex = _free_vertex(state)
    state = _place_settlement(state, vertex).state
    state = _place_road(state, _edge_at(state, vertex)).state

    assert decode_state(GAME.encode_state(state)) == state
