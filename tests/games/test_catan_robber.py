"""The robber: where it may move, what it blocks, and who sits next to it (RULES.md 4.9).

FR-12.3 is one sentence - the current player must move the robber to a different hex - and it
hides three things worth testing. The robber is the one part of the position whose *progress* is
invisible: a robber that has just moved looks exactly like one that has not, so the phase records
the phase instance the move happened in and answers "has it moved yet" from the state instead of
from a flag the machine keeps between calls. It blocks a hex without blocking anything else. And
the players it can steal from are not a list anybody writes down: the hex knows its vertices, the
vertices know who built on them, and the answer moves with the board.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.errors import BAD_PARAMS, NOT_YOUR_DECISION, WRONG_PHASE, Rejection
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import verify
from lgbg.core.rng import (
    KIND_RANDINT,
    NullRandomSource,
    ReplayRandomSource,
    RngDraw,
    SeededRandomSource,
)
from lgbg.core.run import GameRun
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.rejections import ROBBER_ALREADY_MOVED, ROBBER_SAME_HEX
from lgbg.games.catan.rules.production import DICE_DIE_1, DICE_DIE_2
from lgbg.games.catan.rules.robber import robber_victims
from lgbg.games.catan.state import NO_OWNER, RESOURCE_ORDER, CatanState, Phase, Placed

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20250922
DESERT: Final[int] = 9
"""Hex 9 is the desert of the curated board: the robber starts there."""


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _token_hex(state: CatanState, total: int) -> int:
    return next(
        hex_.id
        for hex_ in state.board.topology.hexes
        if state.board.tokens[hex_.id] == total and hex_.id != state.robber
    )


def _token_hex_of(state: CatanState, total: int, name: str) -> int:
    return next(
        hex_.id
        for hex_ in state.board.topology.hexes
        if state.board.tokens[hex_.id] == total
        and (resource := state.board.resource_of_hex(hex_.id)) is not None
        and resource.value == name
    )


def _building(state: CatanState, *, settlements: Sequence[tuple[int, int]] = ()) -> CatanState:
    seats = list(state.placed.settlements)
    for vertex, seat in settlements:
        seats[vertex] = seat
    return replace(state, placed=Placed(tuple(seats), state.placed.cities, state.placed.roads))


def _rolling(*dice: int) -> ReplayRandomSource:
    labels = (DICE_DIE_1, DICE_DIE_2)
    return ReplayRandomSource(
        [
            RngDraw(purpose=label, kind=KIND_RANDINT, args={"lo": 1, "hi": 6}, value=value)
            for label, value in zip(labels, dice, strict=True)
        ],
        action="roll_dice",
    )


def _resolving(state: CatanState, *, robber: int = DESERT) -> CatanState:
    """The position a seven leaves: the robber phase, with its move still to come."""
    return replace(state, phase=Phase.ROBBER, dice=(3, 4), robber=robber, robber_moved_at=NO_OWNER)


def _move(state: CatanState, seat: int, hex_id: int) -> Applied:
    result = GAME.apply(
        state,
        Action(player=seat, type=phases.MOVE_ROBBER, params={"hex": hex_id}),
        NullRandomSource(),
    )
    assert isinstance(result, Applied), "a legal move must be applied, not refused"
    return result


def _refusal(state: CatanState, seat: int, params: dict[str, Any]) -> Rejection:
    result = GAME.apply(
        state, Action(player=seat, type=phases.MOVE_ROBBER, params=params), NullRandomSource()
    )
    assert isinstance(result, Rejected), "an illegal move must be refused"
    return result.rejection


def test_the_robber_phase_asks_the_current_seat_to_move_the_robber() -> None:
    """RULES.md 4.9 item 4: there is no option to leave the robber where it is."""
    state = _resolving(_opening())

    requests = GAME.pending_decisions(state)

    assert len(requests) == 1
    assert requests[0].player == state.turn
    assert requests[0].kind == phases.MOVE_ROBBER
    assert requests[0].schema_ref == phases.MOVE_ROBBER
    assert dict(requests[0].context)["from"] == DESERT


def test_every_hex_but_the_one_it_occupies_is_a_destination() -> None:
    """The desert is a legal destination; the current hex is the only one that is not."""
    state = _resolving(_opening(), robber=0)

    offered = {dict(action.params)["hex"] for action in GAME.legal_actions(state, state.turn)}
    everywhere = {hex_.id for hex_ in state.board.topology.hexes}

    assert offered == everywhere - {state.robber}
    assert DESERT in offered, "the desert is somewhere to put it"
    for action in GAME.legal_actions(state, state.turn):
        assert isinstance(GAME.apply(state, action, NullRandomSource()), Applied)


def test_a_move_to_the_same_hex_is_refused() -> None:
    state = _resolving(_opening())

    refusal = _refusal(state, state.turn, {"hex": DESERT})

    assert refusal.code == ROBBER_SAME_HEX
    assert dict(refusal.details)["from"] == DESERT


@pytest.mark.parametrize("params", [{"hex": 19}, {"hex": -1}, {"hex": "three"}, {}])
def test_a_destination_that_is_not_a_hex_is_refused(params: dict[str, Any]) -> None:
    """FR-18.2: the declared schema judges the shape of the parameter, before any rule logic."""
    state = _resolving(_opening())

    refusal = _refusal(state, state.turn, params)

    assert refusal.code == BAD_PARAMS


def test_only_the_current_seat_may_move_the_robber() -> None:
    state = _resolving(_opening())

    refusal = _refusal(state, (state.turn + 1) % PLAYERS, {"hex": 0})

    assert refusal.code == NOT_YOUR_DECISION


def test_the_robber_does_not_move_in_another_phase() -> None:
    state = replace(_resolving(_opening()), phase=Phase.ACTION)

    refusal = _refusal(state, state.turn, {"hex": 0})

    assert refusal.code == WRONG_PHASE


def test_the_robber_moves_once_per_phase() -> None:
    """RULES.md 4.4: the phase has two steps, and the move is the first of them."""
    hex_id = _token_hex(_opening(), 5)
    first, second = _opening().board.topology.vertices_of_hex(hex_id)[:2]
    state = _resolving(_building(_opening(), settlements=[(first, 1), (second, 2)]))

    moved = _move(state, state.turn, hex_id)
    refusal = _refusal(moved.state, state.turn, {"hex": 1})

    assert moved.state.robber == hex_id
    assert moved.state.phase is Phase.ROBBER, "two candidates: the steal is not resolved"
    assert refusal.code == ROBBER_ALREADY_MOVED
    assert dict(refusal.details)["to"] == hex_id


def test_the_move_is_announced_with_both_hexes() -> None:
    state = _resolving(_opening())

    moved = _move(state, state.turn, 4)

    assert next(event.type for event in moved.events) == "robber_moved"
    payload = dict(moved.events[0].payload)
    assert payload == {"player": state.turn, "from": DESERT, "to": 4}
    assert moved.state.robber == 4
    assert moved.state.robber_moved_at == state.phase_index, (
        "the move records the phase instance it happened in, which is what tells the machine "
        "that this step is done"
    )


def test_the_phase_closes_into_the_action_phase_when_nobody_is_adjacent() -> None:
    """RULES.md 4.4: the robber phase ends when the move is resolved, and the turn goes on."""
    state = _resolving(_opening())
    empty = next(
        hex_.id
        for hex_ in state.board.topology.hexes
        if hex_.id != state.robber and not _occupied_by_anyone(state, hex_.id)
    )

    moved = _move(state, state.turn, empty)

    assert robber_victims(moved.state) == ()
    assert moved.state.phase is Phase.ACTION
    announced = [event for event in moved.events if event.type == "phase_started"]
    assert [dict(event.payload)["phase"] for event in announced] == ["action"]


def test_a_victim_is_asked_for_when_there_is_a_choice() -> None:
    """RULES.md 4.9 item 5: the choice arrives as its own request, answered by K-027."""
    hex_id = _token_hex(_opening(), 5)
    first, second = _opening().board.topology.vertices_of_hex(hex_id)[:2]
    occupied = _resolving(_building(_opening(), settlements=[(first, 1), (second, 2)]))

    moved = _move(occupied, occupied.turn, hex_id)

    requests = GAME.pending_decisions(moved.state)
    assert moved.state.phase is Phase.ROBBER, "the steal is not resolved yet"
    assert moved.state.robber_moved_at == moved.state.phase_index
    assert [request.kind for request in requests] == [phases.CHOOSE_ROBBER_VICTIM]
    assert requests[0].player == occupied.turn
    assert dict(requests[0].context)["candidates"] == [1, 2]


def test_the_mover_is_never_a_candidate() -> None:
    """RULES.md 4.9 item 5: the candidates are the players other than the one who moved it."""
    hex_id = _token_hex(_opening(), 5)
    vertex = _opening().board.topology.vertices_of_hex(hex_id)[0]
    state = _resolving(_building(_opening(), settlements=[(vertex, 0)]))

    moved = _move(state, 0, hex_id)

    assert robber_victims(moved.state) == (), "a seat cannot steal from itself"
    assert moved.state.phase is Phase.ACTION, "and with no victim the phase is over"


def test_the_candidates_are_derived_from_the_board() -> None:
    """Not a list anybody authored: the inverse of the hex-to-vertex relation and the occupancy."""
    state = _resolving(_opening())
    hex_id = _token_hex(state, 5)
    vertices = state.board.topology.vertices_of_hex(hex_id)
    occupied = _building(
        _opening(), settlements=[(vertices[0], 2), (vertices[1], 3), (vertices[2], 2)]
    )
    moved = replace(_resolving(occupied), robber=hex_id, turn=0)

    expected = sorted(
        {
            seat
            for vertex, seat in enumerate(moved.placed.settlements)
            if seat != NO_OWNER
            and seat != moved.turn
            and hex_id in moved.board.topology.hexes_at(vertex)
        }
    )

    assert expected == [2, 3], "the fixture must be worth asserting on"
    assert robber_victims(moved) == tuple(expected)
    assert robber_victims(replace(moved, robber=_other_hex(moved, hex_id))) == ()


def test_a_city_counts_as_a_building_next_to_the_robber() -> None:
    """RULES.md 4.9 item 5: the candidates have a settlement *or a city* on the hex."""
    state = _resolving(_opening())
    hex_id = _token_hex(state, 6)
    vertex = state.board.topology.vertices_of_hex(hex_id)[0]
    seats = list(state.placed.cities)
    seats[vertex] = 2
    with_city = replace(
        state,
        placed=Placed(state.placed.settlements, tuple(seats), state.placed.roads),
        robber=hex_id,
    )

    assert robber_victims(with_city) == (2,)


def test_a_blocked_hex_produces_nothing() -> None:
    """FR-12.3: the hex under the robber pays nothing, and the hex sharing its number still does."""
    state = _opening()
    blocked = _token_hex_of(state, 5, "wheat")
    paying = _token_hex_of(state, 5, "wood")
    occupied = _building(
        state,
        settlements=[
            (state.board.topology.vertices_of_hex(blocked)[0], 1),
            (state.board.topology.vertices_of_hex(paying)[0], 2),
        ],
    )
    in_turn = replace(occupied, phase=Phase.TURN_PRODUCTION, turn=0)

    before = GAME.apply(in_turn, Action(player=0, type="roll_dice", params={}), _rolling(2, 3))
    assert isinstance(before, Applied)
    with_robber = replace(in_turn, robber=blocked)
    after = GAME.apply(with_robber, Action(player=0, type="roll_dice", params={}), _rolling(2, 3))

    assert isinstance(before, Applied)
    assert isinstance(after, Applied)
    paid_before = dict(next(e for e in before.events if e.type == "production").payload)
    paid_after = dict(next(e for e in after.events if e.type == "production").payload)
    assert blocked in _hexes(paid_before), "the fixture must be worth asserting on"
    assert _hexes(paid_after) == [paying]
    assert after.state.hands[1] == (0,) * 5, "the settlement on the blocked hex earned nothing"
    assert after.state.hands[2][RESOURCE_ORDER.index(Resource.WOOD)] == 1, "the other hex paid"


def test_a_seven_is_resolved_through_the_runtime(tmp_path: Any) -> None:
    """RULES.md 4.4 item 5, in one record: roll, discard, move the robber, then the turn."""
    run = GameRun(
        GAME,
        RunConfig(
            seed=SEED,
            players=PLAYERS,
            interaction_protocol="decline_only",
            game_config=GameConfig({"board": "fixed:standard_a"}),
        ),
        game_id="g-0001",
        directory=tmp_path,
    )
    for _ in range(16):
        request = run.pending[0]
        assert isinstance(run.submit(GAME.legal_actions(run.state, request.player)[0]), Applied)
    for _ in range(60):
        assert isinstance(
            run.submit(Action(player=run.state.turn, type="roll_dice", params={})), Applied
        )
        if run.state.phase is Phase.ROBBER:
            break
        assert isinstance(
            run.submit(Action(player=run.state.turn, type="end_turn", params={})), Applied
        )
    assert run.state.phase is Phase.ROBBER, "this seed rolls a seven within sixty turns"

    mover = run.state.turn
    moved = run.submit(
        Action(player=mover, type=phases.MOVE_ROBBER, params={"hex": _other_hex(run.state, DESERT)})
    )
    assert isinstance(moved, Applied)
    run.finish()

    log = GameLogReader(god_log_path(tmp_path, "g-0001")).read()
    recorded = [
        dict(event.payload)
        for record in log.actions
        for event in record.events
        if event.type == "robber_moved"
    ]

    assert recorded == [{"player": mover, "from": DESERT, "to": run.state.robber}]
    assert [record.phase for record in log.phases][-3:] == ["discard", "robber", "action"], (
        "the seven is resolved: the discards, the robber, and the turn's action phase"
    )
    assert verify(log, GAME).rejections == 0


def _hexes(payload: dict[str, Any]) -> list[Any]:
    """The hexes a production event names, checked rather than assumed (the payload is JSON)."""
    hexes = payload["hexes"]
    assert isinstance(hexes, list)
    return hexes


def _occupied_by_anyone(state: CatanState, hex_id: int) -> bool:
    return any(
        state.placed.settlements[vertex] != NO_OWNER or state.placed.cities[vertex] != NO_OWNER
        for vertex in state.board.topology.vertices_of_hex(hex_id)
    )


def _other_hex(state: CatanState, hex_id: int) -> int:
    return next(hex_.id for hex_ in state.board.topology.hexes if hex_.id != hex_id)
