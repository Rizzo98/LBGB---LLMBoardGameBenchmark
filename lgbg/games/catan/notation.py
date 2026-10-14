"""Notation: how a position is written down (ARCHITECTURE.md section 11; PRD-v1 FR-19.4).

Notation is a first-class artefact, not a debugging convenience. How a state is rendered
measurably changes how a model plays, so the rendering is held constant across models - which
means it has to be one renderer, used by the CLI today and by prompts and MCP resources later.
Divergent renderings across surfaces would confound exactly what the benchmark measures.

Two details are required, and they differ only in shape: **full** for a person reading a game,
**compact** for a token budget. Both describe the same projection, so a fact present in one is
present in the other; both are pure functions of what they are given.

The renderer never decides what may be seen. It renders the projection it is handed, field by
field, and a field the projection left out cannot appear - the allow-list in projection.py is
the only gate. An unrecognised field is rendered rather than dropped, deliberately: rendering
fails open, because failing closed would silently lose a fact the projection had allowed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Final

from lgbg.core.canonical import to_canonical_json
from lgbg.core.types import JsonValue, Observation

GAME_NAME: Final[str] = "catan"
"""The name this notation belongs to: a rendering is a fact about one game, not about games."""

HANDLED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "awards",
        "bank",
        "board",
        "dice",
        "hands",
        "phase",
        "pieces",
        "robber",
        "round",
        "supply",
        "turn",
    }
)


class Detail(StrEnum):
    """How much of the rendering to produce (ARCHITECTURE.md section 11.4).

    Full and compact are required of any game; board is this game's extra, for an operator who
    wants to look at the board alone.
    """

    FULL = "full"
    COMPACT = "compact"
    BOARD = "board"


def render(observation: Observation, *, detail: Detail = Detail.FULL) -> str:
    """Render a projection. The same projection always renders to the same string."""
    if detail is Detail.COMPACT:
        return _compact(observation)
    if detail is Detail.BOARD:
        return render_board(observation)
    return _full(observation)


def render_board(observation: Observation) -> str:
    """Just the board, laid out as the board is: the hex rows of a hexagon."""
    board = observation.get("board")
    if not isinstance(board, Mapping):
        return f"{GAME_NAME}: no board in this projection"
    lines = ["board:"]
    lines.extend(_board_rows(board))
    ports = board.get("ports")
    if isinstance(ports, Sequence) and ports:
        lines.append("ports: " + " ".join(_port(entry) for entry in ports))
    lines.append(f"robber: {_robber(observation)}")
    return "\n".join(lines)


def _headline(observation: Observation) -> str:
    phase = observation.get("phase", "?")
    turn = observation.get("turn", "?")
    round_ = observation.get("round", "?")
    return f"{GAME_NAME} | {phase} | turn {turn} | round {round_}"


def _full(observation: Observation) -> str:
    lines = [_headline(observation)]
    board = observation.get("board")
    if isinstance(board, Mapping):
        lines.append("board:")
        lines.extend(_board_rows(board))
        ports = board.get("ports")
        if isinstance(ports, Sequence) and ports:
            lines.append("ports: " + " ".join(_port(entry) for entry in ports))
    lines.append(f"robber: {_robber(observation)}")
    lines.append(f"pieces: {_pieces(observation)}")
    lines.append(f"bank: {_bank(observation)}")
    lines.append(f"supply: {_supply(observation)}")
    lines.append(f"awards: {_awards(observation)}")
    lines.append(f"dice: {_dice(observation)}")
    if "hands" in observation:
        lines.append(f"hands: {_hands(observation)}")
    for key, value in _other_fields(observation):
        lines.append(f"{key}: {to_canonical_json(value)}")
    return "\n".join(lines)


def _compact(observation: Observation) -> str:
    parts = [_headline(observation)]
    board = observation.get("board")
    if isinstance(board, Mapping):
        hexes = board.get("hexes")
        if isinstance(hexes, Sequence):
            parts.append("board " + " ".join(_hex_cell(entry) for entry in hexes))
        ports = board.get("ports")
        if isinstance(ports, Sequence) and ports:
            parts.append("ports " + " ".join(_port(entry) for entry in ports))
    parts.append(f"robber {_robber(observation)}")
    parts.append(f"pieces {_pieces(observation)}")
    parts.append(f"bank {_bank(observation)}")
    parts.append(f"supply {_supply(observation)}")
    parts.append(f"awards {_awards(observation)}")
    parts.append(f"dice {_dice(observation)}")
    if "hands" in observation:
        parts.append(f"hands {_hands(observation)}")
    for key, value in _other_fields(observation):
        parts.append(f"{key} {to_canonical_json(value)}")
    return " | ".join(parts)


def _row_lengths(count: int) -> list[int]:
    """The rows of a hexagonal board, derived from how many hexes it has.

    A hexagon of radius r has 3r(r+1)+1 hexes in rows of r+1, r+2, ... 2r+1, ... r+1. Deriving
    the shape keeps the rendering honest for a board that is not the standard one, and a count
    that is not a hexagon is simply written as a single row rather than guessed at.
    """
    radius = 0
    while 3 * radius * (radius + 1) + 1 < count:
        radius += 1
    if 3 * radius * (radius + 1) + 1 != count:
        return [count]
    half = [radius + 1 + step for step in range(radius + 1)]
    return half + half[-2::-1]


def _board_rows(board: Mapping[str, JsonValue]) -> list[str]:
    hexes = board.get("hexes")
    if not isinstance(hexes, Sequence):
        return ["(no hexes)"]
    cells = [_hex_cell(entry) for entry in hexes]
    lengths = _row_lengths(len(cells))
    width = max(len(cell) for cell in cells) if cells else 0
    rows: list[str] = []
    at = 0
    for length in lengths:
        row = cells[at : at + length]
        at += length
        indent = " " * ((max(lengths) - length) * (width + 2) // 2)
        rows.append(indent + "  ".join(cell.ljust(width) for cell in row).rstrip())
    return rows


def _hex_cell(entry: JsonValue) -> str:
    if not isinstance(entry, Mapping):
        return to_canonical_json(entry)
    hex_id = entry.get("id", "?")
    terrain = entry.get("terrain", "?")
    token = entry.get("token")
    cell = f"h{hex_id} {terrain}"
    return cell if token is None else f"{cell} t{token}"


def _port(entry: JsonValue) -> str:
    if not isinstance(entry, Mapping):
        return to_canonical_json(entry)
    resource = entry.get("resource")
    ratio = entry.get("ratio")
    face = "3:1" if resource is None else f"{resource} {ratio}:1"
    return f"e{entry.get('edge', '?')} {face}"


def _robber(observation: Observation) -> str:
    return f"h{observation.get('robber', '?')}"


def _pieces(observation: Observation) -> str:
    """Every player's pieces, by site, since that is what the rules talk about."""
    pieces = observation.get("pieces")
    if not isinstance(pieces, Mapping):
        return "none"
    settlements = _by_seat(pieces.get("settlements"), "v")
    cities = _by_seat(pieces.get("cities"), "v")
    roads = _by_seat(pieces.get("roads"), "e")
    turn = observation.get("turn")
    seats = sorted({*settlements, *cities, *roads} | ({turn} if isinstance(turn, int) else set()))
    if not seats:
        return "none"
    rendered = []
    for seat in seats:
        held = []
        if settlements.get(seat):
            held.append("v " + " ".join(settlements[seat]))
        if cities.get(seat):
            held.append("c " + " ".join(cities[seat]))
        if roads.get(seat):
            held.append("e " + " ".join(roads[seat]))
        rendered.append(f"p{seat} " + (" ".join(held) if held else "none"))
    return " | ".join(rendered)


