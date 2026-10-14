"""Author the curated standard board (kanban card K-013).

The rulebook's *variable* setup shuffles the terrain, so no arrangement of it is pinned by
the rules text; the physical game shows one as a picture. A curated board is therefore
curation, and this script is the record of how it was chosen: a search under two constraints,
rather than a layout picked by eye.

    1. No two hexes of the same terrain are adjacent. Around an intersection the three hexes
       are pairwise adjacent, so this is equivalent to saying that no intersection touches two
       hexes of the same resource: no player can hold a spot that produces the same thing
       twice, which is the clustering that makes a board unfair.
    2. The desert is the centre hex, so the robber's opening position borders six hexes.

The search is deterministic - attempts are seeded 0, 1, 2, ... and the first solution wins -
so re-running this script reproduces the committed file exactly. The properties themselves are
asserted by tests/games/test_board_layout.py, which is what protects them afterwards.

Usage:
    uv run python scripts/author_standard_a.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Final

from lgbg.games.catan.board.generation import (
    coastal_edge_ring,
    corner_hex_ids,
    place_tokens_spiral,
    repair_adjacent_reds,
    spiral_walk,
    standard_port_edges,
)
from lgbg.games.catan.board.layout import (
    Board,
    Port,
    Resource,
    Terrain,
    check_board,
)
from lgbg.games.catan.board.topology import Topology, standard_topology

OUTPUT: Final[Path] = Path("lgbg/games/catan/board/boards/standard_a.json")

FACES: Final[tuple[tuple[int, Resource | None], ...]] = (
    (3, None),
    (2, Resource.WOOD),
    (3, None),
    (2, Resource.BRICK),
    (3, None),
    (2, Resource.WOOL),
    (3, None),
    (2, Resource.WHEAT),
    (2, Resource.ORE),
)
"""The port faces in the order they are placed around the coast: the five specific 2:1 ports
spread among the four generics rather than clustered at one end of the ring."""

TERRAIN_GROUPS: Final[tuple[Terrain, ...]] = (
    (Terrain.FOREST,) * 4
    + (Terrain.PASTURE,) * 4
    + (Terrain.FIELD,) * 4
    + (Terrain.HILLS,) * 3
    + (Terrain.MOUNTAINS,) * 3
)

MAX_ATTEMPTS: Final[int] = 20_000


def _vertices_at(topology: Topology) -> dict[int, list[tuple[int, ...]]]:
    """For each hex, the hexes that meet it at an intersection, including itself."""
    at: dict[int, list[tuple[int, ...]]] = {}
    for vertex in topology.vertices:
        for hex_id in vertex.hexes:
            at.setdefault(hex_id, []).append(vertex.hexes)
    return at


def _fits(
    topology: Topology,
    at: dict[int, list[tuple[int, ...]]],
    assignment: dict[int, Terrain],
    hex_id: int,
    terrain: Terrain,
) -> bool:
    if any(
        assignment.get(neighbour) is terrain for neighbour in topology.neighbouring_hexes(hex_id)
    ):
        return False
    return all(
        assignment.get(other) is not terrain
        for hexes in at[hex_id]
        for other in hexes
        if other != hex_id
    )


def search_arrangement(topology: Topology) -> dict[int, Terrain]:
    """The deterministic search for an arrangement that satisfies both constraints."""
    centre = next(hex_.id for hex_ in topology.hexes if hex_.axial.q == 0 and hex_.axial.r == 0)
    at = _vertices_at(topology)
    candidates = [hex_id for hex_id in range(len(topology.hexes)) if hex_id != centre]
    for attempt in range(MAX_ATTEMPTS):
        rng = random.Random(attempt)
        order = list(TERRAIN_GROUPS)
        rng.shuffle(order)
        assignment: dict[int, Terrain] = {centre: Terrain.DESERT}
        for terrain in order:
            free = [
                hex_id
                for hex_id in candidates
                if hex_id not in assignment and _fits(topology, at, assignment, hex_id, terrain)
            ]
            if not free:
                break
            assignment[rng.choice(free)] = terrain
        else:
            return assignment
    raise SystemExit(f"no arrangement satisfied the constraints in {MAX_ATTEMPTS} attempts")


def main() -> int:
    topology = standard_topology()
    assignment = search_arrangement(topology)
    terrain = tuple(assignment[hex_.id] for hex_ in topology.hexes)

    start = corner_hex_ids(topology)[0]
    walk = spiral_walk(topology, start)
    tokens = repair_adjacent_reds(topology, place_tokens_spiral(topology, terrain, start), walk)
    ports = tuple(
        Port(edge=edge, ratio=ratio, resource=resource)
        for edge, (ratio, resource) in zip(standard_port_edges(topology), FACES, strict=True)
    )
    board = Board(
        name="fixed:standard_a",
        topology=topology,
        terrain=terrain,
        tokens=tokens,
        ports=ports,
        token_start_hex=start,
    )
    violations = check_board(board)
    if violations:
        raise SystemExit("the arrangement is not a sound board: " + "; ".join(violations))

    ring = coastal_edge_ring(topology)
    data = {
        "name": "standard_a",
        "rationale": (
            "Curated under three checkable constraints, asserted by "
            "tests/games/test_board_layout.py. (1) No two hexes of the same terrain are "
            "adjacent, so every intersection touches at most one hex of each resource: no "
            "player can hold a spot that produces the same thing twice. (2) The desert is the "
            "centre hex, so the robber's opening position borders six hexes. (3) The nine "
            "harbour edges are spread evenly around the 30-edge coast, three or four edges "
            "apart, with the five specific 2:1 ports spread among the four generics. The "
            "arrangement satisfying (1) and (2) was found by search in "
            "scripts/author_standard_a.py rather than chosen by eye; this file stores the "
            "result, and the tests are what protect the properties."
        ),
        "number_placement": "spiral_no_adjacent_red",
        "number_start_hex": start,
        "terrain": [face.value for face in terrain],
        "ports": [
            {
                "edge": port.edge,
                "ratio": port.ratio,
                "resource": None if port.resource is None else port.resource.value,
            }
            for port in ports
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")
    print("desert at hex", board.desert_hex, "of", len(board.topology.hexes))
    print("spiral starts at hex", start, "of corners", corner_hex_ids(topology))
    print("port ring positions", [ring.index(port.edge) for port in ports])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
