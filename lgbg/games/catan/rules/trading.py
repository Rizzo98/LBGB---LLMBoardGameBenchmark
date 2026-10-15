"""Ports, and what they are worth to a player (RULES.md 4.12.1; PRD-v1 FR-14.1).

A harbour is not a property of the board; it is a property of a *player's position* on the board.
The rules say a player controls a harbour when they have a settlement or a city on a coastal
intersection that borders it (S2 Almanac p.8), and they say it just as plainly the other way
round: you may not trade through a harbour where somebody else has settled (S5). So what this
module computes is, for each player, the best ratio they may use for each resource - derived from
the board's port placement and their own buildings, never authored.

The derivation is the whole of the rule: four to one by default, three to one if the player holds
a generic port, two to one if they hold the specific port *for the resource they are giving away*
- and a specific port never improves anything else, "not even to 3:1" (S2 Almanac p.9).
"""

from __future__ import annotations

from typing import Final

from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.state import NO_OWNER, RESOURCE_ORDER, CatanState

GENERAL: Final[int] = 4
"""The rate that is always available (S2 p.4: "The 4:1 trade is always possible")."""

GENERIC: Final[int] = 3
SPECIFIC: Final[int] = 2


def controls(state: CatanState, player: int, vertex: int) -> bool:
    """Whether this player has a building on this intersection, settlement or city."""
    return state.placed.settlements[vertex] == player or state.placed.cities[vertex] == player


def port_edges(state: CatanState, player: int) -> tuple[int, ...]:
    """Every harbour edge this player's buildings border, in board order.

    An edge is a harbour if the board says so, and a player controls it if one of the two
    intersections at its ends carries their building. Nothing is stored: a building that is
    placed or upgraded changes the answer on the next call, and a curated board that moved a port
    would move the answer with it.
    """
    topology = state.board.topology
    return tuple(
        port.edge
        for port in state.board.ports
        if any(controls(state, player, vertex) for vertex in topology.vertices_of_edge(port.edge))
    )


def ratios(state: CatanState, player: int) -> dict[Resource, int]:
    """The best exchange rate this player has for each resource (RULES.md 4.12.1 item 3)."""
    best = dict.fromkeys(RESOURCE_ORDER, GENERAL)
    for edge in port_edges(state, player):
        port = next(port for port in state.board.ports if port.edge == edge)
        for resource in RESOURCE_ORDER:
            if port.resource is not None and port.resource is not resource:
                continue
            best[resource] = min(best[resource], port.ratio)
    return best


def ratio(state: CatanState, player: int, resource: Resource) -> int:
    """What this player must give for one card of this resource."""
    return ratios(state, player)[resource]


def _owners_are_known(state: CatanState) -> bool:
    """A guard the tests use: every building on the board belongs to somebody."""
    return all(
        seat == NO_OWNER or 0 <= seat < state.players
        for seat in (*state.placed.settlements, *state.placed.cities)
    )
