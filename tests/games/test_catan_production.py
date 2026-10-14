"""Production (PRD-v1 FR-10.3; RULES.md 4.5).

What the dice pay: one card per settlement and two per city, on every hex showing the rolled
number that the robber is not sitting on. The distribution is computed for everyone before it
is applied, which is what makes the bank-shortage rule of 4.6 meaningful - "the players
affected" is only well defined if the demand is known before anything is handed out.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Final

from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.game import Applied, get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.rng import SeededRandomSource
from lgbg.core.run import GameRun
from lgbg.core.types import Action
from lgbg.games.catan.rules.production import produce
from lgbg.games.catan.state import (
    BANK_PER_RESOURCE,
    RESOURCE_ORDER,
    CatanState,
    Phase,
    Placed,
)

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20250901


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _token_hex(state: CatanState, total: int) -> int:
    """A hex showing this number, which is not the desert and not under the robber."""
    return next(
        hex_.id
        for hex_ in state.board.topology.hexes
        if state.board.tokens[hex_.id] == total and hex_.id != state.robber
    )


def _with(
    state: CatanState,
    *,
    settlements: Sequence[tuple[int, int]] = (),
    cities: Sequence[tuple[int, int]] = (),
) -> CatanState:
    """A state with buildings placed by hand, since placement rules are another card's business."""
    placed = state.placed
    seats = list(placed.settlements)
    city_seats = list(placed.cities)
    for vertex, seat in settlements:
        seats[vertex] = seat
    for vertex, seat in cities:
        city_seats[vertex] = seat
    return replace(
        state,
        placed=Placed(tuple(seats), tuple(city_seats), placed.roads),
        phase=Phase.TURN_PRODUCTION,
    )


def _hand(state: CatanState, seat: int) -> dict[str, int]:
    return {
        resource.value: state.hands[seat][index] for index, resource in enumerate(RESOURCE_ORDER)
    }


def _payload(events: list[Any]) -> dict[str, Any]:
    return dict(next(event.payload for event in events if event.type == "production"))


def test_a_settlement_on_a_producing_hex_earns_one_card() -> None:
    state = _opening()
    hex_id = _token_hex(state, 5)
    vertex = state.board.topology.vertices_of_hex(hex_id)[0]
    before = _with(state, settlements=[(vertex, 1)])

    after, events = produce(before, 5)

    resource = state.board.resource_of_hex(hex_id)
    assert resource is not None
    assert _hand(after, 1)[resource.value] == 1
    assert hex_id in _payload(events)["hexes"], "every hex showing the total is listed"


def test_a_city_earns_two_cards() -> None:
    state = _opening()
    hex_id = _token_hex(state, 6)
    vertex = state.board.topology.vertices_of_hex(hex_id)[0]
    before = _with(state, cities=[(vertex, 2)])

    after, _events = produce(before, 6)

    resource = state.board.resource_of_hex(hex_id)
    assert resource is not None
    assert _hand(after, 2)[resource.value] == 2


def test_two_players_on_the_same_hex_both_earn() -> None:
    state = _opening()
    hex_id = _token_hex(state, 8)
    first, second = state.board.topology.vertices_of_hex(hex_id)[:2]
    before = _with(state, settlements=[(first, 0), (second, 3)])

    after, _events = produce(before, 8)

    resource = state.board.resource_of_hex(hex_id)
    assert resource is not None
    assert _hand(after, 0)[resource.value] == 1
    assert _hand(after, 3)[resource.value] == 1


def test_a_hex_under_the_robber_earns_nothing() -> None:
    state = _opening()
    hex_id = _token_hex(state, 9)
    vertex = state.board.topology.vertices_of_hex(hex_id)[0]
    blocked = replace(_with(state, settlements=[(vertex, 1)]), robber=hex_id)

    after, _events = produce(blocked, 9)

    assert after.hands[1] == (0,) * len(RESOURCE_ORDER)


def test_hexes_showing_another_number_earn_nothing() -> None:
    state = _opening()
    hex_id = _token_hex(state, 4)
    vertex = state.board.topology.vertices_of_hex(hex_id)[0]
    before = _with(state, settlements=[(vertex, 1)])

    after, _events = produce(before, 10)

    assert after.hands[1] == (0,) * len(RESOURCE_ORDER)


