"""What a build costs, and paying for it (RULES.md 4.7; PRD-v1 FR-11.1, FR-11.7).

Every build in this game has the same two halves: a target the rules judge, and a price paid
from the player's hand to the bank. The price is not spread across the four build actions - it
lives here as a table that reads like the rulebook, and paying is one function, so a cost can
only be wrong in one place and a payment can only be atomic in one place.

Paying is atomic by construction: the shortfall is computed before a card moves, so a player who
cannot afford something loses nothing and the rejection carries exactly what was missing. That
is what makes "insufficient resources" a measurable rejection (FR-11.7) rather than a
half-applied position somebody has to unwind.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import Final

from lgbg.core.errors import BAD_PARAMS, Rejection
from lgbg.core.game import Applied, ApplyResult, Rejected
from lgbg.core.rng import RandomSource
from lgbg.core.types import Action, Event, JsonValue
from lgbg.games.catan import phases
from lgbg.games.catan.board.layout import Resource
from lgbg.games.catan.rejections import (
    EDGE_OCCUPIED,
    NO_PIECES_REMAINING,
    NOT_CONNECTED,
    NOT_ENOUGH_RESOURCES,
    NOT_YOUR_SETTLEMENT,
    TOO_CLOSE,
    VERTEX_OCCUPIED,
)
from lgbg.games.catan.state import NO_OWNER, RESOURCE_ORDER, CatanState, Phase, Placed, Supply

ROAD: Final[str] = "road"
SETTLEMENT: Final[str] = "settlement"
CITY: Final[str] = "city"
DEVELOPMENT_CARD: Final[str] = "development_card"
"""The four things a hand can pay for, named the way the actions and the rules name them."""

ROADS: Final[str] = "roads"
SETTLEMENTS: Final[str] = "settlements"
CITIES: Final[str] = "cities"
PIECES: Final[tuple[str, ...]] = (ROADS, SETTLEMENTS, CITIES)
"""The three piece supplies, named as the state names them: plural, and not the build names.

A build and a piece are different words on purpose - you build a *settlement*, and five
*settlements* is what you own - and keeping both spelled out is what stops one being passed
where the other belongs.
"""

COSTS: Final[Mapping[str, Mapping[str, int]]] = MappingProxyType(
    {
        ROAD: MappingProxyType({Resource.BRICK.value: 1, Resource.WOOD.value: 1}),
        SETTLEMENT: MappingProxyType(
            {
                Resource.BRICK.value: 1,
                Resource.WOOD.value: 1,
                Resource.WOOL.value: 1,
                Resource.WHEAT.value: 1,
            }
        ),
        CITY: MappingProxyType({Resource.WHEAT.value: 2, Resource.ORE.value: 3}),
        DEVELOPMENT_CARD: MappingProxyType(
            {
                Resource.WOOL.value: 1,
                Resource.WHEAT.value: 1,
                Resource.ORE.value: 1,
            }
        ),
    }
)
"""The prices of RULES.md 4.7 and PRD-v1 Appendix A, written resource by resource.

