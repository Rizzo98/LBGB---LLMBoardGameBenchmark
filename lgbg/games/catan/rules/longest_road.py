"""Longest Road: the award, and the search behind it (RULES.md 4.10; PRD-v1 FR-13.9, FR-13.10).

The card is worth two victory points and it is held by a *player*, not by the board, which is
why the state carries a holder rather than a length: recomputing the holder is what this module
does, and recomputing it after every build is what makes the award automatic - awarded, held and
revoked with no claim action and no memory of who held it before.

The length itself is a search, and the rulebook's definition is narrower than it looks. A
continuous road is a *simple path* or a *simple cycle* - no vertex repeated - so a road that
branches is not the sum of its branches: a T of six roads has a longest continuous road of four.
And an opponent's building may sit at the *end* of a continuous road but never in the middle of
it, so the search stops there rather than passing through.

RULES.md 4.10 item 4 admits no greedy, heuristic or approximate computation here, so the search
is exhaustive over simple paths and cycles. It is a depth-first walk of the player's own road
graph, which is at most fifteen edges on this board: the branching a real network has is small,
and being wrong about a two-point award is worse than being slow about it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Final

from lgbg.core.types import Event
from lgbg.games.catan.state import NO_OWNER, CatanState

MINIMUM: Final[int] = 5
"""The length at which a road becomes eligible for the card (RULES.md 4.10 item 5)."""

VALUE: Final[int] = 2
"""What the card is worth, in victory points. The accounting itself belongs to victory.py."""


def road_length(state: CatanState, player: int) -> int:
    """This player's longest continuous road, by exhaustive enumeration (RULES.md 4.10 item 4).

    Every start vertex is tried, because the longest continuous road need not begin at a leaf:
    in a loop it begins wherever the enumeration happens to start and closes back on itself.
    """
    graph = _graph(state, player)
    blocked = _blocked(state, player)
    best = 0
    for start in sorted(graph):
        best = max(best, _walk(graph, blocked, start, start, frozenset({start}), 0))
    return best


def holder(state: CatanState) -> int:
    """Who holds the card, given every player's length and the current holder (item 6).

    The tie rule is the one that needs the incumbent: two players at the same length leave the
    card where it is if the holder is one of them, and take it off the board otherwise.
    """
    lengths = {player: road_length(state, player) for player in range(state.players)}
    best = max(lengths.values(), default=0)
    if best < MINIMUM:
        return NO_OWNER
    tied = sorted(player for player, length in lengths.items() if length == best)
    if len(tied) == 1:
        return tied[0]
    return state.longest_road if state.longest_road in tied else NO_OWNER


def recompute(state: CatanState) -> tuple[CatanState, list[Event]]:
    """Award, keep or revoke the card, saying so when it moves (RULES.md 4.10 items 7 to 9).

    Nothing here is a claim or a decision: the card follows the roads, so every action that can
    change a road or break one calls this, and the only thing it may do is change the holder.
    """
    awarded = holder(state)
    if awarded == state.longest_road:
        return state, []
    if awarded == NO_OWNER:
        return (
            replace(state, longest_road=NO_OWNER),
            [
                Event(
                    type="longest_road_vacated",
                    payload={"player": state.longest_road},
                )
            ],
        )
    return (
        replace(state, longest_road=awarded),
        [
            Event(
                type="longest_road_awarded",
                payload={"player": awarded, "length": road_length(state, awarded)},
            )
        ],
    )


def _graph(state: CatanState, player: int) -> Mapping[int, tuple[tuple[int, int], ...]]:
    """The player's own roads, as a vertex-to-(neighbour, edge) map in a stable order."""
    topology = state.board.topology
    lines: dict[int, list[tuple[int, int]]] = {}
    for edge in range(len(state.placed.roads)):
        if state.placed.roads[edge] != player:
            continue
        first, second = topology.vertices_of_edge(edge)
        lines.setdefault(first, []).append((second, edge))
        lines.setdefault(second, []).append((first, edge))
    return {vertex: tuple(sorted(neighbours)) for vertex, neighbours in lines.items()}


def _blocked(state: CatanState, player: int) -> frozenset[int]:
    """The vertices where somebody else's building interrupts this player's road (item 3)."""
    return frozenset(
        vertex
        for vertex in range(len(state.placed.settlements))
        if (
            state.placed.settlements[vertex] not in (NO_OWNER, player)
            or state.placed.cities[vertex] not in (NO_OWNER, player)
        )
    )


def _walk(
    graph: Mapping[int, tuple[tuple[int, int], ...]],
    blocked: frozenset[int],
    start: int,
    at: int,
    seen: frozenset[int],
    length: int,
) -> int:
    """The longest continuation from here: a depth-first walk of every simple road.

    Three things end a walk rather than continue it. An edge back to the start closes a *cycle*,
    which is a continuous road in its own right. A vertex already on the walk cannot be visited
    again, because the rule's definition forbids repeating one. And an opponent's building may
    be the end of the road but never part of it.
    """
    best = length
    for neighbour, _edge in graph[at]:
        if neighbour == start and start not in blocked and length + 1 >= 3:
            best = max(best, length + 1)
            continue
        if neighbour in seen:
            continue
        if neighbour in blocked:
            best = max(best, length + 1)
            continue
        best = max(
            best,
            _walk(graph, blocked, start, neighbour, seen | {neighbour}, length + 1),
        )
    return best
