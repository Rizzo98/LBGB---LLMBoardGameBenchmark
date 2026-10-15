"""One leak test per hidden field (PRD-v1 FR-16.6, the table's test_projection_leaks; FR-16.1-16.3).

A projection is only as good as the proof that nothing else got through, and "nothing else" is
hard to enumerate by reading a dictionary. The tests here use the strongest available form of the
claim - **indistinguishability**: two positions that differ *only* in hidden information must
project to exactly the same observation for every observer who is not entitled to see it. If a
single byte of another player's hand, of the development deck or of the hold-back state were
reachable, the two observations would differ.

Every test is paired with a control: the spectator *does* see the difference, so a passing
indistinguishability test cannot be passing because the two positions were the same position.
The last test repeats the whole thing through the renderer, because a projection that is clean
and a renderer that prints something else is still a leak (FR-16.6).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, Final

import pytest

from lgbg.core.rng import SeededRandomSource
from lgbg.core.types import JsonValue
from lgbg.games.catan.board.generation import load_board
from lgbg.games.catan.notation import Detail, render
from lgbg.games.catan.projection import (
    PLAYER_OBSERVATION_FIELDS,
    SPECTATOR_OBSERVATION_FIELDS,
    observe,
    observe_spectator,
)
from lgbg.games.catan.state import CARD_ORDER, RESOURCE_ORDER, CatanState, initial_state

PLAYERS: Final[int] = 4
SEED: Final[int] = 20251006
SEATS: Final[tuple[int, ...]] = tuple(range(PLAYERS))


def _opening() -> CatanState:
    return initial_state(load_board("standard_a"), players=PLAYERS, rng=SeededRandomSource(SEED))


def _hand(**counts: int) -> tuple[int, ...]:
    """A hand named by resource, so a test never depends on the canonical order by accident."""
    assert set(counts) <= {resource.value for resource in RESOURCE_ORDER}
    return tuple(counts.get(resource.value, 0) for resource in RESOURCE_ORDER)


def _cards(**counts: int) -> tuple[int, ...]:
    assert set(counts) <= {card.value for card in CARD_ORDER}
    return tuple(counts.get(card.value, 0) for card in CARD_ORDER)


def _dealt(state: CatanState, hands: Mapping[int, tuple[int, ...]]) -> CatanState:
    """Deal those hands out of the bank, so the position conserves cards like a real one."""
    rows = [list(hand) for hand in state.hands]
    bank = list(state.bank)
    for seat, hand in hands.items():
        for index, count in enumerate(hand):
            rows[seat][index] = count
            bank[index] -= count
    assert min(bank) >= 0, "a hand cannot hold cards the bank does not have"
    return replace(state, hands=tuple(tuple(row) for row in rows), bank=tuple(bank))


def _holds(state: CatanState, seat: int, hand: tuple[int, ...]) -> CatanState:
    """One seat's hand, leaving every other seat's exactly as it was."""
    return _dealt(state, {seat: hand})


def _swapped(state: CatanState, first: int, second: int) -> CatanState:
    """Two seats trade hands.

    The one construction that changes a hidden composition while leaving *every public fact*
    alone: the bank is untouched, every hand size is untouched, and only the two owners can
    tell the difference. Anything an observer could notice would have to have come from the
    cards themselves.
    """
    rows = list(state.hands)
    rows[first], rows[second] = rows[second], rows[first]
    return replace(state, hands=tuple(rows))


def _others(seat: int) -> tuple[int, ...]:
    return tuple(other for other in SEATS if other != seat)


def _text(observation: Mapping[str, JsonValue], detail: Detail) -> str:
    return render(observation, detail=detail)


def test_a_player_sees_their_own_hand_exactly_and_only_its_size_of_others() -> None:
    """FR-16.1, FR-16.2: exact for me, a total for you."""
    state = _dealt(
        _opening(), {0: _hand(wood=2, ore=1), 1: _hand(brick=3), 2: _hand(wool=1, wheat=1)}
    )

    mine = observe(state, 0)
    theirs = observe(state, 1)

    assert mine["hand"] == {"brick": 0, "wood": 2, "wool": 0, "wheat": 0, "ore": 1}
    assert theirs["hand"] == {"brick": 3, "wood": 0, "wool": 0, "wheat": 0, "ore": 0}
    assert mine["hand_counts"] == [3, 3, 2, 0], "every hand's size is on the table"
    assert theirs["hand_counts"] == mine["hand_counts"], "and it is the same fact for everybody"


def test_another_players_hand_composition_is_not_reachable() -> None:
    """FR-16.2, the dedicated leak test: same sizes, swapped cards, same observation."""
    before = _dealt(_opening(), {1: _hand(wood=3), 2: _hand(ore=3)})
    after = _swapped(before, 1, 2)

    for observer in (0, 3):
        assert observe(before, observer) == observe(after, observer), (
            f"seat {observer} can tell three wood from three ore in somebody else's hand"
        )
    for owner in (1, 2):
        assert observe(before, owner) != observe(after, owner), "the owners see their own cards"
    assert observe(before, 0)["hand_counts"] == observe(after, 0)["hand_counts"]
    assert observe_spectator(before) != observe_spectator(after), "control: the states do differ"


def test_the_development_deck_order_is_not_reachable() -> None:
    """FR-16.3: the order is drawn once at the start and is nobody's information but the god's."""
    before = _opening()
    after = replace(before, dev_deck=tuple(reversed(before.dev_deck)))
    assert before.dev_deck != after.dev_deck, "control: the two decks are different orders"

    for observer in SEATS:
        assert observe(before, observer) == observe(after, observer)
    assert observe_spectator(before) != observe_spectator(after)


def test_another_players_development_cards_are_not_reachable() -> None:
    """FR-16.3: other players' dev cards are a count at most, never which cards they are."""
    before = _opening()
    after = replace(
        before,
        dev_cards=(
            before.dev_cards[0],
            _cards(knight=2),
            before.dev_cards[2],
            before.dev_cards[3],
        ),
    )
    assert before.dev_cards != after.dev_cards, "control: seat 1 holds different cards"

    for observer in _others(1):
        assert observe(before, observer) == observe(after, observer)
    assert observe_spectator(before) != observe_spectator(after)