A price is a *mapping* rather than a five-count tuple so that it can be read, diffed and printed
without knowing the canonical resource order - and it is turned into a hand by cost_of, which is
the one place that order is applied to a price.
"""


def cost_of(build: str) -> tuple[int, ...]:
    """A price as a hand: counts in canonical resource order, which is how a hand is held."""
    wanted = COSTS.get(build)
    if wanted is None:
        raise KeyError(f"{build!r} is not something this game sells; it sells {sorted(COSTS)}")
    return tuple(wanted.get(resource.value, 0) for resource in RESOURCE_ORDER)


def shortfall(state: CatanState, player: int, build: str) -> dict[str, int]:
    """What this player is missing for this build, by resource. Empty when they can afford it."""
    wanted = cost_of(build)
    hand = state.hands[player]
    return {
        resource.value: wanted[index] - hand[index]
        for index, resource in enumerate(RESOURCE_ORDER)
        if wanted[index] > hand[index]
    }


def affordable(state: CatanState, player: int, build: str) -> bool:
    """Whether this player can pay for this build, asked without moving anything."""
    return not shortfall(state, player, build)


def pay(state: CatanState, player: int, build: str) -> tuple[CatanState, Event] | Rejected:
    """Move a build's price from one hand to the bank, or refuse with what is missing (FR-11.7).

    The two halves of the answer are the position and the event: a build that was paid for is a
    fact the record should state, not something a reader has to infer from a smaller hand.
    """
    missing = shortfall(state, player, build)
    if missing:
        return Rejected(
            Rejection(
                code=NOT_ENOUGH_RESOURCES,
                message=(
                    f"seat {player} cannot afford a {build}: short of "
                    + ", ".join(f"{count} {name}" for name, count in missing.items())
                ),
                details={
                    "player": player,
                    "build": build,
                    "missing": missing,
                    "cost": dict(COSTS[build]),
                },
            )
        )

    hand = list(state.hands[player])
    bank = list(state.bank)
    for index, wanted in enumerate(cost_of(build)):
        hand[index] -= wanted
        bank[index] += wanted
    hands = list(state.hands)
    hands[player] = tuple(hand)
    return (
        replace(state, bank=tuple(bank), hands=tuple(hands)),
        Event(
            type="resources_spent",
            payload={"player": player, "build": build, "cost": dict(COSTS[build])},
        ),
    )


def spend_piece(supplies: Sequence[Supply], player: int, piece: str) -> tuple[Supply, ...]:
    """Take one piece out of a player's supply, which is a state change its event describes.

    The pieces are the player's own and finite (RULES.md 4.7), so the supply is the only place
    that knows whether a build is available at all - and it is charged here rather than in each
    build, so the ledger can only be wrong in one place. It takes and returns the supply tuple
    rather than the state, so a build that moves two pieces composes the two calls.
    """
    if piece not in PIECES:
        raise KeyError(f"{piece!r} is not a piece; a piece is one of {list(PIECES)}")
    stock = list(supplies)
    held = stock[player]
    stock[player] = Supply(
        roads=held.roads - (piece == ROADS),
        settlements=held.settlements - (piece == SETTLEMENTS),
        cities=held.cities - (piece == CITIES),
    )
    return tuple(stock)


def return_piece(supplies: Sequence[Supply], player: int, piece: str) -> tuple[Supply, ...]:
    """Put a piece back into a player's supply: the other half of an upgrade (RULES.md 4.7)."""
    if piece not in PIECES:
        raise KeyError(f"{piece!r} is not a piece; a piece is one of {list(PIECES)}")
    stock = list(supplies)
    held = stock[player]
    stock[player] = Supply(
        roads=held.roads + (piece == ROADS),
        settlements=held.settlements + (piece == SETTLEMENTS),
        cities=held.cities + (piece == CITIES),
    )
    return tuple(stock)


def piece_returned(player: int, piece: str, remaining: int) -> Event:
    """A piece going *back* to a supply, which only an upgrade ever does."""
    return Event(
        type="piece_returned", payload={"player": player, "piece": piece, "remaining": remaining}
    )


def piece_taken(player: int, piece: str, remaining: int) -> Event:
    """The piece leaving a supply, announced the same way wherever a piece is placed."""
    return Event(
        type="piece_taken", payload={"player": player, "piece": piece, "remaining": remaining}
    )


def neighbouring_vertices(state: CatanState, vertex: int) -> tuple[int, ...]:
    """The vertices one edge away: the neighbourhood every placement rule is written against.

    RULES.md 4.7 states the distance rule over exactly these three vertices - the ones reachable
    by a single edge - so the rule and the geometry that answers it are defined in one place.
    """
    topology = state.board.topology
    neighbours = {
        other
        for edge in topology.edges_at(vertex)
        for other in topology.vertices_of_edge(edge)
        if other != vertex
    }
    return tuple(sorted(neighbours))


