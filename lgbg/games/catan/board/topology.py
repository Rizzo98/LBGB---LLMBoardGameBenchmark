"""Board topology, derived from hex coordinates (ARCHITECTURE.md section 7.5).

Nothing here is a table. Hand-authored relational data of this size is unverifiable by
reading, and one wrong entry is a silent rule error that a test written against the same table
will happily confirm. So the board's structure is computed from the coordinate system, and
what this module publishes is the *result* of that computation.

## The coordinate system

A hex is an axial pair `(q, r)`, equivalent to the cube triple `(q, -q-r, r)` whose elements
sum to zero. Neighbours are the six cube vectors of length one, in cyclic order starting
east: `(+1,0), (+1,-1), (0,-1), (-1,0), (-1,+1), (0,+1)`.

The standard board is every hex within cube distance 2 of the origin: 19 hexes.

## The derivation

A *corner* of a hex is where three hexes meet. For corner `i` of hex `h` those three are
`h`, `h + D[i]` and `h + D[i+1]` - which is why a corner can be identified by the sorted
triple of its coordinates, whether or not all three hexes are on the board. Interior corners
name three board hexes, coastal corners name two, and the six corners of the board's outer
hexagon name one.

Vertices are those triples, deduplicated. Edges are the segments between consecutive corners
of a hex, deduplicated as unordered pairs of vertices.

Identifiers are then assigned by sorting the derived coordinates (FR-7.3), in three steps:

- **Hexes** by row then column, `(r, q)`, so the board's top row comes first.
- **Vertices** by their sorted cube triple, compared position by position: the triple *is* the
  vertex's coordinates, so this is a canonical ordering of the geometry itself.
- **Edges** by their sorted pair of vertex identifiers - the same ordering one level down, an
  edge sitting between its two endpoints.

Sorting the coordinates rather than the enumeration order is what makes the identifiers
reproducible across implementations and stable across runs: the same set of hex positions
always produces the same board, in whatever order they were offered.

## The counts, and why they are what they are

With H hexes, V vertices and E edges, each hex contributing 6 corners and 6 edges:

- Every vertex lies on 1, 2 or 3 hexes, so `6H = V1 + 2V2 + 3V3`, and `V = V1 + V2 + V3`.
- A vertex where one hex meets has degree 2; where two or three meet, degree 3 - so
  `2E = 3(V2 + V3) + 2V1`.
- Euler: `V - E + H = 1` for a hexagonal board.

For H = 19 those give V = 54, E = 72, and the split `V3 = 24`, `V2 = 12`, `V1 = 18`:
24 interior vertices, 30 on the coast, 42 interior edges and the 30 coastal edges the nine
ports are placed on. The tests assert the derivation reproduces all of it.

## Identifier stability

Vertex and edge identifiers appear in recorded actions, so changing this derivation
invalidates every record that exists (PRD-v1 open question Q3). Changing it means bumping the
plugin's `rules_version` and regenerating the golden corpus.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

type Cube = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Axial:
    """A hex position. Axial `(q, r)` is cube `(q, -q-r, r)`."""

    q: int
    r: int

    @property
    def cube(self) -> Cube:
        return (self.q, -self.q - self.r, self.r)

    def neighbour(self, direction: int) -> Axial:
        """The neighbouring position in one of the six directions, by index."""
        step = HEX_DIRECTIONS[direction % len(HEX_DIRECTIONS)]
        return Axial(self.q + step.q, self.r + step.r)

    def distance(self, other: Axial) -> int:
        """How many steps away another position is, in the hex metric."""
        here, there = self.cube, other.cube
        return max(abs(here[axis] - there[axis]) for axis in range(3))


HEX_DIRECTIONS: Final[tuple[Axial, ...]] = (
    Axial(1, 0),
    Axial(1, -1),
    Axial(0, -1),
    Axial(-1, 0),
    Axial(-1, 1),
    Axial(0, 1),
)
"""The six neighbours of a hex, in cyclic order starting east."""

BOARD_RADIUS: Final[int] = 2
"""The standard board is every hex within this distance of the origin."""

CORNERS_PER_HEX: Final[int] = 6
EDGES_PER_HEX: Final[int] = 6


def hexagon(radius: int) -> tuple[Axial, ...]:
    """Every hex within `radius` of the origin, in canonical order (by row, then column)."""
    return tuple(
        sorted(
            (
                Axial(q, r)
                for q in range(-radius, radius + 1)
                for r in range(-radius, radius + 1)
                if max(abs(q), abs(r), abs(q + r)) <= radius
            ),
            key=_hex_order,
        )
    )


def _hex_order(position: Axial) -> tuple[int, int]:
    return (position.r, position.q)


STANDARD_HEXES: Final[tuple[Axial, ...]] = hexagon(BOARD_RADIUS)
"""The 19 positions of the standard board."""


@dataclass(frozen=True, slots=True)
class Hex:
    """One position on the board, with the identifier derived from its coordinates."""

    id: int
    axial: Axial


@dataclass(frozen=True, slots=True)
class Vertex:
    """A corner of the board: where up to three hexes and up to three edges meet."""

    id: int
    hexes: tuple[int, ...]
    edges: tuple[int, ...]

    @property
    def is_coastal(self) -> bool:
        """True where fewer than three hexes meet, which is the boundary of the board."""
        return len(self.hexes) < 3


@dataclass(frozen=True, slots=True)
class Edge:
    """A board edge: the segment between two vertices, shared by one or two hexes."""

    id: int
    vertices: tuple[int, int]
    hexes: tuple[int, ...]

    @property
    def is_coastal(self) -> bool:
        """True where only one hex touches the edge, so a port could sit on it."""
        return len(self.hexes) == 1


@dataclass(frozen=True, slots=True)
class Topology:
    """A derived board. The three fields below are the board; the rest are lookups into it."""

    hexes: tuple[Hex, ...]
    vertices: tuple[Vertex, ...]
    edges: tuple[Edge, ...]

    _vertices_by_hex: tuple[tuple[int, ...], ...] = field(init=False, repr=False)
    _edges_by_hex: tuple[tuple[int, ...], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # One pass, no cross-references: a malformed board must be *reported* by the
        # structural check, not blow up while the lookups are being built.
        by_hex: list[list[int]] = [[] for _ in self.hexes]
        for vertex in self.vertices:
            for hex_id in vertex.hexes:
                if 0 <= hex_id < len(by_hex):
                    by_hex[hex_id].append(vertex.id)
        edges_by_hex: list[list[int]] = [[] for _ in self.hexes]
        for edge in self.edges:
            for hex_id in edge.hexes:
                if 0 <= hex_id < len(edges_by_hex):
                    edges_by_hex[hex_id].append(edge.id)
        object.__setattr__(self, "_vertices_by_hex", tuple(tuple(ids) for ids in by_hex))
        object.__setattr__(self, "_edges_by_hex", tuple(tuple(ids) for ids in edges_by_hex))

    def vertices_of_hex(self, hex_id: int) -> tuple[int, ...]:
        return self._vertices_by_hex[hex_id]

    def edges_of_hex(self, hex_id: int) -> tuple[int, ...]:
        return self._edges_by_hex[hex_id]

    def vertices_of_edge(self, edge_id: int) -> tuple[int, int]:
        return self.edges[edge_id].vertices

    def edges_at(self, vertex_id: int) -> tuple[int, ...]:
        return self.vertices[vertex_id].edges

    def hexes_at(self, vertex_id: int) -> tuple[int, ...]:
        return self.vertices[vertex_id].hexes

    def hexes_of_edge(self, edge_id: int) -> tuple[int, ...]:
        return self.edges[edge_id].hexes

    def neighbouring_hexes(self, hex_id: int) -> tuple[int, ...]:
        """Every hex sharing an edge with this one, by identifier."""
        neighbours: set[int] = set()
        for edge_id in self._edges_by_hex[hex_id]:
            if 0 <= edge_id < len(self.edges):
                neighbours.update(self.edges[edge_id].hexes)
        neighbours.discard(hex_id)
        return tuple(sorted(neighbours))

    @property
    def coastal_edges(self) -> tuple[int, ...]:
        """The edges on the boundary of the board: where ports are placed."""
        return tuple(edge.id for edge in self.edges if edge.is_coastal)


def _corner_key(position: Axial, corner: int) -> tuple[Cube, Cube, Cube]:
    """The sorted cube coordinates of the three hexes meeting at one corner of one hex."""
    first = position.neighbour(corner).cube
    second = position.neighbour(corner + 1).cube
    return tuple(sorted((position.cube, first, second)))  # type: ignore[return-value]


def build_topology(hexes: Sequence[Axial] | None = None) -> Topology:
    """Derive a board from its hex coordinates.

    The coordinates may arrive in any order: identifiers come from the canonical sort, so the
    same set of positions always produces the same board.
    """
    positions = STANDARD_HEXES if hexes is None else tuple(hexes)
    ordered = sorted(set(positions), key=_hex_order)
    hex_id = {position: index for index, position in enumerate(ordered)}

    corner_keys = sorted(
        {_corner_key(position, corner) for position in ordered for corner in range(CORNERS_PER_HEX)}
    )
    vertex_id = {key: index for index, key in enumerate(corner_keys)}

    edge_hexes: dict[tuple[int, int], list[Axial]] = {}
    for position in ordered:
        for corner in range(CORNERS_PER_HEX):
            here = vertex_id[_corner_key(position, corner)]
            following = vertex_id[_corner_key(position, (corner + 1) % CORNERS_PER_HEX)]
            edge_hexes.setdefault((min(here, following), max(here, following)), []).append(position)

    vertices = tuple(
        Vertex(
            id=index,
            hexes=tuple(
                sorted(
                    hex_id[Axial(*key_part[:2])] for key_part in key if _on_board(key_part, hex_id)
                )
            ),
            edges=(),
        )
        for index, key in enumerate(corner_keys)
    )

    edge_vertices = sorted(edge_hexes)
    edges = tuple(
        Edge(
            id=index,
            vertices=(pair[0], pair[1]),
            hexes=tuple(sorted(hex_id[position] for position in edge_hexes[pair])),
        )
        for index, pair in enumerate(edge_vertices)
    )

    edges_at: list[list[int]] = [[] for _ in corner_keys]
    for edge in edges:
        for vertex in edge.vertices:
            edges_at[vertex].append(edge.id)
    vertices = tuple(
        Vertex(id=vertex.id, hexes=vertex.hexes, edges=tuple(sorted(edges_at[vertex.id])))
        for vertex in vertices
    )

    return Topology(
        hexes=tuple(Hex(id=index, axial=position) for index, position in enumerate(ordered)),
        vertices=vertices,
        edges=edges,
    )


def _on_board(cube: Cube, hex_id: dict[Axial, int]) -> bool:
    return Axial(cube[0], cube[2]) in hex_id


def standard_topology() -> Topology:
    """The standard 19-hex board."""
    return _STANDARD


_STANDARD: Final[Topology] = build_topology(STANDARD_HEXES)


def check_structure(topology: Topology) -> list[str]:
    """The structural self-check of ARCHITECTURE.md section 7.5: empty when the board is sound."""
    violations: list[str] = []
    hexes, vertices, edges = topology.hexes, topology.vertices, topology.edges

    if [hex_.id for hex_ in hexes] != list(range(len(hexes))):
        violations.append("hex identifiers must run from 0 without gaps")
    if [vertex.id for vertex in vertices] != list(range(len(vertices))):
        violations.append("vertex identifiers must run from 0 without gaps")
    if [edge.id for edge in edges] != list(range(len(edges))):
        violations.append("edge identifiers must run from 0 without gaps")

    for hex_ in hexes:
        corners = topology.vertices_of_hex(hex_.id)
        sides = topology.edges_of_hex(hex_.id)
        if len(set(corners)) != CORNERS_PER_HEX:
            violations.append(f"hex {hex_.id}: {len(set(corners))} distinct vertices, expected 6")
        if len(set(sides)) != EDGES_PER_HEX:
            violations.append(f"hex {hex_.id}: {len(set(sides))} distinct edges, expected 6")

    for vertex in vertices:
        degree = len(vertex.edges)
        if degree not in {2, 3}:
            violations.append(f"vertex {vertex.id}: degree {degree}, expected 2 or 3")
        if not 1 <= len(vertex.hexes) <= 3:
            violations.append(
                f"vertex {vertex.id}: touches {len(vertex.hexes)} hexes, expected 1 to 3"
            )
        if vertex.is_coastal != (len(vertex.hexes) < 3):
            violations.append(
                f"vertex {vertex.id}: coastal classification disagrees with its hexes"
            )
        for edge_id in vertex.edges:
            if not 0 <= edge_id < len(edges):
                violations.append(f"vertex {vertex.id}: names edge {edge_id}, which does not exist")
            elif vertex.id not in edges[edge_id].vertices:
                violations.append(f"edge {edge_id}: does not name its own vertex {vertex.id}")
        for hex_id in vertex.hexes:
            if not 0 <= hex_id < len(hexes):
                violations.append(f"vertex {vertex.id}: names hex {hex_id}, which does not exist")
            elif vertex.id not in topology.vertices_of_hex(hex_id):
                violations.append(f"hex {hex_id}: does not list its own vertex {vertex.id}")

    for edge in edges:
        if len(set(edge.vertices)) != 2:
            violations.append(f"edge {edge.id}: {len(set(edge.vertices))} distinct vertices")
        if not 1 <= len(edge.hexes) <= 2:
            violations.append(f"edge {edge.id}: touches {len(edge.hexes)} hexes, expected 1 or 2")
        if edge.is_coastal != (len(edge.hexes) == 1):
            violations.append(f"edge {edge.id}: coastal classification disagrees with its hexes")
        for vertex_id in edge.vertices:
            if not 0 <= vertex_id < len(vertices):
                violations.append(f"edge {edge.id}: names vertex {vertex_id}, which does not exist")
            elif edge.id not in vertices[vertex_id].edges:
                violations.append(f"vertex {vertex_id}: does not list its own edge {edge.id}")
        for hex_id in edge.hexes:
            if not 0 <= hex_id < len(hexes):
                violations.append(f"edge {edge.id}: names hex {hex_id}, which does not exist")
            elif edge.id not in topology.edges_of_hex(hex_id):
                violations.append(f"hex {hex_id}: does not list its own edge {edge.id}")

    incidence = sum(len(vertex.hexes) for vertex in vertices)
    if incidence != CORNERS_PER_HEX * len(hexes):
        violations.append(
            f"vertices account for {incidence} hex corners, expected {CORNERS_PER_HEX * len(hexes)}"
        )
    edge_incidence = sum(len(edge.hexes) for edge in edges)
    if edge_incidence != EDGES_PER_HEX * len(hexes):
        violations.append(
            f"edges account for {edge_incidence} hex sides, expected {EDGES_PER_HEX * len(hexes)}"
        )

    euler = len(vertices) - len(edges) + len(hexes)
    if euler != 1:
        violations.append(f"the Euler characteristic is {euler}, expected 1")

    return violations
