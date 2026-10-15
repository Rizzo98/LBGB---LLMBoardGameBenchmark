"""The Catan state and its serialisation (PRD-v1 FR-1.5; ARCHITECTURE.md 5.5, 6).

The state is the god view: every player's hand, the order of the undealt deck, everything
hidden. Hidden information is enforced at the projection boundary, not by keeping secrets from
the engine - so nothing here is private, and the tests below treat the whole state as
encodable and inspectable.

Two properties are load-bearing. **Totality**: every reachable state must serialise, because a
state that cannot be encoded is a state that cannot be hashed, logged or replayed. And
**stability**: the field set is fixed now, in slice 2, rather than grown as later slices need
it. Adding a field changes every recorded hash, so a field added after the golden corpus
exists would invalidate it; a field added before costs nothing.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import FrozenInstanceError, fields, replace
from typing import Any, Final

import pytest

from lgbg.core.canonical import CanonicalJsonError, hash_state, to_canonical_json
from lgbg.core.rng import KIND_SHUFFLE, SeededRandomSource
from lgbg.core.types import JsonValue
from lgbg.games.catan.board.generation import load_board
from lgbg.games.catan.state import (
    BANK_PER_RESOURCE,
    CANONICAL_DECK,
    CARD_ORDER,
    DECK_COMPOSITION,
    DEV_DECK_SHUFFLE,
    NO_OWNER,
    PIECES_PER_PLAYER,
    RESOURCE_ORDER,
    VICTORY_TARGET,
    CatanState,
    Phase,
    Placed,
    Supply,
    TradeOffer,
    decode_state,
    encode_state,
    initial_state,
)

PLAYERS: Final[int] = 4
SEED: Final[int] = 20250101


class _Encoder:
    """The slice of the game plugin interface that hashing needs."""

    def encode_state(self, state: Any) -> Any:
        return encode_state(state)


def _opening(seed: int = SEED) -> CatanState:
    board = load_board("standard_a")
    return initial_state(board, players=PLAYERS, rng=SeededRandomSource(seed))


def _populated() -> CatanState:
    """A state with every field carrying something, so totality is tested on all of it."""
    opening = _opening()
    placed = Placed(
        settlements=tuple(
            0 if vertex == 3 else 2 if vertex == 17 else NO_OWNER for vertex in range(54)
        ),
        cities=tuple(1 if vertex == 9 else NO_OWNER for vertex in range(54)),
        roads=tuple(3 if edge == 5 else NO_OWNER for edge in range(72)),
    )
    return replace(
        opening,
        phase=Phase.SETUP_ROUND_1,
        phase_index=5,
        turn=2,
        round=3,
        hands=((1, 2, 3, 4, 5), (0, 0, 0, 0, 0), (2, 0, 1, 0, 4), (1, 1, 1, 1, 1)),
        supply=(Supply(12, 4, 3), Supply(15, 5, 4), Supply(13, 2, 2), Supply(14, 3, 1)),
        placed=placed,
        dev_cards=((1, 1, 0, 0, 0), (0, 0, 0, 0, 0), (0, 2, 0, 0, 1), (3, 0, 0, 0, 0)),
        bought_this_turn=((1, 0, 0, 0, 0), (0, 0, 0, 0, 0), (0, 0, 0, 0, 1), (0, 0, 0, 0, 0)),
        played_this_turn=(0, 0, 1, 0),
        knights_played=(3, 0, 1, 2),
        discards_pending=(2, 0, 0, 1),
        offer=TradeOffer(offerer=2, give=(0, 2, 0, 0, 0), want=(0, 0, 0, 1, 0)),
        responses=(0, 1, 0, 2),
        longest_road=1,
        largest_army=3,
        robber=4,
        dice=(3, 4),
    )


def test_the_state_is_frozen_and_slotted() -> None:
    """A state that can be mutated in place is a state that can leak a partial transition."""
    state = _opening()

    with pytest.raises(FrozenInstanceError):
        state.turn = 2  # type: ignore[misc]

    assert not hasattr(state, "__dict__"), "slots, so nothing can be attached to a state"
    assert {field.name for field in fields(CatanState)} >= {"board", "hands", "placed", "dev_deck"}


def test_the_opening_state_carries_the_pinned_facts() -> None:
    state = _opening()

    assert state.players == PLAYERS
    assert state.phase is Phase.SETUP_ROUND_1
    assert state.turn == 0, "the snake draft starts with seat 0"
    assert state.round == 0
    assert state.phase_index == 0
    assert state.hands == ((0, 0, 0, 0, 0),) * PLAYERS
    assert state.bank == (BANK_PER_RESOURCE,) * len(RESOURCE_ORDER)
    assert state.supply == (Supply(*PIECES_PER_PLAYER),) * PLAYERS
    assert state.robber == state.board.desert_hex, "the robber starts on the desert"
    assert state.dice is None
    assert state.offer is None
    assert state.longest_road == NO_OWNER
    assert state.largest_army == NO_OWNER
    assert all(seat == NO_OWNER for seat in state.placed.settlements)
    assert len(state.dev_deck) == len(CANONICAL_DECK)


def test_the_deck_is_shuffled_at_the_start_by_the_pinned_draw() -> None:
    """RULES.md 3.1 D5: the deck is shuffled once, at game start, and recorded."""
    source = SeededRandomSource(SEED)

    state = initial_state(load_board("standard_a"), players=PLAYERS, rng=source)

    assert [(draw.purpose, draw.kind, dict(draw.args)) for draw in source.draws()] == [
        (DEV_DECK_SHUFFLE, KIND_SHUFFLE, {"n": len(CANONICAL_DECK)})
    ]
    assert sorted(state.dev_deck) == sorted(card.value for card in CANONICAL_DECK)


def test_the_initial_state_is_deterministic_for_a_seed_and_a_board() -> None:
    """FR-1.5: the same seed and board give the same state, and therefore the same hash."""
    first = hash_state(_opening(), _Encoder())
    again = hash_state(_opening(), _Encoder())
    other_seed = hash_state(_opening(seed=SEED + 1), _Encoder())

    assert first == again
    assert first != other_seed, "a different seed deals a different deck"


def test_the_encoding_is_json_and_free_of_floats() -> None:
    """Determinism contract, clause 2: integers only, no floats in state."""
    encoded = encode_state(_populated())

    text = to_canonical_json(encoded)

    assert text
    assert _types_in(json.loads(text)) <= {dict, list, str, int, bool, type(None)}


def test_every_field_survives_a_round_trip() -> None:
    state = _populated()

    restored = decode_state(encode_state(state))

    assert restored == state


def test_the_encoding_places_pieces_sparsely() -> None:
    """A record is read by people: three occupied vertices beat fifty-four minus ones."""
    encoded = _mapping(encode_state(_populated()), "state")
    placed = _mapping(encoded["placed"], "placed")

    assert placed["settlements"] == [[3, 0], [17, 2]]
    assert placed["cities"] == [[9, 1]]
    assert placed["roads"] == [[5, 3]]


def test_the_opening_state_encodes_its_empty_board_as_empty_lists() -> None:
    placed = _mapping(_mapping(encode_state(_opening()), "state")["placed"], "placed")

    assert dict(placed) == {"cities": [], "roads": [], "settlements": []}


def test_the_encoding_covers_the_board() -> None:
    """The board decides everything that happens on it, so the hash must cover it."""
    board = load_board("standard_a")
    state = initial_state(board, players=PLAYERS, rng=SeededRandomSource(1))
    encoded_board = _mapping(_mapping(encode_state(state), "state")["board"], "board")
    ports = [_mapping(entry, "port") for entry in _sequence(encoded_board["ports"], "ports")]

    assert encoded_board["terrain"] == [terrain.value for terrain in board.terrain]
    assert [port["edge"] for port in ports] == [port.edge for port in board.ports]
    assert [port["ratio"] for port in ports] == [port.ratio for port in board.ports]
    assert encoded_board["hexes"] == len(board.topology.hexes)
    assert encoded_board["token_start_hex"] == board.token_start_hex
    assert encoded_board["name"] == board.name


def test_the_canonical_orders_are_pinned() -> None:
    """Hands and decks are counts in a canonical order, so the order has to be asserted."""
    assert [resource.value for resource in RESOURCE_ORDER] == [
        "brick",
        "wood",
        "wool",
        "wheat",
        "ore",
    ], "RULES.md section 3 pins this order for every list, projection and hash"
    assert [card.value for card in CARD_ORDER] == [
        "knight",
        "victory_point",
        "road_building",
        "year_of_plenty",
        "monopoly",
    ]
    assert sum(DECK_COMPOSITION.values()) == 25
    assert len(CANONICAL_DECK) == 25
    assert {card: CANONICAL_DECK.count(card) for card in CARD_ORDER} == dict(DECK_COMPOSITION)
    assert VICTORY_TARGET == 10
    assert PIECES_PER_PLAYER == (15, 5, 4)


def test_the_opening_state_consumes_exactly_one_draw() -> None:
    source = SeededRandomSource(7)

    initial_state(load_board("standard_a"), players=PLAYERS, rng=source)

    assert len(source.draws()) == 1


def test_decoding_rejects_a_blob_that_is_not_a_state() -> None:
    with pytest.raises(ValueError, match="board"):
        decode_state({"players": 4})

    with pytest.raises(ValueError, match="players"):
        decode_state({"players": "four"})


def test_the_encoding_refuses_a_float_in_state() -> None:
    """A float in state would make the record unhashable; it must fail loudly, not silently."""
    state = replace(_populated(), round=1.5)  # type: ignore[arg-type]

    with pytest.raises(CanonicalJsonError):
        to_canonical_json(encode_state(state))


def _mapping(value: JsonValue, what: str) -> Mapping[str, JsonValue]:
    assert isinstance(value, Mapping), f"{what} is not a JSON object: {value!r}"
    return value


def _sequence(value: JsonValue, what: str) -> Sequence[JsonValue]:
    assert not isinstance(value, str), f"{what} is a string, not a JSON array: {value!r}"
    assert isinstance(value, Sequence), f"{what} is not a JSON array: {value!r}"
    return value


def _types_in(value: Any) -> set[type]:
    """Every JSON type used anywhere in a structure."""
    if isinstance(value, dict):
        found: set[type] = {dict}
        for item in value.values():
            found |= _types_in(item)
        return found
    if isinstance(value, list):
        found = {list}
        for item in value:
            found |= _types_in(item)
        return found
    return {type(value)}