def settlement_targets(state: CatanState, player: int) -> tuple[int, ...]:
    """Every vertex this player may build a settlement on (RULES.md 4.7, "Settlements").

    Three questions, in the order the rules ask them: is the vertex empty, is every vertex one
    edge away free of buildings of any colour, and does this player's own network reach it.
    """
    points = connection_points(state, player)
    return tuple(
        vertex
        for vertex in range(len(state.placed.settlements))
        if vertex in points and _empty(state, vertex) and not _crowded(state, vertex)
    )


def can_build_settlement(state: CatanState, player: int) -> bool:
    """Whether a settlement is on offer: a piece, the price, and somewhere legal to put it."""
    return (
        state.supply[player].settlements > 0
        and affordable(state, player, SETTLEMENT)
        and bool(settlement_targets(state, player))
    )


def build_settlement(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Place a settlement on an empty vertex of the player's own network (FR-11.4).

    The refusals come in the order the rules treat the questions, and the price is paid last, so
    a settlement refused for any other reason costs nothing.
    """
    del rng  # placing a settlement decides nothing and draws nothing
    refusal = phases.refuse_unless_acting(state, action, Phase.ACTION)
    if refusal is not None:
        return refusal
    vertex = _vertex(action, len(state.placed.settlements))
    if isinstance(vertex, Rejected):
        return vertex
    if state.supply[action.player].settlements < 1:
        return Rejected(
            Rejection(
                code=NO_PIECES_REMAINING,
                message="every settlement this player has is already on the board",
                details={"player": action.player, "piece": SETTLEMENT},
            )
        )
    if not _empty(state, vertex):
        return Rejected(
            Rejection(
                code=VERTEX_OCCUPIED,
                message="that vertex already carries a building",
                details={"vertex": vertex, "owner": _owner(state, vertex)},
            )
        )
    crowded = _crowded(state, vertex)
    if crowded:
        return Rejected(
            Rejection(
                code=TOO_CLOSE,
                message="a vertex one edge away carries a building, and settlements keep two apart",
                details={"vertex": vertex, "blocked_by": crowded},
            )
        )
    points = connection_points(state, action.player)
    if vertex not in points:
        return Rejected(
            Rejection(
                code=NOT_CONNECTED,
                message="a settlement must touch the player's own network",
                details={"vertex": vertex, "network": sorted(points)},
            )
        )
    paid = pay(state, action.player, SETTLEMENT)
    if isinstance(paid, Rejected):
        return paid

    built, spent = paid
    sites = list(built.placed.settlements)
    sites[vertex] = action.player
    supply = spend_piece(built.supply, action.player, SETTLEMENTS)
    return Applied(
        state=replace(
            built,
            placed=Placed(tuple(sites), built.placed.cities, built.placed.roads),
            supply=supply,
        ),
        events=[
            spent,
            Event(
                type="settlement_placed",
                payload={
                    "player": action.player,
                    "vertex": vertex,
                    "terrain": [
                        built.board.terrain[hex_id].value
                        for hex_id in built.board.topology.hexes_at(vertex)
                    ],
                },
            ),
            piece_taken(action.player, SETTLEMENT, supply[action.player].settlements),
        ],
    )


def city_targets(state: CatanState, player: int) -> tuple[int, ...]:
    """Every vertex where this player may upgrade a settlement (RULES.md 4.7, "Cities").

    An upgrade changes no vertex, so the target set is exactly the player's own settlements -
    which is also why a city can never appear on an empty vertex "for any price".
    """
    return tuple(vertex for vertex, owner in enumerate(state.placed.settlements) if owner == player)


def can_build_city(state: CatanState, player: int) -> bool:
    """Whether an upgrade is on offer: a city piece, the price, and a settlement to upgrade."""
    return (
        state.supply[player].cities > 0
        and affordable(state, player, CITY)
        and bool(city_targets(state, player))
    )


def build_city(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Upgrade one of the player's own settlements into a city (FR-11.6; RULES.md 4.7).

    Two pieces move in opposite directions: the city comes out of the supply and the settlement
    goes back into it, so the ledger stays true and the player can settle somewhere else again.
    """
    del rng  # upgrading decides nothing and draws nothing
    refusal = phases.refuse_unless_acting(state, action, Phase.ACTION)
    if refusal is not None:
        return refusal
    vertex = _vertex(action, len(state.placed.settlements))
    if isinstance(vertex, Rejected):
        return vertex
    if state.supply[action.player].cities < 1:
        return Rejected(
            Rejection(
                code=NO_PIECES_REMAINING,
                message="every city this player has is already on the board",
                details={"player": action.player, "piece": CITY},
            )
        )
    if state.placed.settlements[vertex] != action.player:
        return Rejected(
            Rejection(
                code=NOT_YOUR_SETTLEMENT,
                message="a city is an upgrade: that vertex does not carry this player's settlement",
                details={"vertex": vertex, "owner": _owner(state, vertex)},
            )
        )
    paid = pay(state, action.player, CITY)
    if isinstance(paid, Rejected):
        return paid

    built, spent = paid
    sites = list(built.placed.settlements)
    towns = list(built.placed.cities)
    sites[vertex] = NO_OWNER
    towns[vertex] = action.player
    supply = return_piece(
        spend_piece(built.supply, action.player, CITIES), action.player, SETTLEMENTS
    )
    return Applied(
        state=replace(
            built,
            placed=Placed(tuple(sites), tuple(towns), built.placed.roads),
            supply=supply,
        ),
        events=[
            spent,
            Event(
                type="city_built",
                payload={
                    "player": action.player,
                    "vertex": vertex,
                    "terrain": [
                        built.board.terrain[hex_id].value
                        for hex_id in built.board.topology.hexes_at(vertex)
                    ],
                },
            ),
            piece_taken(action.player, CITY, supply[action.player].cities),
            piece_returned(action.player, SETTLEMENT, supply[action.player].settlements),
        ],
    )


def _owner(state: CatanState, vertex: int) -> int:
    """Whoever built on this vertex, whether a settlement or a city."""
    settlement = state.placed.settlements[vertex]
    return settlement if settlement != NO_OWNER else state.placed.cities[vertex]


def _empty(state: CatanState, vertex: int) -> bool:
    return state.placed.settlements[vertex] == NO_OWNER and state.placed.cities[vertex] == NO_OWNER


def _crowded(state: CatanState, vertex: int) -> list[int]:
    """The vertices one edge away that carry a building, whoever owns it (RULES.md 4.7)."""
    return sorted(site for site in neighbouring_vertices(state, vertex) if not _empty(state, site))


def _vertex(action: Action, vertices: int) -> int | Rejected:
    """Read a vertex identifier, refusing anything the board does not have (FR-18.2)."""
    value: JsonValue = action.params.get("vertex")
    if not isinstance(value, int) or isinstance(value, bool):
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"vertex must be an integer between 0 and {vertices - 1}",
                details={"vertex": value},
            )
        )
    if not 0 <= value < vertices:
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"vertex {value} is not on this board, which has {vertices}",
                details={"vertex": value, "vertices": vertices},
            )
        )
    return value


