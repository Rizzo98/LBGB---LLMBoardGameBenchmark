"""The declared shape of a projection (PRD-v1 FR-18.3, FR-16.8; ARCHITECTURE.md 7.3).

There are two projections and not one - a player sees their own hand and cannot see anybody's; the
spectator sees every hand and has none of their own - so the declaration is a choice of two shapes
rather than one object with everything optional. `oneOf` says exactly one of them fits, which is
why an object carrying both `hand` and `hands` is refused: no observer is both.

The field *names* are not written down here. They come from the projection's own allow-list, so a
field cannot be projected without a declared shape (the test that every projected name has one
fails on the day somebody adds a field and forgets) and a shape cannot be declared for a field
that is never projected. The names are one fact stated once; what each name *holds* is what this
module adds.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Final

from lgbg.core.types import JsonSchema
from lgbg.games.catan.projection import (
    PLAYER_OBSERVATION_FIELDS,
    SPECTATOR_OBSERVATION_FIELDS,
)
from lgbg.games.catan.state import CARD_ORDER, RESOURCE_ORDER, DevCard, Phase

SEAT: Final[JsonSchema] = {"type": "integer", "minimum": -1}
"""A seat, or -1 for nobody: an award no player holds, and a site nobody has built on."""

COUNTS: Final[JsonSchema] = {
    "type": "object",
    "properties": {
        resource.value: {"type": "integer", "minimum": 0} for resource in RESOURCE_ORDER
    },
    "required": [resource.value for resource in RESOURCE_ORDER],
    "additionalProperties": False,
}
"""One count per resource, all five always written out: a hand is a composition, not a list."""

LIST: Final[JsonSchema] = {"type": "array", "items": {"type": "integer", "minimum": 0}}
"""A list of counts in seat order, which is how every public per-seat tally is written."""

RESOURCE_LIST: Final[JsonSchema] = {
    "type": "array",
    "items": {"type": "integer", "minimum": 0},
    "minItems": len(RESOURCE_ORDER),
    "maxItems": len(RESOURCE_ORDER),
}
"""A hand as the state holds it: one count per resource, in the pinned canonical order.

An observer's *own* hand is written by resource name (the shape above); every other hand is the
list the state keeps, which is why the two shapes are declared separately instead of one being
reused for both."""

CARDS: Final[JsonSchema] = {
    "type": "array",
    "items": {"type": "integer", "minimum": 0},
    "minItems": len(CARD_ORDER),
    "maxItems": len(CARD_ORDER),
}
"""How many of each development card a seat holds, in the deck's own canonical order."""

SITE: Final[JsonSchema] = {
    "type": "array",
    "items": {"type": "integer", "minimum": -1},
    "minItems": 2,
    "maxItems": 2,
}
"""One placed piece as [site, seat]: the identifier of the site and who owns it."""


def _per_seat(items: JsonSchema) -> JsonSchema:
    """One of something per seat, in seat order: the shape of every per-player tally."""
    return {"type": "array", "items": items, "minItems": 1}


def _at_least_one(items: JsonSchema) -> JsonSchema:
    return {"type": "array", "items": items, "minItems": 1}


_HEX: Final[JsonSchema] = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "minimum": 0},
        "terrain": {"type": "string"},
        "token": {"type": ["integer", "null"]},
    },
    "required": ["id", "terrain", "token"],
    "additionalProperties": False,
}
"""One hex as it is projected: where it is, what grows there, and its number or none."""

_PORT: Final[JsonSchema] = {
    "type": "object",
    "properties": {
        "edge": {"type": "integer", "minimum": 0},
        "ratio": {"type": "integer", "minimum": 2, "maximum": 3},
        "resource": {"type": ["string", "null"]},
    },
    "required": ["edge", "ratio", "resource"],
    "additionalProperties": False,
}
"""One harbour: its edge, its rate, and the resource it is printed for or none."""

_SITES: Final[JsonSchema] = {"type": "array", "items": SITE}
"""Every piece of one kind, as [site, seat], lists sorted by site because a record is read."""


FIELDS: Final[Mapping[str, JsonSchema]] = MappingProxyType(
    {
        "awards": {
            "type": "object",
            "properties": {"largest_army": SEAT, "longest_road": SEAT},
            "required": ["largest_army", "longest_road"],
            "additionalProperties": False,
        },
        "bank": COUNTS,
        "board": {
            "type": "object",
            "properties": {"hexes": _at_least_one(_HEX), "ports": _at_least_one(_PORT)},
            "required": ["hexes", "ports"],
            "additionalProperties": False,
        },
        "bought_this_turn": _per_seat(CARDS),
        "dev_cards": _per_seat(CARDS),
        "dev_deck": {
            "type": "array",
            "items": {"type": "string", "enum": [card.value for card in DevCard]},
        },
        "dice": {"type": ["array", "null"], "items": {"type": "integer", "minimum": 1}},
        "discards_pending": LIST,
        "hand": {"type": ["object", "null"]},
        "hand_counts": LIST,
        "hands": _per_seat(RESOURCE_LIST),
        "knights_played": LIST,
        "offer": {"type": ["object", "null"]},
        "phase": {"type": "string", "enum": [phase.value for phase in Phase]},
        "pieces": {
            "type": "object",
            "properties": {"cities": _SITES, "roads": _SITES, "settlements": _SITES},
            "required": ["cities", "roads", "settlements"],
            "additionalProperties": False,
        },
        "played_this_turn": LIST,
        "points": {"type": ["object", "null"]},
        "responses": {"type": "array", "items": {"type": "integer", "minimum": 0}},
        "robber": {"type": "integer", "minimum": 0},
        "round": {"type": "integer", "minimum": 0},
        "supply": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "integer", "minimum": 0}},
        },
        "turn": {"type": "integer", "minimum": 0},
    }
)
"""One shape per projected field, keyed by the name the projection writes it under."""


def observation_schema() -> JsonSchema:
    """The declared shape of both projections (FR-18.3, FR-16.8).

    One shape for the player's view and one for the spectator's, and exactly one of them fits any
    observation the engine produces. The two are built from the projection's own field sets, so
    this is the allow-list with a shape for each name rather than a second list to keep in step.
    """
    return {
        "oneOf": [_shape_of(PLAYER_OBSERVATION_FIELDS), _shape_of(SPECTATOR_OBSERVATION_FIELDS)]
    }


def _shape_of(names: Iterable[str]) -> JsonSchema:
    """One projection, as an object with every one of its fields and nothing else."""
    ordered = sorted(names)
    return {
        "type": "object",
        "properties": {name: FIELDS[name] for name in ordered},
        "required": ordered,
        "additionalProperties": False,
    }


def _per_resource(items: JsonSchema) -> JsonSchema:
    return {
        "type": "object",
        "properties": {resource.value: items for resource in RESOURCE_ORDER},
        "required": [resource.value for resource in RESOURCE_ORDER],
        "additionalProperties": False,
    }