def test_what_another_player_owes_the_bank_is_not_reachable() -> None:
    """The discard a seven forces is asked of the player it belongs to, not announced."""
    before = _dealt(_opening(), {2: _hand(wood=4, ore=4)})
    after = replace(before, discards_pending=(0, 0, 4, 0))
    assert before.discards_pending != after.discards_pending, "control"

    for observer in _others(2):
        assert observe(before, observer) == observe(after, observer)
    assert observe_spectator(before) != observe_spectator(after)


def test_a_trade_offer_is_not_reachable_before_it_is_made() -> None:
    """An offer belongs to the table once it is made; until then it is nobody's fact."""
    before = _opening()
    after = replace(before, responses=(1, 0, 0, 1))
    assert before.responses != after.responses, "control"

    for observer in SEATS:
        assert observe(before, observer) == observe(after, observer)
    assert observe_spectator(before) != observe_spectator(after)


def test_the_players_view_holds_no_field_it_was_not_granted() -> None:
    """FR-16.5: the allow-list is the only gate, and every name in it was chosen deliberately."""
    state = _dealt(_opening(), {0: _hand(wood=1)})

    for observer in SEATS:
        assert set(observe(state, observer)) == PLAYER_OBSERVATION_FIELDS
    assert "hands" not in PLAYER_OBSERVATION_FIELDS
    assert "hand_counts" in SPECTATOR_OBSERVATION_FIELDS, "the spectator sees a superset"


@pytest.mark.parametrize("detail", [Detail.FULL, Detail.COMPACT])
def test_the_rendering_of_a_projection_leaks_nothing_either(detail: Detail) -> None:
    """FR-16.6: a clean projection printed by a renderer that says more is still a leak."""
    before = _dealt(_opening(), {1: _hand(wood=3), 2: _hand(ore=3)})
    after = _swapped(before, 1, 2)

    rendered = [_text(observe(before, observer), detail) for observer in (0, 3)]
    swapped = [_text(observe(after, observer), detail) for observer in (0, 3)]

    assert rendered == swapped, "the renderer added what the projection had left out"
    for text in rendered:
        assert "wood 3" not in text, "a hand the projection never held appeared in the text"
        assert "ore 3" not in text
    assert "wood 3" in _text(observe(before, 1), detail), "the owner's own hand is rendered"
    assert "ore 3" in _text(observe(after, 1), detail), "and the control has two sides"
    assert _text(observe_spectator(before), detail) != _text(observe_spectator(after), detail)


def test_no_composition_appears_anywhere_in_a_players_observation() -> None:
    """The same claim in its blunt form: walk the whole value and look for a hand."""
    state = _dealt(_opening(), {1: _hand(wood=2, ore=1), 2: _hand(wool=3)})

    for observer in SEATS:
        observation: Any = observe(state, observer)
        rows = _rows(observation)

        hidden = [list(state.hands[other]) for other in _others(observer)]
        assert not [hand for hand in hidden if hand in rows], (
            f"seat {observer} can read another seat's whole hand out of a row of the observation"
        )
        assert [row for row in rows if len(row) == len(RESOURCE_ORDER)] == [], (
            "a row of five counts would be a whole hand, and no hand belongs in a player's view"
        )
        own = observation["hand"]
        assert isinstance(own, Mapping)
        assert [own[resource.value] for resource in RESOURCE_ORDER] == list(
            state.hands[observer]
        ), "the one composition the view does hold is the observer's own"


def _rows(observation: Mapping[str, JsonValue]) -> list[Any]:
    """Every list of numbers in the observation, at any depth: the shape a hand would take."""
    found: list[Any] = []

    def walk(value: JsonValue) -> None:
        if isinstance(value, Mapping):
            for entry in value.values():
                walk(entry)
        elif isinstance(value, Sequence) and not isinstance(value, str):
            if value and all(isinstance(entry, int) for entry in value):
                found.append(list(value))
            for entry in value:
                walk(entry)

    walk(dict(observation))
    return found
