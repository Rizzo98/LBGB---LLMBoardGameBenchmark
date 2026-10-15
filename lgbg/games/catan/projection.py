"""What an observer may see (ARCHITECTURE.md 7.8; PRD-v1 FR-16.5, FR-16.7).

The engine holds a god view. Hidden information is enforced *here*, at the projection
boundary, and nowhere else: the state keeps every secret, and this module decides which of
them an observer is told.

It is built from an **allow-list**. The observation is assembled by walking
`PLAYER_FIELDS` - a declared list of (name, extractor) pairs - so a field added to the state
appears in nobody's view until somebody adds it here. A deny-list would fail open on the day
state grows, and nobody would notice.

Two projections, deliberately. A player's view and the spectator's are different artefacts:
with hidden victory-point cards, "who is ahead" is not determinable from any player's view,
so analysis and replay use the spectator's, and it is tested on its own.

What slice 2 shows: the board, the robber, every player's placed pieces, the public turn state
and the bank. Slice 3 adds the one hand a player is entitled to see - their own - because a
steal is only observable to the two players it touches if each of them can see their own cards
(FR-12.5). The other players' hands are still absent, and the development deck with them; each
arrives with the slice that needs it, and with the leak test that proves it does not escape.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from lgbg.core.types import JsonValue, Observation, PlayerId
from lgbg.games.catan.rules import victory
from lgbg.games.catan.state import NO_OWNER, RESOURCE_ORDER, CatanState

Projector = Callable[[CatanState], JsonValue]


def _board(state: CatanState) -> JsonValue:
    return {
        "hexes": [
            {
                "id": hex_.id,
                "terrain": state.board.terrain[hex_.id].value,
                "token": state.board.tokens[hex_.id],
            }
            for hex_ in state.board.topology.hexes
        ],
        "ports": [
            {
                "edge": port.edge,
                "ratio": port.ratio,
                "resource": None if port.resource is None else port.resource.value,
            }
            for port in state.board.ports
        ],
    }


def _robber(state: CatanState) -> JsonValue:
    return state.robber


def _pieces(state: CatanState) -> JsonValue:
    return {
        "cities": _occupied(state.placed.cities),
        "roads": _occupied(state.placed.roads),
        "settlements": _occupied(state.placed.settlements),
    }


def _occupied(occupancy: tuple[int, ...]) -> JsonValue:
    return [[site, seat] for site, seat in enumerate(occupancy) if seat != NO_OWNER]


def _supply(state: CatanState) -> JsonValue:
    return [[item.roads, item.settlements, item.cities] for item in state.supply]


def _bank(state: CatanState) -> JsonValue:
    return {resource.value: state.bank[index] for index, resource in enumerate(RESOURCE_ORDER)}


def _hand_counts(state: CatanState) -> JsonValue:
    """How many cards each seat holds: public, and the only thing said about their hands (16.2).

    A hand is held face up in count and face down in kind - players count each other's cards
    across the table - so the size of a hand is information the rules assume everybody has. What
    the size is *made of* is what the projection must not say, and the leak test asserts it by
    swapping two hands of equal size and requiring every other observer to see no change.
    """
    return [sum(hand) for hand in state.hands]


def _awards(state: CatanState) -> JsonValue:
    return {"largest_army": state.largest_army, "longest_road": state.longest_road}


PLAYER_FIELDS: Final[tuple[tuple[str, Projector], ...]] = (
    ("awards", _awards),
    ("bank", _bank),
    ("board", _board),
    ("dice", lambda state: None if state.dice is None else list(state.dice)),
    ("hand_counts", _hand_counts),
    ("phase", lambda state: state.phase.value),
    ("pieces", _pieces),
    ("robber", _robber),
    ("round", lambda state: state.round),
    ("supply", _supply),
    ("turn", lambda state: state.turn),
)
"""The allow-list for a player's view. A field is here because it was named, and for a reason."""

SPECTATOR_FIELDS: Final[tuple[tuple[str, Projector], ...]] = (
    *PLAYER_FIELDS,
    ("bought_this_turn", lambda state: [list(counts) for counts in state.bought_this_turn]),
    ("dev_cards", lambda state: [list(counts) for counts in state.dev_cards]),
    ("dev_deck", lambda state: list(state.dev_deck)),
    ("discards_pending", lambda state: list(state.discards_pending)),
    ("hands", lambda state: [list(counts) for counts in state.hands]),
    ("knights_played", lambda state: list(state.knights_played)),
    (
        "offer",
        lambda state: (
            None
            if state.offer is None
            else {
                "give": list(state.offer.give),
                "offerer": state.offer.offerer,
                "want": list(state.offer.want),
            }
        ),
    ),
    ("played_this_turn", lambda state: list(state.played_this_turn)),
    ("responses", lambda state: list(state.responses)),
)
"""The allow-list for the spectator's view: the player's, plus what the god view holds back."""

ObserverProjector = Callable[[CatanState, PlayerId], JsonValue]


def _own_hand(state: CatanState, player: PlayerId) -> JsonValue:
    """The observer's own hand, and nobody else's (FR-12.5, FR-16.5)."""
    if not 0 <= player < state.players:
        return None
    return {
        resource.value: state.hands[player][index] for index, resource in enumerate(RESOURCE_ORDER)
    }


def _points(state: CatanState, player: PlayerId) -> JsonValue:
    """Every player's score: the observer's exact, everybody else's as far as it can be computed.

    A player can always count their own victory-point cards and can never see anybody else's
    (FR-16.4), so this is the one field whose answer depends on both who is asking and which seat
    it is about.
    """
    if not 0 <= player < state.players:
        return None
    return {
        str(seat): (
            victory.victory_points(state, seat)
            if seat == player
            else victory.public_points(state, seat)
        )
        for seat in range(state.players)
    }


OBSERVER_FIELDS: Final[tuple[tuple[str, ObserverProjector], ...]] = (
    ("hand", _own_hand),
    ("points", _points),
)
"""The fields whose answer depends on *who is asking*.

An observer-relative field is not in the spectator's view at all, which is why the spectator's
allow-list is a superset of the player's minus this list: the spectator has no hand of their own,
and 'everyone's hand' is a different field with a different shape. Declaring the difference is
what keeps 'the spectator sees everything a player sees' an assertion rather than a hope.
"""

PLAYER_OBSERVATION_FIELDS: Final[frozenset[str]] = frozenset(
    {*(name for name, _ in PLAYER_FIELDS), *(name for name, _ in OBSERVER_FIELDS)}
)
SPECTATOR_OBSERVATION_FIELDS: Final[frozenset[str]] = frozenset(
    name for name, _ in SPECTATOR_FIELDS
)


def observe(state: CatanState, player: PlayerId) -> Observation:
    """What one player may see.

    The observer is a parameter rather than a flag, so a view that differs *between* players
    needs no new interface: the public position is the same for everybody, and the fields that
    are about the observer are appended for the observer alone (FR-16.5).
    """
    observation = dict(_project(state, PLAYER_FIELDS))
    for name, extract in OBSERVER_FIELDS:
        observation[name] = extract(state, player)
    return observation


def observe_spectator(state: CatanState) -> Observation:
    """The full god view, for analysis and replay (FR-16.7)."""
    return _project(state, SPECTATOR_FIELDS)


def _project(state: CatanState, fields: tuple[tuple[str, Projector], ...]) -> Observation:
    return {name: extract(state) for name, extract in fields}
