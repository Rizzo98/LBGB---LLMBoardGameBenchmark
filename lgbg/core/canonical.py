"""Canonical serialisation and state hashing (ARCHITECTURE.md section 6, section 6.1).

One function produces the bytes that are hashed and the bytes that are replayed (P8). Two
implementations would drift, and a drift between what we hash and what we replay is the
failure this module exists to make impossible.

The canonical form is fixed by three properties and nothing else:

- object keys sorted, lists left in the order the game gave them (the order is meaningful,
  so it is the game's job to make it deterministic),
- no insignificant whitespace,
- ASCII escaped, so a record means the same thing whatever the platform encoding.

Two further rules here are guards rather than formatting. Floats are rejected, because
float formatting is not stable across platforms and versions and state is required to be
integral (ARCHITECTURE.md section 6, clause 2). Object keys must be strings, because
'json.dumps' would silently convert an integer key to a string and let two different
states collide.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final, Protocol

from lgbg.core.types import JsonValue

TRUNCATED_HASH_HEX_CHARS: Final[int] = 16
"""Width of every recorded state hash, in hex characters (64 bits).

A single named constant, used everywhere, with no inline literals (FR-1.4). Wide enough
that collision-driven false verification is implausible, short enough to keep records
readable. Confirmed as PRD-v1 open question Q2.
"""


class CanonicalJsonError(TypeError):
    """A value cannot be canonically serialised, so it must never reach the record."""


class EncodesState(Protocol):
    """The slice of the game plugin interface that hashing needs (ARCHITECTURE.md 6.1).

    Structural, so a game plugin satisfies it without importing anything extra.
    """

    def encode_state(self, state: Any) -> JsonValue: ...


def normalise(value: object) -> JsonValue:
    """Convert a value to plain JSON types, rejecting anything that cannot be canonical."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, float):
        raise CanonicalJsonError(
            "float values are not canonical: float formatting is not stable across "
            f"platforms, and state must be integral (got {value!r})"
        )
    if isinstance(value, Mapping):
        mapping: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJsonError(
                    f"object key {key!r} is not a string; JSON object keys must be strings"
                )
            mapping[key] = normalise(item)
        return mapping
    if isinstance(value, list | tuple):
        return [normalise(item) for item in value]
    raise CanonicalJsonError(
        f"value of type {type(value).__name__} is not JSON and cannot be canonicalised"
    )


def to_canonical_json(value: object) -> str:
    """Serialise a value to the canonical form. See the module docstring for the rules."""
    return json.dumps(
        normalise(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def to_wire_json(value: object) -> str:
    """Serialise an HTTP request body, exactly as the adapter sends it.

    This is deliberately not the canonical form. A provider's wire format uses JSON numbers -
    temperature and top-p are floats - while a record may not: the canonical serialiser refuses
    floats because their formatting is not stable, and a record has to be. A request body is not a
    record; it is evidence of the bytes that were sent, so the only rule here is that the bytes
    this function returns are the bytes the adapter puts on the wire (FR-5.4).
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(value: object) -> bytes:
    """The canonical bytes hashed by 'hash_state'; the same bytes replay consumes."""
    return to_canonical_json(value).encode("utf-8")


def _truncated_digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()[:TRUNCATED_HASH_HEX_CHARS]


def hash_state(state: object, game: EncodesState) -> str:
    """Hash a game state through its plugin's encoder (ARCHITECTURE.md section 6.1)."""
    return _truncated_digest(canonical_bytes(game.encode_state(state)))
