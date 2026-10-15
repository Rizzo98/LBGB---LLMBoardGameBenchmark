"""The opening draft (RULES.md 4.3; PRD-v1 FR-8.1, FR-8.2, FR-8.3, FR-8.5).

Setup is a phase like any other. It emits decision requests, it closes when they are answered,
and it shares the ordinary action path - no special case, which is the point of FR-8.5: a draft
implemented as a special case is a draft whose bugs appear only in drafts, and whose
projection and concurrency behaviour the ordinary turn loop never exercises.

The draft is eight steps in snake order: seats ascending, then descending. Each step is two
decisions by the same player - a settlement, then a road attached to it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from lgbg.core.errors import BAD_PARAMS, NOT_YOUR_DECISION, Rejection
from lgbg.core.game import Applied, ApplyResult, Rejected
from lgbg.core.rng import RandomSource
from lgbg.core.types import Action, Event, JsonValue
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.rejections import (
    EDGE_OCCUPIED,
    NO_PIECES_REMAINING,
    NOT_CONNECTED,
    TOO_CLOSE,
    VERTEX_OCCUPIED,
)
from lgbg.games.catan.rules.building import neighbouring_vertices, piece_taken, spend_piece
from lgbg.games.catan.state import NO_OWNER, RESOURCE_ORDER, CatanState, Placed


def setup_order(players: int) -> tuple[int, ...]:
    """The snake: seats ascending, then descending (FR-8.1).

    Derived rather than written down, so the rulebook's four-player order is a consequence of
    the shape rather than a literal that a different seat count would silently falsify.
    """
    ascending = tuple(range(players))
    return ascending + tuple(reversed(ascending))


def selection(state: CatanState) -> int:
    """Which of the eight steps is being drafted, derived from the roads on the board."""
    return _placed(state.placed.roads)


def current_player(state: CatanState) -> int:
    """Whose step it is: the snake order indexed by the steps already drafted."""
    return setup_order(state.players)[selection(state)]


def place_settlement(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Place this step's settlement on a legal empty vertex (RULES.md 4.3 item 4)."""
    del rng  # the draft consumes no randomness
    if action.player != state.turn:
        return Rejected(
            Rejection(
                code=NOT_YOUR_DECISION,
                message=f"seat {action.player} is not to act; seat {state.turn} is",
                details={"turn": state.turn},
            )
        )
    site = _site(action, "vertex", len(state.placed.settlements))
    if isinstance(site, Rejected):
        return site
    if state.supply[action.player].settlements < 1:
        return Rejected(
            Rejection(
                code=NO_PIECES_REMAINING,
                message="every settlement this player has is already on the board",
                details={"player": action.player},
            )
        )
    if _occupied(state.placed.settlements, site) or _occupied(state.placed.cities, site):
        return Rejected(
            Rejection(
                code=VERTEX_OCCUPIED,
                message="that vertex already carries a building",
                details={"vertex": site},
            )
        )
    crowded = sorted(
        neighbour
        for neighbour in neighbouring_vertices(state, site)
        if _occupied(state.placed.settlements, neighbour)
        or _occupied(state.placed.cities, neighbour)
    )
    if crowded:
        return Rejected(
            Rejection(
                code=TOO_CLOSE,
                message="an adjacent vertex carries a building, and settlements stay two apart",
                details={"vertex": site, "blocked_by": crowded},
            )
        )

    placed = Placed(
        settlements=_with_seat(state.placed.settlements, site, action.player),
        cities=state.placed.cities,
        roads=state.placed.roads,
    )
    supply = spend_piece(state, action.player, "settlements")
    updated = replace(state, placed=placed, supply=supply, setup_vertex=site)
    events = [
        Event(
            type="settlement_placed",
            payload={
                "player": action.player,
                "vertex": site,
                "terrain": _terrain_around(state, site),
            },
        ),
        piece_taken(action.player, "settlement", supply[action.player].settlements),
    ]
    # The second settlement is endowed immediately, and that is also what makes the endowment
    # order of RULES.md 4.3 item 7 (seats 3, 2, 1, 0) a consequence rather than a rule: the
    # players take theirs in the order they place.
    if selection(state) >= state.players:
        updated, endowment = _endow(updated, action.player, site)
        events.append(endowment)
    return Applied(state=updated, events=events)