def _by_seat(entries: JsonValue, prefix: str) -> dict[int, list[str]]:
    grouped: dict[int, list[str]] = {}
    if not isinstance(entries, Sequence):
        return grouped
    for entry in entries:
        if not isinstance(entry, Sequence) or len(entry) != 2:
            continue
        site, seat = entry
        if isinstance(site, int) and isinstance(seat, int):
            grouped.setdefault(seat, []).append(f"{prefix}{site}")
    return grouped


def _bank(observation: Observation) -> str:
    bank = observation.get("bank")
    if not isinstance(bank, Mapping):
        return "-"
    return " ".join(f"{name} {count}" for name, count in bank.items())


def _supply(observation: Observation) -> str:
    supply = observation.get("supply")
    if not isinstance(supply, Sequence):
        return "-"
    return " ".join(
        f"p{seat} " + "/".join(str(part) for part in entry)
        for seat, entry in enumerate(supply)
        if isinstance(entry, Sequence)
    )


def _hands(observation: Observation) -> str:
    hands = observation.get("hands")
    if not isinstance(hands, Sequence):
        return "-"
    return " ".join(
        f"p{seat} " + "/".join(str(count) for count in hand)
        for seat, hand in enumerate(hands)
        if isinstance(hand, Sequence)
    )


def _awards(observation: Observation) -> str:
    awards = observation.get("awards")
    if not isinstance(awards, Mapping):
        return "-"
    return " ".join(f"{name.replace('_', ' ')} {seat}" for name, seat in awards.items())


def _dice(observation: Observation) -> str:
    dice = observation.get("dice")
    if not isinstance(dice, Sequence):
        return "-"
    return " ".join(str(die) for die in dice)


def _other_fields(observation: Observation) -> list[tuple[str, JsonValue]]:
    """Everything the renderer does not know how to format, so nothing is silently dropped."""
    return [(key, value) for key, value in sorted(observation.items()) if key not in HANDLED_FIELDS]
