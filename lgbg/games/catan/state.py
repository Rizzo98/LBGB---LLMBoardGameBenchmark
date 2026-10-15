"""The Catan state: the god view (ARCHITECTURE.md 5.5; RULES.md sections 3 to 5).

Everything the engine knows is here, including what the players do not: each hand, the order
of the undealt development deck, the identity of a card taken by the robber. Hidden
information is a *projection* concern, not a state concern - the projection is what refuses to
show a field, and the allow-list that does so is tested separately (FR-16.5, FR-16.6).

## Why the whole field set is here in slice 2

Later slices need more: development cards, awards, a trade offer. Adding a field changes
`encode_state`, and `encode_state` is what every recorded hash is computed from, so a field
added after the golden corpus exists invalidates it. The field set is therefore fixed now, in
the slice that builds the cheapest state to change, and later slices fill it in. Enum members
are the exception: phases are stored by name, so a phase added later does not change a record.

## Encoding

Counts are held in a canonical order - `RESOURCE_ORDER` for hands, bank and a trade offer,
`CARD_ORDER` for development cards - and the encoding writes the counts as a list in that
order. The orders are pinned as module constants and asserted by a test, because a silently
reordered tuple would reinterpret every recorded hand. Occupancy is the exception: settlements,
cities and roads are written as a sparse list of `[site, seat]`, sorted by site, because a
record is read by people and a list of seventy-two minus-ones is not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from lgbg.core.rng import Purpose, RandomSource
from lgbg.core.types import JsonValue
from lgbg.games.catan.board.layout import Board, Port, Resource, Terrain
from lgbg.games.catan.board.topology import standard_topology

RESOURCE_ORDER: Final[tuple[Resource, ...]] = (
    Resource.BRICK,
    Resource.WOOD,
    Resource.WOOL,
    Resource.WHEAT,
    Resource.ORE,
)
"""The canonical resource order of RULES.md section 3: brick, wood, wool, wheat, ore.

