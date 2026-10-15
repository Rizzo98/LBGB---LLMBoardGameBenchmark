"""Positions built by hand, shared by the building tests.

A fixture that merely *looks* like a position proves nothing. The checks that matter here are
about conservation, and a position whose pieces were placed without charging a supply - or whose
cards appeared without leaving the bank - would pass those checks for the wrong reason. So
everything in this module charges for what it places: a piece comes out of its owner's supply, a
card comes out of the bank, and the supply of a player whose pieces are all on the board is
produced by *putting them there* rather than by declaring it so.

This is a declared test helper, not a test module: nothing here is named test_*.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Final

from lgbg.games.catan.state import (
    NO_OWNER,
    PIECES_PER_PLAYER,
    RESOURCE_ORDER,
    CatanState,
    Phase,
    Placed,
    Supply,
)

SLOT: Final[Mapping[str, int]] = {
    resource.value: index for index, resource in enumerate(RESOURCE_ORDER)
}
"""Where a resource sits in a hand, by name, so a fixture cannot be wrong about the order."""

PIECE_SLOT: Final[Mapping[str, int]] = {"roads": 0, "settlements": 1, "cities": 2}
"""Which entry of PIECES_PER_PLAYER belongs to which piece, named rather than indexed."""


def hand(**counts: int) -> tuple[int, ...]:
    """A hand named by resource: hand(wood=2, ore=1)."""
    unknown = sorted(set(counts) - set(SLOT))
    assert not unknown, f"no such resource: {unknown}"
    row = [0] * len(RESOURCE_ORDER)
    for name, count in counts.items():
        row[SLOT[name]] = count
    return tuple(row)


def holding(state: CatanState, seat: int, **counts: int) -> CatanState:
    """Deal that hand out of the bank, so the position conserves cards like a real one."""
    dealt = hand(**counts)
    bank = tuple(cards - dealt[index] for index, cards in enumerate(state.bank))
    assert min(bank) >= 0, "a hand cannot hold cards the bank does not have"
    hands = list(state.hands)
    hands[seat] = dealt
    return replace(state, hands=tuple(tuple(row) for row in hands), bank=bank)


def layout(
    state: CatanState,
    *,
    roads: Sequence[tuple[int, int]] = (),
    settlements: Sequence[tuple[int, int]] = (),
    cities: Sequence[tuple[int, int]] = (),
    roads_in_supply: int | None = None,
    turn: int = 0,
    phase: Phase = Phase.ACTION,
) -> CatanState:
    """A board with pieces placed by hand, in the action phase with every supply charged.

    roads_in_supply, when given, is how many roads **seat 0** has left: the rest of that
    player's fifteen are laid out on free edges, so an exhausted supply is a position the rules
    could have produced rather than a number somebody wrote down.
    """
    lines = [NO_OWNER] * len(state.placed.roads)
    sites = [NO_OWNER] * len(state.placed.settlements)
    towns = [NO_OWNER] * len(state.placed.cities)
    for edge, seat in roads:
        lines[edge] = seat
    for vertex, seat in settlements:
        sites[vertex] = seat
    for vertex, seat in cities:
        towns[vertex] = seat
    if roads_in_supply is not None:
        ends = {vertex for edge, _seat in roads for vertex in vertices_of(state, edge)}
        spare = [
            edge
            for edge in range(len(lines))
            if lines[edge] == NO_OWNER and not ends & set(vertices_of(state, edge))
        ]
        mine = sum(1 for seat in lines if seat == 0)
        for edge in spare[: PIECES_PER_PLAYER[PIECE_SLOT["roads"]] - roads_in_supply - mine]:
            lines[edge] = 0
    return replace(
        state,
        placed=Placed(tuple(sites), tuple(towns), tuple(lines)),
        supply=supplies(lines, sites, towns, state.players),
        phase=phase,
        turn=turn,
    )


def supplies(
    lines: Sequence[int],
    sites: Sequence[int],
    towns: Sequence[int],
    players: int,
) -> tuple[Supply, ...]:
    """What each player has left, counted from the pieces on the board."""
    return tuple(
        Supply(
            PIECES_PER_PLAYER[PIECE_SLOT["roads"]] - sum(1 for seat in lines if seat == player),
            PIECES_PER_PLAYER[PIECE_SLOT["settlements"]]
            - sum(1 for seat in sites if seat == player),
            PIECES_PER_PLAYER[PIECE_SLOT["cities"]] - sum(1 for seat in towns if seat == player),
        )
        for player in range(players)
    )


def vertices_of(state: CatanState, edge: int) -> tuple[int, int]:
    """The two ends of an edge, in the topology's own order."""
    return state.board.topology.vertices_of_edge(edge)


def edges_at(state: CatanState, vertex: int) -> tuple[int, ...]:
    return state.board.topology.edges_at(vertex)


def free_edge(state: CatanState, vertex: int, *, taken: int | None = None) -> int:
    """An empty edge at this vertex, other than one to be avoided."""
    return next(
        edge
        for edge in edges_at(state, vertex)
        if edge != taken and state.placed.roads[edge] == NO_OWNER
    )


def at_distance(state: CatanState, vertex: int, steps: int) -> frozenset[int]:
    """Every vertex exactly this many edges away (the distance rule's own measure)."""
    seen = {vertex}
    ring = {vertex}
    for _ in range(steps):
        ring = {
            other
            for site in ring
            for edge in edges_at(state, site)
            for other in vertices_of(state, edge)
            if other not in seen
        }
        seen |= ring
    return frozenset(ring)