def test_a_seven_earns_nothing_at_all() -> None:
    """FR-10.5: a seven skips production entirely, whatever is on the board."""
    state = _opening()
    vertex = state.board.topology.vertices_of_hex(_token_hex(state, 5))[0]
    before = _with(state, settlements=[(vertex, 1)])

    after, events = produce(before, 7)

    assert after == before
    assert events == []


def test_the_event_names_every_recipient_and_amount() -> None:
    state = _opening()
    hex_id = _token_hex(state, 5)
    vertex = state.board.topology.vertices_of_hex(hex_id)[0]
    before = _with(state, settlements=[(vertex, 2)])

    _after, events = produce(before, 5)

    payload = _payload(events)
    resource = state.board.resource_of_hex(hex_id)
    assert resource is not None
    assert payload["total"] == 5
    assert payload["granted"] == {"2": {resource.value: 1}}
    assert payload["shortfall"] == {}


def test_production_conserves_resources_and_never_overdraws_the_bank() -> None:
    state = _opening()
    hex_id = _token_hex(state, 5)
    vertices = state.board.topology.vertices_of_hex(hex_id)
    before = _with(state, settlements=[(vertex, 0) for vertex in vertices])

    after, _events = produce(before, 5)

    for index in range(len(RESOURCE_ORDER)):
        held = sum(hand[index] for hand in after.hands)
        assert after.bank[index] + held == BANK_PER_RESOURCE
        assert after.bank[index] >= 0


def test_the_demand_is_known_before_anything_is_paid() -> None:
    """RULES.md 4.5 item 4: a short bank is reported as a shortfall, not silently shared out."""
    state = _opening()
    hex_id = _token_hex(state, 5)
    vertices = state.board.topology.vertices_of_hex(hex_id)
    resource = state.board.resource_of_hex(hex_id)
    assert resource is not None
    index = RESOURCE_ORDER.index(resource)
    bank = list(state.bank)
    bank[index] = 1
    starved = replace(
        _with(state, settlements=[(vertex, 0) for vertex in vertices]), bank=tuple(bank)
    )

    after, events = produce(starved, 5)

    payload = _payload(events)
    assert payload["granted"] == {"0": {resource.value: 1}}
    assert payload["shortfall"] == {"0": {resource.value: len(vertices) - 1}}
    assert after.bank[index] == 0


def test_the_roll_pays_production_end_to_end() -> None:
    """The roll and the payment are one record: draws, total, and what everyone received."""
    state = _opening()
    hex_id = _token_hex(state, 5)
    vertex = state.board.topology.vertices_of_hex(hex_id)[0]
    ready = _with(state, settlements=[(vertex, 1)])
    source = SeededRandomSource(SEED)

    result = GAME.apply(ready, Action(player=0, type="roll_dice", params={}), source)

    assert isinstance(result, Applied)
    total = sum(result.state.dice)
    kinds = [event.type for event in result.events]
    asset = total != 7
    assert ("production" in kinds) is asset
    if asset:
        paid = dict(next(e for e in result.events if e.type == "production").payload)
        assert paid["total"] == total, "the event explains which number produced"
        names = [resource.value for resource in RESOURCE_ORDER]
        granted: Any = paid["granted"]
        for seat, amounts in dict(granted).items():
            for resource, amount in dict(amounts).items():
                assert result.state.hands[int(seat)][names.index(resource)] >= int(amount)


def test_production_plays_through_a_whole_turn(tmp_path: Any) -> None:
    """The same guarantees as the draft: the turn replays with every hash verified."""
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
    rolled = run.submit(Action(player=run.state.turn, type="roll_dice", params={}))
    assert isinstance(rolled, Applied)
    run.finish()

    log = GameLogReader(god_log_path(tmp_path, "g-0001")).read()
    from lgbg.core.replay import verify

    kinds = [event.type for event in log.actions[-1].events]

    assert verify(log, GAME).actions == 17
    assert kinds[0] == "dice_rolled", "the roll is the last action, and it is recorded"
