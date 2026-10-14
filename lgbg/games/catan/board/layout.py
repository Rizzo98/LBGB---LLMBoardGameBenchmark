"""What a board is, and what makes one sound (RULES.md sections 4.1 and 4.2).

A board is a topology plus three facts about it: the terrain on each hex, the number token on
each hex (none on the desert), and the port on each harbour edge. This module holds those
types and the checks that make them falsifiable; *building* a board - from curated data or
from recorded draws - is generation.py's job.

The composition is pinned by the rulebook and reproduced here as constants, so a curated board
that quietly drifted from the reference would be caught when it is loaded rather than when a
result is questioned.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from lgbg.games.catan.board.topology import Topology


class Terrain(StrEnum):
    """The six terrain faces."""

    FOREST = "forest"
    PASTURE = "pasture"
    FIELD = "field"
    HILLS = "hills"
    MOUNTAINS = "mountains"
    DESERT = "desert"


class Resource(StrEnum):
    """The five resources a hand can hold."""

    WOOD = "wood"
    BRICK = "brick"
    WOOL = "wool"
    WHEAT = "wheat"
    ORE = "ore"


RESOURCE_OF_TERRAIN: Final[Mapping[Terrain, Resource | None]] = MappingProxyType(
    {
        Terrain.FOREST: Resource.WOOD,
        Terrain.PASTURE: Resource.WOOL,
        Terrain.FIELD: Resource.WHEAT,
        Terrain.HILLS: Resource.BRICK,
        Terrain.MOUNTAINS: Resource.ORE,
        Terrain.DESERT: None,
    }
)
"""The resource a hex produces. The desert produces nothing."""

CANONICAL_TERRAINS: Final[tuple[Terrain, ...]] = (
    (Terrain.FOREST,) * 4
    + (Terrain.PASTURE,) * 4
    + (Terrain.FIELD,) * 4
    + (Terrain.HILLS,) * 3
    + (Terrain.MOUNTAINS,) * 3
    + (Terrain.DESERT,)
)
"""The 19 terrain faces in canonical order (RULES.md 4.1 item 2). Shuffled by draw D1."""

TERRAIN_COUNTS: Final[Mapping[Terrain, int]] = MappingProxyType(Counter(CANONICAL_TERRAINS))

CANONICAL_TOKENS: Final[tuple[int, ...]] = (
    2,
    3,
    3,
    4,
    4,
    5,
    5,
    6,
    6,
    8,
    8,
    9,
    9,
    10,
    10,
    11,
    11,
    12,
)
"""The 18 number tokens in canonical order, ascending. Shuffled by draw D3."""

RED_NUMBERS: Final[frozenset[int]] = frozenset({6, 8})
"""The tokens that may not end up on adjacent hexes (RULES.md 4.2 item 7)."""

PORTS: Final[int] = 9
GENERIC_PORT_RATIO: Final[int] = 3
SPECIFIC_PORT_RATIO: Final[int] = 2

BOARDS_DIRECTORY: Final[Path] = Path(__file__).parent / "boards"


@dataclass(frozen=True, slots=True)
class Port:
    """A harbour: which edge it sits on, its exchange ratio, and its resource if specific."""

    edge: int
    ratio: int
    resource: Resource | None

    @property
    def is_generic(self) -> bool:
        return self.resource is None


@dataclass(frozen=True, slots=True)
class Board:
    """A playable board: terrain, tokens and ports over a derived topology."""

    name: str
    topology: Topology
    terrain: tuple[Terrain, ...]
    tokens: tuple[int | None, ...]
    ports: tuple[Port, ...]
    token_start_hex: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ports", tuple(sorted(self.ports, key=lambda port: port.edge)))

    @property
    def desert_hex(self) -> int:
        return self.terrain.index(Terrain.DESERT)

    def resource_of_hex(self, hex_id: int) -> Resource | None:
        return RESOURCE_OF_TERRAIN[self.terrain[hex_id]]

    def port_at_edge(self, edge_id: int) -> Port | None:
        for port in self.ports:
            if port.edge == edge_id:
                return port
        return None


@dataclass(frozen=True, slots=True)
class BoardData:
    """A curated board as it is stored: the facts, plus why they were chosen."""

    name: str
    rationale: str
    terrain: tuple[Terrain, ...]
    number_placement: str
    number_start_hex: int
    ports: tuple[Port, ...]


def read_board_data(name: str, *, directory: Path | None = None) -> BoardData:
    """Read one curated board file."""
    path = (BOARDS_DIRECTORY if directory is None else directory) / f"{name}.json"
    if not path.is_file():
        raise ValueError(f"no curated board called {name!r}: {path} does not exist")
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    return BoardData(
        name=str(data["name"]),
        rationale=str(data["rationale"]),
        terrain=tuple(Terrain(entry) for entry in data["terrain"]),
        number_placement=str(data["number_placement"]),
        number_start_hex=int(data["number_start_hex"]),
        ports=tuple(_port(entry) for entry in data["ports"]),
    )


def _port(entry: Mapping[str, Any]) -> Port:
    resource = entry.get("resource")
    return Port(
        edge=int(entry["edge"]),
        ratio=int(entry["ratio"]),
        resource=None if resource is None else Resource(str(resource)),
    )


def check_board(board: Board) -> list[str]:
    """Everything a sound board must satisfy. Empty when the board can be played."""
    violations: list[str] = []
    hexes = len(board.topology.hexes)

    if len(board.terrain) != hexes:
        violations.append(f"terrain covers {len(board.terrain)} hexes, expected {hexes}")
    elif Counter(board.terrain) != Counter(TERRAIN_COUNTS):
        violations.append(
            f"terrain composition is {dict(Counter(board.terrain))}, expected the pinned one"
        )

    if len(board.tokens) != hexes:
        violations.append(f"tokens cover {len(board.tokens)} hexes, expected {hexes}")
    else:
        placed = [token for token in board.tokens if token is not None]
        if Counter(placed) != Counter(CANONICAL_TOKENS):
            violations.append(f"the tokens placed are {sorted(placed)}, expected the pinned 18")
        if board.tokens[board.desert_hex] is not None:
            violations.append("the desert must not carry a number token")
        for hex_id, token in enumerate(board.tokens):
            if token is not None and (token < 2 or token > 12 or token == 7):
                violations.append(f"hex {hex_id} carries the impossible token {token}")

    edges = {port.edge for port in board.ports}
    if len(board.ports) != PORTS:
        violations.append(f"{len(board.ports)} ports, expected {PORTS}")
    if len(edges) != len(board.ports):
        violations.append("two ports share an edge")
    for port in board.ports:
        if not 0 <= port.edge < len(board.topology.edges):
            violations.append(f"port on edge {port.edge}, which does not exist")
        elif not board.topology.edges[port.edge].is_coastal:
            violations.append(f"port on edge {port.edge}, which is not on the coast")
    ratios = Counter(port.ratio for port in board.ports)
    if ratios.get(GENERIC_PORT_RATIO, 0) != 4 or ratios.get(SPECIFIC_PORT_RATIO, 0) != 5:
        violations.append(f"port ratios are {dict(ratios)}, expected four 3:1 and five 2:1")
    specifics = {port.resource for port in board.ports if port.ratio == SPECIFIC_PORT_RATIO}
    if specifics != set(Resource):
        violations.append(
            f"the 2:1 ports are {sorted(str(item) for item in specifics)}, "
            "expected one per resource"
        )
    if any(port.resource is not None and port.ratio != SPECIFIC_PORT_RATIO for port in board.ports):
        violations.append("a generic 3:1 port must not name a resource")

    for hex_id, token in enumerate(board.tokens):
        if token not in RED_NUMBERS:
            continue
        for neighbour in board.topology.neighbouring_hexes(hex_id):
            if board.tokens[neighbour] in RED_NUMBERS and neighbour > hex_id:
                violations.append(
                    f"the red numbers {token} and {board.tokens[neighbour]} are adjacent "
                    f"on hexes {hex_id} and {neighbour}"
                )

    return violations
