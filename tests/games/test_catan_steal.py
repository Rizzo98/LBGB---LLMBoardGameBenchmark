"""The steal (PRD-v1 FR-12.4, FR-12.5; RULES.md 4.9 items 5, 6 and 8).

One card, chosen at random from one victim's hand, by a recorded draw. Two things make this more
than a card swap.

The engine does not ask a question it can answer: with exactly one player next to the robber that
player is the victim, and the steal happens as part of the move, so the decision - and the
request - exists only when there is a choice to make (RULES.md 4.9 item 5).

And what each player learns is not the same thing. The thief learns *which* card it took, the
victim learns that one card of that type left their hand, and everybody else learns only that a
hand changed size. That is FR-12.5, and it is a property of the projection: each player is shown
one hand, their own, which is the only place the identity can come from.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.errors import (
    BAD_PARAMS,
    NO_SUCH_REQUEST,
    NOT_YOUR_DECISION,
    WRONG_PHASE,
    Rejection,
)
from lgbg.core.game import Applied, Rejected, get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import verify
from lgbg.core.rng import KIND_CHOICE, NullRandomSource, ReplayRandomSource, SeededRandomSource
from lgbg.core.run import GameRun
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.projection import observe
from lgbg.games.catan.rejections import ROBBER_VICTIM_NOT_ADJACENT
from lgbg.games.catan.rules.robber import ROBBER_STEAL, robber_victims
from lgbg.games.catan.state import NO_OWNER, RESOURCE_ORDER, CatanState, Phase, Placed, Supply

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20250929
DESERT: Final[int] = 9
NOTHING: Final[tuple[int, ...]] = (0,) * len(RESOURCE_ORDER)
VALUE_OF: Final[dict[str, int]] = {
    resource.value: index for index, resource in enumerate(RESOURCE_ORDER)
}


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _hand(**counts: int) -> tuple[int, ...]:
    assert set(counts) <= set(VALUE_OF), f"unknown resource in {sorted(counts)}"
    return tuple(counts.get(resource.value, 0) for resource in RESOURCE_ORDER)


def _held(state: CatanState, seat: int, resource: str) -> int:
    return state.hands[seat][VALUE_OF[resource]]


def _stocked(state: CatanState, seat: int, **counts: int) -> CatanState:
    """Deal one hand out of the bank, so the position conserves cards like a real one (FR-6.9)."""
    hand = _hand(**counts)
    bank = tuple(cards - hand[index] for index, cards in enumerate(state.bank))
    assert min(bank) >= 0, "a hand cannot hold cards the bank does not have"
    hands = list(state.hands)
    hands[seat] = hand
    return replace(state, hands=tuple(hands), bank=bank)


def _waiting(state: CatanState, *, settlements: Sequence[tuple[int, int]]) -> CatanState:
    """A seven already rolled, with the robber still on the desert and a move to make.

    The buildings are taken out of the builders' supplies and the cards out of the bank, so the
    position is one the rules could have produced rather than one that merely looks plausible:
    a fixture that only looked right would pass a conservation check for the wrong reason.
    """
    seats = list(state.placed.settlements)
    supply = list(state.supply)
    for vertex, seat in settlements:
        seats[vertex] = seat
        held = supply[seat]
        supply[seat] = Supply(held.roads, held.settlements - 1, held.cities)
    return replace(
        state,
        placed=Placed(tuple(seats), state.placed.cities, state.placed.roads),
        supply=tuple(supply),
        phase=Phase.ROBBER,
        dice=(3, 4),
        turn=0,
        robber=DESERT,
        robber_moved_at=NO_OWNER,
    )


def _a_hex(state: CatanState) -> int:
    """A hex that is not where the robber is, with room for two neighbouring buildings."""
    return next(hex_.id for hex_ in state.board.topology.hexes if hex_.id != DESERT)


def _lone(state: CatanState, hex_id: int, seat: int) -> CatanState:
    return _waiting(state, settlements=[(state.board.topology.vertices_of_hex(hex_id)[0], seat)])


def _pair(state: CatanState, hex_id: int) -> CatanState:
    first, second = state.board.topology.vertices_of_hex(hex_id)[:2]
    return _waiting(state, settlements=[(first, 1), (second, 2)])


def _move(state: CatanState, hex_id: int, source: Any = None) -> Applied:
    result = GAME.apply(
        state,
        Action(player=state.turn, type=phases.MOVE_ROBBER, params={"hex": hex_id}),
        SeededRandomSource(SEED) if source is None else source,
    )
    assert isinstance(result, Applied), "a legal move must be applied, not refused"
    return result


def _choose(state: CatanState, victim: int, source: Any = None) -> Applied:
    result = GAME.apply(
        state,
        Action(player=state.turn, type=phases.CHOOSE_ROBBER_VICTIM, params={"victim": victim}),
        SeededRandomSource(SEED) if source is None else source,
    )
    assert isinstance(result, Applied), "a legal choice must be applied, not refused"
    return result


def _refusal(state: CatanState, victim: Any, seat: int | None = None) -> Rejection:
    result = GAME.apply(
        state,
        Action(
            player=state.turn if seat is None else seat,
            type=phases.CHOOSE_ROBBER_VICTIM,
            params={"victim": victim},
        ),
        NullRandomSource(),
    )
    assert isinstance(result, Rejected), "an illegal choice must be refused"
    return result.rejection


def _steal(result: Applied) -> dict[str, Any]:
    return dict(next(event.payload for event in result.events if event.type == "robber_stole"))


def test_a_lone_candidate_is_robbed_without_a_decision() -> None:
    """RULES.md 4.9 item 5: one candidate settles the choice, so no request is opened."""
    hex_id = _a_hex(_opening())
    state = _stocked(_lone(_opening(), hex_id, 1), 1, wood=2, brick=1)

    moved = _move(state, hex_id)

    assert robber_victims(moved.state) == (1,)
    assert moved.state.phase is Phase.ACTION, "the steal is resolved, so the phase is over"
    assert [event.type for event in moved.events][:2] == ["robber_moved", "robber_stole"]
    assert sum(moved.state.hands[0]) == sum(state.hands[0]) + 1
    assert sum(moved.state.hands[1]) == sum(state.hands[1]) - 1
    assert GAME.check_invariants(moved.state) == []


def test_a_victim_is_asked_for_only_when_there_is_a_choice() -> None:
    """RULES.md 4.9 item 5: two candidates, and the mover chooses among them."""
    hex_id = _a_hex(_opening())
    state = _pair(_opening(), hex_id)

    moved = _move(state, hex_id)

    requests = GAME.pending_decisions(moved.state)
    assert moved.state.phase is Phase.ROBBER, "the steal has not happened yet"
    assert [request.kind for request in requests] == [phases.CHOOSE_ROBBER_VICTIM]
    assert requests[0].player == state.turn
    assert dict(requests[0].context)["candidates"] == [1, 2]
    assert sum(moved.state.hands[1]) == sum(state.hands[1]), "nobody has been robbed yet"


def test_every_candidate_is_offered_and_nothing_else_is() -> None:
    hex_id = _a_hex(_opening())
    state = _move(_pair(_opening(), hex_id), hex_id).state

    offered = {dict(action.params)["victim"] for action in GAME.legal_actions(state, state.turn)}

    assert offered == {1, 2}
    for action in GAME.legal_actions(state, state.turn):
        assert isinstance(GAME.apply(state, action, SeededRandomSource(SEED)), Applied)


def test_the_card_is_chosen_by_a_recorded_draw() -> None:
    """FR-12.4: one random resource, and the draw that chose it is in the record."""
    hex_id = _a_hex(_opening())
    stocked = _stocked(_opening(), 1, wood=2, ore=1)
    state = _move(_pair(stocked, hex_id), hex_id).state
    source = SeededRandomSource(SEED)

    robbed = _choose(state, 1, source)

    draws = source.draws()
    assert len(draws) == 1, "one card, one draw"
    assert draws[0].purpose == ROBBER_STEAL
    assert draws[0].kind == KIND_CHOICE
    assert dict(draws[0].args) == {"n": sum(state.hands[1])}, "over the cards, not the types"
    taken = str(draws[0].value)
    assert _held(robbed.state, 1, taken) == _held(state, 1, taken) - 1
    assert _held(robbed.state, 0, taken) == _held(state, 0, taken) + 1
    assert _steal(robbed) == {"player": 0, "victim": 1, "resource": taken}


def test_the_steal_replays_from_the_draw_it_recorded() -> None:
    """FR-2.4: the same action, driven by its own recorded draw, produces the same position."""
    hex_id = _a_hex(_opening())
    stocked = _stocked(_opening(), 2, wool=1, wheat=1)
    state = _move(_pair(stocked, hex_id), hex_id).state
    source = SeededRandomSource(SEED)
    first = _choose(state, 2, source)

    record = ReplayRandomSource(source.draws(), action=phases.CHOOSE_ROBBER_VICTIM)
    again = _choose(state, 2, record)

    assert again.state == first.state
    assert again.events == first.events


@pytest.mark.parametrize("resource", ["wood", "brick", "wool", "wheat", "ore"])
def test_the_draw_can_reach_every_resource_of_the_hand(resource: str) -> None:
    """Whatever a hand holds, that is exactly what can be taken out of it."""
    hex_id = _a_hex(_opening())
    stocked = _stocked(_opening(), 1, **{resource: 3})
    state = _move(_pair(stocked, hex_id), hex_id).state

    robbed = _choose(state, 1, SeededRandomSource(SEED))

    assert _steal(robbed)["resource"] == resource


def test_the_draw_is_uniform_over_the_cards_and_not_over_the_types() -> None:
    """RULES.md 4.9, ambiguity: a hand of 3 wood and 1 ore loses wood three times in four."""
    hex_id = _a_hex(_opening())
    stocked = _stocked(_opening(), 1, wood=3, ore=1)
    state = _move(_pair(stocked, hex_id), hex_id).state

    taken = [
        str(_steal(_choose(state, 1, SeededRandomSource(seed)))["resource"]) for seed in range(240)
    ]

    assert set(taken) == {"wood", "ore"}, "both cards are reachable"
    assert taken.count("wood") > 2 * taken.count("ore"), (
        "a card is drawn, not a resource type: three wood cards outweigh one ore card"
    )


def test_a_victim_holding_nothing_is_still_the_victim() -> None:
    """RULES.md 4.9 item 6: the steal is mandatory, and it may yield nothing."""
    hex_id = _a_hex(_opening())
    state = _lone(_opening(), hex_id, 1)
    assert state.hands[1] == NOTHING, "this fixture places a building and deals no cards"

    moved = _move(state, hex_id, NullRandomSource())

    assert moved.state.phase is Phase.ACTION
    assert _steal(moved) == {"player": 0, "victim": 1, "resource": None}, "nothing was taken"
    assert moved.state.hands[1] == NOTHING


def test_the_steal_moves_one_card_and_conserves_the_rest() -> None:
    hex_id = _a_hex(_opening())
    stocked = _stocked(_opening(), 1, wood=2, ore=1)
    state = _move(_pair(stocked, hex_id), hex_id).state

    robbed = _choose(state, 1, SeededRandomSource(SEED))

    assert sum(sum(hand) for hand in robbed.state.hands) == sum(sum(hand) for hand in state.hands)
    assert sum(robbed.state.hands[1]) == 2
    assert GAME.check_invariants(robbed.state) == []


def test_a_player_who_is_not_next_to_the_robber_cannot_be_robbed() -> None:
    hex_id = _a_hex(_opening())
    state = _move(_pair(_opening(), hex_id), hex_id).state

    refusal = _refusal(state, 3)

    assert refusal.code == ROBBER_VICTIM_NOT_ADJACENT
    assert dict(refusal.details)["candidates"] == [1, 2]


@pytest.mark.parametrize("victim", ["one", None, -1, 4, True])
def test_a_victim_that_is_not_a_seat_is_refused(victim: Any) -> None:
    """FR-18.2: the declared schema judges the shape of the parameter, before the rule."""
    hex_id = _a_hex(_opening())
    state = _move(_pair(_opening(), hex_id), hex_id).state

    refusal = _refusal(state, victim)

    assert refusal.code == BAD_PARAMS


def test_only_the_player_who_moved_it_may_choose() -> None:
    hex_id = _a_hex(_opening())
    state = _move(_pair(_opening(), hex_id), hex_id).state

    refusal = _refusal(state, 1, seat=3)

    assert refusal.code == NOT_YOUR_DECISION


def test_a_victim_cannot_be_named_before_the_robber_has_moved() -> None:
    """FR-12.3: the move comes first, so the choice of victim is not open yet."""
    hex_id = _a_hex(_opening())
    state = _pair(_opening(), hex_id)
    assert GAME.pending_decisions(state)[0].kind == phases.MOVE_ROBBER

    refusal = _refusal(state, 1)

    assert refusal.code == NO_SUCH_REQUEST
    assert dict(refusal.details)["phase"] == Phase.ROBBER.value


def test_the_choice_is_over_once_the_engine_has_made_it() -> None:
    """A lone candidate was robbed by the move, so the phase has moved on (item 5)."""
    hex_id = _a_hex(_opening())
    moved = _move(_stocked(_lone(_opening(), hex_id, 1), 1, wood=1), hex_id)

    refusal = _refusal(moved.state, 1)

    assert refusal.code == WRONG_PHASE
    assert dict(refusal.details)["phase"] == Phase.ACTION.value


def test_the_thief_and_the_victim_learn_different_things() -> None:
    """FR-12.5: the identity to the thief, the removal to the victim, nothing to anybody else."""
    hex_id = _a_hex(_opening())
    stocked = _stocked(_stocked(_opening(), 0, wool=1), 1, wood=2, ore=2)
    state = _move(_pair(stocked, hex_id), hex_id).state

    robbed = _choose(state, 1, SeededRandomSource(SEED))
    taken = str(_steal(robbed)["resource"])

    thief_hand = observe(robbed.state, 0)["hand"]
    victim_hand = observe(robbed.state, 1)["hand"]
    bystander = observe(robbed.state, 3)

    assert isinstance(thief_hand, dict)
    assert isinstance(victim_hand, dict)
    assert thief_hand[taken] == _held(state, 0, taken) + 1, "the thief sees the card it gained"
    assert victim_hand[taken] == _held(state, 1, taken) - 1, "the victim sees it leave"
    assert thief_hand != victim_hand, "and neither of them is shown the other's cards"
    assert "hands" not in bystander, "a third party is told nothing about anybody's hand"
    assert bystander["hand"] == {resource.value: 0 for resource in RESOURCE_ORDER}
    assert robbed.state.hands[1] != NOTHING, "the god view holds every hand, as always"


def test_the_robber_phase_is_over_once_the_steal_has_been_made() -> None:
    """Every step of a phase needs a mark of its own, or the step can be taken again.

    This is a regression test with a story. The engine accepted a victim choice over and over
    from the same mover, with the same two neighbours, for thousands of actions: the phase rule
    read "the robber has moved" and asked for a victim again, because nothing in the state
    recorded that the victim had already been chosen. It was found by the generator of golden
    game 3, which never reached a winner because it never left the robber phase.
    """
    hex_id = _a_hex(_opening())
    stocked = _stocked(_stocked(_opening(), 1, wood=2), 2, ore=2)
    state = _move(_pair(stocked, hex_id), hex_id).state
    assert GAME.pending_decisions(state), "the choice of victim is open"

    robbed = _choose(state, 1, SeededRandomSource(SEED))

    assert robbed.state.phase is Phase.ACTION, "the phase is over once the steal is made"
    assert [request.kind for request in GAME.pending_decisions(robbed.state)] == [phases.TAKE_TURN]
    again = GAME.apply(
        robbed.state,
        Action(player=0, type=phases.CHOOSE_ROBBER_VICTIM, params={"victim": 2}),
        NullRandomSource(),
    )
    assert isinstance(again, Rejected), "and the same hand cannot be robbed twice"
    assert sum(state.hands[1]) == 2, "the victim held two cards"
    assert sum(robbed.state.hands[1]) == 1, "exactly one of them left"


def test_the_whole_robber_flow_replays_from_its_record(tmp_path: Any) -> None:
    """FR-12.4 end to end: a steal made for real, replayed from the draws it recorded."""
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
    for _ in range(200):
        if run.state.phase is Phase.ROBBER:
            break
        if run.state.phase is Phase.TURN_PRODUCTION:
            action = Action(player=run.state.turn, type="roll_dice", params={})
        elif run.state.phase is Phase.DISCARD:
            request = run.pending[0]
            action = GAME.legal_actions(run.state, request.player)[0]
        else:
            action = Action(player=run.state.turn, type="end_turn", params={})
        assert isinstance(run.submit(action), Applied)
    assert run.state.phase is Phase.ROBBER, "this seed rolls a seven within two hundred actions"

    mover = run.state.turn
    destination = next(
        hex_.id
        for hex_ in run.state.board.topology.hexes
        if hex_.id != run.state.robber
        and any(
            run.state.hands[seat] != NOTHING
            for seat in robber_victims(replace(run.state, robber=hex_.id))
        )
    )
    assert isinstance(
        run.submit(Action(player=mover, type=phases.MOVE_ROBBER, params={"hex": destination})),
        Applied,
    )
    if run.state.phase is Phase.ROBBER:
        assert isinstance(run.submit(GAME.legal_actions(run.state, mover)[0]), Applied)
    moved_onto = run.state.robber
    run.finish()

    log = GameLogReader(god_log_path(tmp_path, "g-0001")).read()
    stolen = [
        event for record in log.actions for event in record.events if event.type == "robber_stole"
    ]

    assert len(stolen) == 1, "exactly one steal was made, however it was decided"
    assert dict(stolen[0].payload)["resource"] is not None, "a card changed hands on this seed"
    assert [record.phase for record in log.phases][-3:] == ["discard", "robber", "action"]
    assert verify(log, GAME).rejections == 0, "the replay draws the same card again"
    assert moved_onto != DESERT