That is the order in which the rulebook lists the five resource-card stacks, and the document
pins it for *every* list, projection and hash that enumerates resources. Hands, the bank, a
trade offer and the encoded state are therefore counts in this order, and a reordering would
reinterpret every recorded hand - which is why the order is asserted by a test and pinned by
the golden fixture rather than left to the declaration order of the enum above.
"""

RESOURCES: Final[int] = len(RESOURCE_ORDER)


class DevCard(StrEnum):
    """The five kinds of development card (RULES.md 4.8)."""

    KNIGHT = "knight"
    VICTORY_POINT = "victory_point"
    ROAD_BUILDING = "road_building"
    YEAR_OF_PLENTY = "year_of_plenty"
    MONOPOLY = "monopoly"


CARD_ORDER: Final[tuple[DevCard, ...]] = (
    DevCard.KNIGHT,
    DevCard.VICTORY_POINT,
    DevCard.ROAD_BUILDING,
    DevCard.YEAR_OF_PLENTY,
    DevCard.MONOPOLY,
)
"""The canonical development-card order, as PRD-v1 Appendix A lists the deck."""

DECK_COMPOSITION: Final[Mapping[DevCard, int]] = MappingProxyType(
    {
        DevCard.KNIGHT: 14,
        DevCard.VICTORY_POINT: 5,
        DevCard.ROAD_BUILDING: 2,
        DevCard.YEAR_OF_PLENTY: 2,
        DevCard.MONOPOLY: 2,
    }
)

CANONICAL_DECK: Final[tuple[DevCard, ...]] = tuple(
    card for card in CARD_ORDER for _ in range(DECK_COMPOSITION[card])
)
"""The 25 cards in canonical order. Draw D5 shuffles this list once, at game start."""

DEV_DECK_SHUFFLE: Final[Purpose] = "dev_deck_shuffle"
"""Draw D5 of RULES.md section 3.1. The only random draw in the opening state."""

NO_OWNER: Final[int] = -1
"""The value of a vertex or edge that nobody occupies."""

BANK_PER_RESOURCE: Final[int] = 19
PIECES_PER_PLAYER: Final[tuple[int, int, int]] = (15, 5, 4)
HAND_LIMIT: Final[int] = 7
"""A seven leaves a hand of this size alone; a bigger one returns half of it (RULES.md 4.9)."""
"""Roads, settlements and cities each player starts with."""


class Phase(StrEnum):
    """Every phase of a game.

    A phase is stored by name, and the encoded state is what every hash is computed from, so
    the phases are all named here rather than one at a time as each slice reaches them: a name
    is cheaper to add now than to rename later, when a corpus of records depends on it.
    Phases whose behaviour has not landed yet have no rule in phases.py, and asking one for
    decisions is a loud error rather than an empty answer.

    The vocabulary is RULES.md section 4.4's phase table, word for word. That table is the
    pinned statement of which phases exist and what ends each one; an engine that invented its
    own names would be a second, contradicting account of the same rules, and the disagreement
    would live in every record. The names were made to match in card K-022, before the corpus
    grew, and the golden fixture was regenerated with the plugin's rules_version bumped.
    """

    SETUP_ROUND_1 = "setup_round_1"
    """The opening draft, seats ascending: one settlement and one road each."""
    SETUP_ROUND_2 = "setup_round_2"
    """The opening draft, seats descending, with the starting endowment."""
    TURN_PRODUCTION = "turn_production"
    """The current player rolls, or plays a development card first (FR-10.1)."""
    DISCARD = "discard"
    """Everybody over the limit discards, concurrently (FR-9.5, FR-12.1)."""
    ROBBER = "robber"
    """The current player moves the robber and may steal (FR-12.3, FR-12.4)."""
    ACTION = "action"
    """Build, trade, and play development cards, then end the turn (FR-11, FR-13, FR-14)."""
    ROAD_BUILDING = "road_building"
    """The two free roads of the Road Building card (FR-13.5)."""
    TRADE_RESPONSE = "trade_response"
    """Every non-offering player holding cards answers an offer (FR-14.4), and the offerer
    either cancels or chooses among the players who accepted (FR-14.5)."""
    TERMINAL = "terminal"
    """Somebody reached the target; the record is closed (FR-15)."""


@dataclass(frozen=True, slots=True)
class Supply:
    """The pieces one player has left to build with."""

    roads: int
    settlements: int
    cities: int


@dataclass(frozen=True, slots=True)
class Placed:
    """What is on the board: occupancy by site, with `NO_OWNER` where nothing stands."""

    settlements: tuple[int, ...]
    cities: tuple[int, ...]
    roads: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TradeOffer:
    """An open structured offer: what the offerer gives and what they want, by resource."""

    offerer: int
    give: tuple[int, ...]
    want: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CatanState:
    """One position in one game."""

    board: Board
    players: int
    phase: Phase
    phase_index: int
    turn: int
    round: int
    hands: tuple[tuple[int, ...], ...]
    bank: tuple[int, ...]
    supply: tuple[Supply, ...]
    placed: Placed
    setup_vertex: int
    dev_cards: tuple[tuple[int, ...], ...]
    dev_deck: tuple[str, ...]
    bought_this_turn: tuple[tuple[int, ...], ...]
    played_this_turn: tuple[int, ...]
    knights_played: tuple[int, ...]
    discards_pending: tuple[int, ...]
    offer: TradeOffer | None
    responses: tuple[int, ...]
    longest_road: int
    largest_army: int
    robber: int
    robber_stolen_at: int
    """The `phase_index` in which the robber phase's second step was resolved, or `NO_OWNER`.

    A phase rule sees only the state, so each step of a phase needs a mark of its own or the
    step can be taken again. The move has one; the steal needs this one, or a player with two
    neighbouring victims could rob for ever.
    """
    robber_moved_at: int
    """The `phase_index` the robber was last moved in, or `NO_OWNER` if never.

    The robber phase has two steps - move, then steal - and the first leaves no other trace: a
    robber that has just moved sits on a hex like one that has not. Recording the phase instance
    the move happened in is what lets the phase machine work out which step is open from the
    state alone, instead of remembering what it has already asked for.
    """
    dice: tuple[int, int] | None


def initial_state(board: Board, *, players: int, rng: RandomSource) -> CatanState:
    """The opening position: an empty board, a full bank, and a shuffled deck (draw D5)."""
    deck = rng.shuffle(list(CANONICAL_DECK), purpose=DEV_DECK_SHUFFLE)
    vertices = len(board.topology.vertices)
    edges = len(board.topology.edges)
    return CatanState(
        board=board,
        players=players,
        phase=Phase.SETUP_ROUND_1,
        phase_index=0,
        turn=0,
        round=0,
        hands=((0,) * RESOURCES,) * players,
        bank=(BANK_PER_RESOURCE,) * RESOURCES,
        supply=(Supply(*PIECES_PER_PLAYER),) * players,
        placed=Placed(
            settlements=(NO_OWNER,) * vertices,
            cities=(NO_OWNER,) * vertices,
            roads=(NO_OWNER,) * edges,
        ),
        setup_vertex=NO_OWNER,
        dev_cards=((0,) * len(CARD_ORDER),) * players,
        dev_deck=tuple(card.value for card in deck),
        bought_this_turn=((0,) * len(CARD_ORDER),) * players,
        played_this_turn=(0,) * players,
        knights_played=(0,) * players,
        discards_pending=(0,) * players,
        offer=None,
        responses=(0,) * players,
        longest_road=NO_OWNER,
        largest_army=NO_OWNER,
        robber=board.desert_hex,
        robber_moved_at=NO_OWNER,
        robber_stolen_at=NO_OWNER,
        dice=None,
    )


def encode_state(state: CatanState) -> JsonValue:
    """The state as canonical JSON. Total: every state this plugin can build encodes."""
    return {
        "bank": list(state.bank),
        "board": _encode_board(state.board),
        "bought_this_turn": [list(counts) for counts in state.bought_this_turn],
        "dev_cards": [list(counts) for counts in state.dev_cards],
        "dev_deck": list(state.dev_deck),
        "dice": None if state.dice is None else list(state.dice),
        "discards_pending": list(state.discards_pending),
        "hands": [list(counts) for counts in state.hands],
        "knights_played": list(state.knights_played),
        "largest_army": state.largest_army,
        "longest_road": state.longest_road,
        "offer": None if state.offer is None else _encode_offer(state.offer),
        "phase": state.phase.value,
        "phase_index": state.phase_index,
        "placed": _encode_placed(state.placed),
        "setup_vertex": state.setup_vertex,
        "played_this_turn": list(state.played_this_turn),
        "players": state.players,
        "responses": list(state.responses),
        "robber": state.robber,
        "robber_moved_at": state.robber_moved_at,
        "robber_stolen_at": state.robber_stolen_at,
        "round": state.round,
        "supply": [[item.roads, item.settlements, item.cities] for item in state.supply],
        "turn": state.turn,
    }


def decode_state(blob: JsonValue) -> CatanState:
    """Rebuild a state from its canonical JSON."""
    fields = _object(blob, "state")
    players = _integer(fields, "players", "state")
    board = _decode_board(_object(fields.get("board"), "state.board"))
    offer = fields.get("offer")
    dice = fields.get("dice")
    return CatanState(
        board=board,
        players=players,
        phase=Phase(_text(fields, "phase", "state")),
        phase_index=_integer(fields, "phase_index", "state"),
        turn=_integer(fields, "turn", "state"),
        round=_integer(fields, "round", "state"),
        hands=_counts(fields.get("hands"), players, RESOURCES, "state.hands"),
        bank=tuple(_integers(fields.get("bank"), "state.bank")),
        supply=_supply(fields.get("supply"), players),
        placed=_decode_placed(_object(fields.get("placed"), "state.placed"), board),
        setup_vertex=_integer(fields, "setup_vertex", "state"),
        dev_cards=_counts(fields.get("dev_cards"), players, len(CARD_ORDER), "state.dev_cards"),
        dev_deck=tuple(_strings(fields.get("dev_deck"), "state.dev_deck")),
        bought_this_turn=_counts(
            fields.get("bought_this_turn"), players, len(CARD_ORDER), "state.bought_this_turn"
        ),
        played_this_turn=tuple(_integers(fields.get("played_this_turn"), "state.played_this_turn")),
        knights_played=tuple(_integers(fields.get("knights_played"), "state.knights_played")),
        discards_pending=tuple(_integers(fields.get("discards_pending"), "state.discards_pending")),
        offer=None if offer is None else _decode_offer(_object(offer, "state.offer")),
        responses=tuple(_integers(fields.get("responses"), "state.responses")),
        longest_road=_integer(fields, "longest_road", "state"),
        largest_army=_integer(fields, "largest_army", "state"),
        robber=_integer(fields, "robber", "state"),
        robber_moved_at=_integer(fields, "robber_moved_at", "state"),
        robber_stolen_at=_integer(fields, "robber_stolen_at", "state"),
        dice=None if dice is None else _pair(dice, "state.dice"),
    )


def _encode_board(board: Board) -> JsonValue:
    return {
        "hexes": len(board.topology.hexes),
        "name": board.name,
        "ports": [
            {
                "edge": port.edge,
                "ratio": port.ratio,
                "resource": None if port.resource is None else port.resource.value,
            }
            for port in board.ports
        ],
        "terrain": [terrain.value for terrain in board.terrain],
        "token_start_hex": board.token_start_hex,
        "tokens": list(board.tokens),
    }


def _decode_board(fields: Mapping[str, JsonValue]) -> Board:
    if _integer(fields, "hexes", "state.board") != len(standard_topology().hexes):
        raise ValueError(
            "state.board.hexes does not match the standard board: this engine encodes "
            "one topology, and the record says otherwise"
        )
    ports = [
        Port(
            edge=_integer(_object(entry, "state.board.ports[]"), "edge", "port"),
            ratio=_integer(_object(entry, "state.board.ports[]"), "ratio", "port"),
            resource=_resource(_object(entry, "state.board.ports[]").get("resource")),
        )
        for entry in _sequence(fields.get("ports"), "state.board.ports")
    ]
    return Board(
        name=_text(fields, "name", "state.board"),
        topology=standard_topology(),
        terrain=tuple(Terrain(entry) for entry in _strings(fields.get("terrain"), "terrain")),
        tokens=tuple(_optional_integers(fields.get("tokens"), "state.board.tokens")),
        ports=tuple(ports),
        token_start_hex=_optional_integer(
            fields.get("token_start_hex"), "state.board.token_start_hex"
        ),
    )


def _resource(value: JsonValue) -> Resource | None:
    return None if value is None else Resource(str(value))


def _encode_placed(placed: Placed) -> JsonValue:
    return {
        "cities": _occupied(placed.cities),
        "roads": _occupied(placed.roads),
        "settlements": _occupied(placed.settlements),
    }


def _occupied(occupancy: Sequence[int]) -> JsonValue:
    return [[site, seat] for site, seat in enumerate(occupancy) if seat != NO_OWNER]


def _decode_placed(fields: Mapping[str, JsonValue], board: Board) -> Placed:
    return Placed(
        settlements=_occupancy(
            fields.get("settlements"), len(board.topology.vertices), "settlements"
        ),
        cities=_occupancy(fields.get("cities"), len(board.topology.vertices), "cities"),
        roads=_occupancy(fields.get("roads"), len(board.topology.edges), "roads"),
    )


def _occupancy(value: JsonValue, size: int, what: str) -> tuple[int, ...]:
    occupancy = [NO_OWNER] * size
    for entry in _sequence(value, f"state.placed.{what}"):
        site, seat = _pair(entry, f"state.placed.{what}[]")
        if not 0 <= site < size:
            raise ValueError(f"state.placed.{what} names site {site}, which does not exist")
        occupancy[site] = seat
    return tuple(occupancy)


def _encode_offer(offer: TradeOffer) -> JsonValue:
    return {"give": list(offer.give), "offerer": offer.offerer, "want": list(offer.want)}


def _decode_offer(fields: Mapping[str, JsonValue]) -> TradeOffer:
    return TradeOffer(
        offerer=_integer(fields, "offerer", "state.offer"),
        give=tuple(_integers(fields.get("give"), "state.offer.give")),
        want=tuple(_integers(fields.get("want"), "state.offer.want")),
    )


def _counts(value: JsonValue, players: int, width: int, what: str) -> tuple[tuple[int, ...], ...]:
    rows = [
        tuple(_integers(row, f"{what}[{index}]"))
        for index, row in enumerate(_sequence(value, what))
    ]
    if len(rows) != players:
        raise ValueError(f"{what} describes {len(rows)} players, expected {players}")
    if any(len(row) != width for row in rows):
        raise ValueError(f"{what} must hold {width} counts per player")
    return tuple(rows)


def _supply(value: JsonValue, players: int) -> tuple[Supply, ...]:
    rows = [Supply(*_triple(entry, "state.supply[]")) for entry in _sequence(value, "state.supply")]
    if len(rows) != players:
        raise ValueError(f"state.supply describes {len(rows)} players, expected {players}")
    return tuple(rows)


def _object(value: JsonValue, what: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{what} must be a JSON object, got {value!r}")
    return value


def _sequence(value: JsonValue, what: str) -> Sequence[JsonValue]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{what} must be a JSON array, got {value!r}")
    return value


def _integer(fields: Mapping[str, JsonValue], key: str, what: str) -> int:
    value = fields.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{what}.{key} must be an integer, got {value!r}")
    return value


def _text(fields: Mapping[str, JsonValue], key: str, what: str) -> str:
    value = fields.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{what}.{key} must be a string, got {value!r}")
    return value


def _integers(value: JsonValue, what: str) -> list[int]:
    numbers = []
    for entry in _sequence(value, what):
        if not isinstance(entry, int) or isinstance(entry, bool):
            raise ValueError(f"{what} must hold integers, got {entry!r}")
        numbers.append(entry)
    return numbers


def _optional_integers(value: JsonValue, what: str) -> list[int | None]:
    numbers: list[int | None] = []
    for entry in _sequence(value, what):
        if entry is None:
            numbers.append(None)
        elif isinstance(entry, int) and not isinstance(entry, bool):
            numbers.append(entry)
        else:
            raise ValueError(f"{what} must hold integers or null, got {entry!r}")
    return numbers


def _optional_integer(value: JsonValue, what: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{what} must be an integer or null, got {value!r}")
    return value


def _strings(value: JsonValue, what: str) -> list[str]:
    texts = []
    for entry in _sequence(value, what):
        if not isinstance(entry, str):
            raise ValueError(f"{what} must hold strings, got {entry!r}")
        texts.append(entry)
    return texts


def _triple(value: JsonValue, what: str) -> tuple[int, int, int]:
    numbers = _integers(value, what)
    if len(numbers) != 3:
        raise ValueError(f"{what} must hold three integers, got {len(numbers)}")
    return (numbers[0], numbers[1], numbers[2])


def _pair(value: JsonValue, what: str) -> tuple[int, int]:
    numbers = _integers(value, what)
    if len(numbers) != 2:
        raise ValueError(f"{what} must hold two integers, got {len(numbers)}")
    return (numbers[0], numbers[1])