def connection_points(state: CatanState, player: int) -> frozenset[int]:
    """The vertices this player's network reaches, and which a rival's building does not block.

    RULES.md 4.7 items 2 and 3: a road must touch the player's own network - their road, their
    settlement or their city - and an opponent's building is never itself a connection point.
    The second half matters in exactly one case: a vertex carrying both this player's road and
    somebody else's settlement connects nothing further, which is what stops a road from being
    built "on the other side of" a building that happens to sit on the player's own line.
    """
    topology = state.board.topology
    points = set()
    for vertex in range(len(state.placed.settlements)):
        if _held_by_another(state, player, vertex):
            continue
        if (
            state.placed.settlements[vertex] == player
            or state.placed.cities[vertex] == player
            or any(state.placed.roads[edge] == player for edge in topology.edges_at(vertex))
        ):
            points.add(vertex)
    return frozenset(points)


def road_targets(state: CatanState, player: int) -> tuple[int, ...]:
    """Every edge this player may put a road on: empty, and incident to their own network."""
    topology = state.board.topology
    points = connection_points(state, player)
    return tuple(
        edge
        for edge in range(len(state.placed.roads))
        if state.placed.roads[edge] == NO_OWNER
        and any(vertex in points for vertex in topology.vertices_of_edge(edge))
    )


