"""Building a board: from curated data, or from recorded draws (RULES.md sections 4.1, 4.2).

Two things here are worth reading before the code.

**The spiral walk.** The tokens go on in a fixed sequence, following a walk that starts at an
outer corner, goes round the outermost ring, steps inward to the ring below on the same ray,
goes round that, and finishes at the centre. That walk is derived from the coordinates like
everything else, and its defining property - every consecutive pair of hexes is adjacent - is
asserted for all six corners rather than assumed.

**The red-number repair.** The rulebook requires that no two 6s or 8s end up adjacent, and
allows swapping tokens to achieve it. The pinned sequence already satisfies it for every
desert position and every corner on the standard board, so the repair is a guard for curated
or future boards. It never draws: a repair that consumed randomness would make the record's
draw list depend on the arrangement it was repairing.

Every random board consumes exactly the draws RULES.md section 3.1 pins, with those labels:
terrain (D1), the spiral's starting corner (D2) or the token order (D3), and the port faces
(D4). Loading a curated board consumes none, because comparability across runs is what fixed
boards are for (ARCHITECTURE.md section 7.6).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from lgbg.core.rng import Purpose, RandomSource
from lgbg.games.catan.board.layout import (
    CANONICAL_TERRAINS,
    CANONICAL_TOKENS,
    PORTS,
    RED_NUMBERS,
    Board,
    Port,
    Resource,
    Terrain,
    check_board,
    read_board_data,
)
from lgbg.games.catan.board.topology import HEX_DIRECTIONS, Axial, Topology, standard_topology

BOARD_TERRAIN_SHUFFLE: Final[Purpose] = "board_terrain_shuffle"
BOARD_NUMBER_CORNER: Final[Purpose] = "board_number_corner"
BOARD_NUMBER_SHUFFLE: Final[Purpose] = "board_number_shuffle"
BOARD_PORT_SHUFFLE: Final[Purpose] = "board_port_shuffle"

NUMBER_SPIRAL: Final[str] = "spiral"
NUMBER_SPIRAL_NO_ADJACENT_RED: Final[str] = "spiral_no_adjacent_red"
NUMBER_RANDOM: Final[str] = "random"
NUMBER_PLACEMENTS: Final[tuple[str, ...]] = (
    NUMBER_SPIRAL,
    NUMBER_SPIRAL_NO_ADJACENT_RED,
    NUMBER_RANDOM,
)

TOKEN_SEQUENCE: Final[tuple[int, ...]] = (5, 2, 6, 3, 8, 10, 9, 12, 11, 4, 8, 10, 9, 4, 5, 6, 3, 11)
"""The pinned token order of RULES.md 4.2 item 2. Never reorder this: it is a pinned rule."""

CANONICAL_PORT_FACES: Final[tuple[tuple[int, Resource | None], ...]] = (
    (3, None),
    (3, None),
    (3, None),
    (3, None),
    (2, Resource.WOOD),
    (2, Resource.BRICK),
    (2, Resource.WOOL),
    (2, Resource.WHEAT),
    (2, Resource.ORE),
)
"""The nine port faces in canonical order, as draw D4 describes them."""

PORT_FACES: Final[int] = 9
MAX_REPAIR_SWAPS: Final[int] = 100


class BoardGenerationError(Exception):
    """A board could not be built as the rules require."""


def corner_hex_ids(topology: Topology) -> tuple[int, ...]:
    """The six outermost corner hexes, in canonical order by identifier."""
    radius = _radius(topology)
    on_board = {hex_.axial: hex_.id for hex_ in topology.hexes}
    corners = []
    for direction in HEX_DIRECTIONS:
        position = Axial(radius * direction.q, radius * direction.r)
        if position in on_board:
            corners.append(on_board[position])
    return tuple(sorted(corners))


def coastal_edge_ring(topology: Topology) -> tuple[int, ...]:
    """Every coastal edge, in the order they occur around the coast.

    Ports are spread around this ring, so the ring is derived rather than listed: the boundary
    of a hexagonal board is a cycle, and every boundary vertex is incident to exactly two
    coastal edges, which is what makes the walk well defined.
    """
    at_vertex: dict[int, list[int]] = {}
    for edge in topology.edges:
        if not edge.is_coastal:
            continue
        for vertex in edge.vertices:
            at_vertex.setdefault(vertex, []).append(edge.id)
    if not at_vertex:
        return ()

    first = min(edge_id for ids in at_vertex.values() for edge_id in ids)
    start_vertex = topology.edges[first].vertices[0]
    ring = [first]
    current_edge, current_vertex = first, start_vertex
    while True:
        neighbours = [
            edge_id for edge_id in sorted(at_vertex[current_vertex]) if edge_id != current_edge
        ]
        if not neighbours:
            break
        following = neighbours[0]
        other = topology.edges[following].vertices
        next_vertex = other[0] if other[1] == current_vertex else other[1]
        if following == first:
            break
        ring.append(following)
        current_edge, current_vertex = following, next_vertex
    return tuple(ring)


def spiral_walk(topology: Topology, start_hex_id: int) -> tuple[int, ...]:
    """Every hex in spiral order, starting at an outer corner (RULES.md 4.2 item 3)."""
    radius = _radius(topology)
    corner = topology.hexes[start_hex_id].axial
    direction = _direction_of(corner, radius)
    by_axial = {hex_.axial: hex_.id for hex_ in topology.hexes}
    return tuple(by_axial[position] for position in _spiral_positions(radius, direction))


def place_tokens_spiral(
    topology: Topology, terrain: Sequence[Terrain], start_hex_id: int
) -> tuple[int | None, ...]:
    """Place the pinned token sequence along the spiral walk, skipping the desert."""
    tokens: list[int | None] = [None] * len(topology.hexes)
    placed = 0
    for hex_id in spiral_walk(topology, start_hex_id):
        if terrain[hex_id] is Terrain.DESERT:
            continue
        if placed >= len(TOKEN_SEQUENCE):
            raise BoardGenerationError(
                f"the board has more than {len(TOKEN_SEQUENCE)} hexes that take a token"
            )
        tokens[hex_id] = TOKEN_SEQUENCE[placed]
        placed += 1
    if placed != len(TOKEN_SEQUENCE):
        raise BoardGenerationError(
            f"placed {placed} of {len(TOKEN_SEQUENCE)} tokens: the board has no desert to skip"
        )
    return tuple(tokens)


def place_tokens_random(
    rng: RandomSource, topology: Topology, terrain: Sequence[Terrain]
) -> tuple[int | None, ...]:
    """Place a shuffled token order on the hexes that take a token, in canonical order."""
    shuffled = rng.shuffle(list(CANONICAL_TOKENS), purpose=BOARD_NUMBER_SHUFFLE)
    tokens: list[int | None] = [None] * len(topology.hexes)
    index = 0
    for hex_id in range(len(topology.hexes)):
        if terrain[hex_id] is Terrain.DESERT:
            continue
        tokens[hex_id] = shuffled[index]
        index += 1
    return tuple(tokens)


def repair_adjacent_reds(
    topology: Topology, tokens: Sequence[int | None], walk: Sequence[int]
) -> tuple[int | None, ...]:
    """Swap tokens until no two red numbers are adjacent (RULES.md 4.2 item 7).

    Each accepted swap strictly reduces the number of adjacent red pairs, so the loop
    terminates; the cap turns a defective board into a loud failure rather than a silent one.
    """
    placement = list(tokens)
    for _ in range(MAX_REPAIR_SWAPS):
        conflicts = _adjacent_red_pairs(topology, placement)
        if not conflicts:
            return tuple(placement)
        order = {hex_id: index for index, hex_id in enumerate(walk)}
        offender = min(
            (hex_id for pair in conflicts for hex_id in pair), key=lambda hex_id: order[hex_id]
        )
        before = len(conflicts)
        for candidate in walk:
            if candidate == offender or placement[candidate] in RED_NUMBERS:
                continue
            placement[offender], placement[candidate] = placement[candidate], placement[offender]
            if len(_adjacent_red_pairs(topology, placement)) < before:
                break
            placement[offender], placement[candidate] = placement[candidate], placement[offender]
        else:
            raise BoardGenerationError(
                "no swap removes an adjacent pair of red numbers without creating another"
            )
    raise BoardGenerationError(
        f"the red numbers were still adjacent after {MAX_REPAIR_SWAPS} swaps"
    )


def random_board(
    rng: RandomSource,
    *,
    number_placement: str,
    topology: Topology | None = None,
    name: str = "random",
) -> Board:
    """Build a board from recorded draws: terrain D1, numbers D2 or D3, port faces D4."""
    if number_placement not in NUMBER_PLACEMENTS:
        raise ValueError(
            f"unknown number placement {number_placement!r}; "
            f"expected one of {list(NUMBER_PLACEMENTS)}"
        )
    board_topology = standard_topology() if topology is None else topology
    terrain = tuple(rng.shuffle(list(CANONICAL_TERRAINS), purpose=BOARD_TERRAIN_SHUFFLE))

    start_hex: int | None = None
    if number_placement == NUMBER_RANDOM:
        tokens = place_tokens_random(rng, board_topology, terrain)
        walk = spiral_walk(board_topology, corner_hex_ids(board_topology)[0])
    else:
        corners = corner_hex_ids(board_topology)
        start_hex = rng.choice(list(corners), purpose=BOARD_NUMBER_CORNER)
        tokens = place_tokens_spiral(board_topology, terrain, start_hex)
        walk = spiral_walk(board_topology, start_hex)

    tokens = repair_adjacent_reds(board_topology, tokens, walk)
    ports = _assign_ports(
        board_topology, rng.shuffle(list(CANONICAL_PORT_FACES), purpose=BOARD_PORT_SHUFFLE)
    )
    board = Board(
        name=name,
        topology=board_topology,
        terrain=terrain,
        tokens=tokens,
        ports=ports,
        token_start_hex=start_hex,
    )
    _require_sound(board)
    return board


def load_board(name: str, *, directory: Path | None = None) -> Board:
    """Load a curated board: terrain from the data, tokens from the pinned placement rule."""
    data = read_board_data(name, directory=directory)
    if data.number_placement not in NUMBER_PLACEMENTS:
        raise ValueError(
            f"{name}: unknown number placement {data.number_placement!r}; "
            f"expected one of {list(NUMBER_PLACEMENTS)}"
        )
    topology = standard_topology()
    tokens = place_tokens_spiral(topology, data.terrain, data.number_start_hex)
    tokens = repair_adjacent_reds(topology, tokens, spiral_walk(topology, data.number_start_hex))
    board = Board(
        name=f"fixed:{data.name}",
        topology=topology,
        terrain=data.terrain,
        tokens=tokens,
        ports=data.ports,
        token_start_hex=data.number_start_hex,
    )
    _require_sound(board)
    return board


def board_from_selector(
    selector: str,
    *,
    rng: RandomSource,
    number_placement: str,
    directory: Path | None = None,
) -> Board:
    """Resolve a board selector: `fixed:<name>` or `random` (FR-7.4)."""
    if selector == "random":
        return random_board(rng, number_placement=number_placement)
    if selector.startswith("fixed:"):
        return load_board(selector[len("fixed:") :], directory=directory)
    raise ValueError(f"unknown board selector {selector!r}; expected 'random' or 'fixed:<name>'")


def _assign_ports(
    topology: Topology, faces: Sequence[tuple[int, Resource | None]]
) -> tuple[Port, ...]:
    """Put the nine port faces on the nine harbour edges of the frame, in ring order."""
    edges = standard_port_edges(topology)
    if len(edges) != len(faces):
        raise BoardGenerationError(f"the frame has {len(edges)} harbour edges, expected 9")
    return tuple(
        Port(edge=edge, ratio=ratio, resource=resource)
        for edge, (ratio, resource) in zip(edges, faces, strict=True)
    )


def standard_port_edges(topology: Topology) -> tuple[int, ...]:
    """The nine harbour positions of the frame, spread evenly around the coast.

    The rulebook shows the harbours as a picture of the frame rather than as text, so this is
    curation, not translation (RULES.md 2.3): nine positions evenly spaced around the 30
    coastal edges, three or four edges apart, which is what the physical frame looks like.
    """
    ring = coastal_edge_ring(topology)
    if not ring:
        return ()
    if len(ring) < PORTS:
        raise BoardGenerationError(f"the coast has {len(ring)} edges, too few for {PORTS} ports")
    step = len(ring) // PORTS
    extra = len(ring) % PORTS
    positions: list[int] = []
    cursor = 0
    for index in range(PORTS):
        positions.append(cursor % len(ring))
        cursor += step + (1 if index < extra else 0)
    return tuple(ring[position] for position in positions)


def _require_sound(board: Board) -> None:
    violations = check_board(board)
    if violations:
        raise BoardGenerationError(
            f"the board {board.name!r} is not sound: " + "; ".join(violations)
        )


def _radius(topology: Topology) -> int:
    return max(hex_.axial.distance(Axial(0, 0)) for hex_ in topology.hexes)


def _direction_of(position: Axial, radius: int) -> int:
    for index, direction in enumerate(HEX_DIRECTIONS):
        if Axial(radius * direction.q, radius * direction.r) == position:
            return index
    raise BoardGenerationError(f"{position} is not a corner hex of a board of radius {radius}")


def _spiral_positions(radius: int, direction: int) -> list[Axial]:
    positions: list[Axial] = []
    for level in range(radius, -1, -1):
        positions.extend(_ring_walk(level, direction))
    return positions


def _ring_walk(radius: int, direction: int) -> list[Axial]:
    """One ring, counterclockwise, starting at its corner on the chosen ray."""
    if radius == 0:
        return [Axial(0, 0)]
    start = HEX_DIRECTIONS[direction]
    current = Axial(radius * start.q, radius * start.r)
    positions: list[Axial] = []
    for side in range(6):
        step = HEX_DIRECTIONS[(direction + 2 + side) % 6]
        for _ in range(radius):
            positions.append(current)
            current = Axial(current.q + step.q, current.r + step.r)
    return positions


def _adjacent_red_pairs(topology: Topology, tokens: Sequence[int | None]) -> list[tuple[int, int]]:
    reds = [hex_id for hex_id, token in enumerate(tokens) if token in RED_NUMBERS]
    return [
        (first, second)
        for first in reds
        for second in reds
        if second > first and second in topology.neighbouring_hexes(first)
    ]