def _endow(state: CatanState, player: int, vertex: int) -> tuple[CatanState, Event]:
    """One card from the bank for each adjacent hex, of that hex's type (RULES.md 4.3 item 6).

    The bank is finite and its shortfall is defined rather than accidental: a player takes
    what remains and loses the rest (item 8). The resources are walked in canonical order, so
    the event - and therefore the record - is stable.
    """
    wanted: dict[Resource, int] = {}
    for hex_id in state.board.topology.hexes_at(vertex):
        resource = state.board.resource_of_hex(hex_id)
        if resource is not None:
            wanted[resource] = wanted.get(resource, 0) + 1

    bank = list(state.bank)
    hands = [list(hand) for hand in state.hands]
    granted: dict[str, int] = {}
    shortfall: dict[str, int] = {}
    for resource in RESOURCE_ORDER:
        count = wanted.get(resource, 0)
        if count == 0:
            continue
        index = RESOURCE_ORDER.index(resource)
        taken = min(count, bank[index])
        if taken:
            bank[index] -= taken
            hands[player][index] += taken
            granted[resource.value] = taken
        if taken < count:
            shortfall[resource.value] = count - taken

    return (
        replace(state, bank=tuple(bank), hands=tuple(tuple(hand) for hand in hands)),
        Event(
            type="resources_granted",
            payload={
                "player": player,
                "vertex": vertex,
                "granted": granted,
                "shortfall": shortfall,
            },
        ),
    )


def place_road(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Place this step's road on a legal empty edge attached to the new settlement."""
    del rng
    if action.player != state.turn:
        return Rejected(
            Rejection(
                code=NOT_YOUR_DECISION,
                message=f"seat {action.player} is not to act; seat {state.turn} is",
                details={"turn": state.turn},
            )
        )
    site = _site(action, "edge", len(state.placed.roads))
    if isinstance(site, Rejected):
        return site
    if state.setup_vertex == NO_OWNER:
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message="no settlement is waiting for a road: place the settlement first",
                details={"phase": state.phase.value},
            )
        )
    if state.supply[action.player].roads < 1:
        return Rejected(
            Rejection(
                code=NO_PIECES_REMAINING,
                message="the player has no road left in supply",
                details={"player": action.player},
            )
        )
    if _occupied(state.placed.roads, site):
        return Rejected(
            Rejection(
                code=EDGE_OCCUPIED,
                message="that edge already carries a road",
                details={"edge": site},
            )
        )
    if state.setup_vertex not in state.board.topology.vertices_of_edge(site):
        return Rejected(
            Rejection(
                code=NOT_CONNECTED,
                message="a setup road must attach to the settlement placed in this same step",
                details={
                    "edge": site,
                    "must_touch": state.setup_vertex,
                    "touches": list(state.board.topology.vertices_of_edge(site)),
                },
            )
        )

    placed = Placed(
        settlements=state.placed.settlements,
        cities=state.placed.cities,
        roads=_with_seat(state.placed.roads, site, action.player),
    )
    supply = spend_piece(state, action.player, "roads")
    following = _next_player(state)
    return Applied(
        state=replace(state, placed=placed, supply=supply, setup_vertex=NO_OWNER, turn=following),
        events=[
            Event(
                type="road_placed",
                payload={"player": action.player, "edge": site, "next_player": following},
            ),
            piece_taken(action.player, "road", supply[action.player].roads),
        ],
    )


def _next_player(state: CatanState) -> int:
    """Whose step follows, or the same seat when the draft is finished."""
    order = setup_order(state.players)
    following = selection(state) + 1
    return order[following] if following < len(order) else state.turn


def _terrain_around(state: CatanState, vertex: int) -> list[JsonValue]:
    """The terrain of the hexes meeting a vertex, which is what the endowment is made of."""
    return [state.board.terrain[hex_id].value for hex_id in state.board.topology.hexes_at(vertex)]


def _site(action: Action, key: str, size: int) -> int | Rejected:
    """Read a site identifier, refusing anything the board does not have (FR-18.2)."""
    value: Any = action.params.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"{key} must be an integer between 0 and {size - 1}",
                details={key: value},
            )
        )
    if not 0 <= value < size:
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"{key} {value} is not on this board, which has {size}",
                details={key: value, "size": size},
            )
        )
    return value


def _occupied(occupancy: tuple[int, ...], site: int) -> bool:
    return occupancy[site] != NO_OWNER


def _placed(occupancy: tuple[int, ...]) -> int:
    return sum(1 for seat in occupancy if seat != NO_OWNER)


def _with_seat(occupancy: tuple[int, ...], site: int, seat: int) -> tuple[int, ...]:
    updated = list(occupancy)
    updated[site] = seat
    return tuple(updated)