def can_build_road(state: CatanState, player: int) -> bool:
    """Whether a road is on offer: a piece in supply, the price in hand, and somewhere to go.

    This is the availability half of FR-11.5. A player at their road limit is not refused when
    they ask - they are never asked to ask, because the action is not among the ones offered.
    """
    return (
        state.supply[player].roads > 0
        and affordable(state, player, ROAD)
        and bool(road_targets(state, player))
    )


def build_road(state: CatanState, action: Action, rng: RandomSource) -> ApplyResult:
    """Place a road on an empty edge of the player's own network (FR-11.2, FR-11.3, FR-11.5).

    The refusals are ordered the way the rules treat the questions: is there a piece to place,
    is the edge empty, does the edge connect, and is there a price in hand. The price is paid
    last, so a road that is refused for any other reason costs nothing.
    """
    del rng  # placing a road decides nothing and draws nothing
    refusal = phases.refuse_unless_acting(state, action, Phase.ACTION)
    if refusal is not None:
        return refusal
    edge = _edge(action, len(state.placed.roads))
    if isinstance(edge, Rejected):
        return edge
    if state.supply[action.player].roads < 1:
        return Rejected(
            Rejection(
                code=NO_PIECES_REMAINING,
                message="every road this player has is already on the board",
                details={"player": action.player, "piece": ROAD},
            )
        )
    if state.placed.roads[edge] != NO_OWNER:
        return Rejected(
            Rejection(
                code=EDGE_OCCUPIED,
                message="that edge already carries a road",
                details={"edge": edge, "owner": state.placed.roads[edge]},
            )
        )
    points = connection_points(state, action.player)
    if not any(vertex in points for vertex in state.board.topology.vertices_of_edge(edge)):
        return Rejected(
            Rejection(
                code=NOT_CONNECTED,
                message="a road must extend the player's own network",
                details={
                    "edge": edge,
                    "touches": list(state.board.topology.vertices_of_edge(edge)),
                    "network": sorted(points),
                },
            )
        )
    paid = pay(state, action.player, ROAD)
    if isinstance(paid, Rejected):
        return paid

    built, spent = paid
    lines = list(built.placed.roads)
    lines[edge] = action.player
    supply = spend_piece(built.supply, action.player, ROADS)
    return Applied(
        state=replace(
            built,
            placed=Placed(built.placed.settlements, built.placed.cities, tuple(lines)),
            supply=supply,
        ),
        events=[
            spent,
            Event(type="road_built", payload={"player": action.player, "edge": edge}),
            piece_taken(action.player, ROAD, supply[action.player].roads),
        ],
    )


def _edge(action: Action, edges: int) -> int | Rejected:
    """Read an edge identifier, refusing anything the board does not have (FR-18.2)."""
    value: JsonValue = action.params.get("edge")
    if not isinstance(value, int) or isinstance(value, bool):
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"edge must be an integer between 0 and {edges - 1}",
                details={"edge": value},
            )
        )
    if not 0 <= value < edges:
        return Rejected(
            Rejection(
                code=BAD_PARAMS,
                message=f"edge {value} is not on this board, which has {edges}",
                details={"edge": value, "edges": edges},
            )
        )
    return value


def _held_by_another(state: CatanState, player: int, vertex: int) -> bool:
    for occupancy in (state.placed.settlements, state.placed.cities):
        seat = occupancy[vertex]
        if seat != NO_OWNER and seat != player:
            return True
    return False
